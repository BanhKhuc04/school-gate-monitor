"""CLI: xây dataset từ review API + freeze.

Usage:
    python -m scripts.training.build_dataset --name ocr_v1 --engine plate_ocr [--gate main] [--include-unreadable]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Build dataset từ recognition_reviews")
    p.add_argument("--name", required=True)
    p.add_argument("--engine", choices=["plate_ocr", "plate_detector", "helmet"],
                   default="plate_ocr")
    p.add_argument("--gate", default=None)
    p.add_argument("--include-unreadable", action="store_true")
    p.add_argument("--freeze", action="store_true",
                   help="Auto-freeze sau khi build xong")
    p.add_argument("--split-seed", type=int, default=42)
    args = p.parse_args()

    from app.training import dataset_repo, dataset_freeze, adapter, splits, provenance

    # Init training DB
    dataset_repo.init_db()

    # Pull từ review adapter
    reviews = adapter.list_reviewed_with_feedback(
        gate_id=args.gate, include_unreadable=args.include_unreadable,
    )
    if not reviews:
        print(f"[build_dataset] no reviews với gate={args.gate}, status=confirmed/rejected")
        return 1

    # Tạo dataset
    ds_id = dataset_repo.create_dataset(name=args.name, engine=args.engine)
    print(f"[build_dataset] dataset_id={ds_id} (draft)")

    # Build samples từ reviews
    samples = []
    seen_target_ids = set()
    for review in reviews:
        rid = review["review_id"]
        crop_sha = review.get("crop_sha256") or "no-crop-sha"
        sid = provenance.make_sample_id(
            review_id=rid, frame_seq=review.get("frame_seq"), crop_sha256=crop_sha,
        )
        if sid in seen_target_ids:
            continue
        seen_target_ids.add(sid)
        sample = {
            "target_id": sid,
            "review_id": rid,
            "encounter_id": review.get("encounter_id"),
            "gate_id": review["gate_id"],
            "label": review["label"],
            "source": {
                "gate_id": review["gate_id"],
                "camera_id": review.get("camera_id"),
                "run_id": review.get("run_id"),
                "source_epoch": review.get("source_epoch"),
                "frame_seq": review.get("frame_seq"),
                "observed_at": review.get("observed_at"),
                "crop_sha256": crop_sha,
                "crop_media_id": review.get("crop_media_id"),
            },
        }
        samples.append(sample)

    # Khi build plate_ocr, cần target_text — chỉ nhận verdict=correct/incorrect
    if args.engine == "plate_ocr":
        samples = [s for s in samples
                   if s["label"]["verdict"] in {"correct", "incorrect"}
                   and len(s["label"]["target_text"]) >= 4]
    elif args.engine == "plate_detector":
        # Plate detector cần bbox — không có trong review API → bỏ qua nếu thiếu
        samples = [s for s in samples
                   if s["label"]["verdict"] in {"correct", "incorrect", "not_plate", "wrong_association"}]

    added = dataset_repo.add_samples(ds_id, samples)
    print(f"[build_dataset] added {added} samples (total reviews={len(reviews)})")

    if args.split_seed:
        from app.training.splits import split_by_group
        out = split_by_group(samples, seed=args.split_seed)
        for split_name, items in out.items():
            for s in items:
                dataset_repo.set_sample_split(ds_id, s["target_id"], split_name)
        counts = {k: len(v) for k, v in out.items()}
        print(f"[build_dataset] split {counts}")

    if args.freeze:
        result = dataset_freeze.freeze(ds_id)
        print(f"[build_dataset] frozen: manifest={result['manifest_path']}, "
              f"samples={result['sample_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())