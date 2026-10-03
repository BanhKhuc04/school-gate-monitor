"""Dataset freeze — tạo snapshot immutable cho job training.

Khi freeze:
  - Lưu dataset manifest + class mapping + class mapping version vào.manifest_path.
  - Ghi source_hash (sha256 của manifest canonical) để chống sửa giữa kỳ.
  - Chuyển freeze_state='frozen'. Sau đó không thêm/sửa sample được.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.training import provenance
from app.training import dataset_repo, splits
from app.training.schemas import SchemaError, safe_name


def freeze(dataset_id: str, *, output_dir: str | None = None,
           db_path: str | None = None) -> dict:
    """Đóng băng dataset_id: ghi manifest.json vào output_dir, set freeze_state='frozen'."""
    meta = dataset_repo.get_dataset(dataset_id, db_path=db_path)
    if meta is None:
        raise SchemaError(f"dataset_id={dataset_id!r} không tồn tại")
    samples = dataset_repo.list_samples(dataset_id, db_path=db_path)
    if not samples:
        raise SchemaError("dataset rỗng — không thể freeze")

    if output_dir is None:
        from app.config import BASE_DIR
        output_dir = str(Path(os.environ.get('TASK3_CONTEXT_PATH') or BASE_DIR / 'data' / 'training') / 'datasets' / dataset_id)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Lưu manifest dạng canonical (sorted_keys) để hash ổn định.
    manifest = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "name": meta["name"],
        "engine": meta["engine"],
        "freeze_state": "frozen",
        "frozen_at": provenance.now_iso(),
        "class_mapping": _class_mapping_for(meta["engine"]),
        "class_mapping_version": _class_mapping_version(),
        "samples": samples,
    }
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    source_hash = provenance.sha256_canonical(json.loads(canonical))
    manifest["source_hash"] = source_hash

    out_file = out_path / "manifest.json"
    out_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Sidecar hash để chống sửa giữa kỳ
    (out_path / "manifest.sha256").write_text(f"{source_hash}  manifest.json\n", encoding="utf-8")

    # Lưu lại manifest_path vào dataset row + freeze
    _update_manifest_path(dataset_id, str(out_file), db_path=db_path)
    dataset_repo.freeze_dataset(dataset_id, db_path=db_path)
    return {
        "dataset_id": dataset_id,
        "manifest_path": str(out_file),
        "source_hash": source_hash,
        "sample_count": len(samples),
        "stats": splits.dataset_stats(samples),
    }


def _update_manifest_path(dataset_id: str, manifest_path: str, *, db_path: str | None = None) -> None:
    """Helper: lưu lại manifest_path vào dataset row."""
    from app.training import dataset_repo as _repo
    dsn = db_path or _repo.default_db_path()
    import sqlite3 as _sqlite3
    conn = _repo._connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE datasets SET manifest_path=? WHERE id=?",
            (manifest_path, dataset_id),
        )
        conn.commit()
    finally:
        conn.close()


def _class_mapping_for(engine: str) -> dict:
    if engine == "plate_detector":
        return {"0": "plate"}
    if engine == "plate_ocr":
        return {"alphabet": "0-9A-Z"}  # EasyOCR default reader alphabet
    if engine == "helmet":
        # Match cấu hình vận hànhành trong app/config.py HELMET_MODEL_MAPPING
        return {"0": "With Helmet", "1": "Without Helmet"}
    return {}


def _class_mapping_version() -> str:
    return os.environ.get("HELMET_MODEL_MAPPING", "0=With Helmet,1=Without Helmet")


def verify_frozen(dataset_id: str, *, manifest_path: str | None = None,
                  db_path: str | None = None) -> dict:
    """Đọc lại manifest + hash; fail nếu lệch."""
    meta = dataset_repo.get_dataset(dataset_id, db_path=db_path)
    if meta is None:
        raise SchemaError(f"dataset_id={dataset_id!r} không tồn tại")
    if manifest_path is None:
        manifest_path = meta.get("manifest_path")
    if not manifest_path or not Path(manifest_path).exists():
        raise SchemaError(f"manifest_path={manifest_path!r} không tồn tại")
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    canonical = json.dumps({k: v for k, v in data.items() if k != "source_hash"},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    expected = provenance.sha256_canonical(json.loads(canonical))
    if data.get("source_hash") and data["source_hash"] != expected:
        raise SchemaError(f"manifest bị khớp source_hash; có người sửa giữa kỳ")
    return {"dataset_id": dataset_id, "manifest_path": manifest_path,
            "source_hash": data.get("source_hash"), "samples": len(data.get("samples", []))}
