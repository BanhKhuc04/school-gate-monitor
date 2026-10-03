"""F07 regression tests (Task 1) — late-issue merge preserves existing issues.

F07 review:
> F07 — P1: late issue đang overwrite, không merge và không phân phối update

Tái hiện helper thực với DB adapter giả: ban đầu NO_HELMET, cập nhật muộn
chỉ RIDING_THROUGH_GATE => còn duy nhất RIDING_THROUGH_GATE (BUG).

Sau F07 fix: dispatch_late_issues() đọc issues hiện tại từ DB, merge theo
`code` — issue cũ giữ nguyên (NO_HELMET), issue mới RIDING_THROUGH_GATE
được thêm vào.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _bare_pipeline():
    from app.cv.pipeline import VideoPipeline
    p = VideoPipeline.__new__(VideoPipeline)
    p.gate_id = "main"
    p.camera_id = "main"
    p._crossing_event_to_db_id = {}
    return p


class TestF07LateIssueMerge:
    """F07: dispatch_late_issues must NOT overwrite existing issues."""

    def test_no_helmet_then_riding_preserves_both(self, monkeypatch):
        """Ban đầu NO_HELMET; late update thêm RIDING_THROUGH_GATE
        → merge: [NO_HELMET, RIDING_THROUGH_GATE]."""
        import app.cv.pipeline as pipeline_mod
        import app.db as db_mod

        # Mock DB: read returns NO_HELMET already
        def fake_get_connection():
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = {"issues_json": json.dumps([
                {"code": "NO_HELMET", "status": "confirmed", "sample_count": 4}
            ])}
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn
        monkeypatch.setattr(db_mod, "get_connection", fake_get_connection)
        monkeypatch.setattr(pipeline_mod, "get_connection", fake_get_connection)

        captured_writes = []
        def fake_update(violation_id, **kwargs):
            captured_writes.append((violation_id, kwargs.get("issues_json")))
            return True
        # Note: update_violation_issues is lazy-imported in pipeline.dispatch_late_issues;
        # we patch app.db.update_violation_issues and the test relies on the
        # from-import inside dispatch_late_issues to find it via sys.modules.
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)

        p = _bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99

        new_issues = [{"code": "RIDING_THROUGH_GATE", "status": "confirmed",
                       "sample_count": 4}]
        result = p.dispatch_late_issues("enc-1", new_issues)
        assert result is True
        assert len(captured_writes) == 1
        # Parse and verify
        parsed = json.loads(captured_writes[0][1])
        codes = {it["code"] for it in parsed}
        assert "NO_HELMET" in codes, "existing NO_HELMET must be preserved"
        assert "RIDING_THROUGH_GATE" in codes, "new issue must be added"

    def test_existing_confirmed_not_downgraded_by_pending(self, monkeypatch):
        """Nếu issue cũ là 'confirmed' và issue mới cùng code là 'pending',
        issue cũ giữ nguyên (không bị hạ cấp)."""
        import app.cv.pipeline as pipeline_mod
        import app.db as db_mod

        def fake_get_connection():
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = {"issues_json": json.dumps([
                {"code": "NO_HELMET", "status": "confirmed", "sample_count": 4}
            ])}
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn
        monkeypatch.setattr(db_mod, "get_connection", fake_get_connection)
        monkeypatch.setattr(pipeline_mod, "get_connection", fake_get_connection)

        captured = []
        def fake_update(violation_id, **kwargs):
            captured.append(json.loads(kwargs["issues_json"]))
            return True
        # Note: update_violation_issues is lazy-imported in pipeline.dispatch_late_issues;
        # we patch app.db.update_violation_issues and the test relies on the
        # from-import inside dispatch_late_issues to find it via sys.modules.
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)

        p = _bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99

        # New same-code issue with LOWER status
        new = [{"code": "NO_HELMET", "status": "pending", "sample_count": 2}]
        p.dispatch_late_issues("enc-1", new)
        assert len(captured) == 1
        merged = captured[0]
        helmet = next(it for it in merged if it["code"] == "NO_HELMET")
        assert helmet["status"] == "confirmed", "must not downgrade confirmed"
        assert helmet["sample_count"] == 4, "must keep original sample_count"

    def test_db_failure_returns_false(self, monkeypatch):
        """DB update returns False → dispatch returns False, không báo success."""
        import app.cv.pipeline as pipeline_mod
        import app.db as db_mod

        def fake_get_connection():
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = {"issues_json": "[]"}
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn
        monkeypatch.setattr(db_mod, "get_connection", fake_get_connection)
        monkeypatch.setattr(pipeline_mod, "get_connection", fake_get_connection)

        def fake_update(violation_id, **kwargs):
            return False  # DB said row doesn't exist
        # Note: update_violation_issues is lazy-imported in pipeline.dispatch_late_issues;
        # we patch app.db.update_violation_issues and the test relies on the
        # from-import inside dispatch_late_issues to find it via sys.modules.
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)

        p = _bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99

        result = p.dispatch_late_issues("enc-1",
                                        [{"code": "NO_HELMET", "status": "confirmed"}])
        assert result is False, "DB failure must propagate as False"

    def test_unknown_eid_returns_false(self):
        """Eid không có trong _crossing_event_to_db_id → bỏ qua (idempotent)."""
        p = _bare_pipeline()
        # Empty map → eid not found
        result = p.dispatch_late_issues("missing-eid",
                                        [{"code": "NO_HELMET"}])
        assert result is False

    def test_empty_issues_returns_false(self):
        """new_issues rỗng → bỏ qua."""
        p = _bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99
        result = p.dispatch_late_issues("enc-1", [])
        assert result is False


class TestF07MultipleLateUpdatesAccumulate:
    """F07: nhiều lần dispatch_late_issues() cùng eid tích lũy issues."""

    def test_two_sequential_dispatches_accumulate(self, monkeypatch):
        import app.cv.pipeline as pipeline_mod
        import app.db as db_mod

        # State held outside the closure to simulate DB persistence
        db_state = {"issues_json": json.dumps([
            {"code": "NO_HELMET", "status": "confirmed", "sample_count": 4}
        ])}

        def fake_get_connection():
            conn = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = {"issues_json": db_state["issues_json"]}
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn
        monkeypatch.setattr(db_mod, "get_connection", fake_get_connection)
        monkeypatch.setattr(pipeline_mod, "get_connection", fake_get_connection)

        def fake_update(violation_id, **kwargs):
            # Simulate DB persistence
            db_state["issues_json"] = kwargs["issues_json"]
            return True
        # Note: update_violation_issues is lazy-imported in pipeline.dispatch_late_issues;
        # we patch app.db.update_violation_issues and the test relies on the
        # from-import inside dispatch_late_issues to find it via sys.modules.
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)

        p = _bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99

        # 1st dispatch: add RIDING_THROUGH_GATE
        p.dispatch_late_issues("enc-1", [{"code": "RIDING_THROUGH_GATE",
                                           "status": "confirmed"}])
        # 2nd dispatch: add TOO_MANY_RIDERS
        p.dispatch_late_issues("enc-1", [{"code": "TOO_MANY_RIDERS",
                                           "status": "confirmed"}])

        # Final state: 3 issues (NO_HELMET, RIDING_THROUGH_GATE, TOO_MANY_RIDERS)
        final = json.loads(db_state["issues_json"])
        codes = {it["code"] for it in final}
        assert codes == {"NO_HELMET", "RIDING_THROUGH_GATE", "TOO_MANY_RIDERS"}
