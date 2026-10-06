"""Real API + isolated SQLite fixtures for the OCR browser regression suite."""
import os
import sys
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
QA_ROOT = ROOT / 'qa_logs' / 'ocr_browser'
QA_ROOT.mkdir(parents=True, exist_ok=True)
QA = Path(tempfile.mkdtemp(prefix='run_', dir=QA_ROOT))
(QA / 'snapshots').mkdir()
for key, value in {
    'APP_DB_PATH': str(QA / 'app.db'), 'TRAINING_DB_PATH': str(QA / 'training.db'),
    'SNAPSHOTS_DIR': str(QA / 'snapshots'), 'BACKUP_DIR': str(QA / 'backups'),
    'CLEANUP_ENABLED': '0', 'BACKUP_ENABLED': '0',
    'JWT_SECRET_KEY': 'ocr-browser-test-secret-not-for-production',
    'CORS_ORIGINS': 'http://127.0.0.1:5196',
}.items():
    os.environ[key] = value

from app import db
from app.main import create_app
from app.training import dataset_repo, dataset_freeze


@asynccontextmanager
async def lifespan(app):
    import bcrypt
    import cv2
    import numpy as np
    db.init_db()
    dataset_repo.init_db()
    if not db.get_user_by_username('ocr_admin'):
        db.create_user('ocr_admin', bcrypt.hashpw(b'ocr-test-password', bcrypt.gensalt()).decode(), 'admin')
    crop = QA / 'snapshots' / 'plate.jpg'
    crop.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(crop), np.full((60, 120, 3), 120, np.uint8))
    db.create_recognition_review(
        review_id='ocr-browser-review', violation_id=None, encounter_id=None,
        gate_id='main', camera_id='front', run_id='ocr-browser', source_epoch=0,
        frame_seq=1, observed_at='2026-10-03T00:00:00Z', crop_media_id=str(crop),
        crop_sha256=None, proposal_raw='89F123792', proposal_canonical='89F123792',
        proposal_engine='easyocr',
    )
    if db.get_recognition_review('ocr-browser-review')['version'] == 0:
        db.record_review_feedback(review_id='ocr-browser-review', reviewer_username='ocr_admin',
                                  reviewer_role='admin', verdict='correct', expected_version=0)
    from app.training.sample_collector import SampleCollector
    collector = SampleCollector(task_context_path=str(QA / 'collector'))
    collector.run_reconcile_once()
    assert collector.metrics()['reconcile_errors'] == 0
    assert collector.metrics()['processed_assets_copied'] == 1
    from app.training.worker import TrainingWorker
    TrainingWorker()._process_once()
    if not dataset_repo.list_datasets():
        dataset_id = dataset_repo.create_dataset(name='ocr_live_seed', engine='plate_ocr')
        dataset_repo.add_samples(dataset_id, [{
            'target_id': 'ocr-seed-target', 'review_id': 'ocr-browser-review', 'gate_id': 'main',
            'label': {'verdict': 'correct', 'target_text': '89F123792'},
            'source': {'gate_id': 'main', 'camera_id': 'front', 'crop_media_id': str(crop)},
            'bbox': [0.1, 0.1, 0.9, 0.9],
        }])
        dataset_freeze.freeze(dataset_id, output_dir=str(QA / 'frozen'))
    dataset_repo.create_candidate(
        job_id='qa-seeded-job', dataset_id=dataset_id, engine='plate_ocr', target='plate_ocr',
        model_class='QA baseline', model_path='', config={'fixture': True},
    )
    yield


app = create_app()
app.router.lifespan_context = lifespan

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8026)
