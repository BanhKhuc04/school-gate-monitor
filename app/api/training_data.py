"""Task 3 — Training data API (datasets, samples, splits, freeze).

Endpoint Task 3, độc lập với API admin/guard của Task 1/2. KHÔNG sửa các file
runtime khác.

Endpoints:
- GET  /api/training/datasets              — list datasets (admin only)
- POST /api/training/datasets              — tạo dataset mới
- POST /api/training/datasets/{id}/freeze   — freeze dataset version
- POST /api/training/datasets/{id}/samples — thêm samples (chỉ khi draft)
- GET  /api/training/datasets/{id}/samples — list samples (with optional split filter)
- POST /api/training/datasets/{id}/split   — chia train/val/test theo group
- GET  /api/training/datasets/{id}/leakage — chạy leakage checker
- PATCH /api/training/datasets/{id}/samples/{target_id}/bbox — chỉnh bbox sample
"""
from __future__ import annotations

from typing import Optional
from pathlib import Path
import os
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_role
from app.api.recognition_reviews import list_reviews
from app.training import (
    dataset_freeze,
    dataset_repo,
    label_validator,
    schemas as training_schemas_mod,
    splits,
)
from app.training.schemas import SchemaError, validate_bbox


router = APIRouter(prefix="/api/training", tags=["training"])
# Training clients share the canonical review query and pagination contract.
router.add_api_route(
    "/recognition-reviews", list_reviews, methods=["GET"],
    dependencies=[Depends(require_role("admin"))],
)


# ─── Pydantic models ──────────────────────────────────────────────────────────

class CreateDatasetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    engine: str = Field(..., pattern="^(plate_ocr|plate_detector|helmet)$")
    notes: str = Field("", max_length=512)


class AddSamplesIn(BaseModel):
    samples: list[dict]


class SplitIn(BaseModel):
    seed: int = 42
    ratios: Optional[dict] = None  # mặc định 70/15/15


class PatchBBoxIn(BaseModel):
    bbox: list = Field(..., min_length=4, max_length=4,
                       description="[x1,y1,x2,y2] normalized 0..1")
    expected_version: int = Field(..., ge=0,
                                  description="optimistic version; current sample.version phải khớp")
    reason: str = Field("manual_edit", max_length=64)


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/datasets")
def list_datasets(
    engine: Optional[str] = Query(None),
    user: dict = Depends(require_role("admin")),
):
    return {"items": dataset_repo.list_datasets(engine=engine)}


@router.post("/datasets")
def create_dataset(payload: CreateDatasetIn,
                  user: dict = Depends(require_role("admin"))):
    try:
        ds_id = dataset_repo.create_dataset(
            name=payload.name, engine=payload.engine, notes=payload.notes,
        )
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"dataset_id": ds_id}


@router.post("/datasets/{dataset_id}/freeze")
def freeze_dataset(dataset_id: str,
                   user: dict = Depends(require_role("admin"))):
    try:
        result = dataset_freeze.freeze(dataset_id)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/datasets/{dataset_id}/samples")
def add_samples(dataset_id: str, payload: AddSamplesIn,
                user: dict = Depends(require_role("admin"))):
    try:
        added = dataset_repo.add_samples(dataset_id, payload.samples)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"dataset_id": dataset_id, "added": added}


@router.get("/datasets/{dataset_id}/samples")
def list_samples(dataset_id: str,
                 split: Optional[str] = Query(None, pattern="^(train|val|test)$"),
                 user: dict = Depends(require_role("admin"))):
    items = dataset_repo.list_samples(dataset_id, split=split)
    return {"items": items, "count": len(items)}


@router.get('/datasets/{dataset_id}/samples/{target_id}/image')
def sample_image(dataset_id: str, target_id: str, user: dict = Depends(require_role('admin'))):
    from app.config import BASE_DIR, SNAPSHOTS_DIR
    samples = dataset_repo.list_samples(dataset_id)
    sample = next((s for s in samples if s.get('target_id') == target_id), None)
    if sample is None:
        raise HTTPException(404, 'sample không tồn tại')
    source = sample.get('source') or {}
    path = Path(source.get('crop_media_id') or '').resolve()
    roots = [Path(SNAPSHOTS_DIR).resolve(),
             Path(os.environ.get('TASK3_CONTEXT_PATH') or BASE_DIR / 'data' / 'training').resolve()]
    if not any(path.is_relative_to(root) for root in roots):
        raise HTTPException(400, 'asset ngoài kho dữ liệu đã cấu hình')
    if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise HTTPException(404, 'ảnh mẫu không có sẵn')
    if path.stat().st_size > 16 * 1024 * 1024:
        raise HTTPException(413, 'ảnh mẫu vượt giới hạn')
    expected = source.get('crop_sha256')
    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise HTTPException(409, 'hash ảnh mẫu đã thay đổi')
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})


@router.post("/datasets/{dataset_id}/split")
def run_split(dataset_id: str, payload: SplitIn,
              user: dict = Depends(require_role("admin"))):
    samples = dataset_repo.list_samples(dataset_id)
    if not samples:
        raise HTTPException(status_code=400, detail="dataset rỗng")
    try:
        out = splits.split_by_group(samples, seed=payload.seed,
                                     ratios=payload.ratios)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Cập nhật split vào DB
    for split_name, items in out.items():
        for s in items:
            dataset_repo.set_sample_split(dataset_id, s["target_id"], split_name)
    return {
        "dataset_id": dataset_id,
        "counts": {k: len(v) for k, v in out.items()},
        "stats": splits.dataset_stats([s for items in out.values() for s in items]),
    }


@router.get("/datasets/{dataset_id}/leakage")
def check_leakage(dataset_id: str,
                  user: dict = Depends(require_role("admin"))):
    samples = dataset_repo.list_samples(dataset_id)
    if not samples:
        raise HTTPException(status_code=400, detail="dataset rỗng")
    findings = splits.check_leakage(samples)
    return {"dataset_id": dataset_id, "findings": findings}


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str,
                user: dict = Depends(require_role("admin"))):
    meta = dataset_repo.get_dataset(dataset_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="dataset không tồn tại")
    return meta


@router.post("/datasets/{dataset_id}/verify")
def verify_dataset(dataset_id: str,
                   user: dict = Depends(require_role("admin"))):
    try:
        return dataset_freeze.verify_frozen(dataset_id)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/datasets/{dataset_id}/samples/{target_id}/bbox")
def patch_sample_bbox(dataset_id: str, target_id: str, payload: PatchBBoxIn,
                      user: dict = Depends(require_role("admin"))):
    """Sửa bbox chuẩn hoá cho 1 sample trong dataset (khi dataset còn draft).

    - Optimistic version: expected_version phải khớp sample.version hiện tại
      (chống 2 user cùng sửa 1 sample — bị 409).
    - Sau khi sửa: tăng version, append audit history, KHÔNG đổi target_text,
      KHÔNG đổi verdict. KHÔNG cập nhật recognition_reviews (chỉ sửa bản local
      trong dataset — runtime không tự thay đổi vì plan cấm).
    - Nếu dataset đã frozen → 409 (phải tạo version mới).
    """
    meta = dataset_repo.get_dataset(dataset_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="dataset không tồn tại")
    if meta.get("freeze_state") == "frozen":
        raise HTTPException(
            status_code=409,
            detail="dataset đã frozen — tạo dataset version mới để sửa bbox",
        )
    samples = dataset_repo.list_samples(dataset_id)
    target = next((s for s in samples if s["target_id"] == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="sample không tồn tại")
    current_version = int(target.get("version", 0))
    if current_version != payload.expected_version:
        raise HTTPException(
            status_code=409,
            detail=f"version stale: hiện tại={current_version}, expected={payload.expected_version}",
        )
    # Validate bbox (validate_bbox giữ nguyên bbox nếu hợp lệ, raise nếu invalid)
    try:
        norm = validate_bbox(payload.bbox, path="bbox")
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=f"bbox không hợp lệ: {e}")
    history = list(target.get("bbox_history") or [])
    history.append({
        "prev_bbox": target.get("bbox"),
        "new_bbox": norm,
        "reason": payload.reason,
        "by": user.get("username"),
        "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "version": current_version,
    })
    new_version = current_version + 1
    try:
        dataset_repo.update_sample_bbox(
            dataset_id, target_id, bbox=norm, version=new_version, bbox_history=history,
        )
    except SchemaError as e:
        # Nếu repo raise (vd: dataset bị frozen giữa lúc), chuyển 409
        if "frozen" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "ok": True,
        "target_id": target_id,
        "bbox": norm,
        "version": new_version,
        "history_len": len(history),
    }
