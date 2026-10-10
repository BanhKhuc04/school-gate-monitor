"""Plate OCR quality gates added on top of the existing async OCR + voter:
- blur crops never reach OCR (saves a worker slot, keeps garbage out of the vote)
- a track already CONFIRMED by the voter stops re-submitting OCR every frame
"""
from unittest.mock import MagicMock
import numpy as np

from app.cv.ocr import compute_blur_score
from app.tests.test_dot_R import _build_pipeline_with_mocks, _FakeDet


def test_compute_blur_score_distinguishes_sharp_from_flat():
    flat = np.full((60, 120, 3), 100, dtype=np.uint8)
    checkerboard = np.indices((60, 120)).sum(axis=0) % 2 * 255
    sharp = np.repeat(checkerboard[:, :, None], 3, axis=2).astype(np.uint8)
    assert compute_blur_score(flat) == 0.0
    assert compute_blur_score(sharp) > compute_blur_score(flat)


def test_blur_crop_is_skipped_before_ocr_submit(monkeypatch):
    import app.cv.pipeline as module
    pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
    monkeypatch.setattr(module, 'PLATE_MIN_BLUR_SCORE', 40.0)
    pipeline._ocr_pool = MagicMock()
    frame = np.full((100, 100, 3), 100, dtype=np.uint8)  # flat -> blur score 0
    pipeline._ocr_submit_with_epoch(frame, _FakeDet('plate', (10, 10, 70, 50)), 1, 1, 0)
    pipeline._ocr_pool.submit.assert_not_called()
    assert pipeline._ocr_health['blur_skipped'] == 1
    assert 1 not in pipeline._ocr_pending


def test_confirmed_plate_skips_resubmitting_ocr(monkeypatch):
    from app.cv.plate_voter import PlateReadResult
    pipeline, _ = _build_pipeline_with_mocks(monkeypatch)
    pipeline._ocr_pool = MagicMock()
    confirmed = PlateReadResult(text='89F123792', confidence=0.9, sample_count=2, is_confident=True)
    pipeline._recognition_results = {1: (confirmed, __import__('time').time(), 5)}
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = pipeline._read_plate_voted(frame, _FakeDet('plate', (10, 10, 70, 50)), track_id=1, frame_seq=6)
    pipeline._ocr_pool.submit.assert_not_called()
    assert result.is_confident and result.text == '89F123792'
    assert pipeline._ocr_health['confirmed_skipped'] == 1
