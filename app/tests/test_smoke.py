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
    from app.tests.conftest import ROLE_PASSWORD
    resp = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
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
