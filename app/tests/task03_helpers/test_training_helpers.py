"""Tests cho Task 3 — provenance + schemas + splits + label_validator.

Tập trung vào deterministic helper, không cần DB runtime, không cần CV libs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_sample_id_deterministic():
    from app.training import provenance
    sid1 = provenance.make_sample_id(review_id="rev_abc", frame_seq=10, crop_sha256="abcd")
    sid2 = provenance.make_sample_id(review_id="rev_abc", frame_seq=10, crop_sha256="abcd")
    sid3 = provenance.make_sample_id(review_id="rev_abc", frame_seq=11, crop_sha256="abcd")
    assert sid1 == sid2
    assert sid1 != sid3
    assert sid1.startswith("smp_")
    # Format: smp_<24hex>
    assert len(sid1.split("_")[1]) == 24


def test_dataset_version_id_format():
    from app.training import provenance
    from datetime import datetime, timezone
    dvid = provenance.make_dataset_version_id(
        base="plate_ocr", ts=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
    )
    assert dvid.startswith("dsv_plate_ocr_20261002_")


def test_normalize_plate_text():
    from app.training import provenance
    assert provenance.normalize_plate_text("89F1 237 92") == "89F123792"
    assert provenance.normalize_plate_text("89f1.237,92") == "89F123792"
    assert provenance.normalize_plate_text("") == ""
    assert provenance.normalize_plate_text("###") == ""


def test_validate_target_text_correct_requires_4_12_chars():
    from app.training.schemas import validate_target_text, SchemaError
    assert validate_target_text("89F123792", verdict="correct") == "89F123792"
    with pytest.raises(SchemaError):
        validate_target_text("AB", verdict="correct")
    with pytest.raises(SchemaError):
        validate_target_text("X" * 20, verdict="correct")


def test_validate_target_text_unreadable_must_be_empty():
    from app.training.schemas import validate_target_text, SchemaError
    assert validate_target_text("", verdict="unreadable") == ""
    with pytest.raises(SchemaError):
        validate_target_text("89F123", verdict="unreadable")


def test_validate_bbox_normalized():
    from app.training.schemas import validate_bbox, SchemaError
    validate_bbox([0.1, 0.2, 0.5, 0.6])
    with pytest.raises(SchemaError):
        validate_bbox([0.5, 0.5, 0.4, 0.6])  # x1 >= x2
    with pytest.raises(SchemaError):
        validate_bbox([-0.1, 0.1, 0.5, 0.5])  # ngoài [0,1]
    with pytest.raises(SchemaError):
        validate_bbox([0.0, 0.0, 0.001, 0.001])  # quá nhỏ


def test_validate_sample_minimal():
    from app.training.schemas import validate_sample, SchemaError
    sample = {
        "review_id": "rev_1",
        "target_id": "smp_x",
        "gate_id": "main",
        "label": {"verdict": "correct", "target_text": "89F123792"},
        "source": {"gate_id": "main", "camera_id": "main-front", "frame_seq": 1,
                   "source_epoch": 0, "crop_sha256": "abc", "crop_media_id": "abc.jpg",
                   "image_w": 200, "image_h": 100},
    }
    out = validate_sample(sample, schema_version=1)
    assert out["label"]["target_text"] == "89F123792"


def test_validate_sample_unknown_verdict():
    from app.training.schemas import validate_sample, SchemaError
    sample = {
        "review_id": "rev_1",
        "target_id": "smp_x",
        "gate_id": "main",
        "label": {"verdict": "wrong", "target_text": "89F123792"},
        "source": {"gate_id": "main"},
    }
    with pytest.raises(SchemaError):
        validate_sample(sample, schema_version=1)


def test_safe_name():
    from app.training.schemas import safe_name, SchemaError
    assert safe_name("ocr_v1") == "ocr_v1"
    with pytest.raises(SchemaError):
        safe_name("../bad")


def test_split_by_group_distributes_by_group():
    from app.training.splits import split_by_group
    samples = []
    for g in range(20):
        for i in range(5):
            samples.append({
                "review_id": f"rev_{g}_{i}",
                "source": {"gate_id": "main", "run_id": f"run_{g}"},
                "label": {"verdict": "correct", "target_text": "89F123792"},
            })
    out = split_by_group(samples, seed=42)
    total = sum(len(v) for v in out.values())
    assert total == 100
    # Không group nào xuất hiện ở 2 split
    by_group: dict[str, set[str]] = {}
    for split_name, items in out.items():
        for s in items:
            gk = s["source"]["run_id"]
            by_group.setdefault(gk, set()).add(split_name)
    for gk, splits_seen in by_group.items():
        assert len(splits_seen) == 1


def test_check_leakage_finds_duplicate_target_text():
    from app.training.splits import split_by_group, check_leakage
    samples = []
    for g in range(20):
        for i in range(5):
            samples.append({
                "review_id": f"rev_{g}_{i}",
                "encounter_id": f"enc_{g}",
                "source": {"gate_id": "main", "run_id": f"run_{g}",
                           "crop_sha256": f"hash_{g}_{i}"},
                "label": {"verdict": "correct", "target_text": "89F123792"},
            })
    out = split_by_group(samples, seed=42)
    all_samples = [s for items in out.values() for s in items]
    findings = check_leakage(all_samples)
    assert findings["duplicate_target_text"]  # cùng target_text ở train vs test


def test_dataset_stats_counts():
    from app.training.splits import dataset_stats
    samples = [
        {"label": {"verdict": "correct", "target_text": "89F123792"}, "split": "train"},
        {"label": {"verdict": "incorrect", "target_text": "59F100000"}, "split": "test"},
        {"label": {"verdict": "unreadable", "target_text": ""}, "split": "train"},
    ]
    s = dataset_stats(samples)
    assert s["total"] == 3
    assert s["by_split"] == {"train": 2, "test": 1}
    assert s["by_verdict"]["correct"] == 1


def test_augmentation_no_label_change():
    from app.training.augmentation import jitter_quality, validate_no_fake_target
    import random
    sample = {
        "target_id": "smp_1", "split": "train",
        "label": {"verdict": "correct", "target_text": "89F123792"},
    }
    out = jitter_quality(sample, rng=random.Random(0))
    assert out[0] is sample  # bản gốc giữ nguyên
    for aug in out[1:]:
        assert aug["is_augmented"] is True
        # Label không đổi
        assert aug["label"]["target_text"] == "89F123792"
        # Provenance link
        validate_no_fake_target(aug)


def test_augmentation_skip_val_test():
    from app.training.augmentation import jitter_quality
    sample = {"target_id": "smp_1", "split": "test",
              "label": {"verdict": "correct", "target_text": "89F123792"}}
    out = jitter_quality(sample)
    assert len(out) == 1
    assert "is_augmented" not in out[0]


def test_label_validator_sha256_file(tmp_path):
    from app.training.label_validator import sha256_file
    p = tmp_path / "x.txt"
    p.write_bytes(b"hello")
    assert sha256_file(p) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"