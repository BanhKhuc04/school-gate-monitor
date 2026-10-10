"""Inspect dataset audit để hỗ trợ người duyệt R8."""
import json
import sys
from pathlib import Path

AUDIT = Path("tasks/task-05/dataset_audit.json")


def main():
    if not AUDIT.exists():
        print(f"Missing {AUDIT}", file=sys.stderr)
        return 1
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    print("=" * 70)
    print("DETECT DUPLICATES (cần người duyệt chọn 1 ảnh / nhóm)")
    print("=" * 70)
    det = data["datasets"]["vn_plate_detect"]
    for i, dup in enumerate(det["duplicates"]):
        h = dup["hash"][:16]
        print()
        print(f"Group {i + 1}: hash={h}...  cross_split={dup['cross_split']}  label_conflict={dup['label_conflict']}")
        for img in dup["images"]:
            print(f"  - {img}")
    print()
    print("=" * 70)
    print("OCR SUMMARY")
    print("=" * 70)
    ocr = data["datasets"]["plate_char_ocr"]
    s = ocr["summary"]
    print(f"  images: {s['images']}, valid: {s['valid']}, invalid: {s['invalid']}")
    print(f"  by_split: {s['by_split']}")
    print(f"  duplicates: {s['duplicate_groups']}, cross_split: {s['cross_split_duplicates']}")
    by_cls = s.get("objects_by_class", {})
    rare = sorted([(k, v) for k, v in by_cls.items() if v < 10])
    print(f"  rare chars (<10 bbox): {rare}")
    print()
    with_proposal = sum(1 for r in ocr["records"] if r.get("proposed_plate_text"))
    print(f"  records có proposal_from_labels: {with_proposal} / {s['images']}")
    print()
    print("=" * 70)
    print("HELMET SUMMARY")
    print("=" * 70)
    h = data["datasets"]["helmet_detect"]["summary"]
    print(f"  {h}")
    print()
    print("=" * 70)
    print("HOLDOUT STATUS")
    print("=" * 70)
    for name, ds in data["datasets"].items():
        print(f"  {name}: {ds['summary']['holdout_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())