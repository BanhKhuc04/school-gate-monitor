"""Task 3 — Candidates API (list, promote, rollback).

Endpoints:
- GET  /api/training/candidates                — list (admin)
- POST /api/training/candidates/{id}/promote   — promote (admin only)
- POST /api/training/candidates/{id}/rollback  — retire current active (admin)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_role
from app.training import dataset_repo, promotion
from app.training.schemas import SchemaError


router = APIRouter(prefix="/api/training/candidates", tags=["training-candidates"])


class PromoteIn(BaseModel):
    expected_metrics: Optional[dict] = None


@router.get("")
def list_candidates(engine: Optional[str] = Query(None),
                    state: Optional[str] = Query(None),
                    user: dict = Depends(require_role("admin"))):
    return {"items": dataset_repo.list_candidates(engine=engine, state=state)}


@router.get("/active")
def get_active(engine: str = Query(..., pattern="^(plate_ocr|plate_detector|helmet)$"),
               user: dict = Depends(require_role("admin"))):
    cand = dataset_repo.get_active_candidate(engine)
    if cand is None:
        return {"engine": engine, "active": None}
    return {"engine": engine, "active": cand}


@router.post("/{candidate_id}/promote")
def promote(candidate_id: str, payload: PromoteIn,
            user: dict = Depends(require_role("admin"))):
    try:
        return promotion.promote(candidate_id, expected_metrics=payload.expected_metrics)
    except SchemaError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rollback")
def rollback(engine: str = Query(..., pattern="^(plate_ocr|plate_detector|helmet)$"),
             user: dict = Depends(require_role("admin"))):
    return promotion.rollback(engine)