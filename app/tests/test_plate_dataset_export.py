"""Tests for scripts/export_plate_dataset.py — manifest shape & leakage-safe split."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


def _seed_review(db, *, gate="main", camera="main-front", encounter="enc-1",
                 proposal_canonical="89F123792"):
    review_id = uuid.uuid4().hex
    db.create_recognition_review(
        review_id=review_id,
        violation_id=None,
        encounter_id=encounter,
        gate_id=gate,
        camera_id=camera,
        run_id="run-test",
        source_epoch=0,
        frame_seq=42,
        observed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        crop_media_id=None,
        crop_sha256=None,
        proposal_raw="89F1 237.92",
        proposal_canonical=proposal_canonical,
        proposal_top_line="89F1",
        proposal_bottom_line="23792",
        proposal_confidence=0.61,
        proposal_engine="easyocr",
    )
    return review_id


def test_export_writes_manifest_with_correct_shape(test_app, tmp_path):
    """Run the export script against the test DB and verify the manifest."""
    from app import db

    # Seed: 2 reviews, both confirmed (correct).
    rid_a = _seed_review(db, encounter="enc-A")
    rid_b = _seed_review(db, encounter="enc-A")  # same encounter — must group together
    db.record_review_feedback(
        review_id=rid_a, reviewer_username="admin", reviewer_role="admin",
        verdict="correct", expected_version=0,
    )
    db.record_review_feedback(
        review_id=rid_b, reviewer_username="admin", reviewer_role="admin",
        verdict="correct", expected_version=0,
    )

    # Run script pointing at the test DB (env override so the script picks up our schema).
    out_dir = tmp_path / "ds1"
    import app.db as _db
    # Use APP_DB_PATH (overrides config default for subprocess isolation) — DB_PATH
    # is captured at module-import time of app.config.
    env = {**__import__("os").environ, "APP_DB_PATH": _db.DB_PATH}
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_plate_dataset.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(out_dir)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["exported_at"]
    assert manifest["total_reviews"] >= 2
    assert manifest["total_groups"] >= 1
    # Both reviews belong to encounter 'enc-A' → must be in same group key.
    enc_keys = manifest["group_split_recommendation"]["keys"]
    assert any(k == "enc-A" for k in enc_keys), f"enc-A missing from {enc_keys}"

    # Each item preserves provenance for leakage-safe splits.
    for item in manifest["items"]:
        assert "review_id" in item
        assert "gate_id" in item
        assert "camera_id" in item
        assert "run_id" in item
        assert "source_epoch" in item
        assert "label" in item
        assert item["label"]["verdict"] in {"correct", "incorrect", "unreadable",
                                            "not_plate", "wrong_association"}


def test_export_excludes_unreadable_by_default(test_app, tmp_path):
    from app import db
    rid_a = _seed_review(db)
    rid_b = _seed_review(db, proposal_canonical="OTHER123")
    db.record_review_feedback(
        review_id=rid_a, reviewer_username="admin", reviewer_role="admin",
        verdict="correct", expected_version=0,
    )
    db.record_review_feedback(
        review_id=rid_b, reviewer_username="admin", reviewer_role="admin",
        verdict="unreadable", expected_version=0,
    )

    out_dir = tmp_path / "ds2"
    import app.db as _db
    env = {**__import__("os").environ, "APP_DB_PATH": _db.DB_PATH}
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_plate_dataset.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(out_dir)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    verdicts = [it["label"]["verdict"] for it in manifest["items"]]
    assert "correct" in verdicts
    assert "unreadable" not in verdicts, "default export must skip unreadable"


def test_export_include_unreadable_flag(test_app, tmp_path):
    from app import db
    rid = _seed_review(db)
    db.record_review_feedback(
        review_id=rid, reviewer_username="admin", reviewer_role="admin",
        verdict="unreadable", expected_version=0,
    )

    out_dir = tmp_path / "ds3"
    import app.db as _db
    env = {**__import__("os").environ, "APP_DB_PATH": _db.DB_PATH}
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_plate_dataset.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(out_dir),
         "--include-unreadable"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["include_unreadable"] is True
    assert any(it["label"]["verdict"] == "unreadable" for it in manifest["items"])


def test_manifest_split_groups_by_encounter(test_app, tmp_path):
    """Reviews from same encounter must share a group key."""
    from app import db
    rid_a = _seed_review(db, encounter="enc-shared")
    rid_b = _seed_review(db, encounter="enc-shared")
    rid_c = _seed_review(db, encounter="enc-other")
    for r in [rid_a, rid_b, rid_c]:
        db.record_review_feedback(
            review_id=r, reviewer_username="admin", reviewer_role="admin",
            verdict="correct", expected_version=0,
        )
    out_dir = tmp_path / "ds4"
    import app.db as _db
    env = {**__import__("os").environ, "APP_DB_PATH": _db.DB_PATH}
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_plate_dataset.py"
    subprocess.run([sys.executable, str(script), "--output", str(out_dir)],
                    env=env, capture_output=True, text=True, timeout=30)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    keys = set(manifest["group_split_recommendation"]["keys"])
    assert "enc-shared" in keys
    assert "enc-other" in keys
    # Items for the same encounter MUST appear once per encounter-key group.
    by_key = {}
    for item in manifest["items"]:
        key = item.get("encounter_id")
        by_key.setdefault(key, []).append(item["review_id"])
    assert len(by_key["enc-shared"]) == 2
    assert len(by_key["enc-other"]) == 1
