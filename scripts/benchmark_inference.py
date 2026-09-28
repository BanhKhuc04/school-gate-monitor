"""
So sánh tốc độ .pt (PyTorch) vs .onnx (onnxruntime) trên CPU, dùng ảnh thật.
Chỉ đo, không đổi hành vi app — quyết định bật USE_ONNX_MODELS dựa vào kết quả này.

Chạy: python scripts/benchmark_inference.py
"""
import glob
import time
import cv2
from ultralytics import YOLO

from app.config import HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH, POSE_MODEL_PATH

N_RUNS = 50
N_WARMUP = 5

MODEL_PAIRS = [
    ("Helmet", HELMET_MODEL_PATH, HELMET_MODEL_PATH.replace(".pt", ".onnx")),
    ("Plate", PLATE_MODEL_PATH, PLATE_MODEL_PATH.replace(".pt", ".onnx")),
    ("Person (COCO)", PERSON_MODEL_PATH, PERSON_MODEL_PATH.replace(".pt", ".onnx")),
    ("Pose", POSE_MODEL_PATH, POSE_MODEL_PATH.replace(".pt", ".onnx")),
]


def bench(model, frame):
    for _ in range(N_WARMUP):
        model.predict(frame, verbose=False)
    t0 = time.perf_counter()
    for _ in range(N_RUNS):
        model.predict(frame, verbose=False)
    return (time.perf_counter() - t0) / N_RUNS * 1000  # ms/lần


if __name__ == "__main__":
    sample = sorted(glob.glob("data/snapshots/*.jpg"))[0]
    frame = cv2.imread(sample)
    print(f"Ảnh test: {sample}  ({N_RUNS} lần/model, bỏ {N_WARMUP} lần warmup)\n")

    print(f"{'Model':<16} {'.pt (ms)':>10} {'.onnx (ms)':>12} {'Nhanh hơn':>10}")
    print("-" * 52)
    for name, pt_path, onnx_path in MODEL_PAIRS:
        pt_ms = bench(YOLO(pt_path), frame)
        onnx_ms = bench(YOLO(onnx_path), frame)
        speedup = pt_ms / onnx_ms if onnx_ms > 0 else float("inf")
        print(f"{name:<16} {pt_ms:>10.1f} {onnx_ms:>12.1f} {speedup:>9.2f}x")

    print("\nNếu tốc độ ONNX nhanh hơn rõ rệt (>1.3x), bật bằng:")
    print("  set USE_ONNX_MODELS=1   (PowerShell: $env:USE_ONNX_MODELS=1)")
