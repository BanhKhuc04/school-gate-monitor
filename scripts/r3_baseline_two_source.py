"""
R3 — Baseline hai nguồn với 2 video độc lập (Owner A).

Theo handoff §3 R3:
- Dùng 2 video độc lập từ `C:\\Users\\khucv\\Downloads\\tranning\\` làm nguồn runtime.
- Đo frame age, FPS, capture/drop/queue wait, detect (helmet/plate/person),
  OCR, encode latency p50/p95, CPU/RAM, Torch allocated/reserved và VRAM.
- Kiểm owner fairness và queue đầy.
- Warmup tách khỏi kết quả. Ghi config/hash vào báo cáo.
- Output: `RUNTIME_BASELINE.json` + báo cáo tái lập.

KHÔNG chạy benchmark này song song full regression. Nếu model nặng, hãy
chạy trên QA env với các flag tắt (xem conftest.py).
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set QA isolation flags BEFORE import app modules
os.environ.setdefault("QA_MODE", "1")
os.environ.setdefault("CV_PIPELINES_ENABLED", "0")
os.environ.setdefault("BACKUP_ENABLED", "0")
os.environ.setdefault("CLEANUP_ENABLED", "0")

from app.config import (
    DEVICE, DETECT_WIDTH, DETECT_HEIGHT, VIDEO_WIDTH, VIDEO_HEIGHT,
    HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
)


VIDEO_DIR = Path(r"C:\Users\khucv\Downloads\tranning")


def list_candidate_videos() -> List[Path]:
    """Liệt kê tất cả .mp4 trong thư mục tranning theo tên sort."""
    if not VIDEO_DIR.exists():
        return []
    return sorted([p for p in VIDEO_DIR.glob("*.mp4") if p.is_file()])


def select_two_videos(explicit: Optional[List[str]] = None) -> Tuple[Optional[Path], Optional[Path]]:
    """Chọn 2 video để chạy song song. Ưu tiên arg --videos nếu có."""
    if explicit:
        paths = [Path(p) for p in explicit[:2]]
        for p in paths:
            if not p.exists():
                return None, None
        return paths[0], (paths[1] if len(paths) > 1 else None)
    cands = list_candidate_videos()
    if len(cands) >= 2:
        return cands[0], cands[1]
    if len(cands) == 1:
        return cands[0], None
    return None, None


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(values, p))


def measure_capture_only(path: Path, max_frames: int = 200) -> Dict[str, Any]:
    """Đo capture: thời gian đọc frame, FPS thực tế, số frame đến EOF."""
    if not path or not path.exists():
        return {"error": f"video not found: {path}"}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"error": f"cannot open: {path}"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    times_ms: List[float] = []
    drop_count = 0
    frames_read = 0
    t_start = time.perf_counter()
    for _ in range(max_frames):
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret:
            drop_count += 1
            if drop_count > 5:
                break
            continue
        # Simulate downstream consumption — không xử lý gì thêm ở đây
        _ = frame.shape
        times_ms.append((time.perf_counter() - t0) * 1000.0)
        frames_read += 1
    total_elapsed = (time.perf_counter() - t_start) or 1e-9
    cap.release()
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "fps_declared": fps,
        "n_total_declared": n_total,
        "width": width,
        "height": height,
        "frames_read": frames_read,
        "drop_count": drop_count,
        "elapsed_sec": round(total_elapsed, 3),
        "fps_measured": round(frames_read / total_elapsed, 2),
        "capture_p50_ms": round(percentile(times_ms, 50), 3),
        "capture_p95_ms": round(percentile(times_ms, 95), 3),
        "capture_p99_ms": round(percentile(times_ms, 99), 3),
        "capture_mean_ms": round(statistics.mean(times_ms) if times_ms else 0.0, 3),
    }


def measure_encode_only(frames: List[np.ndarray]) -> Dict[str, Any]:
    """Đo encode JPEG latency cho 1 lần/frame (giả định đã resize)."""
    if not frames:
        return {"frames": 0}
    times: List[float] = []
    for f in frames:
        t0 = time.perf_counter()
        _, _ = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 85])
        times.append((time.perf_counter() - t0) * 1000.0)
    return {
        "frames": len(frames),
        "encode_p50_ms": round(percentile(times, 50), 3),
        "encode_p95_ms": round(percentile(times, 95), 3),
        "encode_mean_ms": round(statistics.mean(times), 3),
    }


def _try_import_optional() -> Dict[str, Any]:
    """Thử import torch + psutil để đo GPU/CPU/RAM. Nếu thiếu → đánh dấu unavailable."""
    info: Dict[str, Any] = {}
    try:
        import psutil  # noqa
        info["psutil"] = True
        info["cpu_count"] = psutil.cpu_count()
        info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        info["ram_total_gb"] = round(vm.total / 1024**3, 2)
        info["ram_used_gb"] = round(vm.used / 1024**3, 2)
        info["ram_percent"] = vm.percent
    except ImportError:
        info["psutil"] = False
    try:
        import torch  # noqa
        info["torch"] = True
        info["torch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["torch_allocated_mb"] = round(torch.cuda.memory_allocated() / 1024**2, 1)
            info["torch_reserved_mb"] = round(torch.cuda.memory_reserved() / 1024**2, 1)
            try:
                info["vram_total_mb"] = round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**2, 1
                )
            except Exception:
                pass
    except ImportError:
        info["torch"] = False
    return info


def run_two_source_benchmark(
    front: Path, rear: Optional[Path], max_frames: int, workers: int
) -> Dict[str, Any]:
    """Chạy benchmark 2 nguồn song song với ThreadPoolExecutor.

    Mỗi worker đo capture riêng; đo encode + resource chung ở main.
    """
    print(f"Front: {front}")
    if rear:
        print(f"Rear:  {rear}")
    else:
        print("Rear:  (skipped — chỉ 1 video)")

    # Đo resource trước
    res_before = _try_import_optional()

    # Warmup 5 frame (single-thread, không tính vào result)
    cap = cv2.VideoCapture(str(front))
    warm_frames: List[np.ndarray] = []
    for _ in range(5):
        ret, fr = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, fr = cap.read()
        if ret and fr is not None:
            warm_frames.append(cv2.resize(fr, (DETECT_WIDTH, DETECT_HEIGHT)))
    cap.release()

    # Đo 2 nguồn song song
    tasks = [front]
    if rear:
        tasks.append(rear)
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(measure_capture_only, p, max_frames): p for p in tasks}
        per_source: Dict[str, Any] = {}
        for fut, p in futures.items():
            per_source[p.name] = fut.result()
    t_parallel = time.perf_counter() - t_start

    # Đo encode JPEG (chung) — lấy 50 frame từ front
    cap = cv2.VideoCapture(str(front))
    encode_frames: List[np.ndarray] = []
    for _ in range(50):
        ret, fr = cap.read()
        if not ret:
            break
        encode_frames.append(cv2.resize(fr, (DETECT_WIDTH, DETECT_HEIGHT)))
    cap.release()
    encode_stats = measure_encode_only(encode_frames)

    # Đo resource sau
    res_after = _try_import_optional()

    summary: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "device": DEVICE,
            "detect_size": [DETECT_WIDTH, DETECT_HEIGHT],
            "video_size": [VIDEO_WIDTH, VIDEO_HEIGHT],
            "max_frames_per_source": max_frames,
            "workers": workers,
            "front_video": str(front),
            "rear_video": str(rear) if rear else None,
        },
        "isolation_flags": {
            "QA_MODE": os.environ.get("QA_MODE"),
            "CV_PIPELINES_ENABLED": os.environ.get("CV_PIPELINES_ENABLED"),
            "BACKUP_ENABLED": os.environ.get("BACKUP_ENABLED"),
            "CLEANUP_ENABLED": os.environ.get("CLEANUP_ENABLED"),
        },
        "resources_before": res_before,
        "resources_after": res_after,
        "parallel_capture_elapsed_sec": round(t_parallel, 3),
        "per_source_capture": per_source,
        "encode_jpeg": encode_stats,
        "kpi_check": {},
    }

    # KPI gates (theo handoff §4)
    front_capture = per_source.get(front.name, {})
    fps_front = front_capture.get("fps_measured", 0.0)
    summary["kpi_check"]["front_fps_geq_15"] = fps_front >= 15.0
    summary["kpi_check"]["note"] = (
        "KPI 15 FPS preview chỉ đạt khi không có AI/OCR/pose cùng lúc. "
        "AI ≥5 FPS đo riêng ở R3-ai/benchmark_inference.py."
    )

    return summary


def write_baseline(summary: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="R3 — Baseline hai nguồn")
    parser.add_argument(
        "--videos", nargs="*", default=None,
        help="Đường dẫn 2 video (front rear). Mặc định lấy 2 file đầu trong tranning/."
    )
    parser.add_argument(
        "--max-frames", type=int, default=200,
        help="Số frame tối đa đọc từ mỗi nguồn (mặc định 200)."
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Số thread song song (mặc định 2)."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("tasks/task-05/R3_BASELINE_TWO_SOURCE.json"),
        help="File JSON output (mặc định tasks/task-05/R3_BASELINE_TWO_SOURCE.json)."
    )
    args = parser.parse_args()

    front, rear = select_two_videos(args.videos)
    if not front:
        print("ERROR: Không tìm thấy video. Kiểm tra C:\\Users\\khucv\\Downloads\\tranning\\")
        return 1
    print(f"Front: {front}")
    print(f"Rear:  {rear if rear else '(none — only 1 video available)'}")
    print()

    summary = run_two_source_benchmark(front, rear, args.max_frames, args.workers)

    # In summary console
    print("=" * 60)
    print("R3 BASELINE — TWO SOURCE")
    print("=" * 60)
    print(f"Parallel capture elapsed: {summary['parallel_capture_elapsed_sec']}s")
    for name, stats in summary["per_source_capture"].items():
        if "error" in stats:
            print(f"  {name}: ERROR {stats['error']}")
            continue
        print(
            f"  {name}: fps={stats['fps_measured']} p50={stats['capture_p50_ms']}ms "
            f"p95={stats['capture_p95_ms']}ms frames={stats['frames_read']} drops={stats['drop_count']}"
        )
    print(f"Encode JPEG: {summary['encode_jpeg']}")
    if summary["resources_after"].get("psutil"):
        print(
            f"Resources after: cpu%={summary['resources_after']['cpu_percent']} "
            f"ram%={summary['resources_after']['ram_percent']}"
        )
    if summary["resources_after"].get("torch") and summary["resources_after"].get("cuda_available"):
        print(
            f"GPU after: torch_alloc={summary['resources_after'].get('torch_allocated_mb')}MB "
            f"vram_total={summary['resources_after'].get('vram_total_mb')}MB"
        )

    write_baseline(summary, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
