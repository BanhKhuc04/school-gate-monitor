"""
Phase 6 (Task 1) tests — GPU profiling and benchmark plumbing.

Covers:
- get_runtime_config() returns expected fields, handles missing torch.
- GpuMemoryProfiler.sample() throttles by interval.
- GpuMemoryProfiler.stats() returns percentile p50/p95/peak.
- profile_inference() runs N samples, returns median/p95/min/max.
- InferenceTimer context manager measures time.
- VideoPipeline.get_status() exposes gpu_runtime field.
- VideoPipeline.get_status() handles missing _gpu_profiler gracefully.
"""
import os
import sys
import time
from collections import deque

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.cv.gpu_profiler import (
    get_runtime_config, GpuMemoryProfiler, InferenceTimer, profile_inference,
)


# --------------------------------------------------------------------------- #
# 1. get_runtime_config
# --------------------------------------------------------------------------- #

class TestRuntimeConfig:
    def test_runtime_config_has_required_fields(self):
        cfg = get_runtime_config()
        for key in ("device", "fp16", "cuda_available", "cudnn_enabled",
                    "cudnn_benchmark", "torch_version", "env_use_fp16",
                    "onnxruntime_available", "tensorrt_available"):
            assert key in cfg, f"missing {key}"

    def test_runtime_config_device_is_known(self):
        cfg = get_runtime_config()
        assert cfg["device"] in ("cpu", "cuda")

    def test_runtime_config_env_use_fp16_default(self, monkeypatch):
        monkeypatch.delenv("USE_FP16", raising=False)
        cfg = get_runtime_config()
        assert cfg["env_use_fp16"] is True

    def test_runtime_config_env_use_fp16_zero(self, monkeypatch):
        monkeypatch.setenv("USE_FP16", "0")
        cfg = get_runtime_config()
        assert cfg["env_use_fp16"] is False

    def test_runtime_config_fp16_only_on_cuda(self, monkeypatch):
        """USE_FP16 chỉ = True nếu CUDA available."""
        cfg = get_runtime_config()
        if cfg["cuda_available"]:
            assert cfg["fp16"] is True
        else:
            assert cfg["fp16"] is False


# --------------------------------------------------------------------------- #
# 2. GpuMemoryProfiler
# --------------------------------------------------------------------------- #

class TestGpuMemoryProfiler:
    def test_profiler_sample_throttled(self):
        p = GpuMemoryProfiler(maxlen=10)
        p.set_interval(10.0)  # long interval
        # First call samples (or returns None if no CUDA), but is recorded
        first = p.sample()
        # Second call within 10s should return None (throttled)
        second = p.sample()
        if first is not None:
            assert second is None  # throttled

    def test_profiler_force_sample(self):
        p = GpuMemoryProfiler(maxlen=10)
        p.set_interval(10.0)
        # force=True bypasses throttle
        first = p.sample(force=True)
        second = p.sample(force=True)
        if first is not None:
            assert second is not None

    def test_profiler_stats_empty(self):
        p = GpuMemoryProfiler()
        stats = p.stats()
        # Empty buffer → all zeros, samples=0
        assert stats["allocated_mb"]["samples"] == 0
        assert stats["reserved_mb"]["samples"] == 0
        assert stats["allocated_mb"]["peak"] == 0.0
        assert stats["reserved_mb"]["peak"] == 0.0

    def test_profiler_stats_with_fake_samples(self):
        """Feed fake samples into a profiler via direct deque append to
        avoid depending on CUDA available."""
        p = GpuMemoryProfiler()
        for v in (10.0, 20.0, 30.0, 40.0, 50.0):
            p._samples_allocated.append(v)
        stats = p.stats()
        assert stats["allocated_mb"]["peak"] == 50.0
        assert stats["allocated_mb"]["samples"] == 5
        # p50 of 5 sorted = 30.0 (middle)
        assert stats["allocated_mb"]["p50"] == 30.0


# --------------------------------------------------------------------------- #
# 3. InferenceTimer
# --------------------------------------------------------------------------- #

class TestInferenceTimer:
    def test_timer_measures_something(self):
        with InferenceTimer() as t:
            time.sleep(0.01)
        assert t.elapsed_ms >= 10.0  # at least 10ms

    def test_timer_with_name(self):
        with InferenceTimer(name="model.predict") as t:
            time.sleep(0.001)
        assert t.name == "model.predict"
        assert t.elapsed_ms >= 0.0

    def test_timer_no_cuda_sync(self):
        """sync_cuda=False trên CPU environment không lỗi."""
        with InferenceTimer(sync_cuda=False) as t:
            time.sleep(0.001)
        assert t.elapsed_ms >= 0.0


# --------------------------------------------------------------------------- #
# 4. profile_inference
# --------------------------------------------------------------------------- #

class TestProfileInference:
    def test_profile_returns_median_p95(self):
        def slow_fn(x):
            time.sleep(0.001)
            return x * 2

        stats = profile_inference(slow_fn, 5, samples=5, warmup=1)
        assert stats["samples"] == 5
        assert stats["median_ms"] >= 0.0
        assert stats["p95_ms"] >= stats["median_ms"]
        assert stats["max_ms"] >= stats["min_ms"]

    def test_profile_zero_samples_clamped_to_one(self):
        """samples=0 được clamp lên 1 để đo ít nhất 1 lần."""
        stats = profile_inference(lambda: None, samples=0)
        assert stats["samples"] == 1
        assert stats["median_ms"] >= 0.0

    def test_profile_warmup_runs_but_not_recorded(self):
        call_count = [0]
        def fn():
            call_count[0] += 1
        profile_inference(fn, samples=3, warmup=2)
        # 2 warmup + 3 samples = 5 calls total
        assert call_count[0] == 5

    def test_profile_passes_kwargs(self):
        def fn(x, y=0):
            return x + y
        # Just verify it runs without error
        stats = profile_inference(fn, 1, y=2, samples=2, warmup=0)
        assert stats["samples"] == 2


# --------------------------------------------------------------------------- #
# 5. Pipeline integration — gpu_runtime in get_status()
# --------------------------------------------------------------------------- #

class TestPipelineGpuRuntime:
    def _bare_pipeline(self):
        from app.cv.pipeline import VideoPipeline
        from app.cv.pipeline_metrics import MetricsBuffer
        import queue as queue_mod
        p = VideoPipeline.__new__(VideoPipeline)
        p.role = "front"
        p.profile = "full"
        p._running = False
        p._thread = None
        p._webcam = None
        p._last_frame_time = time.time()
        p._last_detection_time = time.time()
        p._frame_count = 0
        p._start_time = time.time()
        p._frame_timestamps = deque(maxlen=64)
        p._plate_attempts = 0
        p._plate_successes = 0
        p._jpeg_new_count = 0
        p._jpeg_repeat_count = 0
        p._capture_fps_value = 0.0
        p._ai_fps_value = 0.0
        p._frames_dropped_stale = 0
        p._frames_dropped_encode = 0
        p._metrics_capture = MetricsBuffer(maxlen=200)
        p._metrics_detect = MetricsBuffer(maxlen=200)
        p._metrics_ocr_wait = MetricsBuffer(maxlen=200)
        p._metrics_encode = MetricsBuffer(maxlen=200)
        p._metrics_persistence = MetricsBuffer(maxlen=200)
        p._metrics_dispatch = MetricsBuffer(maxlen=200)
        p._ocr_pending = deque(maxlen=64)
        p._ocr_max_pending = 64
        p._alert_queue = queue_mod.Queue(maxsize=64)
        p._clip_buffer = deque(maxlen=600)
        p._jpeg_cache = {}
        p._ocr_health = {"submitted": 0, "completed": 0, "stale_dropped": 0, "duplicate_dropped": 0}
        p._violations_persisted_total = 0
        p._violations_skipped_total = 0
        p._run_generation = 0
        p._reconnect_failures = 0
        p._plate_consensus = None
        p._resource_sampler = type("Sampler", (), {"snapshot": staticmethod(lambda: (0.0, 0.0, 0.0))})()
        p._pedestrian_count = 0
        p._rider_count = 0
        p._last_process_latency_ms = 0.0
        p._io_health = {}
        p._persist_pending = {}
        p._posture_confirmed = "UNKNOWN"
        p._posture_confidence = 0.0
        return p

    def test_pipeline_has_gpu_runtime_in_status(self):
        p = self._bare_pipeline()
        p._gpu_profiler = GpuMemoryProfiler(maxlen=10)
        st = p.get_status()
        assert "gpu_runtime" in st
        assert "device" in st["gpu_runtime"]
        assert "fp16" in st["gpu_runtime"]
        assert "vram" in st["gpu_runtime"]

    def test_pipeline_handles_missing_gpu_profiler(self):
        p = self._bare_pipeline()
        if hasattr(p, "_gpu_profiler"):
            delattr(p, "_gpu_profiler")
        st = p.get_status()
        assert "gpu_runtime" in st
        # Should still return valid runtime config (vram=None)
        assert st["gpu_runtime"]["vram"] is None
        assert "device" in st["gpu_runtime"]


# --------------------------------------------------------------------------- #
# 6. Acceptance: runtime config matches what config.py sets
# --------------------------------------------------------------------------- #

class TestRuntimeConfigConsistency:
    def test_fp16_matches_config(self):
        """config.py: USE_FP16 = (DEVICE == 'cuda'). get_runtime_config
        phải báo cùng giá trị khi CUDA available."""
        from app.config import USE_FP16, DEVICE
        cfg = get_runtime_config()
        if DEVICE == "cuda" and cfg["cuda_available"]:
            assert cfg["fp16"] is True
        assert cfg["device"] == DEVICE or (
            DEVICE == "cuda" and cfg["cuda_available"]
        ) or DEVICE == "cpu"

    def test_torch_cudnn_benchmark_flag(self):
        """config.py bật cudnn.benchmark nếu torch import được. Runtime
        config phải phản ánh đúng."""
        try:
            import torch
            expected = bool(torch.backends.cudnn.benchmark)
        except ImportError:
            expected = False
        cfg = get_runtime_config()
        assert cfg["cudnn_benchmark"] == expected