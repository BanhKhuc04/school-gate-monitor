"""
Ghi vi phạm theo từng người/xe (track) — app/cv/pipeline.py + app/cv/tracker.py.

Hồi quy cho lỗi: mọi xe không đọc được biển số dùng chung khóa cooldown "UNKNOWN"
60s → xe thứ 2, 3... không biển số đi qua trong cùng 1 phút bị BỎ SÓT hoàn toàn.
"""
import time
import threading
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from app.cv.detector import Detection, helmet_state
from app.cv.plate_voter import PlateVoter


class _SyncPool:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return MagicMock()

    def shutdown(self, wait=False):
        pass


def _make_pipeline():
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    pipeline.gate_id = "main"
    pipeline.gate_name = "Cổng Chính"
    pipeline._last_log_time = {}
    pipeline._last_alert_time = 0.0
    pipeline._alert_queue = MagicMock()
    pipeline._io_pool = _SyncPool()
    pipeline._plate_voter = PlateVoter(grid_px=60, window_sec=2.5, min_agree=2, min_confidence_single=0.55)
    pipeline._clip_buffer = []
    pipeline._plate_attempts = 0
    pipeline._plate_successes = 0
    pipeline._track_state = {}
    return pipeline


def _step(pipeline, track_id, **kwargs):
    """Mô phỏng đúng việc _run_loop làm cho 1 người ở 1 khung hình."""
    state = pipeline._track_state.setdefault(track_id, pipeline._new_track_state())
    state['frames'] += 1
    state['last_seen'] = time.time()
    kwargs.setdefault('helmet_dets', [])
    kwargs.setdefault('plate_dets', [])
    kwargs.setdefault('vehicle_type', 'motorcycle')
    return pipeline._process_violations(np.zeros((100, 100, 3), dtype=np.uint8), track_id=track_id, **kwargs)


@pytest.fixture
def db_calls():
    with patch("app.cv.pipeline.add_violation_event", return_value=1) as mock_add, \
         patch("app.cv.pipeline.cv2.imwrite", return_value=True), \
         patch("app.cv.pipeline.get_vehicle_by_plate", return_value=None), \
         patch("os.makedirs"):
        yield mock_add


def test_two_different_plateless_vehicles_both_logged(db_calls):
    """Lỗi cũ: xe thứ 2 không biển số trong cùng 60s bị bỏ sót."""
    pipeline = _make_pipeline()
    for _ in range(3):
        _step(pipeline, track_id=1)
    for _ in range(3):
        _step(pipeline, track_id=2)
    assert db_calls.call_count == 2
    assert [c.kwargs["violation_type"] for c in db_calls.call_args_list] == ["NO_PLATE", "NO_PLATE"]


def test_same_vehicle_logged_once_and_alerted_once(db_calls):
    pipeline = _make_pipeline()
    for _ in range(20):
        _step(pipeline, track_id=7)
    assert db_calls.call_count == 1
    assert pipeline._alert_queue.put.call_count == 1


def test_not_logged_before_min_frames(db_calls):
    from app.config import TRACK_MIN_FRAMES
    pipeline = _make_pipeline()
    for _ in range(TRACK_MIN_FRAMES - 1):
        summary = _step(pipeline, track_id=3)
        assert summary['pending'] is True
    db_calls.assert_not_called()
    summary = _step(pipeline, track_id=3)
    assert summary['logged'] is True
    db_calls.assert_called_once()


def test_plate_seen_earlier_is_not_reported_as_no_plate(db_calls):
    """Biển số đã thấy + đọc rõ ở khung trước, khung sau bị che → vẫn dùng biển đã đọc."""
    pipeline = _make_pipeline()
    plate = [MagicMock(bbox=(10, 10, 70, 45))]
    with patch("app.cv.pipeline.read_plate_detailed", return_value={"full": "29A12345", "confidence": 0.9}):
        _step(pipeline, track_id=4, plate_dets=plate)
    _step(pipeline, track_id=4)
    _step(pipeline, track_id=4)
    db_calls.assert_called_once()
    kwargs = db_calls.call_args.kwargs
    assert kwargs["violation_type"] == "PLATE_NOT_REGISTERED"
    assert kwargs["plate_read"] == "29A12345"


def test_registered_vehicle_with_helmet_no_violation(db_calls):
    pipeline = _make_pipeline()
    plate = [MagicMock(bbox=(10, 10, 70, 45))]
    helmet = [MagicMock(class_name="With Helmet")]
    with patch("app.cv.pipeline.read_plate_detailed", return_value={"full": "29A12345", "confidence": 0.9}), \
         patch("app.cv.pipeline.get_vehicle_by_plate", return_value={"plate_number": "29A12345"}):
        for _ in range(5):
            summary = _step(pipeline, track_id=5, plate_dets=plate, helmet_dets=helmet, posture_status='standing')
    db_calls.assert_not_called()
    assert summary['registered'] is True and summary['violations'] == []


def test_single_frame_helmet_flicker_does_not_flag_no_helmet(db_calls):
    """1 khung hình nhiễu 'không mũ' giữa nhiều khung 'có mũ' → không bắt lỗi."""
    pipeline = _make_pipeline()
    plate = [MagicMock(bbox=(10, 10, 70, 45))]
    with patch("app.cv.pipeline.read_plate_detailed", return_value={"full": "29A12345", "confidence": 0.9}), \
         patch("app.cv.pipeline.get_vehicle_by_plate", return_value={"plate_number": "29A12345"}):
        _step(pipeline, track_id=6, plate_dets=plate, helmet_dets=[MagicMock(class_name="With Helmet")], posture_status='standing')
        _step(pipeline, track_id=6, plate_dets=plate, helmet_dets=[MagicMock(class_name="Without Helmet")], posture_status='standing')
        _step(pipeline, track_id=6, plate_dets=plate, helmet_dets=[MagicMock(class_name="With Helmet")], posture_status='standing')
    db_calls.assert_not_called()


def test_no_helmet_majority_is_flagged_with_details(db_calls):
    pipeline = _make_pipeline()
    for _ in range(3):
        _step(pipeline, track_id=8, helmet_dets=[MagicMock(class_name="no_helmet")])
    db_calls.assert_called_once()
    kwargs = db_calls.call_args.kwargs
    assert kwargs["violation_type"] == "MULTIPLE"
    assert kwargs["violation_details"] == "NO_PLATE,NO_HELMET"
    alert = pipeline._alert_queue.put.call_args.args[0]
    assert alert["violation_details"] == ["NO_PLATE", "NO_HELMET"]


def test_passenger_with_different_violation_on_same_plate_is_logged(db_calls):
    """2 người trên cùng 1 xe (cùng biển): người lái có mũ, người ngồi sau không
    mũ → lỗi khác nhau thì đều được ghi; cùng lỗi thì chỉ ghi 1 lần."""
    pipeline = _make_pipeline()
    plate = [MagicMock(bbox=(10, 10, 70, 45))]
    with patch("app.cv.pipeline.read_plate_detailed", return_value={"full": "29A12345", "confidence": 0.9}):
        for _ in range(3):
            _step(pipeline, track_id=10, plate_dets=plate, helmet_dets=[MagicMock(class_name="With Helmet")], posture_status='standing')
            _step(pipeline, track_id=11, plate_dets=plate, helmet_dets=[MagicMock(class_name="Without Helmet")])
            _step(pipeline, track_id=12, plate_dets=plate, helmet_dets=[MagicMock(class_name="With Helmet")], posture_status='standing')
    types = [c.kwargs["violation_type"] for c in db_calls.call_args_list]
    assert sorted(types) == ["MULTIPLE", "PLATE_NOT_REGISTERED"]


def test_track_state_pruned_after_idle():
    pipeline = _make_pipeline()
    pipeline._track_state[1] = dict(pipeline._new_track_state(), last_seen=0.0)
    pipeline._track_state[2] = dict(pipeline._new_track_state(), last_seen=time.time())
    pipeline._prune_track_state(time.time())
    assert set(pipeline._track_state) == {2}


def test_labels_show_plate_and_violations():
    pipeline = _make_pipeline()
    person = Detection('person', 0.9, (100, 100, 200, 400))
    plate = Detection('plate', 0.9, (120, 300, 180, 340))
    group = {'_person': person, 'track_id': 3, 'plate_dets': [plate], 'vehicle_type': 'motorcycle'}
    summary = {'plate': '59K165072', 'registered': False, 'review': False,
               'violations': ['PLATE_NOT_REGISTERED', 'NO_HELMET'], 'logged': True, 'pending': False}
    labels = pipeline._labels_for_group(group, summary)
    texts = [t for _, t, _ in labels]
    assert texts == ["#3 BIEN LA, KHONG MU", "59K1-650.72 CHUA DANG KY"]
    assert pipeline._labels_for_group({'_person': person, 'track_id': 1, 'vehicle_type': None}, None)[0][1] == "#1 DI BO"


def test_helmet_state_accepts_common_class_names():
    assert helmet_state("With Helmet") == 'with'
    assert helmet_state("helmet") == 'with'
    assert helmet_state("Without Helmet") == 'without'
    assert helmet_state("no_helmet") == 'without'
    assert helmet_state("plate") is None  # model biển số đặt nhầm tên → phải bị phát hiện


# ─── END-TO-END: chạy đúng _run_loop thật với detector giả theo kịch bản ───

_SCRIPT: dict[int, dict] = {}


class _Scenario:
    frame_no = 0


class _FakeStream:
    def read_frame(self):
        _Scenario.frame_no += 1
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        time.sleep(0.002)
        return frame

    def release(self):
        pass


class _FakeDetector:
    """Trả detection theo kịch bản _SCRIPT[frame_no] (tọa độ ảnh detect 640x480)."""
    def __init__(self, model_path, conf_threshold=0.25, imgsz=None, fallback_path=None):
        self.model_path = model_path
        if "helmet" in model_path:
            self.role, self.class_names = "helmet", {0: "With Helmet", 1: "Without Helmet"}
        elif "plate" in model_path:
            self.role, self.class_names = "plate", {0: "plate"}
        else:
            self.role, self.class_names = "person", {0: "person", 3: "motorcycle"}

    def detect(self, frame):
        return list(_SCRIPT.get(_Scenario.frame_no, {}).get(self.role, []))


class _NoPose:
    def detect_pose(self, crop):
        return None


def _rider(x):
    """Người + xe máy ở vị trí x (ảnh detect 640x480, giữa khung — không chạm mép)."""
    return {"person": [Detection("person", 0.9, (x, 100, x + 60, 300)),
                       Detection("motorcycle", 0.9, (x - 10, 200, x + 70, 360))]}


def test_run_loop_end_to_end_two_plateless_vehicles(test_app, tmp_path, monkeypatch):
    import app.cv.pipeline as pl
    import app.cv.pose as pose_module
    from app.db import list_violations

    monkeypatch.setattr(pl, "HelmetPlateDetector", _FakeDetector)
    monkeypatch.setattr(pl, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setattr(pl, "FRAME_SKIP", 1)
    monkeypatch.setattr(pl, "warm_up_ocr", lambda: None)
    monkeypatch.setattr(pose_module, "PostureDetector", _NoPose)
    monkeypatch.setattr(pl.VideoPipeline, "_open_webcam", lambda self, cfg: _FakeStream())

    # Xe A (frame 1-8) rồi xe B ở chỗ khác (frame 12-19), cả 2 không có biển số
    _SCRIPT.clear()
    for f in range(1, 9):
        _SCRIPT[f] = _rider(100 + 10 * f)
    for f in range(12, 20):
        _SCRIPT[f] = _rider(420 + 5 * f)
    _Scenario.frame_no = 0

    before = list_violations(limit=1000)["total"]
    pipeline = pl.VideoPipeline("main", {"source": 0, "name": "Cổng Chính"})
    pipeline._io_pool = _SyncPool()  # ghi DB ngay để assert chắc chắn
    pipeline.start()
    try:
        deadline = time.monotonic() + 20
        while _Scenario.frame_no < 25 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        pipeline.stop()

    new_items = list_violations(limit=1000)["items"][: list_violations(limit=1000)["total"] - before]
    assert len(new_items) == 2, [dict(i) for i in new_items]
    assert all(i["violation_type"] == "NO_PLATE" for i in new_items)
    assert pipeline.get_status()["helmet_model_ok"] is True
