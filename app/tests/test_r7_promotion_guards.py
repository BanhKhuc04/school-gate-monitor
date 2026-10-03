"""R7 — Model import/evaluate/apply/rollback guards (Owner A).

Theo handoff §3 R7:
- Chốt contract artifact: weights/ONNX, config, mapping, hashes, package versions,
  dataset/holdout hash và metrics.
- API import admin kiểm kích thước, path/hash/mapping/load.
- Không load pickle/checkpoint từ nguồn tùy ý.
- Apply chỉ sau runtime xác nhận đúng model hash.
- Tách eligible/selected/pending_runtime/applied.

Test các guard trong `app/training/promotion.py`:
- _verify_artifact: file >= 100 bytes, hash tính được
- _verify_hash: SHA256 model_path phải khớp với claimed hash
- _verify_runtime_contract: engine → class mapping hợp lệ
- _verify_not_smoke: tên candidate chứa 'smoke' → block
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.training import promotion
from app.training.schemas import SchemaError


# ── helpers ────────────────────────────────────────────────────────────────


def _make_artifact(tmp_path, content: bytes = None, min_size: int = 200) -> Path:
    """Tạo file artifact giả với size tối thiểu."""
    if content is None:
        content = b"ARTIFACT_FAKE" * 50  # 650 bytes
    f = tmp_path / "model.bin"
    f.write_bytes(content)
    return f


def _make_candidate(model_path: Path = None, model_sha256: str = None,
                    engine: str = "plate_ocr", metrics_path: str = None,
                    class_mapping: dict = None, model_class: str = "EasyOCR_v1") -> dict:
    """Tạo dict candidate mẫu."""
    return {
        "id": "cand-001",
        "name": "TestCandidate",
        "engine": engine,
        "model_class": model_class,
        "model_path": str(model_path) if model_path else "/tmp/model.bin",
        "model_sha256": model_sha256 or "",
        "class_mapping": class_mapping or {"0": "license-plate"},
        "metrics_path": metrics_path or "/tmp/metrics.json",
    }


# ── 1. _verify_artifact: file missing → raise ──────────────────────────


def test_verify_artifact_rejects_missing_file(tmp_path, monkeypatch):
    """model_path không tồn tại → raise SchemaError."""
    cand = _make_candidate(model_path=tmp_path / "missing.bin")
    # Patch _load_artifact_with_timeout để skip load thật
    monkeypatch.setattr(promotion, "_load_artifact_with_timeout",
                        lambda *a, **kw: None)
    with pytest.raises(SchemaError, match="tồn tại|không"):
        promotion._verify_artifact(cand)


# ── 2. _verify_artifact: file too small → raise ───────────────────────


def test_verify_artifact_rejects_too_small_file(tmp_path, monkeypatch):
    """File < 100 bytes (placeholder) → raise SchemaError."""
    small = tmp_path / "small.bin"
    small.write_bytes(b"X")  # 1 byte
    cand = _make_candidate(model_path=small)
    monkeypatch.setattr(promotion, "_load_artifact_with_timeout",
                        lambda *a, **kw: None)
    with pytest.raises(SchemaError, match="100 byte|placeholder|too small|size"):
        promotion._verify_artifact(cand)


# ── 3. _verify_artifact: model_path missing in candidate ──────────────


def test_verify_artifact_rejects_missing_path_field(monkeypatch):
    """Candidate thiếu model_path → raise SchemaError."""
    cand = _make_candidate(model_path=None)
    monkeypatch.setattr(promotion, "_load_artifact_with_timeout",
                        lambda *a, **kw: None)
    with pytest.raises(SchemaError, match="model_path"):
        promotion._verify_artifact(cand)


# ── 4. _verify_hash: SHA256 mismatch → raise ────────────────────────────


def test_verify_hash_rejects_mismatch(tmp_path, monkeypatch):
    """Claimed hash khác SHA256 thực của file → raise SchemaError."""
    artifact = _make_artifact(tmp_path)
    cand = _make_candidate(model_path=artifact, model_sha256="0" * 64)
    # Mock metrics loading để tránh DB
    monkeypatch.setattr(promotion, "_verify_metrics_server_side",
                        lambda *a, **kw: {})
    with pytest.raises(SchemaError, match="hash|SHA256"):
        promotion._verify_hash(cand)


# ── 5. _verify_hash: SHA256 match → pass ───────────────────────────────


def test_verify_hash_accepts_matching_hash(tmp_path, monkeypatch):
    """Claimed hash đúng SHA256 thực → không raise."""
    artifact = _make_artifact(tmp_path)
    real_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    cand = _make_candidate(model_path=artifact, model_sha256=real_hash)
    monkeypatch.setattr(promotion, "_verify_metrics_server_side",
                        lambda *a, **kw: {})
    # Không raise
    promotion._verify_hash(cand)


# ── 6. _verify_runtime_contract: engine không hợp lệ ──────────────────


def test_verify_runtime_contract_rejects_unknown_engine():
    """engine='foo' không có trong _RUNTIME_CONTRACT → raise."""
    cand = _make_candidate(engine="foo", class_mapping={"0": "x"})
    with pytest.raises(SchemaError, match="engine|runtime"):
        promotion._verify_runtime_contract(cand)


# ── 7. _verify_runtime_contract: plate_ocr cần EasyOCR/CustomOCR ───────


def test_verify_runtime_contract_plate_ocr_blocks_unknown_class():
    """plate_ocr engine chỉ cho phép class bắt đầu bằng EasyOCR/CustomOCR."""
    cand = _make_candidate(
        engine="plate_ocr",
        model_class="RandomClass_xyz",
    )
    with pytest.raises(SchemaError, match="runtime|contract|class"):
        promotion._verify_runtime_contract(cand)


# ── 8. _verify_runtime_contract: class_mapping phải khớp engine ────────


def test_verify_runtime_contract_accepts_compatible_class():
    """plate_ocr + class 'EasyOCR_v1' → OK."""
    cand = _make_candidate(
        engine="plate_ocr",
        model_class="EasyOCR_v1",
    )
    # Không raise
    promotion._verify_runtime_contract(cand)


# ── 9. _verify_not_smoke: tên chứa 'smoke' → block ────────────────────


def test_verify_not_smoke_blocks_smoke_in_model_class():
    """model_class chứa 'smoke' → raise SchemaError (R7 chống fake metric)."""
    metrics = {"name": "real_eval_v1", "exact_accuracy": 0.95}
    cand = _make_candidate(model_class="YOLO_smoke_test")
    with pytest.raises(SchemaError, match="smoke"):
        promotion._verify_not_smoke(metrics, cand)


def test_verify_not_smoke_blocks_simulate_in_model_class():
    """model_class chứa 'simulate' → raise SchemaError."""
    metrics = {"name": "real_eval_v1", "exact_accuracy": 0.95}
    cand = _make_candidate(model_class="EasyOCR_simulate_v1")
    with pytest.raises(SchemaError, match="smoke|simulate"):
        promotion._verify_not_smoke(metrics, cand)


def test_verify_not_smoke_allows_clean_model_class():
    """model_class clean → không raise."""
    metrics = {"name": "real_eval_v1", "exact_accuracy": 0.95}
    cand = _make_candidate(model_class="YOLO_v11_clean")
    # Không raise
    promotion._verify_not_smoke(metrics, cand)


def test_verify_not_smoke_blocks_lifecycle_simulation_note():
    """metrics['note'] chứa 'lifecycle_simulation' → raise."""
    metrics = {"name": "eval_v1", "note": "lifecycle_simulation result"}
    cand = _make_candidate()
    with pytest.raises(SchemaError, match="lifecycle_simulation"):
        promotion._verify_not_smoke(metrics, cand)


# ── 10. _verify_runtime_contract: helmet engine → YOLO/Ultralytics ────


def test_verify_runtime_contract_helmet_accepts_yolo():
    """helmet + class 'YOLO_v11' → OK (YOLO prefix match)."""
    cand = _make_candidate(
        engine="helmet",
        model_class="YOLO_v11",
    )
    promotion._verify_runtime_contract(cand)


def test_verify_runtime_contract_helmet_blocks_pickle():
    """helmet + class 'pickle' → block (không cho phép pickle thô)."""
    cand = _make_candidate(
        engine="helmet",
        model_class="pickle_v1",
    )
    with pytest.raises(SchemaError):
        promotion._verify_runtime_contract(cand)


# ── 11. RUNTIME_CONTRACT keys whitelist ────────────────────────────────


def test_runtime_contract_has_expected_engines():
    """Contract phải có ít nhất plate_ocr/plate_detector/helmet."""
    assert "plate_ocr" in promotion._RUNTIME_CONTRACT
    assert "plate_detector" in promotion._RUNTIME_CONTRACT
    assert "helmet" in promotion._RUNTIME_CONTRACT
    # Mỗi engine phải có ít nhất 1 class prefix cho phép
    for engine, prefixes in promotion._RUNTIME_CONTRACT.items():
        assert len(prefixes) > 0, f"{engine} có prefix list rỗng"


# ── 12. SchemaError là SchemaError (không phải generic Exception) ─────


def test_verify_artifact_raises_schema_error():
    """Đảm bảo contract error raise SchemaError (không bị nuốt)."""
    from app.training.schemas import SchemaError
    cand = _make_candidate(model_path=None)
    # model_path None raise SchemaError, không phải ValueError/Exception chung
    with pytest.raises(SchemaError):
        try:
            promotion._verify_artifact(cand)
        except SchemaError:
            raise
        except Exception as e:
            pytest.fail(f"Expected SchemaError, got {type(e).__name__}: {e}")
