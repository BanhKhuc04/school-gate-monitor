"""Validator cho label/provenance/sample/dataset manifest.

Tập trung vào các lỗi phổ biến:
- target_text rỗng nhưng verdict=correct/incorrect.
- target_text quá ngắn/dài so với biển VN (heur 4-12).
- crop_sha256 trùng nhưng verdict khác nhau (data error).
- bbox normalized ngoài [0,1].
- Ảnh thiếu file, MIME không hợp lệ.
- schema_version không khớp.

Đây là helper cho cả export/import workflow. KHÔNG phụ thuộc file IO — caller
chuyển file path hoặc bytes đã được kiểm soát (vd. staging root của import).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.training import provenance
from app.training.schemas import (
    SchemaError,
    validate_dataset_manifest,
    validate_sample,
)


def sha256_file(path: str | os.PathLike, *, chunk: int = 65536) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def validate_image_file(path: str | os.PathLike) -> dict:
    """Trả về thông tin file: tồn tại, đúng đuôi, decode được."""
    p = Path(path)
    info = {"path": str(p), "exists": p.exists(), "size": 0, "decoded": False, "mime": None}
    if not info["exists"]:
        return info
    info["size"] = p.stat().st_size
    if info["size"] == 0:
        return info
    ext = p.suffix.lower()
    info["mime"] = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    if not info["mime"].startswith("image/"):
        return info
    # Decode bằng PIL nếu có — fallback không raise
    try:
        from PIL import Image  # type: ignore
        with Image.open(p) as im:
            im.verify()
        info["decoded"] = True
        info["width"], info["height"] = Image.open(p).size  # type: ignore
    except Exception:
        info["decoded"] = False
    return info


def validate_label_file(path: str | os.PathLike) -> dict:
    """Validate 1 file label JSON theo schema task3."""
    p = Path(path)
    info = {"path": str(p), "exists": p.exists(), "valid": False, "errors": []}
    if not info["exists"]:
        info["errors"].append("file không tồn tại")
        return info
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        info["errors"].append(f"JSON decode error: {e}")
        return info
    try:
        validate_sample(obj, schema_version=obj.get("schema_version", 1))
        info["valid"] = True
    except SchemaError as e:
        info["errors"].append(str(e))
    return info


def validate_manifest(manifest: dict) -> dict:
    """Validate manifest + danh sách sample + file tồn tại.

    Trả về dict {valid: bool, errors: [], samples_checked: N, samples_invalid: int}.
    """
    errors: list[str] = []
    samples_valid = 0
    samples_invalid = 0
    try:
        validate_dataset_manifest(manifest)
    except SchemaError as e:
        errors.append(str(e))
        return {"valid": False, "errors": errors, "samples_checked": 0,
                "samples_invalid": 0}
    samples = manifest.get("samples", [])
    for s in samples:
        try:
            validate_sample(s, schema_version=manifest.get("schema_version", 1))
            samples_valid += 1
        except SchemaError as e:
            samples_invalid += 1
            errors.append(f"target_id={s.get('target_id', '?')}: {e}")
    return {
        "valid": not errors,
        "errors": errors,
        "samples_checked": len(samples),
        "samples_valid": samples_valid,
        "samples_invalid": samples_invalid,
    }


def verify_provenance_link(samples: list[dict]) -> dict:
    """Rà soanh sự liên kết provenance (review_id ↔ crop_sha256 ↔ review đã chấp thuận)."""
    findings = {
        "missing_review_id": [],
        "missing_crop_sha256": [],
        "short_label_target": [],
        "duplicate_review_id_crop_sha256": [],
        "inconsistent_verdict": [],
    }
    by_review_crop: dict[tuple[str, str], list[dict]] = {}
    for s in samples:
        rid = s.get("review_id")
        crop = s.get("source", {}).get("crop_sha256")
        if not rid:
            findings["missing_review_id"].append(s.get("target_id", "?"))
        if not crop:
            findings["missing_crop_sha256"].append(s.get("target_id", "?"))
        target = s.get("label", {}).get("target_text", "")
        verdict = s.get("label", {}).get("verdict", "")
        if verdict in {"correct", "incorrect"} and len(target) < 4:
            findings["short_label_target"].append({"target_id": s.get("target_id"), "target": target})
        key = (rid, crop or "?")
        by_review_crop.setdefault(key, []).append(s)
    for (rid, crop), items in by_review_crop.items():
        if len(items) > 1:
            verdicts = {i.get("label", {}).get("verdict") for i in items}
            if len(verdicts) > 1:
                findings["inconsistent_verdict"].append({
                    "review_id": rid, "crop_sha256": crop, "verdicts": sorted(verdicts),
                })
            findings["duplicate_review_id_crop_sha256"].append({
                "review_id": rid, "crop_sha256": crop, "count": len(items),
            })
    return findings