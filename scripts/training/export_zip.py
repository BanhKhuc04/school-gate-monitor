"""CLI: export dataset (đã freeze) ra ZIP portable.

Usage:
    python -m scripts.training.export_zip --dataset-id dsv_xxx --output /path/out.zip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Export frozen dataset → ZIP portable")
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--output", default=None)
    args = p.parse_args()

    from app.training import export_portable
    out = export_portable.export_portable_zip(
        dataset_id=args.dataset_id, output_path=args.output,
    )
    print(f"[export_zip] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())