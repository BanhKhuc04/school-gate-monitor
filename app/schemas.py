"""
Pydantic schemas for request/response models.
"""
from typing import Literal
from pydantic import BaseModel, Field


class VehicleIn(BaseModel):
    """Request body for creating/updating a vehicle."""
    plate_number: str
    student_name: str
    student_class: str
    # UT8: hồ sơ hồ sơ mở rộng
    photo_path: str | None = None
    dob: str | None = None  # ISO date string 'YYYY-MM-DD'
    phone: str | None = None
    student_id: str | None = None


class ViolationStatusUpdate(BaseModel):
    """Request body for updating violation status (Feature 10)."""
    status: str | None = None          # 'reviewed' | 'resolved' | 'reopened'
    note: str | None = None
    expected_version: int | None = None  # T2.4 — optimistic concurrency


# ─── Đợt E2.1: Issue + enriched violation schemas ──────────────────────────
# Một lượt xe có thể có nhiều issue (NO_HELMET + PLATE_LOW_CONFIDENCE).
# Mỗi issue có status xác nhận riêng ('confirmed' | 'deferred' | 'conflict' |
# 'pending'), lý do (vì sao evidence chưa đủ), số mẫu và tham chiếu evidence.
IssueStatus = Literal["confirmed", "deferred", "conflict", "pending", "resolved"]


class Issue(BaseModel):
    """Một issue con trong 1 lượt vi phạm (E2.1).
    - code: 'NO_HELMET' | 'NO_PLATE' | 'PLATE_OBSCURED' | 'PLATE_LOW_CONFIDENCE'
            | 'PLATE_NOT_REGISTERED' | 'RIDING_THROUGH_GATE' | 'TOO_MANY_RIDERS'
            | 'MISSING_MIRROR' (review-only ở giai đoạn này)
    - status: trạng thái xác nhận AI
    - reason: lý do ngắn (vd. 'sample_count < 4', 'format mismatch', ...)
    - sample_count: số mẫu evidence đã thu
    - evidence_ref: tham chiếu bằng chứng (vd. ledger key, frame_seq list)"""
    code: str
    status: IssueStatus
    reason: str | None = None
    sample_count: int = 0
    evidence_ref: str | None = None


class EncounterGroup(BaseModel):
    """Một lượt xe gom theo encounter_id (E2.1). Nhiều violation_events có
    cùng encounter_id → cùng một lượt, issues là union (dedup theo code)."""
    encounter_id: str
    gate_id: str | None = None
    observed_at: str | None = None
    plate_read: str | None = None
    plate_matched: str | None = None
    helmet_status: str | None = None
    issues: list[Issue] = Field(default_factory=list)
    # Danh sách record vi phạm thuộc encounter này (mỗi record = 1 lần
    # ghi log; thường 1 record, đôi khi nhiều do helmet/OCR riêng).
    violation_ids: list[int] = Field(default_factory=list)
    snapshot_path: str | None = None
    crop_snapshot_path: str | None = None
    clip_path: str | None = None
    # Trạng thái màu bảng: 'red' (đã xác nhận), 'yellow' (cần kiểm tra),
    # 'gray' (đang kiểm tra), 'resolved' (đã xử lý).
    display_status: str = "gray"


class UserIn(BaseModel):
    """Request body for creating/updating a user (Feature 9)."""
    username: str
    password: str | None = None
    role: str
    homeroom_class: str | None = None


class RosterEntryIn(BaseModel):
    """UT8: 1 mã số sinh viên hợp lệ cho trang /register public."""
    student_id: str
    student_name: str
    student_class: str


class PublicRegisterIn(BaseModel):
    """UT8: body cho POST /api/register (không cần auth — public endpoint).

    Lưu ý: chỉ dùng khi student_id đã được verify hợp lệ qua /api/register/lookup.
    """
    student_id: str
    plate_number: str
    photo_path: str | None = None
    dob: str | None = None
    phone: str | None = None
