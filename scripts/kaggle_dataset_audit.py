"""Read-only audit of existing YOLO labels; produces hashes and review templates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_yolo_labels(text: str, class_count: int) -> list[tuple]:
    labels = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"line {line_number}: expected class x y width height")
        try:
            class_id = int(parts[0])
            x, y, width, height = map(float, parts[1:])
        except ValueError as exc:
            raise ValueError(f"line {line_number}: nonnumeric label") from exc
        if not 0 <= class_id < class_count:
            raise ValueError(f"line {line_number}: class {class_id} out of mapping")
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            raise ValueError(f"line {line_number}: nonfinite coordinates")
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1):
            raise ValueError(f"line {line_number}: coordinates not normalized")
        if x - width / 2 < -.001 or y - height / 2 < -.001 or x + width / 2 > 1.001 or y + height / 2 > 1.001:
            raise ValueError(f"line {line_number}: bbox outside image")
        labels.append((class_id, x, y, width, height))
    return labels


def proposed_transcription(labels: list[tuple], names: list[str]) -> str | None:
    """Annotation-derived proposal only. A person must review before CCT export."""
    if not 4 <= len(labels) <= 10 or any(len(names[label[0]]) != 1 for label in labels):
        return None
    tolerance = statistics.median(label[4] for label in labels) * .6
    rows: list[list[tuple]] = []
    for label in sorted(labels, key=lambda item: item[2]):
        matching = next((row for row in rows if abs(label[2] - statistics.mean(item[2] for item in row)) <= tolerance), None)
        if matching is None:
            rows.append([label])
        else:
            matching.append(label)
    if len(rows) > 2:
        return None
    return "".join(names[label[0]] for row in rows for label in sorted(row, key=lambda item: item[1]))


def audit_dataset(root: Path) -> dict:
    root = root.resolve()
    config = yaml.safe_load((root / "data.yaml").read_text(encoding="utf-8-sig"))
    mapping = config["names"]
    if isinstance(mapping, dict):
        ordered = sorted((int(key), str(value)) for key, value in mapping.items())
        if [key for key, _ in ordered] != list(range(len(ordered))):
            raise ValueError("class mapping must be contiguous from 0")
        names = [value for _, value in ordered]
    else:
        names = list(map(str, mapping))
    if config.get("nc", len(names)) != len(names):
        raise ValueError("nc and names disagree")
    records = []
    class_counts = Counter()
    orphan_labels = []
    for split in SPLITS:
        image_root = root / "images" / split
        images = sorted(path for path in image_root.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES) if image_root.exists() else []
        label_paths = set()
        for image_path in images:
            if not image_path.resolve().is_relative_to(root):
                raise ValueError("image symlink escapes dataset")
            relative = image_path.relative_to(image_root)
            label_path = root / "labels" / split / relative.with_suffix(".txt")
            label_paths.add(label_path)
            record = {"image": image_path.relative_to(root).as_posix(), "label": label_path.relative_to(root).as_posix(), "source_split": split, "image_sha256": file_sha256(image_path), "bytes": image_path.stat().st_size, "valid": True, "group_id": None}
            try:
                image = cv2.imread(str(image_path))
                if image is None:
                    raise ValueError("image cannot decode")
                record["height"], record["width"] = image.shape[:2]
                pixels = hashlib.sha256()
                pixels.update(str(image.shape).encode())
                pixels.update(memoryview(image).cast("B"))
                record["pixel_sha256"] = pixels.hexdigest()
                if not label_path.resolve().is_relative_to(root):
                    raise ValueError("label symlink escapes dataset")
                record["label_sha256"] = file_sha256(label_path)
                labels = parse_yolo_labels(label_path.read_text(encoding="utf-8-sig"), len(names))
                record["object_count"] = len(labels)
                record["class_ids"] = sorted({label[0] for label in labels})
                class_counts.update(label[0] for label in labels)
                if len(names) == 36:
                    record["proposed_plate_text"] = proposed_transcription(labels, names)
            except (OSError, ValueError) as exc:
                record["valid"] = False
                record["error"] = str(exc)
            records.append(record)
        label_root = root / "labels" / split
        orphan_labels.extend(path.relative_to(root).as_posix() for path in label_root.rglob("*.txt") if path not in label_paths)
    by_hash = defaultdict(list)
    for record in records:
        by_hash[record.get("pixel_sha256", record["image_sha256"])].append(record)
    duplicates = [{"hash": digest, "images": [item["image"] for item in items], "cross_split": len({item["source_split"] for item in items}) > 1, "label_conflict": len({item.get("label_sha256") for item in items}) > 1} for digest, items in by_hash.items() if len(items) > 1]
    manifest_hash = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "root": str(root), "names": names, "config_sha256": file_sha256(root / "data.yaml"),
        "summary": {"images": len(records), "valid": sum(item["valid"] for item in records), "invalid": sum(not item["valid"] for item in records), "by_split": dict(Counter(item["source_split"] for item in records)), "objects_by_class": {names[class_id]: count for class_id, count in sorted(class_counts.items())}, "duplicate_groups": len(duplicates), "cross_split_duplicates": sum(item["cross_split"] for item in duplicates), "orphan_labels": len(orphan_labels), "holdout_status": "pending_human_group_curation"},
        "manifest_sha256": manifest_hash, "duplicates": duplicates, "orphan_labels": orphan_labels, "records": records,
    }


def write_review_template(dataset: dict, path: Path) -> None:
    fields = ["image", "image_sha256", "label_sha256", "group_id", "split", "human_verified", "plate_text", "proposal_from_labels"]
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in dataset["records"]:
            writer.writerow({"image": record["image"], "image_sha256": record["image_sha256"], "label_sha256": record.get("label_sha256", ""), "human_verified": "0", "proposal_from_labels": record.get("proposed_plate_text") or ""})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", type=Path, default=Path(__file__).resolve().parents[1] / "datasets")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--names", nargs="+", default=["vn_plate_detect", "plate_char_ocr", "helmet_detect"])
    args = parser.parse_args()
    review_paths = [args.output.parent / (name + "_curation.csv") for name in args.names]
    if args.output.exists() or any(path.exists() for path in review_paths):
        parser.error("audit/review output already exists; use a new run folder to preserve human curation")
    datasets = {}
    for name in args.names:
        if Path(name).name != name or name in {".", ".."}:
            parser.error("dataset names must be plain folder names")
        datasets[name] = audit_dataset(args.datasets / name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "audited_at": datetime.now(timezone.utc).isoformat(), "ground_truth": "Existing annotations audited structurally; human verification and group provenance still required", "datasets": datasets}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, dataset in datasets.items():
        write_review_template(dataset, args.output.parent / (name + "_curation.csv"))
    print(json.dumps({name: data["summary"] for name, data in datasets.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
