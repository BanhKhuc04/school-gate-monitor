"""R2 slice 2 — Source epoch filter cho OCR callback xuyên pipeline.

Theo handoff §3 R2:
- Sau khi `_apply_camera_change` chạy, `_source_epoch` tăng.
- Mọi OCR result từ epoch cũ KHÔNG được ảnh hưởng tới pipeline mới.
- `_ocr_consume_pending_if_fresh` đã có filter — R2 slice 2 bổ sung test
  để đảm bảo hành vi ổn định và không có test nào "cheat" bằng cách
  bypass filter.

Mỗi test nhắm vào một hành vi độc lập để dễ truy vết khi regress.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.cv.pipeline import VideoPipeline


# ── 1. _ocr_consume_pending_if_fresh lọc result có source_epoch cũ ────────


def _make_minimal_pipeline():
    """Tạo VideoPipeline instance tối thiểu đủ để test OCR consume filter.

    Không gọi __init__ đầy đủ (cần GATES, lock, executor). Thay vào đó
    set các attribute cần thiết cho `_ocr_consume_pending_if_fresh`.
    """
    pipeline = VideoPipeline.__new__(VideoPipeline)
    pipeline._ocr_pending = {}
    pipeline._ocr_submit_meta = {}
    pipeline._ocr_health = {
        "submitted": 0, "completed": 0, "errors": 0, "stale_dropped": 0, "empty": 0,
    }
    pipeline._metrics_ocr_wait = MagicMock()
    pipeline._metrics_ocr_wait.add = MagicMock()
    return pipeline


def test_consume_pending_if_fresh_drops_stale_source_epoch():
    """OCR result có source_epoch cũ (khác current_epoch) phải bị drop,
    KHÔNG trả về cho caller. Counter `stale_dropped` phải tăng.
    """
    pipeline = _make_minimal_pipeline()
    current_epoch = 5
    # Giả lập pending result từ epoch 4 (cũ hơn current 1)
    fut = Future()
    fut.set_result({"full": "30A-123", "source_epoch": 4, "frame_seq": 100,
                    "track_id": 1, "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[1] = fut
    pipeline._ocr_submit_meta[1] = {"ts": time.time(), "frame_seq": 100}

    result = pipeline._ocr_consume_pending_if_fresh(1, current_epoch)
    assert result is None, "Stale result phải bị drop"
    assert pipeline._ocr_health["stale_dropped"] == 1


def test_consume_pending_if_fresh_keeps_matching_source_epoch():
    """OCR result có source_epoch == current_epoch thì được giữ lại."""
    pipeline = _make_minimal_pipeline()
    current_epoch = 5
    fut = Future()
    fut.set_result({"full": "30A-123", "source_epoch": 5, "frame_seq": 100,
                    "track_id": 1, "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[1] = fut
    pipeline._ocr_submit_meta[1] = {"ts": time.time(), "frame_seq": 100}

    result = pipeline._ocr_consume_pending_if_fresh(1, current_epoch)
    assert result is not None
    assert result["full"] == "30A-123"


def test_consume_pending_if_fresh_drops_track_id_mismatch():
    """Result có track_id khác với key submit → drop (chống cross-track leak)."""
    pipeline = _make_minimal_pipeline()
    current_epoch = 5
    fut = Future()
    fut.set_result({"full": "30A-123", "source_epoch": 5, "frame_seq": 100,
                    "track_id": 99,  # khác với key submit 1
                    "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[1] = fut
    pipeline._ocr_submit_meta[1] = {"ts": time.time(), "frame_seq": 100}

    result = pipeline._ocr_consume_pending_if_fresh(1, current_epoch)
    assert result is None
    assert pipeline._ocr_health["stale_dropped"] == 1


def test_consume_pending_if_fresh_drops_oversized_latency():
    """Result submit quá lâu (> PLATE_VOTE_WINDOW_SEC) → drop."""
    from app.config import PLATE_VOTE_WINDOW_SEC
    pipeline = _make_minimal_pipeline()
    current_epoch = 5
    fut = Future()
    fut.set_result({"full": "30A-123", "source_epoch": 5, "frame_seq": 100,
                    "track_id": 1, "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[1] = fut
    # Submit cách đây quá PLATE_VOTE_WINDOW_SEC + 1s
    pipeline._ocr_submit_meta[1] = {
        "ts": time.time() - PLATE_VOTE_WINDOW_SEC - 1.0,
        "frame_seq": 100,
    }

    result = pipeline._ocr_consume_pending_if_fresh(1, current_epoch)
    assert result is None
    assert pipeline._ocr_health["stale_dropped"] == 1


# ── 2. _apply_camera_change tăng epoch và clear pending OCR ──────────────


def test_apply_camera_change_increments_source_epoch_and_clears_pending(monkeypatch):
    """Sau _apply_camera_change: _source_epoch phải tăng, _ocr_pending bị clear,
    _recognition_results bị clear, _plate_consensus.reset() được gọi.
    """
    pipeline = _make_minimal_pipeline()
    pipeline._source_epoch = 3
    pipeline._ocr_pending = {1: MagicMock(), 2: MagicMock()}
    pipeline._ocr_submit_meta = {1: {"ts": 0, "frame_seq": 1}, 2: {"ts": 0, "frame_seq": 2}}
    pipeline._recognition_log = MagicMock()
    pipeline._recognition_results = [MagicMock(), MagicMock()]
    pipeline._recognition_cards = MagicMock()
    pipeline._plate_consensus = MagicMock()
    pipeline._best_plates = MagicMock()
    pipeline._riding_temporal = MagicMock()
    pipeline._lock = threading.Lock()
    pipeline._latest_frame = None
    pipeline._latest_jpeg = None
    pipeline._jpeg_cache = MagicMock()
    pipeline._jpeg_cache.clear = MagicMock()
    pipeline._last_person_dets = [1]
    pipeline._last_helmet_dets = [1]
    pipeline._last_plate_dets = [1]
    pipeline._last_pose_data = [1]
    pipeline._prev_track_bbox = {1: (0, 0, 10, 10)}
    pipeline._track_vehicle_history = {1: []}
    pipeline._last_face_t = 1.0
    pipeline._last_log_time = {1: 1.0}
    pipeline._plate_approach = {1: 1.0}
    pipeline._crossing_sealed = {1: True}
    pipeline._plate_last_crossing = {1: 1.0}
    pipeline._last_sealed_crossing = {1: 1.0}
    pipeline._crossing_event_to_db_id = {1: 1}
    pipeline._evidence_ledger = MagicMock()
    pipeline._crossing_detector = MagicMock()

    # Mock stop_capture trả True và camera_switch (phải là CameraSwitch instance
    # thật để pass isinstance check trong _apply_camera_change).
    pipeline._stop_capture = MagicMock(return_value=True)

    from app.cv.camera_switch import CameraSwitch
    # Dùng instance thật (không phải spec mock) để chắc chắn pass isinstance check
    real_switch = CameraSwitch("old_source")
    real_switch._pending = "fake_source"  # trigger apply thật
    real_switch.apply = MagicMock(return_value=(MagicMock(), None))
    real_switch.source = "fake_source"
    pipeline.camera_switch = real_switch
    pipeline._open_webcam = MagicMock()
    pipeline._start_capture = MagicMock()
    pipeline._webcam = MagicMock()
    # GATES dict (mock)
    import app.cv.pipeline as pipe_mod
    monkeypatch.setitem(pipe_mod.GATES, "test_gate", {"source": "old"})

    # Patch set_gate_camera_source (gọi qua lambda) để tránh DB write
    monkeypatch.setattr(pipe_mod, "set_gate_camera_source", lambda *a, **kw: None)

    # Gọi _apply_camera_change
    pipeline.gate_id = "test_gate"
    try:
        ok = pipeline._apply_camera_change()
    except Exception as e:
        pytest.fail(f"_apply_camera_change raised: {e!r}")
    assert ok is True, f"_apply_camera_change returned False (epoch={pipeline._source_epoch}, pending={pipeline._ocr_pending})"
    assert pipeline._source_epoch == 4
    assert pipeline._ocr_pending == {}, "OCR pending phải được clear"
    pipeline._plate_consensus.reset.assert_called_once()
    pipeline._recognition_log.reset.assert_called_once_with(4)


def test_apply_camera_change_keeps_old_epoch_if_stop_capture_fails():
    """Nếu _stop_capture fail → _apply_camera_change trả False, epoch KHÔNG tăng,
    pending KHÔNG clear (giữ state cũ cho caller retry)."""
    pipeline = _make_minimal_pipeline()
    pipeline._source_epoch = 3
    original_pending = {1: MagicMock()}
    pipeline._ocr_pending = original_pending
    pipeline._ocr_submit_meta = {}
    pipeline._recognition_log = MagicMock()
    pipeline._recognition_cards = MagicMock()
    pipeline._plate_consensus = MagicMock()
    pipeline._lock = threading.Lock()
    pipeline._stop_capture = MagicMock(return_value=False)

    ok = pipeline._apply_camera_change()
    assert ok is False
    assert pipeline._source_epoch == 3, "Epoch không được tăng khi stop fail"
    assert pipeline._ocr_pending is original_pending, "Pending phải giữ nguyên"


# ── 3. Stale OCR result qua nhiều epoch đều bị drop ──────────────────────


def test_stale_results_from_multiple_old_epochs_all_dropped():
    """3 result từ 3 epoch khác nhau (đều < current) đều phải drop.
    Verify filter hoạt động xuyên suốt nhiều epoch thay đổi.
    """
    pipeline = _make_minimal_pipeline()
    current_epoch = 10
    for old_epoch in (7, 8, 9):
        fut = Future()
        fut.set_result({"full": f"plate_e{old_epoch}", "source_epoch": old_epoch,
                        "frame_seq": 100, "track_id": 1,
                        "completed_monotonic": time.monotonic()})
        pipeline._ocr_pending[old_epoch] = fut
        pipeline._ocr_submit_meta[old_epoch] = {"ts": time.time(), "frame_seq": 100}

    for old_epoch in (7, 8, 9):
        result = pipeline._ocr_consume_pending_if_fresh(old_epoch, current_epoch)
        assert result is None, f"Epoch {old_epoch} phải bị drop"
    assert pipeline._ocr_health["stale_dropped"] == 3


# ── 4. Mỗi track_id trong pending có thể stale independently ──────────────


def test_stale_filter_per_track_independent():
    """Track A có result epoch cũ, track B có result epoch mới →
    track A bị drop, track B được giữ.
    """
    pipeline = _make_minimal_pipeline()
    current_epoch = 5

    # Track 1: result từ epoch 3 (cũ)
    fut_old = Future()
    fut_old.set_result({"full": "OLD", "source_epoch": 3, "frame_seq": 100,
                        "track_id": 1, "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[1] = fut_old
    pipeline._ocr_submit_meta[1] = {"ts": time.time(), "frame_seq": 100}

    # Track 2: result từ epoch 5 (mới)
    fut_new = Future()
    fut_new.set_result({"full": "NEW", "source_epoch": 5, "frame_seq": 200,
                        "track_id": 2, "completed_monotonic": time.monotonic()})
    pipeline._ocr_pending[2] = fut_new
    pipeline._ocr_submit_meta[2] = {"ts": time.time(), "frame_seq": 200}

    r1 = pipeline._ocr_consume_pending_if_fresh(1, current_epoch)
    r2 = pipeline._ocr_consume_pending_if_fresh(2, current_epoch)
    assert r1 is None, "Track 1 phải drop"
    assert r2 is not None and r2["full"] == "NEW", "Track 2 phải giữ"
    assert pipeline._ocr_health["stale_dropped"] == 1
    # `completed` tăng cho cả 2 lần consume (kể cả stale) — verify metric khác
    assert pipeline._ocr_health["errors"] == 0
    assert pipeline._ocr_health["empty"] == 0
