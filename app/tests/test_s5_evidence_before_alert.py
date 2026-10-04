"""
S5: evidence-before-alert + evidence_state='pending'/'persisted'/'failed'

Pre-E3 fix plan:
- DB + snapshot ghi xong MỚI đẩy alert (tránh URL giả).
- imwrite/DB fail → evidence_state='failed', KHÔNG phát alert.
- Fault injection: giả lập imwrite trả False hoặc DB insert lỗi.
"""

import os
import queue
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _build_pipeline_for_s5(monkeypatch, gate_id="main"):
    """Pipeline + mock cho S5 — không load model thật."""
    from app.cv import pipeline as p_mod

    # Stub WebcamStream
    class FakeWebcam:
        _opened = True
        def read_frame(self):
            return np.zeros((720, 1280, 3), dtype=np.uint8)
        def release(self):
            pass
        @property
        def is_open(self):
            return True
    monkeypatch.setattr(p_mod, "WebcamStream", FakeWebcam)

    # Stub detectors — không cần load model thật
    class StubDetector:
        def __init__(self, *a, **kw):
            pass
        def detect(self, frame):
            return []
    monkeypatch.setattr(p_mod, "HelmetPlateDetector", StubDetector)

    pipeline = p_mod.VideoPipeline.__new__(p_mod.VideoPipeline)
    pipeline.gate_id = gate_id
    pipeline._running = True
    pipeline._lock = __import__('threading').Lock()
    pipeline._latest_frame = None
    pipeline._latest_jpeg = None
    pipeline._frame_seq = 0
    pipeline._frame_count = 0
    pipeline._source_epoch = 0
    pipeline._alert_queue = queue.Queue()
    pipeline._last_alert_time = 0.0
    pipeline._last_log_time = {}
    pipeline._last_helmet_dets = []
    pipeline._last_plate_dets = []
    pipeline._last_person_dets = []
    pipeline._last_pose_data = []
    pipeline._clip_buffer = []
    pipeline._evidence_ledger = None
    pipeline._event_manager = None
    pipeline._plate_voter = MagicMock()
    pipeline._plate_voter.read = MagicMock(return_value=MagicMock(
        text="", confidence=0.0, sample_count=0, is_confident=False,
        pending=False,
    ))
    pipeline.camera_switch = None
    pipeline.camera_id = gate_id
    # IO pool đồng bộ cho test — submit() chạy ngay trên caller thread
    import concurrent.futures
    pipeline._io_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="s5-test")
    pipeline._detect_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="s5-test-det")
    pipeline._ocr_pool = pipeline._io_pool
    pipeline._ocr_pending = {}
    pipeline._ocr_submit_meta = {}
    pipeline._ocr_max_pending = 16
    pipeline._ocr_health = {"errors": 0, "empty": 0, "submitted": 0,
                            "completed": 0, "stale_dropped": 0,
                            "sync_fallbacks": 0, "duplicate_dropped": 0}
    pipeline._jpeg_max_size = 30
    return pipeline


class TestS5EvidenceBeforeAlert:
    """S5: pipeline ghi DB/snapshot xong MỚI phát alert; nếu fail → không phát."""

    def _make_db_mock(self, monkeypatch, fail_insert=False):
        """Mock app.db.add_violation_event — trả id giả hoặc raise."""
        captured = {"calls": [], "fail_insert": fail_insert}

        def fake_add(**kwargs):
            captured["calls"].append(kwargs)
            if fail_insert:
                raise RuntimeError("simulated DB write failure")
            captured["next_id"] = captured.get("next_id", 0) + 1
            return captured["next_id"]

        monkeypatch.setattr(
            "app.cv.pipeline.add_violation_event", fake_add)
        monkeypatch.setattr(
            "app.cv.pipeline.find_correlation_candidates", lambda *a, **kw: [])
        monkeypatch.setattr(
            "app.cv.pipeline.mark_correlation_unmatched", lambda *a, **kw: None)
        monkeypatch.setattr(
            "app.cv.pipeline.link_violation_events", lambda *a, **kw: True)
        return captured

    def test_alert_pushed_only_after_successful_persist(self, monkeypatch):
        """imwrite OK + insert OK → alert có trong queue SAU khi _persist_violation
        return. Không gọi alert trước khi IO hoàn tất."""
        from app.cv import pipeline as p_mod

        pipeline = _build_pipeline_for_s5(monkeypatch)
        captured = self._make_db_mock(monkeypatch, fail_insert=False)

        # Patch imwrite thành công
        def ok_imwrite(path, frame):
            # Tạo file giả để os.path.exists đúng (cho _write_clip không sao)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"fake_jpg")
            return True
        monkeypatch.setattr(p_mod.cv2, "imwrite", ok_imwrite)

        # Chạy _persist_violation trực tiếp
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        pipeline._persist_violation(
            frame, "/tmp/s5_test/test.jpg", "test.jpg",
            "59A12345", None, "no_helmet", "NO_HELMET",
            "riding", True, 0.9, "main", "pending",
            "enc-1", None, "2026-10-01T08:00:00", 0, "main",
        )

        # Alert phải có trong queue
        assert not pipeline._alert_queue.empty(), (
            "Alert phải được đẩy SAU khi DB + snapshot ghi xong"
        )
        alert = pipeline._alert_queue.get_nowait()
        assert alert["violation_type"] == "NO_HELMET"
        assert alert["plate_read"] == "59A12345"
        assert alert["snapshot_url"] == "/api/media/snapshots/test.jpg"
        # DB insert có gọi, evidence_state='persisted'
        assert len(captured["calls"]) == 1
        assert captured["calls"][0]["evidence_state"] == "persisted"

    def test_alert_not_pushed_when_imwrite_fails(self, monkeypatch):
        """imwrite False (disk full / bad path) → alert KHÔNG đẩy,
        evidence_state='failed' trong DB."""
        from app.cv import pipeline as p_mod

        pipeline = _build_pipeline_for_s5(monkeypatch)
        captured = self._make_db_mock(monkeypatch, fail_insert=False)

        def fail_imwrite(path, frame):
            return False
        monkeypatch.setattr(p_mod.cv2, "imwrite", fail_imwrite)

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        pipeline._persist_violation(
            frame, "/tmp/s5_test/test.jpg", "test.jpg",
            "59A12345", None, "no_helmet", "NO_HELMET",
            "riding", True, 0.9, "main", "pending",
            "enc-1", None, "2026-10-01T08:00:00", 0, "main",
        )

        # Queue alert phải rỗng — imwrite fail, KHÔNG phát alert
        assert pipeline._alert_queue.empty(), (
            "Alert KHÔNG được đẩy khi snapshot imwrite fail"
        )
        # DB vẫn có row nhưng evidence_state='failed'
        assert len(captured["calls"]) == 1
        assert captured["calls"][0]["evidence_state"] == "failed"
        # snapshot_path phải None
        assert captured["calls"][0]["snapshot_path"] is None

    def test_alert_not_pushed_when_db_insert_raises(self, monkeypatch):
        """DB insert raise (DB locked / disk error) → alert KHÔNG đẩy,
        nhưng pipeline không crash (try/except outer)."""
        from app.cv import pipeline as p_mod

        pipeline = _build_pipeline_for_s5(monkeypatch)
        captured = self._make_db_mock(monkeypatch, fail_insert=True)

        def ok_imwrite(path, frame):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"fake_jpg")
            return True
        monkeypatch.setattr(p_mod.cv2, "imwrite", ok_imwrite)

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Không được raise ra ngoài — outer try/except nuốt exception
        try:
            pipeline._persist_violation(
                frame, "/tmp/s5_test/test.jpg", "test.jpg",
                "59A12345", None, "no_helmet", "NO_HELMET",
                "riding", True, 0.9, "main", "pending",
                "enc-1", None, "2026-10-01T08:00:00", 0, "main",
            )
        except Exception as e:
            pytest.fail(f"_persist_violation không được raise ra ngoài: {e}")

        # Alert KHÔNG đẩy vì DB raise trước khi _push_alert()
        assert pipeline._alert_queue.empty(), (
            "Alert KHÔNG được đẩy khi DB insert lỗi"
        )

    def test_process_violations_does_not_push_alert_directly(self, monkeypatch):
        """Pre-E3 bug: _process_violations đẩy alert TRƯỚC khi ghi DB/snapshot.
        Sau fix: _process_violations chỉ enqueue IO; alert đẩy từ _persist_violation.
        Kiểm tra _process_violations gọi _persist_violation mà KHÔNG gọi
        _push_alert ở đường chính (vehicle_type=None → early-return)."""
        from app.cv import pipeline as p_mod

        pipeline = _build_pipeline_for_s5(monkeypatch)

        # Stub push_alert để track call
        push_calls = []
        def fake_push_alert(*a, **kw):
            push_calls.append((a, kw))
        pipeline._push_alert = fake_push_alert

        # Stub persist để track call
        persist_calls = []
        def fake_persist(*a, **kw):
            persist_calls.append((a, kw))
        pipeline._persist_violation = fake_persist

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # vehicle_type=None → early-return (người đi bộ, không có vi phạm)
        # → không gọi _push_alert, không gọi _persist_violation
        pipeline._process_violations(
            frame, [], [],
            posture_status="riding", vehicle_type=None,
            too_many_riders=False, track_id=1,
            person_bbox=(10, 10, 50, 50), crossed_gate=False,
            frame_seq=1, vehicle_bbox=(10, 10, 50, 50),
        )
        assert push_calls == [], (
            f"_process_violations gọi _push_alert quá sớm: {push_calls}"
        )
        assert persist_calls == [], (
            f"_process_violations gọi _persist_violation quá sớm (no violation): {persist_calls}"
        )


class TestS5EvidenceStateColumn:
    """Migration evidence_state phải có và mặc định 'persisted' cho record cũ."""

    def test_evidence_state_column_exists(self):
        """ALTER TABLE migration chạy → cột evidence_state tồn tại."""
        from app.db import init_db, get_connection, _write_lock
        import tempfile
        tmp = tempfile.mkdtemp(prefix="s5_db_")
        db_path = os.path.join(tmp, "test.db")

        from app import config as cfg
        import app.db as db_module
        orig_path = cfg.DB_PATH
        orig_module_path = db_module.DB_PATH
        cfg.DB_PATH = db_path
        db_module.DB_PATH = db_path

        import sqlite3 as _sq
        def _get():
            conn = _sq.connect(db_path, check_same_thread=False)
            conn.row_factory = _sq.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            return conn
        orig_conn = db_module.get_connection
        db_module.get_connection = _get

        try:
            init_db()
            conn = db_module.get_connection()
            cols = [r["name"] for r in conn.execute(
                "PRAGMA table_info(violation_events)").fetchall()]
            assert "evidence_state" in cols, (
                f"Cột evidence_state phải có; hiện có {cols}"
            )
            conn.close()
        finally:
            cfg.DB_PATH = orig_path
            db_module.DB_PATH = orig_module_path
            db_module.get_connection = orig_conn

    def test_add_violation_event_default_evidence_state(self):
        """add_violation_event() không truyền evidence_state → default 'persisted'."""
        from app.db import init_db, get_connection, add_violation_event
        import tempfile
        tmp = tempfile.mkdtemp(prefix="s5_db2_")
        db_path = os.path.join(tmp, "test.db")

        from app import config as cfg
        import app.db as db_module
        orig_path = cfg.DB_PATH
        orig_module_path = db_module.DB_PATH
        cfg.DB_PATH = db_path
        db_module.DB_PATH = db_path

        import sqlite3 as _sq
        def _get():
            conn = _sq.connect(db_path, check_same_thread=False)
            conn.row_factory = _sq.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            return conn
        orig_conn = db_module.get_connection
        db_module.get_connection = _get

        try:
            init_db()
            new_id = add_violation_event(
                timestamp="2026-10-01T08:00:00",
                plate_read="59A12345",
                helmet_status="no_helmet",
                violation_type="NO_HELMET",
                gate_id="main",
            )
            conn = db_module.get_connection()
            row = conn.execute(
                "SELECT evidence_state FROM violation_events WHERE id = ?",
                (new_id,)
            ).fetchone()
            assert row["evidence_state"] == "persisted", (
                f"Default evidence_state phải là 'persisted'; "
                f"hiện tại {row['evidence_state']!r}"
            )
            conn.close()
        finally:
            cfg.DB_PATH = orig_path
            db_module.DB_PATH = orig_module_path
            db_module.get_connection = orig_conn

def test_clip_is_h264_real_speed_with_post_roll(tmp_path):
    """Browsers cannot play OpenCV's mp4v; the clip must be H.264, play at the
    real rate, and include frames from after the crossing."""
    import subprocess, shutil
    import numpy as np
    from collections import deque
    from app.cv import pipeline as module
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p._clip_buffer, p._clip_times = deque(maxlen=64), deque(maxlen=64)
    t0 = 1000.0
    for i in range(30):  # 30 frames over 3 s; event at t0+2
        p._clip_buffer.append(np.full((360, 640, 3), i * 8, np.uint8))
        p._clip_times.append(t0 + i * .1)
    pre = module._ClipFrames(list(p._clip_buffer)[:21])
    pre.times, pre.event_ts = list(p._clip_times)[:21], t0 + 2.0
    import unittest.mock as m
    with m.patch.object(module.time, 'time', return_value=t0 + 10), m.patch.object(module, 'VIOLATION_CLIP_POST_SECONDS', 1):
        frames = p._add_post_roll(pre)
    assert len(frames) == 30 and frames.times[-1] == t0 + 2.9
    out = tmp_path / 'clip.mp4'
    assert p._write_clip(frames, str(out))
    if shutil.which('ffprobe'):
        info = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,r_frame_rate',
                               '-of', 'csv=p=0', str(out)], capture_output=True, text=True).stdout
        assert info.startswith('h264') and '10/1' in info
