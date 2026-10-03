"""Schema cho dataset/sample/label/job/candidate — chuẩn JSON để truyền qua API/CLI.

Mỗi schema chỉ là typed dict + validator helper. KHÔNG phụ thuộc FastAPI/Pydantic
để giữ layer adapter gọn; chỉ cần validator trả lỗi rõ ràng khi nhập sai.

Lưu ý: KHÔNG dùng Pydantic để giảm coupling với Task 1/2; tự validate tránh phụ
thuộc vào app/schemas.py đang được task khác giữ.
"""
from __future__ import annotations

import re
from typing import Any

from app.training import provenance


VERDICT_LABELS = (
    "correct",
    "incorrect",
    "unreadable",
    "not_plate",
    "wrong_association",
)


SPLIT_NAMES = ("train", "val", "test")


class SchemaError(ValueError):
    """Lỗi schema — để caller xử lý (HTTP 400 cho API, exit code 1 cho CLI)."""


def require_keys(obj: dict, keys: list[str], path: str = "") -> None:
    for k in keys:
        if k not in obj:
            raise SchemaError(f"{path}.{k}" if path else f"missing key: {k}")


def expect_str(obj: dict, key: str, *, max_len: int = 1024, path: str = "") -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        raise SchemaError(f"{path or key} phải là chuỗi (got {type(val).__name__})")
    if len(val) > max_len:
        raise SchemaError(f"{path or key} quá dài (>{max_len})")
    return val


def expect_int(obj: dict, key: str, *, min_val: int | None = None, max_val: int | None = None, path: str = "") -> int:
    val = obj.get(key)
    if not isinstance(val, int) or isinstance(val, bool):
        raise SchemaError(f"{path or key} phải là int (got {type(val).__name__})")
    if min_val is not None and val < min_val:
        raise SchemaError(f"{path or key} < {min_val}")
    if max_val is not None and val > max_val:
        raise SchemaError(f"{path or key} > {max_val}")
    return val


def expect_float(obj: dict, key: str, *, min_val: float | None = None, max_val: float | None = None, path: str = "") -> float:
    val = obj.get(key)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise SchemaError(f"{path or key} phải là số (got {type(val).__name__})")
    val = float(val)
    if min_val is not None and val < min_val:
        raise SchemaError(f"{path or key} < {min_val}")
    if max_val is not None and val > max_val:
        raise SchemaError(f"{path or key} > {max_val}")
    return val


def expect_one_of(obj: dict, key: str, allowed: tuple[str, ...], path: str = "") -> str:
    val = expect_str(obj, key, path=path)
    if val not in allowed:
        raise SchemaError(f"{path or key}={val!r} không thuộc {allowed!r}")
    return val


def validate_bbox(bbox: Any, *, image_w: int | None = None, image_h: int | None = None,
                  path: str = "bbox") -> list[float]:
    """Bbox list 4 số [x1,y1,x2,y2] normalized 0-1 (training detector). Trả về bbox gốc nếu hợp lệ."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise SchemaError(f"{path} phải là [x1,y1,x2,y2]")
    nums = []
    for i, v in enumerate(bbox):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise SchemaError(f"{path}[{i}] phải là số")
        nums.append(float(v))
    x1, y1, x2, y2 = nums
    if x1 < 0 or y1 < 0 or x2 > 1.0001 or y2 > 1.0001:
        raise SchemaError(f"{path} ngoài phạm vi [0,1]: {nums}")
    if x2 - x1 < 0.005 or y2 - y1 < 0.005:
        raise SchemaError(f"{path} quá nhỏ (<0.5% mỗi chiều): {nums}")
    if x1 >= x2 or y1 >= y2:
        raise SchemaError(f"{path} x1>=x2 hoặc y1>=y2: {nums}")
    if image_w is not None and image_h is not None:
        # Bbox normalized không phụ thuộc image_w/h — nhưng check tỉ lệ bảo vệ letterbox
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        if bbox_w * image_w < 4 or bbox_h * image_h < 4:
            raise SchemaError(f"{path} quá nhỏ so với ảnh {image_w}x{image_h}")
    return nums


def validate_target_text(target: str, *, verdict: str) -> str:
    """target_text hợp lệ tuỳ verdict:
    - correct/incorrect: chuỗi canonical biển 4-12 ký tự A-Z0-9.
    - unreadable/not_plate/wrong_association: chuỗi rỗng.
    """
    target = target or ""
    if verdict in {"correct", "incorrect"}:
        canon = provenance.normalize_plate_text(target)
        if not canon or len(canon) < 4 or len(canon) > 12:
            raise SchemaError(f"target_text={target!r} (canonical={canon!r}) không hợp lệ cho verdict={verdict}")
        return canon
    if verdict in {"unreadable", "not_plate", "wrong_association"}:
        if target.strip():
            raise SchemaError(f"target_text phải rỗng khi verdict={verdict}")
        return ""
    raise SchemaError(f"verdict={verdict!r} không thuộc {VERDICT_LABELS}")


def validate_sample(sample: dict, *, schema_version: int) -> dict:
    """Validate một sample record trong dataset (Task 3.4 schema).

    Required keys: review_id, target_id, gate_id, label {verdict, target_text},
    source {camera_id?, run_id?, observed_at?, frame_seq?, source_epoch?,
    crop_sha256?, crop_media_id?, image_w?, image_h?},
    bbox {x1,y1,x2,y2} (chỉ detector task — bỏ qua cho OCR),
    classes {is_hi?, is_no_hi?, is_unknown?} (chỉ helmet),
    split? {train|val|test}, holdout? bool.
    Trả về dict đã chuẩn hoá (canonical target_text, normalized).
    """
    if not isinstance(sample, dict):
        raise SchemaError("sample phải là dict")
    if schema_version != 1:
        raise SchemaError(f"schema_version={schema_version} không hỗ trợ")
    require_keys(sample, ["review_id", "gate_id", "label", "source"], "sample")
    expect_str(sample, "review_id", max_len=128)
    expect_str(sample, "gate_id", max_len=64)
    label = sample["label"]
    if not isinstance(label, dict):
        raise SchemaError("sample.label phải là dict")
    verdict = expect_one_of(label, "verdict", VERDICT_LABELS, "label")
    target_raw = label.get("target_text") or label.get("target") or ""
    target = validate_target_text(target_raw, verdict=verdict)
    sample["label"] = {
        **label,
        "verdict": verdict,
        "target_text": target,
    }
    src = sample["source"]
    if not isinstance(src, dict):
        raise SchemaError("sample.source phải là dict")
    expect_str(src, "gate_id", max_len=64, path="source")
    if "camera_id" in src and src["camera_id"] is not None:
        expect_str(src, "camera_id", max_len=64, path="source")
    if "run_id" in src and src["run_id"] is not None:
        expect_str(src, "run_id", max_len=128, path="source")
    if "observed_at" in src and src["observed_at"] is not None:
        expect_str(src, "observed_at", max_len=64, path="source")
    if "frame_seq" in src:
        expect_int(src, "frame_seq", min_val=0, max_val=10**8, path="source")
    if "source_epoch" in src:
        expect_int(src, "source_epoch", min_val=0, max_val=10**8, path="source")
    if "crop_sha256" in src and src["crop_sha256"] is not None:
        expect_str(src, "crop_sha256", max_len=128, path="source")
    if "crop_media_id" in src and src["crop_media_id"] is not None:
        expect_str(src, "crop_media_id", max_len=256, path="source")
    image_w = src.get("image_w")
    image_h = src.get("image_h")
    if image_w is not None:
        expect_int(src, "image_w", min_val=1, max_val=20000, path="source")
    if image_h is not None:
        expect_int(src, "image_h", min_val=1, max_val=20000, path="source")
    bbox = sample.get("bbox")
    if bbox is not None:
        validate_bbox(bbox, image_w=image_w, image_h=image_h, path="bbox")
    cls = sample.get("classes")
    if cls is not None:
        if not isinstance(cls, dict):
            raise SchemaError("sample.classes phải là dict")
        for k in ("is_hi", "is_no_hi", "is_unknown"):
            if k in cls:
                if not isinstance(cls[k], bool):
                    raise SchemaError(f"sample.classes.{k} phải là bool")
    if "split" in sample and sample["split"] is not None:
        expect_one_of(sample, "split", SPLIT_NAMES, path="split")
    if "holdout" in sample:
        if not isinstance(sample["holdout"], bool):
            raise SchemaError("sample.holdout phải là bool")
    return sample


def validate_dataset_manifest(manifest: dict) -> dict:
    """Validate top-level manifest (Task 3.3 export format)."""
    if not isinstance(manifest, dict):
        raise SchemaError("manifest phải là dict")
    schema_version = expect_int(manifest, "schema_version", min_val=1, max_val=99)
    require_keys(manifest, ["dataset_id", "samples", "class_mapping", "engine"], "manifest")
    expect_str(manifest, "dataset_id", max_len=128)
    expect_str(manifest, "engine", max_len=64)  # "plate_ocr" | "plate_detector" | "helmet"
    class_mapping = manifest["class_mapping"]
    if not isinstance(class_mapping, dict):
        raise SchemaError("manifest.class_mapping phải là dict")
    samples = manifest["samples"]
    if not isinstance(samples, list):
        raise SchemaError("manifest.samples phải là list")
    seen_target_ids = set()
    for i, sample in enumerate(samples):
        try:
            validate_sample(sample, schema_version=schema_version)
        except SchemaError as exc:
            raise SchemaError(f"samples[{i}]: {exc}") from exc
        target_id = sample.get("target_id")
        if not target_id:
            raise SchemaError(f"samples[{i}].target_id rỗng")
        if target_id in seen_target_ids:
            raise SchemaError(f"samples[{i}].target_id={target_id!r} trùng")
        seen_target_ids.add(target_id)
    return manifest


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def safe_name(name: str, *, label: str = "name") -> str:
    if not isinstance(name, str) or not _SAFE_NAME_RE.match(name):
        raise SchemaError(f"{label}={name!r} không phải [A-Za-z0-9_-]{{1,128}}")
    return name