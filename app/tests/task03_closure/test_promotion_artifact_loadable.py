"""Task 3 — P5 Artifact Loadability Tests.

Theo yêu cầu: file 200-byte giả (random) phải REJECT bởi promotion gate vì
không load được qua `torch.load(..., weights_only=False)` (raise 'Invalid magic
number' hoặc 'invalid load key').

`_verify_artifact()` trong `app/training/promotion.py` được extend với:
  - `_load_artifact_with_timeout()` chạy trong thread với timeout 5s.
  - `_try_load_torch()` wrap torch.load với `weights_only=False`.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
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
    db = str(tmp_path / "load_training.db")
    _populate_training_db(db)
    return db


def _make_loadable_artifact(path: Path) -> str:
    """Tạo file artifact torch.save → loadable."""
    import torch  # type: ignore
    torch.save({"weights": "fake_state_8s"}, str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_job(db_path: str, job_id: str, metrics_path: str) -> None:
    import sqlite3
    c = sqlite3.connect(db_path)
    c.execute(
        "UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
        "metrics_path=?, runner_type='train' WHERE id=?",
        (metrics_path, job_id),
    )
    c.commit()
    c.close()


def _build_candidate_with_artifact(tmp_path, db_path, *, artifact_path: Path,
                                    sha: str | None = None,
                                    model_class: str = "EasyOCR.engine.plate_ocr") -> str:
    """Tạo candidate với artifact cho trước."""
    from app.training import dataset_repo
    if sha is None:
        sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    ds = dataset_repo.create_dataset(name="ds_load", engine="plate_ocr", db_path=db_path)
    job = dataset_repo.create_job(
        dataset_id=ds, target="plate_ocr", config={"epochs": 1},
        db_path=db_path, operation="train",
    )
    mp = tmp_path / "metrics.json"
    mp.write_text(json.dumps({
        "total": 30,
        "exact_match_pct": 90.0,
        "cer_avg": 0.05,
        "model_sha256": sha,
        "dataset_id": ds,
    }), encoding="utf-8")
    cand = dataset_repo.create_candidate(
        job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
        model_class=model_class, model_path=str(artifact_path),
        model_sha256=sha,
        config={"class_mapping": {"alphabet": "ABC"}},
        metrics_path=str(mp), db_path=db_path,
    )
    _complete_job(db_path, job, str(mp))
    return cand


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

class TestPromotionArtifactLoadable:
    """P5: file artifact phải loadable qua torch.load với timeout."""

    def test_loadable_artifact_passes(self, tmp_path, training_db):
        """torch.save(dict) → torch.load OK → gate pass."""
        from app.training import promotion
        art = tmp_path / "model_loadable.bin"
        sha = _make_loadable_artifact(art)
        cand = _build_candidate_with_artifact(tmp_path, training_db,
                                              artifact_path=art, sha=sha)
        result = promotion.promote(cand, db_path=training_db)
        assert result["state"] in ("pending_runtime", "active")

    def test_random_bytes_artifact_rejected(self, tmp_path, training_db):
        """File 200-byte random → torch.load raise 'Invalid magic number' → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        art = tmp_path / "model_random.bin"
        art.write_bytes(b"\xde\xad\xbe\xef" * 50)  # 200-byte random
        cand = _build_candidate_with_artifact(tmp_path, training_db,
                                              artifact_path=art)
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "load được" in str(ei.value).lower() or "magic" in str(ei.value).lower()

    def test_zero_bytes_artifact_rejected(self, tmp_path, training_db):
        """File 256-byte zero → torch.load raise 'invalid load key' → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        art = tmp_path / "model_zero.bin"
        art.write_bytes(b"\x00" * 256)
        cand = _build_candidate_with_artifact(tmp_path, training_db,
                                              artifact_path=art)
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "load được" in str(ei.value).lower() or "load key" in str(ei.value).lower()

    def test_corrupt_zip_artifact_rejected(self, tmp_path, training_db):
        """File zip nhưng KHÔNG phải torch.save payload → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        art = tmp_path / "model_fakezip.bin"
        # Tạo zip rỗng (magic PK\x03\x04 OK) nhưng nội dung dummy
        with zipfile.ZipFile(art, "w") as zf:
            zf.writestr("dummy.txt", "hello world padding " * 20)  # >= 200 bytes
        cand = _build_candidate_with_artifact(tmp_path, training_db,
                                              artifact_path=art)
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        # torch.load sẽ raise ở đâu đó trong thư mục hợp lệ
        assert "load được" in str(ei.value).lower() or "magic" in str(ei.value).lower()

    def test_small_artifact_below_size_gate_rejected(self, tmp_path, training_db):
        """File < 100 bytes → size gate reject trước loadability."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        art = tmp_path / "model_tiny.bin"
        art.write_bytes(b"\x00" * 50)
        cand = _build_candidate_with_artifact(tmp_path, training_db,
                                              artifact_path=art)
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        msg = str(ei.value).lower()
        assert "nhỏ" in msg or "load" in msg

    def test_missing_artifact_rejected(self, tmp_path, training_db):
        """model_path không tồn tại → reject sớm (trước loadability)."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        from app.training import dataset_repo
        ds = dataset_repo.create_dataset(name="ds_missing", engine="plate_ocr", db_path=training_db)
        job = dataset_repo.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=training_db)
        mp = tmp_path / "metrics.json"
        mp.write_text(json.dumps({"total": 30, "exact_match_pct": 80.0,
                                  "model_sha256": "x" * 64, "dataset_id": ds}))
        _complete_job(training_db, job, str(mp))
        cand = dataset_repo.create_candidate(
            job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
            model_class="EasyOCR.engine.plate_ocr", model_path="Z:/nonexistent/missing.bin",
            model_sha256="x" * 64,
            config={"class_mapping": {"alphabet": "ABC"}},
            metrics_path=str(mp), db_path=training_db,
        )
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "không tồn tại" in str(ei.value).lower()