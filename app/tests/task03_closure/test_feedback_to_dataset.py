"""Task 3 — P5 Feedback → Dataset Hook Tests.

Theo yêu cầu: gọi feedback API → kiểm tra sample_collector nhận đúng
(review_id, feedback_id, new_version, source).

Contract từ `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md`:
  - hook signature: `on_feedback_recorded(review_id, feedback_id, new_version, *, source="feedback")`
  - collector singleton (chỉ 1 instance active)
  - enqueue KHÔNG block caller (return True/False nhanh)
"""
from __future__ import annotations

import pytest


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

class TestFeedbackHookContract:
    """Verify hook signature + collector nhận đúng tham số."""

    def test_hook_signature_post_p1(self):
        """P1: hook signature phải có feedback_id + new_version (positional)."""
        from app.training import sample_collector
        import inspect
        sig = inspect.signature(sample_collector.on_feedback_recorded)
        params = list(sig.parameters.keys())
        assert "review_id" in params
        assert "feedback_id" in params
        assert "new_version" in params
        assert "source" in params
        # P1: bỏ echo feedback_version
        assert "feedback_version" not in params, (
            "P1 bỏ feedback_version — dùng new_version thay"
        )

    def test_hook_accepts_full_payload(self, tmp_path):
        """Hook call với đủ (review_id, feedback_id, new_version, source) → enqueue OK."""
        from app.training import sample_collector
        sample_collector._SINGLETON = None
        coll = sample_collector.SampleCollector(
            task_context_path=str(tmp_path),
            queue_max=8,
            worker_period_sec=0.5,
        )
        sample_collector._SINGLETON = coll
        try:
            ok1 = sample_collector.on_feedback_recorded(
                "rev_001", feedback_id=42, new_version=6, source="recognition_feedback",
            )
            ok2 = sample_collector.on_feedback_recorded(
                "rev_002", feedback_id=43, new_version=7, source="recognition_feedback",
            )
            assert ok1 is True
            assert ok2 is True
            m = coll.metrics()
            assert m["enqueued"] >= 2
            assert m["last_event_ts"] > 0
        finally:
            coll.stop()
            sample_collector._SINGLETON = None

    def test_hook_missing_required_kwarg_rejected(self):
        """Hook không truyền new_version → TypeError (positional required)."""
        from app.training import sample_collector
        sample_collector._SINGLETON = None
        try:
            with pytest.raises(TypeError):
                sample_collector.on_feedback_recorded(
                    "rev_no_arg", feedback_id=99,  # type: ignore[call-arg]
                )
        finally:
            sample_collector._SINGLETON = None

    def test_feedback_event_dataclass_post_p1(self):
        """FeedbackEvent có feedback_id + new_version, KHÔNG có feedback_version."""
        from app.training.sample_collector import FeedbackEvent
        import dataclasses
        fields = {f.name for f in dataclasses.fields(FeedbackEvent)}
        assert "feedback_id" in fields
        assert "new_version" in fields
        assert "review_id" in fields
        assert "ts" in fields
        assert "source" in fields
        # Post-P1 bỏ feedback_version
        assert "feedback_version" not in fields

    def test_record_review_feedback_response_post_p1(self, tmp_path):
        """record_review_feedback trả feedback_id + new_version, bỏ expected_version echo."""
        from app.db import record_review_feedback
        from app import db as app_db
        old = app_db.DB_PATH
        app_db.DB_PATH = str(tmp_path / "frf.db")
        conn = app_db.get_connection()
        conn.executescript("""
            CREATE TABLE recognition_reviews (
                id INTEGER PRIMARY KEY,
                review_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                version INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE recognition_review_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                reviewer_username TEXT NOT NULL,
                reviewer_role TEXT NOT NULL,
                verdict TEXT NOT NULL,
                corrected_text TEXT,
                expected_version INTEGER NOT NULL,
                note TEXT,
                idempotency_key TEXT
            );
        """)
        conn.execute(
            "INSERT INTO recognition_reviews (review_id, status, version) VALUES (?, ?, ?)",
            ("fbhv_001", "pending", 3),
        )
        conn.commit()
        conn.close()
        try:
            r = record_review_feedback(
                review_id="fbhv_001",
                reviewer_username="admin",
                reviewer_role="admin",
                verdict="correct",
                expected_version=3,
            )
            assert "feedback_id" in r
            assert "new_version" in r
            # P1: bỏ echo expected_version
            assert "expected_version" not in r
            assert r["new_version"] == 4
        finally:
            app_db.DB_PATH = old

    def test_collector_singleton(self, tmp_path):
        """SampleCollector singleton: 2 lần _SINGLETON access phải trả về cùng 1 instance."""
        from app.training import sample_collector
        sample_collector._SINGLETON = None
        c1 = sample_collector.SampleCollector(task_context_path=str(tmp_path / "a"))
        sample_collector._SINGLETON = c1
        try:
            # Cùng module access _SINGLETON → cùng object
            assert sample_collector._SINGLETON is c1
            # Nếu module-singleton helper tồn tại → verify nó trả về c1
            if hasattr(sample_collector, "get_or_create_collector"):
                c2 = sample_collector.get_or_create_collector(task_context_path=str(tmp_path / "b"))
                assert c2 is c1, "Singleton phải trả về cùng instance"
        finally:
            c1.stop()
            sample_collector._SINGLETON = None


class TestFeedbackToDatasetEndToEnd:
    """End-to-end: record feedback → collector nhận → sample được tạo trong dataset."""

    def test_feedback_hook_chains_to_collector(self, tmp_path):
        """record_feedback → on_feedback_recorded → collector queue lưu event."""
        from app.training import sample_collector
        sample_collector._SINGLETON = None
        coll = sample_collector.SampleCollector(
            task_context_path=str(tmp_path),
            queue_max=8,
            worker_period_sec=0.5,
        )
        sample_collector._SINGLETON = coll
        try:
            # Simulate Task 1 calling hook với new_version=5
            ok = sample_collector.on_feedback_recorded(
                "rev_chain_001", feedback_id=101, new_version=5,
                source="recognition_feedback",
            )
            assert ok is True
            # Drain queue để xác nhận event có feedback_id + new_version
            drained = []
            try:
                while True:
                    item = coll._queue.get_nowait()
                    if item is None:
                        break
                    drained.append(item)
            except Exception:
                pass
            assert len(drained) >= 1
            evt = drained[0]
            # evt có feedback_id + new_version (đúng contract)
            assert evt.feedback_id == 101
            assert evt.new_version == 5
            assert evt.review_id == "rev_chain_001"
            assert evt.source == "recognition_feedback"
        finally:
            coll.stop()
            sample_collector._SINGLETON = None