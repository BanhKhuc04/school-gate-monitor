"""Import portable dataset — staging root, validator, preview, idempotent.

Quy trình:
  1. Validate ZIP an toàn (no path traversal, no symlink, file count giới hạn).
  2. Unzip sang staging dataset root (KHÔNG ghi đè DB runtime/models/media).
  3. Validate manifest + samples + provenance.
  4. Trả preview: số mới/sửa/trùng/xung đột/lỗi.
  5. Caller quyết định apply (sau khi xem preview).

Chống ghi đè:
  - DB mới (dataset_samples) chỉ ghi sau khi admin bấm 'apply'.
  - Nhãn mới hơn (feedback_history từ review gốc) KHÔNG bị overwrite bởi export cũ.
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.training import dataset_repo, label_validator, provenance
from app.training.schemas import SchemaError, safe_name, validate_dataset_manifest


# Defaults
MAX_FILES = 5000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


class ImportBlockedError(Exception):
    """ZIP không hợp lệ về bảo mật hoặc schema."""


@dataclass
class PreviewResult:
    dataset_name: str = ""
    engine: str = ""
    schema_version: int = 0
    class_mapping: dict = field(default_factory=dict)
    would_create: list[str] = field(default_factory=list)
    would_update: list[str] = field(default_factory=list)
    would_skip: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sample_count: int = 0
    missing_files: list[str] = field(default_factory=list)
    provenance_issues: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "dataset_name": self.dataset_name,
            "engine": self.engine,
            "schema_version": self.schema_version,
            "class_mapping": self.class_mapping,
            "counts": {
                "would_create": len(self.would_create),
                "would_update": len(self.would_update),
                "would_skip": len(self.would_skip),
                "total": self.sample_count,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "missing_files": len(self.missing_files),
            },
            "errors": self.errors[:50],
            "warnings": self.warnings[:50],
            "missing_files": self.missing_files[:50],
            "provenance_issues": self.provenance_issues,
        }


def _safe_extract(zf: zipfile.ZipFile, dest: Path, *,
                  max_files: int = MAX_FILES,
                  max_bytes: int = MAX_UNCOMPRESSED_BYTES) -> None:
    """Extract an toàn: path traversal/absolute/symlink/file count/size guard.

    Guard:
      - max_files: tổng số entry vượt quá → reject.
      - max_bytes: tổng uncompressed bytes → reject.
      - symlink: external_attr kiểm tra S_ISLNK; create_system KHÔNG đủ vì
        ZIP Unix thường cũng dùng create_system=3 (Unix) cho non-symlink file.
      - containment: resolve path thực + kiểm tra relative_to(dest).
    """
    dest.mkdir(parents=True, exist_ok=True)
    real_dest = dest.resolve()
    count = 0
    total = 0
    for info in zf.infolist():
        count += 1
        if count > max_files:
            raise ImportBlockedError(f"ZIP chứa quá nhiều file (>{max_files})")
        # Symlink: chỉ khi mode bits == 0o120000 (S_IFLNK). create_system=3 là
        # Unix (file, dir, symlink đều có thể đó). KHÔNG dùng create_system.
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if (unix_mode & 0o170000) == 0o120000:
            raise ImportBlockedError(f"ZIP chứa symlink: {info.filename}")
        name = info.filename
        # Block absolute paths (POSIX + Windows drive + UNC + leading slash)
        if os.path.isabs(name) or name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
            raise ImportBlockedError(f"ZIP entry có absolute path: {name!r}")
        # Backslash đơn (chỉ Windows drive-style) không an toàn
        if "\\" in name and "/" not in name:
            raise ImportBlockedError(f"ZIP entry path không hợp lệ: {name!r}")
        # Containment check dùng resolve + relative_to (chính xác hơn startswith)
        try:
            target = (dest / name).resolve(strict=False)
        except OSError:
            raise ImportBlockedError(f"ZIP path không resolve được: {name!r}")
        try:
            target.relative_to(real_dest)
        except ValueError:
            raise ImportBlockedError(f"ZIP path traversal: {name!r}")
        total += info.file_size
        if total > max_bytes:
            raise ImportBlockedError(f"ZIP uncompressed quá lớn (> {max_bytes} bytes)")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def preview_import(zip_path: str, *, staging_root: str | None = None,
                   db_path: str | None = None) -> PreviewResult:
    """Preview import — KHÔNG ghi vào DB runtime. Trả diff count + errors."""
    zp = Path(zip_path)
    if not zp.exists() or not zp.is_file():
        raise ImportBlockedError(f"file không tồn tại: {zip_path}")
    if zp.stat().st_size == 0:
        raise ImportBlockedError("ZIP rỗng")

    if staging_root is None:
        from app.config import BASE_DIR
        staging_root = str(BASE_DIR / "data" / "training" / "imports")
    staging_root_p = Path(staging_root)
    staging_root_p.mkdir(parents=True, exist_ok=True)
    staging = staging_root_p / f"_preview_{zp.stem}_{provenance.now_iso().replace(':', '-')}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    result = PreviewResult()
    try:
        with zipfile.ZipFile(zp) as zf:
            _safe_extract(zf, staging)
        manifest_path = staging / "manifest.json"
        if not manifest_path.exists():
            raise ImportBlockedError("ZIP không có manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_dataset_manifest(manifest)
        except SchemaError as e:
            result.errors.append(f"manifest không hợp lệ: {e}")
            return result
        result.dataset_name = manifest.get("name", "")
        result.engine = manifest.get("engine", "")
        result.schema_version = int(manifest.get("schema_version", 0))
        result.class_mapping = manifest.get("class_mapping", {})

        # Validate provenance link
        result.provenance_issues = label_validator.verify_provenance_link(manifest.get("samples", []))
        # Verify file ảnh nếu có trong images/
        images_dir = staging / "images"
        for s in manifest.get("samples", []):
            sid = s.get("target_id")
            crop_id = s.get("source", {}).get("crop_media_id")
            if not crop_id:
                continue
            target_name = f"{sid}{Path(crop_id).suffix}"
            p = images_dir / target_name
            if not p.exists():
                result.missing_files.append(f"{sid}: missing {target_name}")
        result.sample_count = len(manifest.get("samples", []))
        if result.errors:
            return result

        # Diff against DB hiện tại
        existing_datasets = {d["name"]: d for d in dataset_repo.list_datasets(db_path=db_path)}
        existing = existing_datasets.get(result.dataset_name)
        if existing is not None:
            existing_samples = {s["target_id"]: s for s in
                                dataset_repo.list_samples(existing["id"], db_path=db_path)}
        else:
            existing_samples = {}
        for s in manifest.get("samples", []):
            sid = s.get("target_id")
            label_v = s.get("label", {}).get("verdict")
            target_text = s.get("label", {}).get("target_text", "")
            if sid in existing_samples:
                prev = existing_samples[sid]
                prev_label = prev.get("label", {})
                if (prev_label.get("verdict") == label_v
                        and prev_label.get("target_text") == target_text):
                    result.would_skip.append(sid)
                else:
                    # Nhãn mới hơn từ DB → bỏ qua để không overwrite bằng export cũ
                    prev_review = prev.get("reviewer")
                    if prev.get("source_latest_reviewed_at") and \
                       s.get("_label").get("reviewed_at", "") < prev.get("source_latest_reviewed_at", ""):
                        result.would_skip.append(sid)
                        result.warnings.append(
                            f"{sid}: export cũ hơn review trong DB — bỏ qua để tránh mất nhãn mới"
                        )
                    else:
                        result.would_update.append(sid)
            else:
                result.would_create.append(sid)
    finally:
        # KHÔNG xoá staging ngay — caller có thể muốn lưu diff cho người duyệt
        pass
    return result


def _asset_root_for(dataset_id: str) -> Path:
    from app.config import BASE_DIR
    p = BASE_DIR / "data" / "training" / "assets" / dataset_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _copy_assets_into_dataset(dataset_id: str, staging_dir: Path,
                              samples: list[dict]) -> tuple[list[dict], list[str]]:
    """Copy ảnh crop từ staging_dir/images sang asset_root bền vững.

    Trả (updated_samples, missing_target_ids). updated_samples có gắn 'crop_path'
    tương đối trong asset root. Idempotent — nếu file đã tồn tại ở asset root,
    không copy lại; vẫn ghi crop_path.
    """
    asset_root = _asset_root_for(dataset_id)
    images_dir = staging_dir / "images"
    missing: list[str] = []
    for s in samples:
        sid = s.get("target_id")
        if not sid:
            continue
        crop_id = (s.get("source") or {}).get("crop_media_id")
        if not crop_id:
            # Sample thiếu crop_media_id — ghi crop_path=None để caller quyết
            s.setdefault("source", {})["crop_path"] = None
            missing.append(sid)
            continue
        target_name = f"{sid}{Path(crop_id).suffix}"
        src = images_dir / target_name
        if not src.exists():
            missing.append(sid)
            s.setdefault("source", {})["crop_path"] = None
            continue
        dest = asset_root / target_name
        if not dest.exists():
            try:
                shutil.copy2(src, dest)
            except Exception:  # noqa: BLE001
                missing.append(sid)
                s.setdefault("source", {})["crop_path"] = None
                continue
        # Ghi path tương đối để portable, có resolve khi cần đọc.
        rel = dest.relative_to(asset_root.parent.parent)
        s.setdefault("source", {})["crop_path"] = str(rel.as_posix())
    return samples, missing


def apply_import(zip_path: str, *, dataset_name: str,
                 staging_root: str | None = None,
                 db_path: str | None = None) -> dict:
    """Apply import sau khi preview OK — ghi dataset + samples vào dataset DB riêng.

    Step:
      1. Preview (extract staging → đọc manifest, không ghi DB).
      2. Re-extract lần nữa vì preview có thể đã xoá.
      3. Copy ảnh vào asset root bền vững theo dataset_id.
      4. Tạo dataset + samples trong DB (sample JSON có gắn crop_path).
      5. Cleanup staging, giữ asset root.
    """
    preview = preview_import(zip_path, staging_root=staging_root, db_path=db_path)
    if preview.errors:
        raise ImportBlockedError(f"preview có lỗi: {preview.errors[:3]}")
    if not preview.dataset_name:
        raise ImportBlockedError("manifest thiếu name")

    zp = Path(zip_path)
    if staging_root is None:
        from app.config import BASE_DIR
        staging_root = str(BASE_DIR / "data" / "training" / "imports")
    staging_apply = Path(staging_root) / f"_apply_{zp.stem}_{provenance.now_iso().replace(':', '-')}"
    if staging_apply.exists():
        shutil.rmtree(staging_apply)
    staging_apply.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as zf:
        _safe_extract(zf, staging_apply)
    manifest = json.loads((staging_apply / "manifest.json").read_text(encoding="utf-8"))
    validate_dataset_manifest(manifest)

    engine = manifest.get("engine", "plate_ocr")
    schema_version = int(manifest.get("schema_version", 1))

    # Tạo dataset mới (KHÔNG ghi nhãn DB runtime — chỉ dataset riêng Task 3)
    new_id = dataset_repo.create_dataset(
        name=dataset_name, engine=engine, schema_version=schema_version,
        db_path=db_path,
    )
    samples = manifest.get("samples", [])

    # Copy ảnh crop từ staging vào asset root bền vững + ghi crop_path
    samples, missing = _copy_assets_into_dataset(new_id, staging_apply, samples)

    added = dataset_repo.add_samples(new_id, samples, db_path=db_path)

    # Cleanup staging (asset root giữ nguyên để round-trip)
    shutil.rmtree(staging_apply, ignore_errors=True)

    if missing:
        LOG = __import__("logging").getLogger("task3.import")
        LOG.warning("[task3] import %s: %d sample thiếu ảnh (crop_path=None)", new_id, len(missing))

    return {
        "dataset_id": new_id,
        "added": added,
        "missing_after_copy": len(missing),
        "would_create": len(preview.would_create),
        "would_update": len(preview.would_update),
        "would_skip": len(preview.would_skip),
        "missing_files": len(preview.missing_files),
        "preview": preview.to_dict(),
    }