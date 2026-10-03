"""
T2.3 — Hồ sơ xe/học sinh đầy đủ round-trip + GET detail + history pagination.

Đặc tả T2.3:
- POST/PUT lưu đủ plate/name/class/student_id/dob/phone/photo_path.
- GET /api/vehicles/{id} với scope phù hợp (admin/management xem full,
  teacher chỉ lớp mình).
- Trùng biển sau chuẩn hoá → 409 (không phải 500).
- History có limit 1..200, offset >= 0, total đúng.
- Frontend có thể gọi endpoint; (FE test riêng dùng browser test).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestVehicleRoundTrip:
    """POST/PUT lưu tất cả field mở rộng, GET trả đủ."""

    def test_post_persists_all_fields(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.post(
            "/api/vehicles",
            json={
                "plate_number": "50C12345",
                "student_name": "Nguyễn Văn A",
                "student_class": "10A1",
                "student_id": "HS2025999",
                "dob": "2010-05-15",
                "phone": "0912345678",
                "photo_path": "data/student_photos/test.jpg",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["plate_number"] == "50C12345"
        assert created["student_id"] == "HS2025999"
        assert created["dob"] == "2010-05-15"
        assert created["phone"] == "0912345678"
        assert created["photo_path"] == "data/student_photos/test.jpg"
        vehicle_id = created["id"]

        # GET detail
        r = client.get(
            f"/api/vehicles/{vehicle_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["plate_number"] == "50C12345"
        assert data["student_id"] == "HS2025999"
        assert data["dob"] == "2010-05-15"
        assert data["phone"] == "0912345678"

    def test_put_updates_all_fields(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.post(
            "/api/vehicles",
            json={
                "plate_number": "50C22222",
                "student_name": "Trần Văn B",
                "student_class": "10A1",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        vid = r.json()["id"]
        # PUT cập nhật các trường mở rộng
        r = client.put(
            f"/api/vehicles/{vid}",
            json={
                "plate_number": "50C22222",
                "student_name": "Trần Văn B",
                "student_class": "10A1",
                "student_id": "HS2025888",
                "dob": "2011-03-10",
                "phone": "0987654321",
                "photo_path": "data/student_photos/new.jpg",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["student_id"] == "HS2025888"
        assert updated["dob"] == "2011-03-10"
        assert updated["phone"] == "0987654321"
        assert updated["photo_path"] == "data/student_photos/new.jpg"

    def test_duplicate_plate_returns_409(self, test_app):
        """Trùng biển (sau normalize) → 409, không 500."""
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r1 = client.post(
            "/api/vehicles",
            json={"plate_number": "50D11111", "student_name": "A", "student_class": "10A1"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r1.status_code == 201
        r2 = client.post(
            "/api/vehicles",
            json={"plate_number": "50-D1 1111", "student_name": "B", "student_class": "10A1"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Sau normalize cả 2 đều thành 50D11111 → 409
        assert r2.status_code == 409, r2.text

    def test_teacher_cannot_view_other_class_vehicle(self, test_app):
        """Teacher thiếu lớp matching → 404 (không lộ tồn tại)."""
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.post(
            "/api/vehicles",
            json={"plate_number": "60E11111", "student_name": "Z", "student_class": "10A2"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        vid = r.json()["id"]
        t_token = _login(client, "teacher").json()["access_token"]
        r = client.get(
            f"/api/vehicles/{vid}",
            headers={"Authorization": f"Bearer {t_token}"},
        )
        assert r.status_code in (403, 404)


class TestVehicleViolationsHistoryPagination:
    """GET /api/vehicles/{id}/violations — limit/offset phù hợp, total đúng."""

    def _seed(self, client, plate, cls):
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.post(
            "/api/vehicles",
            json={"plate_number": plate, "student_name": f"X {plate}", "student_class": cls},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        return r.json()["id"]

    def test_history_pagination_limit_offset(self, test_app):
        client = TestClient(test_app)
        vid = self._seed(client, "50F11111", "10A1")
        # Tạo 5 vi phạm giả
        from app.db import add_violation_event
        for i in range(5):
            add_violation_event(
                timestamp=f"2026-10-0{i+1}T10:00:00",
                plate_read="50F11111", plate_matched="50F11111",
                helmet_status="no_helmet", violation_type="NO_HELMET",
                snapshot_path=f"snapshots/test_{i}.jpg",
            )
        admin_token = _login(client, "admin").json()["access_token"]
        # limit=2
        r = client.get(
            f"/api/vehicles/{vid}/violations?limit=2&offset=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(items) == 2
        # offset=2 → 2 tiếp theo
        r = client.get(
            f"/api/vehicles/{vid}/violations?limit=2&offset=2",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(items) == 2

    def test_history_includes_violations_for_vehicle(self, test_app):
        client = TestClient(test_app)
        vid = self._seed(client, "50F22222", "10A1")
        from app.db import add_violation_event
        for i in range(3):
            add_violation_event(
                timestamp=f"2026-09-0{i+1}T10:00:00",
                plate_read="50F22222", plate_matched="50F22222",
                helmet_status="no_helmet", violation_type="NO_HELMET",
            )
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.get(
            f"/api/vehicles/{vid}/violations",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        # Có thể trả list hoặc dict có items; cả 2 đều OK
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(items) == 3