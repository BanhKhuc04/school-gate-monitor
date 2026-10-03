"""Task 3 — Behavioral regression tests for C01-C08 + P1."""
import time
from unittest.mock import MagicMock, patch
import pytest

# ── P1: Hook contract — feedback_id identity (P1) ─────────────────────────────
class TestP1HookContractFeedbackId:
    """P1: hook dùng feedback_id (server-generated) thay echo expected_version."""

    def test_record_review_feedback_returns_feedback_id_and_new_version(self, tmp_path):
        from app.db import record_review_feedback
        from app import db as app_db
        old = app_db.DB_PATH
        app_db.DB_PATH = str(tmp_path / "trf.db")
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
        conn.execute("INSERT INTO recognition_reviews (review_id, status, version) VALUES ('p1','pending',5)")
        conn.commit()
        conn.close()
        try:
            # Client gửi expected=5, server phải trả feedback_id + new_version=6
            r = record_review_feedback(
                review_id="p1",
                reviewer_username="admin",
                reviewer_role="admin",
                verdict="correct",
                expected_version=5,
            )
            assert "feedback_id" in r, "must return feedback_id (server-generated identity)"
            assert r["feedback_id"] >= 1
            assert "new_version" in r, "must return new_version (server-authoritative committed version)"
            assert r["new_version"] == 6, f"new_version phải là version DB đã commit (=6), got {r['new_version']}"
            # KHÔNG dùng echo expected_version làm new_version
            assert r.get("new_version") != 5, "new_version KHÔNG được echo input client (expected_version=5)"
        finally:
            app_db.DB_PATH = old

    def test_idempotent_replay_returns_same_feedback_id(self, tmp_path):
        """Replay cùng idempotency_key → cùng feedback_id, new_version đúng."""
        from app.db import record_review_feedback
        from app import db as app_db
        old = app_db.DB_PATH
        app_db.DB_PATH = str(tmp_path / "trf2.db")
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
        conn.execute("INSERT INTO recognition_reviews (review_id, status, version) VALUES ('p1r','pending',3)")
        conn.commit()
        conn.close()
        try:
            r1 = record_review_feedback(
                review_id="p1r", reviewer_username="u", reviewer_role="r",
                verdict="correct", expected_version=3, idempotency_key="key1",
            )
            r2 = record_review_feedback(
                review_id="p1r", reviewer_username="u", reviewer_role="r",
                verdict="correct", expected_version=3, idempotency_key="key1",
            )
            assert r1["feedback_id"] == r2["feedback_id"], "replay cùng key → cùng feedback_id"
            assert r1["new_version"] == r2["new_version"]
            assert r2.get("idempotent_replay") is True
        finally:
            app_db.DB_PATH = old

    def test_conflict_returns_no_event(self, tmp_path):
        """409 conflict → feedback_id=None, KHÔNG phát event thành công."""
        from app.db import record_review_feedback
        from app import db as app_db
        old = app_db.DB_PATH
        app_db.DB_PATH = str(tmp_path / "trf3.db")
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
        conn.execute("INSERT INTO recognition_reviews (review_id, status, version) VALUES ('p1c','pending',10)")
        conn.commit()
        conn.close()
        try:
            r = record_review_feedback(
                review_id="p1c", reviewer_username="u", reviewer_role="r",
                verdict="correct", expected_version=5,  # stale
            )
            assert r["conflict"] is True
            assert r["feedback_id"] is None, "conflict: feedback_id=None → không phát event"
            assert r["applied"] is False
            assert r["new_version"] == 10, "trả current_version DB để client biết"
        finally:
            app_db.DB_PATH = old

    def test_hook_signature_uses_feedback_id_and_new_version(self):
        """Hook public on_FEedback_recorded phải nhận feedback_id + new_version."""
        from app.training import sample_collector
        import inspect
        sig = inspect.signature(sample_collector.on_feedback_recorded)
        params = list(sig.parameters.keys())
        assert "feedback_id" in params, "hook phải nhận feedback_id (server-generated)"
        assert "new_version" in params, "hook phải nhận new_version (server-authoritative)"
        # Bỏ feedback_version (echo) — KHÔNG dùng echo expected_version
        assert "feedback_version" not in params, "hook KHÔNG dùng feedback_version (echo client)"

    def test_feedback_event_dataclass_has_feedback_id(self):
        from app.training.sample_collector import FeedbackEvent
        import dataclasses
        fields = [f.name for f in dataclasses.fields(FeedbackEvent)]
        assert "feedback_id" in fields
        assert "new_version" in fields
        assert "feedback_version" not in fields, "FeedbackEvent KHÔNG dùng feedback_version"


# ── C02: waiting_resource resume ───────────────────────────────────────────────
class TestC02WaitingResume:
    def test_accepts_waiting_resource(self, training_db):
        from app.training import jobs, dataset_repo
        ds = dataset_repo.create_dataset(name="ds_c02", engine="plate_ocr", db_path=training_db)
        jid = jobs.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=training_db)
        conn = dataset_repo._connect(training_db)
        conn.execute("UPDATE dataset_jobs SET state='waiting_resource' WHERE id=?", (jid,))
        conn.commit(); conn.close()
        mock = MagicMock(return_value={"state": "completed", "metrics": {}})
        with patch("app.training.jobs.can_start_gpu_job", return_value=True):
            result = jobs.run_training_job(jid, runner=mock, db_path=training_db)
        assert result["state"] in {"completed","pending_data","unsupported","failed"}
        mock.assert_called_once()

    def test_rejects_completed(self, training_db):
        from app.training import jobs, dataset_repo
        from app.training.schemas import SchemaError
        ds = dataset_repo.create_dataset(name="ds_c02b", engine="plate_ocr", db_path=training_db)
        jid = jobs.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=training_db)
        conn = dataset_repo._connect(training_db)
        conn.execute("UPDATE dataset_jobs SET state='completed' WHERE id=?", (jid,))
        conn.commit(); conn.close()
        with pytest.raises(SchemaError):
            jobs.run_training_job(jid, runner=MagicMock(), db_path=training_db)

    def test_claim_resumes_waiting(self, training_db):
        from app.training import jobs, dataset_repo
        ds = dataset_repo.create_dataset(name="ds_c02c", engine="plate_ocr", db_path=training_db)
        jid = jobs.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=training_db)
        conn = dataset_repo._connect(training_db)
        conn.execute("UPDATE dataset_jobs SET state='waiting_resource' WHERE id=?", (jid,))
        conn.commit(); conn.close()
        cnt = 0
        def f(j, *, db_path=None):
            nonlocal cnt; cnt += 1
            return {"state": "completed", "metrics": {}}
        with patch("app.training.jobs.can_start_gpu_job", return_value=True):
            result = jobs.claim_and_run_one_waiting_job("plate_ocr", runner=f, db_path=training_db)
        assert result is not None and result["state"] == "completed" and cnt == 1

# ── C03: State reflects runner result ──────────────────────────────────────────
class TestC03StateReflectsResult:
    def _mkjob(self, training_db, name):
        from app.training import jobs, dataset_repo
        ds = dataset_repo.create_dataset(name=name, engine="plate_ocr", db_path=training_db)
        return jobs.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=training_db)

    def test_pending_data_not_completed(self, training_db):
        from app.training import jobs, dataset_repo
        jid = self._mkjob(training_db, "ds_c03a")
        with patch("app.training.jobs.can_start_gpu_job", return_value=True):
            result = jobs.run_training_job(jid, runner=MagicMock(return_value={"state": "pending_data", "note": "holdout<30"}), db_path=training_db)
        assert result["state"] == "pending_data"
        conn = dataset_repo._connect(training_db)
        row = conn.execute("SELECT state FROM dataset_jobs WHERE id=?", (jid,)).fetchone()
        conn.close()
        assert row["state"] == "pending_data"

    def test_unsupported_not_completed(self, training_db):
        from app.training import jobs, dataset_repo
        jid = self._mkjob(training_db, "ds_c03b")
        with patch("app.training.jobs.can_start_gpu_job", return_value=True):
            result = jobs.run_training_job(jid, runner=MagicMock(return_value={"state": "unsupported", "note": "no engine"}), db_path=training_db)
        assert result["state"] == "unsupported"
        conn = dataset_repo._connect(training_db)
        row = conn.execute("SELECT state FROM dataset_jobs WHERE id=?", (jid,)).fetchone()
        conn.close()
        assert row["state"] == "unsupported"

    def test_completed_only_when_runner_completed(self, training_db):
        from app.training import jobs
        jid = self._mkjob(training_db, "ds_c03c")
        with patch("app.training.jobs.can_start_gpu_job", return_value=True):
            result = jobs.run_training_job(jid, runner=MagicMock(return_value={"state": "completed", "metrics": {"exact_match_pct": 0.5}}), db_path=training_db)
        assert result["state"] == "completed"

# ── C04a: Cursor ACK only after copy ───────────────────────────────────────────
class TestC04aCursorAckAfterCopy:
    def test_cursor_not_updated_on_copy_fail(self, sample_collector_factory):
        from app.training.sample_collector import FeedbackEvent
        coll = next(sample_collector_factory(batch_max=32))
        coll.start()
        try:
            def fake(review_id):
                return {"review_id": review_id, "version": 6, "latest_feedback_id": 42, "source": {"crop_media_id": "nonexistent.png"}}
            with patch("app.training.sample_collector.adapter.fetch_sample_assets", fake):
                ev = FeedbackEvent("rev_c04a", feedback_id=42, new_version=6, ts=time.time())
                coll._handle_event(ev)
            assert coll.metrics().get("processed_copy_failed_skipped", 0) >= 1
            assert coll.cursor_state().get("rev_c04a") is None
        finally:
            coll.stop()

# ── C04b: Cursor version comparison ────────────────────────────────────────────
class TestC04bCursorVersionComparison:
    def test_equal_feedback_id_skipped(self, sample_collector_factory):
        """latest_feedback_id == cursor_feedback_id → skipped (already processed)."""
        from app.training.sample_collector import FeedbackEvent
        coll = next(sample_collector_factory(batch_max=32))
        coll.start()
        try:
            coll._cursor["rev_c04b"] = 3
            def fake(review_id):
                return {"review_id": review_id, "version": 6, "latest_feedback_id": 3, "source": {}}
            with patch("app.training.sample_collector.adapter.fetch_sample_assets", fake):
                with patch.object(coll, "_copy_asset_if_needed", return_value=True):
                    ev = FeedbackEvent("rev_c04b", feedback_id=3, new_version=6, ts=time.time())
                    coll._handle_event(ev)
            assert coll.metrics().get("processed_skipped_existing", 0) >= 1
        finally:
            coll.stop()

    def test_newer_feedback_id_processed(self, sample_collector_factory):
        """latest_feedback_id > cursor_feedback_id → processed."""
        from app.training.sample_collector import FeedbackEvent
        coll = next(sample_collector_factory(batch_max=32))
        coll.start()
        try:
            coll._cursor["rev_c04b2"] = 3
            def fake(review_id):
                return {"review_id": review_id, "version": 7, "latest_feedback_id": 5, "source": {}}
            with patch("app.training.sample_collector.adapter.fetch_sample_assets", fake):
                with patch.object(coll, "_copy_asset_if_needed", return_value=True):
                    ev = FeedbackEvent("rev_c04b2", feedback_id=5, new_version=7, ts=time.time())
                    coll._handle_event(ev)
            assert coll.cursor_state().get("rev_c04b2") == 5
        finally:
            coll.stop()

# ── C05a: Cursor-based pagination ──────────────────────────────────────────────
class TestC05aCursorPagination:
    def test_pagination_advances(self, tmp_path):
        from app.training import sample_collector
        items = [{"review_id": f"rev_{i:04d}", "version": i, "source": {}} for i in range(1, 71)]
        mock = MagicMock(return_value=items)
        coll = sample_collector.SampleCollector(task_context_path=str(tmp_path), batch_max=32, adapter_fn=mock)
        # Pagination assumes successful copies; missing crops are retried, not ACKed.
        with patch.object(coll, "_copy_asset_if_needed", return_value=True):
            for expected_count in (32, 64, 70):
                result = coll.run_reconcile_once()
                assert 0 < result["updated"] <= 32
                assert len(coll.cursor_state()) == expected_count
            assert coll.run_reconcile_once()["updated"] == 0
        coll.stop()

# ── C05b: Hook singleton ───────────────────────────────────────────────────────
class TestC05bHookSingleton:
    def test_hook_returns_false_when_not_started(self):
        from app.training import sample_collector
        original = sample_collector._SINGLETON
        sample_collector._SINGLETON = None
        try:
            assert sample_collector.on_feedback_recorded("rv", feedback_id=1, new_version=2) is False
        finally:
            sample_collector._SINGLETON = original

    def test_hook_uses_get_collector(self):
        from app.training import sample_collector
        import inspect
        src = inspect.getsource(sample_collector.on_feedback_recorded)
        assert "get_collector()" in src
        assert "SampleCollector(" not in src

# ── C07a: Real SHA256 verification ────────────────────────────────────────────
class TestC07aRealHashVerify:
    def test_rejects_invalid_format(self, tmp_path):
        from app.training import promotion
        import hashlib
        p = tmp_path / "a.bin"; p.write_bytes(b"x" * 200)
        with pytest.raises(Exception, match="64.*hex|hex"):
            promotion._verify_hash({"model_path": str(p), "model_sha256": "bad"})

    def test_rejects_wrong_hash(self, tmp_path):
        from app.training import promotion
        import hashlib
        p = tmp_path / "m.bin"; p.write_bytes(b"x" * 200)
        with pytest.raises(Exception, match="mismatch"):
            promotion._verify_hash({"model_path": str(p), "model_sha256": "a" * 64})

    def test_accepts_correct_hash(self, tmp_path):
        from app.training import promotion
        import hashlib
        p = tmp_path / "m.bin"; p.write_bytes(b"x" * 200)
        h = hashlib.sha256(b"x" * 200).hexdigest()
        promotion._verify_hash({"model_path": str(p), "model_sha256": h})

    def test_small_file_rejected(self, tmp_path):
        from app.training import promotion
        (tmp_path / "t.bin").write_bytes(b"tiny")
        with pytest.raises(Exception, match="too small|quá nhỏ"):
            promotion._verify_hash({"model_path": str(tmp_path / "t.bin"), "model_sha256": "0" * 64})

# ── C07b: Smoke blocked ────────────────────────────────────────────────────────
class TestC07bSmokeBlocked:
    def test_smoke_model_class_blocked(self, tmp_path):
        from app.training import promotion
        import hashlib
        p = tmp_path / "m.bin"; p.write_bytes(b"x" * 200)
        sha = hashlib.sha256(b"x" * 200).hexdigest()
        with pytest.raises(Exception, match="smoke"):
            promotion._verify_runtime_contract({"model_path": str(p), "model_sha256": sha, "engine": "plate_ocr", "model_class": "EasyOCR_smoke_v1"})

    def test_smoke_metrics_blocked(self, tmp_path):
        from app.training import promotion
        import hashlib
        p = tmp_path / "m.bin"; p.write_bytes(b"x" * 200)
        sha = hashlib.sha256(b"x" * 200).hexdigest()
        cand = {"model_path": str(p), "model_sha256": sha, "engine": "plate_ocr", "model_class": "EasyOCR"}
        with pytest.raises(Exception, match="lifecycle_simulation"):
            promotion._verify_not_smoke({"note": "lifecycle_simulation_run"}, cand)

# ── C01: OCR is evaluator ─────────────────────────────────────────────────────
class TestC01EvaluatorNotTrainer:
    def test_has_evaluator_marker(self):
        from app.training import ocr_trainer
        assert hasattr(ocr_trainer, "IS_EVALUATOR")
        assert ocr_trainer.IS_EVALUATOR is True

    def test_docstring_says_evaluator(self):
        from app.training import ocr_trainer
        assert "EVALUATOR" in (ocr_trainer.__doc__ or "").upper()

    def test_returns_model_path_none(self):
        from app.training import ocr_trainer
        import inspect
        src = inspect.getsource(ocr_trainer.run_ocr_training_job)
        assert '"model_path": None' in src or "'model_path': None" in src

# ── C08: Worker connected ──────────────────────────────────────────────────────
class TestC08WorkerConnected:
    def test_worker_module_exists(self):
        from app.training import worker
        assert hasattr(worker, "start_training_worker")
        assert hasattr(worker, "stop_training_worker")
        assert hasattr(worker, "TrainingWorker")

    def test_worker_selects_ocr(self):
        from app.training import worker
        r = worker._select_runner("plate_ocr")
        assert callable(r)
        # runner có thể là wrapper; kiểm tra target phân giải đúng qua việc gọi
        result = r({"id": "x", "target": "plate_ocr", "dataset_id": "d"}, db_path=None)
        assert isinstance(result, dict)
        assert "state" in result

    def test_worker_rejects_unknown(self):
        from app.training import worker
        from app.training.schemas import SchemaError
        with pytest.raises(SchemaError):
            worker._select_runner("unknown")

# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture
def training_db(tmp_path):
    db = tmp_path / "tr.db"
    from app.training import dataset_repo
    conn = dataset_repo._connect(str(db))
    conn.executescript("""
        CREATE TABLE dataset_jobs (
            id TEXT PRIMARY KEY, dataset_id TEXT, target TEXT,
            config_json TEXT DEFAULT '{}', state TEXT DEFAULT 'queued',
            error TEXT, metrics_path TEXT, log_path TEXT,
            created_at TEXT, updated_at TEXT, finished_at TEXT,
            gpu_resource_id TEXT,
            operation TEXT NOT NULL DEFAULT 'evaluate_baseline',
            runner_type TEXT,
            split_hash TEXT
        );
        CREATE TABLE datasets (
            id TEXT PRIMARY KEY, name TEXT, engine TEXT, schema_version INTEGER,
            created_at TEXT, freeze_state TEXT, notes TEXT
        );
        CREATE TABLE dataset_samples (
            id TEXT PRIMARY KEY, dataset_id TEXT, target_id TEXT,
            text TEXT, holdout INTEGER, split TEXT
        );
        CREATE TABLE dataset_candidates (
            id TEXT PRIMARY KEY, dataset_id TEXT, job_id TEXT, engine TEXT,
            state TEXT DEFAULT 'pending', model_path TEXT, model_sha256 TEXT,
            config_json TEXT, metrics_path TEXT, promoted_at TEXT, retired_at TEXT
        );
    """)
    conn.commit(); conn.close()
    return str(db)

@pytest.fixture
def sample_collector_factory(tmp_path):
    from app.training import sample_collector as sc
    def make(batch_max=32, queue_max=16):
        orig = sc._SINGLETON
        sc._SINGLETON = None
        try:
            path = tmp_path / f"s_{id(tmp_path)}_{time.time()}"
            path.mkdir(parents=True, exist_ok=True)
            yield sc.SampleCollector(task_context_path=str(path), batch_max=batch_max, queue_max=queue_max)
        finally:
            sc._SINGLETON = orig
            sc._SINGLETON = None
    return make
