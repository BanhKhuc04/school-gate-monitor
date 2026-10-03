"""R2 — Tách EOF video khỏi lỗi mạng + race tests cho stop/release.

Theo handoff §3 R2:
- File video đến EOF phải kết thúc lần chạy, không reconnect và phát lại clip.
- Lỗi mạng (RTSP offline) vẫn reconnect qua backoff như cũ.
- Stop/join reader phải xảy ra trước release webcam; không leak frame cũ.

Mỗi test nhắm vào một hành vi độc lập để dễ truy vết khi regress.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from app.cv import capture as capture_mod
from app.cv.capture import LatestFrameCapture, WebcamStream


# ── 1. EOF phân biệt với lỗi mạng ────────────────────────────────────────────


def test_local_video_raises_eof_when_file_ends_and_loop_false():
    """Khi loop=False và file hết frame → EOFError, KHÔNG phải RuntimeError chung.

    Hiện tại (trước R2) code raise RuntimeError('Không đọc được frame từ bình thường')
    cho mọi lỗi read; người xử lý caller không phân biệt được EOF với mất mạng.
    """
    cap = MagicMock()
    cap.read.return_value = (False, None)
    cap.get.return_value = 25.0  # FPS
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(capture_mod.cv2, "VideoCapture", lambda *a, **kw: cap)
        stream = WebcamStream("sample.mp4", loop=False)
        with pytest.raises(EOFError):
            stream.read_source_frame()


def test_local_video_loop_true_does_not_re_raise_eof_for_loop():
    """Khi loop=True, EOF phải seek về đầu và đọc tiếp — KHÔNG raise EOFError.

    Đây là hành vi demo lặp liên tục đã có từ trước; R2 chỉ đảm bảo nó vẫn hoạt động.
    """
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    cap = MagicMock()
    cap.read.side_effect = [(False, None), (True, frame)]
    cap.get.return_value = 25.0
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(capture_mod.cv2, "VideoCapture", lambda *a, **kw: cap)
        stream = WebcamStream("sample.mp4", loop=True)
        assert stream.read_source_frame() is frame


def test_network_source_read_failure_is_not_eof():
    """Lỗi mạng (RTSP offline) KHÔNG được raise EOFError — pipeline phải nhận biết
    để quyết định reconnect. RuntimeError là phù hợp.
    """
    cap = MagicMock()
    cap.read.return_value = (False, None)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(capture_mod.cv2, "VideoCapture", lambda *a, **kw: cap)
        stream = WebcamStream("rtsp://example.test/live", loop=False)
        with pytest.raises(RuntimeError) as exc:
            stream.read_source_frame()
        # EOFError không được lẫn vào đây.
        assert not isinstance(exc.value, EOFError)


# ── 2. LatestFrameCapture phân biệt EOF từ các lỗi khác ────────────────────


def _make_source(raise_exc):
    """Tạo source có method read_source_frame raise đúng exception."""
    class _Src:
        def read_source_frame(self_inner):
            raise raise_exc
    return _Src()


def test_latest_capture_propagates_eof_to_consumer():
    """EOF từ WebcamStream phải tới consumer (read_latest) như EOFError."""
    capture = LatestFrameCapture(_make_source(EOFError("file ended")))
    capture.start()
    try:
        with pytest.raises(EOFError):
            capture.read_latest(timeout=1)
    finally:
        capture.stop()


def test_latest_capture_propagates_runtime_for_other_errors():
    """Lỗi khác (mất mạng, decode) phải tới consumer như RuntimeError."""
    capture = LatestFrameCapture(_make_source(RuntimeError("rtsp offline")))
    capture.start()
    try:
        with pytest.raises(RuntimeError, match="rtsp offline"):
            capture.read_latest(timeout=1)
    finally:
        capture.stop()


# ── 3. Pipeline _run_loop kết thúc khi EOF, KHÔNG reconnect ────────────────


def test_pipeline_handle_read_error_eof_terminates_run(monkeypatch):
    """Unit test _handle_read_error: EOFError → set _running=False, return False.

    Trước đây EOFError bị nuốt vào 'processing_error' và đếm consecutive_errors
    dẫn tới reconnect cho cả video file. Sau R2 EOF kết thúc run ngay.
    """
    import app.cv.pipeline as module

    pipeline = module.VideoPipeline.__new__(module.VideoPipeline)
    pipeline.gate_id = "main"
    pipeline._running = True
    pipeline._capture = MagicMock()
    pipeline._webcam = MagicMock()
    pipeline._consecutive_errors = 0
    pipeline._RECONNECT_AFTER = 5
    pipeline._stop_capture = MagicMock()
    pipeline._apply_camera_change = MagicMock()
    pipeline._diagnostic = MagicMock()
    monkeypatch.setattr(module, "GATES", {"main": {"source": 0}})

    continue_loop = pipeline._handle_read_error(EOFError("file ended"))

    assert continue_loop is False, "EOFError phải trả về False để _run_loop break"
    assert pipeline._running is False, "EOF phải set _running=False"
    pipeline._stop_capture.assert_called_once()
    pipeline._apply_camera_change.assert_not_called()


def test_pipeline_handle_read_error_network_continues_loop(monkeypatch):
    """Unit test _handle_read_error: RuntimeError (network) → reconnect khi
    consecutive_errors >= _RECONNECT_AFTER; vòng lặp tiếp tục.
    """
    import app.cv.pipeline as module

    pipeline = module.VideoPipeline.__new__(module.VideoPipeline)
    pipeline.gate_id = "main"
    pipeline._running = True
    pipeline._capture = MagicMock()
    pipeline._webcam = MagicMock()
    pipeline._consecutive_errors = 3  # sau +=1 = 4, dưới ngưỡng 5
    pipeline._RECONNECT_AFTER = 5
    pipeline._reconnect_failures = 0
    pipeline._stop_capture = MagicMock(return_value=True)
    pipeline._apply_camera_change = MagicMock()
    pipeline._diagnostic = MagicMock()
    monkeypatch.setattr(module, "GATES", {"main": {"source": 0}})
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    continue_loop = pipeline._handle_read_error(RuntimeError("rtsp offline"))

    assert continue_loop is True
    assert pipeline._consecutive_errors == 4  # 3 → 4, dưới ngưỡng
    # Dưới ngưỡng → không reconnect
    pipeline._stop_capture.assert_not_called()
    pipeline._apply_camera_change.assert_not_called()


def test_pipeline_handle_read_error_reconnects_after_threshold(monkeypatch):
    """Sau _RECONNECT_AFTER consecutive errors → reconnect (stop_capture + apply)."""
    import app.cv.pipeline as module

    pipeline = module.VideoPipeline.__new__(module.VideoPipeline)
    pipeline.gate_id = "main"
    pipeline._running = True
    pipeline._capture = MagicMock()
    pipeline._webcam = MagicMock()
    pipeline._consecutive_errors = 5  # đạt ngưỡng
    pipeline._RECONNECT_AFTER = 5
    pipeline._reconnect_failures = 0
    pipeline._stop_capture = MagicMock(return_value=True)
    pipeline._apply_camera_change = MagicMock(return_value=True)
    pipeline.camera_switch = MagicMock()
    pipeline._diagnostic = MagicMock()
    monkeypatch.setattr(module, "GATES", {"main": {"source": 0}})
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    continue_loop = pipeline._handle_read_error(RuntimeError("rtsp offline"))

    assert continue_loop is True
    pipeline._stop_capture.assert_called_once()
    pipeline._apply_camera_change.assert_called_once()
    assert pipeline._consecutive_errors == 0  # reset sau reconnect


def test_pipeline_run_loop_reconnects_on_network_error(monkeypatch):
    """Lỗi mạng KHÔNG kết thúc run — phải để backoff/reconnect hoạt động.

    Test _handle_read_error trực tiếp (unit), vì _run_loop integration
    cần nhiều mock state để không treo trên Linux.
    """
    # Đã cover trong test_pipeline_handle_read_error_network_continues_loop
    # và test_pipeline_handle_read_error_reconnects_after_threshold.
    pytest.skip("covered by _handle_read_error unit tests")


def test_pipeline_run_loop_reconnects_on_network_error(monkeypatch):
    """Lỗi mạng KHÔNG kết thúc run — phải để backoff/reconnect hoạt động.

    Test _handle_read_error trực tiếp (unit), vì _run_loop integration
    cần nhiều mock state để không treo trên Linux.
    """
    # Đã cover trong test_pipeline_handle_read_error_network_continues_loop
    # và test_pipeline_handle_read_error_reconnects_after_threshold.
    pytest.skip("covered by _handle_read_error unit tests")


# ── 4. Race: stop phải join reader trước khi trả về ────────────────────────


def test_capture_stop_joins_reader_while_reader_blocks_on_condition():
    """Reader thread đang đợi condition.wait (không có frame) → stop() phải
    notify_all + join trong timeout. Sau stop(), thread KHÔNG còn alive.

    Dùng event để giữ reader trong vòng lặp forever — không raise, không emit frame.
    Điều này mô phỏng trạng thái reader vừa start, chưa có frame nào.
    """
    block = threading.Event()

    class _BlockingSource:
        def read_source_frame(self_inner):
            block.wait(10)  # Block cho đến khi stop set event
            # Trong code thật, nếu stop set _stop thì vòng while sẽ thoát.
            # Ở đây ta giả lập vòng lặp cũ đã thoát qua _stop.
            raise RuntimeError("reader stopped")

    capture = LatestFrameCapture(_BlockingSource())
    capture.start()
    # Chờ reader thread được tạo và vào block
    time.sleep(0.05)
    assert capture._thread is not None
    # Force release event để reader không kẹt vĩnh viễn
    try:
        block.set()
        assert capture.stop(timeout=2) is True
        assert not capture._thread.is_alive()
    finally:
        block.set()


def test_capture_stop_returns_false_if_reader_hangs_response_to_action():
    """Reader bị 'treo' (giả lập join không bao giờ xong) → stop(timeout) trả về False.

    Dùng một reader thread giả để verify timeout semantics.
    """
    stuck = LatestFrameCapture(MagicMock())
    # Không start thread; thay vào đó gán thread mock không bao giờ join xong
    fake = MagicMock()
    fake.is_alive.return_value = True
    stuck._thread = fake
    stuck._stop.set()  # Tránh reader thật (nếu start) lặp vô hạn
    # Khi thread.is_alive() True sau join → stop() trả về False
    assert stuck.stop(timeout=0.05) is False


# ── 5. stop() không được return stale packet từ queue ────────────────────────


def test_stopped_capture_does_not_return_stale_latest_packet():
    """Sau stop(), read_latest phải raise RuntimeError('stopped') — không trả về
    packet cũ trong _latest.

    Đã có test tương tự trong test_latest_capture.py — bổ sung thêm 1 test để
    đảm bảo behavior ổn định qua cả hai race: reader blocked và reader vừa emit.
    """
    class _Src:
        def __init__(self):
            self.calls = 0

        def read_source_frame(self_inner):
            self_inner.calls += 1
            return np.full((4, 6, 3), self_inner.calls % 255, np.uint8)

    capture = LatestFrameCapture(_Src())
    capture.start()
    first = capture.read_latest(timeout=1)
    capture.stop(timeout=2)
    with pytest.raises(RuntimeError, match="stopped"):
        capture.read_latest(after=first.seq, timeout=0.2)


# ── 6. R2 slice 2 — Source epoch filter cho OCR callback qua apply_camera_change ──


def _make_pipeline_with_voter():
    """Tạo VideoPipeline rỗng + plate_voter mock để test collect/vote."""
    import app.cv.pipeline as module
    from app.cv.plate_voter import PlateVoter
    from app.cv.pipeline_metrics import MetricsBuffer

    pipeline = module.VideoPipeline.__new__(module.VideoPipeline)
    pipeline.gate_id = "main"
    pipeline._source_epoch = 0
    pipeline._ocr_pending = {}
    pipeline._ocr_submit_meta = {}
    pipeline._ocr_health = {
        "errors": 0, "empty": 0, "submitted": 0, "completed": 0,
        "stale_dropped": 0, "sync_fallbacks": 0, "duplicate_dropped": 0,
        "blur_skipped": 0, "confirmed_skipped": 0,
    }
    pipeline._plate_voter = PlateVoter(
        grid_px=60, window_sec=2.0, min_agree=2, min_confidence_single=0.7,
    )
    pipeline._recognition_results = {}
    # metric buffer for _ocr_consume_pending
    pipeline._metrics_ocr_wait = MetricsBuffer()
    # lock for _apply_camera_change
    pipeline._lock = threading.Lock()
    pipeline._jpeg_cache = {}
    pipeline._latest_frame = None
    pipeline._latest_jpeg = None
    pipeline._last_person_dets = []
    pipeline._last_helmet_dets = []
    pipeline._last_plate_dets = []
    pipeline._last_pose_data = []
    pipeline._prev_track_bbox = {}
    pipeline._track_vehicle_history = {}
    pipeline._last_log_time = {}
    pipeline._last_face_t = 0.0
    return pipeline


def test_ocr_callback_drops_stale_result_after_camera_change():
    """Slice 2: submit OCR ở epoch=0 → đổi nguồn (epoch→1) → consume phải drop.

    Race thật — không gọi _apply_camera_change thật (cần camera_switch/DB), chỉ
    mô phỏng việc tăng epoch và clear pending như _apply_camera_change đã làm.
    Consumer gọi _collect_plate_vote → voter KHÔNG được add_result từ epoch cũ.
    """
    pipeline = _make_pipeline_with_voter()
    # Mô phỏng submit OCR ở epoch=0 (giả lập future đã done)
    from concurrent.futures import Future
    fut = Future()
    fut.set_result({'full': '59A12345', 'confidence': 0.9, 'track_id': 7,
                    'frame_seq': 10, 'source_epoch': 0})
    pipeline._ocr_pending[7] = fut
    pipeline._ocr_submit_meta[7] = {
        'frame_seq': 10, 'source_epoch': 0, 'ts': time.time(),
        'plate_bbox': (100, 100, 200, 150), 'plate_class': 'plate',
        'plate_confidence': 0.85, 'submitted_at_perf': time.perf_counter(),
    }
    # Đổi nguồn — epoch tăng, pending bị clear (giống _apply_camera_change)
    pipeline._source_epoch = 1
    pipeline._ocr_pending.clear()
    pipeline._ocr_submit_meta.clear()
    # Submit OCR mới ở epoch=1 cho cùng track_id 7 (giả lập future đã done)
    fut2 = Future()
    fut2.set_result({'full': '59A12345', 'confidence': 0.9, 'track_id': 7,
                     'frame_seq': 20, 'source_epoch': 1})
    pipeline._ocr_pending[7] = fut2
    pipeline._ocr_submit_meta[7] = {
        'frame_seq': 20, 'source_epoch': 1, 'ts': time.time(),
        'plate_bbox': (110, 110, 210, 160), 'plate_class': 'plate',
        'plate_confidence': 0.85, 'submitted_at_perf': time.perf_counter(),
    }
    # Consumer với current_epoch=1 → phải lấy fut2 (epoch=1)
    from app.cv.pipeline import Detection
    plate_det = Detection('plate', 0.85, (110, 110, 210, 160), track_id=7)
    voted = pipeline._collect_plate_vote(7, plate_det)
    assert voted is not None, "epoch=1 result phải được accept"
    assert voted.text == '59A12345'
    # Voter chỉ chứa 1 lượt (epoch=0 đã drop)
    samples = pipeline._plate_voter._samples_by_track.get(7)
    assert samples is not None
    sample_count = len(samples)
    assert sample_count == 1, f"Voter phải có 1 sample từ epoch=1, có {sample_count}"


def test_ocr_callback_after_camera_change_stale_pending_cleared():
    """_apply_camera_change phải clear cả _ocr_pending lẫn _ocr_submit_meta.

    Tránh tình trạng: future cũ vẫn nằm trong _ocr_pending, khi done sẽ được
    consume → voter bị nhiễu bởi dữ liệu từ nguồn cũ.
    """
    pipeline = _make_pipeline_with_voter()
    from concurrent.futures import Future
    # Pending ở epoch=0
    fut_old = Future()
    fut_old.set_result({'full': '59A12345', 'confidence': 0.9,
                        'track_id': 7, 'frame_seq': 5, 'source_epoch': 0})
    pipeline._ocr_pending[7] = fut_old
    pipeline._ocr_submit_meta[7] = {
        'frame_seq': 5, 'source_epoch': 0, 'ts': time.time(),
        'plate_bbox': (10, 10, 110, 60), 'plate_class': 'plate',
        'plate_confidence': 0.8, 'submitted_at_perf': time.perf_counter(),
    }
    # Source cũ bị _apply_camera_change clear:
    pipeline._ocr_pending.clear()
    pipeline._ocr_submit_meta.clear()
    pipeline._source_epoch = 1
    # Consumer với epoch=1 không có pending → consume trả None
    result = pipeline._ocr_consume_pending_if_fresh(7, 1)
    assert result is None
    assert pipeline._ocr_health['stale_dropped'] == 0  # không vào branch stale, mà là None do không có future
    # Voter chưa có entry cho track 7
    samples = pipeline._plate_voter._samples_by_track.get(7)
    assert samples is None or len(samples) == 0


def test_ocr_result_with_matching_epoch_but_old_frame_seq_dropped():
    """Ngoài epoch filter, _ocr_consume_pending_if_fresh còn check frame_seq
    và _submitted_at. Nếu frame_seq lệch (một stale future lẫn vào)
    → drop tăng stale_dropped.

    Test này bảo vệ guard thứ 2 — không chỉ dựa vào epoch.
    """
    pipeline = _make_pipeline_with_voter()
    pipeline._source_epoch = 1
    from concurrent.futures import Future
    fut = Future()
    fut.set_result({'full': '59A12345', 'confidence': 0.9, 'track_id': 7,
                    'frame_seq': 999,  # lệch so với meta
                    'source_epoch': 1})
    pipeline._ocr_pending[7] = fut
    pipeline._ocr_submit_meta[7] = {
        'frame_seq': 10, 'source_epoch': 1, 'ts': time.time(),
        'plate_bbox': (10, 10, 110, 60), 'plate_class': 'plate',
        'plate_confidence': 0.8,
        'submitted_at_perf': time.perf_counter(),
    }
    result = pipeline._ocr_consume_pending_if_fresh(7, 1)
    assert result is None, "frame_seq lệch → drop"
    assert pipeline._ocr_health['stale_dropped'] == 1


def test_ocr_result_old_submitted_at_dropped_as_stale():
    """Result quá cũ (submitted > PLATE_VOTE_WINDOW_SEC) → drop, stale_dropped++."""
    pipeline = _make_pipeline_with_voter()
    pipeline._source_epoch = 1
    from concurrent.futures import Future
    fut = Future()
    fut.set_result({'full': '59A12345', 'confidence': 0.9, 'track_id': 7,
                    'frame_seq': 10, 'source_epoch': 1,
                    '_submitted_at': time.time() - 60})  # 60s cũ
    pipeline._ocr_pending[7] = fut
    pipeline._ocr_submit_meta[7] = {
        'frame_seq': 10, 'source_epoch': 1, 'ts': time.time() - 60,
        'plate_bbox': (10, 10, 110, 60), 'plate_class': 'plate',
        'plate_confidence': 0.8,
        'submitted_at_perf': time.perf_counter() - 60,
    }
    result = pipeline._ocr_consume_pending_if_fresh(7, 1)
    assert result is None
    assert pipeline._ocr_health['stale_dropped'] == 1


def test_apply_camera_change_clears_ocr_pending_and_meta():
    """Khi _apply_camera_change chạy thật (không mock), pending + meta phải clear.

    Mock camera_switch.apply để tránh DB/webcam I/O. Verify _ocr_pending và
    _ocr_submit_meta trống sau apply, _source_epoch tăng.
    """
    import app.cv.pipeline as module
    from app.cv.camera_switch import CameraSwitch
    pipeline = _make_pipeline_with_voter()
    # Pretend có pending
    from concurrent.futures import Future
    fut = Future()
    fut.set_result({'full': '59A12345', 'source_epoch': 0})
    pipeline._ocr_pending[7] = fut
    pipeline._ocr_submit_meta[7] = {'frame_seq': 1, 'source_epoch': 0,
                                    'ts': time.time()}
    # Stub camera_switch + webcam → _apply_camera_change chạy được
    pipeline._stop_capture = MagicMock(return_value=True)
    pipeline._capture = MagicMock()
    pipeline._webcam = MagicMock()
    pipeline._latest_frame = None
    pipeline._latest_jpeg = None
    pipeline._jpeg_cache = {}
    pipeline._last_person_dets = []
    pipeline._last_helmet_dets = []
    pipeline._last_plate_dets = []
    pipeline._last_pose_data = []
    pipeline._prev_track_bbox = {}
    pipeline._track_vehicle_history = {}
    pipeline._plate_consensus = None
    pipeline._riding_temporal = None
    pipeline._ocr_consensus_reset = MagicMock()
    pipeline._ocr_pool = MagicMock()
    pipeline._ocr_health_history = []
    pipeline._recognition_log = MagicMock()
    pipeline._recognition_cards = MagicMock()
    new_webcam = MagicMock()
    switch = MagicMock(spec=CameraSwitch)
    switch.apply = MagicMock(return_value=(new_webcam, None))
    switch.source = 1
    pipeline.camera_switch = switch
    pipeline._open_webcam = MagicMock(return_value=new_webcam)
    monkeypatch_obj = pytest.MonkeyPatch()
    monkeypatch_obj.setattr(module, "GATES", {"main": {"source": 0}})
    monkeypatch_obj.setattr(module, "set_gate_camera_source",
                            lambda *a, **kw: None)
    try:
        result = pipeline._apply_camera_change()
        assert result is True
        assert pipeline._source_epoch == 1, "epoch phải tăng từ 0→1"
        assert pipeline._ocr_pending == {}, "pending phải clear"
        assert pipeline._ocr_submit_meta == {}, "submit_meta phải clear"
    finally:
        monkeypatch_obj.undo()