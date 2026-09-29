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
from datetime import datetime, timezone

from app.auth import get_current_user, require_role
from app.db import (
    get_violation_stats,
    get_old_violation_snapshot_paths,
    clear_violation_snapshot_paths,
    list_maintenance_log,
    backup_database, list_backup_files,
    DB_PATH,
)
from app.config import SNAPSHOTS_DIR, BACKUP_DIR, BACKUP_KEEP_COUNT

router = APIRouter(prefix="/api/system", tags=["system"])


def _pipeline_status(gate_id: str = "main") -> dict:
    """Get pipeline health status for a given gate (returns safe defaults if not running)."""
    try:
        from app.cv.pipeline import get_pipeline
        pipeline = get_pipeline(gate_id)
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
    """Get snapshot count and total size in MB."""
    total_size = 0
    count = 0
    if os.path.exists(SNAPSHOTS_DIR):
        for path in glob.glob(os.path.join(SNAPSHOTS_DIR, "*")):
            try:
                total_size += os.path.getsize(path)
                count += 1
            except OSError:
                pass
    return count, round(total_size / (1024 * 1024), 2)


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
    """
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

    # Build per-gate pipeline status
    gates_status = {}
    for gid, cfg in GATES.items():
        gates_status[gid] = _pipeline_status(gid)

    # Legacy top-level pipeline field — main gate only (backwards compat)
    pipeline_status = gates_status.get("main", _pipeline_status("main"))

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
        from app.cv.pipeline import get_pipeline
    except ImportError:
        return {"enabled": True, "error": "pipeline unavailable"}
    result = {"enabled": True, "gates": {}}
    for gid in GATES:
        try:
            p = get_pipeline(gid)
            if p is not None and p._recorder is not None:
                result["gates"][gid] = p._recorder.get_stats()
        except Exception as e:
            result["gates"][gid] = {"error": str(e)}
    return result


class CleanupResponse(BaseModel):
    deleted_files: int
    updated_records: int


@router.post("/snapshots/cleanup", response_model=CleanupResponse)
def cleanup_old_snapshots(
    older_than_days: int = 90,
    current_user: dict = Depends(require_role("admin")),
):
    """
    Delete snapshot files older than N days and null their paths in DB.
    Requires: admin role only.
    """
    if older_than_days < 1 or older_than_days > 3650:
        raise HTTPException(status_code=422, detail="older_than_days must be 1-3650")

    from app.db import get_old_violation_media_paths
    snapshot_paths, clip_paths = get_old_violation_media_paths(older_than_days)
    all_paths = snapshot_paths + clip_paths

    deleted_files = 0
    for path in all_paths:
        full_path = path if os.path.isabs(path) else os.path.join(SNAPSHOTS_DIR, os.path.basename(path))
        try:
            if os.path.exists(full_path):
                os.unlink(full_path)
                deleted_files += 1
        except OSError:
            pass

    updated_records = clear_violation_snapshot_paths(older_than_days)

    return {
        "deleted_files": deleted_files,
        "updated_records": updated_records,
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
    backup_file: str
    db_size_mb: float


@router.post("/backup/run", response_model=BackupRunResponse)
def run_backup_now(
    current_user: dict = Depends(require_role("admin")),
):
    """
    POST /api/system/backup/run — chạy backup NGAY (không chờ lịch).
    Dùng khi admin muốn snapshot DB trước khi thay đổi lớn (migration, sửa code...).
    Tái dùng style route như cleanup preview/run đã có.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"app_{ts}.db")
    backup_database(dest)
    size_mb = round(os.path.getsize(dest) / (1024 * 1024), 2)
    return {"backup_file": os.path.basename(dest), "db_size_mb": size_mb}


@router.get("/backup/list")
def list_backups(
    current_user: dict = Depends(require_role("admin")),
):
    """
    GET /api/system/backup/list — liệt kê file backup, mới nhất trước.
    """
    return list_backup_files(BACKUP_DIR)
