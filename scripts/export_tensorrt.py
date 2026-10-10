"""Export the live detectors to TensorRT FP16 engines next to their .pt files.

Run once per machine (an engine is tied to its GPU and TensorRT version):
    pip install "tensorrt-cu12==10.*"
    python scripts/export_tensorrt.py

A nano YOLO in eager PyTorch spends most of a call launching kernels, not
computing: on the RTX 3050 Laptop plate detection took the same ~25 ms at
1280 px as at 640 px. app.cv.detector loads `<stem>-<imgsz>.engine` instead of
the .pt when it exists and is newer; delete the engine (or USE_TENSORRT=0) to
go back to PyTorch.
"""
import os
import shutil
import sys
from pathlib import Path

# Ultralytics otherwise pip-installs export extras mid-run; with the backend
# holding numpy's DLLs open that left numpy's metadata half-deleted.
os.environ.setdefault('YOLO_AUTOINSTALL', 'false')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultralytics import YOLO

from app.config import (DETECT_WIDTH, HELMET_MODEL_PATH, PERSON_MODEL_PATH,
                        PLATE_MODEL_PATH, PLATE_ONLY_DETECT_WIDTH, POSE_MODEL_PATH)
from app.cv.detector import engine_path, usable_engine
from app.cv.pose import POSE_IMGSZ, POSE_MAX_BATCH

# (weights, imgsz, batch): plate twice — the rear camera detects at full width.
EXPORTS = [(PERSON_MODEL_PATH, DETECT_WIDTH, 1), (HELMET_MODEL_PATH, DETECT_WIDTH, 1),
           (PLATE_MODEL_PATH, DETECT_WIDTH, 1), (PLATE_MODEL_PATH, PLATE_ONLY_DETECT_WIDTH, 1),
           (POSE_MODEL_PATH, POSE_IMGSZ, POSE_MAX_BATCH)]

if __name__ == '__main__':
    for weights, imgsz, batch in EXPORTS:
        target = engine_path(weights, imgsz)
        if usable_engine(weights, imgsz):
            print(f'{target} is up to date')
            continue
        print(f'{weights} @ {imgsz} (batch {batch}) -> {target}')
        # Pose takes every rider crop in one call, so its engine has a dynamic
        # batch; the detectors always see one frame of one fixed size.
        built = YOLO(weights).export(format='engine', imgsz=imgsz, half=True, device=0,
                                     batch=batch, dynamic=batch > 1, workspace=2, verbose=False)
        shutil.move(built, target)
        Path(built).with_suffix('.onnx').unlink(missing_ok=True)
