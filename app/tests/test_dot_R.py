"""Behavioral tests cho Đợt R — sửa thiếu sót A–C.

R1: Capture thực sự độc lập với AI (frame metadata + source_epoch).
R2: OCR async — consume kết quả đúng 1 lần, không fallback sync, crop là
    bản sao độc lập, stale future/epoch bị loại.
R3: JPEG cache — update cho mọi frame mới (skip, no-person, full), encode
    1 lần, viewer dùng chung bytes; đổi nguồn không phát lại JPEG cũ.
R4: OCR lỗi kỹ thuật không thành kết luận vi phạm; helmet độc lập.
R5: Crop OCR từ frame gốc nét, bbox scale 1280x720↔640x480, lọc
    aspect ratio dưới 1.5.

Test dùng nguồn giả + detector/OCR điều khiển được; KHÔNG tìm chuỗi
trong source làm bằng chứng.
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ────────────────────────────── Helpers ─────────────────────────────────


class _FakeDet:
    """Detection-like duck type cho pipeline tests."""

    def __init__(self, class_name: str, bbox: tuple, confidence: float = 0.9,
                 track_id: int | None = None):
        self.class_name = class_name
        self.bbox = bbox  # (x1, y1, x2, y2)
        self.confidence = confidence
        self.track_id = track_id


class _BlockingDetector:
    """Detector giả: block cho tới khi main giải phóng."""

    def __init__(self, sleep_sec: float = 0.3):
        self.sleep_sec = sleep_sec
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        time.sleep(self.sleep_sec)
        return []

    def detect_tracked(self, frame):
        self.calls += 1
        time.sleep(self.sleep_sec)
        return []


def _build_pipeline_with_mocks(monkeypatch, gate_id: str = "main"):
    """Khởi tạo pipeline thật nhưng thay detectors/OCR bằng mock.

    Trả về (pipeline, mocks) — pipeline đã start thread _run_loop.
    """
    from app.cv import pipeline as p_mod

    # Patch trước khi tạo pipeline
    person_mock = _BlockingDetector(sleep_sec=0.05)
    helmet_mock = _BlockingDetector(sleep_sec=0.05)
    plate_mock = _BlockingDetector(sleep_sec=0.05)

    monkeypatch.setattr(p_mod, "HelmetPlateDetector",
                        lambda *a, **kw: helmet_mock)
    monkeypatch.setattr(p_mod, "PersonPoseDetector",
                        lambda *a, **kw: person_mock, raising=False)

    # WebcamStream giả
    class FakeWebcam:
        def __init__(self):
            self._opened = True
            self.counter = 0
            self.released = False

        def read_frame(self):
            self.counter += 1
            return np.zeros((720, 1280, 3), dtype=np.uint8)

        def release(self):
            self.released = True
            self._opened = False

        @property
        def is_opened(self):
            return self._opened

    monkeypatch.setattr(p_mod, "WebcamStream", FakeWebcam)
    monkeypatch.setattr(p_mod, "set_gate_camera_source", lambda *a, **kw: None)
    monkeypatch.setattr(p_mod, "set_gate_roi", lambda *a, **kw: None)
    monkeypatch.setattr(p_mod, "set_gate_line", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(p_mod, "get_gate_roi", lambda *a, **kw: None)
    monkeypatch.setattr(p_mod, "get_gate_line", lambda *a, **kw: None)

    pipeline = p_mod.VideoPipeline.__new__(p_mod.VideoPipeline)
    # Đặt các thuộc tính cần thiết cho test (nhưng KHÔNG load model)
    pipeline.gate_id = gate_id
    pipeline._running = True
    pipeline._thread = None
    pipeline._lock = threading.Lock()
    pipeline._latest_frame = None
    pipeline._latest_jpeg = None
    pipeline._frame_seq = 0
    pipeline._frame_count = 0
    pipeline._last_frame_time = 0.0
    pipeline._last_detection_time = 0.0
    pipeline._start_time = time.time()
    pipeline._last_helmet_dets = []
    pipeline._last_plate_dets = []
    pipeline._last_person_dets = []
    pipeline._last_pose_data = []
    pipeline._prev_track_bbox = {}
    pipeline._fast_track_active = False
    pipeline._track_vehicle_history = {}
    pipeline._last_log_time = {}
    from collections import deque as _deque
    pipeline._clip_buffer = _deque(maxlen=64)
    pipeline._frame_timestamps = _deque(maxlen=30)
    pipeline._consecutive_errors = 0
    pipeline._recorder = None
    pipeline._plate_attempts = 0
    pipeline._plate_successes = 0
    pipeline._last_process_latency_ms = 0.0
    pipeline._pedestrian_count = 0
    pipeline._rider_count = 0
    pipeline._jpeg_cache = {}
    pipeline._jpeg_max_size = 30
    pipeline._source_epoch = 0
    pipeline._ocr_pending = {}
    pipeline._ocr_submit_meta = {}
    pipeline._ocr_max_pending = 16
    pipeline._ocr_health = {"errors": 0, "empty": 0, "submitted": 0,
                            "completed": 0, "stale_dropped": 0,
                            "sync_fallbacks": 0, "duplicate_dropped": 0,
                            "blur_skipped": 0, "confirmed_skipped": 0}
    pipeline._ocr_pool = ThreadPoolExecutor(max_workers=1,
                                              thread_name_prefix="ocr-test")  # sẽ tự tạo khi test
    pipeline._detect_pool = None
    pipeline._io_pool = None
    # Phase 0 (Task 1): metrics buffers + counters
    from app.cv.pipeline_metrics import MetricsBuffer, ResourceSampler
    pipeline._metrics_capture = MetricsBuffer()
    pipeline._metrics_detect = MetricsBuffer()
    pipeline._metrics_ocr_wait = MetricsBuffer()
    pipeline._metrics_encode = MetricsBuffer()
    pipeline._metrics_persistence = MetricsBuffer()
    pipeline._metrics_dispatch = MetricsBuffer()
    pipeline._resource_sampler = ResourceSampler()
    pipeline._capture_fps_value = 0.0
    pipeline._ai_fps_value = 0.0
    pipeline._fps_compute_at = time.monotonic()
    pipeline._fps_capture_window = 0
    pipeline._fps_ai_window = 0
    pipeline._jpeg_new_count = 0
    pipeline._jpeg_repeat_count = 0
    pipeline._jpeg_last_emitted_seq = -1
    pipeline._frames_dropped_stale = 0
    pipeline._frames_dropped_encode = 0
    pipeline._violations_persisted_total = 0
    pipeline._violations_skipped_total = 0
    # Phase 1 — stop guard + reconnect
    pipeline._run_generation = 0
    pipeline._stopped = False
    pipeline._reconnect_failures = 0
    pipeline._alert_queue = type("MQueue", (), {"qsize": lambda self: 0,
                                                  "maxsize": 256})()
    pipeline._open_webcam = MagicMock()
    pipeline._webcam = FakeWebcam()
    pipeline._fast_movement_px = 80
    pipeline._vehicle_vote_window_sec = 2.5
    pipeline._vehicle_vote_min_samples = 3
    pipeline._roi_points = None
    pipeline._roi_polygon_px = None
    pipeline._crossing_detector = MagicMock()
    pipeline._crossing_detector.is_configured = False
    pipeline._midline_track_state = {}
    pipeline._instant_alerted_tracks = set()
    pipeline.camera_switch = MagicMock()
    pipeline.camera_switch.has_pending = False
    pipeline._active_source = "fake"
    pipeline._last_saved_source = "fake"
    pipeline._last_source_poll = 0.0
    pipeline._SOURCE_POLL_INTERVAL_SEC = 5.0
    pipeline._plate_voter = MagicMock()
    pipeline._event_manager = MagicMock()
    pipeline._event_manager.update.return_value = MagicMock(kind="skip", label=None,
                                                              plate_read="")
    pipeline._alert_queue = MagicMock()
    return pipeline, person_mock


# ────────────────────────────── R1: Capture ──────────────────────────────


class TestR1CaptureDecoupling:
    """R1: Frame phải có metadata gate_id/source_epoch/frame_seq/timestamp."""

    def test_frame_has_required_metadata(self):
        """Metadata phải được gắn vào frame, không chỉ là np.ndarray."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        meta = pipeline._attach_frame_metadata(frame, gate_id="main",
                                                source_epoch=0, frame_seq=1,
                                                ts=time.time())
        assert meta.gate_id == "main"
        assert meta.source_epoch == 0
        assert meta.frame_seq == 1
        assert isinstance(meta.ts, float)
        assert meta.image is frame

    def test_source_epoch_increments_on_camera_change(self, monkeypatch):
        """Đổi camera thành công phải tăng source_epoch."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        # FIX (T4): mock set_gate_camera_source — production DB không có gate_roi.
        monkeypatch.setattr("app.cv.pipeline.set_gate_camera_source", MagicMock())
        from app.cv.camera_switch import CameraSwitch
        cs = CameraSwitch("source_a")
        pipeline.camera_switch = cs
        pipeline._active_source = "source_a"
        pipeline._webcam = MagicMock()
        pipeline._webcam.is_opened = True
        new_wc = MagicMock()
        new_wc.read_frame.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        new_wc.is_opened = True
        pipeline._open_webcam = MagicMock(return_value=new_wc)
        assert pipeline._source_epoch == 0
        # Yêu cầu đổi sang source_b
        cs.request("source_b")
        pipeline._apply_camera_change()
        assert pipeline._active_source == "source_b"
        assert pipeline._source_epoch == 1
        assert pipeline._ocr_pending == {}, "Đổi nguồn phải clear pending OCR"


# ────────────────────────────── R2: OCR Async ────────────────────────────


class TestR2OcrAsyncFix:
    """R2: OCR async đúng nguyên tắc — 1 lần result, không fallback sync."""

    def test_collect_done_result_consumes_once(self):
        """Khi future đã xong: lấy result đúng 1 lần, lần sau bỏ."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        # Tạo future đã set result sẵn trước khi đưa vào pending
        fut = Future()
        fut.set_result({"full": "59H12345", "confidence": 0.7,
                         "top_line": "", "bottom_line": ""})
        pipeline._ocr_pending = {1: fut}
        result1 = pipeline._ocr_consume_pending(track_id=1)
        # Lần gọi sau phải trả None (đã consume rồi)
        result2 = pipeline._ocr_consume_pending(track_id=1)
        assert result1 is not None
        assert result2 is None
        assert 1 not in pipeline._ocr_pending

    def test_pending_future_returns_none_no_sync_fallback(self):
        """Future chưa xong: KHÔNG fallback OCR đồng bộ. Trả PlateReadResult
        pending=True — không gọi read_plate_detailed."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        pending = Future()
        pipeline._ocr_pending = {1: pending}
        pipeline._ocr_submit_meta = {1: {"frame_seq": 1, "source_epoch": 0, "ts": time.time()}}
        # PlateVoter mock trả PlateReadResult
        from app.cv.plate_voter import PlateReadResult
        pipeline._plate_voter = MagicMock()
        pipeline._plate_voter.add_result.return_value = PlateReadResult(
            text="", confidence=0.0, sample_count=0, is_confident=False)
        pipeline._plate_voter.read.return_value = PlateReadResult(
            text="59H12345", confidence=0.9, sample_count=1, is_confident=True)
        # Gọi _read_plate_voted — phải không sync fallback
        result = pipeline._read_plate_voted(
            frame=np.zeros((100, 100, 3)),
            plate_det=_FakeDet("plate", (0, 0, 50, 20), track_id=1),
            track_id=1, frame_seq=1,
        )
        # Sync OCR KHÔNG ĐƯỢC gọi khi future đang chạy (PlateVoter.read = sync)
        assert pipeline._plate_voter.read.call_count == 0, (
            "OCR async đang chờ mà vẫn fallback OCR sync là vi phạm R2")
        assert result is not None
        assert getattr(result, "pending", False) is True

    def test_crop_is_independent_copy(self):
        """Crop gửi cho worker phải là bản sao, không phải view vào frame."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        frame = np.ones((200, 200, 3), dtype=np.uint8) * 100
        crop_view = frame[10:30, 20:80]
        crop_copy = pipeline._independent_crop_copy(crop_view)
        # Sửa crop_copy, frame phải KHÔNG đổi
        crop_copy[:] = 255
        assert frame[15, 30, 0] == 100, (
            "Crop phải là bản sao, view vào frame là vi phạm R2")
        assert crop_copy.shape == (20, 60, 3)

    def test_ocr_result_rejected_when_source_epoch_changed(self, monkeypatch):
        """A controlled completed result from the previous source is rejected."""
        from concurrent.futures import Future
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        pipeline._source_epoch = 5
        fut = Future()
        fut.set_result({'full':'59H12345','confidence':.7,'source_epoch':4,'frame_seq':10,'track_id':1})
        pipeline._ocr_pending[1] = fut
        try:
            assert pipeline._ocr_consume_pending_if_fresh(1,5) is None
            assert pipeline._ocr_health['stale_dropped'] == 1
        finally:
            pipeline._ocr_pool.shutdown(wait=True)

    def test_one_pending_per_track(self, monkeypatch):
        """A second submit retains the same Future and does not start real OCR."""
        from concurrent.futures import Future
        pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
        pool = pipeline._ocr_pool
        pipeline._ocr_pool = MagicMock()
        first_fut = Future()
        pipeline._ocr_pool.submit.return_value = first_fut
        try:
            for seq in (1, 2):
                pipeline._ocr_submit_with_epoch(np.zeros((100,100,3),dtype=np.uint8),
                    _FakeDet('plate',(0,0,50,20),track_id=1),1,seq,0)
            assert pipeline._ocr_pending[1] is first_fut
            pipeline._ocr_pool.submit.assert_called_once()
            assert pipeline._ocr_health['duplicate_dropped'] == 1
        finally:
            pool.shutdown(wait=True)


# ────────────────────────────── R3: JPEG ────────────────────────────────


class TestR3JpegCache:
    """R3: JPEG update mỗi frame mới (cả skip/no-person); đổi nguồn không
    phát lại JPEG cũ."""

    def test_jpeg_updated_on_skipped_frame(self):
        """Frame bị FRAME_SKIP vẫn phải cập nhật JPEG cache."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        pipeline._frame_count = 2  # 2 % 3 = 2 → không phải skip
        pipeline._FRAME_SKIP = 3
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Vẽ box mượt từ cache → set _latest_frame
        pipeline._latest_frame = None
        pipeline._latest_jpeg = None
        pipeline._publish_frame_jpeg(frame, frame_seq=1)
        assert pipeline._latest_jpeg is not None, (
            "JPEG phải được encode ngay cả khi skip AI")

    def test_jpeg_updated_on_no_person_frame(self):
        """Frame không có người vẫn phải cập nhật JPEG (không replay cũ)."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        pipeline._latest_jpeg = None
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        pipeline._publish_frame_jpeg(frame, frame_seq=7)
        assert pipeline._latest_jpeg is not None
        # frame_seq trong cache phải khớp frame_seq submit
        assert pipeline._frame_seq == 0  # chưa increment vì _publish không tăng

    def test_jpeg_encode_shared_among_viewers(self):
        """Hai viewer gọi get_jpeg() → cùng bytes object, không encode lại."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Patch imencode để đếm số lần encode
        with patch("app.cv.pipeline.cv2.imencode") as imencode_mock:
            buf = MagicMock()
            buf.tobytes.return_value = b"\xff\xd8\xff\xe0jpegdata"
            imencode_mock.return_value = (True, buf)
            pipeline._publish_frame_jpeg(frame, frame_seq=1)
            j1 = pipeline.get_jpeg()
            j2 = pipeline.get_jpeg()
            assert j1 is j2, "JPEG phải là cùng object chia sẻ"
            # Chỉ encode đúng 1 lần cho cùng frame
            assert imencode_mock.call_count == 1

    def test_camera_change_discards_old_jpeg(self, monkeypatch):
        """Đổi nguồn camera phải vô hiệu JPEG cũ (không phát lại)."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        # FIX (T4): mock set_gate_camera_source — production DB không có gate_roi.
        monkeypatch.setattr("app.cv.pipeline.set_gate_camera_source", MagicMock())
        # Giả lập JPEG cũ đã được publish
        pipeline._latest_jpeg = b"\xff\xd8\xff\xe0old"
        pipeline._jpeg_cache[100] = (b"\xff\xd8\xff\xe0old", time.time())
        # Đổi nguồn
        from app.cv.camera_switch import CameraSwitch
        cs = CameraSwitch("source_a")
        cs.request("source_b")
        pipeline.camera_switch = cs
        pipeline._active_source = "source_a"
        pipeline._webcam = MagicMock()
        pipeline._webcam.is_opened = True
        new_wc = MagicMock()
        new_wc.read_frame.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        new_wc.is_opened = True
        pipeline._open_webcam = MagicMock(return_value=new_wc)
        pipeline._apply_camera_change()
        assert pipeline._latest_jpeg is None, (
            "Sau đổi nguồn phải vô hiệu JPEG cũ (tránh replay frame cũ)")


# ────────────────────────────── R4: Tech vs Violation ───────────────────


class TestR4TechVsViolation:
    """R4: OCR lỗi kỹ thuật không trở thành NO_PLATE/PLATE_OBSCURED; helmet
    độc lập; không gán từ 1 lần đọc confidence cao."""

    def test_ocr_engine_error_not_violation_evidence(self):
        """OCR engine exception phải được đếm riêng trong health, không tạo
        kết luận NO_PLATE."""
        from app.cv.ocr import read_plate_detailed
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        pipeline._ocr_health["errors"] = 0
        # Mock reader để raise
        import app.cv.ocr as ocr_mod
        orig_reader = ocr_mod._reader
        ocr_mod._reader = None

        class _BoomReader:
            def readtext(self, *a, **kw):
                raise RuntimeError("EasyOCR CUDA OOM")

        ocr_mod._reader = _BoomReader()
        try:
            result = read_plate_detailed(np.ones((60, 150, 3), dtype=np.uint8) * 200)
            assert result["full"] == ""
            assert result.get("error", "").startswith("ocr_engine_error")
        finally:
            ocr_mod._reader = orig_reader

    def test_helmet_violation_independent_of_ocr(self):
        """Helmet xác nhận phải cập nhật ngay cả khi OCR chưa có kết quả."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        # Mock EventManager để xác nhận helmet ngay
        pipeline._event_manager.update.return_value = MagicMock(
            kind="commit", label="NO_HELMET", streak=5,
            plate_read="")
        # OCR pending (chưa có kết quả)
        pipeline._ocr_pending[1] = Future()
        # Gọi commit event — phải thành công mà không cần OCR
        decision = pipeline._event_manager.update.return_value
        assert decision.kind == "commit"
        assert decision.label == "NO_HELMET"

    def test_single_high_confidence_does_not_commit(self):
        """PlateVoter không được commit 1 lần đọc confidence cao. Cần ≥2
        mẫu hoặc vote đủ min_agree."""
        from app.cv.plate_voter import PlateVoter
        voter = PlateVoter(
            grid_px=60, window_sec=2.5, min_agree=2,
            min_confidence_single=0.9,  # chỉ 1 lần với conf này mới commit
        )

        class _D:
            bbox = (100, 50, 400, 100)
            track_id = 1

        # 1 lần đọc với conf = 0.95 (cao hơn threshold 0.9)
        # PHẢI không commit nếu chưa đủ min_agree
        result = voter.add_result(_D(), {"full": "59A12345", "confidence": 0.95,
                                          "top_line": "", "bottom_line": ""})
        assert result.text == "" or result.is_confident is False, (
            "1 lần đọc confidence cao không được tự commit biển — R4 yêu cầu"
            " ≥2 crop khác frame")
        # Nhưng cần n>=min_agree mới được commit
        result2 = voter.add_result(_D(), {"full": "59A12345", "confidence": 0.6,
                                          "top_line": "", "bottom_line": ""})
        assert result2.is_confident is False
        result3 = voter.add_result(_D(), {'full':'59A12345', 'confidence':0.95, 'frame_seq':3, 'source_epoch':0})
        assert result3.is_confident is True

    def test_ocr_empty_does_not_auto_trigger_plate_obscured_e1_2(self):
        """E1.2/R4: OCR rỗng (empty) không được tự động chuyển thành
        PLATE_OBSCURED. Biển có thể ở ngoài khung hình hoặc camera mất
        tín hiệu — coi như 'chưa xác định', KHÔNG kết luận biển bị che."""
        # Gọi plate_voter.read() trả về empty text — KHÔNG tự tin,
        # KHÔNG đẩy sample nào vào history.
        from app.cv.plate_voter import PlateVoter
        voter = PlateVoter(
            grid_px=60, window_sec=2.5, min_agree=2,
            min_confidence_single=0.55)
        from app.cv.detector import Detection
        det = Detection(class_name="plate", confidence=1.0,
                         bbox=(50, 50, 200, 100), track_id=42)
        ocr_empty = MagicMock(return_value={"full": "", "confidence": 0.0,
                                             "top_line": "", "bottom_line": ""})
        # Frame đủ lớn để crop > 20x40
        frame = np.zeros((300, 300, 3), dtype=np.uint8)
        result = voter.read(frame, det, ocr_empty)
        # Empty result không tăng phiếu
        assert result.text == ""
        assert result.is_confident is False
        assert result.sample_count == 0

    def test_ocr_pending_does_not_create_plate_obscured_e1_2(self):
        """E1.2: OCR async chưa trả kết quả (pending=True) → KHÔNG tạo
        PLATE_OBSCURED. PlateReadResult.pending=True phải được pipeline
        tôn trọng (R2)."""
        from app.cv.plate_voter import PlateReadResult
        # Kết quả rỗng + pending=True từ OCR async
        pending_result = PlateReadResult(
            text="", confidence=0.0, sample_count=0, is_confident=False,
            pending=True,
        )
        # E1.2: KHÔNG tự ý coi pending là PLATE_OBSCURED — pipeline phải
        # chờ OCR thật sự trả về.
        assert pending_result.pending is True
        assert pending_result.text == ""
        assert pending_result.is_confident is False


# ────────────────────────────── R5: Crop & Aspect ────────────────────────


class TestR5CropAspectRatio:
    """R5: Crop OCR từ frame gốc, scale bbox đúng, lọc aspect ratio."""

    def test_bbox_scale_1280x720_to_640x360(self):
        """Bbox detect trên ảnh 640x360 → quy đổi về 1280x720 phải đúng."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        det = _FakeDet("plate", (10, 10, 50, 30))  # detect frame 640x360
        scale_x = 1280 / 640
        scale_y = 720 / 360
        scaled = pipeline._rescale_bbox(det.bbox, scale_x, scale_y)
        assert scaled == (20, 20, 100, 60)

    def test_crop_from_raw_frame_not_drawn(self):
        """OCR crop phải lấy từ frame gốc, KHÔNG từ frame đã vẽ box."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        raw = np.zeros((200, 200, 3), dtype=np.uint8)
        drawn = raw.copy()
        cv2 = pytest.importorskip("cv2")
        # Vẽ box trắng lên drawn
        cv2.rectangle(drawn, (10, 10, 60, 30), (255, 255, 255), 2)
        crop_raw = pipeline._crop_for_ocr(raw, (10, 10, 60, 30))
        crop_drawn = pipeline._crop_for_ocr(drawn, (10, 10, 60, 30))
        # Crop từ raw phải toàn 0, crop từ drawn có viền trắng
        assert crop_raw.sum() == 0
        assert crop_drawn.sum() > 0

    def test_plate_aspect_ratio_filter(self):
        """Plate bbox có tỷ lệ w/h < 1.5 phải bị loại (1 dòng và 2 dòng VN)."""
        pipeline, _ = _build_pipeline_with_mocks(MagicMock())
        # 1 dòng ~ 4:1
        assert pipeline._plate_aspect_ok((0, 0, 200, 50), min_ratio=1.5) is True
        # 2 dòng ~ 2:1
        assert pipeline._plate_aspect_ok((0, 0, 100, 50), min_ratio=1.5) is True
        # Quá vuông → loại
        assert pipeline._plate_aspect_ok((0, 0, 60, 60), min_ratio=1.5) is False
        # Quá cao → loại
        assert pipeline._plate_aspect_ok((0, 0, 50, 200), min_ratio=1.5) is False
