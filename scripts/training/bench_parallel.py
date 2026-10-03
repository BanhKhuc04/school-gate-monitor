"""Test: 3 YOLO models chạy song song qua ThreadPoolExecutor có thực sự parallel?"""
import sys
import os
import time
import numpy as np
sys.path.insert(0, 'D:/Work/Project_motorbike')

from concurrent.futures import ThreadPoolExecutor
from ultralytics import YOLO

# Load 3 models (3 instance)
print("Loading 3 models...")
person = YOLO('D:/Work/Project_motorbike/yolov8n.pt').to('cuda')
helmet = YOLO('D:/Work/Project_motorbike/models/helmet_best.pt').to('cuda')
plate = YOLO('D:/Work/Project_motorbike/models/plate_best.pt').to('cuda')
print("✓ Loaded")

frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

# Warmup
for _ in range(3):
    person(frame, verbose=False, conf=0.25, half=True)
    helmet(frame, verbose=False, conf=0.25, half=True)
    plate(frame, verbose=False, conf=0.25, half=True)
import torch
torch.cuda.synchronize()
print("✓ Warmup done")

# Test 1: sequential
N = 20
t0 = time.perf_counter()
for _ in range(N):
    person(frame, verbose=False, conf=0.25, half=True)
    helmet(frame, verbose=False, conf=0.25, half=True)
    plate(frame, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
seq_ms = (time.perf_counter() - t0) / N * 1000
print(f"\nSequential 3 models: {seq_ms:.1f} ms/frame → {1000/seq_ms:.1f} fps")

# Test 2: parallel via ThreadPoolExecutor
def call(model):
    return model(frame, verbose=False, conf=0.25, half=True)

with ThreadPoolExecutor(max_workers=3) as ex:
    f_p = ex.submit(call, person)
    f_h = ex.submit(call, helmet)
    f_pl = ex.submit(call, plate)
    f_p.result(); f_h.result(); f_pl.result()
torch.cuda.synchronize()
# warm one more
t0 = time.perf_counter()
for _ in range(N):
    with ThreadPoolExecutor(max_workers=3) as ex:
        f1 = ex.submit(call, person); f2 = ex.submit(call, helmet); f3 = ex.submit(call, plate)
        f1.result(); f2.result(); f3.result()
torch.cuda.synchronize()
par_ms = (time.perf_counter() - t0) / N * 1000
print(f"Parallel 3 models:   {par_ms:.1f} ms/frame → {1000/par_ms:.1f} fps")
print(f"Speedup: {seq_ms/par_ms:.2f}x")

# Test 3: parallel + batched (gộp 3 model thành 1 forward pass — không thực tế cho YOLO)
# Bỏ qua, YOLO không batch được giữa 2 model khác nhau.

print("\nConclusion:")
print(f"  Sequential 3 models: ~{seq_ms:.0f}ms = max(50fps single) × 3 serialize")
print(f"  Parallel 3 models:   ~{par_ms:.0f}ms = ?? fps (đây mới là bottleneck thật)")
print(f"  Cần song song để đạt 30 fps (1000/30 = 33ms budget)")