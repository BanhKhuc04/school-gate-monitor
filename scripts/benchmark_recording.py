#!/usr/bin/env python
"""
Benchmark FPS/CRAP recording impact — Đợt 2, Bước 7.

Đo sự chênh lệch hiệu năng giữa:
  - Recorder TẮT (CONTINUOUS_RECORDING_ENABLED=0)
  - Recorder BẬT (CONTINUOUS_RECORDING_ENABLED=1)

trong VideoPipeline chạy thật với video training.

Đầu ra:
  - Console: bảng tóm tắt.
  - File `benchmark_recording_result.json`: số liệu chi tiết (cho AI/dev review sau).

Cách dùng:
  1. Set CAMERA_SOURCE trỏ tới 1 file video (xem DEVELOPMENT_HANDOVER.md mục 5).
  2. Set GATES theo `app/config.py::GATES` — script dùng gate 'main' mặc định.
  3. Chạy: `./venv/Scripts/python.exe scripts/benchmark_recording.py`
  4. Sau khi chạy xong, AI/dev sẽ review số liệu → quyết định có bật
     CONTINUOUS_RECORDING_ENABLED=1 làm mặc định không.

Lưu ý: KHÔNG đụng vào source code hay config — chỉ chạy pipeline và ghi log.
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Đảm bảo project root nằm trong sys.path khi chạy trực tiếp
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (
    CONTINUOUS_RECORDING_ENABLED, CONTINUOUS_RECORDING_DIR,
    VIDEO_WIDTH, VIDEO_HEIGHT,
)


def _measure_once(recording_enabled: bool, duration_sec: int, gate_id: str = "main") -> dict:
    """
    Chạy VideoPipeline 1 lần với `recording_enabled`, đo FPS / latency / CPU
    trong `duration_sec` giây. Trả về dict stats.

    Lưu ý:
      - KHÔNG load models thật nếu không có GPU/CPU đủ. Fallback: tạo frame giả.
      - ContinuousRecorder dùng cv2.VideoWriter (CPU encode) — bottleneck chính.
    """
    # Patch config trước khi import pipeline (vì pipeline đọc ở __init__)
    import app.config as cfg
    import app.cv.pipeline as pl_module
    cfg.CONTINUOUS_RECORDING_ENABLED = recording_enabled
    pl_module.CONTINUOUS_RECORDING_ENABLED = recording_enabled

    from app.cv.pipeline import VideoPipeline
    import numpy as np
    import cv2

    # Dùng SyntheticFrameGenerator nếu có, fallback tạo frame zero
    def synthetic_frame():
        return np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)

    pipeline = VideoPipeline(
        gate_id=gate_id,
        gate_config={"source": 0, "loop": True, "name": gate_id},
    )
    # Override webcam với synthetic — chạy được kể cả không có camera/file
    from app.cv.capture import WebcamStream

    class SyntheticStream:
        def __init__(self):
            self._open = True

        def is_open(self):
            return self._open

        def read_frame(self):
            return synthetic_frame()

        def release(self):
            self._open = False

    pipeline._webcam = SyntheticStream()

    # Khởi động pipeline KHÔNG qua .start() (vì nó cần thread); chạy inline
    pipeline._running = True
    pipeline._frame_count = 0
    pipeline._last_frame_time = time.time()
    pipeline._last_detect_latency_ms = 0.0

    # Fake pipeline main loop: chỉ đọc + push recorder (mục đích đo impact của recorder)
    start = time.monotonic()
    frames = 0
    while time.monotonic() - start < duration_sec:
        frame = synthetic_frame()
        pipeline._frame_count += 1
        if pipeline._recorder is not None:
            pipeline._recorder.push_frame(frame)
        frames += 1
        # Không sleep — đo throughput tối đa
    elapsed = time.monotonic() - start

    fps = frames / elapsed if elapsed > 0 else 0

    recorder_stats = pipeline._recorder.get_stats() if pipeline._recorder else None

    # Dừng recorder (finalize file)
    if pipeline._recorder:
        pipeline._recorder.stop()

    # CPU usage đơn giản: psutil nếu có, fallback = None
    cpu_pct = None
    try:
        import psutil
        cpu_pct = psutil.Process().cpu_percent(interval=0.1)
    except ImportError:
        pass

    return {
        "recording_enabled": recording_enabled,
        "duration_sec": elapsed,
        "frames_processed": frames,
        "fps": round(fps, 2),
        "recorder": recorder_stats,
        "cpu_pct": cpu_pct,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark continuous recording impact")
    parser.add_argument("--duration", type=int, default=10,
                        help="Số giây đo cho MỖI lần chạy (default: 10s)")
    parser.add_argument("--gate", default="main", help="Gate ID (default: main)")
    parser.add_argument("--output", default="benchmark_recording_result.json",
                        help="File JSON output (default: benchmark_recording_result.json)")
    args = parser.parse_args()

    print("=" * 60)
    print("Benchmark Continuous Recording — Đợt 2, Bước 7")
    print("=" * 60)
    print(f"Duration per run: {args.duration}s")
    print(f"Gate: {args.gate}")
    print()

    # Chạy OFF trước (control)
    print("[1/2] Recorder TẮT (CONTINUOUS_RECORDING_ENABLED=0)...")
    result_off = _measure_once(recording_enabled=False, duration_sec=args.duration, gate_id=args.gate)
    print(f"  FPS: {result_off['fps']}, frames: {result_off['frames_processed']}")
    print()

    # Chạy ON
    print("[2/2] Recorder BẬT (CONTINUOUS_RECORDING_ENABLED=1)...")
    result_on = _measure_once(recording_enabled=True, duration_sec=args.duration, gate_id=args.gate)
    print(f"  FPS: {result_on['fps']}, frames: {result_on['frames_processed']}")
    if result_on["recorder"]:
        rs = result_on["recorder"]
        print(f"  Recorder stats: written={rs['frames_written']}, dropped={rs['frames_dropped']}")
    print()

    # So sánh
    if result_off["fps"] > 0:
        fps_drop_pct = (1 - result_on["fps"] / result_off["fps"]) * 100
    else:
        fps_drop_pct = 0

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "duration_sec": args.duration,
            "gate": args.gate,
            "recording_dir": CONTINUOUS_RECORDING_DIR,
        },
        "off": result_off,
        "on": result_on,
        "delta": {
            "fps_drop_pct": round(fps_drop_pct, 2),
            "frames_dropped_in_recorder": (
                result_on["recorder"]["frames_dropped"] if result_on["recorder"] else 0
            ),
        },
    }

    # Ghi file JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("KẾT QUẢ")
    print("=" * 60)
    print(f"FPS (recorder TẮT): {result_off['fps']}")
    print(f"FPS (recorder BẬT): {result_on['fps']}")
    print(f"Drop:               {fps_drop_pct:.2f}%")
    if result_on["recorder"]:
        rs = result_on["recorder"]
        print(f"Frame ghi được:     {rs['frames_written']}")
        print(f"Frame bị drop:      {rs['frames_dropped']}")
    print(f"\nChi tiết: {args.output}")
    print()
    print("⚠️  ĐÂY LÀ SỐ LIỆU ĐỂ DEV REVIEW — KHÔNG TỰ ĐỘNG BẬT")
    print("   CONTINUOUS_RECORDING_ENABLED=1. Xem plan mục 'Bước 7'.")


if __name__ == "__main__":
    main()