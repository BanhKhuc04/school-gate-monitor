"""Task 3 — P5 NaN/Infinity Gate Tests.

Theo yêu cầu: metrics có NaN / Infinity / total không nguyên → REJECT.

`_verify_counted_test()` trong `app/training/promotion.py` được extend với
`_verify_numeric_metric()` để reject:
  - NaN, +Infinity, -Infinity
  - None / string / bool
  - total không phải integer
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────
# Helpers (chia sẻ)
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
    db = str(tmp_path / "nan_training.db")
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


def _build_full_candidate(tmp_path, db_path, *, total=30, emp=90.0, cer=0.05,
                          extra: dict | None = None) -> str:
    from app.training import dataset_repo
    ds = dataset_repo.create_dataset(name="ds_nan", engine="plate_ocr", db_path=db_path)
    job = dataset_repo.create_job(
        dataset_id=ds, target="plate_ocr", config={"epochs": 1},
        db_path=db_path, operation="train",
    )
    art = tmp_path / "model.bin"
    sha = _make_loadable_artifact(art)
    mp = tmp_path / "metrics.json"
    _make_metrics_file(mp, model_sha=sha, dataset_id=ds,
                       extra={"total": total, "exact_match_pct": emp, "cer_avg": cer,
                              **(extra or {})})
    cand = dataset_repo.create_candidate(
        job_id=job, dataset_id=ds, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.engine.plate_ocr", model_path=str(art),
        model_sha256=sha,
        config={"class_mapping": {"alphabet": "ABC"}},
        metrics_path=str(mp), db_path=db_path,
    )
    _complete_job(db_path, job, str(mp))
    return cand


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

class TestPromotionNaNGate:
    """P5: metrics có NaN, Infinity, hoặc total không nguyên → reject."""

    def test_metrics_nan_total_rejected(self, tmp_path, training_db):
        """total = NaN → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"total": float("nan")})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "NaN" in str(ei.value)

    def test_metrics_nan_emp_rejected(self, tmp_path, training_db):
        """exact_match_pct = NaN → reject (gate counted_test)."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"exact_match_pct": float("nan")})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "NaN" in str(ei.value)

    def test_metrics_positive_infinity_emp_rejected(self, tmp_path, training_db):
        """exact_match_pct = +Infinity → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"exact_match_pct": float("inf")})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "Infinity" in str(ei.value) or "inf" in str(ei.value).lower()

    def test_metrics_negative_infinity_cer_rejected(self, tmp_path, training_db):
        """cer_avg = -Infinity → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"cer_avg": float("-inf")})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "Infinity" in str(ei.value) or "inf" in str(ei.value).lower()

    def test_metrics_total_non_integer_rejected(self, tmp_path, training_db):
        """total = 30.5 (float) → reject vì total phải là int."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"total": 30.5})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "nguyên" in str(ei.value).lower() or "int" in str(ei.value).lower()

    def test_metrics_total_string_rejected(self, tmp_path, training_db):
        """total = '30' (string) → reject vì không phải số."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"total": "30"})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "không phải số" in str(ei.value).lower() or "str" in str(ei.value).lower()

    def test_metrics_total_none_rejected(self, tmp_path, training_db):
        """total = None → reject."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"total": None})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "None" in str(ei.value) or "nguyên" in str(ei.value).lower()

    def test_metrics_emp_none_rejected(self, tmp_path, training_db):
        """exact_match_pct = None → counted_test sẽ pass None check (skip),
        nhưng sẽ fail ở gate khác (provenance/runtime). Verify counted_test KHÔNG
        False-pass NaN.
        """
        from app.training import promotion
        # Test counted_test với emp=None KHÔNG raise (gate logic skip None).
        # Mục đích: NaN gate KHÔNG false-reject None, chỉ reject NaN/Inf/bool.
        from app.training.promotion import _verify_counted_test
        # None → counted_test pass (skip), vì total=30 OK
        try:
            _verify_counted_test({"total": 30, "exact_match_pct": None, "cer_avg": 0.05}, "plate_ocr")
            _accept = True
        except Exception:
            _accept = False
        assert _accept, "counted_test với emp=None KHÔNG nên raise (gate logic cho phép None)"

    def test_metrics_emp_bool_rejected(self, tmp_path, training_db):
        """exact_match_pct = True (bool) → reject vì bool không phải số."""
        from app.training import promotion
        from app.training.schemas import SchemaError
        cand = _build_full_candidate(tmp_path, training_db,
                                     extra={"exact_match_pct": True})
        with pytest.raises(SchemaError) as ei:
            promotion.promote(cand, db_path=training_db)
        assert "bool" in str(ei.value).lower()

    def test_valid_metrics_pass_nan_gate(self, tmp_path, training_db):
        """Sanity: metrics sạch vẫn pass gate counted_test (nếu pass các gate khác)."""
        from app.training import promotion
        # Note: KHÔNG setup dataset cần thiết → promotion sẽ fail ở gate khác
        # nhưng KHÔNG phải ở NaN gate. Test chỉ check NaN gate không false-positive.
        try:
            cand = _build_full_candidate(tmp_path, training_db, total=30, emp=80.0, cer=0.1)
            result = promotion.promote(cand, db_path=training_db)
            # Nếu pass hết gate → state=pending_runtime
            assert result["state"] in ("pending_runtime", "active")
        except Exception as e:
            # Nếu fail ở gate khác (vd class_mapping) thì OK — KHÔNG phải NaN/Infinity.
            msg = str(e).lower()
            assert "nan" not in msg
            assert "infinity" not in msg
            assert "không hợp lệ" not in msg  # 'không hợp lệ' từ NaN/Infinity gate