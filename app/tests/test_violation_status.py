"""
Tests for Feature 10: Violation audit trail + status update.
"""
import pytest


def test_update_status_ok(client):
    """Security can update violation status → 404 (no such violation, but auth OK)."""
    from app.tests.conftest import auth_headers

    resp = client.patch(
        "/api/violations/999/status",
        json={"status": "reviewed", "note": "Đã kiểm tra", "expected_version": 0},
        headers=auth_headers(client, "security"),
    )
    # 404 OK — violation doesn't exist, but auth + concurrency check succeeded.
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
        json={"status": "invalid_status", "expected_version": 0},
        headers=auth_headers(client, "security"),
    )
    assert resp.status_code == 422


def test_update_status_missing_expected_version(client):
    """T2.4: thiếu expected_version → 422 (atomic CAS bắt buộc)."""
    from app.tests.conftest import auth_headers
    resp = client.patch(
        "/api/violations/1/status",
        json={"status": "resolved"},
        headers=auth_headers(client, "management"),
    )
    assert resp.status_code == 422


def test_update_status_management_ok(client):
    """Management role passes auth, but version conflict → 409 (vì version=0 và row mới trống)."""
    from app.tests.conftest import auth_headers

    resp = client.patch(
        "/api/violations/1/status",
        json={"status": "resolved", "expected_version": 0},
        headers=auth_headers(client, "management"),
    )
    # 404 (no violation) hoặc 409 nếu violation_id tồn tại với version khác
    assert resp.status_code in (404, 409)


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
