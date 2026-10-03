"""Task 3 — sample collector: thu mẫu từ feedback, enqueue nhẹ, worker nền xử lý.

Nguyên tắc (E1):
- HTTP handler CHỈ enqueue (review_id, feedback_version, ts). KHÔNG đọc ảnh,
  KHÔNG copy, KHÔNG train trong request.
- Worker nền xử lý reconcile: cursor-based scan, idempotent theo
  (review_id, feedback_version), dedup.
- Queue có giới hạn; queue đầy/lỗi ghi metric, KHÔNG làm mất feedback.
- Cursor bền vững (JSON file); chỉ ACK cursor sau khi asset copy thành công.
- Hook chỉ dùng singleton đã được lifespan start; chưa start → return False.
- Hook KHÔNG làm I/O (không tạo thư mục/đọc file).

C06: record_review_feedback trả expected_version (echo), không phải version.
  Hook dùng result['expected_version'] — chính là feedback_version của review đó.
C04a: cursor ack CHỈ sau khi asset copy thành công. Nếu copy fail, không update
  cursor — version đó sẽ được retry ở pass sau.
C04b: version comparison với cursor (đã xử lý) thay vì với event version.
C05a: pagination dùng review_id cursor (stable ordering) thay vì [:batch_max] luôn
  lấy trang đầu.
C05b: hook dùng singleton đã khởi tạo (start_collector_task); chưa start → False.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import threading

from app.training import adapter, provenance, schemas
from app.training.schemas import SchemaError

LOG = logging.getLogger("task3.sample_collector")

DEFAULT_QUEUE_MAX = 1024
DEFAULT_BATCH_MAX = 32
DEFAULT_WORKER_PERIOD_SEC = 5.0
DEFAULT_HEARTBEAT_SEC = 30.0
CURSOR_FILENAME = "sample_collector.cursor.json"
METRICS_FILENAME = "sample_collector.metrics.json"
ENABLE_ENV = "TASK3_COLLECTOR_ENABLED"


def is_enabled() -> bool:
    flag = os.environ.get(ENABLE_ENV, "1")
    return flag not in {"0", "false", "False", "no", "NO"}


@dataclass
class FeedbackEvent:
    review_id: str
    feedback_id: int         # server-generated identity (from record_review_feedback)
    new_version: int         # server-authoritative version actually committed
    ts: float
    source: str = "feedback"

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "feedback_id": int(self.feedback_id),
            "new_version": int(self.new_version),
            "ts": float(self.ts),
            "source": self.source,
        }


# ----------------------- Singleton state -----------------------

_LOCK = threading.Lock()
_SINGLETON: "SampleCollector | None" = None


def start_collector_task(
    *,
    task_context_path: str | None = None,
    queue_max: int = DEFAULT_QUEUE_MAX,
    batch_max: int = DEFAULT_BATCH_MAX,
    worker_period_sec: float = DEFAULT_WORKER_PERIOD_SEC,
    heartbeat_sec: float = DEFAULT_HEARTBEAT_SEC,
    adapter_fn=None,
    storage_root: str | None = None,
) -> "SampleCollector":
    """Start (hoặc lấy) singleton collector. Idempotent."""
    global _SINGLETON
    with _LOCK:
        if _SINGLETON is None:
            _SINGLETON = SampleCollector(
                task_context_path=task_context_path,
                queue_max=queue_max,
                batch_max=batch_max,
                worker_period_sec=worker_period_sec,
                heartbeat_sec=heartbeat_sec,
                adapter_fn=adapter_fn,
                storage_root=storage_root,
            )
        if is_enabled():
            _SINGLETON.start()
        return _SINGLETON


def stop_collector_task(*, timeout: float = 5.0) -> None:
    global _SINGLETON
    with _LOCK:
        if _SINGLETON is not None:
            _SINGLETON.stop(timeout=timeout)
            _SINGLETON = None


def get_collector() -> "SampleCollector | None":
    """Trả singleton. KHÔNG tự tạo."""
    return _SINGLETON


# ----------------------- Public hook -----------------------

def on_feedback_recorded(review_id: str, feedback_id: int, new_version: int,
                       *, source: str = "feedback") -> bool:
    """Hook cho Task 1 gọi sau record_review_feedback thành công.

    Contract (post-closure P1):
      - review_id: ID của review vừa được feedback.
      - feedback_id: int — ID server-generated từ record_review_feedback (identity
        để replay cùng feedback_id KHÔNG nhân sample). BẮT BUỘC phải lấy từ
        response `feedback_id` của API, KHÔNG phải expected_version echo.
      - new_version: int — version DB MÀ REVIEW ĐÃ ĐƯỢC COMMIT (server-authoritative).
        Lấy từ response `new_version` của API. KHÔNG dùng `expected_version` (echo input).
      - Trả True nếu enqueue được; False nếu collector chưa start hoặc queue đầy.
      - KHÔNG bao giờ raise.
      - KHÔNG làm I/O (không tạo thư mục/đọc file).

    Idempotency: replay cùng feedback_id → cursor đã có feedback_id →
    worker skip. Worker lấy review.version thật từ adapter/DB để so cursor.
    """
    coll = get_collector()
    if coll is None:
        # Singleton chưa được start_collector_task() → không enqueue
        # (reconciliation sẽ thu lại từ DB khi worker chạy)
        LOG.debug("[task3] on_feedback_recorded: no collector started, skipping enqueue")
        return False
    try:
        return coll.on_feedback(review_id, feedback_id, new_version, source=source)
    except Exception:  # noqa: BLE001
        LOG.exception("[task3] on_feedback_recorded: unexpected error")
        return False


# ----------------------- Collector core -----------------------

class SampleCollector:
    """Bounded queue + worker thread + cursor-based reconcile.

    Workflow:
      1. HTTP endpoint gọi on_feedback() → event enqueued (không I/O).
      2. Worker loop mỗi 5s:
         a. Dequeue events từ queue.
         b. Gọi _handle_event (copy crop → update cursor only on success).
         c. Reconcile pass: cursor-based scan của ALL reviews có version > cursor.
    """

    def __init__(
        self,
        *,
        task_context_path: str | None = None,
        queue_max: int = DEFAULT_QUEUE_MAX,
        batch_max: int = DEFAULT_BATCH_MAX,
        worker_period_sec: float = DEFAULT_WORKER_PERIOD_SEC,
        heartbeat_sec: float = DEFAULT_HEARTBEAT_SEC,
        adapter_fn=None,
        storage_root: str | None = None,
    ) -> None:
        from app.config import BASE_DIR
        self._task_root = Path(task_context_path or (BASE_DIR / "data" / "training"))
        self._cursor_path = self._task_root / CURSOR_FILENAME
        self._metrics_path = self._task_root / METRICS_FILENAME

        self._queue: "queue.Queue[FeedbackEvent | None]" = queue.Queue(maxsize=queue_max)
        self._batch_max = max(1, batch_max)
        self._period = worker_period_sec
        self._heartbeat = heartbeat_sec
        self._adapter_fn = adapter_fn or adapter.list_reviewed_with_feedback
        self._storage_root = Path(storage_root) if storage_root else (
            self._task_root / "collected_assets"
        )

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._started = threading.Event()
        self._metrics = {
            "enqueued": 0,
            "dropped_queue_full": 0,
            "dropped_other": 0,
            "processed": 0,
            "processed_skipped_existing": 0,
            "processed_assets_copied": 0,
            "processed_assets_missing": 0,
            "processed_copy_failed_skipped": 0,
            "reconcile_runs": 0,
            "reconcile_scanned": 0,
            "reconcile_updated": 0,
            "reconcile_errors": 0,
            "errors": 0,
            "last_run_ts": 0.0,
            "last_event_ts": 0.0,
            "started_at": 0.0,
            "heartbeat": 0.0,
        }
        self._metrics_lock = threading.Lock()
        # Cursor: {review_id -> last_acked_feedback_id}
        self._cursor = self._load_cursor()

    # ---------------- Public API ----------------

    def on_feedback(self, review_id: str, feedback_id: int, new_version: int,
                    *, source: str = "feedback") -> bool:
        """Enqueue 1 event. Trả True nếu enqueue được, False nếu queue đầy."""
        if not is_enabled():
            return False
        if not review_id or feedback_id is None or new_version is None:
            return False
        ev = FeedbackEvent(
            review_id=str(review_id),
            feedback_id=int(feedback_id),
            new_version=int(new_version),
            ts=time.time(),
            source=source,
        )
        try:
            self._queue.put_nowait(ev)
            with self._metrics_lock:
                self._metrics["enqueued"] += 1
                self._metrics["last_event_ts"] = ev.ts
            return True
        except queue.Full:
            with self._metrics_lock:
                self._metrics["dropped_queue_full"] += 1
            LOG.warning("[task3] queue full, dropped review_id=%s fb=%s", ev.review_id, ev.feedback_id)
            return False
        except Exception as e:  # noqa: BLE001
            with self._metrics_lock:
                self._metrics["dropped_other"] += 1
                self._metrics["errors"] += 1
            LOG.exception("[task3] enqueue failed: %s", e)
            return False

    def start(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        with self._metrics_lock:
            self._metrics["started_at"] = time.time()
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            name="task3-sample-collector",
            daemon=True,
        )
        self._worker_thread.start()
        self._started.set()
        LOG.info("[task3] sample collector worker started")

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
            self._worker_thread = None
        self._started.clear()

    def metrics(self) -> dict:
        with self._metrics_lock:
            return dict(self._metrics)

    def cursor_state(self) -> dict:
        return dict(self._cursor)

    def run_reconcile_once(self) -> dict:
        """Chạy 1 pass reconcile (test/admin)."""
        return self._reconcile_pass()

    # ---------------- Worker internals ----------------

    def _run_worker(self) -> None:
        last_heartbeat = 0.0
        while not self._stop_event.is_set():
            try:
                ev = self._queue.get(timeout=self._period)
                if ev is not None:
                    self._handle_event(ev)
            except queue.Empty:
                pass
            except Exception as e:  # noqa: BLE001
                LOG.exception("[task3] worker loop error: %s", e)
                with self._metrics_lock:
                    self._metrics["errors"] += 1

            now = time.time()
            if now - last_heartbeat >= self._heartbeat:
                last_heartbeat = now
                self._persist_metrics()
                with self._metrics_lock:
                    self._metrics["heartbeat"] = now

            # Reconcile pass: thu các event bị miss (crash, restart, etc.)
            try:
                self._reconcile_pass()
            except Exception as e:  # noqa: BLE001
                LOG.exception("[task3] reconcile error: %s", e)
                with self._metrics_lock:
                    self._metrics["reconcile_errors"] += 1

        self._persist_metrics()

    def _handle_event(self, ev: FeedbackEvent) -> None:
        """Xử lý 1 queued event.

        C04a: chỉ ACK cursor sau khi asset copy thành công.
        C04b: cursor = (review_id → feedback_id) đã xử lý, không dùng event version.
        P1: identity là feedback_id (server-generated), KHÔNG dùng echo expected_version.
        """
        try:
            full = adapter.fetch_sample_assets(ev.review_id)
        except Exception:  # noqa: BLE001
            full = None

        if not full:
            with self._metrics_lock:
                self._metrics["processed"] += 1
                self._metrics["processed_assets_missing"] += 1
            return

        # C04b/P1: so với cursor (last acked feedback_id)
        cursor_fid = int(self._cursor.get(ev.review_id, 0))
        # Adapter/DB có thể trả latest_feedback_id (server-authoritative) hoặc fallback về version
        latest_fid = int(full.get("latest_feedback_id", 0) or full.get("feedback_id", 0) or 0)
        if latest_fid == 0:
            # fallback dùng version nếu adapter chưa expose latest_feedback_id
            latest_fid = int(full.get("version", 0))
        if latest_fid <= cursor_fid:
            # Đã acked rồi
            with self._metrics_lock:
                self._metrics["processed"] += 1
                self._metrics["processed_skipped_existing"] += 1
            return

        # C04a: chỉ ack sau khi copy thành công
        copied = self._copy_asset_if_needed(full)
        with self._metrics_lock:
            self._metrics["processed"] += 1
            if copied:
                self._metrics["processed_assets_copied"] += 1
            else:
                self._metrics["processed_assets_missing"] += 1
                # C04a: KHÔNG update cursor nếu copy fail → sẽ retry ở reconcile pass
                self._metrics["processed_copy_failed_skipped"] += 1
                LOG.warning("[task3] copy failed for review_id=%s fb=%s, will retry", ev.review_id, ev.feedback_id)
                return

        # C04a: chỉ update cursor khi copy thành công
        self._update_cursor_for(ev.review_id, latest_fid)

    def _copy_asset_if_needed(self, review: dict) -> bool:
        """Copy crop asset vào storage root. Trả True nếu copy thành công."""
        source = review.get("source") or review
        sid = provenance.make_sample_id(
            review_id=review.get("review_id", ""),
            frame_seq=review.get("frame_seq"),
            crop_sha256=source.get("crop_sha256"),
        )
        target = self._storage_root / f"{sid}.bin"
        if target.exists():
            return True
        crop_id = source.get("crop_media_id")
        if not crop_id:
            return False
        path = self._resolve_media_path(crop_id)
        if not path:
            return False
        try:
            self._storage_root.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            return True
        except Exception:  # noqa: BLE001
            LOG.exception("[task3] copy asset failed review_id=%s", review.get("review_id"))
            return False

    def _resolve_media_path(self, crop_media_id: str) -> Path | None:
        """Resolve media ID → file path trong SNAPSHOTS_DIR."""
        from app.config import SNAPSHOTS_DIR
        root = Path(SNAPSHOTS_DIR).resolve()
        candidates = [
            root / crop_media_id,
            root / "snapshots" / crop_media_id,
        ]
        for c in candidates:
            try:
                rp = c.resolve()
            except OSError:
                continue
            try:
                rp.relative_to(root)
            except ValueError:
                continue
            if rp.is_file():
                return rp
        return None

    def _reconcile_pass(self) -> dict:
        """Cursor-based scan: tìm review có version > cursor, process 1 batch.

        C05a: dùng review_id ordering để paginate ổn định, không dùng [:batch_max]
        luôn lấy trang đầu.
        """
        scanned = 0
        updated = 0
        with self._metrics_lock:
            self._metrics["reconcile_runs"] += 1

        try:
            items = self._adapter_fn() if callable(self._adapter_fn) else []
        except Exception as e:  # noqa: BLE001
            LOG.exception("[task3] reconcile adapter call failed: %s", e)
            with self._metrics_lock:
                self._metrics["reconcile_errors"] += 1
            return {"scanned": 0, "updated": 0}

        if not isinstance(items, list):
            return {"scanned": 0, "updated": 0}

        # C05a: sắp xếp theo review_id → paginate stable
        items.sort(key=lambda r: r.get("review_id") or r.get("reviewId") or "")
        last_processed = None

        for r in items:
            rid = r.get("review_id") or r.get("reviewId")
            if not rid:
                continue
            # Skip all items ≤ last cursor key (stable pagination)
            if last_processed is not None and rid <= last_processed:
                continue

            scanned += 1
            with self._metrics_lock:
                self._metrics["reconcile_scanned"] += 1

            cursor_fid = int(self._cursor.get(rid, 0))
            latest_fid = int(r.get("latest_feedback_id", 0) or r.get("feedback_id", 0) or 0)
            if latest_fid == 0:
                latest_fid = int(r.get("version", 0))
            if latest_fid <= cursor_fid:
                continue

            # Attempt copy
            copied = self._copy_asset_if_needed(r)
            with self._metrics_lock:
                if copied:
                    self._metrics["processed_assets_copied"] += 1
                else:
                    self._metrics["processed_assets_missing"] += 1
                    self._metrics["processed_copy_failed_skipped"] += 1
            if not copied:
                continue
            self._update_cursor_for(rid, latest_fid)
            updated += 1
            with self._metrics_lock:
                self._metrics["reconcile_updated"] += 1
            last_processed = rid

            # Process only batch_max items per reconcile pass
            if updated >= self._batch_max:
                break

        with self._metrics_lock:
            self._metrics["last_run_ts"] = time.time()
        return {"scanned": scanned, "updated": updated}

    # ---------------- Cursor / Metrics persistence ----------------

    def _load_cursor(self) -> dict[str, int]:
        """Load cursor JSON. Keys: review_id, Values: last_acked_feedback_id."""
        if not self._cursor_path.exists():
            return {}
        try:
            raw = json.loads(self._cursor_path.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in raw.items()}
        except Exception:  # noqa: BLE001
            LOG.warning("[task3] cursor file unreadable; starting fresh")
            return {}

    def _save_cursor(self) -> None:
        tmp = self._cursor_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cursor, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._cursor_path)

    def _update_cursor_for(self, review_id: str, feedback_id: int) -> None:
        prev = int(self._cursor.get(review_id, 0))
        if feedback_id > prev:
            self._cursor[review_id] = int(feedback_id)
            self._save_cursor()

    def _persist_metrics(self) -> None:
        with self._metrics_lock:
            payload = dict(self._metrics)
        tmp = self._metrics_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._metrics_path)
