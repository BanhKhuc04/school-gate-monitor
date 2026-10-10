import torch
print('torch:', torch.__version__)
print('cuda:', torch.cuda.is_available())
print('cudnn:', torch.backends.cudnn.version())
print('device count:', torch.cuda.device_count())
print('device name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')
print('compute capability:', torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'N/A')

try:
    import tensorrt
    print('tensorrt:', tensorrt.__version__)
except ImportError:
    print('tensorrt: NOT INSTALLED')

try:
    import onnxruntime as ort
    print('onnxruntime:', ort.__version__)
    print('providers:', ort.get_available_providers())
except ImportError:
    print('onnxruntime: NOT INSTALLED')

# Test FP16 on 1 model
import sys, os
sys.path.insert(0, 'D:/Work/Project_motorbike')
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
from ultralytics import YOLO
import time
import numpy as np

m = YOLO('D:/Work/Project_motorbike/models/helmet_best.pt')
m.to('cuda')
print('helmet classes:', m.names)

# Warmup
dummy = np.zeros((480, 640, 3), dtype=np.uint8)
for _ in range(3):
    m(dummy, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()

# Benchmark single model, half precision
N = 30
t0 = time.perf_counter()
for _ in range(N):
    m(dummy, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0
print(f'helmet detect (FP16, 640x480): {(elapsed/N)*1000:.1f} ms/frame, {N/elapsed:.1f} fps (1 model)')

# Same with full FP32
t0 = time.perf_counter()
for _ in range(N):
    m(dummy, verbose=False, conf=0.25, half=False)
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0
print(f'helmet detect (FP32, 640x480): {(elapsed/N)*1000:.1f} ms/frame, {N/elapsed:.1f} fps')

# Try 416x416 (smaller)
dummy2 = np.zeros((416, 416, 3), dtype=np.uint8)
for _ in range(3):
    m(dummy2, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
t0 = time.perf_counter()
for _ in range(N):
    m(dummy2, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0
print(f'helmet detect (FP16, 416x416): {(elapsed/N)*1000:.1f} ms/frame, {N/elapsed:.1f} fps')

# 320x320
dummy3 = np.zeros((320, 320, 3), dtype=np.uint8)
for _ in range(3):
    m(dummy3, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
t0 = time.perf_counter()
for _ in range(N):
    m(dummy3, verbose=False, conf=0.25, half=True)
torch.cuda.synchronize()
elapsed = time.perf_counter() - t0
print(f'helmet detect (FP16, 320x320): {(elapsed/N)*1000:.1f} ms/frame, {N/elapsed:.1f} fps')