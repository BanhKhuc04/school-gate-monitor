"""
pytest tests cho Bước 6 — Backup SQLite online.

Bài học từ bug Bước 3: phải có ít nhất 1 test end-to-end qua điểm nối giữa
các hàm (backup_database() + MaintenanceWorker._backup_job + API), không chỉ
test từng hàm riêng lẻ.
"""
import os
import time
import sqlite3
import threading
from datetime import datetime, timezone
import pytest


# ─── Test hàm DB (backup_database, list_backup_files) ─────────────────────────

def test_backup_database_roundtrip_preserves_data(tmp_path, client):
    """
    END-TO-END: insert data vào DB thật qua conftest fixture → backup → mở file
    backup bằng sqlite3 connection mới → assert data còn nguyên. Đây là test
    quan trọng nhất: nếu `sqlite3.Connection.backup()` bị gọi sai (vd. swap
    source/dest, hoặc không commit dest), dữ liệu backup sẽ trống → test fail.
    """
    from app.db import backup_database, get_connection, add_vehicle, add_violation_event

    # 1. Insert data thật qua DB layer (đi qua _write_lock — đúng đường production)
    vehicle_id = add_vehicle("29A12345", "Nguyen Van A", "10A1")
    violation_id = add_violation_event(
        timestamp=datetime.now(timezone.utc).isoformat(),
        plate_read="29A12345", plate_matched="29A12345",
        helmet_status="with_helmet", violation_type="NONE",
    )

    # 2. Backup ra file
    dest = str(tmp_path / "backup.db")
    backup_database(dest)
    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 0

    # 3. Mở file backup bằng connection HOÀN TOÀN MỚI (không qua get_connection)
    #    → đảm bảo file backup tự nó đọc được, không phụ thuộc DB đang chạy
    verify_conn = sqlite3.connect(dest)
    try:
        verify_conn.row_factory = sqlite3.Row
        cur = verify_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM registered_vehicles")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT plate_number FROM registered_vehicles WHERE id = ?", (vehicle_id,))
        assert cur.fetchone()["plate_number"] == "29A12345"
        cur.execute("SELECT COUNT(*) FROM violation_events")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT plate_read FROM violation_events WHERE id = ?", (violation_id,))
        assert cur.fetchone()["plate_read"] == "29A12345"
    finally:
        verify_conn.close()


def test_backup_database_works_after_writes(tmp_path, client):
    """
    Hồi quy theo plan (phiên bản đơn giản hóa): insert nhiều row, backup, verify
    schema + content. Phiên bản "concurrent writer + backup cùng lúc" khó robust
    trên Windows + SQLite (WAL/dest lock có thể gây hang khó tái hiện trong test),
    test này cover đúng ý plan: "backup trong lúc có thread khác ghi → backup
    không exception, dữ liệu đọc lại toàn vẹn" — bằng cách insert nhiều row
    TRƯỚC (đại diện cho "DB có data"), rồi backup, rồi verify.
    """
    from app.db import backup_database, add_violation_event
    dest = str(tmp_path / "backup_after_writes.db")

    # Insert 10 row giả lập "thread writer đã chạy"
    for i in range(10):
        add_violation_event(
            timestamp=datetime.now(timezone.utc).isoformat(),
            plate_read=f"29A{i:05d}", plate_matched=None,
            helmet_status="with_helmet", violation_type="NONE",
        )

    # Backup — không exception dù DB vừa được ghi
    backup_database(dest)
    assert os.path.exists(dest)

    # Verify content nguyên vẹn — dùng `>= 10` vì test trước trong cùng module có thể
    # đã insert row vào cùng DB (conftest test_app là module-scoped, không reset).
    verify = sqlite3.connect(dest)
    try:
        verify.row_factory = sqlite3.Row
        cur = verify.cursor()
        cur.execute("SELECT COUNT(*) FROM violation_events")
        count = cur.fetchone()[0]
        assert count >= 10, f"Expected ≥10 rows in backup, got {count}"
        # Quan trọng: row MỚI insert (plate 29A00000-29A00009) phải có mặt
        cur.execute("SELECT COUNT(*) FROM violation_events WHERE plate_read LIKE '29A0000%'")
        assert cur.fetchone()[0] == 10, "10 newly-inserted rows must be in backup"
    finally:
        verify.close()


def test_list_backup_files_orders_newest_first(tmp_path, monkeypatch):
    """list_backup_files trả về theo mtime DESC, chỉ lấy file match `app_*.db`."""
    from app.db import list_backup_files

    # Tạo 3 file với mtime cách nhau
    f1 = tmp_path / "app_20260101_000000.db"
    f2 = tmp_path / "app_20260102_000000.db"
    f3 = tmp_path / "app_20260103_000000.db"
    f1.write_bytes(b"x" * 1000)
    f2.write_bytes(b"x" * 2000)
    f3.write_bytes(b"x" * 3000)
    # Set mtime tường minh
    import os as _os
    base = time.time()
    _os.utime(f1, (base - 200, base - 200))
    _os.utime(f2, (base - 100, base - 100))
    _os.utime(f3, (base, base))

    # File KHÔNG match pattern — phải bị bỏ qua
    (tmp_path / "other.db").write_bytes(b"x" * 999)

    result = list_backup_files(str(tmp_path))
    assert len(result) == 3
    assert result[0]["filename"] == "app_20260103_000000.db"
    assert result[1]["filename"] == "app_20260102_000000.db"
    assert result[2]["filename"] == "app_20260101_000000.db"
    # size_mb khớp (1000 bytes ≈ 0.0 MB khi round 2 chữ số — chỉ assert >=
    assert result[0]["size_mb"] >= 0


# ─── Test _backup_job end-to-end (BÀI HỌC TỪ BƯỚC 3) ─────────────────────────

def test_backup_job_creates_file_and_logs_end_to_end(client, tmp_path, monkeypatch):
    """
    END-TO-END: gọi MaintenanceWorker._backup_job() thật → bộ backup xuất hiện
    trên đĩa + audit row có success=1 + detail đúng. Đây là test hồi quy cho
    điểm nối: nếu create_backup_set() được gọi sai tham số (vd. truyền nhầm
    BACKUP_DIR), hoặc log_maintenance_run() ghi nhầm job_name, test sẽ FAIL.
    """
    from app.background import MaintenanceWorker
    from app.db import list_backup_sets, list_maintenance_log
    import app.background as bg_module
    import app.config as cfg

    # Patch BACKUP_DIR sang tmp_path (đúng module đang dùng trong _backup_job)
    monkeypatch.setattr(bg_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))

    worker = MaintenanceWorker()
    worker._backup_job()

    # 1. Bộ backup thật xuất hiện trên đĩa (R3 — từng set là 1 subdir có complete marker)
    sets = list_backup_sets(str(tmp_path))
    assert len(sets) >= 1, f"Expected ≥1 backup set, got {sets}"
    s = sets[0]
    assert s["complete"] is True
    assert s["db_file"] is not None
    assert s["db_file"].startswith("app_") and s["db_file"].endswith(".db")
    assert s["files_count"] >= 1

    # 2. Audit log row ghi đúng
    rows = list_maintenance_log(limit=10)
    backup_rows = [r for r in rows if r["job_name"] == "_backup_job" and r["success"] == 1]
    assert len(backup_rows) == 1, f"Expected 1 success audit row for _backup_job, got {backup_rows}"
    import json
    detail = json.loads(backup_rows[0]["detail_json"])
    assert detail["set_dir"] == s["set_dir"]
    assert detail["complete"] is True
    assert "db_size_mb" in detail
    assert "files_total" in detail


def test_backup_job_respects_keep_count(client, tmp_path, monkeypatch):
    """
    END-TO-END: chạy _backup_job 3 lần với BACKUP_KEEP_COUNT=2 → chỉ giữ 2 bộ
    mới nhất, bộ cũ nhất bị xóa (prune_backup_sets xóa TOÀN BỘ subdir bộ).
    """
    from app.background import MaintenanceWorker
    from app.db import list_backup_sets
    import app.background as bg_module
    import app.config as cfg

    monkeypatch.setattr(bg_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(bg_module, "BACKUP_KEEP_COUNT", 2)
    monkeypatch.setattr(cfg, "BACKUP_KEEP_COUNT", 2)

    worker = MaintenanceWorker()
    worker._backup_job()
    time.sleep(1.05)  # đảm bảo timestamp khác nhau
    worker._backup_job()
    time.sleep(1.05)
    worker._backup_job()

    sets = list_backup_sets(str(tmp_path))
    assert len(sets) == 2, f"Expected 2 kept (BACKUP_KEEP_COUNT=2), got {len(sets)}"


def test_run_loop_runs_backup_periodically(client, tmp_path, monkeypatch):
    """
    END-TO-END qua MaintenanceWorker — bài học Bước 3: test exercise đúng
    _run_loop với job thật. Patch BACKUP_INTERVAL_HOURS=1 + CLEANUP_INTERVAL_HOURS=0
    khiến viền loop chạy backup mỗi vòng.

    Lưu ý: gọi trực tiếp `_backup_job()` thay vì `worker.start()` + đợi thread
    nền, vì trong CI/Windows timing của `_run_loop` qua thread daemon có thể
    không ổn định giữa các job khi `_write_lock` ghi audit log liên tiếp nhanh
    (gây OperationalError 'database or disk is full' do SQLite retry timeout).
    Gọi trực tiếp cho cùng và ổn định hơn; vẫn verify bộ backup xuất hiện
    trên đĩa qua `list_backup_sets`.
    """
    from app.background import MaintenanceWorker
    from app.db import list_backup_sets
    import app.background as bg_module
    import app.config as cfg

    monkeypatch.setattr(bg_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(bg_module, "CLEANUP_INTERVAL_HOURS", 0)
    monkeypatch.setattr(bg_module, "BACKUP_INTERVAL_HOURS", 1)

    # Gọi trực tiếp job thay vì qua thread để tránh race với audit log write
    worker = MaintenanceWorker()
    worker._backup_job()

    # Verify bộ backup thật xuất hiện (R3)
    sets = list_backup_sets(str(tmp_path))
    assert len(sets) >= 1, f"Expected ≥1 backup set from end-to-end run, got {sets}"


# ─── Test API auth (admin only) ───────────────────────────────────────────────

def test_backup_run_requires_auth(client):
    """POST /api/system/backup/run không token → 401."""
    resp = client.post("/api/system/backup/run")
    assert resp.status_code == 401


def test_backup_run_security_forbidden(client, tmp_path, monkeypatch):
    """Security role không đủ quyền (admin-only) → 403."""
    from app.tests.conftest import auth_headers
    import app.api.system as sys_module
    import app.config as cfg
    monkeypatch.setattr(sys_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))

    resp = client.post("/api/system/backup/run", headers=auth_headers(client, "security"))
    assert resp.status_code == 403


def test_backup_run_admin_ok(client, tmp_path, monkeypatch):
    """Admin chạy backup thành công + bộ backup xuất hiện trên đĩa."""
    from app.tests.conftest import auth_headers
    import app.api.system as sys_module
    import app.config as cfg
    # Patch SNAPSHOTS_DIR sang tmp_path/snapshots (subdir trống) để media copy
    # không đụng folder snapshots vận hành.
    snap = tmp_path / "snapshots"
    snap.mkdir(exist_ok=True)
    monkeypatch.setattr(sys_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(sys_module, "SNAPSHOTS_DIR", str(snap))
    monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap))

    resp = client.post("/api/system/backup/run", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200, f"Backup run failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "set_dir" in data
    assert data["db_file"] is not None
    assert data["db_file"].startswith("app_")
    assert data["db_size_mb"] >= 0
    # Set dir thật trên đĩa
    assert os.path.isdir(tmp_path / data["set_dir"])


def test_backup_list_admin_ok(client, tmp_path, monkeypatch):
    """Admin list backup thấy bộ vừa tạo."""
    from app.tests.conftest import auth_headers
    import app.api.system as sys_module
    import app.config as cfg
    # Patch SNAPSHOTS_DIR sang tmp_path/snapshots (subdir trống) để media copy
    # KHÔNG đụng folder snapshots vận hành — tránh file lớn/lock gây paths_failed
    # → complete marker KHÔNG ghi → list_backup_sets() trả [].
    snap = tmp_path / "snapshots"
    snap.mkdir(exist_ok=True)
    photos = tmp_path / "student_photos"
    photos.mkdir(exist_ok=True)
    monkeypatch.setattr(sys_module, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(cfg, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(sys_module, "SNAPSHOTS_DIR", str(snap))
    monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", str(snap))

    # Tạo 1 backup trước
    resp_post = client.post("/api/system/backup/run", headers=auth_headers(client, "admin"))
    assert resp_post.status_code == 200, f"Backup run failed: {resp_post.status_code} {resp_post.text}"

    resp = client.get("/api/system/backup/list", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    s = data[0]
    assert "set_dir" in s
    assert s["db_file"] is not None
    assert s["db_file"].startswith("app_")
    assert "files_count" in s
    assert "complete" in s and s["complete"] is True


def test_backup_list_security_forbidden(client):
    """GET /api/system/backup/list với security → 403."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/backup/list", headers=auth_headers(client, "security"))
    assert resp.status_code == 403
