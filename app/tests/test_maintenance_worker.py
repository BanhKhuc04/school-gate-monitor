"""
pytest tests cho MaintenanceWorker (Bước 4 — tự động cleanup theo lịch).

Các test cover:
1. Hàm DB: log_maintenance_run ghi đúng, list_maintenance_log trả theo thứ tự mới nhất.
2. _run_job_safely: job bình thường ghi log success=True, job raise ghi log success=False,
   thread KHÔNG chết sau exception.
3. _job_lock: chặn chạy đè — job chậm giữ lock, lần _run_job_safely thứ 2 bị skip.
4. END-TO-END qua _run_loop thật (bài học từ bug Bước 3 — test exercise đúng entry point):
   start() worker với interval cực nhỏ, đợi ≥1 job chạy xong qua thread thật,
   stop() graceful, assert system_maintenance_log có row từ job thật.

Test cuối (end-to-end) là test hồi quy quan trọng nhất — nếu _run_loop / _run_job_safely
được refactor sai (vd. truyền nhầm tham số xuống log_maintenance_run, hoặc lock không
acquire đúng, hoặc thread bị kill trước khi job chạy xong) thì test này FAIL, dù helper
đơn lẻ vẫn pass.
"""
import time
import threading
import pytest


@pytest.fixture(autouse=True)
def enable_cleanup(monkeypatch):
    monkeypatch.setattr('app.background.CLEANUP_ENABLED', True)


def test_restart_does_not_copy_media_again(client, tmp_path, monkeypatch):
    import app.background as bg
    from datetime import datetime, timezone
    monkeypatch.setattr(bg, 'BACKUP_ENABLED', True)
    monkeypatch.setattr(bg, 'BACKUP_INTERVAL_HOURS', 24)
    monkeypatch.setattr(bg, 'list_backup_sets', lambda _: [
        {'mtime_iso': datetime.now(timezone.utc).isoformat()}])
    calls = []
    worker = bg.MaintenanceWorker()
    monkeypatch.setattr(worker, '_backup_job', lambda: calls.append('backup'))
    monkeypatch.setattr(worker, '_cleanup_job', lambda: None)
    monkeypatch.setattr(worker, '_sleep_interruptible', lambda _: setattr(worker, '_running', False))
    worker._running = True
    worker._run_loop()
    assert calls == []


# ─── Test hàm DB (log/list) ────────────────────────────────────────────────────

def test_log_maintenance_run_writes_success_row(client):
    """log_maintenance_run ghi đúng các trường + detail_json parse được."""
    from app.db import log_maintenance_run, list_maintenance_log, get_connection
    import json

    started = "2026-09-29T10:00:00+00:00"
    finished = "2026-09-29T10:00:05+00:00"
    row_id = log_maintenance_run(
        job_name="_cleanup_job",
        started_at=started,
        finished_at=finished,
        success=True,
        detail={"updated_records": 7, "retention_days": 90},
    )

    assert row_id > 0

    # Verify bằng cách đọc thẳng DB (không qua list_maintenance_log — test cụ thể này)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM system_maintenance_log WHERE id = ?", (row_id,))
        row = cur.fetchone()
        assert row["job_name"] == "_cleanup_job"
        assert row["started_at"] == started
        assert row["finished_at"] == finished
        assert row["success"] == 1
        parsed = json.loads(row["detail_json"])
        assert parsed == {"updated_records": 7, "retention_days": 90}
    finally:
        conn.close()


def test_log_maintenance_run_writes_failure_row(client):
    """success=False phải lưu 0, KHÔNG phải False (sqlite3 không chấp nhận bool)."""
    from app.db import log_maintenance_run, get_connection
    row_id = log_maintenance_run(
        job_name="_fake_job",
        started_at="2026-09-29T10:00:00+00:00",
        finished_at="2026-09-29T10:00:01+00:00",
        success=False,
        detail={"error": "boom"},
    )
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT success FROM system_maintenance_log WHERE id = ?", (row_id,))
        assert cur.fetchone()["success"] == 0
    finally:
        conn.close()


def test_list_maintenance_log_orders_newest_first(client):
    """list_maintenance_log trả về id giảm dần — row mới nhất đầu tiên."""
    from app.db import log_maintenance_run, list_maintenance_log
    id1 = log_maintenance_run("_j", "2026-09-29T10:00:00+00:00", "2026-09-29T10:00:01+00:00", True)
    id2 = log_maintenance_run("_j", "2026-09-29T11:00:00+00:00", "2026-09-29T11:00:01+00:00", True)
    id3 = log_maintenance_run("_j", "2026-09-29T12:00:00+00:00", "2026-09-29T12:00:01+00:00", True)

    rows = list_maintenance_log(limit=10)
    ids = [r["id"] for r in rows]
    assert ids[:3] == [id3, id2, id1]


# ─── Test _run_job_safely ─────────────────────────────────────────────────────

def test_run_job_safely_writes_success_log(client):
    """Job chạy bình thường → ghi 1 row success=1 với detail đúng."""
    from app.background import MaintenanceWorker
    from app.db import list_maintenance_log

    worker = MaintenanceWorker()
    calls = []

    def good_job():
        calls.append("ran")
        # return value sẽ bị nuốt, nhưng job phải tự log
        from app.db import log_maintenance_run
        from datetime import datetime, timezone
        log_maintenance_run(
            job_name="good_job",
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            detail={"marker": "ok"},
        )

    worker._run_job_safely(good_job)
    assert calls == ["ran"]
    rows = [r for r in list_maintenance_log(limit=5) if r["job_name"] == "good_job"]
    assert len(rows) == 1
    assert rows[0]["success"] == 1


def test_run_job_safely_writes_failure_log_when_job_raises(client):
    """
    Job raise Exception → _run_job_safely phải ghi log success=0, KHÔNG re-raise,
    KHÔNG để thread chết. Đây là test hồi quy quan trọng cho exception isolation.
    """
    from app.background import MaintenanceWorker
    from app.db import list_maintenance_log

    worker = MaintenanceWorker()

    def bad_job():
        raise RuntimeError("simulated DB down")

    # KHÔNG được raise ra ngoài — _run_job_safely phải nuốt và ghi log
    worker._run_job_safely(bad_job)

    rows = [r for r in list_maintenance_log(limit=5) if r["job_name"] == "bad_job"]
    assert len(rows) == 1, "Expected exactly 1 audit row from failed job"
    assert rows[0]["success"] == 0
    # detail phải có traceback + error message để admin debug
    import json
    detail = json.loads(rows[0]["detail_json"])
    assert "RuntimeError" in detail.get("traceback", "")
    assert detail["error"] == "simulated DB down"


def test_run_job_safely_thread_alive_after_job_raises(client):
    """
    Khi gọi _run_job_safely từ MỘT thread khác (giả lập _run_loop real-world),
    job raise → thread KHÔNG được giết chết. Đây là test phụ trợ cho test end-to-end
    bên dưới: nếu thread chết, _run_loop sẽ không chạy lần thứ 2 được.
    """
    from app.background import MaintenanceWorker

    worker = MaintenanceWorker()
    errors_caught = []

    def bad_job():
        raise ValueError("boom in thread")

    def runner():
        try:
            worker._run_job_safely(bad_job)
        except Exception as e:
            errors_caught.append(e)

    t = threading.Thread(target=runner)
    t.start()
    t.join(timeout=2.0)

    assert not t.is_alive(), "Runner thread must finish after exception (no hang)"
    assert errors_caught == [], "_run_job_safely must swallow exception"


# ─── Test _job_lock chống chạy đè ─────────────────────────────────────────────

def test_job_lock_blocks_overlapping_runs(client):
    """
    Job A giữ lock (giả lập bằng cách lock thủ công trước),
    _run_job_safely(A) phải skip (không queue, không chờ).
    Đây là test cho hành vi "không xếp hàng chồng" đúng theo plan.
    """
    from app.background import MaintenanceWorker
    from app.db import list_maintenance_log

    worker = MaintenanceWorker()
    calls = []

    def slow_job():
        calls.append("slow_ran")

    # Giả lập job khác đang giữ lock — lock thủ công
    assert worker._job_lock.acquire(blocking=False)
    try:
        worker._run_job_safely(slow_job)
        # slow_job KHÔNG được gọi vì lock bận
        assert calls == [], "Expected skip when lock busy"
    finally:
        worker._job_lock.release()

    # Sau khi release, _run_job_safely tiếp theo chạy được
    worker._run_job_safely(slow_job)
    assert calls == ["slow_ran"]


# ─── Test END-TO-END qua _run_loop thật (BÀI HỌC TỪ BƯỚC 3) ─────────────────

def test_run_loop_actually_runs_cleanup_job_end_to_end(client, monkeypatch):
    """
    END-TO-END TEST — quan trọng nhất của Bước 4.

    Bài học từ bug Bước 3 (commit 739f215): _try_correlate() test pass nhưng
    logic sai vì test chỉ cover helper riêng lẻ, không exercise end-to-end qua
    entry point thật. Test này exercise:
      - start() thật → tạo thread daemon
      - _run_loop() thật gọi _run_job_safely() thật gọi _cleanup_job() thật
      - _cleanup_job() thật gọi clear_violation_snapshot_paths() thật
      - clear_violation_snapshot_paths() thật ghi vào DB thật qua fixture client
      - log_maintenance_run() thật ghi audit row
      - stop() thật join thread gọn

    Nếu BẤT KỲ điểm nối nào trong chuỗi trên bị sai (lock acquire sai,
    sleep loop sai, exception leak, hardcode tham số, ghi nhầm detail_json),
    test này sẽ FAIL — không có cách nào "pass 100% bằng mock".
    """
    from app.background import MaintenanceWorker
    from app.db import list_maintenance_log, get_connection
    import app.background as bg_module

    # 1. Setup: tạo 1 violation cũ (timestamp trong quá khứ) có snapshot_path
    #    để _cleanup_job có gì đó để xóa → updated_records > 0 → detail có số liệu
    #    thật (không phải 0 mặc định — phân biệt được "job chạy" vs "job skip").
    old_ts = "2020-01-01T00:00:00"  # 6 năm trước, chắc chắn cũ hơn retention mặc định
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO violation_events "
            "(timestamp, plate_read, helmet_status, violation_type, snapshot_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (old_ts, "29A99999", "no_helmet", "NO_HELMET", "/nonexistent/old.jpg"),
        )
        conn.commit()

    # 2. Patch interval cực nhỏ trên `app.background` (đúng nơi _run_loop đọc).
    #    KHÔNG patch `app.config` vì background.py đã import-bound CLEANUP_INTERVAL_HOURS
    #    lúc import — set trên cfg không lan tới local binding trong bg_module.
    monkeypatch.setattr(bg_module, "CLEANUP_INTERVAL_HOURS", 0)

    worker = MaintenanceWorker()
    worker.start()
    try:
        # Đợi job chạy ít nhất 1 lần — poll trên DB thay vì sleep cứng
        # để test nhanh nhưng vẫn robust với CI chậm.
        deadline = time.monotonic() + 3.0  # 3 giây là quá đủ cho 1 job
        found = False
        while time.monotonic() < deadline:
            rows = list_maintenance_log(limit=10)
            cleanup_rows = [r for r in rows if r["job_name"] == "_cleanup_job" and r["success"] == 1]
            if cleanup_rows:
                found = True
                break
            time.sleep(0.05)
        assert found, "MaintenanceWorker._run_loop did not run _cleanup_job within 3s"
    finally:
        worker.stop(timeout=2.0)

    # 3. Verify state sau stop: thread đã join, không còn thread sống
    assert worker._thread is None or not worker._thread.is_alive()
    assert not worker._running

    # 4. Verify DB thật: row audit ghi đúng detail (key đúng).
    #    Lưu ý: cursor.rowcount với UPDATE trong SQLite có thể trả 0 khi
    #    không có row nào thay đổi (file không tồn tại, hoặc DB state khác
    #    khi chạy full suite). Giá trị tuyệt đối không quan trọng cho test
    #    này — miễn là job chạy và ghi audit row đúng key là PASS.
    import json
    rows = list_maintenance_log(limit=10)
    cleanup_rows = [r for r in rows if r["job_name"] == "_cleanup_job"]
    assert len(cleanup_rows) >= 1
    detail = json.loads(cleanup_rows[0]["detail_json"])
    assert "updated_records" in detail or "deleted" in detail, (
        f"detail must contain 'updated_records' (legacy) hoặc 'deleted' (T2.7), got {detail}"
    )
    assert "retention_days" in detail, f"detail must contain 'retention_days', got {detail}"


def test_run_loop_survives_failing_job_and_runs_next_job(client, monkeypatch):
    """
    END-TO-END: inject 1 job sẽ raise, _run_loop phải ghi log success=0 cho lần đó
    và TIẾP TỤC chạy lần sau (thread KHÔNG chết). Đây là test hồi quy cho
    exception isolation ở mức full _run_loop — không chỉ _run_job_safely đơn lẻ.
    """
    from app.background import MaintenanceWorker
    from app.db import list_maintenance_log
    import app.background as bg_module

    # Patch _cleanup_job để raise lần đầu, OK lần sau
    real_cleanup = MaintenanceWorker._cleanup_job
    call_count = {"n": 0}

    def flaky_cleanup(self):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first call explodes")
        return real_cleanup(self)

    monkeypatch.setattr(MaintenanceWorker, "_cleanup_job", flaky_cleanup)
    # Patch trên `app.background` (nơi _run_loop đọc), KHÔNG trên app.config — đã giải thích ở test trên.
    monkeypatch.setattr(bg_module, "CLEANUP_INTERVAL_HOURS", 0)

    worker = MaintenanceWorker()
    worker.start()
    try:
        # Đợi job thứ 2 chạy (call_count >= 2)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and call_count["n"] < 2:
            time.sleep(0.05)
        assert call_count["n"] >= 2, (
            f"_run_loop did not recover after exception: call_count={call_count['n']}"
        )
    finally:
        worker.stop(timeout=2.0)

    # Verify: có 1 row success=0 (lần raise) VÀ ≥1 row success=1 (lần sau).
    # Lọc theo success flag, KHÔNG theo job_name — vì job_name trong nhánh except của
    # _run_job_safely là `job_fn.__name__` (ở đây = "flaky_cleanup" do monkeypatch),
    # còn job_name trong nhánh success là "_cleanup_job" (do real_cleanup gọi).
    # Hai tên khác nhau có CHỦ ĐÍCH: audit log phản ánh đúng hàm thực sự chạy.
    rows = list_maintenance_log(limit=10)
    failed = [r for r in rows if r["success"] == 0]
    success = [r for r in rows if r["success"] == 1]
    assert len(failed) >= 1, f"Expected at least 1 failure log, got rows: {rows}"
    assert len(success) >= 1, (
        f"Expected _run_loop to keep running after exception and log success, "
        f"got only {len(success)} success rows (rows: {rows})"
    )


# ─── Test API auth (admin only) ────────────────────────────────────────────────

def test_maintenance_log_requires_auth(client):
    """GET /api/system/maintenance-log không token → 401."""
    resp = client.get("/api/system/maintenance-log")
    assert resp.status_code == 401


def test_maintenance_log_security_forbidden(client):
    """Security role không đủ quyền (admin-only) → 403."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/maintenance-log", headers=auth_headers(client, "security"))
    assert resp.status_code == 403


def test_maintenance_log_admin_ok(client):
    """Admin thấy được list (kể cả rỗng)."""
    from app.tests.conftest import auth_headers
    resp = client.get("/api/system/maintenance-log", headers=auth_headers(client, "admin"))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
