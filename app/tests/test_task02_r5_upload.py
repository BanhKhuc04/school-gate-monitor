"""
R5 — Upload ảnh: decode PIL + giới hạn + UUID + production URL.

Đặc tả R5:
- Decode ảnh thật qua PIL (không tin MIME/extension client).
- Bytes tối đa 5MB + pixel tối đa ~16M.
- Tên file UUID (không phải timestamp mili giây).
- URL production: /api/media/student-photos/... (auth), KHÔNG /media/...
  (production tắt static).
- Ảnh giả / không decode / quá lớn → 4xx rõ.
- Hai upload cùng thời điểm không trùng tên.
"""
from __future__ import annotations

import io
import os
import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _make_jpeg(width: int = 64, height: int = 64, color=(255, 128, 0)) -> bytes:
    """Tạo JPEG thật bằng PIL — bytes này decode được."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png(width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGBA", (width, height), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestUploadDecodeReal:
    """R5 — decode ảnh thật, không fake MIME."""

    def _admin(self, client):
        return _login(client, "admin").json()["access_token"]

    def test_valid_jpeg_upload_returns_uuid_filename(self, test_app, tmp_path, monkeypatch):
        """JPEG thật → trả photo_path với UUID hex 32 char + .jpg."""
        from app.api import admin as admin_mod
        # Patch student_photos_dir sang tmp để tránh ghi vào data/
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        jpeg_bytes = _make_jpeg()
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("avatar.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "photo_path" in body
        filename = body["photo_path"].split("/")[-1]
        # UUID hex 32 char + .jpg
        assert re.match(r"^[0-9a-f]{32}\.jpg$", filename), filename
        # URL production
        assert body["photo_url"].startswith("/api/media/student-photos/"), body
        # Kích thước ảnh được báo
        assert body["width"] == 64
        assert body["height"] == 64
        # File tồn tại trên disk
        assert (photos / filename).exists()

    def test_valid_png_upload_returns_uuid_png(self, test_app, tmp_path, monkeypatch):
        """PNG thật → UUID.png; format=PNG."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        png_bytes = _make_png()
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        filename = body["photo_path"].split("/")[-1]
        assert filename.endswith(".png"), filename
        assert body["format"] == "PNG"

    def test_fake_image_bytes_rejected(self, test_app, tmp_path, monkeypatch):
        """Bytes không phải ảnh dù MIME image/png → 400."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        fake = b"not-an-image-just-bytes"
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("fake.png", io.BytesIO(fake), "image/png")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400, r.text
        assert "không phải ảnh" in r.json()["detail"].lower() or "hợp" in r.json()["detail"].lower()

    def test_oversize_5mb_rejected(self, test_app, tmp_path, monkeypatch):
        """File >5MB (dù là ảnh thật) → 413."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        # Tạo ảnh >5MB (JPEG ~4MB với 3000x3000 + nhiễu)
        import random as _r
        rng = _r.Random(0)
        img = Image.new("RGB", (2400, 2400))
        pixels = img.load()
        for x in range(2400):
            for y in range(2400):
                pixels[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        big_bytes = buf.getvalue()
        # Skip nếu môi trường PIL không nén đủ 5MB; ép 5MB bằng bytes bất kỳ
        if len(big_bytes) <= 5 * 1024 * 1024:
            big_bytes = b"\xff\xd8\xff\xe0" + b"x" * (5 * 1024 * 1024 + 100)
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("big.jpg", io.BytesIO(big_bytes), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413, r.text

    def test_pixel_limit_rejected(self, test_app, tmp_path, monkeypatch):
        """Ảnh giải nén quá pixel → 413."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        # 100x100 pixel → 10000 pixel; tăng max_pixels = 100 để force 413
        from PIL import Image as _Image
        img = _Image.new("RGB", (50, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        valid_bytes = buf.getvalue()

        # Patch max_pixels của helper nội bộ qua monkeypatch attribute
        import app.api.admin as admin_mod
        original_helper = admin_mod._decode_and_save_image

        def _strict_helper(*a, **kw):
            kw.setdefault("max_pixels", 100)  # 50x50=2500 > 100
            return original_helper(*a, **kw)

        monkeypatch.setattr(admin_mod, "_decode_and_save_image", _strict_helper)
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("small.jpg", io.BytesIO(valid_bytes), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413, r.text

    def test_two_uploads_no_filename_collision(self, test_app, tmp_path, monkeypatch):
        """Hai upload cùng thời điểm → 2 file UUID khác nhau."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        seen = set()
        for _ in range(5):
            r = client.post(
                "/api/vehicles/upload-photo",
                files={"file": ("x.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200
            seen.add(r.json()["photo_path"])
        assert len(seen) == 5

    def test_filename_uses_uuid_not_timestamp(self, test_app, tmp_path, monkeypatch):
        """Tên file phải là UUID hex, KHÔNG phải timestamp."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("x.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        name = body["photo_path"].split("/")[-1]
        # UUID hex 32 char; không phải 13 số (timestamp ms)
        assert not re.match(r"^\d{13}\.jpg$", name), f"vẫn dùng timestamp: {name}"

    def test_production_url_no_static_media(self, test_app, tmp_path, monkeypatch):
        """Photo_url KHÔNG được /media/... (production tắt static)."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("x.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        # URL phải dùng API media (auth), KHÔNG dùng static /media/...
        assert body["photo_url"].startswith("/api/media/"), body
        # Từ chối đường dẫn static cũ (FastAPI StaticFiles mount tại /media/ hoặc /static/)
        url = body["photo_url"]
        assert not url.startswith("/media/"), f"vẫn dùng /media/ static: {url}"
        assert not url.startswith("/static/"), f"vẫn dùng /static/ static: {url}"

    def test_non_image_mime_rejected(self, test_app, tmp_path, monkeypatch):
        """Bytes không phải ảnh dù MIME image/* → 400 (F06: không tin MIME)."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        # Gửi bytes rác nhưng claim image/png → phải 400 vì PIL không decode được
        fake = b"not-an-image-just-bytes-12345"
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("fake.png", io.BytesIO(fake), "image/png")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400, r.text

    def test_svg_rejected(self, test_app, tmp_path, monkeypatch):
        """SVG có thể chứa script → KHÔNG cho phép (F06: từ chối fake image)."""
        from app.api import admin as admin_mod
        photos = (tmp_path / "photos")
        photos.mkdir()
        monkeypatch.setattr(admin_mod, "_STUDENT_PHOTOS_DIR", str(photos))

        client = TestClient(test_app)
        token = self._admin(client)
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        r = client.post(
            "/api/vehicles/upload-photo",
            files={"file": ("x.svg", io.BytesIO(svg), "image/svg+xml")},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 400 (MIME không phải image/* theo rule) HOẶC 400 (không decode PIL)
        assert r.status_code == 400, r.text


class TestPublicUploadR5:
    """R5 — public upload dùng helper chung, đảm bảo bảo mật như admin."""

    def test_public_register_disabled_blocks_upload(self, test_app):
        """PUBLIC_REGISTER_ENABLED=0 (mặc định) → 503, không decode ảnh."""
        client = TestClient(test_app)
        r = client.post(
            "/api/register/upload-photo",
            files={"file": ("x.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
        )
        assert r.status_code == 503

    def test_public_upload_when_enabled_uses_uuid(self, test_app, tmp_path, monkeypatch):
        """PUBLIC_REGISTER_ENABLED=1 → upload thật dùng UUID."""
        from app.api import register as reg_mod
        from app.config import PUBLIC_REGISTER_ENABLED as _cfg_flag
        photos = (tmp_path / "photos_public")
        photos.mkdir()
        monkeypatch.setattr(reg_mod, "_STUDENT_PHOTOS_DIR", str(photos))
        monkeypatch.setattr(reg_mod, "PUBLIC_REGISTER_ENABLED", True)

        client = TestClient(test_app)
        r = client.post(
            "/api/register/upload-photo",
            files={"file": ("x.jpg", io.BytesIO(_make_jpeg()), "image/jpeg")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        name = body["photo_path"].split("/")[-1]
        assert re.match(r"^[0-9a-f]{32}\.jpg$", name), name
        # URL production path
        assert body["photo_url"].startswith("/api/media/student-photos/"), body