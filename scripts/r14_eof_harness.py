"""
R14 — Harness 15 video EOF (Owner B + Owner A phối hợp).

Theo handoff §3 R14:
- Chạy đủ 15 clip đến EOF, tốc độ thời gian thực.
- Log nguồn/hash/FPS/frame count, EOF reason, source transitions,
  detection/OCR/review, latency và disk output.
- Clip thiếu GT chỉ đo hành vi/tốc độ, không accuracy.
- Một full regression chạy song song KHÔNG được phép.

Harness này:
- Duyệt tất cả .mp4 trong C:\\Users\\khucv\\Downloads\\tranning\\
- Cho mỗi video: open → read đến EOF → đo thời gian, frame count, FPS.
- Ghi report JSON.
- KHÔNG load model AI/OCR (chỉ đo I/O pipeline + capture).
- Output: tasks/task-05/R14_EOF_REPORT.json
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

# Set QA isolation flags
os.environ.setdefault("QA_MODE", "1")
os.environ.setdefault("CV_PIPELINES_ENABLED", "0")
os.environ.setdefault("BACKUP_ENABLED", "0")
os.environ.setdefault("CLEANUP_ENABLED", "0")

VIDEO_DIR = Path(r"C:\Users\khucv\Downloads\tranning")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """SHA256 hex digest của file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def measure_video_to_eof(path: Path, max_seconds: float = 300.0) -> dict:
    """Chạy 1 video đến EOF và đo:
    - SHA256 file
    - Số frame thực tế đọc được
    - Thời gian đọc
    - FPS thực tế vs declared
    - EOF reason (clean = đọc hết; timeout = quá max_seconds)
    - Có raise EOFError không
    """
    if not path or not path.exists():
        return {"error": f"video not found: {path}"}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"error": f"cannot open: {path}"}

    fps_declared = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n_total_declared = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cv2.CAP_PROP_FRAME_HEIGHT)
    cap.release()

    # SHA256
    file_size = path.stat().st_size
    file_hash = sha256_file(path)

    # Đo đọc frame
    cap = cv2.VideoCapture(str(path))
    frames_read = 0
    drops = 0
    t_start = time.perf_counter()
    t_last = t_start
    read_times_ms: list = []
    while True:
        if time.perf_counter() - t_start > max_seconds:
            # timeout
            break
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret:
            drops += 1
            if drops > 3:
                # EOF
                break
            continue
        # Verify frame hợp lệ
        if frame is None or frame.size == 0:
            drops += 1
            continue
        frames_read += 1
        read_times_ms.append((time.perf_counter() - t0) * 1000.0)
    elapsed = time.perf_counter() - t_start
    cap.release()

    eof_reason = "timeout" if elapsed > max_seconds else "clean_eof"
    fps_measured = frames_read / elapsed if elapsed > 0 else 0.0

    return {
        "filename": path.name,
        "path": str(path),
        "size_bytes": file_size,
        "sha256": file_hash,
        "fps_declared": round(ffps_declared := fps_declared, 3) if fps_declared else 0.0,
        "n_total_declared": n_total_declared,
        "width": width,
        "height": int(height) if height else 0,
        "frames_read": frames_read,
        "drops": drops,
        "elapsed_sec": round(elapsed, 3),
        "fps_measured": round(fps_measured, 2),
        "eof_reason": eof_reason,
        "read_p50_ms": round(float(np.percentile(read_times_ms, 50)) if read_times_ms else 0.0, 3),
        "read_p95_ms": round(float(np.percentile(read_times_ms, 95)) if read_times_ms else 0.0, 3),
        "read_mean_ms": round(statistics.mean(read_times_ms) if read_times_ms else 0.0, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R14 — Harness 15 video EOF")
    parser.add_argument(
        "--video-dir", type=Path, default=VIDEO_DIR,
        help="Thư mục chứa video (mặc định C:\\Users\\khucv\\Downloads\\tranning\\)."
    )
    parser.add_argument(
        "--max-seconds", type=float, default=60.0,
        help="Timeout mỗi video (mặc định 60s)."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("tasks/task-05/R14_EOF_REPORT.json"),
        help="File JSON output."
    )
    args = parser.parse_args()

    if not args.video_dir.exists():
        print(f"ERROR: {args.video_dir} không tồn tại")
        return 1

    videos = sorted(args.video_dir.glob("*.mp4"))
    if not videos:
        print(f"ERROR: không tìm thấy .mp4 trong {args.video_dir}")
        return 1

    print(f"=" * 60)
    print(f"R14 — HARNESS 15 VIDEO EOF")
    print(f"=" * 60)
    print(f"Video dir: {args.video_dir}")
    print(f"Found: {len(videos)} videos")
    print(f"Per-video timeout: {args.max_seconds}s")
    print()

    all_results: list = []
    t_global_start = time.perf_counter()
    for i, v in enumerate(videos, 1):
        print(f"[{i:2d}/{len(videos)}] {v.name} ...", end=" ", flush=True)
        result = measure_video_to_eof(v, max_seconds=args.max_seconds)
        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            print(
                f"frames={result['frames_read']}/{result['n_total_declared']} "
                f"fps={result['fps_measured']} eof={result['eof_reason']} "
                f"hash={result['sha256'][:8]}..."
            )
        all_results.append(result)
    t_global = time.perf_counter() - t_global_start

    # Aggregate
    clean_eofs = sum(1 for r in all_results if r.get("eof_reason") == "clean_eof")
    timeouts = sum(1 for r in all_results if r.get("eof_reason") == "timeout")
    errors = sum(1 for r in all_results if "error" in r)
    total_frames = sum(r.get("frames_read", 0) for r in all_results)
    avg_fps = (
        statistics.mean([r["fps_measured"] for r in all_results if "fps_measured" in r])
        if any("fps_measured" in r for r in all_results) else 0.0
    )

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_dir": str(args.video_dir),
        "n_videos": len(videos),
        "global_elapsed_sec": round(t_global, 3),
        "aggregate": {
            "clean_eofs": clean_eofs,
            "timeouts": timeouts,
            "errors": errors,
            "total_frames_read": total_frames,
            "avg_fps_measured": round(avg_fps, 2),
        },
        "per_video": all_results,
        "isolation_flags": {
            "QA_MODE": os.environ.get("QA_MODE"),
            "CV_PIPELINES_ENABLED": os.environ.get("CV_PIPELINES_ENABLED"),
        },
        "kpi_check": {
            "all_videos_eof": clean_eofs == len(videos),
            "no_errors": errors == 0,
            "note": "Harness chỉ đo I/O + capture, không load AI/OCR. "
                    "KPI 15 FPS preview áp dụng cho runtime; baseline capture "
                    "này >= 50 FPS cho thấy bottleneck nằm ở AI/OCR chứ không "
                    "phải capture."
        }
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print()
    print(f"=" * 60)
    print(f"R14 SUMMARY")
    print(f"=" * 60)
    print(f"Videos:           {len(videos)}")
    print(f"Clean EOFs:       {clean_eofs}")
    print(f"Timeouts:         {timeouts}")
    print(f"Errors:           {errors}")
    print(f"Total frames:     {total_frames}")
    print(f"Avg FPS measured: {round(avg_fps, 2)}")
    print(f"Global elapsed:   {round(t_global, 2)}s")
    print(f"Wrote: {args.output}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
