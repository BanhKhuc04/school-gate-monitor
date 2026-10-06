"""Task 3 — Training jobs API (queue, lifecycle, cancel).

Endpoints:
- GET  /api/training/jobs                  — list jobs (admin)
- POST /api/training/jobs                  — create job (queue)
- GET  /api/training/jobs/{id}             — get job status
- POST /api/training/jobs/{id}/cancel      — cancel job (idempotent)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_role
from app.training import dataset_repo, jobs
from app.training.schemas import SchemaError


router = APIRouter(prefix="/api/training/jobs", tags=["training-jobs"])


class CreateJobIn(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=128)
    target: str = Field(..., pattern="^(plate_ocr|plate_detector|helmet)$")
    config: dict = Field(default_factory=dict)


@router.get("")
def list_jobs(state: Optional[str] = Query(None),
              user: dict = Depends(require_role("admin"))):
    return {"items": dataset_repo.list_jobs(state=state)}


@router.post("")
def create_job(payload: CreateJobIn,
               user: dict = Depends(require_role("admin"))):
    try:
        job_id = jobs.create_job(dataset_id=payload.dataset_id, target=payload.target,
                                  config=payload.config)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job_id}


@router.get("/{job_id}")
def get_job(job_id: str,
            user: dict = Depends(require_role("admin"))):
    job = dataset_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job không tồn tại")
    # Parse config_json nếu có
    if isinstance(job.get("config_json"), str):
        import json
        try:
            job["config"] = json.loads(job["config_json"])
        except Exception:  # noqa: BLE001
            job["config"] = {}
    return job


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str,
               user: dict = Depends(require_role("admin"))):
    try:
        ok = jobs.cancel(job_id)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job_id, "cancelled": ok}