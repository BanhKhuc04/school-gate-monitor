"""CLI: validate dataset (schema + leakage + provenance).

Usage:
    python -m scripts.training.validate_dataset --dataset-id dsv_xxx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Validate dataset schema/leakage/provenance")
    p.add_argument("--dataset-id", required=True)
    args = p.parse_args()

    from app.training import dataset_repo, label_validator, splits

    meta = dataset_repo.get_dataset(args.dataset_id)
    if meta is None:
        print(f"[validate] dataset_id {args.dataset_id} không tồn tại")
        return 1
    samples = dataset_repo.list_samples(args.dataset_id)
    print(f"[validate] dataset_id={args.dataset_id} engine={meta['engine']} samples={len(samples)}")

    # Provenance
    findings = label_validator.verify_provenance_link(samples)
    print("[validate] provenance:", findings)

    # Leakage (nếu đã split)
    leakage = splits.check_leakage(samples)
    print("[validate] leakage:", leakage)

    # Stats
    stats = splits.dataset_stats(samples)
    print("[validate] stats:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())