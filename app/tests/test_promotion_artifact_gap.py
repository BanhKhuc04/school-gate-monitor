"""F4.5 gap test: promotion artifact validation.

Codex recheck (2026-10-02) probe: artifact 256 bytes toàn zero được accept
bởi tất cả promotion gates vì:
  - _verify_artifact: check size >= 100 bytes + readable + hash match
  - _verify_hash: check SHA256 full-file match
  - _verify_metrics_server_side: check metrics file readable + has key fields

P5 update (2026-10-02): thêm loadability check với timeout vào _verify_artifact.
  - torch.load(path, map_location='cpu', weights_only=False) trong thread với timeout.
  - 256-byte zero file raise 'invalid load key' → gate REJECT.

Test này document transition:
  - TRƯỚC P5: 256-byte zero PASS gates (chứng minh gap).
  - SAU P5: 256-byte zero REJECT (gap đã đóng).
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest


def test_256_byte_zero_fails_loadability_gate_post_p5():
    """P5 (NEW 2026-10-02): Artifact 256-byte zero file bị REJECT bởi
    `_verify_artifact` loadability gate (torch.load fails với 'invalid load key').

    Trước P5: gap documented — 256-byte zero pass size+hash+metrics → pending_runtime.
    Sau P5: gate `_verify_artifact` thêm torch.load() với timeout → REJECT.

    Test này EXPECT SchemaError vì loadability gate chặn đúng.
    """
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    # Use persistent temp dir so Windows doesn't fight over open DB handles
    import shutil, uuid
    tmp_dir = Path(tempfile.gettempdir()) / f"gap_test_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(tmp_dir / "gap.db")
    tmp_p = tmp_dir  # alias for artifact/metrics paths

    try:
        # Setup full schema (split_hash column added P5)
        from app import db as app_db
        app_db.DB_PATH = db_path
        conn = app_db.get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, engine TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                freeze_state TEXT NOT NULL DEFAULT 'draft', manifest_path TEXT,
                source_hash TEXT, notes TEXT);
            CREATE TABLE IF NOT EXISTS dataset_items (
                dataset_id TEXT NOT NULL, review_id TEXT NOT NULL,
                PRIMARY KEY (dataset_id, review_id));
            CREATE TABLE IF NOT EXISTS dataset_jobs (
                id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, target TEXT NOT NULL,
                state TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
                config_json TEXT, log_path TEXT, metrics_path TEXT, error TEXT,
                gpu_resource_id TEXT, operation TEXT NOT NULL DEFAULT 'evaluate_baseline',
                runner_type TEXT,
                split_hash TEXT);
            CREATE TABLE IF NOT EXISTS dataset_candidates (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, dataset_id TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL, target TEXT NOT NULL, model_class TEXT NOT NULL,
                model_path TEXT NOT NULL, model_sha256 TEXT, config_json TEXT NOT NULL,
                created_at TEXT NOT NULL, promoted_at TEXT, retired_at TEXT,
                state TEXT NOT NULL DEFAULT 'candidate', metrics_path TEXT);
            CREATE TABLE IF NOT EXISTS gpu_resources (
                id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                state TEXT NOT NULL, holder TEXT, last_heartbeat_at TEXT,
                current_job_id TEXT);
            CREATE TABLE IF NOT EXISTS dataset_samples (
                dataset_id TEXT NOT NULL, target_id TEXT NOT NULL,
                sample_json TEXT NOT NULL, split TEXT NOT NULL DEFAULT 'train',
                holdout INTEGER NOT NULL DEFAULT 0, review_id TEXT,
                added_at TEXT NOT NULL,
                PRIMARY KEY (dataset_id, target_id));
        """)
        conn.commit()
        conn.close()

        # Create dataset
        ds_id = dataset_repo.create_dataset(
            name="gap_test", engine="plate_ocr", notes="", db_path=db_path,
        )

        # Create job
        job_id = dataset_repo.create_job(
            dataset_id=ds_id, target="plate_ocr",
            config={"x": 1}, db_path=db_path, operation="train",
        )

        # Create artifact: 256-byte zero file (sẽ fail loadability)
        art_path = tmp_p / "model.bin"
        art_content = b"\x00" * 256
        art_path.write_bytes(art_content)
        sha = hashlib.sha256(art_content).hexdigest()

        # Create metrics file
        mp_path = tmp_p / "metrics.json"
        mp_path.write_text(json.dumps({
            "total": 30,
            "exact_match_pct": 80.0,
            "cer_avg": 0.05,
            "model_sha256": sha,
            "dataset_id": ds_id,
        }), encoding="utf-8")

        # Update job to completed (split_hash sẽ None — gate mới có chấp nhận None)
        with app_db.get_connection() as c:
            c.execute(
                "UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                "metrics_path=?, runner_type='train' WHERE id=?",
                (str(mp_path), job_id),
            )
            c.commit()

        # Create candidate
        cand_id = dataset_repo.create_candidate(
            job_id=job_id, dataset_id=ds_id, engine="plate_ocr", target="plate_ocr",
            model_class="EasyOCR.engine.plate_ocr",
            model_path=str(art_path), model_sha256=sha,
            config={"class_mapping": {"alphabet": "ABC"}},
            metrics_path=str(mp_path), db_path=db_path,
        )

        # P5 (NEW): torch.load fails với 'invalid load key' → gate reject.
        with pytest.raises(SchemaError) as exc_info:
            promotion.promote(cand_id, db_path=db_path)
        msg = str(exc_info.value).lower()
        assert "load được" in msg or "load key" in msg, (
            f"P5 loadability gate phải reject 256-byte zero, got: {exc_info.value}"
        )

        # Verify artifact vẫn là 256-byte (gap đã được đóng bởi loadability check)
        artifact_size = art_path.stat().st_size
        assert artifact_size == 256
        assert artifact_size < 1_000_000
    finally:
        # Cleanup persistent temp dir
        shutil.rmtree(str(tmp_dir), ignore_errors=True)


def test_real_ocr_model_is_large():
    """Verify real model files are much larger than 256 bytes.

    This test documents the baseline: real production models are > 100MB.
    It passes on this machine to prove the gap is real.
    """
    import os
    models_dir = Path("D:/Work/Project_motorbike/models")
    if not models_dir.exists():
        pytest.skip("models directory not found")

    for pt_file in models_dir.glob("*.pt"):
        size_mb = pt_file.stat().st_size / (1024 * 1024)
        # All real YOLO/OCR model files are > 1MB
        assert size_mb > 1.0, f"{pt_file.name} only {size_mb:.1f}MB — suspiciously small"


def test_size_gate_detects_extreme_fake():
    """File 50 bytes (dưới gate 100) → reject."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError
    import shutil, uuid

    tmp_dir = Path(tempfile.gettempdir()) / f"size_test_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(tmp_dir / "size.db")
    try:
        from app import db as app_db
        app_db.DB_PATH = db_path
        conn = app_db.get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, engine TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                freeze_state TEXT NOT NULL DEFAULT 'draft', manifest_path TEXT,
                source_hash TEXT, notes TEXT);
            CREATE TABLE IF NOT EXISTS dataset_jobs (
                id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, target TEXT NOT NULL,
                state TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
                config_json TEXT, log_path TEXT, metrics_path TEXT, error TEXT,
                gpu_resource_id TEXT, operation TEXT NOT NULL DEFAULT 'evaluate_baseline',
                runner_type TEXT,
                split_hash TEXT);
            CREATE TABLE IF NOT EXISTS dataset_candidates (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, dataset_id TEXT NOT NULL DEFAULT '',
                engine TEXT NOT NULL, target TEXT NOT NULL, model_class TEXT NOT NULL,
                model_path TEXT NOT NULL, model_sha256 TEXT, config_json TEXT NOT NULL,
                created_at TEXT NOT NULL, promoted_at TEXT, retired_at TEXT,
                state TEXT NOT NULL DEFAULT 'candidate', metrics_path TEXT);
            CREATE TABLE IF NOT EXISTS gpu_resources (
                id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                state TEXT NOT NULL, holder TEXT, last_heartbeat_at TEXT,
                current_job_id TEXT);
        """)
        conn.commit()
        conn.close()

        ds = dataset_repo.create_dataset(name="size_t", engine="plate_ocr", db_path=db_path)
        job = dataset_repo.create_job(dataset_id=ds, target="plate_ocr", config={}, db_path=db_path)
        art = tmp_dir / "tiny.bin"
        art.write_bytes(b"\x00" * 50)  # dưới gate 100
        sha = hashlib.sha256(art.read_bytes()).hexdigest()
        mp = tmp_dir / "m.json"
        mp.write_text(json.dumps({"total": 30, "exact_match_pct": 80.0, "model_sha256": sha, "dataset_id": ds}))

        with app_db.get_connection() as c:
            c.execute("UPDATE dataset_jobs SET state='completed', metrics_path=?, runner_type='train' WHERE id=?",
                      (str(mp), job))
            c.commit()

        cand = dataset_repo.create_candidate(
            job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
            model_class="EasyOCR.engine.plate_ocr", model_path=str(art),
            model_sha256=sha, config={"class_mapping": {"alphabet": "ABC"}},
            metrics_path=str(mp), db_path=db_path,
        )
        with pytest.raises(SchemaError) as exc:
            promotion.promote(cand, db_path=db_path)
        # Có thể fail ở size gate hoặc loadability gate (50 bytes < torch header)
        assert "nhỏ" in str(exc.value).lower() or "load" in str(exc.value).lower()
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)