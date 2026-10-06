"""
D6.1: Auth security tests — JWT secret env, cookie session, CORS.
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import os


class TestJWTSecretFromEnv:
    @pytest.fixture(autouse=True)
    def restore_config(self):
        # reload(config) mutates the shared module even after env mocks unwind.
        # Keep paths/secrets from escaping this test class into later modules.
        from app import config
        original = vars(config).copy()
        yield
        vars(config).clear()
        vars(config).update(original)

    """JWT_SECRET_KEY phải đọc từ môi trường, không hardcode."""

    def test_dev_mode_uses_ephemeral_key_without_env(self):
        """Dev: không đặt JWT_SECRET_KEY → dùng key tạm, server vẫn chạy."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
                # Patch at module level before import
                import importlib
                import app.config as cfg
                # config.py tự load .env thật trên đĩa (xem load_dotenv trong
                # config.py) — patch no-op để env giả lập ở trên không bị file
                # .env thật (có JWT_SECRET_KEY) ghi đè, giữ test hermetic.
                with patch("dotenv.load_dotenv"):
                    importlib.reload(cfg)
                assert cfg.JWT_SECRET_KEY is not None
                assert len(cfg.JWT_SECRET_KEY) == 64  # 32 bytes hex = 64 chars
                assert cfg._PRODUCTION is False

    def test_production_mode_requires_jwt_secret(self):
        """Production: không đặt JWT_SECRET_KEY → lỗi khi import config."""
        import importlib
        import app.config as cfg

        # Simulate production without secret
        env = {"ENVIRONMENT": "production"}
        with patch.dict(os.environ, env, clear=True):
            with patch("dotenv.load_dotenv"):
                with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
                    importlib.reload(cfg)

    def test_production_mode_accepts_env_secret(self):
        """Production: đặt JWT_SECRET_KEY → dùng đúng giá trị đó."""
        import importlib
        import app.config as cfg

        env = {"ENVIRONMENT": "production", "JWT_SECRET_KEY": "test-secret-32-chars-exactly-here-123456"}
        with patch.dict(os.environ, env, clear=True):
            with patch("dotenv.load_dotenv"):
                importlib.reload(cfg)
            assert cfg.JWT_SECRET_KEY == "test-secret-32-chars-exactly-here-123456"
            assert cfg._PRODUCTION is True

    def test_cookie_flags_dev(self):
        """Dev: cookie không bật Secure (HTTP OK)."""
        import importlib
        import app.config as cfg
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            with patch("dotenv.load_dotenv"):
                importlib.reload(cfg)
            assert cfg.COOKIE_SECURE is False
            assert cfg.COOKIE_SAMESITE == "lax"


class TestLoginReturnsCookie:
    """POST /api/auth/login trả HttpOnly cookie ngoài body."""

    def test_login_returns_session_cookie(self, test_app):
        """Login response có Set-Cookie header với gate_session."""
        from app.tests.conftest import ROLE_PASSWORD
        client = TestClient(test_app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # Cookie phải được set
        set_cookie = resp.headers.get("set-cookie", "")
        assert "gate_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        # SameSite case varies by framework version — check value exists, case-insensitive
        assert "samesite=" in set_cookie.lower()
        # Cookie không có Secure trong dev mode
        # (Secure chỉ bật khi ENVIRONMENT=production)

    def test_login_cookie_value_equals_body_token(self, test_app):
        """Giá trị cookie = giá trị access_token trong body."""
        from app.tests.conftest import ROLE_PASSWORD
        client = TestClient(test_app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
        assert resp.status_code == 200
        data = resp.json()
        token = data["access_token"]
        set_cookie = resp.headers.get("set-cookie", "")
        # Cookie value is URL-encoded; extract raw part
        cookie_part = set_cookie.split("gate_session=")[1].split(";")[0]
        # URL-decode %3A -> :  (base64 JWT contains only alphanumeric + _ - so no encoding needed)
        assert cookie_part == token

    def test_login_invalid_credentials_no_cookie(self, test_app):
        """Sai password → không set cookie."""
        client = TestClient(test_app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401
        assert "gate_session" not in resp.headers.get("set-cookie", "")


class TestMeEndpoint:
    """GET /api/auth/me hoạt động với cả Bearer và cookie."""

    def test_me_with_bearer(self, test_app):
        """Bearer header vẫn hoạt động (backward compat)."""
        from app.tests.conftest import ROLE_PASSWORD
        client = TestClient(test_app)
        login = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
        token = login.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["username"] == "admin"

    def test_me_with_cookie(self, test_app):
        """Session cookie hoạt động khi không có Bearer header."""
        from app.tests.conftest import ROLE_PASSWORD
        client = TestClient(test_app)
        login = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
        token = login.json()["access_token"]
        # Extract cookie from response
        cookies = login.cookies
        me = client.get("/api/auth/me", cookies=cookies)
        assert me.status_code == 200
        assert me.json()["username"] == "admin"

    def test_me_no_auth_401(self, test_app):
        """Không có Bearer hay cookie → 401."""
        client = TestClient(test_app)
        me = client.get("/api/auth/me")
        assert me.status_code == 401


class TestLogout:
    """POST /api/auth/logout xóa session cookie."""

    def test_logout_clears_cookie(self, test_app):
        """Logout trả Delete-Cookie cho gate_session."""
        client = TestClient(test_app)
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        cookies = login.cookies
        logout = client.post("/api/auth/logout", cookies=cookies)
        assert logout.status_code == 200
        set_cookie = logout.headers.get("set-cookie", "")
        assert "gate_session=" in set_cookie
        # Max-Age=0 means delete
        assert "Max-Age=0" in set_cookie

    def test_me_after_logout_still_works_with_bearer(self, test_app):
        """Logout chỉ xóa cookie, không vô hiệu token — Bearer vẫn hoạt động."""
        from app.tests.conftest import ROLE_PASSWORD
        client = TestClient(test_app)
        login = client.post("/api/auth/login", json={"username": "admin", "password": ROLE_PASSWORD})
        token = login.json()["access_token"]
        cookies = login.cookies

        # Logout xóa cookie
        client.post("/api/auth/logout", cookies=cookies)

        # Nhưng Bearer vẫn còn hiệu lực (token không bị revoke)
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["username"] == "admin"
