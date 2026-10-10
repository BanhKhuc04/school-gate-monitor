"""Small deterministic tests for annotation and export safety, without training."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from kaggle_dataset_audit import audit_dataset, parse_yolo_labels, proposed_transcription, write_review_template
from kaggle_export import export_curated, validate_curation


class AnnotationTests(unittest.TestCase):
    def test_invalid_class_coordinates_and_nan_rejected(self):
        for text in ("36 .5 .5 .2 .2", "0 nan .5 .2 .2", "0 .99 .5 .2 .2", "0 .5 .5 0 .2"):
            with self.assertRaises(ValueError):
                parse_yolo_labels(text, 36)

    def test_two_lines_preserve_top_bottom_order(self):
        labels = parse_yolo_labels("8 .2 .25 .1 .15\n9 .4 .25 .1 .15\n15 .6 .25 .1 .15\n1 .2 .75 .1 .15\n2 .4 .75 .1 .15\n3 .6 .75 .1 .15\n4 .8 .75 .1 .15", 36)
        self.assertEqual(proposed_transcription(labels, list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")), "89F1234")

    def test_legend_is_not_ocr_plate(self):
        labels = [(i, .5, .5, .05, .05) for i in range(36)]
        self.assertIsNone(proposed_transcription(labels, list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")))

    def test_review_template_does_not_overwrite_existing_work(self):
        with tempfile.TemporaryDirectory(prefix="kaggle-review-test-") as directory:
            path = Path(directory) / "curation.csv"
            path.write_text("human-reviewed work", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_review_template({"records": []}, path)
            self.assertEqual(path.read_text(), "human-reviewed work")


class CurationTests(unittest.TestCase):
    def record(self, image, digest):
        return {"image": image, "image_sha256": digest, "valid": True}

    def row(self, image, group, split, digest):
        return {"image": image, "image_sha256": digest, "group_id": group, "split": split, "human_verified": "1", "plate_text": "89F1234"}

    def test_cross_split_session_rejected(self):
        records = [self.record("a.jpg", "a"), self.record("b.jpg", "b")]
        rows = [self.row("a.jpg", "video1", "train", "a"), self.row("b.jpg", "video1", "test", "b")]
        with self.assertRaises(ValueError):
            validate_curation(records, rows, "detect")

    def test_duplicate_image_hash_rejected(self):
        records = [self.record("a.jpg", "a"), self.record("b.jpg", "a")]
        rows = [self.row("a.jpg", "video1", "train", "a"), self.row("b.jpg", "video2", "test", "a")]
        with self.assertRaises(ValueError):
            validate_curation(records, rows, "detect")

    def test_unreviewed_or_changed_image_rejected(self):
        records = [self.record("a.jpg", "a")]
        for update in ({"human_verified": "0"}, {"image_sha256": "changed"}, {"group_id": ""}):
            row = self.row("a.jpg", "video1", "train", "a") | update
            with self.assertRaises(ValueError):
                validate_curation(records, [row], "ocr")

    def test_human_correction_kept_without_character_rewrite(self):
        record = self.record("a.jpg", "a")
        row = self.row("a.jpg", "video1", "train", "a") | {"plate_text": "30A10009"}
        result = validate_curation([record], [row], "ocr")
        self.assertEqual(result[0]["plate_text"], "30A10009")


class ExportTests(unittest.TestCase):
    def fixture(self, base):
        root = base / "source"
        root.mkdir()
        (root / "data.yaml").write_text("names: [plate]\nnc: 1\n", encoding="utf-8")
        for index, split in enumerate(("train", "val", "test")):
            (root / "images" / split).mkdir(parents=True)
            (root / "labels" / split).mkdir(parents=True)
            image = np.full((32, 64, 3), 40 + index * 50, dtype=np.uint8)
            cv2.imwrite(str(root / "images" / split / "plate.png"), image)
            (root / "labels" / split / "plate.txt").write_text("0 0.5 0.5 0.8 0.5\n", encoding="ascii")
        dataset = audit_dataset(root)
        rows = [{"image": record["image"], "image_sha256": record["image_sha256"], "label_sha256": record["label_sha256"], "group_id": "session_" + record["source_split"], "split": record["source_split"], "human_verified": "1", "plate_text": "89F12345"} for record in dataset["records"]]
        return dataset, rows

    def test_export_hash_and_portable_paths_for_detect_and_ocr(self):
        # Tiny temporary fixture. Mock only disk capacity, never annotation checks.
        with tempfile.TemporaryDirectory(prefix="kaggle-export-test-") as directory:
            base = Path(directory)
            dataset, rows = self.fixture(base)
            with patch("kaggle_export.shutil.disk_usage", return_value=SimpleNamespace(free=20 * 1024 ** 3)):
                for kind in ("detect", "ocr"):
                    output = base / kind
                    export_curated(dataset, rows, output, kind)
                    manifest_bytes = (output / "manifest.json").read_bytes()
                    self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), (output / "manifest.sha256").read_text().strip())
                    manifest = json.loads(manifest_bytes)
                    self.assertEqual(manifest["counts"], {"train": 1, "val": 1, "test": 1})
                    for sample in manifest["samples"]:
                        self.assertTrue((output / sample["image"]).is_file())
                        if kind == "detect":
                            self.assertTrue((output / sample["label"]).is_file())
                    if kind == "ocr":
                        for split in ("train", "val", "test"):
                            with (output / (split + ".csv")).open(newline="") as stream:
                                entry = next(csv.DictReader(stream))
                            self.assertTrue((output / entry["image_path"]).is_file())
                            self.assertEqual(entry["plate_text"], "89F12345")

    def test_changed_labels_and_low_space_rejected_before_output(self):
        with tempfile.TemporaryDirectory(prefix="kaggle-export-test-") as directory:
            base = Path(directory)
            dataset, rows = self.fixture(base)
            output = base / "blocked"
            with patch("kaggle_export.shutil.disk_usage", return_value=SimpleNamespace(free=9 * 1024 ** 3)):
                with self.assertRaisesRegex(ValueError, "insufficient space"):
                    export_curated(dataset, rows, output, "detect")
            self.assertFalse(output.exists())
            (base / "source" / "labels" / "train" / "plate.txt").write_text("0 0.5 0.5 0.7 0.5\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "changed"):
                export_curated(dataset, rows, output, "detect")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
