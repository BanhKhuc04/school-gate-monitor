"""F4.3 integration test: POST /feedback gọi on_feedback_recorded đúng params.

Contract (FEEDBACK_HOOK_CONTRACT v1.2):
  - Chỉ gọi khi result["applied"] == True VÀ result["idempotent_replay"] == False
  - feedback_id: server-generated identity (>= 1)
  - new_version: server-authoritative version (DB committed)
  - source: "recognition_feedback"
  - Hook không raise → endpoint không crash
"""
from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest


@pytest.fixture
def db_module(test_app):
    from app import db
    return db


def _seed_review(db, *, gate="main", camera="main-front", epoch=0):
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
        observed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        crop_media_id=None,
        crop_sha256=None,
        proposal_raw="89F1 237.92",
        proposal_canonical="89F123792",
        proposal_top_line="89F1",
        proposal_bottom_line="23792",
        proposal_confidence=0.61,
        proposal_engine="easyocr",
        quality_score=0.74,
        blur_score=120.0,
        contrast_score=42.0,
    )
    return review_id


def _admin_token(client):
    resp = client.post("/api/auth/login",
                       json={"username": "admin", "password": "test123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _post_feedback(client, review_id, token, verdict="correct", expected_version=0,
                  corrected_text=None):
    json_body = {"verdict": verdict, "expected_version": expected_version}
    if corrected_text is not None:
        json_body["corrected_text"] = corrected_text
    return client.post(
        f"/api/recognition/reviews/{review_id}/feedback",
        json=json_body,
        headers={"Authorization": f"Bearer {token}"},
    )


class TestFeedbackHookCalled:
    """on_feedback_recorded được gọi khi feedback lưu thành công."""

    def test_hook_called_with_correct_params(self, client, db_module):
        """feedback_id >= 1, new_version = 1 (first feedback), source = recognition_feedback."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        with patch("app.training.sample_collector.on_feedback_recorded") as mock_hook:
            mock_hook.return_value = True
            resp = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
            assert resp.status_code == 200
            body = resp.json()
            assert body["applied"] is True
            assert body["idempotent_replay"] is False

            # Hook phải được gọi đúng 1 lần
            mock_hook.assert_called_once()
            call_kwargs = mock_hook.call_args.kwargs
            call_args = mock_hook.call_args.args

            # Signature: (review_id, feedback_id, new_version, *, source="feedback")
            # Gọi positional: positional trước, keyword sau
            # Xác minh review_id đúng
            assert call_kwargs.get("review_id") == review_id or (
                len(call_args) >= 1 and call_args[0] == review_id
            ), f"review_id mismatch: {call_kwargs} / {call_args}"

            # feedback_id >= 1
            fid = call_kwargs.get("feedback_id") or (
                len(call_args) >= 2 and call_args[1]
            )
            assert fid is not None and fid >= 1, f"feedback_id must be >= 1, got {fid}"

            # new_version = 1 (first feedback on version 0)
            nv = call_kwargs.get("new_version") or (
                len(call_args) >= 3 and call_args[2]
            )
            assert nv == 1, f"new_version must be 1, got {nv}"

            # source = "recognition_feedback"
            assert call_kwargs.get("source") == "recognition_feedback"

    def test_hook_not_called_on_conflict(self, client, db_module):
        """409 conflict → hook KHÔNG được gọi."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        # First: apply feedback
        resp1 = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
        assert resp1.status_code == 200

        # Second: stale version → 409 conflict
        with patch("app.training.sample_collector.on_feedback_recorded") as mock_hook:
            mock_hook.return_value = True
            resp2 = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
            assert resp2.status_code == 409
            mock_hook.assert_not_called()

    def test_hook_not_called_on_idempotent_replay(self, client, db_module):
        """idempotent_replay=True → hook KHÔNG được gọi lại."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)
        key = "test-idempotent-hook-001"

        # First call
        resp1 = client.post(
            f"/api/recognition/reviews/{review_id}/feedback",
            json={"verdict": "correct", "expected_version": 0},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        assert resp1.status_code == 200
        assert resp1.json()["idempotent_replay"] is False

        # Replay: idempotent_replay=True → hook NOT called
        with patch("app.training.sample_collector.on_feedback_recorded") as mock_hook:
            mock_hook.return_value = True
            resp2 = client.post(
                f"/api/recognition/reviews/{review_id}/feedback",
                json={"verdict": "correct", "expected_version": 0},
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
            )
            assert resp2.status_code == 200
            assert resp2.json()["idempotent_replay"] is True
            mock_hook.assert_not_called()

    def test_hook_exception_does_not_break_endpoint(self, client, db_module):
        """Hook raise exception → KHÔNG làm crash endpoint feedback."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        with patch("app.training.sample_collector.on_feedback_recorded") as mock_hook:
            mock_hook.side_effect = RuntimeError("collector exploded")
            resp = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
            # Endpoint vẫn trả 200
            assert resp.status_code == 200
            body = resp.json()
            assert body["applied"] is True
            assert body["status"] == "confirmed"

    def test_feedback_id_and_new_version_are_server_authoritative(self, client, db_module):
        """Response trả feedback_id và new_version từ DB, không echo input."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        resp = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["conflict"] is False
        # feedback_id >= 1 (server-generated)
        assert "feedback_id" in body
        assert body["feedback_id"] >= 1
        # new_version == 1 (version 0 → 1)
        assert "new_version" in body
        assert body["new_version"] == 1
        # NOT echo input expected_version (which was 0)
        assert body["new_version"] != 0

    def test_multiple_feedback_increments_version(self, client, db_module):
        """2 feedback liên tiếp → new_version tăng 1→2."""
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        resp1 = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
        assert resp1.status_code == 200
        assert resp1.json()["new_version"] == 1
        assert resp1.json()["feedback_id"] >= 1

        fid1 = resp1.json()["feedback_id"]

        # Second feedback: expected_version = 1
        resp2 = _post_feedback(client, review_id, token, verdict="incorrect",
                               corrected_text="89F1 237 99", expected_version=1)
        assert resp2.status_code == 200
        assert resp2.json()["new_version"] == 2
        # feedback_id must be different
        assert resp2.json()["feedback_id"] > fid1

    def test_hook_not_called_when_collector_disabled(self, client, db_module, monkeypatch):
        """Khi TASK3_COLLECTOR_ENABLED=0: hook vẫn được gọi nhưng trả False."""
        # Hook gọi được ngay cả khi collector chưa start (singleton None → return False)
        # Test rằng endpoint không quan tâm kết quả hook
        db = db_module
        review_id = _seed_review(db)
        token = _admin_token(client)

        from app.training import sample_collector
        monkeypatch.setattr(sample_collector, "_SINGLETON", None)

        with patch("app.training.sample_collector.on_feedback_recorded") as mock_hook:
            mock_hook.return_value = False  # collector chưa start
            resp = _post_feedback(client, review_id, token, verdict="correct", expected_version=0)
            assert resp.status_code == 200
            # Hook vẫn được gọi
            mock_hook.assert_called_once()
