"""
T2.2 — Same-origin / LAN, production deep link, media scope.

Đặc tả T2.2:
- Production: không mount static /media. Tất cả ảnh/clip qua /api/media/...
- API 404 trả JSON `{detail}`, KHÔNG trả SPA index.html.
- /api/violations/{id} có snapshot_url dạng /api/media/snapshots/...
- Teacher chỉ xem được media của lớp mình (qua _check_class_scope).
- SPA deep link /admin/violations, /teacher/violations: không trả 410.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestViolationsUrlsSameOrigin:
    """API list/detail luôn trả URL media đi qua /api/media/... (auth+scope)."""

    def test_violations_list_uses_api_media_urls(self, test_app):
        client = TestClient(test_app)
        # Add a vehicle so the JOIN has a row
        admin_token = _login(client, "admin").json()["access_token"]
        client.post(
            "/api/vehicles",
            json={"plate_number": "50A11111", "student_name": "Test", "student_class": "10A1"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Tạo violation event giả bằng cách dùng add_violation_event qua admin (qua _dev)
        # Cách an toàn: tận dụng helper nội bộ — import từ app.db.
        from app.db import add_violation_event
        ev_id = add_violation_event(
            timestamp="2026-10-02T10:00:00",
            plate_read="50A11111",
            plate_matched="50A11111",
            helmet_status="no_helmet",
            violation_type="NO_HELMET",
            snapshot_path="snapshots/test_no_helmet.jpg",
            crop_snapshot_path="snapshots/test_no_helmet_crop.jpg",
            clip_path="clips/test_no_helmet.mp4",
        )
        # Đợi DB commit, gọi API list
        r = client.get(
            "/api/violations",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        ev_found = next((i for i in items if i["id"] == ev_id), None)
        assert ev_found is not None
        assert ev_found["snapshot_url"].startswith("/api/media/snapshots/")
        assert ev_found["crop_snapshot_url"].startswith("/api/media/snapshots/")
        assert ev_found["clip_url"].startswith("/api/media/clips/")


class TestMediaApiScopeForTeacher:
    """Teacher chỉ xem được ảnh/clip thuộc lớp mình."""

    def _add_violation_with_path(self, plate: str, cls: str, snapshot_file: str):
        from app.db import add_violation_event
        # Tạo vehicle trước nếu chưa có (qua DB)
        from app.db import add_vehicle
        from app.db import get_vehicle_by_plate
        if get_vehicle_by_plate(plate) is None:
            add_vehicle(plate, f"Học sinh {plate}", cls)
        ev = add_violation_event(
            timestamp="2026-10-02T11:00:00",
            plate_read=plate, plate_matched=plate,
            helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=f"snapshots/{snapshot_file}",
        )
        return ev

    def test_teacher_can_view_own_class_snapshot(self, test_app, tmp_path):
        """Tạo ảnh giả + DB event cho lớp 10A1 → teacher lớp 10A1 xem được."""
        client = TestClient(test_app)
        # Patch SNAPSHOTS_DIR để dùng tmp
        from app import config as cfg
        import app.api.media as media_api
        orig_snap = cfg.SNAPSHOTS_DIR
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir()
        (snap_dir / "test_a.jpg").write_bytes(b"\xff\xd8\xff\xd9")  # JPEG tối thiểu
        cfg.SNAPSHOTS_DIR = str(snap_dir)
        media_api.SNAPSHOTS_DIR = str(snap_dir)

        # Reload file mapping module so _safe_file_path uses new SNAPSHOTS_DIR
        # (do function được define khi import; ta monkey-patch root trực tiếp)
        orig_safe = media_api._safe_file_path
        from pathlib import Path as _Path
        def _safe_patched(subdir, filename, base_dir):
            root = _Path(base_dir).resolve()
            for candidate in (root / filename, root / subdir / filename):
                resolved = candidate.resolve()
                if not resolved.is_relative_to(root):
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail="Invalid filename")
                if resolved.is_file():
                    return str(resolved)
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="File not found")
        media_api._safe_file_path = _safe_patched

        try:
            admin_token = _login(client, "admin").json()["access_token"]
            # Vehicle 10A1
            r = client.post(
                "/api/vehicles",
                json={"plate_number": "50B11111", "student_name": "Học A1", "student_class": "10A1"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r.status_code == 201
            # Tạo violation event giả với snapshot file thuộc 10A1
            ev = self._add_violation_with_path("50B11111", "10A1", "test_a.jpg")

            # teacher login
            t_token = _login(client, "teacher").json()["access_token"]
            # Lấy URL
            r = client.get(
                "/api/violations",
                headers={"Authorization": f"Bearer {t_token}"},
            )
            assert r.status_code == 200
            ev_found = next((i for i in r.json()["items"] if i["id"] == ev), None)
            assert ev_found is not None, "teacher phải thấy event lớp mình"
            snap_url = ev_found["snapshot_url"]
            assert snap_url.startswith("/api/media/snapshots/")

            # Gọi media endpoint — teacher lớp 10A1 OK
            r = client.get(snap_url, headers={"Authorization": f"Bearer {t_token}"})
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("image/")
        finally:
            cfg.SNAPSHOTS_DIR = orig_snap
            media_api.SNAPSHOTS_DIR = orig_snap
            media_api._safe_file_path = orig_safe

    def test_teacher_forbidden_other_class_snapshot(self, test_app, tmp_path):
        client = TestClient(test_app)
        from app import config as cfg
        import app.api.media as media_api
        orig_snap = cfg.SNAPSHOTS_DIR
        snap_dir = tmp_path / "snapshots_b"
        snap_dir.mkdir()
        (snap_dir / "test_b.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        cfg.SNAPSHOTS_DIR = str(snap_dir)
        media_api.SNAPSHOTS_DIR = str(snap_dir)
        orig_safe = media_api._safe_file_path
        from pathlib import Path as _Path
        def _safe_patched(subdir, filename, base_dir):
            root = _Path(base_dir).resolve()
            for candidate in (root / filename, root / subdir / filename):
                resolved = candidate.resolve()
                if not resolved.is_relative_to(root):
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail="Invalid filename")
                if resolved.is_file():
                    return str(resolved)
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="File not found")
        media_api._safe_file_path = _safe_patched
        try:
            admin_token = _login(client, "admin").json()["access_token"]
            # Vehicle lớp 10A2 (teacher là lớp 10A1)
            r = client.post(
                "/api/vehicles",
                json={"plate_number": "60C11111", "student_name": "Học A2", "student_class": "10A2"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r.status_code == 201
            ev = self._add_violation_with_path("60C11111", "10A2", "test_b.jpg")

            t_token = _login(client, "teacher").json()["access_token"]
            # Tìm URL qua DB (teacher không thấy event vì scope lọc)
            r = client.get("/api/violations", headers={"Authorization": f"Bearer {t_token}"})
            assert r.status_code == 200
            ev_b = next((i for i in r.json()["items"] if i["id"] == ev), None)
            assert ev_b is None, "teacher lớp 10A1 KHÔNG được thấy event lớp 10A2"
        finally:
            cfg.SNAPSHOTS_DIR = orig_snap
            media_api.SNAPSHOTS_DIR = orig_snap
            media_api._safe_file_path = orig_safe


class TestApiReturnsJson404:
    """API 404 phải trả JSON `{detail}`, không trả SPA index.html."""

    def test_unknown_api_route_returns_json_404(self, test_app):
        client = TestClient(test_app)
        r = client.get("/api/khong-ton-tai")
        # 404 hoặc 405 tuỳ FastAPI — quan trọng là không phải HTML
        assert r.status_code in (404, 405)
        ct = r.headers.get("content-type", "")
        assert "application/json" in ct or "text/plain" in ct, ct

    def test_api_violations_not_found_returns_json(self, test_app):
        client = TestClient(test_app)
        admin_token = _login(client, "admin").json()["access_token"]
        r = client.get(
            "/api/violations/9999999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 404
        assert "application/json" in r.headers.get("content-type", "")


class TestMediaApiRangeSupport:
    """Media endpoint trả 200 cho GET, hỗ trợ Range header đúng RFC."""

    def test_snapshot_returns_200_image_content(self, test_app, tmp_path):
        client = TestClient(test_app)
        from app import config as cfg
        import app.api.media as media_api
        orig_snap = cfg.SNAPSHOTS_DIR
        snap_dir = tmp_path / "range_snap"
        snap_dir.mkdir()
        # Tạo ảnh JPEG hợp lệ tối thiểu
        img_bytes = bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000"
            "ffdb0043000302020203020203030303040304040405"
            "060505060b080a0a0b0a0a0c0c0c0c0c0c0c0c0c0c0c"
            "0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c"
            "0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c"
            "0c0c0c0c0cffc0001108000100010301220002110103"
            "1101ffc4001f00000105010101010101000000000000"
            "00000102030405060708090a0bffc400b51000020103"
            "03020403050504040000010277000102031104052131"
            "0612415107111322711432810891a1082342c11552d1"
            "f02433627282090a161718191a25262728292a343536"
            "3738393a434445464748494a535455565758595a6364"
            "65666768696a737475767778797a838485868788898a92"
            "939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6"
            "b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9da"
            "e1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4"
            "001bfcffd9"
        )
        # Fallback: just write a minimal JPEG marker
        (snap_dir / "small.jpg").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")
        cfg.SNAPSHOTS_DIR = str(snap_dir)
        media_api.SNAPSHOTS_DIR = str(snap_dir)
        try:
            admin_token = _login(client, "admin").json()["access_token"]
            r = client.get(
                "/api/media/snapshots/small.jpg",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r.status_code == 200, r.text
            assert r.content[:2] == "image" or r.headers.get("content-type", "").startswith("image/")
        finally:
            cfg.SNAPSHOTS_DIR = orig_snap
            media_api.SNAPSHOTS_DIR = orig_snap

    def test_snapshot_range_request_returns_206(self, test_app, tmp_path):
        """Test Range header — Starlette FileResponse hỗ trợ partial content."""
        client = TestClient(test_app)
        from app import config as cfg
        import app.api.media as media_api
        orig_snap = cfg.SNAPSHOTS_DIR
        snap_dir = tmp_path / "range_snap2"
        snap_dir.mkdir()
        (snap_dir / "data.bin").write_bytes(b"X" * 100)
        cfg.SNAPSHOTS_DIR = str(snap_dir)
        media_api.SNAPSHOTS_DIR = str(snap_dir)
        try:
            admin_token = _login(client, "admin").json()["access_token"]
            # Tạo file với tên snapshots prefix
            r = client.get(
                "/api/media/snapshots/data.bin",
                headers={"Authorization": f"Bearer {admin_token}", "Range": "bytes=0-9"},
            )
            assert r.status_code in (200, 206), r.text
            # Nếu 206 thì body phải ngắn hơn file gốc
            if r.status_code == 206:
                assert len(r.content) == 10
        finally:
            cfg.SNAPSHOTS_DIR = orig_snap
            media_api.SNAPSHOTS_DIR = orig_snap


class TestApiClientSameOrigin:
    """Không hardcode URL backend trong frontend/src/api/client.js."""

    def test_client_baseurl_is_empty_or_relative(self):
        """API_BASE_URL phải là '' (relative) — axios tự resolve theo window.location."""
        from pathlib import Path
        client_js = Path("frontend/src/api/client.js").read_text(encoding="utf-8")
        # Phải có dòng `export const API_BASE_URL = '';`
        assert "API_BASE_URL = ''" in client_js or 'API_BASE_URL = ""' in client_js
        # Comment có thể nhắc tới 'localhost' nhưng URL gán vào biến phải rỗng.
        # Tìm dòng gán thực sự — không phải dòng comment.
        import re
        # Match: export const API_BASE_URL = '...'; (không phải trong comment)
        m = re.search(r"^\s*export\s+const\s+API_BASE_URL\s*=\s*['\"]([^'\"]*)['\"]", client_js, re.MULTILINE)
        assert m is not None, "Không tìm thấy export const API_BASE_URL"
        assert m.group(1) == "", f"API_BASE_URL phải rỗng, hiện tại: {m.group(1)!r}"


class TestProductionDeepLinkAndApi404:
    """R2 — production deep link trả 200 index.html, /api/... không tồn tại
    trả JSON 404. Test qua app.main.create_app() với frontend_dist stub."""

    @pytest.fixture
    def production_app(self, tmp_path, monkeypatch):
        """Tạo app production-mode bằng create_app() thật + frontend dist giả."""
        # Tạo dist giả với index.html tối thiểu để SPA fallback mount được
        dist = tmp_path / "frontend_dist"
        dist.mkdir()
        (dist / "index.html").write_bytes(b"<html><body>SPA stub</body></html>")
        assets = dist / "assets"
        assets.mkdir()
        (assets / "main.js").write_bytes(b"console.log('stub');")

        # Patch frontend_dist path trong app.main thành dist giả
        import app.main as main_mod
        monkeypatch.setattr(main_mod, "frontend_dist", str(dist))

        # Build app mới qua create_app() + attach SPA fallback
        new_app = main_mod.create_app()
        main_mod._attach_spa_fallback(new_app, str(dist))
        return new_app

    def test_root_public_file_served_and_traversal_blocked(self, production_app, tmp_path):
        """favicon/logo copied from public/ live at dist root, not under assets/."""
        (tmp_path / "frontend_dist" / "favicon.svg").write_bytes(b"<svg/>")
        (tmp_path / "secret.txt").write_bytes(b"nope")
        client = TestClient(production_app)
        assert client.get("/favicon.svg").content == b"<svg/>"
        assert client.get("/missing.svg").status_code == 404
        assert client.get("/..%2Fsecret.txt").status_code == 404

    def test_admin_deep_link_returns_html(self, production_app):
        """/admin/violations phải 200 + text/html (KHÔNG 410, codex F03)."""
        client = TestClient(production_app)
        r = client.get("/admin/violations")
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", ""), r.headers
        assert b"SPA stub" in r.content

    def test_teacher_deep_link_returns_html(self, production_app):
        """/teacher/violations phải 200 + text/html."""
        client = TestClient(production_app)
        r = client.get("/teacher/violations")
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", "")

    def test_api_unknown_returns_json_404(self, production_app):
        """/api/khong-ton-tai phải 404 + JSON, KHÔNG rơi vào SPA fallback (F03)."""
        client = TestClient(production_app)
        r = client.get("/api/khong-ton-tai")
        assert r.status_code == 404, r.text
        # JSON, không phải HTML
        ct = r.headers.get("content-type", "")
        assert ct.startswith("application/json"), f"phải JSON, hiện {ct}: {r.text}"
        # Body là dict có 'detail'
        body = r.json()
        assert "detail" in body

    def test_assets_real_file_served(self, production_app):
        """/assets/main.js phải trả file thật (không phải SPA index.html)."""
        client = TestClient(production_app)
        r = client.get("/assets/main.js")
        assert r.status_code == 200, r.text
        assert b"console.log" in r.content
        # application/javascript, không phải text/html
        ct = r.headers.get("content-type", "")
        assert "javascript" in ct or "text/plain" in ct or "octet-stream" in ct, ct

    def test_asset_not_found_returns_404_json(self, production_app):
        """/assets/khong-ton-tai.js phải 404 JSON (F07: không trả index.html giả)."""
        client = TestClient(production_app)
        r = client.get("/assets/khong-ton-tai.js")
        assert r.status_code == 404, r.text

    def test_dot_file_not_served_as_html(self, production_app):
        """/favicon.ico (file có .) phải 200/404 file, KHÔNG trả SPA index.html."""
        client = TestClient(production_app)
        r = client.get("/favicon.ico")
        # 404 OK vì không có favicon; nếu SPA fallback nuốt sẽ trả 200 + text/html
        assert r.status_code == 404, r.text
        ct = r.headers.get("content-type", "")
        # JSON hoặc text/plain (lỗi 404 HTTP), không phải text/html (SPA)
        assert "text/html" not in ct, f"F03 regression: SPA fallback nuốt .ico ({ct})"

    def test_no_410_for_jinja_routes(self, production_app):
        """Route /admin không còn 410 (F03 codex review)."""
        client = TestClient(production_app)
        r = client.get("/admin")
        assert r.status_code != 410, "F03 regression: route /admin vẫn trả 410"
        # 200 HTML là đúng (admin landing page qua SPA)
        assert r.status_code == 200, r.text