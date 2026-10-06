"""Manual round-trip test for Task 3 — verify export + import giữ ảnh thật."""
import json
import os
import tempfile
from pathlib import Path

# Workaround: chạy inline
import sys
sys.path.insert(0, "D:/Work/Project_motorbike")

from app.training import dataset_repo, dataset_freeze, export_portable, import_portable


def sample(tid, target="ABC1234", crop="crop.png"):
    return {
        "target_id": tid,
        "review_id": f"r_{tid}",
        "gate_id": "main",
        "label": {"verdict": "correct", "target_text": target, "top_line": None,
                  "bottom_line": None, "quality_score": 0.9},
        "source": {"gate_id": "main", "camera_id": "cam1", "run_id": "run1",
                   "frame_seq": 1, "source_epoch": 0,
                   "observed_at": "2026-10-02T00:00:00Z",
                   "crop_sha256": "abc", "crop_media_id": crop,
                   "image_w": 200, "image_h": 80},
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "classes": None, "split": None, "holdout": False, "is_augmented": False,
    }


tmp = Path(tempfile.mkdtemp())
fake_snap = tmp / "snaps"
fake_snap.mkdir()
crop_file = fake_snap / "crop.png"
crop_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

# Patch config module trước khi import
import app.config as cfg
cfg.SNAPSHOTS_DIR = str(fake_snap)

db1 = str(tmp / "src.db")
dataset_repo.init_db(db_path=db1)
ds = dataset_repo.create_dataset(name="rt1", engine="plate_ocr", db_path=db1)
dataset_repo.add_samples(ds, [
    sample(f"t{i}", target=f"XYZ{i:04d}", crop="crop.png") for i in range(3)
], db_path=db1)
dataset_freeze.freeze(ds, output_dir=str(tmp / "frz"), db_path=db1)

zip_path = tmp / "out.zip"
res = export_portable.export_portable_zip(
    dataset_id=ds, output_path=str(zip_path), db_path=db1,
    staging_dir=str(tmp / "stg"),
)
print(f"export: asset_count={res['asset_count']}, missing={len(res['missing_files'])}")

db2 = str(tmp / "dst.db")
dataset_repo.init_db(db_path=db2)
imp = import_portable.apply_import(str(zip_path), dataset_name="rt1_imp",
                                   staging_root=str(tmp / "imp"), db_path=db2)
print(f"import: dataset_id={imp['dataset_id']}, added={imp['added']}")

samples = dataset_repo.list_samples(imp["dataset_id"], db_path=db2)
for s in samples:
    print(f"  sample {s['target_id']}: crop_path={s['source'].get('crop_path')}")

asset_root = Path("data") / "training" / "assets" / imp["dataset_id"]
files = list(asset_root.glob("*"))
print(f"asset root exists={asset_root.exists()}, file count={len(files)}")
print("OK round-trip")