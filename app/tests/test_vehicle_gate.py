"""
pytest tests for the vehicle-type gate in _process_violations (app/cv/pipeline.py).

Regression coverage: before this gate existed, EVERY detected person was treated
as if they must have a readable plate — a pedestrian walking through the gate
with no bike at all got flagged PLATE_UNREADABLE, and a student on a regular
bicycle (not legally required to wear a helmet) could get flagged NO_HELMET.
"""
import time
from unittest.mock import patch, MagicMock
import numpy as np


class _SyncPool:
    """Test stand-in for ThreadPoolExecutor — runs submitted work inline so
    assertions right after _process_violations() see its effects deterministically."""
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return MagicMock()


def _make_pipeline():
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    pipeline._last_log_time = {}
    pipeline._last_alert_time = 0.0
    pipeline._alert_queue = MagicMock()
    pipeline._io_pool = _SyncPool()
    pipeline._plate_ocr_cache = {}
    pipeline._clip_buffer = []
    pipeline._plate_attempts = 0
    pipeline._plate_successes = 0
    return pipeline


def _frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_no_vehicle_detected_skips_entirely():
    """Pedestrian (no motorcycle/bicycle nearby) must not be flagged at all."""
    pipeline = _make_pipeline()
    with patch("app.cv.pipeline.add_violation_event") as mock_add:
        pipeline._process_violations(_frame(), helmet_dets=[], plate_dets=[], vehicle_type=None)
    mock_add.assert_not_called()
    pipeline._alert_queue.put.assert_not_called()


def test_bicycle_skips_helmet_and_plate_checks():
    """Regular bicycle is exempt from helmet law — must not be flagged."""
    pipeline = _make_pipeline()
    with patch("app.cv.pipeline.add_violation_event") as mock_add:
        pipeline._process_violations(_frame(), helmet_dets=[], plate_dets=[], vehicle_type="bicycle")
    mock_add.assert_not_called()
    pipeline._alert_queue.put.assert_not_called()


def test_motorcycle_is_unaffected_by_gate():
    """Motorcycle must not be short-circuited by the gate — existing logic still runs."""
    pipeline = _make_pipeline()
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("os.makedirs"):
        pipeline._process_violations(_frame(), helmet_dets=[], plate_dets=[], vehicle_type="motorcycle")
    # No plate_dets at all → NO_PLATE (Feature 1: split from PLATE_UNREADABLE).
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "NO_PLATE"


def test_walking_bike_bare_head_is_not_no_helmet():
    """Dắt xe (đứng, posture 'standing'), đầu trần: không bắt buộc đội mũ khi không lái —
    chỉ bắt NO_PLATE (không có plate_dets), không được có NO_HELMET."""
    pipeline = _make_pipeline()
    helmet_dets = [MagicMock(class_name="Without Helmet")]
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("os.makedirs"):
        pipeline._process_violations(
            _frame(), helmet_dets=helmet_dets, plate_dets=[],
            posture_status="standing", vehicle_type="motorcycle",
        )
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "NO_PLATE"


def test_riding_bare_head_is_still_flagged():
    """Ngồi lái (posture 'riding'), đầu trần: vẫn phải bắt lỗi (RIDING_THROUGH_GATE), không được bỏ qua."""
    pipeline = _make_pipeline()
    helmet_dets = [MagicMock(class_name="Without Helmet")]
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("os.makedirs"):
        pipeline._process_violations(
            _frame(), helmet_dets=helmet_dets, plate_dets=[],
            posture_status="riding", vehicle_type="motorcycle",
        )
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "MULTIPLE"


def test_too_many_riders_flags_violation():
    """Chở quá số người quy định, không kèm vi phạm khác → TOO_MANY_RIDERS riêng."""
    pipeline = _make_pipeline()
    helmet_dets = [MagicMock(class_name="With Helmet")]
    plate_dets = [MagicMock(bbox=(10, 10, 70, 45))]
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("app.cv.pipeline.read_plate", return_value="29A12345"), \
         patch("app.cv.pipeline.get_vehicle_by_plate", return_value={"plate_number": "29A12345"}), \
         patch("os.makedirs"):
        pipeline._process_violations(
            _frame(), helmet_dets=helmet_dets, plate_dets=plate_dets,
            vehicle_type="motorcycle", too_many_riders=True,
        )
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "TOO_MANY_RIDERS"


def test_too_many_riders_combines_with_no_helmet():
    """Chở quá người + không đội mũ cùng lúc → gộp thành MULTIPLE."""
    pipeline = _make_pipeline()
    helmet_dets = [MagicMock(class_name="Without Helmet")]
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("os.makedirs"):
        pipeline._process_violations(
            _frame(), helmet_dets=helmet_dets, plate_dets=[],
            vehicle_type="motorcycle", too_many_riders=True,
        )
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "MULTIPLE"


def test_count_riders_per_vehicle_flags_all_when_over_limit():
    """3 người cùng khớp 1 xe (giới hạn mặc định 2) → cả 3 group đều bị đánh dấu."""
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    vehicle = MagicMock(bbox=(0, 0, 100, 100))
    groups = [{'_vehicle': vehicle} for _ in range(3)]
    pipeline._count_riders_per_vehicle(groups)
    assert all(g.get('too_many_riders') is True for g in groups)


def test_count_riders_per_vehicle_ok_at_exact_limit():
    """Đúng 2 người khớp 1 xe (bằng giới hạn, không vượt) → KHÔNG bị đánh dấu."""
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    vehicle = MagicMock(bbox=(0, 0, 100, 100))
    groups = [{'_vehicle': vehicle} for _ in range(2)]
    pipeline._count_riders_per_vehicle(groups)
    assert all('too_many_riders' not in g for g in groups)


def test_count_riders_per_vehicle_ignores_pedestrians():
    """Group không khớp xe nào (_vehicle=None, người đi bộ) không được tính vào bất kỳ xe nào."""
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    vehicle = MagicMock(bbox=(0, 0, 100, 100))
    groups = [{'_vehicle': vehicle} for _ in range(2)] + [{'_vehicle': None} for _ in range(5)]
    pipeline._count_riders_per_vehicle(groups)
    assert all('too_many_riders' not in g for g in groups)
