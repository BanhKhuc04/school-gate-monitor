"""Task 3 — P5 Additional Tests.

3 file riêng (NaN gate, Artifact loadable, Feedback to dataset) đã có ở:
  - test_promotion_nan_gate.py
  - test_promotion_artifact_loadable.py
  - test_feedback_to_dataset.py

File này giữ:
  - Provenance snapshot verification (dataset_snapshot + split_hash)
  - Runner contract documented (CODE_PARTIAL markers)
  - R5 training loop end-to-end với operation='train'
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _populate_training_db(db_path: str) -> None:
    from app import db as app_db
    app_db.DB_PATH = db_path
    conn = app_db.get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            engine TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            freeze_state TEXT NOT NULL DEFAULT 'draft',
            manifest_path TEXT,
            source_hash TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS dataset_samples (
            dataset_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            sample_json TEXT NOT NULL,
            split TEXT NOT NULL DEFAULT 'train',
            holdout INTEGER NOT NULL DEFAULT 0,
            review_id TEXT,
            added_at TEXT NOT NULL,
            PRIMARY KEY (dataset_id, target_id)
        );
        CREATE TABLE IF NOT EXISTS dataset_jobs (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            target TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            config_json TEXT,
            log_path TEXT,
            metrics_path TEXT,
            error TEXT,
            gpu_resource_id TEXT,
            operation TEXT NOT NULL DEFAULT 'evaluate_baseline',
            runner_type TEXT,
            split_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS dataset_candidates (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL DEFAULT '',
            engine TEXT NOT NULL,
            target TEXT NOT NULL,
            model_class TEXT NOT NULL,
            model_path TEXT NOT NULL,
            model_sha256 TEXT,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            promoted_at TEXT,
            retired_at TEXT,
            state TEXT NOT NULL DEFAULT 'candidate',
            metrics_path TEXT
        );
        CREATE TABLE IF NOT EXISTS gpu_resources (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            kind TEXT NOT NULL,
            state TEXT NOT NULL,
            holder TEXT,
            last_heartbeat_at TEXT,
            current_job_id TEXT
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture
def training_db(tmp_path):
    db = str(tmp_path / "p5_training.db")
    _populate_training_db(db)
    return db


def _make_loadable_artifact(path: Path) -> str:
    import torch  # type: ignore
    torch.save({"weights": "fake_state_8s"}, str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_metrics_file(path: Path, *, model_sha="", dataset_id="",
                       extra: dict | None = None) -> str:
    data = {
        "total": 30,
        "exact_match_pct": 90.0,
        "cer_avg": 0.05,
        "model_sha256": model_sha,
        "dataset_id": dataset_id,
    }
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _complete_job_with_metrics(db_path: str, job_id: str, metrics_path: str) -> None:
    import sqlite3
    c = sqlite3.connect(db_path)
    c.execute(
        "UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
        "metrics_path=?, runner_type='train' WHERE id=?",
        (metrics_path, job_id),
    )
    c.commit()
    c.close()


# ──────────────────────────────────────────────────────────────────────────
# P5 — Provenance: dataset_snapshot + split_hash
# ──────────────────────────────────────────────────────────────────────────

class TestPromotionProvenanceSnapshot:
    """P5: metrics có dataset_snapshot → verify hash hiện tại match."""

    def test_metrics_snapshot_mismatch_rejected(self, tmp_path, training_db):
        """Snapshot sai → reject."""
        from app.training import dataset_repo, promotion
        from app.training.schemas import SchemaError
        ds = dataset_repo.create_dataset(name="ds_p5", engine="plate_ocr", db_path=training_db)
        dataset_repo.add_samples(ds, [{
            "target_id": "s1", "review_id": "r1", "gate_id": "g1",
            "split": "train", "holdout": False,
            "label": {"verdict": "correct", "target_text": "ABC123"},
            "source": {"gate_id": "g1"},
        }], db_path=training_db)
        job = dataset_repo.create_job(
            dataset_id=ds, target="plate_ocr", config={}, db_path=training_db,
            operation="train",
        )
        art = tmp_path / "model.bin"
        sha = _make_loadable_artifact(art)
        mp = tmp_path / "metrics.json"
        _make_metrics_file(mp, model_sha=sha, dataset_id=ds,
                           extra={"dataset_snapshot": "0" * 64,
                                  "split_hash": "0" * 64})
        cand = dataset_repo.create_candidate(
            job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
            model_class="EasyOCR.engine.plate_ocr", model_path=str(art),
            model_sha256=sha,
            config={"class_mapping": {"alphabet": "ABC"}},
            metrics_path=str(mp), db_path=training_db,
        )
        _complete_job_with_metrics(training_db, job, str(mp))
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        msg = str(ei.value).lower()
        assert "snapshot" in msg or "split_hash" in msg

    def test_metrics_correct_snapshot_passes(self, tmp_path, training_db):
        """Snapshot + split_hash đúng → pass gate."""
        from app.training import dataset_repo, promotion, provenance as _prov
        ds = dataset_repo.create_dataset(name="ds_p5_ok", engine="plate_ocr", db_path=training_db)
        dataset_repo.add_samples(ds, [
            {"target_id": "s1", "review_id": "r1", "gate_id": "g1",
             "split": "train", "holdout": False,
             "label": {"verdict": "correct", "target_text": "ABC123"},
             "source": {"gate_id": "g1"}},
            {"target_id": "s2", "review_id": "r2", "gate_id": "g2",
             "split": "val", "holdout": True,
             "label": {"verdict": "correct", "target_text": "XYZ987"},
             "source": {"gate_id": "g2"}},
        ], db_path=training_db)
        ds_row = dataset_repo.get_dataset(ds, db_path=training_db)
        samples = dataset_repo.list_samples(ds, db_path=training_db)
        split_map = {s.get("target_id", ""): s.get("split", "train") for s in samples}
        real_split_hash = _prov.compute_split_hash(samples=samples, split_map=split_map)
        real_snapshot = _prov.compute_dataset_snapshot(
            dataset_id=ds, samples=samples,
            freeze_state=ds_row.get("freeze_state", "draft"),
            source_hash=ds_row.get("source_hash"),
        )
        job = dataset_repo.create_job(
            dataset_id=ds, target="plate_ocr", config={}, db_path=training_db,
            operation="train",
        )
        art = tmp_path / "model.bin"
        sha = _make_loadable_artifact(art)
        mp = tmp_path / "metrics.json"
        _make_metrics_file(mp, model_sha=sha, dataset_id=ds,
                           extra={"dataset_snapshot": real_snapshot,
                                  "split_hash": real_split_hash})
        cand = dataset_repo.create_candidate(
            job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
            model_class="EasyOCR.engine.plate_ocr", model_path=str(art),
            model_sha256=sha,
            config={"class_mapping": {"alphabet": "ABC"}},
            metrics_path=str(mp), db_path=training_db,
        )
        _complete_job_with_metrics(training_db, job, str(mp))
        result = promotion.promote(cand, db_path=training_db)
        assert result["state"] == "pending_runtime"


# ──────────────────────────────────────────────────────────────────────────
# P5 — Runner contract thống nhất
# ──────────────────────────────────────────────────────────────────────────

class TestRunnerContractDocumented:
    """P5: runner.py có CODE_STATUS marker cho từng target."""

    def test_runner_module_has_code_status_for(self):
        from app.training import runner as runner_mod
        assert hasattr(runner_mod, "code_status_for")
        assert runner_mod.code_status_for("plate_ocr") == "CODE_COMPLETE"
        assert runner_mod.code_status_for("plate_detector") == "CODE_PARTIAL"
        assert runner_mod.code_status_for("helmet") == "CODE_PARTIAL"
        assert runner_mod.code_status_for("unknown_target") == "CODE_NOT_IMPLEMENTED"

    def test_runner_module_has_list_supported_targets(self):
        from app.training import runner as runner_mod
        targets = runner_mod.list_supported_targets()
        assert "plate_ocr" in targets
        assert "plate_detector" in targets
        assert "helmet" in targets

    def test_runner_docstring_marks_partial_targets(self):
        """Đọc nội dung runner.py và verify CODE_PARTIAL cho detector/helmet."""
        from pathlib import Path
        runner_path = Path(__file__).resolve().parents[3] / "app" / "training" / "runner.py"
        txt = runner_path.read_text(encoding="utf-8")
        assert "CODE_PARTIAL" in txt
        assert "plate_detector" in txt
        assert "helmet" in txt
        assert "REOPEN" in txt

    def test_plate_detector_runner_unsupported(self, training_db):
        """plate_detector runner trả unsupported + code_line_marker=CODE_PARTIAL."""
        from app.training import runner as runner_mod
        runner = runner_mod.select_runner("plate_detector")
        result = runner(
            {"id": "j", "target": "plate_detector", "dataset_id": "d"},
            db_path=training_db,
        )
        assert result["state"] == "unsupported"
        assert "code_partial" in result["note"].lower()
        assert result["code_line_marker"] == "CODE_PARTIAL"

    def test_helmet_runner_unsupported(self, training_db):
        """helmet runner trả unsupported + code_line_marker=CODE_PARTIAL."""
        from app.training import runner as runner_mod
        runner = runner_mod.select_runner("helmet")
        result = runner(
            {"id": "j", "target": "helmet", "dataset_id": "d"},
            db_path=training_db,
        )
        assert result["state"] == "unsupported"
        assert "code_partial" in result["note"].lower()
        assert result["code_line_marker"] == "CODE_PARTIAL"

    def test_worker_uses_runner_module(self):
        """worker._select_runner delegate xuống runner.py."""
        from app.training import worker as worker_mod
        from app.training import runner as runner_mod
        assert worker_mod._select_runner("plate_detector") is runner_mod._run_detector_job
        assert worker_mod._select_runner("helmet") is runner_mod._run_helmet_job


# ──────────────────────────────────────────────────────────────────────────
# P5 — R5 training loop end-to-end (operation='train')
# ──────────────────────────────────────────────────────────────────────────

class TestR5TrainingLoopFlow:
    """P5: tạo dataset draft + operation='train' (KHÔNG evaluate_baseline) →
    candidate state=pending_runtime."""

    def test_training_operation_e2e(self, tmp_path, training_db):
        """End-to-end: dataset draft + operation='train' → candidate pending_runtime."""
        from app.training import dataset_repo, jobs as jobs_mod
        from app.training import evaluator, worker as worker_mod
        from unittest.mock import patch

        ds = dataset_repo.create_dataset(name="ds_r5", engine="plate_ocr", db_path=training_db)
        dataset_repo.add_samples(ds, [
            {"target_id": f"r5_{i}", "review_id": f"rev_r5_{i}", "gate_id": f"g_{i}",
             "split": "val", "holdout": True,
             "label": {"verdict": "correct", "target_text": f"PLT{i:03d}"},
             "source": {"gate_id": f"g_{i}"}}
            for i in range(5)
        ], db_path=training_db)
        job_id = dataset_repo.create_job(
            dataset_id=ds, target="plate_ocr", config={"epochs": 1},
            db_path=training_db, operation="train",
        )

        mock_metrics = {"total": 30, "exact_match_pct": 90.0, "cer_avg": 0.04}
        with patch.object(evaluator, "evaluate_ocr", return_value=mock_metrics):
            runner = worker_mod._select_runner("plate_ocr")
            result = jobs_mod.run_training_job(
                job_id, runner=runner, db_path=training_db,
            )

        job = dataset_repo.get_job(job_id, db_path=training_db)
        assert job["operation"] == "train"
        assert job.get("runner_type") == "train"
        assert job.get("split_hash") is not None
        assert len(job["split_hash"]) == 64  # SHA256 hex
        assert result["state"] in {"completed", "pending_data"}

    def test_training_loop_with_detector_returns_unsupported(self, training_db):
        """plate_detector + operation='train' → trả unsupported, KHÔNG tạo candidate."""
        from app.training import dataset_repo, runner as runner_mod
        ds = dataset_repo.create_dataset(name="ds_r5_det", engine="plate_ocr", db_path=training_db)
        job_id = dataset_repo.create_job(
            dataset_id=ds, target="plate_detector", config={}, db_path=training_db,
            operation="train",
        )
        runner = runner_mod.select_runner("plate_detector")
        result = runner(
            {"id": job_id, "target": "plate_detector", "dataset_id": ds},
            db_path=training_db,
        )
        assert result["state"] == "unsupported"
        assert result["code_line_marker"] == "CODE_PARTIAL"
        cands = dataset_repo.list_candidates(db_path=training_db)
        assert len(cands) == 0

    def test_training_loop_with_helmet_returns_unsupported(self, training_db):
        """helmet + operation='train' → trả unsupported, KHÔNG tạo candidate."""
        from app.training import dataset_repo, runner as runner_mod
        ds = dataset_repo.create_dataset(name="ds_r5_helmet", engine="plate_ocr", db_path=training_db)
        job_id = dataset_repo.create_job(
            dataset_id=ds, target="helmet", config={}, db_path=training_db,
            operation="train",
        )
        runner = runner_mod.select_runner("helmet")
        result = runner(
            {"id": job_id, "target": "helmet", "dataset_id": ds},
            db_path=training_db,
        )
        assert result["state"] == "unsupported"
        assert result["code_line_marker"] == "CODE_PARTIAL"