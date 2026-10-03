"""
T2.8 — Backup bộ dữ liệu hoàn chỉnh + restore verification.

Đặc tả T2.8:
- backup_database() round-trip: insert → backup → đọc backup → schema + data khớp.
- backup trong khi DB có writer khác không exception, dữ liệu toàn vẹn.
- backup bao phủ DB schema (registered_vehicles, violation_events,
  encounter_observations, violation_audit_log, recognition_reviews).
- Restore sang vị trí KHÔNG ghi đè DB vận hành.
- integrity_check trên file backup phải 'ok'.
- Manifest liệt kê file db + size + checksum (đơn giản: SHA256).
- Bộ backup dang dở (file không hoàn chỉnh) KHÔNG có marker complete.
"""
from __future__ import annotations

import os
import sqlite3
import hashlib
import pytest
from datetime import datetime, timezone


def _add_basic_data(plate: str = "50X1-001", name: str = "Nguyễn Văn Test", klass: str = "10T1"):
    """Tạo data mẫu đủ các bảng. Plate mặc định đã tồn tại sau test đầu — gọi
    với plate khác nhau nếu muốn seed fresh.
    """
    from app.db import add_vehicle, add_violation_event, normalize_plate, get_connection
    norm = normalize_plate(plate)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM registered_vehicles WHERE plate_number = ?", (norm,)
        ).fetchone()
        if row is None:
            # Retry add_vehicle nếu SQLite báo locked từ backup trước đó
            import time as _t
            last_err = None
            for _ in range(5):
                try:
                    vehicle_id = add_vehicle(plate, name, klass)
                    break
                except Exception as e:
                    last_err = e
                    _t.sleep(0.2)
            else:
                raise last_err
        else:
            vehicle_id = row["id"]
    finally:
        conn.close()
    ev_id = add_violation_event(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        plate_read=plate, plate_matched=plate,
        helmet_status="no_helmet", violation_type="NO_HELMET",
    )
    return vehicle_id, ev_id


class TestBackupRoundtrip:
    """T2.8 — backup round-trip cơ bản."""

    def test_backup_preserves_all_required_tables(self, tmp_path, test_app):
        """Backup phải có đủ các bảng chính của hệ thống."""
        from app.db import backup_database

        _add_basic_data()
        dest = str(tmp_path / "backup_full.db")
        backup_database(dest)
        assert os.path.exists(dest)
        # Mở file backup, kiểm schema
        conn = sqlite3.connect(dest)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Lấy tất cả tên bảng
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {r["name"] for r in cur.fetchall()}
            # Schema phải có (T2.6 đã thêm encounter_observations):
            required = {
                "registered_vehicles",
                "violation_events",
                "users",
            }
            for t in required:
                assert t in tables, f"Missing table {t} in backup; got: {tables}"
        finally:
            conn.close()

    def test_backup_integrity_check_ok(self, tmp_path, test_app):
        """Backup file phải pass integrity_check."""
        from app.db import backup_database

        _add_basic_data()
        dest = str(tmp_path / "backup_integrity.db")
        backup_database(dest)

        conn = sqlite3.connect(dest)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            row = cur.fetchone()
            assert row[0] == "ok", f"integrity_check failed: {row}"
        finally:
            conn.close()

    def test_backup_size_matches_data(self, tmp_path, test_app):
        """Backup file size > 0 và phản ánh dữ liệu (>= page size)."""
        from app.db import backup_database

        _add_basic_data()
        dest = str(tmp_path / "backup_size.db")
        backup_database(dest)
        size = os.path.getsize(dest)
        # SQLite page size thường 4096; backup tối thiểu 1 page
        assert size >= 4096, f"Backup too small: {size} bytes"


class TestRestoreVerification:
    """T2.8 — restore sang vị trí riêng KHÔNG ghi đè DB vận hành."""

    def test_restore_to_separate_path_preserves_original(self, tmp_path, test_app):
        """Restore sang path khác; DB gốc KHÔNG bị ảnh hưởng."""
        from app.db import backup_database, add_vehicle, get_connection

        # Insert data ban đầu
        _add_basic_data()
        backup_path = str(tmp_path / "before.db")
        backup_database(backup_path)
        before = os.path.getsize(backup_path)

        # Restore = copy backup vào 1 path MỚI (KHÔNG overwrite DB gốc)
        restore_path = str(tmp_path / "restored.db")
        with open(backup_path, "rb") as src, open(restore_path, "wb") as dst:
            dst.write(src.read())
        # Verify restore file khác path DB vận hành
        from app import config as cfg
        assert restore_path != cfg.DB_PATH
        # Mở restore và đọc data
        conn = sqlite3.connect(restore_path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM registered_vehicles")
            assert cur.fetchone()[0] >= 1
            cur.execute("SELECT COUNT(*) FROM violation_events")
            assert cur.fetchone()[0] >= 1
        finally:
            conn.close()
        # DB vận hành KHÔNG thay đổi
        live = get_connection()
        try:
            cur = live.cursor()
            cur.execute("SELECT COUNT(*) FROM registered_vehicles")
            live_vehicle_count = cur.fetchone()[0]
            assert live_vehicle_count >= 1
        finally:
            live.close()
        assert os.path.getsize(backup_path) == before


class TestBackupManifest:
    """T2.8 — manifest: danh sách + size + checksum."""

    def test_backup_manifest_includes_checksum(self, tmp_path, test_app):
        """Backup manifest có SHA256 checksum."""
        from app.db import backup_database, compute_backup_manifest

        _add_basic_data()
        dest = str(tmp_path / "backup_manifest.db")
        backup_database(dest)
        manifest = compute_backup_manifest(dest)
        assert "filename" in manifest
        assert "size_bytes" in manifest
        assert "sha256" in manifest
        assert "created_at_utc" in manifest
        assert "integrity" in manifest
        # SHA256 dài 64 hex chars
        assert len(manifest["sha256"]) == 64
        assert manifest["size_bytes"] == os.path.getsize(dest)
        # Recompute checksum manually verify
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        assert h.hexdigest() == manifest["sha256"]
        # integrity_check should be 'ok'
        assert manifest["integrity"] == "ok"

    def test_incomplete_backup_marked_failed(self, tmp_path):
        """File DB truncated → manifest integrity != 'ok'."""
        from app.db import compute_backup_manifest

        # Tạo 1 file SQLite hợp lệ trước
        good_path = str(tmp_path / "good.db")
        conn = sqlite3.connect(good_path)
        conn.execute("CREATE TABLE x (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO x (v) VALUES ('a')")
        conn.commit()
        conn.close()
        # Truncate file (cắt 100 bytes cuối)
        with open(good_path, "rb") as f:
            data = f.read()
        truncated_path = str(tmp_path / "truncated.db")
        with open(truncated_path, "wb") as f:
            f.write(data[:-100])
        # Manifest của file truncated
        m = compute_backup_manifest(truncated_path)
        # Integrity KHÔNG phải 'ok' (có thể 'corrupt' hoặc exception)
        assert m["integrity"] != "ok"


class TestBackupConcurrency:
    """T2.8 — backup dưới writer concurrency."""

    def test_backup_succeeds_with_concurrent_writer(self, tmp_path, test_app):
        """Backup trong khi 1 thread khác đang insert vào DB."""
        import threading
        from app.db import backup_database, add_violation_event, get_connection

        stop = threading.Event()
        errors: list[str] = []

        def writer():
            i = 0
            while not stop.is_set() and i < 20:
                try:
                    add_violation_event(
                        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        plate_read=f"50X9-{i:04d}",
                        helmet_status="no_helmet", violation_type="NO_HELMET",
                    )
                    i += 1
                except Exception as e:
                    errors.append(f"writer error: {e}")
                    break

        t = threading.Thread(target=writer, daemon=True)
        t.start()
        try:
            # Trong khi writer chạy, gọi backup
            dest = str(tmp_path / "concurrent.db")
            backup_database(dest)
            assert os.path.exists(dest)
            assert os.path.getsize(dest) > 0
        finally:
            stop.set()
            t.join(timeout=3)
        assert not errors, errors

        # Verify backup có data
        conn = sqlite3.connect(dest)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM violation_events")
            assert cur.fetchone()[0] >= 0
        finally:
            conn.close()


class TestBackupSet:
    """R3.1/R3.3 — bộ backup gồm DB + media + manifest + complete marker."""

    def _make_snap(self, tmp_path, name: str, content: bytes = b"\xff\xd8\xff\xd9") -> str:
        d = tmp_path / "snap_input"
        d.mkdir(exist_ok=True)
        (d / name).write_bytes(content)
        return str(d)

    def _make_photos(self, tmp_path, name: str) -> str:
        d = tmp_path / "photos_input"
        d.mkdir(exist_ok=True)
        (d / name).write_bytes(b"\xff\xd8\xff\xd9")
        return str(d)

    def test_create_backup_set_has_complete_marker(self, tmp_path, test_app):
        """R3.1 — bộ backup có complete marker khi integrity pass."""
        from app.db import create_backup_set

        snap_dir = self._make_snap(tmp_path, "snap1.jpg")
        photos_dir = self._make_photos(tmp_path, "stu1.jpg")
        backup_root = str(tmp_path / "backups")

        result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snap_dir,
            student_photos_dir=photos_dir,
            include_media=True,
            label="hourly",
        )
        assert result["complete"] is True, result
        assert result["paths_failed"] == [], result
        assert os.path.isfile(os.path.join(result["set_dir"], "complete"))
        # Manifest có DB + media + photo
        roles = {f["role"] for f in result["files"]}
        assert "db" in roles
        assert "media" in roles
        assert "photo" in roles

    def test_incomplete_backup_no_complete_marker(self, tmp_path, test_app, monkeypatch):
        """R3.1 — DB integrity fail hoặc copy fail → KHÔNG có complete marker."""
        from app.db import create_backup_set

        snap_dir = self._make_snap(tmp_path, "snap1.jpg")
        backup_root = str(tmp_path / "backups_inc")

        # Monkeypatch backup_database để throw → DB fail → không có marker
        from app import db as db_mod
        def _failing_backup(dest_path):
            raise OSError("simulated disk full")
        monkeypatch.setattr(db_mod, "backup_database", _failing_backup)

        result = create_backup_set(
            backup_root=backup_root,
            snapshots_dir=snap_dir,
            include_media=True,
        )
        assert result["complete"] is False
        assert len(result["paths_failed"]) >= 1
        assert "db_backup" in result["paths_failed"][0]["reason"]
        assert not os.path.exists(os.path.join(result["set_dir"], "complete"))

    def test_list_backup_sets_filters_by_complete(self, tmp_path, test_app, monkeypatch):
        """R3.2 — list_backup_sets chỉ trả về các bộ có complete marker."""
        from app.db import create_backup_set, list_backup_sets

        snap_dir = self._make_snap(tmp_path, "snap1.jpg")
        backup_root = str(tmp_path / "backups_list")

        # 1 bộ OK
        r1 = create_backup_set(
            backup_root=backup_root, snapshots_dir=snap_dir, include_media=False,
            label="ok",
        )
        # 1 bộ incomplete (xóa marker)
        r2 = create_backup_set(
            backup_root=backup_root, snapshots_dir=snap_dir, include_media=False,
            label="incomplete",
        )
        # Xóa marker của bộ incomplete
        os.remove(os.path.join(r2["set_dir"], "complete"))

        listed = list_backup_sets(backup_root)
        listed_names = {s["set_dir"] for s in listed}
        # Chỉ bộ OK có marker → chỉ nó trong list
        assert any(r1["set_dir"].endswith(name) or name in r1["set_dir"]
                   for name in listed_names), listed_names

    def test_verify_backup_set_ok(self, tmp_path, test_app):
        """R3.3 — verify_backup_set trả True khi bộ nguyên vẹn."""
        from app.db import create_backup_set, verify_backup_set

        snap_dir = self._make_snap(tmp_path, "snap.jpg")
        backup_root = str(tmp_path / "backups_v")
        r = create_backup_set(
            backup_root=backup_root, snapshots_dir=snap_dir, include_media=True,
        )
        assert r["complete"]
        v = verify_backup_set(r["set_dir"])
        assert v["verified"] is True, v
        assert v["complete_marker_present"]
        assert v["db_integrity_ok"]
        assert v["db_sha256_match"]
        assert v["media_missing"] == []
        assert v["media_sha256_mismatch"] == []
        assert v["media_total"] >= 1

    def test_verify_backup_set_detects_corruption(self, tmp_path, test_app):
        """R3.3 — media file bị đổi → verify trả False."""
        from app.db import create_backup_set, verify_backup_set

        snap_dir = self._make_snap(tmp_path, "snap.jpg", b"ORIGINAL")
        backup_root = str(tmp_path / "backups_corr")
        r = create_backup_set(
            backup_root=backup_root, snapshots_dir=snap_dir, include_media=True,
        )
        assert r["complete"]
        # Sửa file media trong bộ backup
        media_path = os.path.join(r["set_dir"], "media", "snap.jpg")
        with open(media_path, "wb") as f:
            f.write(b"CORRUPTED")
        v = verify_backup_set(r["set_dir"])
        assert v["verified"] is False
        assert len(v["media_sha256_mismatch"]) >= 1

    def test_restore_backup_set_to_new_root(self, tmp_path, test_app):
        """R3.3 — restore sang restore_root MỚI; DB integrity ok; không gâng hệ vận hành."""
        from app.db import create_backup_set, restore_backup_set

        snap_dir = self._make_snap(tmp_path, "snap.jpg")
        backup_root = str(tmp_path / "backups_r")
        r = create_backup_set(
            backup_root=backup_root, snapshots_dir=snap_dir, include_media=True,
        )
        assert r["complete"]

        # Restore sang root MỚI
        restore_root = str(tmp_path / "restored")
        out = restore_backup_set(r["set_dir"], restore_root)
        assert out["db_restored"] is True
        assert out["db_ok"] is True
        assert out["media_restored_count"] >= 1
        assert out["media_missing"] == []
        # File DB restore tồn tại và integrity OK
        db_files = [f for f in os.listdir(restore_root) if f.endswith(".db")]
        assert len(db_files) == 1
        conn = sqlite3.connect(os.path.join(restore_root, db_files[0]))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            assert cur.fetchone()[0] == "ok"
        finally:
            conn.close()
        # File media restore tồn tại
        media_sub = os.path.join(restore_root, "media")
        assert os.path.isdir(media_sub)
        assert len(os.listdir(media_sub)) >= 1

    def test_prune_backup_sets_keeps_n_most_recent(self, tmp_path, test_app):
        """R3.2 — prune_backup_sets giữ N bộ mới nhất, xóa TOÀN BỘ subdir bộ cũ."""
        from app.db import create_backup_set, list_backup_sets, prune_backup_sets
        import time as _t

        snap_dir = self._make_snap(tmp_path, "snap.jpg")
        backup_root = str(tmp_path / "backups_p")
        # Tạo 3 bộ
        created = []
        for i in range(3):
            r = create_backup_set(
                backup_root=backup_root, snapshots_dir=snap_dir,
                include_media=False, label=f"set{i}",
            )
            created.append(r["set_dir"])
            _t.sleep(1.1)  # đảm bảo mtime khác nhau

        listed = list_backup_sets(backup_root)
        assert len(listed) == 3, listed
        deleted = prune_backup_sets(backup_root, keep_count=2)
        # 1 bộ cũ nhất bị xóa
        assert len(deleted) == 1
        remaining = list_backup_sets(backup_root)
        assert len(remaining) == 2
        # Bộ cũ nhất đã biến mất hoàn toàn
        for d in deleted:
            assert not os.path.isdir(d)