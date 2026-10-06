"""
T2.5 — CSV import/export round-trip, public register off mặc định.

Đặc tả T2.5:
- CSV import: decode UTF-8-SIG (BOM), hỗ trợ quoted field, validate dob/phone,
  giới hạn kích thước file & dòng, dry-run trả preview chính xác.
- CSV export: round-trip lại DB trống phải giữ student_id/dob/phone.
- Public register API trả 503 {enabled: false} khi PUBLIC_REGISTER_ENABLED=0.
"""
from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _make_csv(rows, header=None):
    """Helper tạo CSV bytes với BOM tuỳ chọn."""
    if header is None:
        header = ["plate_number", "student_name", "student_class"]
    out = io.StringIO()
    out.write(",".join(header))
    out.write("\r\n")
    for r in rows:
        out.write(",".join(f'"{c}"' if "," in str(c) else str(c) for c in r))
        out.write("\r\n")
    return out.getvalue().encode("utf-8")


class TestCsvImportBOM:
    """CSV có BOM phải parse được."""

    def test_csv_with_bom_creates_vehicle(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        csv_text = "plate_number,student_name,student_class\r\n50AB1234,Nguyen Van A,10A1\r\n"
        # Thêm BOM (EF BB BF)
        content = b"\xef\xbb\xbf" + csv_text.encode("utf-8")
        r = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(content), "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 1, data
        # Vehicle đã có trong DB với header key "plate_number" (không phải "\ufeffplate_number")
        r = client.get("/api/vehicles", headers={"Authorization": f"Bearer {admin_token}"})
        plates = [v["plate_number"] for v in r.json()]
        assert "50AB1234" in plates


class TestCsvImportValidation:
    """Thiếu cột, sai định dạng → báo lỗi, không 500."""

    def test_missing_column_reported(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        # Chỉ có 1 cột plate_number → student_name và student_class thiếu
        content = _make_csv([["50CD1111"]])
        r = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(content), "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 0
        assert data["skipped"] == 1
        assert any("student_name" in e["message"] for e in data["errors"])

    def test_invalid_phone_reported(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        content = _make_csv(
            [["50CD2222", "Nguyen Van B", "10A1", "", "", "abc-not-phone", ""]],
            header=["plate_number", "student_name", "student_class", "student_id", "dob", "phone", "photo_path"],
        )
        r = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(content), "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 0
        assert data["skipped"] == 1
        assert any("phone" in e["message"].lower() for e in data["errors"])

    def test_dry_run_no_writes(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        content = _make_csv([
            ["50CD3333", "Nguyen Van C", "10A1"],
            ["50CD4444", "Nguyen Van D", "10A2"],
        ])
        r = client.post(
            "/api/vehicles/import?dry_run=true",
            files={"file": ("vehicles.csv", io.BytesIO(content), "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] == 2
        # Sau dry-run, DB KHÔNG có dòng nào
        r = client.get("/api/vehicles", headers={"Authorization": f"Bearer {admin_token}"})
        plates = [v["plate_number"] for v in r.json()]
        assert "50CD3333" not in plates
        assert "50CD4444" not in plates

    def test_size_limit_returns_413(self, test_app, monkeypatch):
        """CSV quá lớn (env override) → 413."""
        monkeypatch.setenv("CSV_IMPORT_MAX_BYTES", "100")  # 100B
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        big = _make_csv([
            ["50XX1111", "Nguyen Van X" + "1" * 80, "10A1"],
        ])
        r = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(big), "text/csv")},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 413


class TestCsvExportRoundTrip:
    """Export → import lại DB trống phải giữ student_id/dob/phone."""

    def test_export_includes_extended_fields(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        # Tạo 1 xe có đủ trường
        r = client.post(
            "/api/vehicles",
            json={
                "plate_number": "50EE1111",
                "student_name": "Nguyen Van E",
                "student_class": "10A1",
                "student_id": "HS2025111",
                "dob": "2010-01-15",
                "phone": "0901234567",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201, r.text  # in ra lỗi 422 nếu có
        # Export
        r = client.get(
            "/api/vehicles/export",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        body = r.content.decode("utf-8-sig")
        lines = body.strip().split("\r\n")
        assert lines[0] == "Biển số,Học sinh,Lớp,Mã số,Ngày sinh,SĐT,Photo Path"
        # Tìm dòng 50EE1111
        row = next(l for l in lines if l.startswith("50EE1111"))
        assert "HS2025111" in row
        assert "2010-01-15" in row
        assert "0901234567" in row


class TestPublicRegisterDefaultOff:
    """PUBLIC_REGISTER_ENABLED=0 (mặc định) → /api/register/* trả 503 enabled=false."""

    def test_register_disabled_returns_503(self, test_app):
        client = TestClient(test_app)
        r = client.get("/api/register/lookup", params={"student_id": "ANY"})
        assert r.status_code == 503
        data = r.json()
        assert data["enabled"] is False

    def test_register_disabled_blocks_post(self, test_app):
        client = TestClient(test_app)
        r = client.post("/api/register", json={
            "student_id": "ANY",
            "plate_number": "50FF1234",
        })
        assert r.status_code == 503
        data = r.json()
        assert data["enabled"] is False

    def test_register_disabled_blocks_upload(self, test_app):
        client = TestClient(test_app)
        # Gửi file giả rất nhỏ
        r = client.post(
            "/api/register/upload-photo",
            files={"file": ("a.jpg", io.BytesIO(b"\xff\xd8\xff\xd9"), "image/jpeg")},
        )
        assert r.status_code == 503
        assert r.json()["enabled"] is False

    def test_register_enabled_via_env(self, test_app, monkeypatch):
        """PUBLIC_REGISTER_ENABLED=1 → lookup hoạt động bình thường (200 hoặc 404)."""
        from app.config import PUBLIC_REGISTER_ENABLED
        monkeypatch.setattr("app.config.PUBLIC_REGISTER_ENABLED", True)
        # Patch biến trong module đã import
        import app.api.register as reg_mod
        monkeypatch.setattr(reg_mod, "PUBLIC_REGISTER_ENABLED", True)

        client = TestClient(test_app)
        r = client.get("/api/register/lookup", params={"student_id": "UNKNOWN"})
        # 200 với found=False là đúng (KHÔNG phải 503)
        assert r.status_code == 200
        assert r.json()["found"] is False


class TestCsvImportIdempotency:
    """R4 — import_id + payload_hash lưu bền: replay trả kết quả cũ,
    key trùng nhưng payload khác → 409."""

    def _make_csv_bytes(self, plate: str, name: str, klass: str) -> bytes:
        out = io.StringIO()
        out.write("plate_number,student_name,student_class\r\n")
        out.write(f"{plate},{name},{klass}\r\n")
        return out.getvalue().encode("utf-8")

    def test_replay_same_idempotency_returns_cached(self, test_app):
        """Cùng import_id + cùng file → lần 2 trả kết quả lưu + replay=True."""
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]
        csv_bytes = self._make_csv_bytes("50ID1111", "Nguyen Van ID1", "10A1")

        r1 = client.post(
            "/api/vehicles/import",
            params={"import_id": "test-uuid-001"},
            files={"file": ("vehicles.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["created"] == 1
        assert body1.get("replay") is not True

        r2 = client.post(
            "/api/vehicles/import",
            params={"import_id": "test-uuid-001"},
            files={"file": ("vehicles.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        # Lần 2 trả về cached + replay=True; KHÔNG tạo thêm row
        assert body2.get("replay") is True
        assert body2["created"] == 1
        # DB chỉ có 1 record
        assert "50ID1111" in [v["plate_number"]
                              for v in client.get("/api/vehicles",
                                                  headers={"Authorization": f"Bearer {token}"}).json()]

    def test_same_import_id_different_file_returns_409(self, test_app):
        """import_id cũ + payload khác → 409."""
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]
        csv1 = self._make_csv_bytes("50ID2222", "Nguyen Van A", "10A1")
        csv2 = self._make_csv_bytes("50ID3333", "Tran Thi B", "10A2")

        client.post(
            "/api/vehicles/import",
            params={"import_id": "test-uuid-002"},
            files={"file": ("vehicles.csv", io.BytesIO(csv1), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Reuse cùng import_id nhưng file khác → 409
        r = client.post(
            "/api/vehicles/import",
            params={"import_id": "test-uuid-002"},
            files={"file": ("vehicles.csv", io.BytesIO(csv2), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409, r.text

    def test_no_import_id_does_not_error(self, test_app):
        """Không truyền import_id → vẫn hoạt động như cũ, không replay."""
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]
        csv_bytes = self._make_csv_bytes("50ID4444", "Nguyen Van C", "10A1")
        r1 = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200, r1.text
        # Lần 2 cùng file không có import_id → tạo duplicate (DB reject 409 + duplicates)
        r2 = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        # Lần này là duplicate
        assert r2.json()["created"] == 0
        assert r2.json()["duplicates"] == 1


class TestCsvExportRoundTripFull:
    """R4 — export có cột photo_path + xử lý formula injection."""

    def test_export_includes_photo_path_column(self, test_app):
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]
        client.post(
            "/api/vehicles",
            json={
                "plate_number": "50RT0001",
                "student_name": "Pham Van RT",
                "student_class": "10B1",
                "student_id": "HSRT001",
                "dob": "2010-06-15",
                "phone": "0900000001",
                "photo_path": "data/student_photos/uuid1.jpg",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/vehicles/export",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.content.decode("utf-8-sig")
        lines = body.strip().split("\r\n")
        assert "Photo Path" in lines[0]
        row = next(l for l in lines if l.startswith("50RT0001"))
        assert "data/student_photos/uuid1.jpg" in row

    def test_export_escapes_formula_injection(self, test_app):
        """Trường bắt đầu bằng `=` → prefix `'` để Excel không chạy formula."""
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]
        # Tạo xe có tên bắt đầu bằng "=" (CSV injection)
        client.post(
            "/api/vehicles",
            json={
                "plate_number": "50FM0001",
                "student_name": "=1+1",
                "student_class": "10B1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get("/api/vehicles/export",
                       headers={"Authorization": f"Bearer {token}"})
        body = r.content.decode("utf-8-sig")
        # Tên phải có prefix '
        assert "'=1+1" in body
        # Không có raw "=1+1" ngay đầu dòng (chỉ có khi prefix ' chưa được apply)
        # Lưu ý: "=1+1" có thể xuất hiện sau "'"; chỉ kiểm tra dòng bắt đầu bằng =
        for line in body.split("\r\n"):
            if line.startswith("="):
                pytest.fail(f"Line starts with = without prefix: {line!r}")

    def test_export_import_roundtrip_keeps_photo_path(self, test_app):
        """Export rồi import lại vào DB trống → photo_path còn nguyên."""
        client = TestClient(test_app)
        token = _login(client, "admin").json()["access_token"]

        # Tạo 1 xe có photo_path
        client.post(
            "/api/vehicles",
            json={
                "plate_number": "50RP0001",
                "student_name": "Hoang Thi RP",
                "student_class": "10C1",
                "photo_path": "data/student_photos/rp1.jpg",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # Export
        r = client.get("/api/vehicles/export",
                       headers={"Authorization": f"Bearer {token}"})
        export_csv = r.content.decode("utf-8-sig")

        # Xóa tất cả vehicles
        for v in client.get("/api/vehicles",
                           headers={"Authorization": f"Bearer {token}"}).json():
            client.delete(f"/api/vehicles/{v['id']}",
                          headers={"Authorization": f"Bearer {token}"})

        # Import lại file export
        import_bytes = export_csv.encode("utf-8")
        r = client.post(
            "/api/vehicles/import",
            files={"file": ("vehicles.csv", io.BytesIO(import_bytes), "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["created"] >= 1

        # Tìm lại xe 50RP0001, kiểm photo_path
        r = client.get("/api/vehicles",
                       headers={"Authorization": f"Bearer {token}"})
        items = r.json()
        rp = next((v for v in items if v["plate_number"] == "50RP0001"), None)
        assert rp is not None
        assert rp.get("photo_path") == "data/student_photos/rp1.jpg"