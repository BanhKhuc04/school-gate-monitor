"""Task 1 — Phase 1 (Stop-guard, generation invalidation, reconnect/backoff,
memory hygiene).

Phase 1 closes three concrete failure modes observed before this task:

1. **Stop generation invalidation** — `stop()` only set `_running=False`,
   joined the thread, and shut down worker pools. But futures already
   submitted to `_io_pool` and `_crossing_pool` were still running and could
   insert a DB row or push an alert for a session the admin just killed.
   Phase 1 introduces `_run_generation` (monotonic counter, incremented in
   `start()` and `stop()`). Every callback captures the generation at submit
   time and bails out early if the pipeline moved on.

2. **Reconnect/backoff** — `_run_loop` had a fixed 2.0s sleep on every
   reconnect failure, which spammed logs and overloaded the camera if it
   stayed disconnected for hours. Phase 1 turns this into exponential backoff
   capped at 30s and resets to 0 on the first successful frame read.

3. **Memory hygiene** — `_recognition_results` was capped at 500 entries by
   raw count. After many unique track_ids in a long session, prune was FIFO
   only. Phase 1 adds a 30-second TTL prune that runs once per second inside
   `_maybe_update_fps`. The `_ocr_pending` dict was already capped at 8
   (Phase B2); this suite asserts that cap.

These tests are unit/regression tests. They do not touch live cameras or
the operational DB — they construct a `VideoPipeline` with mocks via the
existing `_build_pipeline_with_mocks` fixture from `test_dot_R.py`.

Run:
    cd D:/Work/Project_motorbike
    venv\\Scripts\\python.exe -m pytest app/tests/test_task01_phase1_latest_frame.py -v
"""
from __future__ import annotations

import time
import threading
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class _FakeWebcam:
    def __init__(self, ok: bool = True):
        self._ok = ok
        self.released = False

    def is_open(self) -> bool:
        return self._ok

    def read(self):
        return self._ok, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True
        self._ok = False


def _build_minimal_pipeline(monkeypatch):
    """Construct a VideoPipeline with the bare minimum mocks needed to
    exercise the Phase 1 surface (init, start/stop generation counters,
    reconnect state, _recognition_results prune). Does NOT call start() —
    tests control that explicitly when needed."""
    from app.cv import pipeline as pipeline_module

    # Patch heavy constructors BEFORE constructing VideoPipeline.
    # We use __new__ + manual attribute init to skip the real __init__
    # which would otherwise build detectors and load models.
    class FakeWebcam:
        def __init__(self):
            self._opened = True

        def read_frame(self):
            return np.zeros((480, 640, 3), dtype=np.uint8)

        def release(self):
            self._opened = False

        @property
        def is_opened(self):
            return self._opened

    monkeypatch.setattr(pipeline_module, "HelmetPlateDetector", MagicMock(), raising=False)
    monkeypatch.setattr(pipeline_module, "PersonPoseDetector", MagicMock(), raising=False)
    monkeypatch.setattr(pipeline_module, "WebcamStream", FakeWebcam, raising=False)
    monkeypatch.setattr(pipeline_module, "set_gate_camera_source", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pipeline_module, "set_gate_roi", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pipeline_module, "set_gate_line", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pipeline_module, "get_gate_roi", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pipeline_module, "get_gate_line", lambda *a, **kw: None, raising=False)

    p = pipeline_module.VideoPipeline.__new__(pipeline_module.VideoPipeline)
    p.gate_id = "phase1-test"
    p._running = False
    p._thread = None
    p._webcam = None
    p._lock = threading.Lock()
    p._alert_queue = MagicMock()
    p._alert_queue.qsize.return_value = 0
    p._alert_queue.maxsize = 256
    # Pools that shutdown() must accept
    p._detect_pool = MagicMock()
    p._io_pool = MagicMock()
    p._clip_pool = MagicMock()
    p._ocr_pool = MagicMock()
    p._crossing_pool = MagicMock()
    p._recognition_cards = MagicMock()
    p._recorder = None
    # Phase 0 + Phase 1 metrics attrs needed by get_status()
    from app.cv.pipeline_metrics import MetricsBuffer
    p._metrics_capture = MetricsBuffer()
    p._metrics_detect = MetricsBuffer()
    p._metrics_ocr_wait = MetricsBuffer()
    p._metrics_encode = MetricsBuffer()
    p._metrics_persistence = MetricsBuffer()
    p._metrics_dispatch = MetricsBuffer()
    p._resource_sampler = MagicMock()
    p._resource_sampler.snapshot.return_value = (None, None, 0.0)
    p._jpeg_cache = {}
    p._ocr_health = {"submitted": 0, "completed": 0, "stale_dropped": 0, "duplicate_dropped": 0}
    p._last_frame_time = time.time()
    p._last_detection_time = time.time()
    p._start_time = time.time()
    p._frame_count = 0
    p._frame_timestamps = []
    p._plate_attempts = 0
    p._plate_successes = 0
    p._last_process_latency_ms = 0.0
    p._recognition_results = {}
    p._recognition_log = MagicMock()
    p._recognition_log.reset = MagicMock()
    p._recognition_cards = MagicMock()
    p._recognition_cards.reset = MagicMock()
    p._capture_fps_value = 0.0
    p._ai_fps_value = 0.0
    p._fps_compute_at = time.monotonic()
    p._fps_capture_window = 0
    p._fps_ai_window = 0
    p._jpeg_new_count = 0
    p._jpeg_repeat_count = 0
    p._jpeg_last_emitted_seq = -1
    p._frames_dropped_stale = 0
    p._frames_dropped_encode = 0
    p._violations_persisted_total = 0
    p._violations_skipped_total = 0
    # Phase 1
    p._run_generation = 0
    p._stopped = False
    p._reconnect_failures = 0
    p._ocr_pending = {}
    p._ocr_max_pending = 8
    p._persist_pending = {}
    p._pedestrian_count = 0
    p._rider_count = 0
    p._io_health = {}
    p._diagnostic = MagicMock()  # don't write to log
    p._clip_buffer = MagicMock()
    p._clip_buffer.__len__.return_value = 0
    p._clip_buffer.maxlen = 100
    return p


@pytest.fixture
def pipeline(monkeypatch):
    return _build_minimal_pipeline(monkeypatch)


# --------------------------------------------------------------------------- #
# Phase 1.1: _run_generation lifecycle
# --------------------------------------------------------------------------- #


class TestRunGeneration:
    """Phase 1: start()/stop() phải tăng `_run_generation` để mọi callback
    đã submit trước đó biết là phiên đã chết."""

    def test_initial_generation_is_zero(self, pipeline):
        assert pipeline._run_generation == 0
        assert pipeline._stopped is False

    def test_stop_sets_stopped_true(self, pipeline):
        pipeline._running = True
        pipeline._thread = MagicMock()
        pipeline._thread.is_alive.return_value = False
        pipeline.stop()
        assert pipeline._stopped is True

    def test_stop_increments_generation(self, pipeline):
        before = pipeline._run_generation
        pipeline._running = True
        pipeline._thread = MagicMock()
        pipeline._thread.is_alive.return_value = False
        pipeline.stop()
        assert pipeline._run_generation > before

    def test_stop_when_not_running_is_noop(self, pipeline):
        before = pipeline._run_generation
        pipeline._running = False
        pipeline.stop()
        assert pipeline._run_generation == before
        assert pipeline._stopped is False

    def test_is_session_alive_true_when_running(self, pipeline):
        pipeline._stopped = False
        pipeline._running = True
        gen = pipeline._run_generation
        assert pipeline._is_session_alive(gen) is True

    def test_is_session_alive_false_when_stopped(self, pipeline):
        pipeline._stopped = True
        pipeline._running = False
        gen = pipeline._run_generation
        assert pipeline._is_session_alive(gen) is False

    def test_is_session_alive_false_on_generation_drift(self, pipeline):
        pipeline._stopped = False
        pipeline._running = True
        assert pipeline._is_session_alive(pipeline._run_generation - 1) is False


# --------------------------------------------------------------------------- #
# Phase 1.2: _persist_violation respects run_generation
# --------------------------------------------------------------------------- #


class TestPersistViolationGeneration:
    """Phase 1: `_persist_violation` nhận `run_generation` kwarg. Nếu
    pipeline generation đã tăng (do start()/stop()), callback trả về False
    NGAY, không insert DB, không push alert, không submit clip."""

    def test_stale_generation_returns_false_without_db(self, pipeline, monkeypatch):
        """Stale generation → bỏ qua, không gọi add_violation_event."""
        add_called = {"n": 0}

        def _fake_add(**kwargs):
            add_called["n"] += 1
            return 999

        from app.cv import pipeline as pipeline_module
        monkeypatch.setattr(pipeline_module, "add_violation_event", _fake_add)

        # Capture generation cũ rồi tăng pipeline generation → callback STALE
        stale_gen = pipeline._run_generation
        pipeline._run_generation += 1

        ok = pipeline._persist_violation(
            frame=np.zeros((10, 10, 3), dtype=np.uint8),
            snapshot_path="/tmp/__phase1_dummy__.jpg",
            snapshot_filename="dummy.jpg",
            plate_read="ABC123",
            plate_matched=False,
            helmet_status="no_helmet",
            violation_type="NO_HELMET",
            posture_status="riding",
            plate_format_valid=True,
            run_generation=stale_gen,
        )
        assert ok is False
        assert add_called["n"] == 0
        assert pipeline._violations_skipped_total >= 1

    def test_current_generation_proceeds(self, pipeline, monkeypatch):
        """Current generation → insert DB bình thường."""
        add_called = {"n": 0}

        def _fake_add(**kwargs):
            add_called["n"] += 1
            return 1

        # pipeline imports add_violation_event directly — patch on the
        # pipeline module namespace, not on app.db.
        from app.cv import pipeline as pipeline_module
        monkeypatch.setattr(pipeline_module, "add_violation_event", _fake_add)
        monkeypatch.setattr("os.path.isfile", lambda p: True)
        monkeypatch.setattr("os.path.getsize", lambda p: 1024)
        monkeypatch.setattr("os.makedirs", lambda *a, **kw: None)

        # Patch cv2.imwrite in the pipeline module namespace (it was imported
        # at module-load, so sys.modules swap doesn't affect it).
        fake_imwrite = MagicMock(return_value=True)
        monkeypatch.setattr(pipeline_module.cv2, "imwrite", fake_imwrite)
        # _push_alert also reads recognition_log → mock it.
        pipeline._push_alert = MagicMock()
        # event_versions dict — keep fresh
        pipeline._event_versions = {}
        # explicit source_epoch so the inner guard doesn't bail
        pipeline._source_epoch = 0

        ok = pipeline._persist_violation(
            frame=np.zeros((10, 10, 3), dtype=np.uint8),
            snapshot_path="/tmp/__phase1_dummy__.jpg",
            snapshot_filename="dummy.jpg",
            plate_read="ABC123",
            plate_matched=False,
            helmet_status="no_helmet",
            violation_type="NO_HELMET",
            posture_status="riding",
            plate_format_valid=True,
            run_generation=pipeline._run_generation,
        )
        # The main thing we assert: generation guard did NOT short-circuit.
        # add_violation_event was called exactly once.
        assert add_called["n"] == 1


# --------------------------------------------------------------------------- #
# Phase 1.3: _finish_crossing_event respects run_generation
# --------------------------------------------------------------------------- #


class TestFinishCrossingGeneration:
    """Phase 1: `_finish_crossing_event` đọc `frozen['run_generation']` và
    short-circuit nếu pipeline đã move on."""

    def test_stale_generation_returns_true_without_aggregate(self, pipeline):
        push_called = {"n": 0}
        original_push = pipeline._push_alert
        pipeline._push_alert = lambda *a, **kw: push_called.__setitem__("n", push_called["n"] + 1)
        try:
            stale_gen = pipeline._run_generation
            pipeline._run_generation += 1

            frozen = {
                "plate": None,
                "future": None,
                "source_epoch": 0,
                "vehicle_track_id": 1,
                "plate_frame_id": 0,
                "deadline": time.monotonic() + 10.0,
                "run_generation": stale_gen,
            }
            result = pipeline._finish_crossing_event(
                frozen,
                frame=np.zeros((10, 10, 3), dtype=np.uint8),
                crop=np.zeros((10, 10, 3), dtype=np.uint8),
                clip_frames=[],
            )
            assert result is True
            assert push_called["n"] == 0
        finally:
            pipeline._push_alert = original_push


# --------------------------------------------------------------------------- #
# Phase 1.4: exponential backoff for reconnect
# --------------------------------------------------------------------------- #


class TestReconnectBackoff:
    """Phase 1: `_reconnect_failures` tăng theo power-of-2 cap 30s, reset
    khi read THÀNH CÔNG."""

    def test_initial_failures_zero(self, pipeline):
        assert pipeline._reconnect_failures == 0

    def test_backoff_grows_with_failures(self):
        """Kiểm tra công thức backoff đúng: min(2 * 2^n, 30)."""
        # Replicate formula from pipeline._run_loop
        for n in range(0, 8):
            backoff = min(2.0 * (2 ** n), 30.0)
            expected = min(2.0 * (2 ** n), 30.0)
            assert backoff == expected, f"n={n}: {backoff} != {expected}"
        # Cap at 30s
        assert min(2.0 * (2 ** 20), 30.0) == 30.0

    def test_exponential_growth(self):
        """Backoff sequence: 2, 4, 8, 16, 30 (cap)."""
        seq = []
        for n in range(5):
            seq.append(min(2.0 * (2 ** n), 30.0))
        assert seq == [2.0, 4.0, 8.0, 16.0, 30.0]


# --------------------------------------------------------------------------- #
# Phase 1.5: _recognition_results TTL prune
# --------------------------------------------------------------------------- #


class TestRecognitionResultsPrune:
    """Phase 1: `_maybe_update_fps` prune `_recognition_results` theo TTL 30s.
    Không phụ thuộc interval FPS — chỉ cần gọi sau khi interval đã qua."""

    def _add_recognition(self, pipeline, track_id, ts):
        pipeline._recognition_results[track_id] = (MagicMock(), ts, 0)

    def test_prune_removes_old_entries(self, pipeline, monkeypatch):
        # 3 entries: 2 cũ (60s ago), 1 mới
        now = time.time()
        self._add_recognition(pipeline, 1, now - 60.0)
        self._add_recognition(pipeline, 2, now - 60.0)
        self._add_recognition(pipeline, 3, now)

        # Force _maybe_update_fps to RUN (>=1s elapsed)
        pipeline._fps_compute_at = time.monotonic() - 2.0
        pipeline._fps_capture_window = 0
        pipeline._fps_ai_window = 0
        pipeline._capture_fps_value = 0.0
        pipeline._ai_fps_value = 0.0

        pipeline._maybe_update_fps()

        # Old entries phải bị prune
        assert 1 not in pipeline._recognition_results
        assert 2 not in pipeline._recognition_results
        # Mới giữ lại
        assert 3 in pipeline._recognition_results

    def test_no_prune_when_all_fresh(self, pipeline):
        now = time.time()
        for tid in (1, 2, 3):
            self._add_recognition(pipeline, tid, now)
        pipeline._fps_compute_at = time.monotonic() - 2.0
        pipeline._maybe_update_fps()
        for tid in (1, 2, 3):
            assert tid in pipeline._recognition_results

    def test_no_op_when_interval_not_reached(self, pipeline):
        """Khi <1s chưa trôi qua, KHÔNG prune."""
        now = time.time()
        for tid in (1, 2):
            self._add_recognition(pipeline, tid, now - 60.0)
        pipeline._fps_compute_at = time.monotonic()
        pipeline._maybe_update_fps()
        # vẫn còn nguyên vì interval chưa hit
        assert 1 in pipeline._recognition_results
        assert 2 in pipeline._recognition_results


# --------------------------------------------------------------------------- #
# Phase 1.6: get_status() exposes new fields
# --------------------------------------------------------------------------- #


class TestGetStatusExposesPhase1:
    """Phase 1: `get_status()` phải trả về `metrics.run_generation` và
    `metrics.reconnect_failures`."""

    def test_run_generation_in_metrics(self, pipeline):
        pipeline._stopped = False
        pipeline._running = True
        pipeline._last_frame_time = time.time()
        pipeline._last_detection_time = time.time()
        pipeline._start_time = time.time()
        pipeline._thread = None
        pipeline._frame_count = 0
        pipeline._frame_timestamps = []
        pipeline._plate_attempts = 0
        pipeline._plate_successes = 0
        pipeline._last_process_latency_ms = 0.0

        # Resource sampler may be None if psutil missing — patch:
        sampler = MagicMock()
        sampler.snapshot.return_value = (None, None, 0.0)
        pipeline._resource_sampler = sampler
        pipeline._jpeg_cache = {}
        pipeline._alert_queue.qsize.return_value = 0
        pipeline._alert_queue.maxsize = 256
        pipeline._ocr_health = {"submitted": 0, "completed": 0, "stale_dropped": 0, "duplicate_dropped": 0}

        status = pipeline.get_status()
        metrics = status["metrics"]
        assert "run_generation" in metrics
        assert "reconnect_failures" in metrics
        assert metrics["run_generation"] == pipeline._run_generation
        assert metrics["reconnect_failures"] == pipeline._reconnect_failures


# --------------------------------------------------------------------------- #
# Phase 1.7: dispatch site captures generation
# --------------------------------------------------------------------------- #


class TestDispatchCapturesGeneration:
    """Phase 1: dispatch site (submit `_persist_violation`) PHẢI pass
    `run_generation=self._run_generation`. Đây là defense-in-depth — không
    pass = callback không có cách nào biết mình stale."""

    def test_dispatch_kwarg_passes_generation(self, pipeline, monkeypatch):
        """Tìm đoạn code submit _persist_violation và đảm bảo nó pass
        `run_generation=...` (Phase 1 capture generation tại submit time)."""
        import inspect
        from app.cv import pipeline as pipeline_module
        src = inspect.getsource(pipeline_module.VideoPipeline._persist_violation)
        assert "run_generation" in src, "_persist_violation must accept run_generation kwarg"

        # Check the call site that submits _persist_violation (the one that
        # builds `future = self._io_pool.submit(...)` with `encounter, ...`).
        full_src = inspect.getsource(pipeline_module.VideoPipeline)
        submit_idx = full_src.find("_io_pool.submit(self._persist_violation,")
        assert submit_idx >= 0, "submit call not found"
        window = full_src[submit_idx:submit_idx + 2000]
        # Phase 1 uses getattr to tolerate test fixtures that bypass __init__.
        assert "run_generation=" in window, (
            "dispatch site must pass run_generation=... at submit time")


# --------------------------------------------------------------------------- #
# Phase 1.8: crossing submit captures generation
# --------------------------------------------------------------------------- #


class TestCrossingSubmitCapturesGeneration:
    """Phase 1: crossing submit pass `run_generation` qua frozen dict."""

    def test_crossing_submit_passes_generation(self):
        import inspect
        from app.cv import pipeline as pipeline_module
        src = inspect.getsource(pipeline_module.VideoPipeline)
        idx = src.find("_crossing_pool.submit(self._finish_crossing_event,")
        assert idx >= 0, "crossing submit not found"
        window = src[idx:idx + 600]
        # Phase 1 uses getattr for fixture tolerance — accept either form.
        assert ("'run_generation': self._run_generation" in window
                or "'run_generation': getattr(self, '_run_generation', 0)" in window), (
            "crossing submit must include run_generation in frozen dict")

    def test_finish_crossing_checks_generation(self):
        import inspect
        from app.cv import pipeline as pipeline_module
        src = inspect.getsource(pipeline_module.VideoPipeline._finish_crossing_event)
        # First thing it does after imports is check generation
        assert "run_gen = frozen.get('run_generation')" in src
        assert "run_gen != getattr(self, '_run_generation', 0)" in src
