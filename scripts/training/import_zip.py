"""CLI: preview ZIP import rồi apply.

Usage:
    python -m scripts.training.import_zip preview /path/in.zip
    python -m scripts.training.import_zip apply /path/in.zip --name dataset_name
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description="Preview/apply ZIP portable dataset")
    sub = p.add_subparsers(dest="action", required=True)
    pp = sub.add_parser("preview")
    pp.add_argument("zip_path")
    ap = sub.add_parser("apply")
    ap.add_argument("zip_path")
    ap.add_argument("--name", required=True)
    args = p.parse_args()

    from app.training import dataset_repo, import_portable
    dataset_repo.init_db()

    if args.action == "preview":
        result = import_portable.preview_import(args.zip_path)
        import json
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0
    elif args.action == "apply":
        result = import_portable.apply_import(args.zip_path, dataset_name=args.name)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())