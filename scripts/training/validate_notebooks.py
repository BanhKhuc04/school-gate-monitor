"""Validate JSON của 3 notebook Kaggle."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # workspace root
nb_dir = ROOT / "notebooks"

failed = 0
for name in ("yolo11_plate.ipynb", "yolo11_helmet_electric.ipynb", "cct_plate_ocr.ipynb"):
    path = nb_dir / name
    if not path.is_file():
        print(f"MISSING: {path}")
        failed += 1
        continue
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"INVALID JSON {name}: {exc}")
        failed += 1
        continue
    print(f"\n=== {name} ===")
    fmt = f"{nb['nbformat']}.{nb['nbformat_minor']}"
    print(f"nbformat: {fmt}")
    n_cells = len(nb["cells"])
    print(f"cells: {n_cells}")
    ks = nb["metadata"]["kernelspec"]
    print(f"kernel: {ks['name']} ({ks['display_name']})")
    for i, c in enumerate(nb["cells"]):
        first = c["source"][0].strip()[:70] if c["source"] else ""
        print(f"  cell {i}: {c['cell_type']} | {first}")
    # Required keys
    required = {"cells", "metadata", "nbformat", "nbformat_minor"}
    missing = required - set(nb.keys())
    if missing:
        print(f"  MISSING keys: {missing}")
        failed += 1

if failed:
    print(f"\n{failed} notebook invalid")
    sys.exit(1)
print("\nALL 3 NOTEBOOKS OK")