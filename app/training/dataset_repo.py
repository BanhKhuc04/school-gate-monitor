"""Dataset repository — lưu dataset version + samples (Task 3 QA DB riêng).

Bảng:
  datasets (id, name, schema_version, created_at, freeze_state)
  dataset_samples (dataset_id, target_id, label_json, source_json, bbox_json,
               classes_json, crop_path, image_w, image_h, holdout, split, review_id,
               added_at)
  dataset_jobs (id, dataset_id, target, state, created_at, finished_at, config_json,
              log_path, metrics_path)
  dataset_candidates (id, job_id, engine, model_class, model_path, image_hash,
                     created_at, promoted_at, retired_at)

Repository dùng path DB riêng (DATASET_DB_PATH env hoặc data/training.db mặc
định). KHÔNG dùng chung DB_PATH với runtime vận hành (Task 3 nguyên tắc #2).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.training import provenance
from app.training.schemas import (
    SPLIT_NAMES,
    SchemaError,
    safe_name,
    validate_sample,
)


_WRITE_LOCK = threading.Lock()


def default_db_path() -> str:
    from app.config import BASE_DIR
    p = os.environ.get("TRAINING_DB_PATH") or str(BASE_DIR / "data" / "training.db")
    return p


def _connect(dsn: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(dsn), exist_ok=True)
    conn = sqlite3.connect(dsn, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager cho một connection. Caller quyết định đóng."""
    dsn = db_path or default_db_path()
    conn = _connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Tạo schema Task 3 — idempotent."""
    dsn = db_path or default_db_path()
    with _WRITE_LOCK:
        conn = _connect(dsn)
        try:
            cur = conn.cursor()
            cur.execute('''
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
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS dataset_samples (
                    dataset_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    sample_json TEXT NOT NULL,
                    split TEXT,
                    holdout INTEGER NOT NULL DEFAULT 0,
                    review_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, target_id)
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_samples_review ON dataset_samples(review_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_samples_split ON dataset_samples(dataset_id, split)')

            cur.execute('''
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
                )
            ''')
            # CREATE TABLE IF NOT EXISTS does not upgrade an existing database.
            columns = {r[1] for r in cur.execute("PRAGMA table_info(dataset_jobs)")}
            for name, definition in {
                "operation": "TEXT NOT NULL DEFAULT 'evaluate_baseline'",
                "runner_type": "TEXT",
                "split_hash": "TEXT",
            }.items():
                if name not in columns:
                    cur.execute(f"ALTER TABLE dataset_jobs ADD COLUMN {name} {definition}")
            cur.execute('CREATE INDEX IF NOT EXISTS idx_jobs_state ON dataset_jobs(state, created_at)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_jobs_dataset ON dataset_jobs(dataset_id, created_at DESC)')

            cur.execute('''
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
                )
            ''')
            columns = {r[1] for r in cur.execute("PRAGMA table_info(dataset_candidates)")}
            for name, definition in {
                "dataset_id": "TEXT NOT NULL DEFAULT ''",
                "model_sha256": "TEXT",
                "metrics_path": "TEXT",
            }.items():
                if name not in columns:
                    cur.execute(f"ALTER TABLE dataset_candidates ADD COLUMN {name} {definition}")
            cur.execute('CREATE INDEX IF NOT EXISTS idx_candidates_job ON dataset_candidates(job_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_candidates_engine ON dataset_candidates(engine, state)')
            conn.commit()
        finally:
            conn.close()


# ─── Dataset CRUD ─────────────────────────────────────────────────────────────

def create_dataset(*, name: str, engine: str, schema_version: int = 1,
                   notes: str = "", db_path: str | None = None) -> str:
    safe_name(name, label="name")
    if engine not in {"plate_ocr", "plate_detector", "helmet"}:
        raise SchemaError(f"engine={engine!r} không hỗ trợ")
    dataset_id = provenance.make_dataset_version_id(base=f"{engine}-{name}")
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO datasets (id, name, engine, schema_version, created_at, freeze_state, notes) "
                "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
                (dataset_id, name, engine, schema_version, provenance.now_iso(), notes),
            )
            conn.commit()
        finally:
            conn.close()
    return dataset_id


def freeze_dataset(dataset_id: str, *, db_path: str | None = None) -> None:
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE datasets SET freeze_state='frozen' WHERE id=? AND freeze_state='draft'",
                (dataset_id,),
            )
            if cur.rowcount == 0:
                raise SchemaError(f"dataset_id={dataset_id!r} không tồn tại hoặc đã frozen")
            conn.commit()
        finally:
            conn.close()


def list_datasets(*, engine: str | None = None, db_path: str | None = None) -> list[dict]:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        if engine:
            cur.execute(
                "SELECT id, name, engine, schema_version, created_at, freeze_state, manifest_path, source_hash, notes "
                "FROM datasets WHERE engine=? ORDER BY created_at DESC", (engine,)
            )
        else:
            cur.execute(
                "SELECT id, name, engine, schema_version, created_at, freeze_state, manifest_path, source_hash, notes "
                "FROM datasets ORDER BY created_at DESC"
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_dataset(dataset_id: str, db_path: str | None = None) -> dict | None:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, engine, schema_version, created_at, freeze_state, manifest_path, source_hash, notes "
            "FROM datasets WHERE id=?", (dataset_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_samples(dataset_id: str, samples: list[dict], *,
                split: str | None = None, db_path: str | None = None) -> int:
    """Thêm nhiều sample vào dataset. Idempotent theo (dataset_id, target_id)."""
    if split is not None and split not in SPLIT_NAMES:
        raise SchemaError(f"split={split!r} không thuộc {SPLIT_NAMES}")
    added = 0
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute("SELECT freeze_state FROM datasets WHERE id=?", (dataset_id,))
            row = cur.fetchone()
            if row is None:
                raise SchemaError(f"dataset_id={dataset_id!r} không tồn tại")
            if row["freeze_state"] != "draft":
                raise SchemaError(f"dataset_id={dataset_id!r} đã frozen — không thêm được")
            for sample in samples:
                validate_sample(sample, schema_version=1)
                cur.execute(
                    "INSERT OR REPLACE INTO dataset_samples "
                    "(dataset_id, target_id, sample_json, split, holdout, review_id, added_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (dataset_id, sample["target_id"], json.dumps(sample, ensure_ascii=False),
                     split or sample.get("split"), int(bool(sample.get("holdout", False))),
                     sample["review_id"], provenance.now_iso()),
                )
                added += 1
            conn.commit()
        finally:
            conn.close()
    return added


def list_samples(dataset_id: str, *, split: str | None = None, db_path: str | None = None) -> list[dict]:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        if split:
            cur.execute(
                "SELECT target_id, sample_json, split, holdout, review_id, added_at "
                "FROM dataset_samples WHERE dataset_id=? AND split=? ORDER BY added_at",
                (dataset_id, split),
            )
        else:
            cur.execute(
                "SELECT target_id, sample_json, split, holdout, review_id, added_at "
                "FROM dataset_samples WHERE dataset_id=? ORDER BY added_at",
                (dataset_id,),
            )
        rows = []
        for r in cur.fetchall():
            data = json.loads(r["sample_json"])
            data["_split"] = r["split"]
            data["_holdout"] = bool(r["holdout"])
            data["_review_id"] = r["review_id"]
            data["_added_at"] = r["added_at"]
            rows.append(data)
        return rows
    finally:
        conn.close()


def set_sample_split(dataset_id: str, target_id: str, split: str, *,
                     db_path: str | None = None) -> None:
    if split not in SPLIT_NAMES:
        raise SchemaError(f"split={split!r} không thuộc {SPLIT_NAMES}")
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dataset_samples SET split=? WHERE dataset_id=? AND target_id=?",
                (split, dataset_id, target_id),
            )
            if cur.rowcount == 0:
                raise SchemaError(f"sample không tồn tại: ({dataset_id}, {target_id})")
            conn.commit()
        finally:
            conn.close()


def update_sample_bbox(dataset_id: str, target_id: str, *,
                        bbox: list[float], version: int,
                        bbox_history: list[dict],
                        db_path: str | None = None) -> None:
    """Sửa bbox + version + history cho 1 sample (khi dataset còn draft).

    Đọc sample_json, cập nhật bbox + version + bbox_history, ghi lại. KHÔNG
    tự kiểm tra freeze (API layer sẽ kiểm tra; repo cho phép vì có thể
    gọi từ script admin).
    """
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT freeze_state, sample_json FROM datasets d "
                "JOIN dataset_samples s ON s.dataset_id = d.id "
                "WHERE s.dataset_id=? AND s.target_id=?",
                (dataset_id, target_id),
            )
            row = cur.fetchone()
            if row is None:
                raise SchemaError(f"sample không tồn tại: ({dataset_id}, {target_id})")
            if row["freeze_state"] != "draft":
                raise SchemaError(f"dataset đã {row['freeze_state']} — không sửa bbox được")
            sample = json.loads(row["sample_json"])
            sample["bbox"] = list(bbox)
            sample["version"] = int(version)
            sample["bbox_history"] = list(bbox_history)
            cur.execute(
                "UPDATE dataset_samples SET sample_json=? WHERE dataset_id=? AND target_id=?",
                (json.dumps(sample, ensure_ascii=False), dataset_id, target_id),
            )
            conn.commit()
        finally:
            conn.close()


# ─── Job lifecycle ────────────────────────────────────────────────────────────

JOB_STATES = (
    "queued",
    "waiting_resource",
    "preparing",
    "training",
    "evaluating",
    "pending_data",
    "unsupported",
    "completed",
    "failed",
    "cancelled",
)


def create_job(*, dataset_id: str, target: str, config: dict,
               db_path: str | None = None,
               operation: str = "evaluate_baseline") -> str:
    """Tạo job training/evaluation.

    P4: operation ∈ {'evaluate_baseline', 'train'} — UI/API phân biệt rõ.
      - 'evaluate_baseline': chạy EasyOCR baseline inference (KHÔNG optimize weights).
      - 'train': chạy optimization thật với weights mới (chưa implement cho OCR).

    Default 'evaluate_baseline' để job cũ không crash, nhưng worker sẽ đánh dấu
    job completed KHÔNG eligible cho promotion (gate `_verify_job_completed`).
    """
    if target not in ("plate_ocr", "plate_detector", "helmet"):
        raise SchemaError(f"target={target!r} không hỗ trợ")
    if operation not in ("evaluate_baseline", "train"):
        raise SchemaError(f"operation={operation!r} không được hỗ trợ")
    job_id = provenance.make_job_id(target=target)
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dataset_jobs (id, dataset_id, target, state, created_at, config_json, operation) "
                "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                (job_id, dataset_id, target, provenance.now_iso(),
                 json.dumps(config, ensure_ascii=False), operation),
            )
            conn.commit()
        finally:
            conn.close()
    return job_id


def transition_job(job_id: str, *, expected: str, new_state: str,
                   error: str | None = None, db_path: str | None = None) -> bool:
    if new_state not in JOB_STATES:
        raise SchemaError(f"state={new_state!r} không hợp lệ")
    finished_at = provenance.now_iso() if new_state in {"completed", "failed", "cancelled"} else None
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dataset_jobs SET state=?, finished_at=COALESCE(finished_at, ?), error=COALESCE(?, error) "
                "WHERE id=? AND state=?",
                (new_state, finished_at, error, job_id, expected),
            )
            ok = cur.rowcount > 0
            conn.commit()
            return ok
        finally:
            conn.close()


def set_job_runner_type(job_id: str, *, runner_type: str, db_path: str | None = None) -> None:
    """Ghi runner_type cho job (P3 + P4 phân biệt evaluate_baseline vs train)."""
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dataset_jobs SET runner_type=? WHERE id=?",
                (runner_type, job_id),
            )
            conn.commit()
        finally:
            conn.close()


def set_job_split_hash(job_id: str, *, split_hash: str, db_path: str | None = None) -> None:
    """Ghi split_hash cho job (P5 provenance)."""
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dataset_jobs SET split_hash=? WHERE id=?",
                (split_hash, job_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_job(job_id: str, db_path: str | None = None) -> dict | None:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, dataset_id, target, state, created_at, finished_at, config_json, "
            "log_path, metrics_path, error, gpu_resource_id, operation, runner_type, split_hash "
            "FROM dataset_jobs WHERE id=?",
            (job_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_jobs(*, state: str | None = None, db_path: str | None = None) -> list[dict]:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        if state:
            cur.execute(
                "SELECT id, dataset_id, target, state, created_at, finished_at, "
                "operation, runner_type, split_hash FROM dataset_jobs WHERE state=? ORDER BY created_at DESC", (state,)
            )
        else:
            cur.execute(
                "SELECT id, dataset_id, target, state, created_at, finished_at, "
                "operation, runner_type, split_hash FROM dataset_jobs ORDER BY created_at DESC"
            )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def active_job_count(*, target: str | None = None, exclude_job_id: str | None = None,
                     db_path: str | None = None) -> int:
    """Số job đang THẬT sự giữ GPU lease.

    Theo contract E4:
      - queued, waiting_resource: KHÔNG chiếm lease (chưa chạy).
      - preparing, training, evaluating: chiếm lease.

    `exclude_job_id` để không tính chính job đang xét.
    """
    running = {"preparing", "training", "evaluating"}
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        conditions = []
        params: list = []
        if target:
            conditions.append("target=?")
            params.append(target)
        conditions.append(f"state IN ({','.join(['?']*len(running))})")
        params.extend(running)
        if exclude_job_id:
            conditions.append("id != ?")
            params.append(exclude_job_id)
        where = " AND ".join(conditions)
        cur.execute(f"SELECT COUNT(*) FROM dataset_jobs WHERE {where}", params)
        return int(cur.fetchone()[0])
    finally:
        conn.close()


# ─── Candidate ────────────────────────────────────────────────────────────────

def create_candidate(*, job_id: str, engine: str, target: str, model_class: str,
                      model_path: str, config: dict,
                      model_sha256: str = "", db_path: str | None = None,
                      dataset_id: str = "", metrics_path: str | None = None) -> str:
    candidate_id = provenance.make_candidate_id(target=engine)
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dataset_candidates "
                "(id, job_id, dataset_id, engine, target, model_class, model_path, model_sha256, config_json, created_at, state, metrics_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)",
                (candidate_id, job_id, dataset_id, engine, target, model_class, model_path,
                 model_sha256, json.dumps(config, ensure_ascii=False), provenance.now_iso(),
                 metrics_path),
            )
            conn.commit()
        finally:
            conn.close()
    return candidate_id


def get_candidate(candidate_id: str, db_path: str | None = None) -> dict | None:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, job_id, dataset_id, engine, target, model_class, model_path, model_sha256, config_json, "
            "created_at, promoted_at, retired_at, state, metrics_path FROM dataset_candidates WHERE id=?",
            (candidate_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_candidates(*, engine: str | None = None, state: str | None = None,
                    db_path: str | None = None) -> list[dict]:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        conditions = ["1=1"]
        params: list = []
        if engine:
            conditions.append("engine=?")
            params.append(engine)
        if state:
            conditions.append("state=?")
            params.append(state)
        cur.execute(
            "SELECT id, job_id, engine, target, model_class, model_path, model_sha256, created_at, "
            "promoted_at, retired_at, state FROM dataset_candidates WHERE "
            + " AND ".join(conditions) + " ORDER BY created_at DESC",
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def promote_candidate(candidate_id: str, *, db_path: str | None = None) -> None:
    """Đánh dấu candidate là active; retire bất kỳ candidate active cùng engine trước đó."""
    cand = get_candidate(candidate_id, db_path=db_path)
    if cand is None:
        raise SchemaError(f"candidate_id={candidate_id!r} không tồn tại")
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            # Retire previous active candidates of the same engine
            cur.execute(
                "UPDATE dataset_candidates SET state='retired', retired_at=? "
                "WHERE engine=? AND state='active'",
                (provenance.now_iso(), cand["engine"]),
            )
            cur.execute(
                "UPDATE dataset_candidates SET state='active', promoted_at=? WHERE id=?",
                (provenance.now_iso(), candidate_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_active_candidate(engine: str, db_path: str | None = None) -> dict | None:
    conn = _connect(db_path or default_db_path())
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, job_id, engine, model_class, model_path, model_sha256, config_json, "
            "created_at, promoted_at, retired_at, state FROM dataset_candidates "
            "WHERE engine=? AND state='active' ORDER BY promoted_at DESC LIMIT 1",
            (engine,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def rollback_to_baseline(engine: str, *, db_path: str | None = None) -> bool:
    """Retire candidate active hiện tại; trả về True nếu có candidate bị retire."""
    with _WRITE_LOCK:
        conn = _connect(db_path or default_db_path())
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dataset_candidates SET state='retired', retired_at=? "
                "WHERE engine=? AND state='active'",
                (provenance.now_iso(), engine),
            )
            ok = cur.rowcount > 0
            conn.commit()
            return ok
        finally:
            conn.close()


# ─── Audit log (best-effort, no credentials) ─────────────────────────────────

def append_audit(*, kind: str, payload: dict, db_path: str | None = None) -> None:
    """Best-effort audit row. Không commit vào runtime DB. Dùng cho trace."""
    try:
        dsn = db_path or default_db_path()
        os.makedirs(os.path.dirname(dsn), exist_ok=True)
        with _WRITE_LOCK:
            conn = _connect(dsn)
            try:
                cur = conn.cursor()
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS training_audit ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
                    "payload_json TEXT NOT NULL, created_at TEXT NOT NULL)"
                )
                cur.execute(
                    "INSERT INTO training_audit (kind, payload_json, created_at) VALUES (?, ?, ?)",
                    (kind, json.dumps(payload, ensure_ascii=False), provenance.now_iso()),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:  # noqa: BLE001 — best-effort, must not raise
        pass
