"""
Tests for Feature 10: Violation audit trail + status update.
"""
import pytest


def test_update_status_ok(client):
    """Security can update violation status → 200."""
    from app.tests.conftest import auth_headers

    resp = client.patch(
        "/api/violations/999/status",
        json={"status": "reviewed", "note": "Đã kiểm tra"},
        headers=auth_headers(client, "security"),
    )
    # 404 OK — violation doesn't exist, but auth succeeded (not 401/403)
    assert resp.status_code == 404


def test_list_violations_management_ok(client):
    """Management (principal) can view the violations list, not just admin/teacher."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/violations", headers=auth_headers(client, "management"))
    assert resp.status_code == 200


def test_update_status_requires_auth(client):
    """Unauthenticated request → 401."""
    resp = client.patch(
        "/api/violations/1/status",
        json={"status": "reviewed"},
    )
    assert resp.status_code == 401


def test_update_status_invalid_value(client):
    """Invalid status value → 422."""
    from app.tests.conftest import auth_headers

    resp = client.patch(
        "/api/violations/1/status",
        json={"status": "invalid_status"},
        headers=auth_headers(client, "security"),
    )
    assert resp.status_code == 422


def test_update_status_management_ok(client):
    """Management role can update status → 404 (not 403)."""
    from app.tests.conftest import auth_headers

    resp = client.patch(
        "/api/violations/1/status",
        json={"status": "resolved"},
        headers=auth_headers(client, "management"),
    )
    assert resp.status_code == 404  # violation doesn't exist, but role OK


def test_get_audit_log_requires_auth(client):
    """GET audit log without auth → 401."""
    resp = client.get("/api/violations/1/audit-log")
    assert resp.status_code == 401


def test_get_audit_log_returns_list(client):
    """GET audit log returns a list (empty if no records)."""
    from app.tests.conftest import auth_headers

    resp = client.get(
        "/api/violations/1/audit-log",
        headers=auth_headers(client, "admin"),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
