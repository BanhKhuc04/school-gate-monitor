"""Provenance utilities — sample/dataset id, hash, dedup.

Tách riêng khỏi DB để dễ test. Mọi helper đều deterministic, không đụng file IO
ngoài SHA256 nội dung bytes. Không phụ thuộc DB_PATH/runtime config.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


_SAMPLE_ID_PREFIX = "smp"
_REVIEW_ID_PREFIX = "rev"
_DATASET_VERSION_PREFIX = "dsv"
_JOB_ID_PREFIX = "trj"
_CANDIDATE_ID_PREFIX = "cnd"


def _sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA256 của bytes (ảnh, crop). Dùng cho crop_sha256/file integrity."""
    return _sha256_hex(data)


def sha256_canonical(obj: Any) -> str:
    """SHA256 của object JSON canonical (sort_keys, ensure_ascii=False, separators=(",", ":"))."""
    payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha256_hex(payload)


def make_sample_id(*, review_id: str, frame_seq: int | None, crop_sha256: str) -> str:
    """sample_id deterministic từ (review_id, frame_seq, crop_sha256).

    - review_id là anh của feedback (crop đã được nhận diện).
    - frame_seq để phân biệt cùng review nhưng crop ở frame khác.
    - crop_sha256 để chống crop "ảo" trùng payload.
    """
    raw = f"{review_id}|{frame_seq if frame_seq is not None else '-'}|{crop_sha256}"
    return f"{_SAMPLE_ID_PREFIX}_{_sha256_hex(raw)[:24]}"


def make_dataset_version_id(*, base: str, ts: datetime | None = None) -> str:
    """dataset_version_id = base + ISO date + nanosecond hash; base để gom cùng dòng dataset."""
    ts = ts or datetime.now(timezone.utc)
    digest = _sha256_hex(ts.isoformat())[:8]
    safe_base = re.sub(r"[^a-zA-Z0-9_-]", "_", base or "ocr") or "ocr"
    return f"{_DATASET_VERSION_PREFIX}_{safe_base}_{ts.strftime('%Y%m%d')}_{digest}"


def make_job_id(*, target: str, ts: datetime | None = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    digest = _sha256_hex(ts.isoformat())[:8]
    safe_target = re.sub(r"[^a-zA-Z0-9_-]", "_", target or "ocr") or "ocr"
    return f"{_JOB_ID_PREFIX}_{safe_target}_{ts.strftime('%Y%m%dT%H%M%S')}_{digest}"


def make_candidate_id(*, target: str, ts: datetime | None = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    digest = _sha256_hex(ts.isoformat())[:8]
    safe_target = re.sub(r"[^a-zA-Z0-9_-]", "_", target or "ocr") or "ocr"
    return f"{_CANDIDATE_ID_PREFIX}_{safe_target}_{ts.strftime('%Y%m%dT%H%M%S')}_{digest}"


def normalize_plate_text(text: str) -> str:
    """Canonical plate — uppercase, bỏ dấu cách/ký tự không phải A-Z0-9; '89F1 237 92' → '89F123792'.

    Tách hẳn ra để mọi adapter dùng cùng quy ước. KHÔNG tự bịa — trả về nguyên chuỗi
    đã normalize, kể cả khi rỗng. Caller tự kiểm tra độ dài tối thiểu.
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", plain.upper())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_split_hash(*, samples: list[dict], split_map: dict[str, str]) -> str:
    """Hash của split assignment.

    Args:
        samples: list sample {target_id, split} (split ∈ {train, val, holdout, ...}).
        split_map: {target_id: split_name} — mapping từ target_id sang split.

    Returns:
        64-char SHA256 hex, deterministic theo sorted (target_id, split).
    """
    if not isinstance(samples, list):
        raise TypeError("samples phải là list")
    if not isinstance(split_map, dict):
        raise TypeError("split_map phải là dict")
    rows = []
    for s in samples:
        tid = str(s.get("target_id") or s.get("id") or "")
        if not tid:
            continue
        rows.append((tid, str(split_map.get(tid, s.get("split") or ""))))
    rows.sort()
    payload = "\n".join(f"{tid}\t{sp}" for tid, sp in rows)
    return _sha256_hex(payload)


def compute_dataset_snapshot(*, dataset_id: str, samples: list[dict],
                             freeze_state: str = "draft",
                             source_hash: str | None = None) -> str:
    """Hash của dataset state tại 1 thời điểm (P5 provenance).

    Args:
        dataset_id: ID dataset.
        samples: list sample {target_id, sample_json, split, holdout, review_id}.
        freeze_state: 'draft' | 'frozen'.
        source_hash: optional manifest hash từ freeze.

    Returns:
        64-char SHA256 hex, deterministic theo (dataset_id, sorted samples, freeze_state, source_hash).
    """
    if not isinstance(samples, list):
        raise TypeError("samples phải là list")
    rows = []
    for s in samples:
        rows.append((
            str(s.get("target_id") or ""),
            str(s.get("review_id") or ""),
            str(s.get("split") or ""),
            str(s.get("holdout") or 0),
            str(s.get("sample_json") or ""),
        ))
    rows.sort()
    payload = json.dumps({
        "dataset_id": str(dataset_id),
        "freeze_state": str(freeze_state),
        "source_hash": str(source_hash) if source_hash else "",
        "samples": rows,
    }, sort_keys=True, ensure_ascii=False)
    return _sha256_hex(payload)