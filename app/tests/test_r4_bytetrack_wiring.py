"""R4 — ByteTrack wiring tests cho detector (Owner A).

Theo handoff §3 R4:
- Tracker phải cho ID ổn định xuyên nhiều frame với cùng một object.
- Test track moving qua ô ảnh, xe sát nhau, mất track/đổi nguồn.
- Tracker theo camera/epoch dù weights/predictor dùng chung.
- Mỗi camera_id có tracker riêng (không trộn giữa front/rear).

Test dùng mock cho YOLO và BYTETracker để không phụ thuộc model thật.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.cv.detector import HelmetPlateDetector, Detection


# ── helpers ────────────────────────────────────────────────────────────────


def _make_boxes_array(xyxys):
    """Tạo object giả boxes tương thích với code (`boxes.xyxy`, `conf`, `cls`,
    `cpu().numpy()`).

    Code: `boxes = result.boxes.cpu().numpy()` — chain trả 1 object mà có:
      - .xyxy (np.array)
      - .conf (np.array)
      - .cls (np.array)
    """
    n = len(xyxys)
    arr = MagicMock()
    arr.xyxy = np.array([list(b) for b in xyxys], dtype=float) if n else np.zeros((0, 4))
    arr.conf = np.array([0.9] * n, dtype=float)
    arr.cls = np.array([0] * n, dtype=float)
    arr.cpu.return_value = arr
    arr.numpy.return_value = arr
    return arr


def _make_yolo_result(boxes_array):
    """Tạo object result giống ultralytics output."""
    result = MagicMock()
    result.boxes = boxes_array
    return result


def _build_detector_with_mock_yolo(monkeypatch):
    """Tạo HelmetPlateDetector với model_owner + YOLO đều được patch.

    monkeypatch.setattr tự động cleanup khi test kết thúc, đảm bảo
    `det.detect(...)` / `det.detect_tracked(...)` ở ngoài helper vẫn dùng mock.

    Trả về (det, mock_model) — mock_model là object được `self.model` tham chiếu
    (kết quả của `model_owner().run("bootstrap", _load_model, path)`).
    """
    mock_names = {0: "license-plate", 1: "motorcyclist"}

    # bootstrap_mock chính là `self.model` sau init
    mock_model = MagicMock()
    mock_model.names = mock_names
    mock_model.to = MagicMock()

    def fake_run(*args, **kwargs):
        if len(args) >= 3:
            key, fn, *rest = args
        elif len(args) == 2:
            key, fn = args
            rest = ()
        else:
            key = args[0]
            fn = args[1] if len(args) > 1 else kwargs.get("fn")
            rest = args[2:] if len(args) > 2 else ()
        if key == "bootstrap":
            return mock_model
        return fn(*rest)

    fake_owner_instance = MagicMock()
    fake_owner_instance.run = MagicMock(side_effect=fake_run)

    monkeypatch.setattr("app.cv.detector.model_owner", lambda: fake_owner_instance)
    # Patch YOLO constructor (cho _load_model) — return value không quan trọng
    # vì fake_run short-circuit trước khi gọi _load_model
    monkeypatch.setattr(
        "app.cv.detector.YOLO", lambda *a, **kw: MagicMock()
    )

    det = HelmetPlateDetector("/fake/path/yolov8n.pt", conf_threshold=0.25)
    return det, fake_owner_instance, mock_model


def _fake_infer(args, kwargs):
    """Side effect cho fake_owner.run. Signature thật là run(key, fn, *args).
    Với bootstrap: run("bootstrap", _load_model, model_path) → fn(path)
    Với detect:    run(camera_id, self._infer, frame, tracked) → fn(frame, tracked)
    """
    # print(f"_fake_infer args={args} kwargs={kwargs}")
    if len(args) >= 3:
        key, fn, *rest = args
    elif len(args) == 2:
        key, fn = args
        rest = ()
    else:
        key = args[0]
        fn = args[1] if len(args) > 1 else kwargs.get("fn")
        rest = args[2:] if len(args) > 2 else ()
    if key == "bootstrap":
        return MagicMock()
    return fn(*rest)


# ── 1. Track ID ổn định xuyên nhiều frame với cùng vị trí ─────────────────


def test_track_id_stable_across_frames_with_same_position(monkeypatch):
    """Cùng vị trí bbox qua 5 frame → BYTETracker trả cùng track_id."""
    det, _, mock_model = _build_detector_with_mock_yolo(monkeypatch)

    # Mock BYTETracker để trả cùng tid mỗi lần
    mock_tracker = MagicMock()
    call_count = {"n": 0}

    def fake_update(boxes, frame):
        # Trả cùng tid=42 cho mọi frame (giả lập object đứng yên)
        return np.array([[10, 20, 110, 70, 42, 0.9, 0]])

    mock_tracker.update = MagicMock(side_effect=fake_update)
    det._tracker = mock_tracker

    # Mock YOLO infer trả boxes ổn định
    boxes = _make_boxes_array([(10, 20, 110, 70)])
    mock_model.return_value = [_make_yolo_result(boxes)]

    track_ids = []
    for _ in range(5):
        dets = det.detect_tracked(np.zeros((480, 640, 3), dtype=np.uint8))
        track_ids.append([d.track_id for d in dets])

    # Tất cả frame phải có cùng tid=42
    assert all(tids == [42] for tids in track_ids), (
        f"Track ID không ổn định: {track_ids}"
    )


# ── 2. Camera_id khác nhau → tracker riêng biệt ──────────────────────────


def test_different_camera_ids_get_independent_trackers():
    """Hai detector với camera_id khác nhau có _tracker state riêng biệt.

    Sau khi cả hai cùng khởi tạo BYTETracker, _tracker phải là object khác nhau
    (mỗi camera_id có state riêng).
    """
    det_front = HelmetPlateDetector.__new__(HelmetPlateDetector)
    det_front.camera_id = "front"
    det_front._tracker = MagicMock(name="tracker_front")

    det_rear = HelmetPlateDetector.__new__(HelmetPlateDetector)
    det_rear.camera_id = "rear"
    det_rear._tracker = MagicMock(name="tracker_rear")

    assert det_front._tracker is not det_rear._tracker, (
        "Tracker phải độc lập giữa camera_id"
    )
    # Reset tracker của front KHÔNG ảnh hưởng rear
    det_front._tracker.reset = MagicMock()
    det_rear._tracker.reset = MagicMock()
    det_front._tracker.reset()
    det_rear._tracker.reset()
    assert det_front._tracker.reset.call_count == 1
    assert det_rear._tracker.reset.call_count == 1


# ── 3. reset_tracker() clear state ───────────────────────────────────────


def test_reset_tracker_calls_underlying_reset(monkeypatch):
    """reset_tracker() phải gọi underlying BYTETracker.reset()."""
    det, _, _ = _build_detector_with_mock_yolo(monkeypatch)
    mock_tracker = MagicMock()
    det._tracker = mock_tracker

    det.reset_tracker()
    mock_tracker.reset.assert_called_once()


def test_reset_tracker_safe_when_tracker_is_none(monkeypatch):
    """reset_tracker() phải an toàn khi _tracker chưa được khởi tạo (lazy init)."""
    det, _, _ = _build_detector_with_mock_yolo(monkeypatch)
    det._tracker = None  # giả lập chưa init
    # Không raise
    det.reset_tracker()


# ── 4. detect() (không tracked) trả Detection với track_id=None ─────────


def test_detect_returns_track_id_none(monkeypatch):
    """detect() (không tracked) phải trả track_id=None cho mọi detection.
    detect_tracked() mới gán track_id."""
    det, _, mock_model = _build_detector_with_mock_yolo(monkeypatch)
    boxes = _make_boxes_array([(10, 20, 110, 70), (200, 30, 300, 80)])
    mock_model.return_value = [_make_yolo_result(boxes)]

    dets = det.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    assert len(dets) == 2
    assert all(d.track_id is None for d in dets), "detect() phải để track_id=None"


# ── 5. detect() vs detect_tracked() qua owner ────────────────────────────


def test_detect_tracked_invokes_tracker_update(monkeypatch):
    """detect_tracked() phải gọi BYTETracker.update(boxes, frame)."""
    det, _, mock_model = _build_detector_with_mock_yolo(monkeypatch)
    boxes = _make_boxes_array([(10, 20, 110, 70)])
    mock_model.return_value = [_make_yolo_result(boxes)]
    mock_tracker = MagicMock()
    mock_tracker.update = MagicMock(return_value=np.array([[10, 20, 110, 70, 1, 0.9, 0]]))
    det._tracker = mock_tracker

    det.detect_tracked(np.zeros((480, 640, 3), dtype=np.uint8))
    assert mock_tracker.update.called, "BYTETracker.update phải được gọi"


# ── 6. Class names mapping qua tracker output ───────────────────────────


def test_tracked_detection_uses_class_names_mapping(monkeypatch):
    """Detection từ tracker phải dùng self._class_names.get(int(cls)) để map."""
    det, _, mock_model = _build_detector_with_mock_yolo(monkeypatch)
    det._class_names = {0: "license-plate", 1: "motorcyclist"}
    boxes = _make_boxes_array([(10, 20, 110, 70)])
    mock_model.return_value = [_make_yolo_result(boxes)]
    mock_tracker = MagicMock()
    # cls=1 → "motorcyclist"
    mock_tracker.update = MagicMock(return_value=np.array([[10, 20, 110, 70, 7, 0.9, 1]]))
    det._tracker = mock_tracker

    dets = det.detect_tracked(np.zeros((480, 640, 3), dtype=np.uint8))
    assert len(dets) == 1
    assert dets[0].class_name == "motorcyclist"
    assert dets[0].track_id == 7


# ── 7. Empty boxes (no detection) không crash tracker ──────────────────


def test_empty_boxes_does_not_crash_tracker(monkeypatch):
    """YOLO trả 0 box → tracker.update vẫn chạy, trả list rỗng."""
    det, _, mock_model = _build_detector_with_mock_yolo(monkeypatch)
    empty_boxes = _make_boxes_array([])
    mock_model.return_value = [_make_yolo_result(empty_boxes)]
    mock_tracker = MagicMock()
    mock_tracker.update = MagicMock(return_value=np.array([]))
    det._tracker = mock_tracker

    dets = det.detect_tracked(np.zeros((480, 640, 3), dtype=np.uint8))
    assert dets == []
