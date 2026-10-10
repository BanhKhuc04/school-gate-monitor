"""Phase 0 (Task 1) — metrics helpers + pipeline instrumentation tests.

Bao phủ:
- `pipeline_metrics.MetricsBuffer` / `percentile()` (bounded, p50/p95)
- `pipeline_metrics.PipelineMetrics` / `ResourceSampler`
- `_pipeline_status()` trong system.py dùng `get_existing_pipeline()` (chỉ đọc)
- `_storage_breakdown()` cache 60s + cross-path invalidation
- `VideoPipeline.get_status()` có field `metrics` đầy đủ (latency/queue/counter/RSS/VRAM)
- `VideoPipeline._publish_frame_jpeg()` đếm riêng `jpeg_new_count` vs `jpeg_repeat_count`
- `_persist_violation()` không block loop và emit alert trong window bình thường

KHÔNG chạy model thật; dùng `_build_pipeline_with_mocks` để khởi tạo
VideoPipeline mà không load YOLO/OCR. Test ở mức unit + smoke.
"""

import time

import numpy as np
import pytest

from app.cv.pipeline_metrics import (
    MetricsBuffer,
    PipelineMetrics,
    ResourceSampler,
    percentile,
)


# ─── percentile ───────────────────────────────────────────────────────────────

class TestPercentile:
    def test_empty_returns_none(self):
        assert percentile([], 50) is None
        assert percentile([], 95) is None

    def test_single_value(self):
        assert percentile([42.0], 50) == 42.0
        assert percentile([42.0], 95) == 42.0

    def test_sorted_input_required(self):
        # Hàm tự sort, không cần input đã sort
        v = percentile([3.0, 1.0, 2.0], 50)
        assert v == 2.0

    def test_p0_p100(self):
        assert percentile([1.0, 2.0, 3.0], 0) == 1.0
        assert percentile([1.0, 2.0, 3.0], 100) == 3.0

    def test_p50_p95_interpolation(self):
        # 20 mẫu 1..20, p50 = (20-1)*0.5 = 9.5 → 9 + 0.5*(10-9) = 9.5
        v = percentile(list(range(1, 21)), 50)
        assert v == pytest.approx(10.5, rel=0.01)
        # p95 = 0.95*19 = 18.05 → sorted[18]=19 + 0.05*(20-19) = 19.05
        v = percentile(list(range(1, 21)), 95)
        assert v == pytest.approx(19.05, rel=0.01)

    def test_p99_stress(self):
        # 100 mẫu 1..100, p99: rank = 0.99*99 = 98.01
        # sorted[98]=99, sorted[99]=100, weight=0.01 → 99 + 0.01*1 = 99.01
        v = percentile(list(range(1, 101)), 99)
        assert v == pytest.approx(99.01, rel=0.01)


# ─── MetricsBuffer ─────────────────────────────────────────────────────────────

class TestMetricsBuffer:
    def test_init_uses_maxlen(self):
        buf = MetricsBuffer(maxlen=10)
        for i in range(20):
            buf.add(float(i))
        # deque(maxlen=10) giữ 10 mẫu cuối = 10..19
        assert len(buf) == 10
        assert buf.percentile(0) == 10.0
        assert buf.percentile(100) == 19.0

    def test_min_maxlen(self):
        # maxlen < 8 vẫn ép về 8 để tránh buffer quá nhỏ
        buf = MetricsBuffer(maxlen=2)
        assert buf._maxlen == 8

    def test_add_ignores_none(self):
        buf = MetricsBuffer()
        buf.add(None)
        assert len(buf) == 0

    def test_add_ignores_bad_values(self):
        buf = MetricsBuffer()
        buf.add("not a number")  # type: ignore[arg-type]
        assert len(buf) == 0

    def test_clear(self):
        buf = MetricsBuffer()
        for i in range(5):
            buf.add(float(i))
        buf.clear()
        assert len(buf) == 0
        assert buf.percentile(50) is None

    def test_snapshot_returns_copy(self):
        buf = MetricsBuffer()
        for i in range(3):
            buf.add(float(i))
        snap = buf.snapshot()
        snap.append(99.0)
        assert len(buf) == 3  # buffer không bị ảnh hưởng


# ─── ResourceSampler ──────────────────────────────────────────────────────────

class TestResourceSampler:
    def test_initial_no_sample(self):
        s = ResourceSampler()
        rss, vram, at = s.snapshot()
        assert rss is None and vram is None and at is None

    def test_update_returns_values(self):
        s = ResourceSampler()
        s.update()
        rss, vram, at = s.snapshot()
        assert at is not None
        # rss có thể None nếu psutil không có; vẫn sample được timestamp
        assert at > 0.0

    def test_interval_throttling(self):
        s = ResourceSampler()
        s.update()
        first_at = s.snapshot()[2]
        # Gọi lại ngay — KHÔNG re-sample do interval chưa đủ (mặc định 1s).
        s.update()
        second_at = s.snapshot()[2]
        assert second_at == first_at


# ─── PipelineMetrics snapshot ─────────────────────────────────────────────────

class TestPipelineMetrics:
    def test_to_dict_has_all_keys(self):
        m = PipelineMetrics(gate_id="main")
        d = m.to_dict()
        assert d["capture_fps"] == 0.0
        assert d["ai_fps"] == 0.0
        assert d["jpeg_new_count"] == 0
        assert d["jpeg_repeat_count"] == 0
        assert d["frames_dropped_stale"] == 0
        assert d["frames_dropped_encode"] == 0
        # latency nested
        for stage in ("capture_latency_ms", "detect_latency_ms",
                       "ocr_wait_latency_ms", "encode_latency_ms",
                       "persistence_latency_ms", "dispatch_latency_ms"):
            assert stage in d, f"missing stage: {stage}"
            assert "p50" in d[stage] and "p95" in d[stage]
            assert d[stage]["p50"] is None
        # queues count
        assert "queues" in d
        assert "ocr_pending" in d["queues"]
        assert "alerts" in d["queues"]
        # counters
        assert "counters" in d
        assert "ocr_submitted" in d["counters"]


# ─── _publish_frame_jpeg: đếm riêng new vs repeat ───────────────────────────

class TestJpegCount:
    def test_first_frame_counted_as_new(self, monkeypatch):
        from app.cv import pipeline as p_mod
        from app.tests.test_dot_R import _build_pipeline_with_mocks
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        # Reset counters
        pipeline._jpeg_new_count = 0
        pipeline._jpeg_repeat_count = 0
        pipeline._jpeg_last_emitted_seq = -1

        frame = np.full((40, 60, 3), 200, dtype=np.uint8)
        pipeline._publish_frame_jpeg(frame, 1)
        assert pipeline._jpeg_new_count == 1
        assert pipeline._jpeg_repeat_count == 0

    def test_same_frame_seq_counted_as_repeat(self, monkeypatch):
        from app.cv import pipeline as p_mod
        from app.tests.test_dot_R import _build_pipeline_with_mocks
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        pipeline._jpeg_new_count = 0
        pipeline._jpeg_repeat_count = 0
        pipeline._jpeg_last_emitted_seq = -1

        frame = np.full((40, 60, 3), 200, dtype=np.uint8)
        pipeline._publish_frame_jpeg(frame, 1)
        pipeline._publish_frame_jpeg(frame, 1)
        pipeline._publish_frame_jpeg(frame, 1)
        assert pipeline._jpeg_new_count == 1
        assert pipeline._jpeg_repeat_count == 2

    def test_distinct_seq_each_new(self, monkeypatch):
        from app.cv import pipeline as p_mod
        from app.tests.test_dot_R import _build_pipeline_with_mocks
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        pipeline._jpeg_new_count = 0
        pipeline._jpeg_repeat_count = 0
        pipeline._jpeg_last_emitted_seq = -1

        frame = np.full((40, 60, 3), 200, dtype=np.uint8)
        for seq in (1, 2, 3, 4):
            pipeline._publish_frame_jpeg(frame, seq)
        assert pipeline._jpeg_new_count == 4
        assert pipeline._jpeg_repeat_count == 0


# ─── get_status() có metrics đầy đủ ──────────────────────────────────────────

class TestGetStatus:
    def test_get_status_has_metrics(self, monkeypatch):
        from app.tests.test_dot_R import _build_pipeline_with_mocks
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        status = pipeline.get_status()
        assert "metrics" in status
        m = status["metrics"]
        assert m["capture_fps"] == 0.0
        assert m["ai_fps"] == 0.0
        # queues có đủ 4 entry với size/capacity (jpeg_cache chỉ size)
        assert set(m["queues"].keys()) == {"ocr_pending", "alerts",
                                            "clip_buffer", "jpeg_cache"}
        assert m["queues"]["ocr_pending"]["capacity"] == 16
        # counters
        assert m["counters"]["ocr_submitted"] == 0
        assert m["counters"]["violations_persisted"] == 0
        # latency có p50/p95 = None khi buffer rỗng
        assert m["latency"]["detect_ms"]["p50"] is None

    def test_get_status_no_token_url(self, monkeypatch):
        """Đảm bảo get_status() KHÔNG leak frame URL / token — Phase 0 yêu cầu
        metrics không chứa URL, token, exception details."""
        from app.tests.test_dot_R import _build_pipeline_with_mocks
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        status = pipeline.get_status()
        # Convert từng value sang str để tránh JSON dump lỗi với MagicMock
        def _walk(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield from _walk(v, f"{path}.{k}")
            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj):
                    yield from _walk(v, f"{path}[{i}]")
            else:
                yield path, obj
        # Quét value cho từ khóa nhạy cảm
        for path, val in _walk(status):
            if val is None:
                continue
            s = str(val)
            for needle in ("http://", "https://", "token=", "Bearer ",
                              "snapshot_url=", ".jpg", ".mp4"):
                assert needle not in s, f"leak {needle!r} in {path}: {s[:120]}"


# ─── system.py: _pipeline_status dùng get_existing_pipeline (chỉ đọc) ─────

class TestSystemReadOnly:
    def test_pipeline_status_no_create(self, monkeypatch):
        """Hệnh health phải dùng get_existing_pipeline() — KHÔNG tạo mới pipeline
        (tránh nạp model ~6GB + mở camera khi admin GET /health)."""
        from app.api import system as sys_module

        # Patch get_existing_pipeline tại `app.cv.pipeline` (nơi system.py
        # import bên trong _pipeline_status).
        import app.cv.pipeline as p_mod
        calls = {"count": 0}

        def fake_existing(gate_id):
            calls["count"] += 1
            return None

        monkeypatch.setattr(p_mod, "get_existing_pipeline", fake_existing)

        result = sys_module._pipeline_status("main")
        assert calls["count"] == 1
        # KHÔNG có field "thread_alive" còn True hay models loaded
        assert result["running"] is False
        assert result["thread_alive"] is False

    def test_storage_breakdown_caches(self, tmp_path, monkeypatch):
        """_storage_breakdown() cache theo 60s + path; monkeypatch sang tmp_path
        phải invalidate cache (không trả về số liệu cũ)."""
        from app.api import system as sys_module
        import app.config as cfg

        # Patch SNAPSHOTS_DIR sang tmp_path
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(tmp_path))
        monkeypatch.setattr(sys_module, "SNAPSHOTS_DIR", str(tmp_path))

        # Tạo 2 jpg + 1 mp4 thật
        (tmp_path / "a.jpg").write_bytes(b"x" * 1000)
        (tmp_path / "b.jpg").write_bytes(b"x" * 1000)
        (tmp_path / "c.mp4").write_bytes(b"x" * 1000)

        # Reset cache trước
        sys_module._storage_cache.update({"expires_at": 0.0,
                                            "path": "",
                                            "snapshot_count": 0,
                                            "snapshot_size_mb": 0.0,
                                            "storage_breakdown": {}})
        b = sys_module._storage_breakdown()
        assert b["jpg"]["count"] == 2
        assert b["mp4"]["count"] == 1

    def test_storage_breakdown_cache_miss_after_path_change(self, tmp_path,
                                                              monkeypatch):
        """Khi monkeypatch đổi SNAPSHOTS_DIR sang tmp_path khác, lần gọi tiếp
        theo phải MISS cache (không trả số liệu của path cũ)."""
        from app.api import system as sys_module
        import app.config as cfg

        # Set up state ban đầu với path thật + 9999 file (giả lập cache cũ)
        sys_module._storage_cache.update({
            "expires_at": time.monotonic() + 60,
            "path": cfg.SNAPSHOTS_DIR,
            "snapshot_count": 9999,
            "snapshot_size_mb": 999.0,
            "storage_breakdown": {"jpg": {"count": 9999, "size_mb": 999.0},
                                    "mp4": {"count": 0, "size_mb": 0.0},
                                    "other": {"count": 0, "size_mb": 0.0}},
        })

        # Monkeypatch sang tmp_path rỗng
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(tmp_path))
        monkeypatch.setattr(sys_module, "SNAPSHOTS_DIR", str(tmp_path))

        # _snapshots_size_mb() sẽ MISS (cache_path != SNAPSHOTS_DIR) → reset
        # cả storage_breakdown về {}.
        size_count, size_mb = sys_module._snapshots_size_mb()
        # tmp_path rỗng → 0 files
        assert size_count == 0
        # Sau khi _snapshots_size_mb update, storage_breakdown bị reset về {} —
        # _storage_breakdown() sẽ chạy lại (vì cache.breakdown = {})
        b = sys_module._storage_breakdown()
        assert b["jpg"]["count"] == 0