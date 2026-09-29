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

from app.auth import get_current_user, require_role
from app.db import (
    get_violation_stats,
    get_old_violation_snapshot_paths,
    clear_violation_snapshot_paths,
    list_maintenance_log,
    DB_PATH,
)
from app.config import SNAPSHOTS_DIR

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


class HealthResponse(BaseModel):
    pipeline: dict
    db_size_mb: float
    snapshot_count: int
    snapshot_size_mb: float
    violations_today: int
    gates: list[dict]


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
    }


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
