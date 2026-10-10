"""
GPU Profiler — Phase 6 (Task 1) chẩn đoán bottleneck GPU/CPU.

Cung cấp:
- `get_runtime_config()` — trả thực trạng device, FP16, cudnn.benchmark,
  cudnn.enabled, TensorRT/ONNX, model input size, batch.
- `GpuMemoryProfiler` — sample VRAM allocated/reserved mỗi interval, lưu
  rolling window, percentile p50/p95.
- `InferenceTimer` — context manager đo thời gian inference, hỗ trợ
  GPU sync (torch.cuda.synchronize) để đo chính xác.
- `profile_inference(model, fn, samples=10)` — chạy N lần inference trên
  input ngẫu nhiên, trả median/p95.

KHÔNG load model thật (nặng). Helpers này phục vụ:
  - System page hiển thị thực trạng FP16/cudnn (UI debug).
  - Benchmark script 30 phút cách ly (Phase 6 acceptance).
  - Unit test verify plumbing đúng.
"""
from __future__ import annotations

import os
import time
from collections import deque
from contextlib import contextmanager
from typing import Optional


# --------------------------------------------------------------------------- #
# Runtime config snapshot
# --------------------------------------------------------------------------- #

def get_runtime_config() -> dict:
    """Trả thực trạng runtime để UI / system page biết.

    Trả về dict với keys:
      - device: 'cuda' | 'cpu'
      - fp16: bool (USE_FP16 env + torch.cuda available)
      - cuda_available: bool
      - cudnn_enabled: bool
      - cudnn_benchmark: bool
      - torch_version: str (vd '2.1.2')
      - cuda_version: str | None
      - gpu_name: str | None
      - gpu_memory_total_mb: float | None
      - env_use_fp16: bool (raw env, không tính điều kiện)
      - onnxruntime_available: bool
      - tensorrt_available: bool
    """
    out = {
        "device": "cpu",
        "fp16": False,
        "cuda_available": False,
        "cudnn_enabled": False,
        "cudnn_benchmark": False,
        "torch_version": "",
        "cuda_version": None,
        "gpu_name": None,
        "gpu_memory_total_mb": None,
        "env_use_fp16": os.environ.get("USE_FP16", "1") == "1",
        "onnxruntime_available": False,
        "tensorrt_available": False,
    }
    try:
        import torch
        out["torch_version"] = torch.__version__
        out["cuda_available"] = bool(torch.cuda.is_available())
        if out["cuda_available"]:
            out["device"] = "cuda"
            out["cuda_version"] = torch.version.cuda
            out["gpu_name"] = torch.cuda.get_device_name(0)
            out["gpu_memory_total_mb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024*1024),
                1)
            out["cudnn_enabled"] = bool(torch.backends.cudnn.enabled)
            out["cudnn_benchmark"] = bool(torch.backends.cudnn.benchmark)
            # USE_FP16 = cuda available (per app/config.py logic)
            out["fp16"] = out["env_use_fp16"]
    except ImportError:
        pass
    try:
        import onnxruntime  # noqa: F401
        out["onnxruntime_available"] = True
    except ImportError:
        pass
    try:
        import tensorrt  # noqa: F401
        out["tensorrt_available"] = True
    except ImportError:
        pass
    return out


# --------------------------------------------------------------------------- #
# GPU memory profiler
# --------------------------------------------------------------------------- #

class GpuMemoryProfiler:
    """Sample VRAM allocated/reserved mỗi interval. Bounded rolling buffer
    cho percentile."""

    def __init__(self, maxlen: int = 600):
        self._samples_allocated: deque = deque(maxlen=maxlen)
        self._samples_reserved: deque = deque(maxlen=maxlen)
        self._last_sample_at: float = 0.0
        self._interval_sec: float = 1.0

    def set_interval(self, sec: float):
        self._interval_sec = max(0.1, float(sec))

    def sample(self, force: bool = False) -> Optional[dict]:
        """Sample 1 lần. Trả dict hoặc None nếu chưa tới interval."""
        now = time.monotonic()
        if not force and (now - self._last_sample_at) < self._interval_sec:
            return None
        self._last_sample_at = now
        try:
            import torch
            if not torch.cuda.is_available():
                return None
            allocated = torch.cuda.memory_allocated(0) / (1024*1024)
            reserved = torch.cuda.memory_reserved(0) / (1024*1024)
            self._samples_allocated.append(round(allocated, 2))
            self._samples_reserved.append(round(reserved, 2))
            return {
                "allocated_mb": round(allocated, 2),
                "reserved_mb": round(reserved, 2),
                "ts": now,
            }
        except ImportError:
            return None

    def stats(self) -> dict:
        """Trả percentile p50/p95/peak. Trả rỗng nếu không có sample."""
        def _pct(buf, p):
            if not buf:
                return 0.0
            data = sorted(buf)
            k = max(0, min(len(data) - 1, int(p / 100 * (len(data) - 1))))
            return data[k]
        return {
            "allocated_mb": {
                "p50": round(_pct(self._samples_allocated, 50), 2),
                "p95": round(_pct(self._samples_allocated, 95), 2),
                "peak": round(max(self._samples_allocated) if self._samples_allocated else 0.0, 2),
                "samples": len(self._samples_allocated),
            },
            "reserved_mb": {
                "p50": round(_pct(self._samples_reserved, 50), 2),
                "p95": round(_pct(self._samples_reserved, 95), 2),
                "peak": round(max(self._samples_reserved) if self._samples_reserved else 0.0, 2),
                "samples": len(self._samples_reserved),
            },
        }


# --------------------------------------------------------------------------- #
# Inference timer
# --------------------------------------------------------------------------- #

@contextmanager
def InferenceTimer(sync_cuda: bool = True, name: str = ""):
    """Context manager đo thời gian. Nếu sync_cuda=True và CUDA available,
    sẽ gọi torch.cuda.synchronize() trước khi đo đầu/cuối để GPU không
    bị async ảo.

    Usage:
            with InferenceTimer() as t:
                model(...)
            print(t.elapsed_ms)
    """
    t0 = time.perf_counter()
    if sync_cuda:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                t0 = time.perf_counter()
        except ImportError:
            pass
    timer = _Timer(name=name)
    yield timer
    if sync_cuda:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
        except ImportError:
            pass
    timer.elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)


class _Timer:
    def __init__(self, name: str):
        self.name = name
        self.elapsed_ms = 0.0


# --------------------------------------------------------------------------- #
# Profiling helper — chạy N lần, trả median/p95
# --------------------------------------------------------------------------- #

def profile_inference(fn, *args, samples: int = 10, warmup: int = 2,
                      **fn_kwargs) -> dict:
    """Chạy fn N lần, trả median/p95/min/max latency (ms).

    Args:
        fn: callable.
        *args: positional args truyền vào fn.
        samples: số lần đo (default 10).
        warmup: số lần warmup (default 2, KHÔNG tính vào stats).
        **fn_kwargs: keyword args truyền vào fn.

    Returns:
        dict {samples, median_ms, p95_ms, min_ms, max_ms}.
    """
    if samples < 1:
        samples = 1
    # warmup
    for _ in range(max(0, warmup)):
        fn(*args, **fn_kwargs)
    times = []
    for _ in range(samples):
        with InferenceTimer() as t:
            fn(*args, **fn_kwargs)
        times.append(t.elapsed_ms)
    times.sort()
    n = len(times)
    return {
        "samples": n,
        "median_ms": round(times[n // 2], 3) if n else 0.0,
        "p95_ms": round(times[max(0, int(n * 0.95) - 1)], 3) if n else 0.0,
        "min_ms": round(times[0], 3) if n else 0.0,
        "max_ms": round(times[-1], 3) if n else 0.0,
    }


__all__ = [
    "get_runtime_config",
    "GpuMemoryProfiler",
    "InferenceTimer",
    "profile_inference",
]