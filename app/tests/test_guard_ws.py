"""
pytest tests for /guard/ws alert delivery.

Regression coverage for a bug tracked in HANDOFF_CURSOR.md / README.md
("WS alerts not delivering"): confirms a connected client actually receives
alerts pushed via POST /api/dev/trigger-test-alert, including with multiple
concurrent clients (the scenario the original investigation suspected).
"""
import json
import threading
import pytest

from app.tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def enable_mocked_cv_endpoints(monkeypatch):
    monkeypatch.setenv('CV_PIPELINES_ENABLED', '1')
    import queue
    from types import SimpleNamespace
    import app.cv.pipeline as pipelines
    alerts = queue.Queue()
    def get_alert():
        try:
            return alerts.get_nowait()
        except queue.Empty:
            return None
    fake = SimpleNamespace(_alert_queue=alerts, get_alert=get_alert)
    monkeypatch.setattr(pipelines, 'get_pipeline', lambda gate_id='main': fake)


def _recv_async(ws, out, key, n=1):
    try:
        out[key] = [ws.receive_text() for _ in range(n)]
    except Exception as e:  # pragma: no cover - failure path surfaced via assertion
        out[key] = [f"ERR:{e}"]


def test_single_client_receives_alert(client):
    headers = auth_headers(client, "security")
    token = headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/guard/ws?token={token}&gate=main") as ws:
        out = {}
        t = threading.Thread(target=_recv_async, args=(ws, out, "c"), daemon=True)
        t.start()

        resp = client.post(
            "/api/dev/trigger-test-alert",
            params={"violation_type": "NO_HELMET", "plate_read": "ABC123"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        t.join(timeout=5)
        assert not t.is_alive(), "WS client never received the alert (timed out)"
        msg = json.loads(out["c"][0])
        assert msg["violation_type"] == "NO_HELMET"
        assert msg["plate_read"] == "ABC123"


def test_multiple_clients_all_receive_every_alert(client):
    """Two concurrent WS clients + two rapid alerts — both clients must get both."""
    headers = auth_headers(client, "security")
    token = headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/guard/ws?token={token}&gate=main") as ws1, \
         client.websocket_connect(f"/guard/ws?token={token}&gate=main") as ws2:
        out = {}
        threads = [
            threading.Thread(target=_recv_async, args=(ws1, out, "c1", 2), daemon=True),
            threading.Thread(target=_recv_async, args=(ws2, out, "c2", 2), daemon=True),
        ]
        for t in threads:
            t.start()

        for i in range(2):
            resp = client.post(
                "/api/dev/trigger-test-alert",
                params={"violation_type": "NO_HELMET", "plate_read": f"T{i}"},
                headers=headers,
            )
            assert resp.status_code == 200

        for t in threads:
            t.join(timeout=8)
            assert not t.is_alive(), "a WS client never received both alerts (timed out)"

        for key in ("c1", "c2"):
            plates = {json.loads(m)["plate_read"] for m in out[key]}
            assert plates == {"T0", "T1"}, f"{key} got {plates}"


def test_ws_rejects_invalid_token(client):
    """An invalid token must close the socket cleanly (1008), not crash the handler."""
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/guard/ws?token=not-a-real-token&gate=main"):
            pass
