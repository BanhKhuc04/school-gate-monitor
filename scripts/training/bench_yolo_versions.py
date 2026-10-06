"""Compare yolo11n vs yolov8n on detection speed (640x480)"""
import sys
import time
import numpy as np
sys.path.insert(0, 'D:/Work/Project_motorbike')

from ultralytics import YOLO
import torch

print("torch:", torch.__version__, "cuda:", torch.cuda.is_available())
print("ultralytics:", __import__('ultralytics').__version__)

frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

def bench(label, path, half=True, n=30):
    print(f"\n--- {label}: {path} (FP16={half}) ---")
    m = YOLO(path)
    m.to('cuda')
    print(f"  classes: {m.names}")
    for _ in range(5):
        m(frame, verbose=False, conf=0.25, half=half)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(n):
        m(frame, verbose=False, conf=0.25, half=half)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0
    ms = elapsed/n*1000
    print(f"  → {ms:.1f} ms/frame, {n/elapsed:.1f} fps")
    return ms

# yolov8n baseline
m_v8 = bench("yolov8n (current)", "D:/Work/Project_motorbike/yolov8n.pt")
# yolo11n candidate
m_11 = bench("yolo11n (new)", "D:/Work/Project_motorbike/yolo11n.pt")
# yolo26n candidate (latest)
m_26 = bench("yolo26n (latest)", "D:/Work/Project_motorbike/weights/yolo26n.pt")

# Also check resolution scaling for yolo11n
print("\n\n=== yolo11n at different resolutions (FP16) ===")
y11 = YOLO("D:/Work/Project_motorbike/yolo11n.pt").to('cuda')
for h, w in [(640, 640), (480, 640), (416, 416), (320, 320)]:
    f = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
    for _ in range(3):
        y11(f, verbose=False, conf=0.25, half=True)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(30):
        y11(f, verbose=False, conf=0.25, half=True)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0
    print(f"  {h}x{w}: {elapsed/30*1000:.1f} ms/frame, {30/elapsed:.1f} fps")