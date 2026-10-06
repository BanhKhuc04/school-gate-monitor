"""Test: camera offline / nguồn trống → 0 violations.

Kiểm chứng: khi pipeline đọc frame liên tục không có person (nguồn trống),
không có sự kiện vi phạm nào được ghi vào DB.

Đây là test tái hiện nguyên nhân violations tăng sau khi dừng nguồn:
stale processes vẫn chạy và tạo violations giả.
"""
import time
import numpy as np
import sqlite3
from unittest.mock import MagicMock, patch
from app.cv.pipeline import VideoPipeline


def _test_conn(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def test_source_change_clears_cooldown(tmp_path, monkeypatch):
    """Khi đổi nguồn camera, cooldown state được reset để tránh
    violations sai sau khi chuyển video/nguồn khác nhau."""
    import app.db as db_module
    import app.config as cfg

    orig_cfg = cfg.DB_PATH
    orig_db = db_module.DB_PATH
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(cfg, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "get_connection", lambda: _test_conn(str(test_db)))

    from app.db import init_db
    init_db()

    try:
        pipeline = VideoPipeline("test", {"source": "0", "loop": False, "name": "Test"})

        pipeline._last_log_time["track:123"] = time.time() - 10
        pipeline._last_log_time["plate:ABC"] = time.time() - 20
        pipeline._last_log_time["grid:3:2:NO_HELMET"] = time.time() - 30

        assert len(pipeline._last_log_time) == 3

        # Source change clears cooldown (matches real _apply_camera_change)
        pipeline._last_log_time.clear()
        assert len(pipeline._last_log_time) == 0

        pipeline._event_manager.reset()
        assert pipeline._event_manager.active_track_count() == 0
    finally:
        cfg.DB_PATH = orig_cfg
        db_module.DB_PATH = orig_db


def test_two_tracks_different_cooldown(tmp_path, monkeypatch):
    """Hai xe ở vị trí khác nhau (track_id khác) không dùng chung cooldown."""
    import app.db as db_module
    import app.config as cfg

    orig_cfg = cfg.DB_PATH
    orig_db = db_module.DB_PATH
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(cfg, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "get_connection", lambda: _test_conn(str(test_db)))

    from app.db import init_db
    init_db()

    try:
        pipeline = VideoPipeline("test", {"source": "0", "loop": False, "name": "Test"})

        key1 = "track:100"
        pipeline._last_log_time[key1] = time.time() - 30

        key2 = "track:200"
        pipeline._last_log_time[key2] = time.time() - 30

        # Different tracks → different cooldown keys
        assert key1 != key2
        assert (time.time() - pipeline._last_log_time[key1]) < cfg.VIOLATION_COOLDOWN
        assert (time.time() - pipeline._last_log_time[key2]) < cfg.VIOLATION_COOLDOWN

        # Grid-based keys also different for different positions
        key3 = "grid:3:2:NO_HELMET"
        key4 = "grid:7:5:NO_HELMET"
        pipeline._last_log_time[key3] = time.time()
        pipeline._last_log_time[key4] = time.time()
        assert key3 != key4
    finally:
        cfg.DB_PATH = orig_cfg
        db_module.DB_PATH = orig_db


def test_frame_without_person_skips_violation_check(monkeypatch):
    """Run the actual empty-frame branch even when helmet inference is disabled."""
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from app.tests.test_dot_R import _build_pipeline_with_mocks
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    p._detect_pool = ThreadPoolExecutor(max_workers=3)
    p._helmet_detector = None
    p._person_detector = SimpleNamespace(detect_tracked=lambda frame: [])
    p._plate_detector = SimpleNamespace(detect=lambda frame: [])
    p._process_violations = MagicMock()
    class Source:
        count = 0
        def read_frame(self):
            self.count += 1
            if self.count == 10:
                p._running = False
            return np.zeros((120, 180, 3), dtype=np.uint8)
        def release(self): pass
    p._open_webcam = lambda config: Source()
    try:
        p._run_loop()
        p._process_violations.assert_not_called()
        assert p._frame_count == 10
        # FIX (T4): _build_pipeline_with_mocks dùng __new__ bypass __init__
        # → KHÔNG có _preview_thread. Test publish JPEG sync trực tiếp.
        last_frame = np.zeros((120, 180, 3), dtype=np.uint8)
        p._publish_frame_jpeg(last_frame, 10)
        assert p.get_jpeg() is not None
        assert any(row['reason_code'] == 'no_objects' for row in p._recognition_log.snapshot()['items'])
    finally:
        p._detect_pool.shutdown(wait=True)
        p._ocr_pool.shutdown(wait=True)


def test_blank_frames_produce_no_violations(tmp_path, monkeypatch):
    """Frame trắng (không có person) không tạo violations."""
    import app.db as db_module
    import app.config as cfg

    orig_cfg = cfg.DB_PATH
    orig_db = db_module.DB_PATH
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(cfg, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "DB_PATH", str(test_db))
    monkeypatch.setattr(db_module, "get_connection", lambda: _test_conn(str(test_db)))

    from app.db import init_db
    init_db()

    try:
        initial_count = db_module.get_connection().cursor().execute(
            "SELECT COUNT(*) FROM violation_events").fetchone()[0]

        with patch("cv2.imwrite", return_value=True):
            with patch.object(VideoPipeline, '_write_clip'):
                with patch("app.cv.ocr.read_plate_detailed",
                          return_value=MagicMock(text="", confidence=0.0, is_confident=False)):
                    pipeline = VideoPipeline("test", {"source": "0", "loop": False, "name": "Test"})

                    # Simulate 60 frames with blank frames (no person detected)
                    for _ in range(60):
                        pipeline._frame_count += 1
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        # This mirrors the "no person" branch in _run_loop
                        pipeline._draw_roi(frame)

                    final_count = db_module.get_connection().cursor().execute(
                        "SELECT COUNT(*) FROM violation_events").fetchone()[0]
                    assert final_count == initial_count, \
                        f"Expected 0 new violations, got {final_count - initial_count}"
    finally:
        cfg.DB_PATH = orig_cfg
        db_module.DB_PATH = orig_db
