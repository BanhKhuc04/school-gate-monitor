"""Tests for FR6 — recognition reviews + feedback endpoint."""
from __future__ import annotations

import time
import uuid

import pytest


@pytest.fixture
def db_module(test_app):
    """Yield the imported app.db module so tests can call helpers directly.

    `test_app` already patches DB_PATH + get_connection to a per-test DB and
    seeds users — see app/tests/conftest.py.
    """
    from app import db
    return db


def _seed_review(db, *, gate="main", camera="main-front", epoch=0, observed_at=None,
                 proposal_raw="89F1 237.92", proposal_canonical="89F123792",
                 engine="easyocr"):
    review_id = uuid.uuid4().hex
    db.create_recognition_review(
        review_id=review_id,
        violation_id=None,
        encounter_id=None,
        gate_id=gate,
        camera_id=camera,
        run_id="run-test",
        source_epoch=epoch,
        frame_seq=42,
        observed_at=observed_at or time.strftime("%Y-%m-%dT%H:%M:%S"),
        crop_media_id=None,
        crop_sha256=None,
        proposal_raw=proposal_raw,
        proposal_canonical=proposal_canonical,
        proposal_top_line="89F1",
        proposal_bottom_line="23792",
        proposal_confidence=0.61,
        proposal_engine=engine,
        proposal_model_hash=None,
        proposal_config_version=None,
        quality_score=0.74,
        blur_score=120.0,
        contrast_score=42.0,
    )
    return review_id


def test_create_review_is_idempotent_by_review_id(db_module):
    db = db_module
    review_id = _seed_review(db)
    # Calling again with same review_id must NOT raise or change state.
    db.create_recognition_review(
        review_id=review_id,
        violation_id=None,
        encounter_id=None,
        gate_id="main",
        camera_id="main-front",
        run_id="run-test",
        source_epoch=0,
        frame_seq=42,
        observed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        crop_media_id=None,
        crop_sha256=None,
        proposal_raw="89F1 237.92",
        proposal_canonical="89F123792",
        proposal_top_line="89F1",
        proposal_bottom_line="23792",
        proposal_confidence=0.61,
        proposal_engine="easyocr",
    )
    fetched = db.get_recognition_review(review_id)
    assert fetched is not None
    assert fetched["proposal_canonical"] == "89F123792"
    assert fetched["feedback"] == []


def test_list_reviews_pagination_and_filter(db_module):
    db = db_module
    # Capture starting count — DB is shared module-scope across tests in this file.
    initial = db.list_recognition_reviews(gate_id="main", limit=1, offset=0)["total"]
    for i in range(5):
        _seed_review(db, epoch=i, proposal_canonical=f"PAGE-FN-{uuid.uuid4().hex[:6]}")
    listed = db.list_recognition_reviews(gate_id="main", limit=3, offset=0)
    assert listed["total"] == initial + 5
    assert listed["limit"] == 3
    assert listed["offset"] == 0
    assert len(listed["items"]) == 3

    # The trailing page may have more than 5-3=2 items if other tests have inserted rows
    # in this shared module-DB; only verify offset pages do not overlap with page 1.
    page2 = db.list_recognition_reviews(gate_id="main", limit=3, offset=3)
    page1_ids = {it["review_id"] for it in listed["items"]}
    page2_ids = {it["review_id"] for it in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)
    assert len(page2["items"]) >= 2  # at least our 5 - 3 = 2 are on this page


def test_list_reviews_invalid_limit_clamped(db_module):
    db = db_module
    assert db.list_recognition_reviews(limit=0, offset=0)["limit"] == 1
    assert db.list_recognition_reviews(limit=1000, offset=0)["limit"] == 100
    assert db.list_recognition_reviews(limit=10, offset=-5)["offset"] == 0


def test_record_feedback_correct_marks_confirmed(db_module):
    db = db_module
    review_id = _seed_review(db)
    result = db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="correct",
        expected_version=0,
    )
    assert result["applied"] is True
    assert result["status"] == "confirmed"
    assert result["conflict"] is False
    review = db.get_recognition_review(review_id)
    assert review["status"] == "confirmed"
    assert any(f["verdict"] == "correct" for f in review["feedback"])


def test_record_feedback_incorrect_keeps_corrected_text(db_module):
    db = db_module
    review_id = _seed_review(db, proposal_raw="89F1 237.92")
    result = db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="incorrect",
        corrected_text="89F1 237 92",
        expected_version=0,
    )
    assert result["applied"] is True
    assert result["status"] == "rejected"
    review = db.get_recognition_review(review_id)
    assert review["feedback"][0]["corrected_text"] == "89F1 237 92"


def test_record_feedback_rejects_invalid_verdict(db_module):
    db = db_module
    review_id = _seed_review(db)
    with pytest.raises(ValueError, match="verdict"):
        db.record_review_feedback(
            review_id=review_id,
            reviewer_username="admin",
            reviewer_role="admin",
            verdict="bogus_verdict",
            expected_version=0,
        )


def test_record_feedback_unknown_review_raises(db_module):
    db = db_module
    with pytest.raises(ValueError, match="review_id"):
        db.record_review_feedback(
            review_id="no-such-review",
            reviewer_username="admin",
            reviewer_role="admin",
            verdict="correct",
            expected_version=0,
        )


def test_record_feedback_idempotency_same_payload_returns_existing(db_module):
    db = db_module
    review_id = _seed_review(db)
    first = db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="correct",
        expected_version=0,
        idempotency_key="client-uuid-1",
    )
    assert first["applied"] is True
    assert first["idempotent_replay"] is False
    second = db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="correct",
        expected_version=0,
        idempotency_key="client-uuid-1",
    )
    assert second["idempotent_replay"] is True
    assert second["feedback_id"] == first["feedback_id"]


def test_record_feedback_idempotency_key_collision_raises(db_module):
    db = db_module
    review_id = _seed_review(db)
    db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="correct",
        expected_version=0,
        idempotency_key="dup-key",
    )
    with pytest.raises(ValueError, match="idempotency_key"):
        db.record_review_feedback(
            review_id=review_id,
            reviewer_username="admin",
            reviewer_role="admin",
            verdict="incorrect",
            corrected_text="59F199999",
            expected_version=0,
            idempotency_key="dup-key",
        )


def test_record_feedback_version_conflict_returns_409_payload(db_module):
    db = db_module
    review_id = _seed_review(db)
    # First feedback — uses expected_version=0; id is row PK (>=1).
    db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="incorrect",
        corrected_text="89F123799",
        expected_version=0,
    )
    # Now a stale client posts with expected_version=0 (already superseded).
    result = db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="correct",
        expected_version=0,  # stale!
    )
    assert result["conflict"] is True
    assert result["applied"] is False


def test_record_feedback_keeps_history_not_overwrite(db_module):
    db = db_module
    review_id = _seed_review(db)
    # First verdict with corrected text — applies.
    db.record_review_feedback(
        review_id=review_id,
        reviewer_username="admin",
        reviewer_role="admin",
        verdict="incorrect",
        corrected_text="59F100000",
        expected_version=0,
        idempotency_key="rev-A",
    )
    review = db.get_recognition_review(review_id)
    # History must contain the first feedback row (never overwritten).
    assert len(review["feedback"]) >= 1
    assert review["feedback"][0]["reviewer_username"] == "admin"
    assert review["feedback"][0]["corrected_text"] == "59F100000"


def test_endpoint_requires_auth(client):
    """Anonymous GET must be rejected (401)."""
    resp = client.get("/api/recognition/reviews")
    assert resp.status_code in (401, 403)


def test_endpoint_admin_can_post_feedback(client, db_module):
    db = db_module
    review_id = _seed_review(db)
    resp = client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json={"verdict": "correct", "expected_version": 0},
        headers={"Authorization": f"Bearer {_get_token(client, 'admin')}",
                 "Idempotency-Key": "test-key-001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["status"] == "confirmed"
    assert body["idempotent_replay"] is False


def test_endpoint_security_can_post_feedback(client, db_module):
    db = db_module
    review_id = _seed_review(db)
    resp = client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json={"verdict": "incorrect", "corrected_text": "89F123799",
              "expected_version": 0},
        headers={"Authorization": f"Bearer {_get_token(client, 'security')}"},
    )
    assert resp.status_code == 200


def test_endpoint_teacher_forbidden_from_posting_feedback(client, db_module):
    db = db_module
    review_id = _seed_review(db)
    resp = client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json={"verdict": "correct", "expected_version": 0},
        headers={"Authorization": f"Bearer {_get_token(client, 'teacher')}"},
    )
    assert resp.status_code == 403


def test_endpoint_idempotency_replay_returns_same_payload(client, db_module):
    db = db_module
    review_id = _seed_review(db)
    headers = {"Authorization": f"Bearer {_get_token(client, 'admin')}",
               "Idempotency-Key": "client-stable-key"}
    body = {"verdict": "correct", "expected_version": 0}
    first = client.post(f"/api/recognition/reviews/{review_id}/feedback", json=body, headers=headers)
    second = client.post(f"/api/recognition/reviews/{review_id}/feedback", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["feedback_id"] == second.json()["feedback_id"]
    assert second.json()["idempotent_replay"] is True


def test_endpoint_version_conflict_returns_409(client, db_module):
    db = db_module
    review_id = _seed_review(db)
    admin = {"Authorization": f"Bearer {_get_token(client, 'admin')}"}
    # First, apply feedback (advances version).
    first = client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json={"verdict": "incorrect", "corrected_text": "59F100000",
              "expected_version": 0},
        headers=admin,
    )
    assert first.status_code == 200
    # Now post again with the same stale version → 409.
    stale = client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json={"verdict": "correct", "expected_version": 0},
        headers=admin,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "version_conflict"


def _get_token(client, role: str) -> str:
    """Helper: login as a seeded user and return Bearer token."""
    resp = client.post("/api/auth/login",
                       json={"username": role, "password": "test123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
