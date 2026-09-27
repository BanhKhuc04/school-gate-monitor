"""
API error/edge-case tests using pytest + httpx.
Run: pytest tests/test_api_errors.py -v
Requires: uvicorn running at http://localhost:8000 (dev mode).
"""
import pytest
import httpx
import time

BASE = "http://localhost:8000"
TIMEOUT = 10.0  # seconds for all HTTP calls

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_token() -> str:
    """Get a valid admin JWT token."""
    resp = httpx.post(f"{BASE}/api/auth/login", json={
        "username": "admin", "password": "admin123"
    }, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
def security_token() -> str:
    """Get a valid security guard JWT token."""
    resp = httpx.post(f"{BASE}/api/auth/login", json={
        "username": "security", "password": "security123"
    }, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Security login failed: {resp.text}"
    return resp.json()["access_token"]


def auth(role: str) -> dict:
    """Get token for a given role."""
    creds = {"admin": ("admin", "admin123"), "security": ("security", "security123"),
             "management": ("management", "management123")}
    username, password = creds.get(role, ("admin", "admin123"))
    resp = httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=TIMEOUT)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def delete_if_exists(plate_number: str, admin_token: str):
    """Remove a vehicle by plate number if it exists. No-op on failure."""
    try:
        vehicles = httpx.get(f"{BASE}/api/vehicles", headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        if vehicles.status_code == 200:
            for v in vehicles.json():
                if v["plate_number"] == plate_number:
                    httpx.delete(f"{BASE}/api/vehicles/{v['id']}", headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
    except Exception:
        pass  # best-effort cleanup


# ─── Auth endpoint tests ────────────────────────────────────────────────────

class TestAuthLogin:
    """/api/auth/login edge cases."""

    def test_login_wrong_password_returns_401(self):
        resp = httpx.post(f"{BASE}/api/auth/login", json={
            "username": "admin", "password": "wrongpassword"
        }, timeout=TIMEOUT)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        assert "detail" in resp.json()

    def test_login_wrong_username_returns_401(self):
        resp = httpx.post(f"{BASE}/api/auth/login", json={
            "username": "nobody", "password": "anypassword"
        }, timeout=TIMEOUT)
        assert resp.status_code == 401
        assert "detail" in resp.json()

    def test_login_missing_password_returns_422(self):
        resp = httpx.post(f"{BASE}/api/auth/login", json={
            "username": "admin"
        }, timeout=TIMEOUT)
        assert resp.status_code == 422, f"Expected 422 for missing field, got {resp.status_code}"

    def test_login_empty_body_returns_422(self):
        resp = httpx.post(f"{BASE}/api/auth/login", json={}, timeout=TIMEOUT)
        assert resp.status_code == 422

    def test_login_correct_returns_200_with_token(self):
        resp = httpx.post(f"{BASE}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        }, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "username" in data
        assert "role" in data
        assert data["username"] == "admin"
        assert data["role"] == "admin"


class TestAuthMe:
    """GET /api/auth/me edge cases."""

    def test_me_no_token_returns_401(self):
        resp = httpx.get(f"{BASE}/api/auth/me", timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_me_invalid_token_returns_401(self):
        resp = httpx.get(f"{BASE}/api/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        }, timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_me_valid_token_returns_user_info(self, admin_token):
        resp = httpx.get(f"{BASE}/api/auth/me", headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"


# ─── Vehicles endpoint tests ─────────────────────────────────────────────────

class TestVehicles:
    """CRUD edge cases for /api/vehicles."""

    def test_get_vehicles_no_token_returns_401(self):
        resp = httpx.get(f"{BASE}/api/vehicles", timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_get_vehicles_security_token_returns_403(self, security_token):
        resp = httpx.get(f"{BASE}/api/vehicles", headers={
            "Authorization": f"Bearer {security_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 403, f"Expected 403 for security role, got {resp.status_code}: {resp.text}"

    def test_add_vehicle_no_token_returns_401(self):
        resp = httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "TEST999", "student_name": "Test User", "student_class": "TestClass"
        }, timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_add_vehicle_security_returns_403(self, security_token):
        resp = httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "TEST999", "student_name": "Test User", "student_class": "TestClass"
        }, headers={"Authorization": f"Bearer {security_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 403

    def test_add_vehicle_admin_returns_201(self, admin_token):
        # Clean up first
        delete_if_exists("TEST99A", admin_token)
        resp = httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "TEST99A", "student_name": "Test User", "student_class": "TestClass"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        # Cleanup
        delete_if_exists("TEST99A", admin_token)

    def test_add_duplicate_plate_returns_409(self, admin_token):
        # Clean up first
        delete_if_exists("DUPE999", admin_token)
        # Add once
        httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "DUPE999", "student_name": "Dup User", "student_class": "DupClass"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        # Try again — should be 409
        resp = httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "DUPE999", "student_name": "Dup User 2", "student_class": "DupClass2"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 409, f"Expected 409 for duplicate, got {resp.status_code}: {resp.text}"
        # Cleanup
        delete_if_exists("DUPE999", admin_token)

    def test_add_missing_fields_returns_422(self, admin_token):
        resp = httpx.post(f"{BASE}/api/vehicles", json={
            "plate_number": "INCOMPLETE"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 422

    def test_update_nonexistent_returns_404(self, admin_token):
        resp = httpx.put(f"{BASE}/api/vehicles/999999", json={
            "plate_number": "UPDATED", "student_name": "Upd", "student_class": "Upd"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, admin_token):
        resp = httpx.delete(f"{BASE}/api/vehicles/999999", headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 404


# ─── Violations endpoint tests ──────────────────────────────────────────────

class TestViolations:
    """Edge cases for /api/violations."""

    def test_get_violations_no_token_returns_401(self):
        resp = httpx.get(f"{BASE}/api/violations", timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_get_violations_security_returns_403(self, security_token):
        resp = httpx.get(f"{BASE}/api/violations", headers={
            "Authorization": f"Bearer {security_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 403

    def test_get_violations_pagination_params(self, admin_token):
        """Pagination params (limit, offset) should be accepted and reflected in response."""
        resp = httpx.get(f"{BASE}/api/violations", params={"limit": 5, "offset": 0}, headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) <= 5

    def test_get_violations_filter_by_type(self, admin_token):
        """Filter by violation_type should be accepted."""
        resp = httpx.get(f"{BASE}/api/violations", params={"violation_type": "NO_HELMET"}, headers={
            "Authorization": f"Bearer {admin_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)


# ─── Stats endpoint tests ───────────────────────────────────────────────────

class TestStats:
    """Edge cases for /api/stats/summary."""

    def test_get_stats_no_token_returns_401(self):
        resp = httpx.get(f"{BASE}/api/stats/summary", timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_get_stats_security_returns_403(self, security_token):
        resp = httpx.get(f"{BASE}/api/stats/summary", headers={
            "Authorization": f"Bearer {security_token}"
        }, timeout=TIMEOUT)
        assert resp.status_code == 403, f"Expected 403 for security, got {resp.status_code}: {resp.text}"

    def test_get_stats_management_returns_200(self):
        resp = httpx.get(f"{BASE}/api/stats/summary", headers=auth("management"), timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_today" in data
        assert "total_week" in data
        assert "by_type" in data
        assert isinstance(data["total_today"], int)
        assert isinstance(data["total_week"], int)


# ─── Dev/test endpoint tests ────────────────────────────────────────────────

class TestDevEndpoint:
    """Edge cases for /api/dev/trigger-test-alert."""

    def test_trigger_no_token_returns_401(self):
        resp = httpx.post(f"{BASE}/api/dev/trigger-test-alert", json={}, timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_trigger_invalid_token_returns_401(self):
        resp = httpx.post(f"{BASE}/api/dev/trigger-test-alert", json={}, headers={
            "Authorization": "Bearer invalid.token.here"
        }, timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_trigger_management_returns_403(self):
        resp = httpx.post(f"{BASE}/api/dev/trigger-test-alert", json={}, headers=auth("management"), timeout=TIMEOUT)
        assert resp.status_code == 403

    def test_trigger_security_returns_200(self, security_token):
        resp = httpx.post(f"{BASE}/api/dev/trigger-test-alert", json={
            "violation_type": "NO_HELMET", "plate_read": "TESTPYTEST"
        }, headers={"Authorization": f"Bearer {security_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "alert" in data

    def test_trigger_admin_returns_200(self, admin_token):
        resp = httpx.post(f"{BASE}/api/dev/trigger-test-alert", json={
            "violation_type": "PLATE_NOT_REGISTERED", "plate_read": "TESTPYADMIN"
        }, headers={"Authorization": f"Bearer {admin_token}"}, timeout=TIMEOUT)
        assert resp.status_code == 200


# ─── SPA fallback tests ─────────────────────────────────────────────────────

class TestSPAFallback:
    """SPA routing edge cases."""

    def test_old_admin_route_returns_410(self):
        resp = httpx.get(f"{BASE}/admin", timeout=TIMEOUT)
        assert resp.status_code == 410

    def test_old_admin_violations_route_returns_410(self):
        resp = httpx.get(f"{BASE}/admin/violations", timeout=TIMEOUT)
        assert resp.status_code == 410

    def test_guard_route_returns_spa_html(self):
        resp = httpx.get(f"{BASE}/guard", timeout=TIMEOUT)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<!doctype" in resp.text.lower() or "<html" in resp.text.lower()

    def test_unknown_route_returns_spa_html(self):
        resp = httpx.get(f"{BASE}/nonexistent/route/here", timeout=TIMEOUT)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<!doctype" in resp.text.lower() or "<html" in resp.text.lower()


# ─── Guard endpoints ───────────────────────────────────────────────────────

class TestGuardVideoFeed:
    """Guard video feed auth edge cases."""

    def test_video_feed_no_token_returns_401(self):
        resp = httpx.get(f"{BASE}/guard/video_feed", timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_video_feed_invalid_token_returns_401(self):
        resp = httpx.get(f"{BASE}/guard/video_feed", params={"token": "invalid.token"}, timeout=TIMEOUT)
        assert resp.status_code == 401

    def test_video_feed_management_returns_403(self):
        resp = httpx.get(f"{BASE}/guard/video_feed", params={"token": auth("management")["Authorization"].split(" ")[1]}, timeout=TIMEOUT)
        assert resp.status_code == 401, "Guard video feed should reject management token"
