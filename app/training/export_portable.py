"""Export portable dataset — ZIP ảnh thật + crops + manifest.

So với scripts/export_plate_dataset.py cũ (chỉ manifest JSON):
  - Đính kèm ảnh: context image (nếu có) + crop image (crop_media_id).
  - Manifest có source/manifest/schema_version, hashes, class mapping version.
  - Cho phép sửa nhãn ngoài rồi import lại.

Giới hạn bảo vệ:
  - ZIP chỉ chứa file ảnh + manifest + README; không đính kèm .pt/model.
  - Khi zip_path đã tồn tại → KHÔNG overwrite nhãn mới hơn.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.training import dataset_repo, provenance
from app.training.schemas import SchemaError, validate_sample


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def export_portable_zip(
    *,
    dataset_id: str,
    output_path: str | None = None,
    db_path: str | None = None,
    staging_dir: str | None = None,
    fail_on_missing_crops: bool = True,
    max_missing_ratio: float = 1.0,
) -> dict:
    """Đóng gói dataset + ZIP outputs để giao ngoài.

    Returns dict với zip_path, missing_files, asset_count.

    Raises:
      SchemaError nếu fail_on_missing_crops=True và tỷ lệ missing vượt
      max_missing_ratio (mặc định 100% = cảm mất tất cả). Caller có thể
      pass fail_on_missing_crops=False để vẫn xuất ZIP (vd. gói manifest-only).

    Rule về tỷ lệ missing:
      - Nếu dataset có crop_media_id mà KHÔNG tìm thấy file ảnh → missing.
      - Sample không có crop_media_id (vd. đánh label 'unreadable') → KHÔNG tính
        missing (chỉ là case đánh giá không có ảnh).
    """
    meta = dataset_repo.get_dataset(dataset_id, db_path=db_path)
    if meta is None:
        raise SchemaError(f"dataset_id={dataset_id!r} không tồn tại")
    if meta.get("freeze_state") != "frozen":
        raise SchemaError("dataset chưa frozen — freeze trước khi export")
    if not meta.get("manifest_path") or not Path(meta["manifest_path"]).exists():
        raise SchemaError("manifest_path không tồn tại — freeze lại dataset")

    if output_path is None:
        from app.config import BASE_DIR
        output_path = str(BASE_DIR / "data" / "training" / "exports" / f"{dataset_id}.zip")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(Path(meta["manifest_path"]).read_text(encoding="utf-8"))
    samples = manifest.get("samples", [])

    # Snapshot path staging (chỉ chứa file trong datasets/training_root)
    if staging_dir is None:
        from app.config import BASE_DIR
        staging_dir = str(BASE_DIR / "data" / "training" / "exports" / f"_staging_{dataset_id}")
    sdir = Path(staging_dir)
    sdir.mkdir(parents=True, exist_ok=True)

    # Đính kèm ảnh crop (nếu crop_media_id tồn tại trong SNAPSHOTS_DIR)
    from app.config import SNAPSHOTS_DIR
    snapshots_root = Path(SNAPSHOTS_DIR)
    images_dir = sdir / "images"
    images_dir.mkdir(exist_ok=True)
    file_inventory: list[dict] = []
    missing_files: list[str] = []
    expected_with_crop = 0

    for s in samples:
        crop_id = s.get("source", {}).get("crop_media_id")
        if not crop_id:
            # Sample không có crop — không tính missing, chỉ note
            continue
        expected_with_crop += 1
        # Tìm file crop — flat hoặc snapshots/<id>
        candidates = [
            snapshots_root / crop_id,
            snapshots_root / "snapshots" / crop_id,
        ]
        resolved = None
        for cand in candidates:
            if cand.exists() and cand.is_file():
                # path traversal guard
                if not str(cand.resolve()).startswith(str(snapshots_root.resolve())):
                    missing_files.append(f"{s.get('target_id')}: path traversal {cand}")
                    continue
                resolved = cand
                break
        if not resolved:
            missing_files.append(f"{s.get('target_id')}: crop {crop_id} không tìm thấy")
            continue
        target_name = f"{s['target_id']}{Path(crop_id).suffix}"
        target_in_zip = images_dir / target_name
        # Đã có sẵn → bỏ qua (idempotent)
        if not target_in_zip.exists():
            target_in_zip.write_bytes(resolved.read_bytes())
        file_inventory.append({
            "target_id": s["target_id"],
            "review_id": s["review_id"],
            "filename": target_name,
            "source_path": str(resolved),
            "size": resolved.stat().st_size,
            "sha256": provenance.sha256_bytes(resolved.read_bytes()),
        })

    # Tỷ lệ missing / expected_with_crop; nếu vượt ngưỡng → fail
    if fail_on_missing_crops and expected_with_crop > 0:
        missing_ratio = len(missing_files) / expected_with_crop
        if missing_ratio > max_missing_ratio:
            raise SchemaError(
                f"export thất bại: {len(missing_files)}/{expected_with_crop} sample "
                f"thiếu crop (ratio={missing_ratio:.2f} > {max_missing_ratio})"
            )

    # Đính kèm manifest + README
    (sdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (sdir / "README.md").write_text(_readme(dataset_id, manifest, missing_files), encoding="utf-8")

    # Pack ZIP
    if Path(output_path).exists():
        # Không overwrite nhãn mới hơn — đổi tên file cũ thành .prev
        backup = Path(str(output_path) + ".prev")
        backup.write_bytes(Path(output_path).read_bytes())
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(sdir.rglob("*")):
            if path.is_file():
                arc = path.relative_to(sdir).as_posix()
                zf.write(path, arc)
    return {
        "zip_path": output_path,
        "sample_count": len(samples),
        "expected_with_crop": expected_with_crop,
        "asset_count": len(file_inventory),
        "missing_files": missing_files,
    }


def _readme(dataset_id: str, manifest: dict, missing: list[str]) -> str:
    n_sample = len(manifest.get("samples", []))
    eng = manifest.get("engine", "?")
    return f"""# Dataset {dataset_id}

- engine: `{eng}`
- schema_version: {manifest.get('schema_version', 1)}
- class_mapping: `{json.dumps(manifest.get('class_mapping', {}), ensure_ascii=False)}`
- class_mapping_version: `{manifest.get('class_mapping_version', 'unknown')}`
- frozen_at: {manifest.get('frozen_at', 'unknown')}
- sample_count: {n_sample}

## Cấu trúc gói

- `manifest.json` — schema metadata + samples. KHÔNG tự ý đổi schema_version.
- `images/` — crop ảnh gốc từng sample (nếu crop_media_id tồn tại runtime).
- `README.md` — file này.

## Sửa nhãn bên ngoài

1. Sửa `manifest.json::samples[*].label.target_text` (canonical, uppercase, A-Z0-9).
2. KHÔNG đổi `target_id` / `review_id`.
3. KHÔNG sửa ảnh (crop pixel-level).
4. KHÔNG đổi class_mapping_version.

Sau đó dùng `python -m app.training.import_portable import <zip> --preview` để xem diff
trước khi apply.

## Missing files

{len(missing)} sample thiếu ảnh (xem `missing.txt` nếu có).

## Lưu ý bảo mật

ZIP chỉ chứa ảnh crop (face/cảnh biển). KHÔNG đính kèm `.pt` weights — import model là
luồng riêng (`scripts/training/import_candidate_models.py`).
"""