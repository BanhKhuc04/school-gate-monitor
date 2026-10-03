"""
Tests cho Đợt 5 — Origin check + cookie auth cho /guard endpoints.

Verify:
- WS auth ưu tiên cookie HttpOnly hơn query token (giảm rủi ro URL token leak).
- WS auth chấp nhận Bearer Authorization header (cho script/curl).
- WS auth từ chối Origin không thuộc allowlist.
- /guard/video_feed chấp nhận cookie auth (Bearer header/cookie > query token).

Capture và MJPEG hữu hạn được fixture cách ly; không tải weights hay mở RTSP.
"""
import pytest
from fastapi.testclient import TestClient


def _login_token(client: TestClient, role: str) -> str:
    resp = client.post("/api/auth/login", json={"username": role, "password": "test123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_ws_accepts_cookie_auth(client):
    """WS endpoint chấp nhận HttpOnly cookie (ưu tiên hơn query token).

    Dùng TestClient để mở WS sau khi login (cookie được set). Connection
    phải được accept() (không raise) — pipeline không có alert trong test
    app, nhưng việc accept() chính là bằng chứng auth OK.
    """
    token = _login_token(client, "security")
    assert token, "Login must succeed"
    with client.websocket_connect(
        "/guard/ws",
        cookies={"gate_session": token},
    ) as ws:
        # WS accept() thành công → không raise WebSocketDisconnect về auth.
        # Gửi 1 message bất kỳ không cần — server không đọc message client.
        pass


def test_ws_accepts_bearer_authorization_header(client):
    """WS endpoint chấp nhận Bearer Authorization header (cho script)."""
    token = _login_token(client, "admin")
    client.cookies.clear()
    with client.websocket_connect(
        "/guard/ws",
        headers={"Authorization": f"Bearer {token}"},
    ) as ws:
        pass


def test_ws_still_accepts_query_token_as_fallback(client):
    """Query token vẫn hoạt động (fallback cho client chưa hỗ trợ cookie)."""
    token = _login_token(client, "security")
    client.cookies.clear()
    with client.websocket_connect(f"/guard/ws?token={token}") as ws:
        pass


def test_video_feed_accepts_cookie_auth(client):
    """GET /guard/video_feed chấp nhận cookie HttpOnly (không cần query token).

    Kỳ vọng: 200 OK (pipeline không có camera → MJPEG stream kết thúc
    nhanh, nhưng không phải 401). Đây là bằng chứng cookie đã được verify.
    """
    token = _login_token(client, "security")
    resp = client.get(
        "/guard/video_feed",
        cookies={"gate_session": token},
    )
    # 200: stream OK; không phải 401/403 — auth đã pass
    assert resp.status_code == 200, f"Cookie auth thất bại: {resp.status_code} {resp.text[:200]}"


def test_video_feed_accepts_bearer_header(client):
    """GET /guard/video_feed chấp nhận Bearer Authorization header."""
    token = _login_token(client, "admin")
    client.cookies.clear()
    resp = client.get(
        "/guard/video_feed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_video_feed_accepts_query_token(client):
    """GET /guard/video_feed vẫn chấp nhận query token (back-compat)."""
    token = _login_token(client, "security")
    client.cookies.clear()
    resp = client.get("/guard/video_feed", params={"token": token})
    assert resp.status_code == 200


def test_video_feed_rejects_unknown_origin(client, monkeypatch):
    monkeypatch.setenv("WS_ALLOWED_ORIGINS", "http://allowed.test")
    _login_token(client, "security")
    assert client.get("/guard/video_feed", headers={"Origin":"http://evil.test"}).status_code == 403


def test_video_feed_allows_configured_origin(client, monkeypatch):
    monkeypatch.setenv("WS_ALLOWED_ORIGINS", "http://allowed.test")
    _login_token(client, "security")
    response=client.get("/guard/video_feed", headers={"Origin":"http://allowed.test"})
    assert response.status_code == 200
    assert b"Content-Type: image/jpeg" in response.content


def test_video_feed_allows_no_origin_header(client):
    _login_token(client, "security")
    assert client.get("/guard/video_feed").status_code == 200


def test_ws_rejects_unknown_origin(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setenv("WS_ALLOWED_ORIGINS", "http://allowed.test")
    _login_token(client, "security")
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/guard/ws", headers={"Origin":"http://evil.test"}):
            pass
    assert error.value.code == 1008
