"""FR6 — Recognition reviews API.

Endpoints:
- GET  /api/recognition/reviews         — list (paginated, filterable)
- GET  /api/recognition/reviews/{id}    — one review with feedback history
- POST /api/recognition/reviews/{id}/feedback — record verdict

Idempotency via `Idempotency-Key` header. Conflict via `expected_version`.
Verdict set is fixed (correct/incorrect/unreadable/not_plate/wrong_association).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.auth import get_current_user


router = APIRouter(prefix="/api/recognition", tags=["recognition"])


class FeedbackIn(BaseModel):
    verdict: str = Field(..., description="correct|incorrect|unreadable|not_plate|wrong_association")
    corrected_text: Optional[str] = Field(None, max_length=20)
    note: Optional[str] = Field(None, max_length=500)
    expected_version: int = Field(..., ge=0)


@router.get("/reviews")
def list_reviews(
    gate_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    return db.list_recognition_reviews(
        gate_id=gate_id, camera_id=camera_id, status=status,
        limit=limit, offset=offset,
    )


@router.get("/reviews/{review_id}")
def get_review(review_id: str, user: dict = Depends(get_current_user)):
    review = db.get_recognition_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review_id không tồn tại")
    return review


@router.post("/reviews/{review_id}/feedback")
def post_feedback(
    review_id: str,
    payload: FeedbackIn,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(get_current_user),
):
    role = user.get("role")
    # The plan restricts who can mark feedback: admin and security only.
    if role not in ("admin", "security"):
        raise HTTPException(
            status_code=403,
            detail="Chỉ admin hoặc bảo vệ mới có quyền duyệt plate recognition",
        )
    username = user.get("username") or user.get("sub") or "unknown"
    try:
        result = db.record_review_feedback(
            review_id=review_id,
            reviewer_username=username,
            reviewer_role=role,
            verdict=payload.verdict,
            corrected_text=payload.corrected_text,
            note=payload.note,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result.get("conflict"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "version_conflict",
                "current_version": result["new_version"],
                "status": result["status"],
            },
        )
    # F4.3: Task 3 sample collector hook — enqueue only, non-blocking, safe
    if result.get("applied") and not result.get("idempotent_replay"):
        try:
            from app.training.sample_collector import on_feedback_recorded
            on_feedback_recorded(
                review_id=review_id,
                feedback_id=result["feedback_id"],
                new_version=result["new_version"],
                source="recognition_feedback",
            )
        except Exception:
            pass
    return result
