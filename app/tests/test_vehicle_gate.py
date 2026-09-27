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


def _make_pipeline():
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    pipeline._last_log_time = {}
    pipeline._last_alert_time = 0.0
    pipeline._alert_queue = MagicMock()
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
    # No plate_dets at all → pre-existing behavior (unchanged by the gate) is PLATE_UNREADABLE.
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["violation_type"] == "PLATE_UNREADABLE"
