"""Export only explicitly reviewed, grouped samples; never infer ground truth."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import yaml

from kaggle_dataset_audit import file_sha256

SPLITS = {"train", "val", "test"}


def validate_curation(records: list[dict], rows: list[dict], kind: str) -> list[dict]:
    by_image = {record["image"]: record for record in records}
    selected = []
    images, hashes, groups = set(), set(), {}
    for row in rows:
        image = row.get("image", "")
        record = by_image.get(image)
        if record is None or not record.get("valid"):
            raise ValueError(f"{image}: missing or invalid audited sample")
        if row.get("human_verified") != "1":
            raise ValueError(f"{image}: human verification required")
        group, split = row.get("group_id", "").strip(), row.get("split", "").strip()
        if not group or split not in SPLITS:
            raise ValueError(f"{image}: explicit video/session/encounter group and split required")
        if row.get("image_sha256") != record["image_sha256"]:
            raise ValueError(f"{image}: image hash changed since review")
        if record.get("label_sha256") and row.get("label_sha256") != record["label_sha256"]:
            raise ValueError(f"{image}: annotation hash changed since review")
        digest = record.get("pixel_sha256", record["image_sha256"])
        if image in images or digest in hashes:
            raise ValueError(f"{image}: duplicate image; curate one copy")
        if group in groups and groups[group] != split:
            raise ValueError(f"{image}: same source group appears in multiple splits")
        if kind == "ocr" and not re.fullmatch(r"[A-Z0-9]{4,10}", row.get("plate_text", "")):
            raise ValueError(f"{image}: reviewed plate_text must contain 4-10 A-Z0-9 characters")
        images.add(image)
        hashes.add(digest)
        groups[group] = split
        selected.append({**record, "split": split, "group_id": group, "human_verified": True, "plate_text": row.get("plate_text", "") if kind == "ocr" else None})
    if not selected:
        raise ValueError("pending_data: no human-reviewed samples selected")
    return selected


def export_curated(dataset: dict, rows: list[dict], output: Path, kind: str) -> dict:
    selected = validate_curation(dataset["records"], rows, kind)
    if {record["split"] for record in selected} != SPLITS:
        raise ValueError("pending_data: independent train, val and test groups are required")
    root = Path(dataset["root"]).resolve()
    output = output.resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError("export output must be outside source dataset")
    if output.exists():
        raise ValueError("output already exists; select a new version")
    # Recheck reviewed files before any copies or directory creation.
    total_bytes = 0
    for record in selected:
        for field in ("image", "label"):
            path = (root / record[field]).resolve()
            if not path.is_relative_to(root) or file_sha256(path) != record[field + "_sha256"]:
                raise ValueError(f"reviewed {field} changed: {record[field]}")
            total_bytes += path.stat().st_size
    if total_bytes > 1024 ** 3:
        raise ValueError("export exceeds 1 GB; reduce the selected batch")
    parent = output.parent
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < max(10 * 1024 ** 3, total_bytes * 2 + 1024 ** 3):
        raise ValueError("insufficient space: require >=10 GB and room for projected output")
    output.mkdir(parents=True)
    output_records = []
    annotations = {split: [] for split in SPLITS}
    for record in selected:
        split = record["split"]
        basename = record["image_sha256"][:20] + Path(record["image"]).suffix.lower()
        image_rel = Path("images") / split / basename
        image_path = output / image_rel
        image_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / record["image"], image_path)
        label_rel = Path("labels") / split / Path(basename).with_suffix(".txt")
        if kind == "detect":
            (output / label_rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / record["label"], output / label_rel)
        else:
            annotations[split].append({"image_path": image_rel.as_posix(), "plate_text": record["plate_text"]})
        output_records.append({**record, "source_image": record["image"], "image": image_rel.as_posix(), "label": label_rel.as_posix() if kind == "detect" else None})
    if kind == "detect":
        config = {"path": ".", "train": "images/train", "val": "images/val", "test": "images/test", "names": dataset["names"]}
        (output / "data.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        for split, entries in annotations.items():
            with (output / (split + ".csv")).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["image_path", "plate_text"])
                writer.writeheader()
                writer.writerows(entries)
        plate_config = {"max_plate_slots": 10, "alphabet": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_", "pad_char": "_", "img_height": 64, "img_width": 128, "image_color_mode": "rgb", "keep_aspect_ratio": False}
        (output / "plate_config.yaml").write_text(yaml.safe_dump(plate_config, sort_keys=False), encoding="utf-8")
    manifest = {"schema_version": 1, "kind": kind, "source_manifest_sha256": dataset["manifest_sha256"], "names": dataset["names"], "counts": dict(Counter(record["split"] for record in selected)), "group_counts": {split: len({record["group_id"] for record in selected if record["split"] == split}) for split in sorted(SPLITS)}, "holdout_status": "human_curated_group_disjoint", "production_acceptance": "pending_local_labeled_encounters", "contains_student_profiles": False, "samples": output_records}
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
    (output / "manifest.json").write_bytes(encoded.encode("utf-8"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    (output / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
    return {"output": str(output), "manifest_sha256": digest, "counts": manifest["counts"], "bytes": total_bytes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--curation", type=Path, required=True)
    parser.add_argument("--kind", choices=("detect", "ocr"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.audit.read_text(encoding="utf-8"))["datasets"][args.dataset]
    with args.curation.open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row.get("human_verified") == "1"]
    try:
        print(json.dumps(export_curated(dataset, rows, args.output, args.kind), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
