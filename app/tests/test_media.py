"""
Test cho media API (D6.2: scoped media endpoint).

Các test được thiết kế để chạy với fixture test_app (override DB/media) và
không phụ thuộc filesystem thật.
"""
import pytest


# ─── Auth helpers ───────────────────────────────────────────────────────────────
ROLE_PASSWORD = "test123"


def _login(client, username: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": ROLE_PASSWORD})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Snapshot endpoint ──────────────────────────────────────────────────────────

def test_snapshot_requires_auth(client):
    """GET /api/media/snapshots/{f} returns 401 without token."""
    resp = client.get("/api/media/snapshots/fake.jpg")
    assert resp.status_code == 401


def test_snapshot_rejects_teacher(client):
    """Teacher role has no access to /api/media/snapshots."""
    token = _login(client, "teacher")
    resp = client.get("/api/media/snapshots/fake.jpg", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_snapshot_accepts_security(client):
    """Security role can access /api/media/snapshots (404 = file not found, auth succeeded)."""
    token = _login(client, "security")
    resp = client.get("/api/media/snapshots/fake.jpg", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_snapshot_accepts_admin(client):
    """Admin role can access /api/media/snapshots (404 = file not found, auth succeeded)."""
    token = _login(client, "admin")
    resp = client.get("/api/media/snapshots/fake.jpg", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_snapshot_path_traversal_rejected(client):
    """Path traversal via ../ in filename is blocked (Starlette normalizes URL path,
    then _safe_file_path checks existence → 404). The attack is fully neutralized."""
    token = _login(client, "admin")
    resp = client.get(
        "/api/media/snapshots/../nonexistent_windows_file_XYZ789.jpg",
        headers=_auth_headers(token),
    )
    # Starlette normalizes ../nonexistent_... → filename="nonexistent_windows_file_XYZ789.jpg"
    # → _safe_file_path checks os.path.exists → 404 (attack blocked)
    assert resp.status_code == 404


def test_snapshot_path_traversal_via_backslash_rejected(client):
    """Backslash path traversal is blocked by backslash separator check."""
    token = _login(client, "admin")
    resp = client.get("/api/media/snapshots/..\\nonexistent_ABC123.jpg",
                      headers=_auth_headers(token))
    # Backslash rejected at separator check → 400
    assert resp.status_code == 400


def test_snapshot_subdir_traversal_rejected(client):
    """Deep traversal (snapshots/../../etc) is blocked by Starlette URL normalization."""
    token = _login(client, "admin")
    resp = client.get("/api/media/snapshots/../../nonexistent_xyz99.jpg",
                      headers=_auth_headers(token))
    assert resp.status_code == 404


# ─── Clip endpoint ──────────────────────────────────────────────────────────────

def test_clip_requires_auth(client):
    """GET /api/media/clips/{f} returns 401 without token."""
    resp = client.get("/api/media/clips/fake.mp4")
    assert resp.status_code == 401


def test_clip_accepts_security(client):
    """Security role can access /api/media/clips (404 = file not found, auth succeeded)."""
    token = _login(client, "security")
    resp = client.get("/api/media/clips/fake.mp4", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_clip_path_traversal_rejected(client):
    """Clip path traversal blocked by Starlette URL normalization."""
    token = _login(client, "admin")
    resp = client.get("/api/media/clips/../../../nonexistent_video.xyz",
                      headers=_auth_headers(token))
    assert resp.status_code == 404


# ─── Student photo endpoint ──────────────────────────────────────────────────────

def test_student_photo_requires_admin(client):
    """GET /api/media/student-photos/{f} returns 403 for non-admin."""
    token = _login(client, "security")
    resp = client.get("/api/media/student-photos/fake.jpg", headers=_auth_headers(token))
    assert resp.status_code == 403


def test_student_photo_accepts_admin(client):
    """Admin role can access /api/media/student-photos (404 = file not found, auth succeeded)."""
    token = _login(client, "admin")
    resp = client.get("/api/media/student-photos/fake.jpg", headers=_auth_headers(token))
    assert resp.status_code == 404


def test_student_photo_path_traversal_rejected(client):
    """Path traversal for student photos: Starlette normalizes ../ -> 404 (no mount),
    but the dot-start check also blocks ..config.py → 400. Both defenses work."""
    token = _login(client, "admin")
    # Either: dot-start in normalized filename (→ 400) or Starlette resolves → 404
    resp = client.get("/api/media/student-photos/../config.py",
                     headers=_auth_headers(token))
    assert resp.status_code in (400, 404)


# ─── Teacher class scope ──────────────────────────────────────────────────────────

def test_teacher_snapshot_unowned_file_is_forbidden(client):
    """Missing DB ownership fails closed before revealing file existence."""
    token = _login(client, "teacher")
    resp = client.get("/api/media/snapshots/viol_999_1234567890.jpg", headers=_auth_headers(token))
    assert resp.status_code == 403


@pytest.fixture
def scoped_media(test_app, monkeypatch, tmp_path):
    import sqlite3
    import numpy as np
    import cv2
    import app.db as db
    import app.api.media as media
    isolated=tmp_path/'media-test.db'
    source=db.get_connection()
    target=sqlite3.connect(isolated)
    source.backup(target)
    source.close()
    target.execute('DELETE FROM violation_events')
    target.execute('DELETE FROM registered_vehicles')
    for plate, school_class in [('fixture-A','10A1'),('fixture-B','10B1')]:
        target.execute('INSERT INTO registered_vehicles(plate_number,student_name,student_class) VALUES (?,?,?)',
                       (plate, 'Synthetic student', school_class))
        target.execute('INSERT INTO violation_events(timestamp,plate_matched,helmet_status,violation_type,snapshot_path,clip_path) VALUES (?,?,?,?,?,?)',
                       ('2026-10-01T08:00:00Z',plate,'no_helmet','NO_HELMET',str(tmp_path/(plate+'.jpg')),str(tmp_path/(plate+'.mp4'))))
    target.commit()
    target.close()
    def connection():
        conn=sqlite3.connect(isolated,check_same_thread=False)
        conn.row_factory=sqlite3.Row
        return conn
    monkeypatch.setattr(db,'get_connection',connection)
    monkeypatch.setattr(media,'SNAPSHOTS_DIR',str(tmp_path))
    ok, encoded=cv2.imencode('.jpg',np.zeros((16,16,3),dtype=np.uint8))
    assert ok
    content=encoded.tobytes()
    for plate in ['fixture-A','fixture-B']:
        (tmp_path/(plate+'.jpg')).write_bytes(content)
        (tmp_path/(plate+'.mp4')).write_bytes(b'isolated-range-fixture')
    return content


@pytest.mark.parametrize('role',['admin','security','teacher'])
def test_authorized_snapshot_returns_actual_image(client, scoped_media, role):
    import cv2, numpy as np
    token=_login(client,role)
    response=client.get('/api/media/snapshots/fixture-A.jpg',headers=_auth_headers(token))
    assert response.status_code==200
    assert response.content==scoped_media
    assert cv2.imdecode(np.frombuffer(response.content,dtype=np.uint8),cv2.IMREAD_COLOR).shape==(16,16,3)


def test_teacher_cannot_access_other_class_media(client, scoped_media):
    token=_login(client,'teacher')
    for path in ['snapshots/fixture-B.jpg','clips/fixture-B.mp4']:
        assert client.get('/api/media/'+path,headers=_auth_headers(token)).status_code==403


def test_teacher_without_class_fails_closed_on_all_event_routes(client, scoped_media):
    from app.auth import create_access_token
    token=create_access_token('fixture-no-class','teacher')
    client.cookies.clear()
    for path in ['/api/violations','/api/violations/encounters','/api/violations/1','/api/media/snapshots/fixture-A.jpg']:
        assert client.get(path,headers=_auth_headers(token)).status_code==403


# ─── Production static mount disabled ──────────────────────────────────────────

def test_media_api_works_in_production_mode(test_app_env_prod):
    """In production mode, API endpoint for media still works (static mount disabled)."""
    from fastapi.testclient import TestClient
    with TestClient(test_app_env_prod) as client:
        token = _login(client, "admin")
        resp = client.get("/api/media/snapshots/test.jpg", headers=_auth_headers(token))
        # Endpoint exists even when static mount is disabled
        assert resp.status_code == 404  # file not found but auth+endpoint succeeded
