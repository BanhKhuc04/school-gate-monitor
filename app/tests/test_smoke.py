"""
Smoke test — verifies the pytest harness works end-to-end.
"""
import pytest


def test_httpx_available():
    """httpx is importable."""
    import httpx
    assert httpx.__version__


def test_pytest_available():
    """pytest is importable."""
    import pytest as p
    assert hasattr(p, "__version__")


def test_auth_login_ok(client):
    """Admin can login with correct credentials."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "test123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"


def test_auth_login_wrong_password(client):
    """Wrong password returns 401."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_auth_me_authenticated(client):
    """GET /api/auth/me returns user info with valid token."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/auth/me", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["role"] == "admin"


def test_auth_me_unauthenticated(client):
    """GET /api/auth/me without token returns 401."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_seed_default_users_only_when_empty(test_app):
    """Máy cài mới (bảng users trống) phải có tài khoản admin để đăng nhập;
    DB đã có user thì không được tạo thêm/đè gì."""
    import app.db as db
    from app.auth import verify_password
    # test_app đã seed sẵn user test → không tạo gì
    assert db.seed_default_users_if_empty() == []

    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM users").fetchall()
        saved = [dict(r) for r in rows]
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()
    try:
        assert db.seed_default_users_if_empty() == ["admin", "security", "management"]
        admin = db.get_user_by_username("admin")
        assert admin["role"] == "admin"
        assert verify_password("admin123", admin["password_hash"])
    finally:
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM users")
            cols = list(saved[0].keys())
            conn.executemany(
                f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [tuple(r[c] for c in cols) for r in saved],
            )
            conn.commit()
        finally:
            conn.close()
