"""Phase 0 (Task 1) — bounded metrics buffer + percentile helpers.

Vấn đề trước Phase 0:
- `get_status()` chỉ trả 1 số `avg_process_latency_ms` (trung bình cuối cùng,
  không p50/p95). Khi có 1 frame đột biến chậm 800ms, average bị kéo lên
  rồi reset về 0 ngay frame kế tiếp — không phản ánh thực trạng.
- FPS hiển thị = `len(frame_timestamps) / span`, phụ thuộc deque(maxlen=30)
  — khi pipeline đang chạy nhanh deque tràn, khi chậm thì FPS giảm ảo.
- Không phân biệt được "hình mới" (frame MỚI đọc về từ camera) và "JPEG
  re-encode" — frontend đếm nhầm số lần refresh thành số hình mới.
- Không có telemetry cho queue/OCR/dropped frames/RAM/VRAM → debug latency
  cao phải đoán.

Giải pháp Phase 0:
- `MetricsBuffer` (bounded deque) cho mỗi loại latency; helper `percentile()`
  trả p50/p95 qua linear interpolation trên sorted list. KHÔNG lưu frame
  thật vào buffer (đủ số là đủ — float ms), nên RAM cố định ~30 * 8 bytes.
- `PipelineMetrics` gom counter + buffer + last-value, có snapshot() trả
  dict sạch sẽ cho `get_status()`. KHÔNG log token/URL/frame data.
- Sampling tài nguyên nền (psutil rss, torch VRAM) chạy theo interval
  `RESOURCE_SAMPLE_SEC` (mặc định 1s) — không gọi mỗi frame (overhead).
- Dropped frames đếm qua 2 kênh: (a) `frames_dropped_stale` (frame cũ bị
  AI bỏ vì tới muộn) và (b) `frames_dropped_encode` (encode JPEG lỗi).
"""

from __future__ import annotations

import bisect
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional as _Optional

# Khoảng cách tối thiểu giữa 2 lần sample tài nguyên (psutil rss / torch VRAM).
# Phase 0 plan yêu cầu "khoảng một giây" — đặt 1.0s; quá nhỏ sẽ tốn CPU,
# quá lớn thì dashboard bỏ lỡ spike. Đổi qua env METRICS_RESOURCE_SAMPLE_SEC
# khi benchmark.
RESOURCE_SAMPLE_SEC: float = float(os.environ.get("METRICS_RESOURCE_SAMPLE_SEC", "1.0") or "1.0")

# Số mẫu latency tối đa giữ trong buffer. 30 ~ 1 giây ở AI 30 FPS. Đủ cho
# p50/p95 trong cửa sổ ngắn, không phình RAM.
METRICS_BUFFER_SIZE: int = 60


def percentile(values: list[float], pct: float) -> _Optional[float]:
    """Linear-interpolation percentile trên list float đã sort.

    Trả None khi list rỗng (để frontend hiển thị "—"). `pct` nằm trong [0, 100]
    (0 = min, 100 = max). Implementation đúng với NumPy `percentile(..., method="linear")`.
    """
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    if pct <= 0:
        return float(sorted_vals[0])
    if pct >= 100:
        return float(sorted_vals[-1])
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(sorted_vals[lower])
    weight = rank - lower
    return float(sorted_vals[lower] + (sorted_vals[upper] - sorted_vals[lower]) * weight)


class MetricsBuffer:
    """Bounded ring buffer cho latency / timing — append O(1), snapshot copy O(n)."""

    __slots__ = ("_data", "_maxlen")

    def __init__(self, maxlen: int = METRICS_BUFFER_SIZE):
        self._data: deque[float] = deque(maxlen=max(8, maxlen))
        self._maxlen = max(8, maxlen)

    def add(self, value: float) -> None:
        if value is None:
            return
        try:
            self._data.append(float(value))
        except (TypeError, ValueError):
            return

    def snapshot(self) -> list[float]:
        return list(self._data)

    def percentile(self, pct: float) -> _Optional[float]:
        return percentile(list(self._data), pct)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


@dataclass
class PipelineMetrics:
    """Snapshot toàn bộ metrics cho 1 pipeline. KHÔNG chứa frame thật, URL,
    token hay bất kỳ thông tin nhạy cảm nào — chỉ số liệu + tên gate."""

    gate_id: str = ""
    capture_fps: float = 0.0
    ai_fps: float = 0.0
    jpeg_new_count: int = 0
    jpeg_repeat_count: int = 0
    frames_dropped_stale: int = 0
    frames_dropped_encode: int = 0

    # Latency (ms). Trước Phase 0 chỉ có 1 giá trị 'avg'; giờ giữ p50/p95
    # cho mỗi giai đoạn để debug latency spike.
    capture_latency_p50: _Optional[float] = None
    capture_latency_p95: _Optional[float] = None
    detect_latency_p50: _Optional[float] = None
    detect_latency_p95: _Optional[float] = None
    ocr_wait_latency_p50: _Optional[float] = None
    ocr_wait_latency_p95: _Optional[float] = None
    encode_latency_p50: _Optional[float] = None
    encode_latency_p95: _Optional[float] = None
    persistence_latency_p50: _Optional[float] = None
    persistence_latency_p95: _Optional[float] = None
    dispatch_latency_p50: _Optional[float] = None
    dispatch_latency_p95: _Optional[float] = None

    # Hàng chờ / tài nguyên.
    ocr_pending_count: int = 0
    ocr_pending_capacity: int = 0
    alert_queue_size: int = 0
    alert_queue_capacity: int = 0
    clip_buffer_size: int = 0
    clip_buffer_capacity: int = 0
    jpeg_cache_size: int = 0

    # Counter tổng (cộng dồn từ lúc pipeline start).
    ocr_submitted_total: int = 0
    ocr_completed_total: int = 0
    ocr_stale_dropped_total: int = 0
    violations_persisted_total: int = 0
    violations_skipped_total: int = 0
    persist_failures_total: int = 0

    # Tài nguyên — sampling nền theo RESOURCE_SAMPLE_SEC; trả None khi
    # chưa có sample hoặc psutil không khả dụng.
    rss_mb: _Optional[float] = None
    vram_mb: _Optional[float] = None
    resource_sample_at: _Optional[float] = None

    def to_dict(self) -> dict:
        """Trả dict phẳng, sẵn cho JSON. Không có frame/URL/token."""
        return {
            "capture_fps": round(self.capture_fps, 2),
            "ai_fps": round(self.ai_fps, 2),
            "jpeg_new_count": self.jpeg_new_count,
            "jpeg_repeat_count": self.jpeg_repeat_count,
            "frames_dropped_stale": self.frames_dropped_stale,
            "frames_dropped_encode": self.frames_dropped_encode,
            "capture_latency_ms": _round_pair(self.capture_latency_p50, self.capture_latency_p95),
            "detect_latency_ms": _round_pair(self.detect_latency_p50, self.detect_latency_p95),
            "ocr_wait_latency_ms": _round_pair(self.ocr_wait_latency_p50, self.ocr_wait_latency_p95),
            "encode_latency_ms": _round_pair(self.encode_latency_p50, self.encode_latency_p95),
            "persistence_latency_ms": _round_pair(self.persistence_latency_p50, self.persistence_latency_p95),
            "dispatch_latency_ms": _round_pair(self.dispatch_latency_p50, self.dispatch_latency_p95),
            "queues": {
                "ocr_pending": {"size": self.ocr_pending_count, "capacity": self.ocr_pending_capacity},
                "alerts": {"size": self.alert_queue_size, "capacity": self.alert_queue_capacity},
                "clip_buffer": {"size": self.clip_buffer_size, "capacity": self.clip_buffer_capacity},
                "jpeg_cache": self.jpeg_cache_size,
            },
            "counters": {
                "ocr_submitted": self.ocr_submitted_total,
                "ocr_completed": self.ocr_completed_total,
                "ocr_stale_dropped": self.ocr_stale_dropped_total,
                "violations_persisted": self.violations_persisted_total,
                "violations_skipped": self.violations_skipped_total,
                "persist_failures": self.persist_failures_total,
            },
            "rss_mb": self.rss_mb,
            "vram_mb": self.vram_mb,
            "resource_sample_at": self.resource_sample_at,
        }


def _round_pair(p50: _Optional[float], p95: _Optional[float]) -> dict:
    return {"p50": round(p50, 2) if p50 is not None else None,
            "p95": round(p95, 2) if p95 is not None else None}


class ResourceSampler:
    """Sample RSS (RAM) + VRAM (nếu torch.cuda có) theo interval cố định.

    Chạy lazy — `update()` chỉ stat process khi đủ interval. Không gọi
    `nvidia-smi` (Phase 0 plan cấm); chỉ đọc `torch.cuda.memory_allocated()`
    nếu torch có CUDA. Khi torch không có hoặc CUDA không khả dụng, vram=None.
    """

    __slots__ = ("_lock", "_rss_mb", "_vram_mb", "_last_sample_at", "_psutil_proc")

    def __init__(self):
        self._lock = threading.Lock()
        self._rss_mb: _Optional[float] = None
        self._vram_mb: _Optional[float] = None
        self._last_sample_at: _Optional[float] = None
        # Lazy-import psutil; nếu thiếu → _psutil_proc = None, sampler hoạt
        # động ở chế độ "không có RSS" (trả None). Không ép dependency mới.
        try:
            import psutil  # type: ignore
            self._psutil_proc = psutil.Process(os.getpid())
        except Exception:
            self._psutil_proc = None  # type: ignore[assignment]

    def update(self, now: _Optional[float] = None) -> None:
        """Sample tài nguyên nếu đủ interval. Cheap O(1) khi interval chưa đủ."""
        if now is None:
            now = time.monotonic()
        with self._lock:
            if self._last_sample_at is not None and now - self._last_sample_at < RESOURCE_SAMPLE_SEC:
                return
            self._last_sample_at = now
        # Sample NGOÀI lock — read() của psutil có thể chậm trên Windows.
        rss = None
        if self._psutil_proc is not None:
            try:
                rss = float(self._psutil_proc.memory_info().rss) / (1024 * 1024)
            except Exception:
                rss = None
        vram = None
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                vram = float(torch.cuda.memory_allocated()) / (1024 * 1024)
        except Exception:
            vram = None
        with self._lock:
            self._rss_mb = rss
            self._vram_mb = vram

    def snapshot(self) -> tuple[_Optional[float], _Optional[float], _Optional[float]]:
        with self._lock:
            return self._rss_mb, self._vram_mb, self._last_sample_at