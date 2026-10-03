"""
T2.7 — Cleanup safety: hold, path ngoài root, unlink fail, batch partial.

Đặc tả T2.7:
- Validate path thực nằm trong SNAPSHOTS_DIR (resolve + relative_to).
- PermissionError/OSError KHÔNG clear DB reference của record đó.
- Tôn trọng evidence_state='hold'.
- Trả về dict {attempted, deleted, missing, failed, held, paths_failed: [...]}.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROLE_PASSWORD = "test123"


def _login(client: TestClient, username: str, password: str = ROLE_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestCleanupSafety:
    """T2.7 — cleanup không làm mất liên kết; partial failure được báo."""

    def test_path_outside_root_not_deleted(self, test_app, tmp_path, monkeypatch):
        """Snapshot_path trỏ ra ngoài root → KHÔNG xóa, KHÔNG null, count failed."""
        from app import config as cfg
        from app.db import (
            get_connection, add_violation_event, clear_violation_snapshot_paths,
            _write_lock,
        )
        # Patch SNAPSHOTS_DIR sang tmp_path
        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()
        outside_file = tmp_path / "outside.jpg"
        outside_file.write_bytes(b"\xff\xd8\xff\xd9")
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        import app.db as db_mod
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        # Tạo violation giả với snapshot_path TRỎ RA NGOÀI ROOT
        # NOTE: add_violation_event already acquires _write_lock internally; do NOT
        # wrap it in another `with _write_lock:` (threading.Lock is non-reentrant
        # → deadlock).
        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",  # cũ để chắc chắn nằm trong cutoff
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=str(outside_file),  # ngoài root!
        )

        result = clear_violation_snapshot_paths(older_than_days=1)
        assert result["failed"] >= 1, result
        assert any(p["reason"] == "outside_root" for p in result["paths_failed"]), result

        # File vẫn còn trên đĩa
        assert outside_file.exists()
        # DB vẫn giữ path
        from app.db import get_violations_by_vehicle  # dummy import path
        from app.db import get_connection as gc
        conn = gc()
        try:
            row = conn.execute("SELECT snapshot_path FROM violation_events WHERE id = ?", (ev_id,)).fetchone()
            assert row["snapshot_path"] == str(outside_file), "Path KHÔNG được null khi fail"
        finally:
            conn.close()

    def test_hold_state_protected_from_cleanup(self, test_app, tmp_path, monkeypatch):
        """evidence_state='hold' → KHÔNG bị cleanup xóa."""
        from app import config as cfg
        from app.db import (
            add_violation_event, clear_violation_snapshot_paths,
            get_connection,
        )
        snap_dir = tmp_path / "snap_h"
        snap_dir.mkdir()
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        import app.db as db_mod
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        # File thật trong root
        keep_file = snap_dir / "keep.jpg"
        keep_file.write_bytes(b"\xff\xd8\xff\xd9")

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="keep.jpg",
            evidence_state="hold",  # đánh dấu hold
        )

        result = clear_violation_snapshot_paths(older_than_days=1)
        assert result["held"] >= 1
        assert keep_file.exists()  # file vẫn còn
        # DB vẫn giữ path
        conn = get_connection()
        try:
            row = conn.execute("SELECT snapshot_path FROM violation_events WHERE id = ?", (ev_id,)).fetchone()
            assert row["snapshot_path"] == "keep.jpg"
        finally:
            conn.close()

    def test_missing_file_nulled_in_db(self, test_app, tmp_path, monkeypatch):
        """File không tồn tại trên disk → null trong DB, count missing."""
        from app import config as cfg
        from app.db import (
            add_violation_event, clear_violation_snapshot_paths,
            get_connection,
        )
        snap_dir = tmp_path / "snap_m"
        snap_dir.mkdir()
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        import app.db as db_mod
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="ghost.jpg",  # không có file này trên disk
        )

        result = clear_violation_snapshot_paths(older_than_days=1)
        assert result["missing"] >= 1, result

        conn = get_connection()
        try:
            row = conn.execute("SELECT snapshot_path FROM violation_events WHERE id = ?", (ev_id,)).fetchone()
            assert row["snapshot_path"] is None  # null vì file không tồn tại
        finally:
            conn.close()

    def test_recent_event_not_touched(self, test_app, tmp_path, monkeypatch):
        """Event mới hơn retention → KHÔNG bị cleanup (cutoff chưa tới)."""
        from app import config as cfg
        from app.db import (
            add_violation_event, clear_violation_snapshot_paths,
        )
        snap_dir = tmp_path / "snap_r"
        snap_dir.mkdir()
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        import app.db as db_mod
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        keep = snap_dir / "recent.jpg"
        keep.write_bytes(b"\xff\xd8\xff\xd9")

        ev_id = add_violation_event(
            timestamp="2026-10-02T01:00:00",  # mới — 0 ngày tuổi
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="recent.jpg",
        )

        result = clear_violation_snapshot_paths(older_than_days=90)
        # Event mới không nằm trong cutoff → không có thao tác gì
        assert result["attempted"] == 0
        assert keep.exists()

    def test_dry_run_no_disk_writes(self, test_app, tmp_path, monkeypatch):
        """dry_run=True — KHÔNG xóa file, KHÔNG update DB."""
        from app import config as cfg
        from app.db import (
            add_violation_event, clear_violation_snapshot_paths,
            get_connection,
        )
        snap_dir = tmp_path / "snap_d"
        snap_dir.mkdir()
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        import app.db as db_mod
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        keep = snap_dir / "old.jpg"
        keep.write_bytes(b"\xff\xd8\xff\xd9")

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="old.jpg",
        )

        result = clear_violation_snapshot_paths(older_than_days=1, dry_run=True)
        # File vẫn còn
        assert keep.exists()
        # DB vẫn giữ path
        conn = get_connection()
        try:
            row = conn.execute("SELECT snapshot_path FROM violation_events WHERE id = ?", (ev_id,)).fetchone()
            assert row["snapshot_path"] == "old.jpg"
        finally:
            conn.close()


class TestCleanupRouteSafety:
    """R1 — cleanup qua HTTP (route `/api/system/snapshots/cleanup`).

    Yêu cầu R1: route phải:
    - KHÔNG tự xóa file trước helper an toàn.
    - Trả response 200 với schema đầy đủ (deleted_files, updated_records, v.v.).
    - Không xóa file hold; không xóa file ngoài root; không xóa crop nếu snapshot
      full-frame còn file.
    - Hỗ trợ `dry_run=true`.
    """

    def _login_admin(self, client: TestClient) -> str:
        return _login(client, "admin").json()["access_token"]

    def test_route_returns_full_schema(self, test_app, tmp_path, monkeypatch):
        """Response shape phải đầy đủ theo CleanupResponse; không 500 khi DB rỗng."""
        from app import config as cfg
        import app.db as db_mod
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(tmp_path))
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(tmp_path))

        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 90, "dry_run": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Schema đầy đủ
        for key in (
            "deleted_files", "updated_records", "deleted", "missing", "failed",
            "held", "attempted", "paths_failed", "dry_run", "duration_ms",
        ):
            assert key in body, f"missing key {key}: {body}"
        assert body["dry_run"] is True
        # DB có thể có record cũ từ test khác trong cùng test_app (scope=module);
        # chỉ assert dry_run=true KHÔNG xóa file trên đĩa và KHÔNG update DB.
        assert body["deleted_files"] == 0  # dry_run = 0 deletes
        assert body["updated_records"] == 0  # dry_run = 0 updates

    def test_route_does_not_unlink_before_helper(self, test_app, tmp_path, monkeypatch):
        """F01 — Route KHÔNG tự unlink trước helper an toàn.

        Tạo event có snapshot_path TRỎ RA NGOÀI root nhưng FILE CÒN TRÊN ĐĨA.
        Sau khi gọi route, file vẫn phải còn (vì helper reject outside_root).
        Trước khi sửa: route tự os.unlink() trước → mất file dù helper từ chối.
        """
        from app import config as cfg
        from app.db import add_violation_event
        import app.db as db_mod

        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()
        outside = tmp_path / "outside_keep.jpg"
        outside.write_bytes(b"\xff\xd8\xff\xd9")

        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path=str(outside),  # ngoài root!
        )

        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 1, "dry_run": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # File ngoài root vẫn còn vì helper không xóa
        assert outside.exists(), "F01 regression: route unlink file ngoài root"
        # Helper phải báo failed > 0
        assert body["failed"] >= 1, body
        assert any(p["reason"] == "outside_root" for p in body["paths_failed"]), body

    def test_route_hold_protects_file(self, test_app, tmp_path, monkeypatch):
        """F01 — Hold: file + DB path đều được giữ."""
        from app import config as cfg
        from app.db import add_violation_event
        import app.db as db_mod

        snap_dir = tmp_path / "snap_h"
        snap_dir.mkdir()
        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        keep = snap_dir / "keep.jpg"
        keep.write_bytes(b"\xff\xd8\xff\xd9")

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="keep.jpg",
            evidence_state="hold",
        )

        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert keep.exists()
        assert body["held"] >= 1, body

        # DB vẫn giữ path
        from app.db import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT snapshot_path FROM violation_events WHERE id = ?",
                (ev_id,),
            ).fetchone()
            assert row["snapshot_path"] == "keep.jpg", row
        finally:
            conn.close()

    def test_route_symlink_outside_root_kept(self, test_app, tmp_path, monkeypatch):
        """F01 — Symlink trỏ ra ngoài root KHÔNG bị xóa."""
        from app import config as cfg
        from app.db import add_violation_event
        import app.db as db_mod

        snap_dir = tmp_path / "snap_sym"
        snap_dir.mkdir()
        # File ngoài root là target thật
        target = tmp_path / "real_target.jpg"
        target.write_bytes(b"\xff\xd8\xff\xd9")
        # Symlink trong root trỏ ra ngoài
        link = snap_dir / "link.jpg"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Symlink không khả dụng trên hệ thống này")

        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        ev_id = add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="link.jpg",
        )

        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # File thật ngoài root còn nguyên — không bị unlink qua symlink
        assert target.exists(), "F01 regression: route theo symlink ra ngoài root"
        # Helper phải báo path ngoài root
        assert body["failed"] >= 1 or any(
            p["reason"] == "outside_root" for p in body["paths_failed"]
        ), body

    def test_route_dry_run_returns_zero_changes(self, test_app, tmp_path, monkeypatch):
        """F02 — dry_run=true không xóa file, deleted_files=0."""
        from app import config as cfg
        from app.db import add_violation_event
        import app.db as db_mod

        snap_dir = tmp_path / "snap_dr"
        keep = snap_dir / "old.jpg"
        snap_dir.mkdir()
        keep.write_bytes(b"\xff\xd8\xff\xd9")

        monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap_dir))
        monkeypatch.setattr(db_mod, "SNAPSHOTS_DIR", str(snap_dir))

        add_violation_event(
            timestamp="2020-01-01T00:00:00",
            plate_read="X", helmet_status="no_helmet", violation_type="NO_HELMET",
            snapshot_path="old.jpg",
        )

        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 1, "dry_run": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True
        assert body["deleted_files"] == 0
        assert keep.exists()

    def test_route_invalid_days_returns_422(self, test_app):
        client = TestClient(test_app)
        token = self._login_admin(client)
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422, r.text

    def test_route_unauthorized_for_non_admin(self, test_app):
        client = TestClient(test_app)
        teacher_token = _login(client, "teacher").json()["access_token"]
        r = client.post(
            "/api/system/snapshots/cleanup",
            params={"older_than_days": 90},
            headers={"Authorization": f"Bearer {teacher_token}"},
        )
        # Teacher không có quyền admin
        assert r.status_code in (401, 403), r.text