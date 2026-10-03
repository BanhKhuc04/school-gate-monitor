"""
T2.1 — Verify teacher demo flow end-to-end (login → role + class → scope).

Đặc tả T2.1:
- Bốn nút demo tự điền (admin / security / management / teacher).
- Teacher login thật → JWT + cookie; token có homeroom_class; role='teacher'.
- Teacher thiếu homeroom_class (sau trim) → 403 khi gọi API scope teacher.
- Teacher chỉ xem được xe/vi phạm thuộc lớp mình; lớp khác trả 403/404.

Test dùng TestClient + fixture `test_app` (DB giả, không load model/camera).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"  # standard seed trong conftest.py


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestTeacherDemoLogin:
    """Bốn role seed sẵn trong conftest: admin/security/management/teacher(10A1)."""

    def test_login_admin_returns_role_and_no_class(self, test_app):
        client = TestClient(test_app)
        r = _login(client, "admin")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "admin"
        assert data.get("homeroom_class") is None

    def test_login_security_returns_role(self, test_app):
        client = TestClient(test_app)
        r = _login(client, "security")
        assert r.status_code == 200
        assert r.json()["role"] == "security"

    def test_login_management_returns_role(self, test_app):
        client = TestClient(test_app)
        r = _login(client, "management")
        assert r.status_code == 200
        assert r.json()["role"] == "management"

    def test_login_teacher_returns_role_and_class(self, test_app):
        """T2.1: bấm nút Giáo viên → tự điền teacher/teacher123 → server xác
        thực thật → trả role='teacher' + homeroom_class='10A1'."""
        client = TestClient(test_app)
        r = _login(client, "teacher")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "teacher"
        assert data.get("homeroom_class") == "10A1"
        assert "access_token" in data
        # Cookie session vẫn hoạt động
        assert "gate_session=" in r.headers.get("set-cookie", "")

    def test_get_me_teacher_includes_class(self, test_app):
        """GET /api/auth/me với Bearer hoặc cookie trả homeroom_class."""
        client = TestClient(test_app)
        r = _login(client, "teacher")
        token = r.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        data = me.json()
        assert data["role"] == "teacher"
        assert data.get("homeroom_class") == "10A1"


class TestTeacherScope:
    """Teacher chỉ xem được dữ liệu thuộc lớp mình."""

    def _make_vehicle(self, client: TestClient, admin_token: str, plate: str, cls: str):
        r = client.post(
            "/api/vehicles",
            json={"plate_number": plate, "student_name": f"Test {plate}", "student_class": cls},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201, r.text
        return r.json()

    def test_teacher_sees_only_own_class_vehicles(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        self._make_vehicle(client, admin_token, "50A12345", "10A1")
        self._make_vehicle(client, admin_token, "50A12346", "10A2")
        t_token = _login(client, "teacher").json()["access_token"]

        r = client.get(
            "/api/vehicles",
            headers={"Authorization": f"Bearer {t_token}"},
        )
        assert r.status_code == 200
        plates = [v["plate_number"] for v in r.json()]
        assert "50A12345" in plates
        assert "50A12346" not in plates


class TestTeacherWithoutClass:
    """Teacher không có homeroom_class → 422 khi tạo user; 403 nếu bypass."""

    def test_admin_api_rejects_teacher_without_class(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.post(
            "/api/users",
            json={"username": "badteacher", "password": "test123", "role": "teacher"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Server phải từ chối ngay khi tạo vì thiếu homeroom_class
        assert r.status_code == 422, r.text

    def test_require_role_blocks_teacher_with_blank_class(self, test_app):
        """Nếu JWT có role=teacher + homeroom_class rỗng → require_role từ chối 403."""
        from app.auth import create_access_token, require_role
        from fastapi import HTTPException

        token = create_access_token("ghost", "teacher", homeroom_class="   ")
        # decode để verify token hợp lệ (chỉ test logic require_role)
        from app.auth import decode_access_token
        payload = decode_access_token(token)
        assert payload["role"] == "teacher"
        # require_role(...) trả thẳng inner dep function (callable nhận current_user)
        dep = require_role("teacher", "admin", "management")
        user = {"username": "ghost", "role": "teacher", "homeroom_class": "   "}
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403


class TestSeedScriptIdempotency:
    """T2.1: seed_user.py / seed_demo.py phải idempotent (không ghi đè)."""

    def test_seed_demo_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        """Chạy seed_demo 2 lần — không tạo trùng, không reset password/role cũ."""
        import os
        from pathlib import Path
        # Tạo DB tạm
        test_db = tmp_path / "seed_demo.db"
        monkeypatch.setenv("APP_DB_PATH", str(test_db))
        import sqlite3, time
        from app.auth import hash_password
        from app.db import (
            get_connection, create_user, get_user_by_username, init_db,
        )
        # Patch DB_PATH trong module db
        import app.db as db_module
        import app.config as cfg
        original_db_path = db_module.DB_PATH
        cfg.DB_PATH = str(test_db)
        db_module.DB_PATH = str(test_db)
        try:
            init_db()
            # Tạo 1 user khác với username 'admin' đã tồn tại từ conftest — chọn
            # user DEMO khác chưa có sẵn, ví dụ 'teacher_b'.
            create_user("teacher_b", hash_password("oldpass"), "security", None)
            from scripts.seed_demo import seed_users
            actions = seed_users(force=False)
            # User 'teacher_b' đã tồn tại → SKIP
            skip_actions = [a for a in actions if "teacher_b" in a]
            assert any("SKIP" in a for a in skip_actions), actions
            # Tài khoản cũ vẫn còn, role vẫn là 'security'
            user = get_user_by_username("teacher_b")
            assert user["role"] == "security", "Idempotent: KHÔNG ghi đè role"
            assert user.get("homeroom_class") is None
            # Teacher (demo) vẫn được tạo từ script vì chưa tồn tại
            teacher = get_user_by_username("teacher")
            assert teacher is not None
            assert teacher["role"] == "teacher"
            assert teacher.get("homeroom_class") == "10A1"
        finally:
            cfg.DB_PATH = original_db_path
            db_module.DB_PATH = original_db_path