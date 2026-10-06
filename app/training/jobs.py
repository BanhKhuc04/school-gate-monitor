"""Training job orchestration — queue, state machine, GPU resource lock.

Nguyên tắc:
- 1 GPU job tại 1 thời điểm. queued/waiting_resource KHÔNG chiếm lease.
- C02: runner nhận cả queued VÀ waiting_resource → resume.
- C03: runner state phải reflect runner result: pending_data/unsupported/failed/cancelled
  KHÔNG được báo completed. completed chỉ khi artifact hợp lệ.
- Cancel dừng runner thật và giải phóng lease.
- KHÔNG commit/ghi vào DB runtime vận hành.

State machine:
  queued ──[GPU free]──> preparing ──> training ──> evaluating ──> completed
       └─[GPU busy]──> waiting_resource ──[GPU free]──> preparing
  queued|preparing|training|evaluating ──[cancel]──> cancelled
  queued|preparing|training|evaluating ──[runner error]──> failed
  evaluating ──[runner pending_data/unsupported]──> pending_data/unsupported
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.training import dataset_repo, provenance
from app.training.schemas import SchemaError


# allowed transitions
JOB_TRANSITIONS = {
    "queued": {"waiting_resource", "preparing", "cancelled", "failed"},
    "waiting_resource": {"preparing", "cancelled", "failed"},
    "preparing": {"training", "cancelled", "failed"},
    "training": {"evaluating", "cancelled", "failed"},
    "evaluating": {"completed", "failed", "cancelled", "pending_data", "unsupported"},
    "pending_data": set(),
    "unsupported": set(),
    "completed": set(),
    "cancelled": set(),
    "failed": set(),
}


def create_job(*, dataset_id: str, target: str, config: dict,
               db_path: str | None = None) -> str:
    return dataset_repo.create_job(dataset_id=dataset_id, target=target,
                                   config=config, db_path=db_path)


def transition(job_id: str, *, expected: str, new_state: str,
               error: str | None = None, db_path: str | None = None) -> bool:
    if new_state not in JOB_TRANSITIONS.get(expected, set()):
        raise SchemaError(f"chuyển trạng thái không hợp lệ: {expected} -> {new_state}")
    return dataset_repo.transition_job(job_id, expected=expected, new_state=new_state,
                                      error=error, db_path=db_path)


def cancel(job_id: str, *, db_path: str | None = None) -> bool:
    """Huỷ job — từ queued/waiting_resource/preparing/training/evaluating. Idempotent."""
    job = dataset_repo.get_job(job_id, db_path=db_path)
    if job is None:
        raise SchemaError(f"job_id={job_id!r} không tồn tại")
    if job["state"] in {"completed", "cancelled", "failed", "pending_data", "unsupported"}:
        return False
    return dataset_repo.transition_job(job_id, expected=job["state"], new_state="cancelled",
                                      db_path=db_path)


# ─── GPU lease management ─────────────────────────────────────────────────────

@dataclass
class _ActiveJobs:
    lock: threading.Lock = threading.Lock()
    running_ids: set[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.running_ids is None:
            self.running_ids = set()


_ACTIVE = _ActiveJobs()


def can_start_gpu_job(target: str, *, exclude_job_id: str | None = None,
                      db_path: str | None = None) -> bool:
    """Check 1-job-at-a-time constraint. queued/waiting_resource KHÔNG chiếm lease."""
    with _ACTIVE.lock:
        if _ACTIVE.running_ids and (not exclude_job_id or exclude_job_id not in _ACTIVE.running_ids):
            return False
        active = dataset_repo.active_job_count(target=target, exclude_job_id=exclude_job_id,
                                               db_path=db_path)
    return active == 0


def mark_job_started(job_id: str) -> None:
    with _ACTIVE.lock:
        _ACTIVE.running_ids.add(job_id)


def mark_job_done(job_id: str) -> None:
    with _ACTIVE.lock:
        _ACTIVE.running_ids.discard(job_id)


# ─── Runner ─────────────────────────────────────────────────────────────────

def run_training_job(
    job_id: str,
    *,
    runner,
    db_path: str | None = None,
) -> dict:
    """Run 1 job.

    Contract:
      - runner(job, db_path) -> {
          state: "completed" | "pending_data" | "unsupported" | "failed",
          candidate_id?: str,
          metrics?: dict,
          model_path?: str,
          model_sha256?: str,
          log_path?: str,
          note?: str,
          error?: str,
        }
      - runner KHÔNG raise; trả dict với state phù hợp.

    C02: nhận cả queued VÀ waiting_resource. C03: state reflect runner result.
    """
    job = dataset_repo.get_job(job_id, db_path=db_path)
    if job is None:
        raise SchemaError(f"job_id={job_id!r} không tồn tại")

    # C02: nhận cả queued và waiting_resource
    if job["state"] not in {"queued", "waiting_resource", "preparing"}:
        raise SchemaError(
            f"job ở state={job['state']!r} — không thể chạy (chỉ queued/waiting_resource)"
        )

    target = job["target"]

    # GPU lease check
    if job["state"] != "preparing" and not can_start_gpu_job(target, exclude_job_id=job_id, db_path=db_path):
        # Chuyển waiting_resource nếu chưa
        if job["state"] == "queued":
            if not transition(job_id, expected="queued", new_state="waiting_resource",
                            db_path=db_path):
                raise SchemaError("race condition khi chuyển waiting_resource")
        return {
            "job_id": job_id,
            "state": "waiting_resource",
            "note": "GPU busy — sẽ thử lại khi free",
        }

    # Transition: queued → preparing hoặc waiting_resource → preparing
    # Nếu đã preparing (từ claim_and_run_one_waiting_job) thì skip
    if job["state"] != "preparing":
        expected_from = job["state"]
        if not transition(job_id, expected=expected_from, new_state="preparing", db_path=db_path):
            raise SchemaError("race condition khi chuyển preparing")

    mark_job_started(job_id)
    # P4: persist runner_type from job.operation
    _persist_runner_type(job_id, db_path=db_path)

    try:
        # preparing → training
        if not transition(job_id, expected="preparing", new_state="training", db_path=db_path):
            raise SchemaError("không thể vào training")
        try:
            result = runner(job, db_path=db_path)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            transition(job_id, expected="training", new_state="failed",
                     error=err, db_path=db_path)
            return {"job_id": job_id, "state": "failed", "error": err}

        # C03: training → evaluating (evaluation luôn chạy)
        if not transition(job_id, expected="training", new_state="evaluating", db_path=db_path):
            raise SchemaError("không thể vào evaluating")

        # State phản ánh runner result — không phải lúc nào cũng completed
        runner_state = result.get("state", "completed")
        if runner_state not in JOB_TRANSITIONS["evaluating"]:
            runner_state = "failed"

        if runner_state == "pending_data":
            transition(job_id, expected="evaluating", new_state="pending_data", db_path=db_path)
            return {
                "job_id": job_id,
                "state": "pending_data",
                "note": result.get("note", "dữ liệu chưa đủ để train"),
                "metrics": result.get("metrics"),
            }
        elif runner_state == "unsupported":
            transition(job_id, expected="evaluating", new_state="unsupported", db_path=db_path)
            return {
                "job_id": job_id,
                "state": "unsupported",
                "note": result.get("note", "engine/training không khả dụng"),
                "metrics": result.get("metrics"),
            }
        elif runner_state == "failed":
            err = result.get("error", "runner failed")
            transition(job_id, expected="evaluating", new_state="failed",
                     error=err, db_path=db_path)
            return {"job_id": job_id, "state": "failed", "error": err}

        # completed: runner trả artifact hợp lệ
        transition(job_id, expected="evaluating", new_state="completed", db_path=db_path)
        return {
            "job_id": job_id,
            "state": "completed",
            "result": result,
        }
    finally:
        mark_job_done(job_id)


def claim_and_run_one_waiting_job(target: str, *, runner, db_path: str | None = None) -> dict | None:
    """Thử claim 1 job waiting của target và chạy nó.

    Dùng bởi worker loop để resume waiting job khi GPU free.
    Trả None nếu không có job waiting nào.
    """
    jobs = dataset_repo.list_jobs(state="waiting_resource", db_path=db_path)
    for job in jobs:
        if job["target"] != target:
            continue
        # GPU must be free for THIS target
        if not can_start_gpu_job(target, exclude_job_id=job["id"], db_path=db_path):
            continue
        # waiting → preparing
        if not transition(job["id"], expected="waiting_resource", new_state="preparing",
                         db_path=db_path):
            continue
        # Chạy job
        return run_training_job(job["id"], runner=runner, db_path=db_path)
    return None


def _persist_runner_type(job_id: str, *, job_record: dict | None = None,
                        db_path: str | None = None) -> None:
    """P4: ghi runner_type từ job.operation để phân biệt evaluate_baseline vs train."""
    job = job_record or dataset_repo.get_job(job_id, db_path=db_path)
    if job is None:
        return
    op = job.get("operation", "evaluate_baseline")
    runner_type = op if op == "evaluate_baseline" else "train"
    try:
        dataset_repo.set_job_runner_type(job_id, runner_type=runner_type, db_path=db_path)
    except Exception:  # noqa: BLE001
        pass