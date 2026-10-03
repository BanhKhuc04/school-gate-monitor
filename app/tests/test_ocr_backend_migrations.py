"""Regression coverage for the deployed OCR/training schema and worker cycles."""
import logging
import sqlite3

from app.training import dataset_repo


def test_legacy_training_jobs_are_migrated_without_losing_rows(tmp_path):
    dsn = str(tmp_path / 'legacy.db')
    with sqlite3.connect(dsn) as conn:
        conn.execute('''CREATE TABLE dataset_jobs (
            id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, target TEXT NOT NULL,
            state TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
            config_json TEXT, log_path TEXT, metrics_path TEXT, error TEXT,
            gpu_resource_id TEXT
        )''')
        conn.execute("INSERT INTO dataset_jobs (id,dataset_id,target,state,created_at) "
                     "VALUES ('old-job','old-data','plate_ocr','cancelled','2026-10-01')")
    dataset_repo.init_db(dsn)
    dataset_repo.init_db(dsn)
    job = dataset_repo.get_job('old-job', dsn)
    assert job['operation'] == 'evaluate_baseline'
    assert job['runner_type'] is None
    assert job['split_hash'] is None
    assert job['state'] == 'cancelled'
    assert dataset_repo.list_jobs(db_path=dsn)[0]['id'] == 'old-job'


def test_training_worker_runs_one_cycle_on_migrated_db(tmp_path, monkeypatch, caplog):
    dsn = str(tmp_path / 'worker.db')
    dataset_repo.init_db(dsn)
    with sqlite3.connect(dsn) as conn:
        for column in ('operation', 'runner_type', 'split_hash'):
            conn.execute(f'ALTER TABLE dataset_jobs DROP COLUMN {column}')
    dataset_repo.init_db(dsn)
    monkeypatch.setenv('TRAINING_DB_PATH', dsn)
    from app.training.worker import TrainingWorker
    with caplog.at_level(logging.WARNING):
        TrainingWorker()._process_once()
    assert 'resume error' not in caplog.text
    assert not caplog.records


def test_review_schema_and_collector_cycle_use_real_db(test_app, tmp_path, monkeypatch):
    from app import db
    from app.training.sample_collector import SampleCollector
    db.init_db()
    monkeypatch.setattr('app.config.SNAPSHOTS_DIR', str(tmp_path))
    import cv2
    import numpy as np
    crop = tmp_path / 'plate.jpg'
    assert cv2.imwrite(str(crop), np.full((60, 120, 3), 120, np.uint8))
    db.create_recognition_review(
        review_id='migration-review', gate_id='main', camera_id='front', run_id='test',
        source_epoch=0, frame_seq=1, observed_at='2026-10-03T00:00:00',
        proposal_raw='89F123792', proposal_canonical='89F123792',
        violation_id=None, encounter_id=None, crop_media_id='plate.jpg', crop_sha256=None,
        proposal_engine='easyocr',
    )
    result = db.record_review_feedback(
        review_id='migration-review', reviewer_username='admin', reviewer_role='admin',
        verdict='correct', expected_version=0,
    )
    assert result['new_version'] == 1
    review = db.get_recognition_review('migration-review')
    assert review['version'] == 1
    assert review['feedback'][-1]['id'] == result['feedback_id']
    page = db.list_recognition_reviews(status='confirmed')
    assert page['total'] == 1
    assert page['items'][0]['version'] == 1
    collector = SampleCollector(task_context_path=str(tmp_path / 'collector'))
    collector.run_reconcile_once()
    assert collector.metrics()['reconcile_errors'] == 0
    assert collector.metrics()['reconcile_updated'] == 1
    assert collector.metrics()['processed_assets_copied'] == 1
    assets = list((tmp_path / 'collector' / 'collected_assets').glob('*.bin'))
    assert len(assets) == 1
    assert assets[0].read_bytes() == crop.read_bytes()


def test_reconcile_retries_missing_crop_and_acks_real_feedback_id(test_app, tmp_path, monkeypatch):
    from app import db
    from app.training.sample_collector import SampleCollector
    monkeypatch.setattr('app.config.SNAPSHOTS_DIR', str(tmp_path))
    review_args = dict(
        review_id='feedback-id-seed', gate_id='main', camera_id='front', run_id='test',
        source_epoch=0, frame_seq=2, observed_at='2026-10-03T00:00:01',
        proposal_raw='89F123792', proposal_canonical='89F123792',
        violation_id=None, encounter_id=None, crop_media_id='late.jpg', crop_sha256=None,
        proposal_engine='easyocr',
    )
    db.create_recognition_review(**review_args)
    db.record_review_feedback(
        review_id='feedback-id-seed', reviewer_username='admin', reviewer_role='admin',
        verdict='unreadable', expected_version=0,
    )
    review_args['review_id'] = 'retry-review'
    db.create_recognition_review(**review_args)
    feedback = db.record_review_feedback(
        review_id='retry-review', reviewer_username='admin', reviewer_role='admin',
        verdict='correct', expected_version=0,
    )
    assert feedback['feedback_id'] > feedback['new_version']
    collector = SampleCollector(task_context_path=str(tmp_path / 'collector'))
    collector.run_reconcile_once()
    assert 'retry-review' not in collector._cursor
    (tmp_path / 'late.jpg').write_bytes(b'recovered-crop')
    collector.run_reconcile_once()
    assert collector._cursor['retry-review'] == feedback['feedback_id']
    assert collector.metrics()['reconcile_updated'] == 1
    collector.run_reconcile_once()
    assert collector.metrics()['reconcile_updated'] == 1


def test_training_reviews_endpoint_reuses_filters_and_requires_admin(client):
    from app.tests.conftest import auth_headers
    route = '/api/training/recognition-reviews'
    assert client.get(route).status_code == 401
    assert client.get(route, headers=auth_headers(client, 'security')).status_code == 403
    headers = auth_headers(client, 'admin')
    response = client.get(route, params={'gate_id': 'missing-gate', 'limit': 1}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {'total': 0, 'limit': 1, 'offset': 0, 'items': []}
    assert client.get(route, params={'limit': 101}, headers=headers).status_code == 422
