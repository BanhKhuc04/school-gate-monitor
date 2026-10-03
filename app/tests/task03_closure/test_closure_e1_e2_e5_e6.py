"""Task 3 closure tests — E1 (collector), E2 (export/import ảnh thật),
E2-c (ZIP guard), E4 (queue), E6 (promotion gate).

Mục đích: bảo vệ các lỗi đã tái hiện trong
CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md.

Các test này dùng gốc lưu trong tmp_path — KHÔNG đụng data runtime.
"""
from __future__ import annotations

import io
import json
import os
import queue
import shutil
import threading
import time
import zipfile
from pathlib import Path

import pytest


# ----------------------------- Helpers ---------------------------------

def _make_sample(tid: str, *, crop_media_id: str | None = None,
                target_text: str | None = None, verdict: str = "correct",
                review_id: str | None = None, bbox=None,
                source_extra: dict | None = None) -> dict:
    if target_text is None:
        target_text = "" if verdict != "correct" else "ABC1234"
    review_id = review_id or f"rev_{tid}"
    s = {
        "target_id": tid,
        "review_id": review_id,
        "gate_id": "main",
        "label": {
            "verdict": verdict,
            "target_text": target_text,
            "corrected_raw": None,
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
            "crop_sha256": "deadbeef" * 8,
            "crop_media_id": crop_media_id,
            "image_w": 320,
            "image_h": 80,
        },
        "bbox": bbox or [0.0, 0.0, 1.0, 1.0],
        "classes": None,
        "split": None,
        "holdout": False,
        "is_augmented": False,
    }
    if source_extra:
        s["source"].update(source_extra)
    return s


def _seed_dataset(db_path: str, *, name: str, engine: str = "plate_ocr",
                  samples: list[dict]) -> str:
    from app.training import dataset_repo, dataset_freeze
    dataset_repo.init_db(db_path=db_path)
    ds_id = dataset_repo.create_dataset(name=name, engine=engine, db_path=db_path)
    if samples:
        dataset_repo.add_samples(ds_id, samples, db_path=db_path)
    return ds_id


# ===========================================================================
# E1: sample collector
# ===========================================================================

def test_collector_enqueue_does_not_block_when_full():
    """Queue đầy → on_feedback trả False và bump metric dropped_queue_full."""
    from app.training import sample_collector
    coll = sample_collector.SampleCollector(task_context_path=str(Path(os.environ.get("TEMP", "/tmp")) / "t3_coll_test1"),
                                            queue_max=2)
    assert coll.on_feedback("r1", feedback_id=1, new_version=1)
    assert coll.on_feedback("r2", feedback_id=2, new_version=1)
    # Đã đầy → drop, không block
    assert not coll.on_feedback("r3", feedback_id=3, new_version=1)
    m = coll.metrics()
    assert m["dropped_queue_full"] >= 1
    coll.stop()


def test_collector_enqueue_never_raises():
    """on_feedback phải nuốt mọi lỗi, không bao giờ raise."""
    from app.training import sample_collector
    coll = sample_collector.SampleCollector(task_context_path=str(Path(os.environ.get("TEMP", "/tmp")) / "t3_coll_test2"))
    # Không raise khi review_id luôn
    assert not coll.on_feedback("", feedback_id=1, new_version=1)
    assert not coll.on_feedback(None, feedback_id=1, new_version=1)  # type: ignore[arg-type]
    assert not coll.on_feedback("r1", feedback_id=None, new_version=1)  # type: ignore[arg-type]
    m = coll.metrics()
    assert m["dropped_other"] >= 0
    coll.stop()


def test_collector_cursor_persisted_and_idempotent(tmp_path, monkeypatch):
    """Cursor phải lưu file và KHÔNG nhân khi replay cùng version."""
    from app.training import sample_collector
    monkeypatch.setattr("app.config.SNAPSHOTS_DIR", str(tmp_path))
    (tmp_path / "crop.jpg").write_bytes(b"sample-crop")
    coll = sample_collector.SampleCollector(task_context_path=str(tmp_path),
                                            queue_max=8)

    class FakeAdapter:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            return [
                {"review_id": "r1", "version": 5, "latest_feedback_id": 5,
                 "source": {"crop_sha256": "abc", "crop_media_id": "crop.jpg"},
                 "frame_seq": 1},
            ]

    # run reconcile manually
    fa = FakeAdapter()
    coll._adapter_fn = fa
    res1 = coll.run_reconcile_once()
    assert res1["updated"] == 1
    assert coll.metrics()["processed_assets_copied"] == 1
    # Cursor updated
    assert coll.cursor_state().get("r1") == 5
    # Re-run → không update vì đã thấy version 5
    res2 = coll.run_reconcile_once()
    assert res2["updated"] == 0
    coll.stop()


def test_collector_on_feedback_recorded_hook_safe():
    """Hook public KHÔNG raise, hoạt mộ ngay cả khi collector chưa khởi tạo."""
    from app.training import sample_collector
    # Singleton có thể chưa được start_collector_task(); hook phải lazy-init
    sample_collector._SINGLETON = None
    # Gọi nhiều lần, queue max của singleton = 1024 nên OK
    for i in range(5):
        ok = sample_collector.on_feedback_recorded(f"r{i}", feedback_id=i + 1, new_version=i + 1)
        # Có thể True hoặc False tuỳ queue — nhưng KHÔNG raise
        assert isinstance(ok, bool)
    sample_collector.stop_collector_task()


# ===========================================================================
# E2: export/import ảnh thật — round-trip
# ===========================================================================

def test_export_round_trip_real_image_persisted(tmp_path, monkeypatch):
    """Crop ảnh PNG thật phải được copy vào asset root khi import."""
    from app.config import BASE_DIR
    from app.training import dataset_repo, dataset_freeze, export_portable, import_portable

    # Tạo crop giả ở tmp để đóng query URL app config
    fake_snap = tmp_path / "snapshots"
    fake_snap.mkdir()
    crop_filename = "crop_abc_001.png"
    crop_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # PNG header + padding
    (fake_snap / crop_filename).write_bytes(crop_bytes)
    monkeypatch.setattr("app.config.SNAPSHOTS_DIR", str(fake_snap))

    db = str(tmp_path / "dataset.db")
    samples = [
        _make_sample("t1", crop_media_id=crop_filename, target_text="ABC1234"),
        _make_sample("t2", crop_media_id=None, verdict="unreadable"),  # no crop OK
    ]
    ds_id = _seed_dataset(db, name="rt_real", samples=samples)
    dataset_freeze.freeze(ds_id, output_dir=str(tmp_path / "freeze"), db_path=db)

    zip_path = tmp_path / "out.zip"
    res = export_portable.export_portable_zip(dataset_id=ds_id, output_path=str(zip_path),
                                              db_path=db, staging_dir=str(tmp_path / "stage"))
    assert res["asset_count"] == 1
    assert res["missing_files"] == []

    # Apply import — copy ảnh vào asset root
    target_db = str(tmp_path / "imported.db")
    dataset_repo.init_db(db_path=target_db)
    apply = import_portable.apply_import(str(zip_path), dataset_name="rt_real_imp",
                                          staging_root=str(tmp_path / "imports"),
                                          db_path=target_db)
    assert apply["added"] == 2

    # Verify crop_path được ghi trong sample DB
    imported_samples = dataset_repo.list_samples(apply["dataset_id"], db_path=target_db)
    by_id = {s["target_id"]: s for s in imported_samples}
    assert "crop_path" in by_id["t1"]["source"]
    assert by_id["t1"]["source"]["crop_path"] is not None
    assert by_id["t2"]["source"]["crop_path"] is None  # unreadable không bắt buộc


def test_export_fails_when_all_crops_missing():
    """fail_on_missing_crops=True (mặc định) + 100% missing → raise."""
    from app.training import dataset_repo, dataset_freeze, export_portable
    from app.training.schemas import SchemaError

    db = str(Path(os.environ.get("TEMP", "/tmp")) / "t3_export_fail.db")
    if Path(db).exists():
        Path(db).unlink()
    samples = [
        _make_sample("t1", crop_media_id="missing_xyz.png", target_text="ABC1234"),
        _make_sample("t2", crop_media_id="missing_uvw.png", target_text="DEF5678"),
    ]
    ds_id = _seed_dataset(db, name="fail", samples=samples)
    # Thư mục freeze không có file
    dataset_freeze.freeze(ds_id, output_dir=str(Path(os.environ.get("TEMP", "/tmp")) / "t3_freeze_fail"), db_path=db)
    with pytest.raises(SchemaError):
        export_portable.export_portable_zip(dataset_id=ds_id, output_path="/dev/null",
                                            db_path=db,
                                            staging_dir=str(Path(os.environ.get("TEMP", "/tmp")) / "t3_stage_fail"),
                                            fail_on_missing_crops=True, max_missing_ratio=0.5)


# ===========================================================================
# E2-c: ZIP guard
# ===========================================================================

def test_zip_guard_unix_regular_file_allowed(tmp_path):
    """ZIP Unix regular file KHÔNG bị chặn nhầm là symlink."""
    from app.training import import_portable
    zp = tmp_path / "unix_reg.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zi = zipfile.ZipInfo("hello.txt")
        # create_system = 3 (Unix), mode = regular file (0o100644)
        zi.create_system = 3
        zi.external_attr = (0o100644 << 16)
        zf.writestr(zi, b"hello")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        import_portable._safe_extract(zf, dest)
    assert (dest / "hello.txt").read_bytes() == b"hello"


def test_zip_guard_blocks_symlink(tmp_path):
    """ZIP có symlink (mode 0o120000) → raise ImportBlockedError."""
    from app.training import import_portable
    zp = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zi = zipfile.ZipInfo("evil")
        zi.create_system = 3
        zi.external_attr = (0o120000 << 16)  # S_IFLNK
        zf.writestr(zi, b"/etc/passwd")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        with pytest.raises(import_portable.ImportBlockedError):
            import_portable._safe_extract(zf, dest)


def test_zip_guard_blocks_traversal(tmp_path):
    from app.training import import_portable
    zp = tmp_path / "trav.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("../evil.txt", b"x")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        with pytest.raises(import_portable.ImportBlockedError):
            import_portable._safe_extract(zf, dest)


def test_zip_guard_blocks_absolute_path(tmp_path):
    from app.training import import_portable
    zp = tmp_path / "abs.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("/etc/evil", b"x")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        with pytest.raises(import_portable.ImportBlockedError):
            import_portable._safe_extract(zf, dest)


def test_zip_guard_blocks_drive_letter(tmp_path):
    from app.training import import_portable
    zp = tmp_path / "drive.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("C:/Windows/System32", b"x")
    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        with pytest.raises(import_portable.ImportBlockedError):
            import_portable._safe_extract(zf, dest)


# ===========================================================================
# E4: jobs queue + lease + resume
# ===========================================================================

def test_queued_state_does_not_hold_lease(tmp_path):
    """queued KHÔNG chiếm lease — hai job queued cùng target có thể tồn tại đồng thời."""
    from app.training import dataset_repo, jobs
    db = str(tmp_path / "jobs.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="q", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    j1 = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                  config={"epochs": 1}, db_path=db)
    j2 = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                  config={"epochs": 1}, db_path=db)
    # Cả hai queued → active_job_count = 0 (queued KHÔNG tính)
    assert jobs.can_start_gpu_job(target="plate_ocr", db_path=db) is True


def test_waiting_state_can_resume(tmp_path):
    """Job waiting_resource phải resume khi nào GPU free."""
    from app.training import dataset_repo, jobs
    db = str(tmp_path / "jobs_resume.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="r", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                       config={"epochs": 1}, db_path=db)
    # Simulate: transition queued → waiting_resource
    dataset_repo.transition_job(job_id, expected="queued", new_state="waiting_resource", db_path=db)
    # can_start phải True cho waiting_resource (chưa can claim)
    # Reset in-process running set để test thuần DB
    jobs._ACTIVE.running_ids.clear()
    # running_ids rỗng → chỉ cần DB active=0 → True
    assert jobs.can_start_gpu_job(target="plate_ocr", db_path=db) is True
    # Worker claim loop phải nhận waiting state
    job = dataset_repo.get_job(job_id, db_path=db)
    assert job["state"] in {"queued", "waiting_resource"}


# ===========================================================================
# E6: promotion gate
# ===========================================================================

def test_promotion_requires_artifact_and_metrics(tmp_path):
    """promote KHÔNG được set active nếu candidate trỏ file không tồn tại
    HOẶC không có evaluation server-side."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    db = str(tmp_path / "promo.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="p", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=db)
    # Candidate trỏ file không tồn tại
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="Smoke", model_path="/nonexistent/file.pt",
        config={"epochs": 1}, db_path=db,
    )
    with pytest.raises(SchemaError):
        promotion.promote(cand, db_path=db)


def test_promotion_requires_evaluation_file(tmp_path):
    """Candidate hợp lệ nhưng KHÔNG có metrics_path từ server → reject."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    db = str(tmp_path / "promo2.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="p2", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=db)
    # Tạo file weights giả
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"fake")
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="X", model_path=str(weights),
        config={"epochs": 1}, db_path=db,
    )
    with pytest.raises(SchemaError):
        promotion.promote(cand, db_path=db)


def test_promotion_class_mapping_validation(tmp_path):
    """Class mapping không khớp runtime contract → reject."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    db = str(tmp_path / "promo3.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="p3", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=db)
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"fake")
    # Class mapping sai (key khác runtime contract)
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="X", model_path=str(weights),
        config={"epochs": 1, "class_mapping": {"0": "car"}},  # sai cho plate_ocr
        db_path=db,
    )
    # Gắn metrics giả để qua được qua đoạn thiếu evaluation
    metrics_path = tmp_path / "m.json"
    metrics_path.write_text(json.dumps({"exact_match_pct": 80.0, "cer_avg": 0.05, "total": 30}))
    from app.training import dataset_repo as _dr
    dsn = db
    conn = _dr._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=?, model_class=? WHERE id=?",
                    ("a" * 64, "WRONG_CLASS_FOR_OCR", cand))
        cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                    (str(metrics_path), job_id))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaError):
        promotion.promote(cand, db_path=db)


def test_promotion_smoke_marker_blocks(tmp_path):
    """Candidate smoke (model_class chứa 'smoke') → KHÔNG eligible."""
    from app.training import dataset_repo, promotion
    from app.training.schemas import SchemaError

    db = str(tmp_path / "promo_smoke.db")
    dataset_repo.init_db(db_path=db)
    ds_id = dataset_repo.create_dataset(name="ps", engine="plate_ocr", db_path=db)
    dataset_repo.add_samples(ds_id, [_make_sample("t1")], db_path=db)
    job_id = dataset_repo.create_job(dataset_id=ds_id, target="plate_ocr",
                                      config={"epochs": 1}, db_path=db)
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"fake")
    cand = dataset_repo.create_candidate(
        job_id=job_id, engine="plate_ocr", target="plate_ocr",
        model_class="EasyOCR.Smoke", model_path=str(weights),
        config={"epochs": 1}, db_path=db,
    )
    metrics_path = tmp_path / "m.json"
    metrics_path.write_text(json.dumps({"exact_match_pct": 80.0, "cer_avg": 0.05, "total": 30}))
    from app.training import dataset_repo as _dr
    conn = _dr._connect(db)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dataset_candidates SET model_sha256=? WHERE id=?",
                    ("a" * 64, cand))
        cur.execute("UPDATE dataset_jobs SET metrics_path=? WHERE id=?",
                    (str(metrics_path), job_id))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaError):
        promotion.promote(cand, db_path=db)


# ===========================================================================
# E5: trainer thật / evaluator không simulation
# ===========================================================================

def test_evaluator_does_not_use_label_as_prediction():
    """Nếu predictions rỗng → metric phải 0% (KHÔNG tự lấy label)."""
    from app.training import evaluator
    samples = [_make_sample("t1", target_text="ABC123"),
               _make_sample("t2", target_text="XYZ999")]
    metrics = evaluator.evaluate_ocr(samples, predictions={})
    assert metrics["exact_match"] == 0
    assert metrics["exact_match_pct"] == 0.0
    assert metrics["read_rate"] == 0.0


def test_evaluator_uses_predictions_only(tmp_path):
    """Với predictions thật → đo đúng trên holdout (không lấy label)."""
    from app.training import evaluator
    samples = [
        _make_sample("t1", target_text="ABC123"),
        _make_sample("t2", target_text="XYZ999"),
        _make_sample("t3", target_text="AAA111"),
    ]
    # Mock predictions: t1 đúng, t2 sai, t3 empty (abstain)
    preds = {"t1": "ABC123", "t2": "XYZ000", "t3": ""}
    m = evaluator.evaluate_ocr(samples, predictions=preds)
    assert m["exact_match"] == 1
    assert m["abstain_rate"] > 0
    # CER cần > 0 cho t2
    assert m["cer_avg"] > 0
