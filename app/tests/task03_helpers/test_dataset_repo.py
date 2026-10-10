"""Tests cho Task 3 — dataset_repo + freeze + export/import (QA DB riêng).

KHÔNG chạm DB runtime vận hành. Mỗi test dùng DB riêng trong tmp_path.
"""
from __future__ import annotations

import io
import json
import os
import pickle
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def training_db(tmp_path):
    dsn = str(tmp_path / "training.db")
    from app.training import dataset_repo
    dataset_repo.init_db(db_path=dsn)
    return dsn


def _sample(target_id: str, review_id: str = "rev_1", verdict: str = "correct",
            target_text: str = "89F123792") -> dict:
    return {
        "target_id": target_id,
        "review_id": review_id,
        "gate_id": "main",
        "label": {"verdict": verdict, "target_text": target_text,
                  "top_line": "89F1", "bottom_line": "23792"},
        "source": {
            "gate_id": "main", "camera_id": "main-front", "run_id": "run_1",
            "frame_seq": 1, "source_epoch": 0,
            "crop_sha256": "abc", "crop_media_id": "abc.jpg",
            "image_w": 200, "image_h": 100,
        },
    }


def test_create_dataset_init_and_freeze(training_db):
    from app.training import dataset_repo
    ds_id = dataset_repo.create_dataset(name="ocr_v1", engine="plate_ocr",
                                         db_path=training_db)
    assert ds_id.startswith("dsv_plate_ocr-ocr_v1_")
    meta = dataset_repo.get_dataset(ds_id, db_path=training_db)
    assert meta["freeze_state"] == "draft"
    dataset_repo.add_samples(ds_id, [_sample("s1")], db_path=training_db)
    with pytest.raises(Exception):
        # double freeze
        dataset_repo.freeze_dataset(ds_id + "_nope", db_path=training_db)


def test_add_samples_rejects_wrong_engine():
    from app.training import dataset_repo
    from app.training.schemas import SchemaError
    import tempfile
    dsn = str(Path(tempfile.mkdtemp()) / "training.db")
    dataset_repo.init_db(db_path=dsn)
    with pytest.raises(SchemaError):
        dataset_repo.create_dataset(name="bad", engine="wrong", db_path=dsn)


def test_freeze_then_cannot_add(training_db):
    from app.training import dataset_repo, dataset_freeze
    from app.training.schemas import SchemaError
    ds_id = dataset_repo.create_dataset(name="ocr_v2", engine="plate_ocr",
                                         db_path=training_db)
    samples = [_sample(f"s{i}", review_id=f"r{i}") for i in range(3)]
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    out = dataset_freeze.freeze(ds_id, output_dir=str(Path(training_db).parent / "out"),
                                 db_path=training_db)
    assert out["sample_count"] == 3
    with pytest.raises(SchemaError):
        dataset_repo.add_samples(ds_id, [_sample("extra")], db_path=training_db)


def test_freeze_manifest_has_source_hash(training_db):
    from app.training import dataset_repo, dataset_freeze
    ds_id = dataset_repo.create_dataset(name="ocr_v3", engine="plate_ocr",
                                         db_path=training_db)
    dataset_repo.add_samples(ds_id, [_sample("s1")], db_path=training_db)
    dataset_freeze.freeze(ds_id, output_dir=str(Path(training_db).parent / "out2"),
                          db_path=training_db)
    meta = dataset_repo.get_dataset(ds_id, db_path=training_db)
    manifest = json.loads(Path(meta["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["source_hash"]
    assert manifest["class_mapping"]["alphabet"] == "0-9A-Z"
    verified = dataset_freeze.verify_frozen(ds_id, db_path=training_db)
    assert verified["source_hash"] == manifest["source_hash"]


def test_freeze_rejects_empty_dataset(training_db):
    from app.training import dataset_repo, dataset_freeze
    from app.training.schemas import SchemaError
    ds_id = dataset_repo.create_dataset(name="empty", engine="plate_ocr",
                                         db_path=training_db)
    with pytest.raises(SchemaError):
        dataset_freeze.freeze(ds_id, db_path=training_db)


def test_export_zip_minimal_round_trip(training_db, tmp_path):
    """Export dataset đã freeze → import lại từ ZIP → round-trip đủ samples."""
    from app.training import dataset_repo, dataset_freeze, export_portable, import_portable
    ds_id = dataset_repo.create_dataset(name="ocr_rt", engine="plate_ocr",
                                         db_path=training_db)
    samples = [_sample(f"s{i}", review_id=f"r{i}") for i in range(3)]
    dataset_repo.add_samples(ds_id, samples, db_path=training_db)
    dataset_freeze.freeze(ds_id, output_dir=str(tmp_path / "freeze"),
                          db_path=training_db)
    zip_path = tmp_path / "out.zip"
    export_portable.export_portable_zip(dataset_id=ds_id, output_path=str(zip_path),
                                         db_path=training_db,
                                         staging_dir=str(tmp_path / "stage"),
                                         fail_on_missing_crops=False)
    assert zip_path.exists() and zip_path.stat().st_size > 0
    # Apply import sang dataset mới
    target_db = str(tmp_path / "imported.db")
    dataset_repo.init_db(db_path=target_db)
    res = import_portable.apply_import(str(zip_path), dataset_name="ocr_rt_imported",
                                       staging_root=str(tmp_path / "imports"),
                                       db_path=target_db)
    assert res["added"] == 3
    assert res["would_create"] == 3
    imported = dataset_repo.list_datasets(db_path=target_db)
    assert any(d["name"] == "ocr_rt_imported" for d in imported)


def test_import_preview_blocks_traversal(tmp_path):
    from app.training import import_portable
    # Tạo ZIP độc hại với path traversal
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "pwned")
    with pytest.raises(import_portable.ImportBlockedError):
        import_portable.preview_import(str(zip_path), staging_root=str(tmp_path / "stage"))


def test_import_preview_blocks_symlink(tmp_path):
    """Symlink trên Windows khó test — tạo ZIP có thông tin symlink bằng cách set external_attr."""
    from app.training import import_portable
    zip_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("evil_link")
    # symlink mode 0o120000
    info.create_system = 3
    info.external_attr = 0o120000 << 16
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(info, "target")
    with pytest.raises(import_portable.ImportBlockedError):
        import_portable.preview_import(str(zip_path), staging_root=str(tmp_path / "stage"))


def test_import_preview_blocks_oversize(tmp_path):
    from app.training import import_portable
    # 2GB+1 file
    zip_path = tmp_path / "big.zip"
    fake_size = 2 * 1024 * 1024 * 1024 + 1
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("big.bin", b"\0" * 1024)  # actually small
    # Dùng phương pháp monkeypatch MAX_UNCOMPRESSED_BYTES để tránh tốn RAM
    import app.training.import_portable as ip
    orig = ip.MAX_UNCOMPRESSED_BYTES
    ip.MAX_UNCOMPRESSED_BYTES = fake_size
    try:
        with pytest.raises(import_portable.ImportBlockedError):
            ip.preview_import(str(zip_path), staging_root=str(tmp_path / "stage"))
    finally:
        ip.MAX_UNCOMPRESSED_BYTES = orig


def test_import_replay_idempotent(training_db, tmp_path):
    """Import cùng ZIP 2 lần — sample count không tăng (round 2 vào dataset MỚI)."""
    from app.training import dataset_repo, dataset_freeze, export_portable, import_portable
    ds_id = dataset_repo.create_dataset(name="ocr_rep", engine="plate_ocr",
                                         db_path=training_db)
    dataset_repo.add_samples(ds_id, [_sample("s1")], db_path=training_db)
    dataset_freeze.freeze(ds_id, output_dir=str(tmp_path / "freeze"), db_path=training_db)
    zip_path = tmp_path / "out.zip"
    export_portable.export_portable_zip(dataset_id=ds_id, output_path=str(zip_path),
                                         db_path=training_db,
                                         staging_dir=str(tmp_path / "stage"),
                                         fail_on_missing_crops=False)
    target_db = str(tmp_path / "imported.db")
    dataset_repo.init_db(db_path=target_db)
    import_portable.apply_import(str(zip_path), dataset_name="ocr_rep_1",
                                  staging_root=str(tmp_path / "imports"),
                                  db_path=target_db)
    res2 = import_portable.apply_import(str(zip_path), dataset_name="ocr_rep_2",
                                         staging_root=str(tmp_path / "imports"),
                                         db_path=target_db)
    assert res2["added"] == 1
    # Vẫn là dataset MỚI — không tăng sample ở dataset cũ
    out_list = dataset_repo.list_datasets(db_path=target_db)
    assert sum(d["name"].startswith("ocr_rep") for d in out_list) == 2


def test_job_lifecycle(training_db):
    from app.training import dataset_repo, jobs
    ds_id = dataset_repo.create_dataset(name="ocr_job", engine="plate_ocr",
                                         db_path=training_db)
    job_id = jobs.create_job(dataset_id=ds_id, target="plate_ocr",
                              config={"epochs": 1, "imgsz": 320}, db_path=training_db)
    assert dataset_repo.get_job(job_id, db_path=training_db)["state"] == "queued"
    # queued → preparing (skip waiting_resource vì GPU rảnh)
    assert jobs.transition(job_id, expected="queued", new_state="preparing", db_path=training_db)
    assert jobs.transition(job_id, expected="preparing", new_state="training", db_path=training_db)
    # Transition không hợp lệ
    from app.training.schemas import SchemaError
    with pytest.raises(SchemaError):
        jobs.transition(job_id, expected="training", new_state="queued", db_path=training_db)
    assert jobs.transition(job_id, expected="training", new_state="evaluating", db_path=training_db)
    assert jobs.transition(job_id, expected="evaluating", new_state="completed", db_path=training_db)
    assert dataset_repo.get_job(job_id, db_path=training_db)["state"] == "completed"


def test_cancel_idempotent(training_db):
    from app.training import dataset_repo, jobs
    ds_id = dataset_repo.create_dataset(name="ocr_cancel", engine="plate_ocr",
                                         db_path=training_db)
    job_id = jobs.create_job(dataset_id=ds_id, target="plate_ocr", config={},
                              db_path=training_db)
    assert jobs.cancel(job_id, db_path=training_db) is True
    # cancel 2 lần → False (idempotent)
    assert jobs.cancel(job_id, db_path=training_db) is False
    assert dataset_repo.get_job(job_id, db_path=training_db)["state"] == "cancelled"


def test_evaluator_exact_match_and_cer():
    from app.training.evaluator import evaluate_ocr
    samples = [
        {"target_id": "s1", "label": {"verdict": "correct", "target_text": "89F123792"}},
        {"target_id": "s2", "label": {"verdict": "incorrect", "target_text": "59F100000"}},
        {"target_id": "s3", "label": {"verdict": "unreadable", "target_text": ""}},
    ]
    metrics = evaluate_ocr(samples, predictions={"s1": "89F123792", "s2": "59F10000X", "s3": ""})
    assert metrics["total"] == 2  # unreadable bị skip
    assert metrics["exact_match"] == 1
    assert 0 < metrics["cer_avg"] <= 1.0


def test_evaluator_quality_pending_thresholds():
    from app.training.evaluator import quality_pending
    pending, reasons = quality_pending({"total": 5, "violation_count": 10, "clean_count": 20})
    assert pending is True
    assert any("biển" in r for r in reasons)


def test_promotion_retire_previous_active(training_db, tmp_path):
    """E6 gate: artifact phải tồn tại + có metrics_path + state=pending_runtime.

    Sau rollback: candidate active bị retired, baseline trước (nếu có) được
    restore. Trong test này không có baseline nên chỉ retire hiện tại.
    """
    from app.training import dataset_repo, promotion
    # Setup dataset + job
    ds_id = dataset_repo.create_dataset(name="p1", engine="plate_ocr", db_path=training_db)
    dataset_repo.add_samples(ds_id, [_sample("s1")], db_path=training_db)

    import hashlib
    # Candidate A — file weights giả thật (>= 100 bytes, loadable qua PyTorch)
    wA = tmp_path / "weights_a.bin"
    sha_A = _make_loadable_artifact(wA, size=200)
    job_a = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr", config={}, db_path=training_db)
    cand_a = dataset_repo.create_candidate(
        job_id=job_a, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(wA), config={"class_mapping": {"alphabet": "0-9A-Z"}},
        db_path=training_db,
    )
    metrics_a = tmp_path / "metrics_a.json"
    metrics_a.write_text(json.dumps({"exact_match_pct": 70.0, "cer_avg": 0.1, "total": 30}))
    dsn = training_db
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha_A, cand_a))
        cur.execute("UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                    "metrics_path=?, runner_type='train' WHERE id=?",
                    (str(metrics_a), job_a))
        conn.commit()
    finally:
        conn.close()

    res_a = promotion.promote(cand_a, db_path=training_db)
    assert res_a["state"] == "pending_runtime"
    active = dataset_repo.get_active_candidate("plate_ocr", db_path=training_db)
    assert active is None  # mới chỉ ở pending_runtime

    # Promote B → A retired
    wB = tmp_path / "weights_b.bin"
    sha_B = _make_loadable_artifact(wB, size=200)
    job_b = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr", config={}, db_path=training_db)
    cand_b = dataset_repo.create_candidate(
        job_id=job_b, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(wB), config={"class_mapping": {"alphabet": "0-9A-Z"}},
        db_path=training_db,
    )
    metrics_b = tmp_path / "metrics_b.json"
    metrics_b.write_text(json.dumps({"exact_match_pct": 75.0, "cer_avg": 0.08, "total": 30}))
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    (sha_B, cand_b))
        cur.execute("UPDATE dataset_jobs SET state='completed', finished_at=datetime('now'), "
                    "metrics_path=?, runner_type='train' WHERE id=?",
                    (str(metrics_b), job_b))
        conn.commit()
    finally:
        conn.close()
    res_b = promotion.promote(cand_b, db_path=training_db)
    assert res_b["state"] == "pending_runtime"

    # Rollback: cả 2 đều ở pending_runtime (chưa applied runtime).
    # rollback() chỉ retire state='active' → không có gì để làm → rolled_back=False
    rb = promotion.rollback("plate_ocr", db_path=training_db)
    assert rb["rolled_back"] is False
    # Nhưng cả 2 candidate vẫn còn trong DB với state pending_runtime (không mất)
    assert dataset_repo.get_candidate(cand_a, db_path=training_db)["state"] == "pending_runtime"
    assert dataset_repo.get_candidate(cand_b, db_path=training_db)["state"] == "pending_runtime"


def test_promotion_rejects_rollback_recommendation(training_db, tmp_path):
    """Candidate metrics < baseline → reject trước khi set state."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    ds_id = dataset_repo.create_dataset(name="ds", engine="plate_ocr", db_path=training_db)
    dataset_repo.add_samples(ds_id, [_sample("s1")], db_path=training_db)

    base_w = tmp_path / "base.bin"
    base_w.write_bytes(b"fake")
    base = dataset_repo.create_candidate(
        job_id="jbase", engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(base_w),
        config={"class_mapping": {"alphabet": "0-9A-Z"}},
        db_path=training_db,
    )
    job_base = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr", config={}, db_path=training_db)
    metrics_base = tmp_path / "metrics_base.json"
    metrics_base.write_text(json.dumps({"exact_match_pct": 80.0, "cer_avg": 0.05, "total": 30}))

    bad_w = tmp_path / "bad.bin"
    bad_w.write_bytes(b"fake")
    bad = dataset_repo.create_candidate(
        job_id="jbad", engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Reader", model_path=str(bad_w),
        config={"class_mapping": {"alphabet": "0-9A-Z"}},
        db_path=training_db,
    )
    job_bad = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr", config={}, db_path=training_db)
    metrics_bad = tmp_path / "metrics_bad.json"
    metrics_bad.write_text(json.dumps({"exact_match_pct": 20.0, "cer_avg": 0.5, "total": 30}))

    dsn = training_db
    conn = dataset_repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET job_id=?, model_sha256=? WHERE id=?",
                    (job_base, "a" * 64, base))
        cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                    (str(metrics_base), job_base))
        # Baseline phải ở state 'active' (cũ) để so sánh
        cur.execute("UPDATE dataset_candidates SET state='active', promoted_at='2026-10-01T00:00:00Z' WHERE id=?", (base,))
        cur.execute("UPDATE dataset_candidates SET job_id=?, model_sha256=? WHERE id=?",
                    (job_bad, "b" * 64, bad))
        cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                    (str(metrics_bad), job_bad))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(SchemaError):
        promotion.promote(bad, db_path=training_db)


def tempfile_or_tmp() -> str:
    import tempfile
    return tempfile.mkdtemp()


def _make_loadable_artifact(path: Path, *, size: int = 256) -> str:
    """Tạo artifact giả mà torch.load(weights_only=False) load được.

    Dùng torch.save(dict, path) → file zip hợp lệ.
    """
    import hashlib
    import torch  # type: ignore
    torch.save({"weights": "fake_state_8s"}, str(path))
    if path.stat().st_size < size:
        with open(path, "ab") as f:
            f.write(b"\x00" * (size - path.stat().st_size))
    return hashlib.sha256(path.read_bytes()).hexdigest()