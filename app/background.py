"""
Background maintenance worker — chạy các job bảo trì định kỳ (cleanup, backup).

Thread pattern giống VideoPipeline: threading.Thread(daemon=True) + cờ _running +
join() khi stop() để graceful shutdown. Mỗi job chạy trong một try/except riêng
(exception isolation) — lỗi 1 job KHÔNG được làm chết thread nền.

Đợt 2, Bước 4 — xem docs/CURSOR_PLAN_DOT2_NANG_CAP.md.

Bài học từ bug Bước 3 (fix trong commit 739f215): mọi job phải exercise đúng
end-to-end qua _run_loop / _run_job_safely, không chỉ test helper riêng lẻ.
"""
import threading
import time
import traceback
import os
from datetime import datetime, timezone

from app.config import (
    CLEANUP_ENABLED, CLEANUP_INTERVAL_HOURS, CLEANUP_RETENTION_DAYS,
    BACKUP_ENABLED, BACKUP_INTERVAL_HOURS, BACKUP_KEEP_COUNT, BACKUP_DIR,
)
from app.db import (
    clear_violation_snapshot_paths, log_maintenance_run,
    backup_database, list_backup_files,
)


class MaintenanceWorker:
    """
    Thread nền chạy các job bảo trì định kỳ (Bước 4: cleanup; Bước 6: backup).

    Vòng đời:
        worker = MaintenanceWorker()
        worker.start()                       # khởi động thread nền
        ... chạy cùng app ...
        worker.stop(timeout=5.0)             # graceful shutdown, đợi job hiện tại

    Đặc tính:
    - **Job lock (`_job_lock`)**: nếu job trước còn chạy (vd. cleanup quá lâu),
      lần wake-up sau BỎ QUA — KHÔNG xếp hàng chồng, KHÔNG chạy song song 2 lần.
      Đây là hành vi đúng cho job idempotent như cleanup/backup: chạy trễ 1 chu kỳ
      còn hơn chạy đè (vd. cleanup 30 phút + interval 1 giờ = bỏ 1 lần, chấp nhận).
    - **Exception isolation (`_run_job_safely`)**: job raise Exception → in log,
      set success=False, KHÔNG re-raise, KHÔNG thoát thread. Vòng lặp tiếp tục.
    - **Audit log**: mỗi lần chạy (kể cả fail) đều ghi 1 row vào
      `system_maintenance_log` qua `log_maintenance_run()` — admin xem qua
      `GET /api/system/maintenance-log`.
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        # Job lock: blocking=False để khi lock bận thì lần wake-up sau skip,
        # không xếp hàng. Đây là CỐ TÝNH khác với hành vi queue mặc định của Lock.
        self._job_lock = threading.Lock()

    # ─── Lifecycle (giống VideoPipeline.start/stop) ─────────────────────────────

    def start(self) -> None:
        """Bắt đầu thread nền. Idempotent — gọi 2 lần không tạo 2 thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="MaintenanceWorker",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Dừng thread nền. join(timeout) để job hiện tại (nếu có) kết thúc gọn —
        KHÔNG kill giữa chừng, tránh để DB/lock ở trạng thái dở dang.

        Sau timeout, thread daemon sẽ tự chết khi process tắt — chấp nhận vì
        daemon thread cleanup không quan trọng bằng main thread FastAPI.
        """
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None

    # ─── Vòng lặp chính ─────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """
        Vòng lặp job. Ngủ CLEANUP_INTERVAL_HOURS giữa mỗi lần chạy (đổi từ giây
        sang giây cho test inject interval cực nhỏ — xem test_maintenance_worker).

        Chu kỳ:
          - Cleanup chạy MỖI lần lặp (theo CLEANUP_INTERVAL_HOURS).
          - Backup chạy MỖI `backup_every_n_loops` lần lặp, nơi N = BACKUP_INTERVAL_HOURS / CLEANUP_INTERVAL_HOURS
            (làm tròn lên, tối thiểu 1 để backup chạy khi interval nhỏ hơn cleanup).
            Ví dụ: cleanup=24h, backup=24h → N=1 (chạy mỗi lần).
                    cleanup=24h, backup=48h → N=2 (chạy cách 1 lần).
                    cleanup=1h, backup=24h  → N=24 (chạy 1 lần/ngày).
            Pattern này tránh 2 sleep tách rời (phức tạp) mà vẫn tôn trọng interval riêng.
        """
        backup_every_n_loops = max(1, -(-BACKUP_INTERVAL_HOURS // max(CLEANUP_INTERVAL_HOURS, 1)))
        loop_count = 0
        while self._running:
            self._run_job_safely(self._cleanup_job)
            loop_count += 1
            if loop_count >= backup_every_n_loops:
                loop_count = 0
                self._run_job_safely(self._backup_job)
            self._sleep_interruptible(CLEANUP_INTERVAL_HOURS * 3600)

    def _sleep_interruptible(self, seconds: float) -> None:
        """
        Ngủ theo từng lát 0.5s để stop() phản ứng nhanh (không phải đợi hết interval).
        Daemon thread có thể bị cắt giữa time.sleep() — pattern này vừa phản ứng
        nhanh vừa không phụ thuộc event đặc biệt nào.
        """
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.5, end - time.monotonic()))

    def _run_job_safely(self, job_fn) -> None:
        """
        Chạy 1 job với lock chống chạy đè + exception isolation.

        Trả về None — kết quả (success/fail + detail) đã được ghi vào
        system_maintenance_log qua job_fn (hoặc qua nhánh except ở đây nếu job
        raise TRƯỚC khi tự log). Hàm này chỉ wrap cơ chế lock + safety, không
        thay job tự quyết định log gì.
        """
        # blocking=False: nếu job trước còn chạy, BỎ QUA lần này, không xếp hàng
        if not self._job_lock.acquire(blocking=False):
            print(f"[Maintenance] Skip {job_fn.__name__}: previous run still in progress")
            return

        started_at = datetime.now(timezone.utc).isoformat()
        try:
            job_fn()
        except Exception as e:
            # Job raise: log + ghi audit row success=0, KHÔNG re-raise.
            # Dùng traceback.format_exc() để admin thấy được stacktrace thật khi
            # xem maintenance-log, không phải chỉ message ngắn.
            tb = traceback.format_exc()
            print(f"[Maintenance] Job {job_fn.__name__} failed:\n{tb}")
            try:
                log_maintenance_run(
                    job_name=job_fn.__name__,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    success=False,
                    detail={"error": str(e), "traceback": tb},
                )
            except Exception as log_err:
                # DB write fail cũng không được nuốt hoàn toàn — in ra console
                # để admin thấy qua log server, không break thread.
                print(f"[Maintenance] CRITICAL: failed to write audit log: {log_err}")
        finally:
            self._job_lock.release()

    # ─── Các job cụ thể ─────────────────────────────────────────────────────────

    def _cleanup_job(self) -> None:
        """
        Cleanup snapshot + clip cũ hơn CLEANUP_RETENTION_DAYS.

        Tái dùng `clear_violation_snapshot_paths()` đã có từ trước (Feature 8) —
        hàm này đã chặn bởi `_write_lock` nội bộ nên an toàn khi pipeline
        camera đang INSERT vi phạm mới. CHỈ đổi cách TRIGGER (từ "admin bấm nút"
        sang "tự động theo lịch"), không đổi logic cleanup thật.

        Audit log: ghi 1 row kể cả khi không có gì để xóa (chạy định kỳ nhưng
        DB rỗng là trường hợp bình thường, vẫn phải ghi để admin thấy "đã chạy,
        không có gì phải dọn").
        """
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            updated = clear_violation_snapshot_paths(CLEANUP_RETENTION_DAYS)
            detail = {
                "retention_days": CLEANUP_RETENTION_DAYS,
                "updated_records": updated,
            }
            log_maintenance_run(
                job_name="_cleanup_job",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                success=True,
                detail=detail,
            )
        except Exception:
            # Re-raise để _run_job_safely bắt và ghi log success=False.
            # KHÔNG nuốt ở đây — đây là nơi thật sự ghi audit khi SUCCESS,
            # nếu để _run_job_safely ghi cả 2 nhánh thì job này sẽ ghi 2 lần.
            # Cách tách: job ghi success=True, _run_job_safely ghi success=False.
            raise

    def _backup_job(self) -> None:
        """
        Backup SQLite online qua `sqlite3.Connection.backup()`.

        Bước 6, đợt 2: chạy song song với cleanup, interval riêng (`BACKUP_INTERVAL_HOURS`).
        Mỗi lần chạy:
          1. Backup `app.db` → `data/backups/app_{timestamp}.db`.
          2. Xóa các file backup cũ hơn N bản gần nhất (`BACKUP_KEEP_COUNT`).
          3. Ghi audit log với danh sách file backup còn lại.

        KHÔNG backup media (`SNAPSHOTS_DIR`) theo mặc định — `BACKUP_MEDIA_ENABLED=False`
        vì dung lượng lớn, không phải ai cũng cần. Bật qua env khi cần.

        Raises re-raise để `_run_job_safely` ghi log success=False khi fail.
        """
        from app.config import BACKUP_MEDIA_ENABLED, SNAPSHOTS_DIR, BASE_DIR

        started_at = datetime.now(timezone.utc).isoformat()
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 1. Backup DB
        ts_filename = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest_db = os.path.join(BACKUP_DIR, f"app_{ts_filename}.db")
        backup_database(dest_db)
        db_size_mb = round(os.path.getsize(dest_db) / (1024 * 1024), 2)

        # 2. (Optional) Backup media — tắt mặc định
        media_backup_path = None
        if BACKUP_MEDIA_ENABLED:
            from shutil import copytree
            media_dest = os.path.join(BACKUP_DIR, f"snapshots_{ts_filename}")
            copytree(SNAPSHOTS_DIR, media_dest, dirs_exist_ok=True)
            media_backup_path = media_dest

        # 3. Dọn backup cũ — giữ BACKUP_KEEP_COUNT bản gần nhất (theo mtime)
        existing = list_backup_files(BACKUP_DIR)
        keep_files = existing[:BACKUP_KEEP_COUNT]
        deleted = []
        for old in existing[BACKUP_KEEP_COUNT:]:
            try:
                os.unlink(old["path"])
                deleted.append(old["filename"])
            except OSError:
                pass

        detail = {
            "backup_file": os.path.basename(dest_db),
            "db_size_mb": db_size_mb,
            "media_backup": media_backup_path,
            "kept_count": len(keep_files),
            "deleted_old": deleted,
        }
        log_maintenance_run(
            job_name="_backup_job",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            detail=detail,
        )


# ─── Module-level singleton (pattern giống _pipelines trong cv/pipeline.py) ───
# FastAPI lifespan khởi động 1 instance duy nhất. Import đâu cũng được cùng
# object — quan trọng cho test: pytest có thể import và gọi start()/stop()
# trên cùng instance đó thay vì tạo mới.
_worker: MaintenanceWorker | None = None


def get_worker() -> MaintenanceWorker | None:
    """Trả về worker hiện tại (None nếu chưa start)."""
    return _worker


def start_maintenance_worker() -> MaintenanceWorker | None:
    """
    Khởi động MaintenanceWorker (idempotent). Trả về None nếu cả CLEANUP_ENABLED
    và BACKUP_ENABLED đều False (không có job nào để chạy — không cần thread).
    Hoặc nếu CV lib không có (parallel với pipeline: nếu pipeline không start
    được thì worker cũng không start — fail together).
    """
    global _worker
    if not CLEANUP_ENABLED and not BACKUP_ENABLED:
        print("[Maintenance] CLEANUP_ENABLED=False & BACKUP_ENABLED=False — skipping worker startup")
        return None
    if _worker is not None:
        return _worker
    _worker = MaintenanceWorker()
    _worker.start()
    return _worker


def stop_maintenance_worker() -> None:
    """Dừng worker (idempotent). Gọi trong FastAPI lifespan shutdown."""
    global _worker
    if _worker is None:
        return
    _worker.stop(timeout=5.0)
    _worker = None
