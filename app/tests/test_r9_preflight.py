"""Selftest cho logic preflight/load/manifest helper được dùng trong 3 notebook R9.

Trích các hàm từ các cell notebook và chạy độc lập để đảm bảo cú pháp + logic
không bị lỗi khi gặp dataset fixture.

KHÔNG cần nbclient/nbconvert — chỉ test logic helper.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NB_DIR = ROOT / "notebooks"


def _cell_source(nb_name: str, cell_type: str, contains: str) -> str:
    """Trích source của 1 cell trong notebook chứa chuỗi `contains`."""
    nb = json.loads((NB_DIR / nb_name).read_text(encoding="utf-8"))
    for c in nb["cells"]:
        if c["cell_type"] != cell_type:
            continue
        if contains in "".join(c["source"]):
            return "".join(c["source"])
    raise KeyError(f"không tìm thấy {cell_type} cell chứa '{contains}' trong {nb_name}")


# ------------------------------------------------------------------
# Test preflight logic — trích cell chứa def preflight
# ------------------------------------------------------------------

def test_preflight_function_compiles():
    """Def preflight trong từng notebook compile được."""
    for nb in ("yolo11_plate.ipynb", "yolo11_helmet_electric.ipynb", "cct_plate_ocr.ipynb"):
        src = _cell_source(nb, "code", "def preflight")
        compile(src, f"{nb}#preflight", "exec")


def _make_manifest(audit_dir: Path, *, holdout="human_curated_group_disjoint",
                   counts=None, with_digest=True):
    """Tạo manifest.json + manifest.sha256 cho test preflight."""
    if counts is None:
        counts = {"train": 1, "val": 1, "test": 1}
    manifest = {
        "schema_version": 1,
        "kind": "detect",
        "holdout_status": holdout,
        "counts": counts,
        "source_manifest_sha256": "abc123",
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    if with_digest:
        digest = hashlib.sha256((audit_dir / "manifest.json").read_bytes()).hexdigest()
        (audit_dir / "manifest.sha256").write_text(digest, encoding="ascii")


def test_preflight_ok_with_valid_manifest(tmp_path):
    """Manifest hợp lệ → preflight trả ok=True."""
    audit_dir = tmp_path / "ds"
    _make_manifest(audit_dir, counts={"train": 5, "val": 2, "test": 1})
    # Thực thi hàm preflight từ cell
    src = _cell_source("yolo11_plate.ipynb", "code", "def preflight")
    ns: dict = {}
    exec(src, ns)
    preflight = ns["preflight"]
    result = preflight(str(audit_dir))
    assert result["ok"] is True
    assert "manifest" in result


def test_preflight_missing_manifest(tmp_path):
    """Thiếu manifest.json → ok=False, pending_data=True."""
    audit_dir = tmp_path / "ds"
    audit_dir.mkdir(parents=True, exist_ok=True)
    src = _cell_source("yolo11_plate.ipynb", "code", "def preflight")
    ns: dict = {}
    exec(src, ns)
    preflight = ns["preflight"]
    result = preflight(str(audit_dir))
    assert result["ok"] is False
    assert result["pending_data"] is True


def test_preflight_zero_count_split(tmp_path):
    """Split có count=0 → pending_data."""
    audit_dir = tmp_path / "ds"
    _make_manifest(audit_dir, counts={"train": 5, "val": 0, "test": 1})
    src = _cell_source("yolo11_plate.ipynb", "code", "def preflight")
    ns: dict = {}
    exec(src, ns)
    preflight = ns["preflight"]
    result = preflight(str(audit_dir))
    assert result["ok"] is False
    assert result["pending_data"] is True
    assert "count=0" in result["reason"]


def test_preflight_wrong_holdout_status(tmp_path):
    """holdout_status chưa human_curated → pending_data."""
    audit_dir = tmp_path / "ds"
    _make_manifest(audit_dir, holdout="pending_human_group_curation")
    src = _cell_source("yolo11_plate.ipynb", "code", "def preflight")
    ns: dict = {}
    exec(src, ns)
    preflight = ns["preflight"]
    result = preflight(str(audit_dir))
    assert result["ok"] is False
    assert result["pending_data"] is True


def test_preflight_hash_mismatch_raises(tmp_path):
    """Hash bị sửa → ValueError."""
    audit_dir = tmp_path / "ds"
    _make_manifest(audit_dir)
    # Sửa digest ghi trong file sha256
    (audit_dir / "manifest.sha256").write_text("0" * 64, encoding="ascii")
    src = _cell_source("yolo11_plate.ipynb", "code", "def preflight")
    ns: dict = {}
    exec(src, ns)
    preflight = ns["preflight"]
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        preflight(str(audit_dir))


# ------------------------------------------------------------------
# Test load helpers — verify các cell LOAD tham chiếu đúng manifest
# ------------------------------------------------------------------

def test_yolo_load_references_audit():
    """yolo load cell phải gọi preflight() và kiểm tra ok."""
    src = _cell_source("yolo11_plate.ipynb", "code", "PLATE_DATASET_SLUG")
    assert "preflight(audit_dir)" in src
    assert "data.yaml" in src
    assert "raise SystemExit" in src or "raise" in src


def test_cct_load_references_csv():
    """cct load cell phải kiểm tra train/val/test.csv."""
    src = _cell_source("cct_plate_ocr.ipynb", "code", "OCR_SLUG")
    # Cell có vòng lặp for split in ("train", "val", "test") + check f"{split}.csv"
    assert '"train"' in src and '"val"' in src and '"test"' in src
    assert ".csv" in src
    assert "preflight" in src


def test_helmet_load_separate_slugs():
    """helmet load cell phải dùng slug riêng cho helmet & EV."""
    src = _cell_source("yolo11_helmet_electric.ipynb", "code", "HELMET_DATASET_SLUG")
    assert "EV_DATASET_SLUG" in src
    assert "preflight" in src


# ------------------------------------------------------------------
# Test manifest hash helpers trong cell export
# ------------------------------------------------------------------

def test_export_writes_artifact_sha256(tmp_path):
    """Cell export yolo phải viết artifact_manifest.json + .sha256."""
    src = _cell_source("yolo11_plate.ipynb", "code", "artifact_manifest")
    assert "hashlib" in src
    assert ".sha256" in src
    assert "json" in src


def test_cct_export_writes_artifact_sha256():
    """Cell export cct phải viết artifact_plate_ocr.json + .sha256."""
    src = _cell_source("cct_plate_ocr.ipynb", "code", "artifact_plate_ocr")
    assert "hashlib" in src
    assert ".sha256" in src
    assert "plate_config.yaml" in src
    assert "onnx" in src.lower()