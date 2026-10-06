"""Real API UI fixture with isolated SQLite/media; no CV, worker or maintenance."""
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
QA_ROOT = ROOT / "qa_logs" / "task05_ui"
QA_ROOT.mkdir(parents=True, exist_ok=True)
QA = Path(tempfile.mkdtemp(prefix="backend_", dir=QA_ROOT))
for key, value in {
    "APP_DB_PATH": str(QA / "app.db"), "TRAINING_DB_PATH": str(QA / "training.db"),
    "SNAPSHOTS_DIR": str(QA / "snapshots"), "BACKUP_DIR": str(QA / "backups"),
    "TRAINING_DATA_DIR": str(QA / "training"), "ENVIRONMENT": "development",
    "TASK3_CONTEXT_PATH": str(QA / "training"), "CV_PIPELINES_ENABLED": "0",
    "CLEANUP_ENABLED": "0", "BACKUP_ENABLED": "0", "PYTHONDONTWRITEBYTECODE": "1",
    "TASK3_TRAINING_WORKER_ENABLED": "0", "TASK3_SAMPLE_COLLECTOR_ENABLED": "0",
    "JWT_SECRET_KEY": "task05-isolated-ui-test-secret-not-production",
    "CORS_ORIGINS": "http://127.0.0.1:5198",
}.items():
    os.environ[key] = value

from app import db
from app.main import create_app
from app.training import dataset_repo


@asynccontextmanager
async def lifespan(app):
    import bcrypt
    import cv2
    import numpy as np
    db.init_db()
    dataset_repo.init_db()
    password_hash = bcrypt.hashpw(b"ui-fixture-password", bcrypt.gensalt()).decode()
    for role in ("admin", "management", "security", "teacher"):
        db.create_user("ui_" + role, password_hash, role, "10A1" if role == "teacher" else None)
    crop = QA / "snapshots" / "ui_plate.jpg"
    crop.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((100, 200, 3), 245, np.uint8)
    cv2.putText(image, "89F12345", (10, 62), cv2.FONT_HERSHEY_SIMPLEX, .9, (15, 15, 15), 2)
    cv2.imwrite(str(crop), image)
    sample = {
        "target_id": "ui_sample", "review_id": "ui_review", "gate_id": "main",
        "label": {"verdict": "correct", "target_text": "89F12345"},
        "source": {"gate_id": "main", "crop_media_id": str(crop), "image_w": 200, "image_h": 100},
        "bbox": [.1, .1, .9, .9], "version": 0,
    }
    draft = dataset_repo.create_dataset(name="UI_draft", engine="plate_ocr")
    dataset_repo.add_samples(draft, [sample])
    frozen = dataset_repo.create_dataset(name="UI_frozen", engine="plate_ocr")
    dataset_repo.add_samples(frozen, [{**sample, "target_id": "ui_frozen_sample"}])
    dataset_repo.freeze_dataset(frozen)
    candidate = dataset_repo.create_candidate(
        job_id="ui_baseline", dataset_id=frozen, engine="plate_ocr", target="plate_ocr",
        model_class="UI fixture without weights", model_path="", config={"fixture": True},
    )
    with dataset_repo.connect() as connection:
        connection.execute("UPDATE dataset_candidates SET state='active' WHERE id=?", (candidate,))
        connection.commit()
    yield


app = create_app()
app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8028)

