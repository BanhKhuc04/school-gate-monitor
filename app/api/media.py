"""
D6.2: Media serving endpoint — replaces static /media mount with role-scoped API.

- /api/media/snapshots/{filename} : security/admin/management/teacher (teacher = own class only)
- /api/media/clips/{filename}     : security/admin/management/teacher (teacher = own class only)
- /api/media/student-photos/{filename} : admin only

Path traversal protection: validate path stays within allowed directories.
No static mount for /media in production.
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from app.auth import require_role
from app.config import SNAPSHOTS_DIR


router = APIRouter(prefix="/api/media", tags=["media"])

# Allowed subdirectories within SNAPSHOTS_DIR
_ALLOWED_SUBDIRS = {"snapshots", "clips"}
# Absolute path for student_photos (sibling to snapshots)
_STUDENT_PHOTOS_DIR = os.path.join(
    os.path.dirname(SNAPSHOTS_DIR), "student_photos"
)


def _safe_file_path(subdir: str, filename: str, base_dir: str) -> str:
    from pathlib import Path
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if subdir not in _ALLOWED_SUBDIRS:
        raise HTTPException(status_code=403, detail="Forbidden subdirectory")
    root = Path(base_dir).resolve()
    # Flat paths are current; nested paths support historical media.
    for candidate in (root / filename, root / subdir / filename):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise HTTPException(status_code=400, detail="Invalid filename")
        if resolved.is_file():
            return str(resolved)
    raise HTTPException(status_code=404, detail="File not found")


def _check_class_scope(current_user: dict, filename: str, subdir: str) -> None:
    if current_user.get("role") != "teacher":
        return
    school_class = (current_user.get("homeroom_class") or "").strip()
    if not school_class or subdir not in _ALLOWED_SUBDIRS:
        raise HTTPException(status_code=403, detail="Forbidden")
    from app.db import get_connection
    conn = get_connection()
    try:
        columns = ('snapshot_path', 'crop_snapshot_path') if subdir == 'snapshots' else ('clip_path',)
        conditions, params = [], []
        for column in columns:
            conditions.append(f"(ve.{column} = ? OR substr(replace(ve.{column}, char(92), '/'), -length(?)) = ?)")
            suffix = '/' + filename
            params.extend([filename, suffix, suffix])
        rows = conn.execute(
            "SELECT rv.student_class FROM violation_events ve "
            "LEFT JOIN registered_vehicles rv ON rv.plate_number=ve.plate_matched WHERE "
            + ' OR '.join(conditions), params).fetchall()
        # Ambiguous shared files must not reveal another class's evidence.
        if not rows or any(row['student_class'] != school_class for row in rows):
            raise HTTPException(status_code=403, detail="Forbidden")
    finally:
        conn.close()


# ─── Snapshot endpoint ─────────────────────────────────────────────────────────

@router.get("/snapshots/{filename}")
def serve_snapshot(
    filename: str,
    current_user: dict = Depends(require_role("admin", "security", "management", "teacher")),
):
    """
    Serve a violation snapshot image.
    - admin/security/management: any snapshot
    - teacher: only snapshots belonging to their homeroom class
    """
    _check_class_scope(current_user, filename, "snapshots")
    safe_path = _safe_file_path("snapshots", filename, SNAPSHOTS_DIR)
    return FileResponse(
        safe_path,
        media_type="image/jpeg",
        filename=filename,
    )


# ─── Clip endpoint ──────────────────────────────────────────────────────────────

@router.get("/clips/{filename}")
def serve_clip(
    filename: str,
    current_user: dict = Depends(require_role("admin", "security", "management", "teacher")),
):
    """
    Serve a violation clip (video).
    - admin/security/management: any clip
    - teacher: only clips belonging to their homeroom class
    """
    _check_class_scope(current_user, filename, "clips")
    safe_path = _safe_file_path("clips", filename, SNAPSHOTS_DIR)
    ext = os.path.splitext(filename)[1].lower()
    media_type = "video/mp4" if ext == ".mp4" else "video/x-msvideo"
    return FileResponse(
        safe_path,
        media_type=media_type,
        filename=filename,
    )


# ─── Student photo endpoint ─────────────────────────────────────────────────────

@router.get("/student-photos/{filename}")
def serve_student_photo(
    filename: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Serve a student profile photo — admin only."""
    # Reject any path separator in filename — prevents ../ injection
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    # Student photos: validate path stays within student_photos dir
    from pathlib import Path
    root = Path(_STUDENT_PHOTOS_DIR).resolve()
    safe = str((root / filename).resolve())
    if not Path(safe).is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(safe):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        safe,
        media_type="image/jpeg",
        filename=filename,
    )
