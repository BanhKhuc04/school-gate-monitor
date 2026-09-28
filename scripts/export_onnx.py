"""
Export model .pt sang .onnx (CPU inference thường nhanh hơn qua onnxruntime).
Chạy 1 lần thủ công, không phải bước chạy app.

Chạy: python scripts/export_onnx.py
"""
import os
from ultralytics import YOLO

from app.config import HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH, POSE_MODEL_PATH

MODELS = [HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH, POSE_MODEL_PATH]

if __name__ == "__main__":
    for path in MODELS:
        print(f"Export {path} -> onnx ...")
        model = YOLO(path)
        onnx_path = model.export(format="onnx", imgsz=640, opset=12, simplify=False)
        size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
        print(f"  OK: {onnx_path} ({size_mb:.1f} MB)")
    print("\nXong. Chạy scripts/benchmark_inference.py để đo tốc độ trước khi bật USE_ONNX_MODELS.")
