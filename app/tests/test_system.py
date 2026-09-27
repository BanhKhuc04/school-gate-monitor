"""
pytest tests for system health & cleanup API.
"""
import pytest


def test_health_requires_auth(client):
    """GET /api/system/health without token returns 401."""
    resp = client.get("/api/system/health")
    assert resp.status_code == 401


def test_health_requires_admin_or_management(client):
    """GET /api/system/health with security role returns 403."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "security"))
    assert resp.status_code == 403


def test_health_admin_ok(client):
    """GET /api/system/health with admin role returns 200 + correct shape."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline" in data
    assert "db_size_mb" in data
    assert "snapshot_count" in data
    assert "snapshot_size_mb" in data
    assert "violations_today" in data
    assert isinstance(data["db_size_mb"], (int, float))


def test_health_management_ok(client):
    """GET /api/system/health with management role also returns 200."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/health", headers=auth_headers(client, "management"))
    assert resp.status_code == 200


def test_cleanup_requires_admin(client):
    """POST /api/system/snapshots/cleanup with security role returns 403."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=90",
        headers=auth_headers(client, "security"),
    )
    assert resp.status_code == 403


def test_cleanup_admin_ok(client):
    """POST /api/system/snapshots/cleanup with admin role returns 200."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=90",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted_files" in data
    assert "updated_records" in data


def test_cleanup_invalid_days(client):
    """Cleanup with invalid older_than_days returns 422."""
    from app.tests.conftest import auth_headers
    resp = client.post(
        "/api/system/snapshots/cleanup?older_than_days=0",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 422
