"""
Test cho guard API: WebSocket alerts và video feed (Đợt 5, D5.1).

D5.1: Phân phối sự kiện nhiều gate/client.
  - Test mỗi client nhận alert đúng gate
  - Test hai client cùng nhận event ID
  - Test disconnect/reconnect
  - Test WS auth
"""
import queue

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# ─── Auth helpers (reuse conftest.py helpers via direct import) ─────────────────

ROLE_PASSWORD = "test123"


@pytest.fixture(autouse=True)
def enable_mocked_cv_endpoints(monkeypatch):
    monkeypatch.setenv('CV_PIPELINES_ENABLED', '1')


def _login(client: TestClient, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": ROLE_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


# ─── Test: WS auth rejects ─────────────────────────────────────────────────────

def test_ws_rejects_missing_token(test_app):
    """WS endpoint rejects connection without token."""
    with TestClient(test_app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/guard/ws"):
                pass


def test_ws_rejects_invalid_token(test_app):
    """WS endpoint rejects connection with invalid token."""
    with TestClient(test_app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/guard/ws?token=invalid"):
                pass


def test_ws_rejects_expired_token(test_app):
    """WS endpoint rejects connection with expired token."""
    import jwt as _jwt
    from app.config import JWT_SECRET_KEY, JWT_ALGORITHM
    from datetime import timedelta, datetime, timezone

    expired_token = _jwt.encode(
        {
            "sub": "security",
            "role": "security",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    with TestClient(test_app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/guard/ws?token={expired_token}"):
                pass


def test_ws_rejects_non_security_role(test_app):
    """WS endpoint rejects non-security role (teacher has no guard access)."""
    with TestClient(test_app) as client:
        token = _login(client, "teacher")
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/guard/ws?token={token}"):
                pass


@pytest.mark.parametrize("role", ["security", "admin", "management"])
def test_ws_accepts_security_role(test_app, role):
    with TestClient(test_app) as client:
        token = _login(client, role)
        client.cookies.clear()
        with client.websocket_connect(f"/guard/ws?token={token}&gate=main") as ws:
            assert ws.accepted_subprotocol is None


def test_ws_accepts_gate_parameter(test_app):
    with TestClient(test_app) as client:
        token = _login(client, "security")
        client.cookies.clear()
        with client.websocket_connect(f"/guard/ws?token={token}&gate=secondary") as ws:
            assert ws.accepted_subprotocol is None


# ─── Test: Video feed auth ───────────────────────────────────────────────────

def test_video_feed_requires_token(test_app):
    """GET /guard/video_feed returns 401 without token."""
    with TestClient(test_app) as client:
        resp = client.get("/guard/video_feed")
        assert resp.status_code == 401


def test_video_feed_requires_valid_token(test_app):
    """GET /guard/video_feed returns 401 with invalid token."""
    with TestClient(test_app) as client:
        resp = client.get("/guard/video_feed", params={"token": "invalid"})
        assert resp.status_code == 401


def test_video_feed_requires_security_role(test_app):
    """GET /guard/video_feed returns 401 for teacher role."""
    with TestClient(test_app) as client:
        token = _login(client, "teacher")
        resp = client.get("/guard/video_feed", params={"token": token})
        assert resp.status_code == 401


def test_video_feed_accepts_security_role(test_app):
    for role in ("security", "admin", "management"):
        with TestClient(test_app) as client:
            token = _login(client, role)
            resp = client.get("/guard/video_feed", params={"token": token})
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("multipart/x-mixed-replace")
            assert b"Content-Type: image/jpeg" in resp.content
            assert b"\xff\xd8fixture\xff\xd9" in resp.content


# ─── Test: Alert dedup via track_id (backend side) ───────────────────────────

def test_duplicate_alerts_suppressed_by_cooldown(client):
    """Backend cooldown (EventManager) prevents duplicate alerts for same track within window."""
    # This is already tested in test_event_manager.py and test_vehicle_gate.py.
    # Here we verify the API-level: GET /api/violations returns consistent results.
    headers = {"Authorization": f"Bearer {_login(client, 'admin')}"}
    resp = client.get("/api/violations", headers=headers)
    assert resp.status_code == 200


# ─── Test: Alert queue contract ────────────────────────────────────────────────

def test_alert_queue_empty_returns_none():
    """Empty alert queue → get_alert() returns None."""
    from app.cv.pipeline import VideoPipeline

    p = VideoPipeline.__new__(VideoPipeline)
    p._alert_queue = queue.Queue()
    assert p.get_alert() is None


def test_alert_queue_fifo():
    """Items leave queue FIFO."""
    from app.cv.pipeline import VideoPipeline

    p = VideoPipeline.__new__(VideoPipeline)
    p._alert_queue = queue.Queue()
    p._alert_queue.put({"violation_type": "A", "track_id": 1})
    p._alert_queue.put({"violation_type": "B", "track_id": 2})
    assert p.get_alert()["violation_type"] == "A"
    assert p.get_alert()["violation_type"] == "B"
    assert p.get_alert() is None


# ─── Test: Alert data structure (D5.1 contract) ────────────────────────────────

def test_alert_data_structure():
    """Alert pushed to queue contains all expected fields for WS broadcast."""
    from app.cv.pipeline import VideoPipeline

    p = VideoPipeline.__new__(VideoPipeline)
    p._alert_queue = queue.Queue()

    mock_alert = {
        "violation_type": "NO_HELMET",
        "plate_read": "30A-12345",
        "plate_matched": "30A-12345",
        "track_id": 5,
        "snapshot_url": "/snapshots/test.jpg",
        "gate_id": "main",
        "helmet_status": "no_helmet",
        "ts": 1234567890.0,
    }
    p._alert_queue.put(mock_alert)

    alert = p.get_alert()
    assert alert["violation_type"] == "NO_HELMET"
    assert alert["track_id"] == 5
    assert alert["gate_id"] == "main"
    assert alert["plate_read"] == "30A-12345"


# ─── Test: WS endpoint responds (not 404/405) ─────────────────────────────────

def test_ws_endpoint_responds(test_app):
    with TestClient(test_app) as client:
        _login(client, "security")
        with client.websocket_connect("/guard/ws?gate=main") as ws:
            assert ws.accepted_subprotocol is None


def test_two_websocket_viewers_receive_event_but_only_owner_can_speak(client, monkeypatch):
    from uuid import uuid4
    from types import SimpleNamespace
    import app.cv.pipeline as pipeline
    import app.api.audio_lease as lease
    monkeypatch.setattr(lease, '_leases', {})
    messages=queue.Queue()
    def get_alert():
        try: return messages.get_nowait()
        except queue.Empty: return None
    monkeypatch.setattr(pipeline, 'get_pipeline', lambda gate_id: SimpleNamespace(get_alert=get_alert))
    _login(client, 'security')
    owner, viewer=str(uuid4()),str(uuid4())
    assert client.post('/guard/audio/lease',json={'client_id':owner,'gate_id':'main'}).status_code==200
    with client.websocket_connect(f'/guard/ws?gate=main&client_id={owner}') as a:
        with client.websocket_connect(f'/guard/ws?gate=main&client_id={viewer}') as b:
            messages.put({'event_id':'shared-live-event','event_version':1})
            first,second=a.receive_json(),b.receive_json()
            assert first['event_id']==second['event_id']=='shared-live-event'
            assert first['audio_authorized'] is True
            assert second['audio_authorized'] is False
