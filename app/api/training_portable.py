"""Task 3 — Export/Import portable dataset API.

Endpoints:
- POST /api/training/export                  — freeze + export ZIP (admin)
- POST /api/training/import/preview           — preview ZIP diff (admin, multipart)
- POST /api/training/import/apply            — apply import (admin, multipart)
"""
from __future__ import annotations

import os
import shutil
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


class ExportIn(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=128)
    output_path: Optional[str] = None


def _staging_dir_root() -> str:
    from app.config import BASE_DIR
    return str(BASE_DIR / "data" / "training" / "imports")


@router.post("/export")
def export_zip(payload: ExportIn,
               user: dict = Depends(require_role("admin"))):
    from pathlib import Path
    staging = str(Path(_staging_dir_root()) / "_staging_export")
    try:
        result = export_portable.export_portable_zip(
            dataset_id=payload.dataset_id,
            output_path=payload.output_path,
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


@router.post("/import/preview")
def preview_import(file: UploadFile = File(...),
                   user: str = Depends(require_role("admin"))):
    """Lưu upload vào staging root và trả preview diff."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="file phải là .zip")
    staging = _staging_dir_root()
    os.makedirs(staging, exist_ok=True)
    saved = os.path.join(staging, f"upload_{os.getpid()}_{file.filename}")
    try:
        with open(saved, "wb") as f:
            shutil.copyfileobj(file.file, f)
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
    saved = os.path.join(staging, f"apply_{os.getpid()}_{file.filename}")
    try:
        with open(saved, "wb") as f:
            shutil.copyfileobj(file.file, f)
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