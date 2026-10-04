"""API /api/camera — đổi nguồn camera per-gate (restart pipeline được mock)."""
import pytest

from app.tests.conftest import auth_headers


@pytest.fixture
def restart_calls(monkeypatch):
    calls = []
    import app.cv.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "restart_pipeline", lambda gate_id: calls.append(gate_id))
    return calls


def test_camera_list_requires_auth(client):
    assert client.get("/api/camera").status_code == 401


def test_camera_list_forbidden_for_non_admin(client):
    resp = client.get("/api/camera", headers=auth_headers(client, "security"))
    assert resp.status_code == 403


def test_camera_list_returns_gates_and_presets(client):
    resp = client.get("/api/camera", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert any(g["id"] == "main" for g in data["gates"])
    assert isinstance(data["presets"], list)


def test_camera_set_source_saves_and_restarts(client, restart_calls):
    headers = auth_headers(client, "admin")
    resp = client.post("/api/camera/main", json={"source": "rtsp://cam.local/stream"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["restarted"] is True
    assert restart_calls == ["main"]

    main = next(g for g in client.get("/api/camera", headers=headers).json()["gates"] if g["id"] == "main")
    assert main["source"] == "rtsp://cam.local/stream"


def test_camera_set_source_unknown_gate_404(client, restart_calls):
    resp = client.post("/api/camera/no_such_gate", json={"source": "0"}, headers=auth_headers(client, "admin"))
    assert resp.status_code == 404
    assert restart_calls == []


def test_camera_set_source_blank_rejected(client, restart_calls):
    resp = client.post("/api/camera/main", json={"source": "   "}, headers=auth_headers(client, "admin"))
    assert resp.status_code == 400
    assert restart_calls == []
