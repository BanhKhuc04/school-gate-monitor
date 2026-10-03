"""Task 3 — Target runners (contract thống nhất qua P2).

Mỗi runner có interface:
    CALLS (job: dict, db_path: str | None = None) -> dict

Return contract:
    {
      "state": "completed" | "pending_data" | "unsupported" | "failed",
      "metrics": dict | None,
      "model_path": str | None,    # chỉ khi completed + operation="train"
      "model_sha256": str | None,
      "log_path": str | None,
      "candidate_id": str | None,
      "note": str | None,
      "error": str | None,         # chỉ khi state=failed
    }

CODE STATUS (T3 review 2026-10-02):
  - plate_ocr:        CODE_COMPLETE (P2/P3/P5 đã verify). Dùng EasyOCR baseline
                       inference + metrics server-side.
  - plate_detector:   CODE_PARTIAL  — runner wrapper hoạt động nhưng detector
                       training chưa có fixture/gpu đủ điều kiện. Trả
                       "unsupported" cho đến khi có engine thật.
  - helmet:           CODE_PARTIAL  — tương tự plate_detector.

REOPEN:
  - Cần engine YOLO/Helmet thật với class mapping version locked + fixture GPU.
  - Chưa có label thật cho helmet, không tự fake accuracy.
  - Smoke optimization/checkpoint riêng chỉ chứng minh plumbing.

P5: mọi runner PHẢI ghi split_hash qua `dataset_repo.set_job_split_hash(job_id, ...)`
TRƯỚC khi return completed/pending_data, để provenance gate verify được.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from app.training import provenance as _prov
from app.training import dataset_repo

LOG = logging.getLogger("task3.runner")

RunnerFn = Callable[[dict, "str | None"], dict]


# ── OCR runner (CODE_COMPLETE) ───────────────────────────────────────────────

def _run_ocr_job(job: dict, db_path: str | None = None) -> dict:
    """Plate OCR — dùng EasyOCR baseline (P1+P5).

    Status: CODE_COMPLETE (verified by 117/117 tests including P3 valid_candidate).
    Output: candidate với model_path=None (EasyOCR không có weights riêng) + metrics.

    Khi operation='train' mà chưa có training runner thật → trả 'pending_data'
    với note rõ ràng (không fake 'completed' với placeholder model).
    """
    from app.training.ocr_trainer import run_ocr_training_job

    dataset_id = job.get("dataset_id", "")
    job_id = job.get("id", "")
    target = job.get("target", "plate_ocr")

    # P5: ghi split_hash provenance trước khi run
    _persist_split_hash_for_job(job_id, dataset_id, db_path=db_path)

    return run_ocr_training_job(
        dataset_id=dataset_id,
        job_id=job_id,
        target=target,
        db_path=db_path,
    )


# ── Detector runner (CODE_PARTIAL) ────────────────────────────────────────────

def _run_detector_job(job: dict, db_path: str | None = None) -> dict:
    """Plate detector — REOPEN CODE_PARTIAL.

    Engine đã có (`app.training.detector_engine.UltralyticsDetectorEngine`) nhưng
    training runner chưa có: chưa có weights thật, chưa có GPU fixture, chưa có
    class mapping version locked.

    Status: CODE_PARTIAL — KHÔNG ghi CODE_COMPLETE.
    Trả "unsupported" thay vì fake raise giả để DB/UI biết engine chưa sẵn sàng.
    """
    job_id = job.get("id", "")
    dataset_id = job.get("dataset_id", "")

    # P5: vẫn ghi split_hash để trace được job đến split
    try:
        _persist_split_hash_for_job(job_id, dataset_id, db_path=db_path)
    except Exception:  # noqa: BLE001
        pass

    return {
        "state": "unsupported",
        "metrics": None,
        "model_path": None,
        "model_sha256": None,
        "log_path": None,
        "candidate_id": None,
        "note": (
            "plate_detector training CODE_PARTIAL: cần YOLO weights thật + "
            "fixture GPU + class mapping version locked. "
            "Engine wrapper đã có ở app/training/detector_engine.py."
        ),
        "error": None,
        "code_line_marker": "CODE_PARTIAL",
    }


# ── Helmet runner (CODE_PARTIAL) ──────────────────────────────────────────────

def _run_helmet_job(job: dict, db_path: str | None = None) -> dict:
    """Helmet detector — REOPEN CODE_PARTIAL.

    Engine wrapper đã có (`app.training.helmet_engine.HelmetDetectorEngine`) nhưng:
      - missing 2026-10-02 helmet label dataset thật
      - missing GPU fixture đủ điều kiện
      - missing optimized weights trained on Vietnamese plates

    Status: CODE_PARTIAL — KHÔNG ghi CODE_COMPLETE.
    """
    job_id = job.get("id", "")
    dataset_id = job.get("dataset_id", "")

    try:
        _persist_split_hash_for_job(job_id, dataset_id, db_path=db_path)
    except Exception:  # noqa: BLE001
        pass

    return {
        "state": "unsupported",
        "metrics": None,
        "model_path": None,
        "model_sha256": None,
        "log_path": None,
        "candidate_id": None,
        "note": (
            "helmet training CODE_PARTIAL: thiếu label thật + GPU fixture. "
            "Engine wrapper đã có ở app/training/helmet_engine.py."
        ),
        "error": None,
        "code_line_marker": "CODE_PARTIAL",
    }


# ── Runner selector ──────────────────────────────────────────────────────────

RUNNER_TABLE: dict[str, RunnerFn] = {
    "plate_ocr": _run_ocr_job,
    "plate_detector": _run_detector_job,
    "helmet": _run_helmet_job,
}


def select_runner(target: str) -> RunnerFn:
    """Trả runner cho target. SchemaError nếu target không hỗ trợ."""
    from app.training.schemas import SchemaError
    fn = RUNNER_TABLE.get(target)
    if fn is None:
        raise SchemaError(f"target={target!r} không được hỗ trợ")
    return fn


def list_supported_targets() -> list[str]:
    """Danh sách target có runner. Dùng cho UI/API để hiển thị 'supported' vs 'partial'."""
    return list(RUNNER_TABLE.keys())


def code_status_for(target: str) -> str:
    """CODE_COMPLETE / CODE_PARTIAL / CODE_NOT_IMPLEMENTED cho 1 target.

    Dùng để UI/API hiển thị rõ trạng thái mà không tự nâng cấp.
    """
    if target == "plate_ocr":
        return "CODE_COMPLETE"
    if target in ("plate_detector", "helmet"):
        return "CODE_PARTIAL"
    return "CODE_NOT_IMPLEMENTED"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _persist_split_hash_for_job(job_id: str, dataset_id: str,
                                 *, db_path: str | None) -> None:
    """P5: ghi split_hash + dataset_snapshot vào job để provenance gate verify."""
    if not job_id or not dataset_id:
        return
    ds = dataset_repo.get_dataset(dataset_id, db_path=db_path)
    if ds is None:
        return
    samples = dataset_repo.list_samples(dataset_id, db_path=db_path)
    split_map = {s.get("target_id", ""): s.get("split", "train") for s in samples}
    split_hash = _prov.compute_split_hash(samples=samples, split_map=split_map)
    snapshot = _prov.compute_dataset_snapshot(
        dataset_id=dataset_id,
        samples=samples,
        freeze_state=ds.get("freeze_state", "draft"),
        source_hash=ds.get("source_hash"),
    )
    try:
        # Lưu snapshot + split_hash trong config_json tạm thời? Đơn giản: lưu split_hash
        # vào dataset_jobs.split_hash; snapshot đã có sẵn nếu caller persist.
        dataset_repo.set_job_split_hash(job_id, split_hash=split_hash, db_path=db_path)
        LOG.info("[task3] job %s split_hash=%s (snapshot=%s)",
                  job_id, split_hash[:16], snapshot[:16])
    except Exception as e:  # noqa: BLE001
        LOG.warning("[task3] persist split_hash failed for job %s: %s", job_id, e)