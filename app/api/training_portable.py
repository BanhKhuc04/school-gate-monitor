"""Task 3 — Export/Import portable dataset API.

Endpoints:
- POST /api/training/export                  — freeze + export ZIP (admin)
- POST /api/training/import/preview           — preview ZIP diff (admin, multipart)
- POST /api/training/import/apply            — apply import (admin, multipart)

R1 — guard cho tác vụ nặng:
- Import preview/apply giới hạn kích thước upload (multipart) + kiểm tra disk
  trước khi ghi. Giới hạn tổng file + bytes đã có sẵn trong import_portable.
- Export: nếu admin chỉ định `output_path`, path phải nằm trong thư mục quản
  lý (root = TASK3_CONTEXT_PATH/exports) — chống path traversal ra ngoài
  thư mục training. Mặc định ghi vào exports/{dataset_id}.zip.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.auth import require_role
from app.training import (
    dataset_repo,
    export_portable,
    import_portable,
)
from app.training.schemas import SchemaError


router = APIRouter(prefix="/api/training", tags=["training-portable"])

# R1 — giới hạn upload: 1 GiB ZIP + 4 MiB slack cho multipart overhead.
MAX_IMPORT_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB


class ExportIn(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=128)
    output_path: Optional[str] = None


def _staging_dir_root() -> str:
    from app.config import BASE_DIR
    return str(Path(os.environ.get('TASK3_CONTEXT_PATH') or BASE_DIR / 'data' / 'training') / 'imports')


def _exports_root() -> Path:
    """Thư mục gốc cho phép ghi output_path. Tất cả output_path tùy ý phải
    nằm trong cây này. Mặc định trỏ vào TASK3_CONTEXT_PATH/exports/ trên D.
    """
    from app.config import BASE_DIR
    return Path(os.environ.get('TASK3_CONTEXT_PATH') or BASE_DIR / 'data' / 'training') / 'exports'


def _safe_export_path(raw: str) -> Path:
    """Resolve + containment check. Trả về absolute path; raise HTTPException
    400 nếu path ra ngoài exports root hoặc không hợp lệ."""
    if not raw or not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="output_path không hợp lệ")
    candidate = Path(raw)
    # Không cho absolute path / drive letter / UNC; ép về relative vào root
    if candidate.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="output_path phải là đường dẫn tương đối trong thư mục exports/",
        )
    root = _exports_root().resolve()
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="output_path nằm ngoài thư mục exports quản lý",
        )
    return target


@router.post("/export")
def export_zip(payload: ExportIn,
               user: dict = Depends(require_role("admin"))):
    from pathlib import Path
    staging = str(Path(_staging_dir_root()) / "_staging_export")
    # R1 — output_path tùy ý phải nằm trong exports root. None thì auto.
    output_path = None
    if payload.output_path:
        output_path = str(_safe_export_path(payload.output_path))
    try:
        result = export_portable.export_portable_zip(
            dataset_id=payload.dataset_id,
            output_path=output_path,
            staging_dir=staging,
        )
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    zip_path = result["zip_path"] if isinstance(result, dict) else str(result)
    return {
        "dataset_id": payload.dataset_id,
        "zip_path": zip_path,
        "size": os.path.getsize(zip_path) if os.path.exists(zip_path) else 0,
        "asset_count": result.get("asset_count") if isinstance(result, dict) else None,
        "missing_files": result.get("missing_files") if isinstance(result, dict) else None,
        "sample_count": result.get("sample_count") if isinstance(result, dict) else None,
        "expected_with_crop": result.get("expected_with_crop") if isinstance(result, dict) else None,
    }


def _save_upload_streaming(file: UploadFile, dest: Path, max_bytes: int) -> int:
    """Ghi streaming từ UploadFile vào đĩa; dừng ngay khi vượt max_bytes.

    Trả tổng bytes đã ghi. Nếu vượt limit, raise HTTPException 413 và xoá
    file dở dang. Tránh để một upload ZIP 50 GB chiếm C trước khi reject.
    """
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = file.file.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"upload vượt giới hạn {max_bytes} bytes",
                    )
                out.write(chunk)
    finally:
        try:
            file.file.close()
        except Exception:
            pass
    return written


@router.post("/import/preview")
def preview_import(file: UploadFile = File(...),
                   user: str = Depends(require_role("admin"))):
    """Lưu upload vào staging root và trả preview diff.

    R1 — guard: cap upload 1 GiB; require_space trước khi write; cleanup khi lỗi.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="file phải là .zip")
    staging = _staging_dir_root()
    os.makedirs(staging, exist_ok=True)
    saved = os.path.join(staging, f"upload_{os.getpid()}_{os.path.basename(file.filename)}")
    try:
        # Preflight disk trước khi tạo file; MAX_IMPORT_UPLOAD_BYTES là trần.
        from app.storage_budget import require_space
        try:
            require_space(saved, expected_bytes=MAX_IMPORT_UPLOAD_BYTES)
        except ValueError as exc:
            raise HTTPException(status_code=507, detail=f"không đủ dung lượng: {exc}")
        written = _save_upload_streaming(file, Path(saved), MAX_IMPORT_UPLOAD_BYTES)
        result = import_portable.preview_import(saved, staging_root=staging)
        return result.to_dict()
    except import_portable.ImportBlockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(saved)
        except OSError:
            pass


class ApplyImportIn(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=64)


@router.post("/import/apply")
def apply_import(file: UploadFile = File(...),
                 dataset_name: str = Form(..., min_length=1, max_length=64),
                 user: str = Depends(require_role("admin"))):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="file phải là .zip")
    staging = _staging_dir_root()
    os.makedirs(staging, exist_ok=True)
    saved = os.path.join(staging, f"apply_{os.getpid()}_{os.path.basename(file.filename)}")
    try:
        from app.storage_budget import require_space
        try:
            require_space(saved, expected_bytes=MAX_IMPORT_UPLOAD_BYTES)
        except ValueError as exc:
            raise HTTPException(status_code=507, detail=f"không đủ dung lượng: {exc}")
        _save_upload_streaming(file, Path(saved), MAX_IMPORT_UPLOAD_BYTES)
        result = import_portable.apply_import(saved, dataset_name=dataset_name,
                                              staging_root=staging)
        return result
    except import_portable.ImportBlockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(saved)
        except OSError:
            pass
