"""
System health & maintenance API.

GET  /api/system/health              — pipeline status + DB/storage stats (admin, management)
POST /api/system/snapshots/cleanup   — delete old snapshots + null DB paths (admin only)
GET  /api/system/maintenance-log     — xem lịch sử job tự động (cleanup/backup) — Bước 4
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
import os
import glob
import shutil
import time
from datetime import datetime, timezone

from app.auth import get_current_user, require_role
from app.db import (
    get_violation_stats,
    get_old_violation_snapshot_paths,
    clear_violation_snapshot_paths,
    list_maintenance_log,
    backup_database,
    create_backup_set, list_backup_sets, restore_backup_set,
    DB_PATH,
)
from app.config import SNAPSHOTS_DIR, BACKUP_DIR, BACKUP_KEEP_COUNT, GATES

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/ready", include_in_schema=False)
def get_ready():
    """Readiness tối thiểu — không auth, read-only.

    Dùng cho START_DEMO.ps1 và các health probe bên ngoài. KHÔNG trả
    thông tin nhạy cảm (storage, violation count, disk usage, gates).
    """
    import os as _os
    import sys as _sys
    return {
        "ok": True,
        "service": "school-gate-monitor",
        "version": "2.0.0",
        "pid": _os.getpid(),
        "python": _sys.version.split()[0],
    }

# Phase 0 (Task 1): cache kết quả các phép đo dung lượng (snapshot, disk, breakdown)
# — trước đây `_storage_breakdown()` duyệt toàn bộ thư mục mỗi lần GET /health, poll
# nhiều lần liên tục (mỗi 2–3 giây từ frontend Admin) khiến I/O đĩa tăng không
# cần thiết và có thể chạm network drive chậm. Khoảng cách tối thiểu 60 giây là
# đủ chi tiết cho dashboard quản trị (1 disk lấp bao giờ cũng thay đổi theo ngày).
_STORAGE_CACHE_TTL_SEC = 60.0
# Cache cũng key theo `path` để test monkeypatch SNAPSHOTS_DIR sang tmp_path
# vẫn nhận đúng số liệu (không bị cache stale trả về giá trị thư mục khác).
# `storage_breakdown` mặc định = {} — buộc _storage_breakdown() chạy lần đầu
# (cache hit trả về {} khi key rỗng, sẽ KHÔNG match check truthy ở helper,
# tránh trả ảo "breakdown = {}" cho request đầu).
_storage_cache: dict = {"expires_at": 0.0, "path": "",
                          "snapshot_count": 0, "snapshot_size_mb": 0.0,
                          "storage_breakdown": {}}


def _pipeline_status(gate_id: str = "main") -> dict:
    """Trả về trạng thái pipeline đang hoạt chồng (read-only). KHÔNG tạo
    pipeline mới — health check chỉ được phép đọc, không được nạp model/mở
    camera. Trước đây hàm này gọi `get_pipeline(gate_id)` có thể kích hoạt
    nạp lại model nặng ~6 GB (YOLO) + mở RTSP — đây là lỗi Phase 0 yêu cầu
    sửa: health phải 'chỉ đọc'."""
    try:
        from app.cv.pipeline import get_existing_pipeline
        pipeline = get_existing_pipeline(gate_id)
    except Exception:
        pipeline = None
    if pipeline is None:
        return {
            "running": False,
            "thread_alive": False,
            "camera_open": False,
            "last_frame_age_sec": None,
            "last_detection_age_sec": None,
            "frame_count": 0,
            "uptime_sec": 0,
        }
    try:
        return pipeline.get_status()
    except Exception:
        return {
            "running": False,
            "thread_alive": False,
            "camera_open": False,
            "last_frame_age_sec": None,
            "last_detection_age_sec": None,
            "frame_count": 0,
            "uptime_sec": 0,
        }


def _db_size_mb() -> float:
    """Get DB file size in MB."""
    try:
        if os.path.exists(DB_PATH):
            return round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
    except OSError:
        pass
    return 0.0


def _snapshots_size_mb() -> tuple[int, float]:
    """Get snapshot count and total size in MB. Kết quả được cache theo
    _STORAGE_CACHE_TTL_SEC (60s mặc định) — trước đây hàm này gọi
    glob() + os.path.getsize() cho từng file trong SNAPSHOTS_DIR mỗi poll,
    frontend Admin /health 2–3s/lần có thể đẩy disk I/O lên hàng nghìn
    stat() mỗi phút trên máy có snapshot nặng.
    """
    now = time.monotonic()
    cache_path = _storage_cache.get("path", "")
    if now < _storage_cache["expires_at"] and cache_path == SNAPSHOTS_DIR:
        return _storage_cache["snapshot_count"], _storage_cache["snapshot_size_mb"]
    count, total_size = 0, 0
    if os.path.exists(SNAPSHOTS_DIR):
        for path in glob.glob(os.path.join(SNAPSHOTS_DIR, "*")):
            try:
                total_size += os.path.getsize(path)
                count += 1
            except OSError:
                pass
    size_mb = round(total_size / (1024 * 1024), 2)
    # Cache _snapshots_size_mb() và _storage_breakdown() theo CÙNG path. Khi
    # path đổi (admin test monkeypatch hoặc admin đổi thư mục), 2 cache phải
    # invalidate cùng lúc — lý do: nếu chỉ invalidate size, lần gọi
    # _storage_breakdown() kế tiếp vẫn khớp path mới và trả cache cũ của
    # thư mục trước (đếm nhầm file thật thành 6000+).
    _storage_cache.update({"expires_at": now + _STORAGE_CACHE_TTL_SEC,
                           "path": SNAPSHOTS_DIR,
                           "snapshot_count": count, "snapshot_size_mb": size_mb,
                           "storage_breakdown": {}})
    return count, size_mb


def _disk_usage_mb(path: str) -> dict:
    """
    Dung lượng đĩa thật của phân vùng chứa `path` (thường là SNAPSHOTS_DIR).

    Đợt 2, Bước 5: stdlib `shutil.disk_usage()` — không thêm dependency mới.
    Trả về 3 trường: total/used/free (MB, làm tròn 2 chữ số). Nếu path không
    tồn tại hoặc OS không cho đọc (một số sandbox/container), trả về 0.0 cho
    cả 3 trường — KHÔNG raise — để frontend vẫn render được (hiện "—").
    """
    if not path or not os.path.exists(path):
        return {"disk_total_mb": 0.0, "disk_used_mb": 0.0, "disk_free_mb": 0.0}
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"disk_total_mb": 0.0, "disk_used_mb": 0.0, "disk_free_mb": 0.0}
    mb = 1024 * 1024
    return {
        "disk_total_mb": round(usage.total / mb, 2),
        "disk_used_mb": round(usage.used / mb, 2),
        "disk_free_mb": round(usage.free / mb, 2),
    }


def _storage_breakdown() -> dict:
    """
    Breakdown dung lượng storage theo phần mở rộng file (Đợt 2, Bước 5).

    Hiện tại phân loại:
      - `jpg`: ảnh snapshot vi phạm (`{timestamp}_*.jpg`)
      - `mp4`: clip video vi phạm (`{timestamp}_*.mp4`)
      - `other`: mọi file khác trong SNAPSHOTS_DIR (nếu có)

    Bước 7 sẽ thêm `recordings` cho thư mục `data/recordings/` (ghi hình liên tục).
    Tách riêng theo extension bây giờ để sau không phải sửa frontend.

    Trả về: `{"jpg": {"count": N, "size_mb": M}, "mp4": ..., "other": ...}`.

    Phase 0 (Task 1): cache kết quả theo `_STORAGE_CACHE_TTL_SEC` (60s) — trước
    đây duyệt toàn bộ thư mục mỗi poll, đẩy disk I/O lên cao khi frontend
    Admin /health refresh liên tục. Cache cùng TTL với `_snapshots_size_mb()`
    để đảm bảo consistency giữa 2 phép đo.
    """
    now = time.monotonic()
    cache_path = _storage_cache.get("path", "")
    if (now < _storage_cache["expires_at"]
            and cache_path == SNAPSHOTS_DIR
            and _storage_cache.get("storage_breakdown")):
        return _storage_cache["storage_breakdown"]
    breakdown = {
        "jpg": {"count": 0, "size_mb": 0.0},
        "mp4": {"count": 0, "size_mb": 0.0},
        "other": {"count": 0, "size_mb": 0.0},
    }
    if not os.path.exists(SNAPSHOTS_DIR):
        return breakdown
    for path in glob.glob(os.path.join(SNAPSHOTS_DIR, "*")):
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        size_mb = round(size / (1024 * 1024), 2)
        if ext == "jpg" or ext == "jpeg":
            breakdown["jpg"]["count"] += 1
            breakdown["jpg"]["size_mb"] += size_mb
        elif ext == "mp4":
            breakdown["mp4"]["count"] += 1
            breakdown["mp4"]["size_mb"] += size_mb
        else:
            breakdown["other"]["count"] += 1
            breakdown["other"]["size_mb"] += size_mb
    # Round tổng để tránh floating-point drift (0.1+0.2...)
    for k in breakdown:
        breakdown[k]["size_mb"] = round(breakdown[k]["size_mb"], 2)
    _storage_cache.update({"expires_at": now + _STORAGE_CACHE_TTL_SEC,
                           "path": SNAPSHOTS_DIR,
                           "storage_breakdown": breakdown})
    return breakdown


class HealthResponse(BaseModel):
    pipeline: dict
    db_size_mb: float
    snapshot_count: int
    snapshot_size_mb: float
    violations_today: int
    gates: list[dict]
    # Đợt 2, Bước 5: disk usage thật + breakdown storage theo extension.
    disk_total_mb: float = 0.0
    disk_used_mb: float = 0.0
    disk_free_mb: float = 0.0
    storage_breakdown: dict = {}
    # Đợt 2, Bước 7: trạng thái continuous recording (ẩn khi TẮT).
    recording: dict = {}


@router.get("/health", response_model=HealthResponse)
def get_health(
    current_user: dict = Depends(require_role("admin", "management", "security")),
):
    """
    System health check — pipeline status + storage stats.
    Requires: admin, management, or security role (guards see pipeline/camera
    status on the live view; the storage/violation-count fields are read-only
    and not sensitive, so no separate slim endpoint is worth building for them).
    """
    from app.config import GATES
    try:
        from app.cv.pipeline import get_pipeline
    except Exception:
        pass  # pipeline unavailable (no ultralytics in test env) — skip per-gate status

    stats = get_violation_stats()
    snapshot_count, snapshot_size = _snapshots_size_mb()

    # Build per-gate pipeline status — Phase 0: chỉ đọc pipeline đang tồn tại
    # (không gọi get_pipeline() có thể tạo mới và nạp model + camera).
    gates_status = {}
    try:
        from app.cv.pipeline import get_existing_pipeline as _get_existing_pipeline
    except Exception:
        _get_existing_pipeline = lambda gate_id: None  # noqa: E731 — test env
    for gid in GATES:
        try:
            p = _get_existing_pipeline(gid)
            if p is None:
                gates_status[gid] = {
                    "running": False, "thread_alive": False, "camera_open": False,
                    "last_frame_age_sec": None, "last_detection_age_sec": None,
                    "frame_count": 0, "uptime_sec": 0,
                }
            else:
                gates_status[gid] = p.get_status()
        except Exception:
            gates_status[gid] = {
                "running": False, "thread_alive": False, "camera_open": False,
                "last_frame_age_sec": None, "last_detection_age_sec": None,
                "frame_count": 0, "uptime_sec": 0,
            }

    # Legacy top-level pipeline field — main gate only (backwards compat)
    pipeline_status = gates_status.get("main", {
        "running": False, "thread_alive": False, "camera_open": False,
        "last_frame_age_sec": None, "last_detection_age_sec": None,
        "frame_count": 0, "uptime_sec": 0,
    })

    # Đợt 2, Bước 5: disk usage thật + breakdown storage theo extension.
    # Field cũ (db_size_mb, snapshot_count, snapshot_size_mb, violations_today)
    # KHÔNG đổi giá trị/tên — chỉ thêm field mới phía dưới.
    disk = _disk_usage_mb(SNAPSHOTS_DIR)
    storage_breakdown = _storage_breakdown()

    return {
        "pipeline": pipeline_status,
        "db_size_mb": _db_size_mb(),
        "snapshot_count": snapshot_count,
        "snapshot_size_mb": snapshot_size,
        "violations_today": stats["total_today"],
        "gates": [
            {"id": gid, "name": cfg.get("name", gid), "pipeline": gates_status.get(gid, {})}
            for gid, cfg in GATES.items()
        ],
        # ── Bước 5 additions ──
        "disk_total_mb": disk["disk_total_mb"],
        "disk_used_mb": disk["disk_used_mb"],
        "disk_free_mb": disk["disk_free_mb"],
        "storage_breakdown": storage_breakdown,
        # Đợt 2, Bước 7: trạng thái continuous recording mỗi gate (chỉ hiện nếu BẬT).
        # Nếu TẮT (mặc định), trả {"recording_enabled": False} — frontend ẩn UI.
        "recording": _recording_status_all_gates(),
    }


def _recording_status_all_gates() -> dict:
    """
    Trả về trạng thái recorder cho mọi gate. Đợt 2, Bước 7.
    Khi CONTINUOUS_RECORDING_ENABLED=False (mặc định), chỉ trả flag để frontend biết
    không cần poll UI — KHÔNG đụng vào pipeline (tránh import cv2 khi test env).
    """
    from app.config import CONTINUOUS_RECORDING_ENABLED
    if not CONTINUOUS_RECORDING_ENABLED:
        return {"enabled": False}
    try:
        from app.cv.pipeline import get_existing_pipeline
    except ImportError:
        return {"enabled": True, "error": "pipeline unavailable"}
    result = {"enabled": True, "gates": {}}
    for gid in GATES:
        try:
            # Phase 0: chỉ đọc pipeline đang tồn tại; không tạo pipeline mới
            # (tránh nạp model + mở camera khi admin bấm /health mà pipeline
            # trước đó chưa khởi động — đặc biệt quan trọng khi restart).
            p = get_existing_pipeline(gid)
            if p is not None and getattr(p, '_recorder', None) is not None:
                result["gates"][gid] = p._recorder.get_stats()
        except Exception as e:
            result["gates"][gid] = {"error": str(e)}
    return result


class CleanupResponse(BaseModel):
    """Cleanup response shape.

    R1 — đã hợp nhất với `clear_violation_snapshot_paths()`:
    - `deleted_files` / `updated_records` là alias tương thích ngược (cộng từ
      `deleted` / tổng số record vi phạm đã chạm).
    - `deleted`, `missing`, `failed`, `held`, `attempted`, `paths_failed`,
      `dry_run`, `duration_ms` phản ánh số liệu THỰC TẾ từ helper — không
      mặc định 0 để che lỗi.
    - Field mới `dry_run` để admin/test kiểm tra trước khi xóa thật.
    """
    deleted_files: int
    updated_records: int
    deleted: int
    missing: int
    failed: int
    held: int
    attempted: int
    paths_failed: list  # list[dict{path,reason}] — error path + lý do
    dry_run: bool
    duration_ms: int


@router.post("/snapshots/cleanup", response_model=CleanupResponse)
def cleanup_old_snapshots(
    older_than_days: int = 90,
    dry_run: bool = False,
    current_user: dict = Depends(require_role("admin")),
):
    """
    R1 — Cleanup an toàn từ API đến file và DB.

    Quy tắc:
    - KHÔNG tự unlink trong route — toàn bộ thao tác xóa đi qua
      `clear_violation_snapshot_paths()` đã có hold/root/retry/symlink guard.
    - Validate path root, không xóa path ngoài SNAPSHOTS_DIR (cả resolve symlink).
    - PermissionError/OSError giữ liên kết DB để retry; không NULL snapshot_path.
    - Bỏ qua record `evidence_state='hold'`; đếm `held`.
    - Hỗ trợ `dry_run=true`: đếm file sẽ xóa nhưng KHÔNG đụng DB/disk.
    - Response thể hiện partial failure; `failed > 0` không che bằng 0.
    """
    if older_than_days < 1 or older_than_days > 3650:
        raise HTTPException(status_code=422, detail="older_than_days must be 1-3650")

    started = time.monotonic()
    # Delegate toàn bộ xóa cho helper an toàn — route chỉ thêm dry_run wrapper
    # và truyền tham số. Helper đã validate root, bỏ hold, retry partial failure.
    cleanup_result = clear_violation_snapshot_paths(
        older_than_days=older_than_days,
        dry_run=dry_run,
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    deleted = int(cleanup_result.get("deleted", 0))
    missing = int(cleanup_result.get("missing", 0))
    failed = int(cleanup_result.get("failed", 0))
    held = int(cleanup_result.get("held", 0))
    attempted = int(cleanup_result.get("attempted", 0))
    paths_failed = list(cleanup_result.get("paths_failed", []) or [])

    # updated_records = số path đã được update DB (xóa thành công + null vì missing).
    # Không tính held (giữ nguyên) và failed (giữ nguyên).
    if dry_run:
        # dry_run không update DB → updated_records = 0
        updated_records = 0
    else:
        updated_records = deleted + missing

    # deleted_files = deleted (số file xóa thật).
    # deleted = same as deleted_files (alias cho caller cũ).
    return {
        "deleted_files": deleted,
        "updated_records": updated_records,
        "deleted": deleted,
        "missing": missing,
        "failed": failed,
        "held": held,
        "attempted": attempted,
        "paths_failed": paths_failed,
        "dry_run": bool(dry_run),
        "duration_ms": duration_ms,
    }


# ─── Feature 8 (backend): Preview snapshot cleanup ───────────────────────────────

@router.get("/snapshots/preview")
def preview_snapshot_cleanup(
    older_than_days: int = Query(default=90, ge=1, le=3650),
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/system/snapshots/preview — xem trước số file + dung lượng trước khi dọn.
    Feature 8.
    """
    if older_than_days < 1 or older_than_days > 3650:
        raise HTTPException(status_code=422, detail="older_than_days must be 1-3650")

    from app.db import get_old_violation_media_paths
    snapshot_paths, clip_paths = get_old_violation_media_paths(older_than_days)
    total_size = 0
    for paths in [snapshot_paths, clip_paths]:
        for path in paths:
            full = path if os.path.isabs(path) else os.path.join(SNAPSHOTS_DIR, os.path.basename(path))
            try:
                if os.path.exists(full):
                    total_size += os.path.getsize(full)
            except OSError:
                pass
    return {
        "file_count": len(snapshot_paths) + len(clip_paths),
        "snapshot_count": len(snapshot_paths),
        "clip_count": len(clip_paths),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }


# ─── Đợt 2, Bước 4: Maintenance log (audit trail cho job tự động) ─────────────

@router.get("/maintenance-log")
def get_maintenance_log(
    limit: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/system/maintenance-log — xem lịch sử chạy job tự động
    (cleanup cũ, backup — Bước 6). Admin-only vì đây là thông tin vận hành
    nội bộ, không liên quan tới phụ huynh/giáo viên.
    Tái dùng pattern list đơn giản giống get_violation_audit_log.
    """
    return list_maintenance_log(limit=limit)


# ─── Đợt 2, Bước 6: Backup SQLite online (admin) ─────────────────────────────

class BackupRunResponse(BaseModel):
    set_dir: str
    db_file: str | None = None
    db_size_mb: float
    media_count: int
    files_total: int
    complete: bool


@router.post("/backup/run", response_model=BackupRunResponse)
def run_backup_now(
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/system/backup/run — chạy backup NGAY (không chờ lịch).

    Dùng R3 helper `create_backup_set` — tạo bộ backup DB + media + manifest
    + complete marker atomic (xem `app/db.py::create_backup_set`).

    Trả về set_dir + file DB bên trong. UI/CLI có thể dùng set_dir để
    restore hoặc verify.

    R1 — preflight disk trước khi backup: estimate dựa trên size hiện có của
    DB + media dir. Nếu thiếu chỗ cho output + reserve (10 GiB) → 507 + lý do.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    photos_root = os.path.join(os.path.dirname(SNAPSHOTS_DIR), "student_photos")
    photos_arg = photos_root if os.path.isdir(photos_root) else None

    # R1 — preflight disk: estimate tổng bytes DB + snapshots + photos
    estimated = 0
    try:
        if os.path.exists(DB_PATH):
            estimated += os.path.getsize(DB_PATH)
    except OSError:
        pass
    if os.path.isdir(SNAPSHOTS_DIR):
        for root, _dirs, files in os.walk(SNAPSHOTS_DIR):
            for fname in files:
                try:
                    estimated += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    pass
    if photos_arg and os.path.isdir(photos_arg):
        for root, _dirs, files in os.walk(photos_arg):
            for fname in files:
                try:
                    estimated += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    pass
    from app.storage_budget import require_space
    try:
        require_space(BACKUP_DIR, expected_bytes=estimated + 64 * 1024 * 1024)
    except ValueError as exc:
        raise HTTPException(status_code=507, detail=f"không đủ dung lượng: {exc}")

    result = create_backup_set(
        backup_root=BACKUP_DIR,
        snapshots_dir=SNAPSHOTS_DIR,
        student_photos_dir=photos_arg,
        include_media=True,
        label="manual",
    )
    db_size_mb = round(
        sum(f["size_bytes"] for f in result["files"]
            if f.get("role") == "db") / (1024 * 1024),
        2,
    )
    media_count = sum(1 for f in result["files"]
                      if f.get("role") in ("media", "photo"))
    return {
        "set_dir": os.path.basename(result["set_dir"]),
        "db_file": result["db_file"],
        "db_size_mb": db_size_mb,
        "media_count": media_count,
        "files_total": len(result["files"]),
        "complete": result["complete"],
    }


@router.get("/backup/list")
def list_backups(
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/system/backup/list — liệt kê bộ backup đầy đủ (R3), mới nhất trước.

    Mỗi entry: set_dir, db_file, media_dir, manifest_file, complete, files_count.
    Chỉ trả về bộ có complete marker; bộ đang dở KHÔNG xuất hiện.
    """
    return list_backup_sets(BACKUP_DIR)
