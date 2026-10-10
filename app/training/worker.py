"""Task 3 — Training worker: background runner cho queued/waiting_resource jobs.

P2: thống nhất runner interface = (job: dict, db_path: str | None = None) -> dict.
Worker truyền dataset_id/job_id/target xuất phát từ `job` dict.
Detector/helmet placeholders trả "unsupported" thay vì TypeError.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.training import dataset_repo, jobs as jobs_mod
from app.training.schemas import SchemaError

LOG = logging.getLogger("task3.training_worker")

DEFAULT_POLL_SEC = 5.0


# ─── Runner interface (P2) ──────────────────────────────────────────────────

RunnerFn = Callable[[dict, "str | None"], dict]


def _select_runner(target: str) -> RunnerFn:
    """Chọn runner theo target (P2).

    P2 fix: Mọi runner trả về (job, db_path) -> dict với state ∈ {completed,
    pending_data, unsupported, failed}. KHÔNG được raise TypeError vì sai
    signature — nếu engine chưa sẵn sàng, trả {"state": "unsupported", ...}.

    Delegate sang `app/training/runner.py` để CODE_STATUS marker và helper
    `_persist_split_hash_for_job` được dùng một cách nhất quán.
    """
    from app.training import runner as runner_mod
    return runner_mod.select_runner(target)


# ─── Worker ─────────────────────────────────────────────────────────────────

class TrainingWorker:
    """Background worker chạy queued/waiting_resource jobs.

    Vòng đời:
        worker = TrainingWorker(poll_sec=5.0)
        worker.start()
        ...
        worker.stop(timeout=5.0)

    Worker loop:
      1. Tìm queued job (GPU free) → run_training_job → runner
      2. Thử resume waiting jobs → claim_and_run_one_waiting_job
      3. Sleep poll_sec
    """

    def __init__(self, poll_sec: float = DEFAULT_POLL_SEC):
        self._poll_sec = poll_sec
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="task3-training-worker",
            daemon=True,
        )
        self._thread.start()
        LOG.info("[task3.training_worker] started (poll_sec=%.1f)", self._poll_sec)

    def stop(self, *, timeout: float = 5.0) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        LOG.info("[task3.training_worker] stopped")

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            try:
                self._process_once()
            except Exception:  # noqa: BLE001
                LOG.exception("[task3.training_worker] loop error")
            self._stop_event.wait(timeout=self._poll_sec)

    def _process_once(self) -> None:
        """Một vòng: thử claim queued job, sau đó thử resume waiting."""
        db_path = None

        # 1. Thử claim queued job (GPU free thì mới claim)
        try:
            queued = dataset_repo.list_jobs(state="queued", db_path=db_path)
        except Exception:  # noqa: BLE001
            queued = []
        for job in queued:
            target = job.get("target", "")
            if not jobs_mod.can_start_gpu_job(target, exclude_job_id=job["id"], db_path=db_path):
                continue
            try:
                LOG.info("[task3.training_worker] claiming queued job %s target=%s",
                         job["id"], target)
                runner = _select_runner(target)
                result = jobs_mod.run_training_job(
                    job["id"],
                    runner=runner,
                    db_path=db_path,
                )
                LOG.info("[task3.training_worker] job %s → state=%s",
                         job["id"], result.get("state"))
            except SchemaError as e:
                LOG.warning("[task3.training_worker] job %s runner error: %s", job["id"], e)
            except Exception:  # noqa: BLE001
                LOG.exception("[task3.training_worker] job %s unexpected error", job["id"])

        # 2. Thử resume waiting jobs
        for target in ("plate_ocr", "plate_detector", "helmet"):
            try:
                runner = _select_runner(target)

                def _chained(job_dict, db_path=db_path, _r=runner):
                    return _r(job_dict, db_path=db_path)

                result = jobs_mod.claim_and_run_one_waiting_job(
                    target,
                    runner=_chained,
                    db_path=db_path,
                )
                if result:
                    LOG.info("[task3.training_worker] resumed job → state=%s",
                             result.get("state"))
            except Exception as e:  # noqa: BLE001
                LOG.warning("[task3.training_worker] resume error for %s: %s", target, e)


# ─── Module-level singleton ─────────────────────────────────────────────────

_WORKER: TrainingWorker | None = None


def get_worker() -> TrainingWorker | None:
    return _WORKER


def start_training_worker(poll_sec: float = DEFAULT_POLL_SEC) -> TrainingWorker:
    global _WORKER
    if not is_enabled():
        LOG.info("[task3.training_worker] TASK3_TRAINING_WORKER_ENABLED=0, skip start")
        return _WORKER
    if _WORKER is not None:
        return _WORKER
    _WORKER = TrainingWorker(poll_sec=poll_sec)
    _WORKER.start()
    return _WORKER


def stop_training_worker(timeout: float = 5.0) -> None:
    global _WORKER
    if _WORKER is None:
        return
    _WORKER.stop(timeout=timeout)
    _WORKER = None


def is_enabled() -> bool:
    """Đọc cờ env TASK3_TRAINING_WORKER_ENABLED. Default: 1 (bật)."""
    import os
    return os.environ.get("TASK3_TRAINING_WORKER_ENABLED", "1") not in ("0", "false", "False")