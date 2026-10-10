"""
Benchmark từng công đoạn của pipeline trên một nguồn video.

Chạy: python scripts/benchmark_pipeline.py

Đợt A2: Đo riêng capture, detect (helmet/plate/person), tracking, pose,
OCR và encode trên một video đại diện. Ghi kết quả ra JSON + console.
"""
import os
import sys
import json
import time
import statistics
import cv2
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import (
    DEVICE, DETECT_WIDTH, DETECT_HEIGHT, VIDEO_WIDTH, VIDEO_HEIGHT,
    HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
)
from app.cv.detector import HelmetPlateDetector
from app.cv.ocr import _get_reader, read_plate_detailed


def find_test_video():
    """Tìm video test đại diện — ưu tiên video tranning nếu có."""
    candidates = [
        r"C:\Users\khucv\Downloads\tranning\b2_v1.mp4",
        r"C:\Users\khucv\Downloads\tranning\b2_v1_001.mp4",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def measure_capture(cap, n_frames=100):
    """Đo thời gian đọc frame từ video."""
    times = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                break
        times.append((time.perf_counter() - t0) * 1000)
    return times


def measure_detect(detector, frames):
    """Đo thời gian inference trên nhiều frame."""
    times = []
    for frame in frames:
        t0 = time.perf_counter()
        _ = detector.detect(frame)
        times.append((time.perf_counter() - t0) * 1000)
    return times


def measure_ocr(crops):
    """Đo thời gian OCR trên nhiều crop ảnh biển số."""
    reader = _get_reader()
    times = []
    for crop in crops:
        t0 = time.perf_counter()
        try:
            _ = read_plate_detailed(crop)
        except Exception:
            pass
        times.append((time.perf_counter() - t0) * 1000)
    return times


def measure_encode(frames):
    """Đo thời gian encode JPEG."""
    times = []
    for frame in frames:
        t0 = time.perf_counter()
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        times.append((time.perf_counter() - t0) * 1000)
    return times


def main():
    print("=" * 60)
    print("BENCHMARK PIPELINE — Đợt A2")
    print("=" * 60)
    print(f"Device: {DEVICE}")
    print(f"DETECT: {DETECT_WIDTH}x{DETECT_HEIGHT} | VIDEO: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    print()

    video_path = find_test_video()
    if video_path:
        print(f"Video: {video_path}")
        cap = cv2.VideoCapture(video_path)
        n_test = min(200, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    else:
        print("No test video found — using synthetic frames")
        cap = None
        n_test = 100

    warmup_frames = []
    test_frames = []
    test_crops = []

    # Warmup + collect frames
    for i in range(n_test + 5):
        if cap:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    break
        else:
            frame = np.random.randint(0, 255, (VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)

        resized = cv2.resize(frame, (DETECT_WIDTH, DETECT_HEIGHT))

        if i < 5:
            warmup_frames.append(resized)
        else:
            test_frames.append(resized)

        # Simulate plate crop for OCR test (random sized crop)
        if i % 5 == 0 and frame is not None:
            h, w = frame.shape[:2]
            x1 = max(0, w // 4)
            y1 = max(0, h // 4)
            x2 = min(w, w * 3 // 4)
            y2 = min(h, h * 3 // 4)
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0 and crop.shape[0] >= 20 and crop.shape[1] >= 40:
                test_crops.append(crop)

    if cap:
        cap.release()

    print(f"Frames for testing: {len(test_frames)}")
    print(f"Crops for OCR test: {len(test_crops)}")
    print()

    # ---- Load models ----
    print("Loading models...")
    t0 = time.perf_counter()
    helmet_det = HelmetPlateDetector(HELMET_MODEL_PATH, conf_threshold=HELMET_CONF_THRESHOLD)
    t_helmet = (time.perf_counter() - t0) * 1000
    print(f"  Helmet model: {t_helmet:.1f}ms to load")

    t0 = time.perf_counter()
    plate_det = HelmetPlateDetector(PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD)
    t_plate = (time.perf_counter() - t0) * 1000
    print(f"  Plate model: {t_plate:.1f}ms to load")

    t0 = time.perf_counter()
    person_det = HelmetPlateDetector(PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD)
    t_person = (time.perf_counter() - t0) * 1000
    print(f"  Person model: {t_person:.1f}ms to load")

    t0 = time.perf_counter()
    reader = _get_reader()
    t_ocr_load = (time.perf_counter() - t0) * 1000
    print(f"  OCR reader: {t_ocr_load:.1f}ms to load")
    print()

    # Warmup models
    for wf in warmup_frames:
        _ = helmet_det.detect(wf)
        _ = plate_det.detect(wf)
        _ = person_det.detect(wf)

    # ---- Measure capture ----
    if video_path:
        print("Measuring capture...")
        cap2 = cv2.VideoCapture(video_path)
        cap_times = measure_capture(cap2, n_frames=min(100, n_test))
        cap2.release()
    else:
        cap_times = []

    # ---- Measure detections ----
    print("Measuring helmet detection...")
    helmet_times = measure_detect(helmet_det, test_frames)

    print("Measuring plate detection...")
    plate_times = measure_detect(plate_det, test_frames)

    print("Measuring person detection...")
    person_times = measure_detect(person_det, test_frames)

    # ---- Measure OCR ----
    print("Measuring OCR...")
    if test_crops:
        ocr_times = measure_ocr(test_crops[:50])  # Limit to 50 for speed
    else:
        ocr_times = []

    # ---- Measure encode ----
    print("Measuring JPEG encode...")
    encode_times = measure_encode(test_frames[:100])

    # ---- Results ----
    print()
    print("=" * 60)
    print("RESULTS (ms)")
    print("=" * 60)

    results = {}

    def stats(times, label):
        if not times:
            return None
        p50 = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else max(times)
        p99 = sorted(times)[int(len(times) * 0.99)] if len(times) >= 100 else max(times)
        mean = statistics.mean(times)
        print(f"  {label:30s} mean={mean:6.1f}ms  p50={p50:6.1f}ms  p95={p95:6.1f}ms  p99={p99:6.1f}ms  n={len(times)}")
        return {'mean': mean, 'p50': p50, 'p95': p95, 'p99': p99, 'n': len(times)}

    print()
    print("Per-operation timing:")
    if cap_times:
        results['capture'] = stats(cap_times, "Capture frame from source")
    results['helmet'] = stats(helmet_times, "Helmet detection (1 model)")
    results['plate'] = stats(plate_times, "Plate detection (1 model)")
    results['person'] = stats(person_times, "Person detection (1 model)")
    results['ocr'] = stats(ocr_times, "OCR (EasyOCR per crop)")
    results['encode'] = stats(encode_times, "JPEG encode")

    # Combined detection estimate
    print()
    print("Combined estimates (sequential):")
    combined = []
    for i in range(min(len(helmet_times), len(plate_times), len(person_times))):
        total = helmet_times[i] + plate_times[i] + person_times[i]
        combined.append(total)
    stats(combined, "3 detections (sequential)")

    # Display FPS estimates
    print()
    print("FPS estimates (single source):")
    for label, times_key in [
        ("Capture FPS", "capture"),
        ("Helmet detection FPS", "helmet"),
        ("Plate detection FPS", "plate"),
        ("Person detection FPS", "person"),
        ("3-detect sequential FPS", None),
    ]:
        if times_key and times_key in results and results[times_key]:
            mean = results[times_key]['mean']
            fps = 1000 / mean if mean > 0 else float('inf')
            print(f"  {label:35s} {fps:.1f} FPS (mean {results[times_key]['mean']:.1f}ms)")
        elif times_key is None and combined:
            mean = statistics.mean(combined)
            fps = 1000 / mean if mean > 0 else float('inf')
            print(f"  {label:35s} {fps:.1f} FPS (mean {mean:.1f}ms)")

    # Save results
    out = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'device': DEVICE,
        'detect_dims': f'{DETECT_WIDTH}x{DETECT_HEIGHT}',
        'video_dims': f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}',
        'video_path': video_path or 'synthetic',
        'n_frames': len(test_frames),
        'results': results,
    }
    out_path = Path(__file__).parent.parent / 'benchmark_pipeline_result.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print()
    print(f"Results saved to: {out_path}")

    return results


if __name__ == '__main__':
    main()
