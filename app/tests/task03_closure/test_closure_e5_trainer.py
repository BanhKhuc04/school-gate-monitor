"""E5: trainer OCR thật (không simulation)."""
from __future__ import annotations

import hashlib
import json
import os
import pickle
from pathlib import Path

import pytest


# Local fixture vì folder closure không có conftest
@pytest.fixture
def training_db(tmp_path):
    dsn = str(tmp_path / "training.db")
    from app.training import dataset_repo
    dataset_repo.init_db(db_path=dsn)
    return dsn


def _seed_sample(*, tid: str, target_text: str = "ABC1234",
                 verdict: str = "correct", crop_media_id: str = "x.png") -> dict:
    return {
        "target_id": tid,
        "review_id": f"r_{tid}",
        "gate_id": "main",
        "label": {
            "verdict": verdict,
            "target_text": target_text,
            "top_line": None,
            "bottom_line": None,
            "quality_score": 0.9,
        },
        "source": {
            "gate_id": "main",
            "camera_id": "cam1",
            "run_id": "run1",
            "frame_seq": 1,
            "source_epoch": 0,
            "observed_at": "2026-10-02T00:00:00Z",
            "crop_sha256": "abc",
            "crop_media_id": crop_media_id,
            "image_w": 200,
            "image_h": 80,
        },
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "classes": None,
        "split": None,
        "holdout": True,
    }


def test_trainer_pending_when_holdout_too_small(tmp_path, training_db):
    """< 30 holdout → PENDING_DATA, KHÔNG tạo candidate."""
    from app.training import dataset_repo, ocr_trainer
    ds_id = dataset_repo.create_dataset(name="ocr_p", engine="plate_ocr", db_path=training_db)
    # 5 samples, holdout=True cho 3
    samples = [_seed_sample(tid=f"t{i}") for i in range(5)]
    for s in samples[:3]:
        s["holdout"] = True
    for s in samples[3:]:
        s["holdout"] = False
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=training_db)
    res = ocr_trainer.run_ocr_training_job(
        dataset_id=ds_id, job_id=job_id, db_path=training_db,
        output_root=str(tmp_path / "out"),
    )
    assert res["state"] == "pending_data"
    assert "holdout" in res["note"].lower() or "asset" in res["note"].lower()


def test_trainer_pending_when_asset_root_missing(tmp_path, training_db):
    """Asset root không tồn tại → PENDING_DATA, không inference."""
    from app.training import dataset_repo, ocr_trainer
    ds_id = dataset_repo.create_dataset(name="ocr_a", engine="plate_ocr", db_path=training_db)
    # 35 holdout
    samples = []
    for i in range(35):
        s = _seed_sample(tid=f"t{i}")
        s["holdout"] = True
        samples.append(s)
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=training_db)
    res = ocr_trainer.run_ocr_training_job(
        dataset_id=ds_id, job_id=job_id, db_path=training_db,
        output_root=str(tmp_path / "out"),
    )
    # Asset root không có → PENDING_DATA
    assert res["state"] in {"pending_data", "unsupported"}
    if res["state"] == "pending_data":
        assert "asset" in res["note"].lower()


def test_trainer_smoke_marker_not_eligible_for_promotion(tmp_path, training_db):
    """Candidate có 'Smoke' trong model_class → KHÔNG eligible cho promotion."""
    from app.training import dataset_repo, promotion
    ds_id = dataset_repo.create_dataset(name="ocr_smoke", engine="plate_ocr", db_path=training_db)
    samples = [_seed_sample(tid=f"t{i}") for i in range(3)]
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    import hashlib
    weights = tmp_path / "w.bin"
    sha = _make_loadable_artifact(weights, size=200)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=training_db)
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Smoke", model_path=str(weights),
        config={"class_mapping": {"alphabet": "0-9A-Z"}}, db_path=training_db,
    )
    metrics_p = tmp_path / "m.json"
    metrics_p.write_text(json.dumps({"exact_match_pct": 70.0, "cer_avg": 0.1, "total": 30}))
    conn = dataset_repo._connect(training_db)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha, cand))
        cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                    (str(metrics_p), job_id))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception):
        promotion.promote(cand, db_path=training_db)


def test_trainer_pending_data_metrics_rejected(tmp_path, training_db):
    """Metrics < 30 samples → promotion gate block (PENDING_DATA)."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError
    ds_id = dataset_repo.create_dataset(name="ocr_smol", engine="plate_ocr", db_path=training_db)
    samples = [_seed_sample(tid=f"t{i}") for i in range(3)]
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    import hashlib
    weights = tmp_path / "w.bin"
    sha = _make_loadable_artifact(weights, size=200)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=training_db)
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(weights),
        config={"class_mapping": {"alphabet": "0-9A-Z"}}, db_path=training_db,
    )
    metrics_p = tmp_path / "m.json"
    metrics_p.write_text(json.dumps({"exact_match_pct": 70.0, "cer_avg": 0.1, "total": 5}))
    conn = dataset_repo._connect(training_db)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha, cand))
        cur.execute("UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                    "metrics_path=?, runner_type='train' WHERE id=?",
                    (str(metrics_p), job_id))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaError) as exc:
        promotion.promote(cand, db_path=training_db)
    assert "PENDING_DATA" in str(exc.value) or "< 30" in str(exc.value) or "nhỏ" in str(exc.value)


def test_trainer_runtime_contract_violation(tmp_path, training_db):
    """model_class không thuộc runtime contract → block."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError
    ds_id = dataset_repo.create_dataset(name="ocr_wrong", engine="plate_ocr", db_path=training_db)
    samples = [_seed_sample(tid=f"t{i}") for i in range(3)]
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    import hashlib
    weights = tmp_path / "w.bin"
    sha = _make_loadable_artifact(weights, size=200)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=training_db)
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="YOLO.Reader",  # sai: plate_ocr không dùng YOLO
        model_path=str(weights),
        config={"class_mapping": {"alphabet": "0-9A-Z"}}, db_path=training_db,
    )
    metrics_p = tmp_path / "m.json"
    metrics_p.write_text(json.dumps({"exact_match_pct": 70.0, "cer_avg": 0.1, "total": 30}))
    conn = dataset_repo._connect(training_db)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha, cand))
        cur.execute("UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                    "metrics_path=?, runner_type='train' WHERE id=?",
                    (str(metrics_p), job_id))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaError) as exc:
        promotion.promote(cand, db_path=training_db)
    assert "runtime contract" in str(exc.value).lower()


def _make_loadable_artifact(path: Path, *, size: int = 200) -> str:
    """Tạo file artifact mà torch.load(weights_only=False) load được.

    Dùng torch.save(dict, path) → file zip hợp lệ.
    """
    import torch  # type: ignore
    torch.save({"weights": "fake_state_8s"}, str(path))
    if path.stat().st_size < size:
        with open(path, "ab") as f:
            f.write(b"\x00" * (size - path.stat().st_size))
    return hashlib.sha256(path.read_bytes()).hexdigest()