"""
pytest tests for face integration in app/cv/pipeline.py (Step 17).
"""
import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from fastapi import status


def _get_token(client, username: str) -> str:
    """Login and return access token."""
    r = client.post("/api/auth/login", json={"username": username, "password": "test123"})
    if r.status_code != 200:
        raise RuntimeError(f"Login failed for {username}: {r.status_code} {r.json()}")
    return r.json()["access_token"]


def _auth_headers(client, username: str) -> dict:
    return {"Authorization": f"Bearer {_get_token(client, username)}"}


def _ensure_user(client, username: str):
    """Ensure user exists with correct test password in current test DB."""
    import app.db as app_db_module  # Same module object that conftest.py patches!
    import bcrypt, time
    conn = app_db_module.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    pw_hash = bcrypt.hashpw("test123".encode(), bcrypt.gensalt()).decode()
    now = int(time.time())
    if row is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, pw_hash, username, now),
        )
    else:
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username))
    conn.commit()


# ─── Face Alert Tests ──────────────────────────────────────────────────────────

class TestFaceMatchAlert:
    def test_face_alert_queue_put(self):
        """Face alert gets queued with correct structure."""
        from app.cv.pipeline import VideoPipeline

        mock_queue = MagicMock()
        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline._running = True
        pipeline._alert_queue = mock_queue
        pipeline._last_face_match_time = 0.0

        pipeline._push_face_match_alert("Nguyễn Văn A", 0.85, None)

        mock_queue.put.assert_called_once()
        alert = mock_queue.put.call_args[0][0]
        assert alert["type"] == "face_match"
        assert alert["matched_label"] == "Nguyễn Văn A"
        assert alert["similarity"] == 0.85
        assert "timestamp" in alert

    def test_face_alert_cooldown(self):
        """Second alert within FACE_MATCH_COOLDOWN is ignored."""
        from app.cv.pipeline import VideoPipeline

        mock_queue = MagicMock()
        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline._running = True
        pipeline._alert_queue = mock_queue
        pipeline._last_face_match_time = 0.0

        pipeline._push_face_match_alert("User 1", 0.9, None)
        assert mock_queue.put.call_count == 1

        pipeline._push_face_match_alert("User 2", 0.8, None)
        assert mock_queue.put.call_count == 1


# ─── Run Face Match Tests ─────────────────────────────────────────────────────

class TestRunFaceMatch:
    def test_run_face_match_no_registered_embeddings(self):
        """No registered embeddings — exits early."""
        from app.cv.pipeline import VideoPipeline

        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline._last_person_dets = [MagicMock(bbox=(100, 100, 200, 400))]
        pipeline._running = True
        pipeline._alert_queue = MagicMock()
        pipeline._last_face_match_time = 0.0

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        with patch("app.db.get_face_embeddings", return_value=[]):
            pipeline._run_face_match(frame)

    def test_run_face_match_saves_snapshot_and_logs_db_event(self):
        """
        Regression test: on a match, _run_face_match must (1) write a snapshot
        file and (2) call add_face_match_event to persist an audit row — both
        were previously silently skipped (snapshot_path was hardcoded to None
        and add_face_match_event was never called at all).
        """
        from app.cv.pipeline import VideoPipeline
        from app.cv.detector import Detection

        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline._last_person_dets = [Detection(class_name="person", confidence=0.9, bbox=(0, 0, 100, 300))]
        pipeline._running = True
        pipeline._alert_queue = MagicMock()
        pipeline._last_face_match_time = 0.0

        registered = [{"label_name": "Nguyễn Văn A", "vehicle_id": 7, "embedding": np.zeros(4, dtype=np.float32).tobytes()}]
        frame = np.zeros((300, 100, 3), dtype=np.uint8)

        with patch("app.db.get_face_embeddings", return_value=registered), \
             patch("app.db.add_face_match_event") as mock_add_event, \
             patch("app.cv.face.detect_and_embed", return_value=np.zeros(4, dtype=np.float32).tobytes()), \
             patch("app.cv.face.match_embedding", return_value=(True, 0.9, 0)), \
             patch("app.cv.pipeline.cv2.imwrite", return_value=True) as mock_imwrite:
            pipeline._run_face_match(frame)

        mock_imwrite.assert_called_once()
        mock_add_event.assert_called_once()
        _, kwargs = mock_add_event.call_args
        assert kwargs["matched_label"] == "Nguyễn Văn A"
        assert kwargs["vehicle_id"] == 7
        assert kwargs["snapshot_path"]  # non-empty path, not None

        pipeline._alert_queue.put.assert_called_once()
        alert = pipeline._alert_queue.put.call_args[0][0]
        assert alert["snapshot_url"]  # WS payload now carries the snapshot URL too

    def test_run_face_match_isolated_exception(self):
        """Exception inside _run_face_match does NOT propagate."""
        from app.cv.pipeline import VideoPipeline

        pipeline = VideoPipeline.__new__(VideoPipeline)
        pipeline._last_person_dets = []
        pipeline._running = True
        pipeline._alert_queue = MagicMock()

        with patch("app.db.get_face_embeddings", side_effect=RuntimeError("DB error")):
            try:
                pipeline._run_face_match(np.zeros((100, 100, 3), dtype=np.uint8))
            except RuntimeError:
                pytest.fail("_run_face_match should catch and not propagate exceptions")


# ─── Dev Trigger Endpoint Tests ───────────────────────────────────────────────

class TestFaceMatchEndpoints:
    def test_trigger_requires_auth(self, client):
        r = client.post("/api/dev/trigger-test-face-match")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_trigger_requires_security_or_admin(self, client):
        """Management cannot trigger face match alerts (only security/admin)."""
        _ensure_user(client, "management")
        r = client.post(
            "/api/dev/trigger-test-face-match",
            headers=_auth_headers(client, "management"),
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_trigger_security_ok(self, client):
        """Security user can trigger face match alert."""
        _ensure_user(client, "security")
        r = client.post(
            "/api/dev/trigger-test-face-match",
            headers=_auth_headers(client, "security"),
        )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["ok"] is True
        assert data["alert"]["type"] == "face_match"
        assert data["alert"]["matched_label"] == "Nguyễn Văn A"
        assert data["alert"]["similarity"] == 0.75

    def test_trigger_admin_ok(self, client):
        """Admin can also trigger face match alert."""
        _ensure_user(client, "admin")
        r = client.post(
            "/api/dev/trigger-test-face-match",
            headers=_auth_headers(client, "admin"),
        )
        assert r.status_code == status.HTTP_200_OK
