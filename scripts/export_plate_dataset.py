"""Export reviewed plate recognition data to a dataset manifest.

Pulls every `recognition_review` with status='confirmed' (correct verdict) or
'rejected' (incorrect verdict + corrected_text). The manifest is grouped by
encounter and preserves full provenance (camera, gate, run, epoch, frame,
crop hash, model hash) so downstream training runs can split by encounter
(not by individual feedback row) to avoid leakage.

This script never reads models, cameras, or the live DB except for the
configured DB_PATH. Output is a JSON manifest under data/datasets/plate_export_<ts>/.

Usage (from repo root):
    .\\venv\\Scripts\\python.exe scripts/export_plate_dataset.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export plate review feedback to dataset manifest")
    parser.add_argument("--output", help="Output directory (default: data/datasets/plate_export_<ts>)")
    parser.add_argument("--gate", help="Optional filter: only this gate")
    parser.add_argument("--include-unreadable", action="store_true",
                        help="Include unreadable/not_plate verdicts as negative samples")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else (
        ROOT / "data" / "datasets" / f"plate_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure schema is initialised (idempotent). This handles the case where the
    # script is run against a freshly-created test DB (the export runs as a
    # subprocess and only sees whatever DB_PATH points to; no implicit migration).
    db.init_db()

    # Pull all confirmed + rejected feedback. The DB API already paginates;
    # export is a one-shot script, so we walk pages in memory.
    rows = []
    offset = 0
    page_size = 100
    while True:
        page = db.list_recognition_reviews(limit=page_size, offset=offset,
                                            gate_id=args.gate, status="confirmed")
        rows.extend(page.get("items", []))
        if len(page.get("items", [])) < page_size:
            break
        offset += page_size
    offset = 0
    while True:
        page = db.list_recognition_reviews(limit=page_size, offset=offset,
                                            gate_id=args.gate, status="rejected")
        rows.extend(page.get("items", []))
        if len(page.get("items", [])) < page_size:
            break
        offset += page_size

    # Group feedback per review_id; each review may have multiple historical entries.
    # We keep the latest verdict for the label (most-recent human decision wins).
    by_review: dict[str, dict] = {}
    for review in rows:
        rid = review["review_id"]
        latest = db.get_recognition_review(rid)
        if not latest:
            continue
        feedbacks = latest.get("feedback", [])
        if not feedbacks:
            continue
        latest_fb = feedbacks[-1]
        if latest_fb["verdict"] in {"unreadable", "not_plate"} and not args.include_unreadable:
            continue
        # corrected_text may be None for unreadable/not_plate — keep label only.
        by_review[rid] = {
            "review_id": rid,
            "encounter_id": latest["encounter_id"],
            "gate_id": latest["gate_id"],
            "camera_id": latest["camera_id"],
            "run_id": latest["run_id"],
            "source_epoch": latest["source_epoch"],
            "frame_seq": latest["frame_seq"],
            "observed_at": latest["observed_at"],
            "crop_media_id": latest["crop_media_id"],
            "crop_sha256": latest["crop_sha256"],
            "proposal_raw": latest["proposal_raw"],
            "proposal_canonical": latest["proposal_canonical"],
            "proposal_top_line": latest["proposal_top_line"],
            "proposal_bottom_line": latest["proposal_bottom_line"],
            "proposal_confidence": latest["proposal_confidence"],
            "proposal_engine": latest["proposal_engine"],
            "proposal_model_hash": latest["proposal_model_hash"],
            "quality_score": latest["quality_score"],
            "blur_score": latest["blur_score"],
            "contrast_score": latest["contrast_score"],
            "label": {
                "verdict": latest_fb["verdict"],
                "corrected_text": latest_fb["corrected_text"],
                "reviewer": latest_fb["reviewer_username"],
                "reviewed_at": latest_fb["created_at"],
                "history_count": len(feedbacks),
            },
        }

    # Provenance-level split recommendation: group by encounter_id (or
    # run_id+gate_id fallback) so 70/15/15 split avoids leakage from the
    # same encounter appearing in both train and test.
    groups: dict[str, list[str]] = {}
    for rid, item in by_review.items():
        key = item.get("encounter_id") or f"{item['gate_id']}/{item['run_id']}"
        groups.setdefault(key, []).append(rid)

    manifest = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_reviews": len(by_review),
        "total_groups": len(groups),
        "include_unreadable": bool(args.include_unreadable),
        "gate_filter": args.gate,
        "items": list(by_review.values()),
        "group_split_recommendation": {
            "note": (
                "Split by encounter/run key, NOT by individual review_id, to "
                "prevent leakage between train and test. Use train_test_split "
                "on the keys, then expand items per split."
            ),
            "keys": sorted(groups.keys()),
        },
        "labels_legend": {
            "correct": "OCR was right — keep proposal as ground truth.",
            "incorrect": "OCR was wrong — use corrected_text as ground truth.",
            "unreadable": "Crop had no readable plate — negative sample only.",
            "not_plate": "Crop is not a plate (false detection).",
            "wrong_association": "Plate is right but assigned to wrong vehicle.",
        },
    }

    out_path = output_dir / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"[export] wrote {len(by_review)} reviews ({len(groups)} groups) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
