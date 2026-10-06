"""Adapter — kết nối với review API/DB hiện có mà không ghi vào file Task 1/2 giữ.

Mọi thao tác với recognition_reviews/recognition_review_feedback đều qua adapter
này. Adapter dùng API đã có (list_recognition_reviews, get_recognition_review,
record_review_feedback) — KHÔNG tự ý sửa app/db.py hoặc
app/api/recognition_reviews.py. Nếu cần mở rộng contract, ghi patch vào
tasks/task-03/integration/.
"""
from __future__ import annotations

from typing import Optional

from app import db
from app.training import provenance


def _derive_text(review: dict, fb: dict | None) -> str:
    """Trả về target text ưu tiên corrected_text (khi verdict=incorrect) hoặc proposal_canonical."""
    if fb and fb.get("verdict") == "incorrect" and fb.get("corrected_text"):
        return provenance.normalize_plate_text(fb["corrected_text"])
    return provenance.normalize_plate_text(review.get("proposal_canonical") or "")


def _derive_label(review: dict, fb: dict | None) -> dict:
    """Tạo label dict: verdict, target_text, two_line, quality."""
    if fb is None:
        return {
            "verdict": None,
            "target_text": "",
            "corrected_raw": None,
            "top_line": review.get("proposal_top_line"),
            "bottom_line": review.get("proposal_bottom_line"),
            "quality_score": review.get("quality_score"),
        }
    target = _derive_text(review, fb)
    return {
        "verdict": fb["verdict"],
        "target_text": target,
        "corrected_raw": fb.get("corrected_text"),
        "top_line": review.get("proposal_top_line"),
        "bottom_line": review.get("proposal_bottom_line"),
        "quality_score": review.get("quality_score"),
        "reviewer": fb.get("reviewer_username"),
        "reviewed_at": fb.get("created_at"),
        "feedback_id": fb.get("id"),
        "expected_version": fb.get("expected_version"),
    }


def list_reviewed_with_feedback(
    *,
    gate_id: str | None = None,
    camera_id: str | None = None,
    status: str | None = None,
    include_unreadable: bool = False,
    page_size: int = 100,
    max_pages: int = 50,
) -> list[dict]:
    """Trả về list review có feedback (status confirmed/rejected hoặc unreadable nếu include_unreadable).

    Mỗi phần tử có dạng:
      {
        review_id, encounter_id, gate_id, camera_id, run_id,
        source_epoch, frame_seq, observed_at, crop_media_id, crop_sha256,
        proposal_raw, proposal_canonical, proposal_top_line, proposal_bottom_line,
        proposal_confidence, proposal_engine, proposal_model_hash, proposal_config_version,
        quality_score, blur_score, contrast_score, version, status,
        label: {verdict, target_text, corrected_raw, ...},
        feedback_history: [...],
      }

    Pagination: page_size * max_pages = 5000 rows max — đủ cho QA.
    """
    rows: list[dict] = []
    statuses_filter = []
    if status:
        statuses_filter.append(status)
    else:
        statuses_filter = ["confirmed", "rejected"]
    if include_unreadable and "rejected" in statuses_filter:
        # unreadable sẽ là 'rejected' sau record_feedback vì verdict != 'correct'.
        pass
    for st in statuses_filter:
        offset = 0
        for _ in range(max_pages):
            page = db.list_recognition_reviews(
                gate_id=gate_id, camera_id=camera_id, status=st,
                limit=page_size, offset=offset,
            )
            items = page.get("items", [])
            if not items:
                break
            for review in items:
                full = db.get_recognition_review(review["review_id"])
                if not full:
                    continue
                feedbacks = full.get("feedback", [])
                if not feedbacks:
                    continue
                latest_fb = feedbacks[-1]
                if latest_fb["verdict"] in {"unreadable", "not_plate"} and not include_unreadable:
                    continue
                rows.append({
                    **full,
                    "label": _derive_label(full, latest_fb),
                    "feedback_history": feedbacks,
                    "latest_feedback_id": int(latest_fb["id"]),
                })
            if len(items) < page_size:
                break
            offset += page_size
    return rows


def fetch_sample_assets(review_id: str) -> dict | None:
    """Lấy lại review đầy đủ qua DB adapter (không sửa db).

    Returns dict với fields:
      - version: int — review.version
      - latest_feedback_id: int — feedback_id mới nhất đã commit (server-authoritative)
      - label: dict — verdict, target_text, ...
      - feedback_history: list
    """
    full = db.get_recognition_review(review_id)
    if not full:
        return None
    feedbacks = full.get("feedback", [])
    latest_fb = feedbacks[-1] if feedbacks else None
    latest_feedback_id = int(latest_fb["id"]) if latest_fb else 0
    return {
        **full,
        "label": _derive_label(full, latest_fb),
        "feedback_history": feedbacks,
        "latest_feedback_id": latest_feedback_id,
    }


def is_review_superseded(review_id: str, expected_version: int) -> bool:
    """True nếu version hiện tại của review đã vượt expected_version."""
    full = db.get_recognition_review(review_id)
    if full is None:
        return True
    return int(full.get("version", 0)) > int(expected_version)
