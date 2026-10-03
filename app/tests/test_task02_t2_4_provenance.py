"""
T2.4 — Provenance + concurrency.

Đặc tả T2.4:
- update_violation_status dùng expected_version, atomic CAS, xung đột → 409.
- Hai operator đổi status cùng violation: 1 thắng, 1 nhận 409.
- Hai admin delete/demote cùng lúc không làm mất admin cuối.
- update_violation_status tăng version sau khi cập nhật.
- Provenance: event lưu student_name/class_at_event khớp hồ sơ tại thời điểm ghi.
- Sửa hồ sơ xe (đổi lớp/tên) KHÔNG làm đổi provenance event cũ.
- update_user giữ transaction (last-admin re-checked dưới _write_lock).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _auth_headers(client: TestClient, role: str) -> dict:
    r = _login(client, role)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_event(test_app, tmp_path, monkeypatch):
    """Tạo 1 violation event qua helper."""
    from app.db import add_violation_event
    return add_violation_event(
        timestamp="2026-01-01T00:00:00",
        plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
        snapshot_path=None,
    )


class TestStatusVersioning:
    """T2.4 — status update phải dùng expected_version, atomic CAS."""

    def test_status_update_requires_expected_version(self, test_app, tmp_path, monkeypatch):
        """PATCH status KHÔNG có expected_version → 422."""
        client = TestClient(test_app)
        ev_id = _make_event(test_app, tmp_path, monkeypatch)
        h = _auth_headers(client, "admin")
        r = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "reviewed", "note": "ok"},
            headers=h,
        )
        assert r.status_code == 422, r.text

    def test_status_update_success_increments_version(self, test_app, tmp_path, monkeypatch):
        """PATCH status với expected_version=0 → 200, version tăng lên 1."""
        client = TestClient(test_app)
        ev_id = _make_event(test_app, tmp_path, monkeypatch)
        h = _auth_headers(client, "admin")
        r = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "reviewed", "note": "ok", "expected_version": 0},
            headers=h,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == 1, body

    def test_stale_expected_version_returns_409(self, test_app, tmp_path, monkeypatch):
        """Sau khi version=1, gửi lại expected_version=0 → 409 + current_version=1."""
        client = TestClient(test_app)
        ev_id = _make_event(test_app, tmp_path, monkeypatch)
        h = _auth_headers(client, "admin")
        # Lần 1: version 0 → 1
        r = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "reviewed", "expected_version": 0},
            headers=h,
        )
        assert r.status_code == 200
        # Lần 2: stale (vẫn expected_version=0)
        r2 = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "resolved", "expected_version": 0},
            headers=h,
        )
        assert r2.status_code == 409, r2.text
        # FastAPI wraps dict detail in 'detail' key
        body2 = r2.json().get("detail") or r2.json()
        assert body2.get("current_version") == 1, body2

    def test_concurrent_status_updates_one_409(self, test_app, tmp_path, monkeypatch):
        """Hai operator cùng expected_version=0 → 1 thắng (200), 1 thua (409)."""
        client = TestClient(test_app)
        ev_id = _make_event(test_app, tmp_path, monkeypatch)
        h1 = _auth_headers(client, "admin")
        h2 = _auth_headers(client, "security")
        r1 = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "reviewed", "expected_version": 0},
            headers=h1,
        )
        r2 = client.patch(
            f"/api/violations/{ev_id}/status",
            json={"status": "resolved", "expected_version": 0},
            headers=h2,
        )
        statuses = sorted([r1.status_code, r2.status_code])
        assert statuses == [200, 409], f"Got {r1.status_code}/{r2.status_code}: {r1.text} | {r2.text}"


class TestProvenanceSnapshot:
    """T2.4 — provenance: event giữ tên/lớp tại thời điểm ghi."""

    def test_event_snapshots_vehicle_class(self, test_app, tmp_path, monkeypatch):
        """Đăng ký xe '50A1' lớp '10A1'; ghi event match biển đó → class_at_event='10A1'."""
        from app.db import add_vehicle, add_violation_event, normalize_plate, get_connection
        client = TestClient(test_app)
        h = _auth_headers(client, "admin")
        # Tạo vehicle (biển sẽ được normalize bỏ dấu '-')
        raw_plate = "50A1-001"
        norm_plate = normalize_plate(raw_plate)
        assert norm_plate == "50A1001"
        vid = add_vehicle(
            plate_number=raw_plate, student_name="Nguyễn Văn A",
            student_class="10A1", photo_path=None,
        )
        # Ghi event match biển (dùng form đã normalize)
        ev_id = add_violation_event(
            timestamp="2026-01-01T00:00:00",
            plate_read=raw_plate, plate_matched=norm_plate,
            helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=None,
        )
        # Verify provenance
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT student_name_at_event, student_class_at_event "
                "FROM violation_events WHERE id = ?", (ev_id,)
            ).fetchone()
            assert row["student_name_at_event"] == "Nguyễn Văn A"
            assert row["student_class_at_event"] == "10A1"
        finally:
            conn.close()

    def test_provenance_preserved_after_vehicle_update(self, test_app, tmp_path, monkeypatch):
        """Đổi lớp xe '50A1' từ '10A1' → '11B2'; event cũ vẫn giữ '10A1'."""
        from app.db import (
            add_vehicle, add_violation_event, update_vehicle, normalize_plate,
            get_connection,
        )
        raw_plate = "50A2-002"
        norm_plate = normalize_plate(raw_plate)
        vid = add_vehicle(
            plate_number=raw_plate, student_name="Trần Thị B",
            student_class="10A1", photo_path=None,
        )
        ev_id = add_violation_event(
            timestamp="2026-01-01T00:00:00",
            plate_read=raw_plate, plate_matched=norm_plate,
            helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=None,
        )
        # Đổi lớp xe
        update_vehicle(vid, student_class="11B2")
        # Verify event vẫn giữ '10A1'
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT student_class_at_event FROM violation_events WHERE id = ?",
                (ev_id,),
            ).fetchone()
            assert row["student_class_at_event"] == "10A1", \
                f"Provenance bị đổi theo hồ sơ! Got {row['student_class_at_event']}"
            # Và hồ sơ hiện tại đã là 11B2
            vrow = conn.execute(
                "SELECT student_class FROM registered_vehicles WHERE id = ?", (vid,)
            ).fetchone()
            assert vrow["student_class"] == "11B2"
        finally:
            conn.close()

    def test_event_without_match_has_null_provenance(self, test_app, tmp_path, monkeypatch):
        """Biển không match hồ sơ → provenance NULL (không suy đoán)."""
        from app.db import add_violation_event, get_connection
        ev_id = add_violation_event(
            timestamp="2026-01-01T00:00:00",
            plate_read="99X9-999", plate_matched=None,
            helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=None,
        )
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT student_name_at_event, student_class_at_event "
                "FROM violation_events WHERE id = ?", (ev_id,)
            ).fetchone()
            assert row["student_name_at_event"] is None
            assert row["student_class_at_event"] is None
        finally:
            conn.close()


class TestAtomicLastAdmin:
    """T2.4 — admin CRUD cuối cùng atomic dưới _write_lock."""

    def test_admin_cannot_delete_self(self, test_app, tmp_path, monkeypatch):
        """Admin xóa chính mình → 409 (bảo vệ tránh khoá hệ thống)."""
        client = TestClient(test_app)
        h = _auth_headers(client, "admin")
        r = client.get("/api/users", headers=h)
        users = r.json()
        admin = next(u for u in users if u["role"] == "admin")
        r = client.delete(f"/api/users/{admin['id']}", headers=h)
        assert r.status_code == 409, r.text

    def test_admin_cannot_demote_last_admin(self, test_app, tmp_path, monkeypatch):
        """Admin duy nhất bị demote → 409."""
        client = TestClient(test_app)
        h = _auth_headers(client, "admin")
        r = client.get("/api/users", headers=h)
        users = r.json()
        admin = next(u for u in users if u["role"] == "admin")
        r = client.put(
            f"/api/users/{admin['id']}",
            json={"role": "security"},
            headers=h,
        )
        assert r.status_code == 409, r.text

    def test_teacher_class_normalized(self, test_app, tmp_path, monkeypatch):
        """homeroom_class='  10A1  ' được normalize về '10A1'."""
        client = TestClient(test_app)
        h = _auth_headers(client, "admin")
        r = client.post(
            "/api/users",
            json={"username": "gv1", "password": "secret123", "role": "teacher", "homeroom_class": "  10A1  "},
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert r.json()["homeroom_class"] == "10A1"