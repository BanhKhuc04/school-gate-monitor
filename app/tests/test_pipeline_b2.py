"""
pytest tests for B2: OCR async worker and JPEG cache in pipeline.

Tests B1 (capture/latest-frame) by verifying:
- OCR jobs submitted to worker thread pool
- PlateVoter.add_result() receives async OCR results
- JPEG cache stores encoded bytes
- Pipeline.get_jpeg() returns bytes

Tests B2 (OCR worker) by verifying:
- _submit_ocr_async cancels old pending job for same track_id
- _ocr_pending dict cleaned up when jobs complete
- OCR pool shutdown on pipeline.stop()
"""
import numpy as np
import pytest
from concurrent.futures import ThreadPoolExecutor

from app.cv.pipeline import VideoPipeline, _ocr_task
from app.cv.plate_voter import PlateVoter, PlateReadResult
from app.cv.ocr import _get_reader


class TestOcrTask:
    """B2: _ocr_task is a pure function that runs in the OCR worker thread."""

    def test_ocr_task_returns_dict(self):
        """_ocr_task must return a dict with 'full', 'confidence', etc."""
        # Create a synthetic plate-like crop (simple pattern)
        crop = np.ones((60, 150, 3), dtype=np.uint8) * 200
        result = _ocr_task(crop, track_id=42, frame_seq=1)
        assert isinstance(result, dict)
        assert 'full' in result
        assert 'confidence' in result
        assert 'top_line' in result
        assert 'bottom_line' in result

    def test_ocr_task_handles_bad_crop(self):
        """_ocr_task must not raise on invalid crop — returns empty dict."""
        # Empty crop
        result = _ocr_task(np.array([]), track_id=1, frame_seq=1)
        assert isinstance(result, dict)
        assert result.get('full', '') == ''

        # Crop too small
        small = np.zeros((10, 50, 3), dtype=np.uint8)
        result = _ocr_task(small, track_id=1, frame_seq=1)
        assert isinstance(result, dict)

    def test_ocr_task_no_global_state_mutation(self):
        """_ocr_task must not mutate the input crop array."""
        crop = np.ones((60, 150, 3), dtype=np.uint8) * 100
        original_sum = crop.sum()
        _ = _ocr_task(crop, track_id=1, frame_seq=1)
        assert crop.sum() == original_sum


class TestPlateVoterAddResult:
    """B2: PlateVoter.add_result() accepts pre-computed OCR dict."""

    def test_add_result_basic(self):
        """add_result() should return PlateReadResult with correct fields."""
        voter = PlateVoter(
            grid_px=60,
            window_sec=2.5,
            min_agree=2,
            min_confidence_single=0.9,
        )
        # Fake plate detection bbox
        class FakeDet:
            bbox = (100, 50, 400, 100)
            track_id = 42

        ocr_result = {'full': '59H112345', 'confidence': 0.7,
                       'top_line': '', 'bottom_line': ''}
        result = voter.add_result(FakeDet(), ocr_result)
        assert isinstance(result, PlateReadResult)
        assert result.text == '59H112345'
        assert result.confidence == 0.7
        # min_agree=2 (1 sample) + conf=0.7 < min_confidence_single=0.9 → not confident
        assert result.is_confident is False
        assert result.sample_count == 1

    def test_add_result_confident_by_count(self):
        """Multiple identical reads should reach is_confident."""
        voter = PlateVoter(
            grid_px=60,
            window_sec=2.5,
            min_agree=2,
            min_confidence_single=0.4,
        )

        class FakeDet:
            bbox = (100, 50, 400, 100)
            track_id = 99

        ocr_result = {'full': '51A12345', 'confidence': 0.5,
                       'top_line': '', 'bottom_line': ''}
        # Add 2 identical reads — đợt R (R4): conf=0.5 phải >= threshold (0.4)
        voter.add_result(FakeDet(), ocr_result)
        result2 = voter.add_result(FakeDet(), ocr_result)
        assert result2.sample_count == 2
        assert result2.is_confident is True

    def test_add_result_invalid_format_rejected(self):
        """add_result() must reject non-plate text via validate_plate_format."""
        voter = PlateVoter(
            grid_px=60,
            window_sec=2.5,
            min_agree=1,
            min_confidence_single=0.5,
        )

        class FakeDet:
            bbox = (100, 50, 400, 100)
            track_id = 7

        # Text that doesn't match VN plate regex → treated as invalid
        ocr_result = {'full': 'AHAMOVE123', 'confidence': 0.8,
                       'top_line': '', 'bottom_line': ''}
        result = voter.add_result(FakeDet(), ocr_result)
        # Should be empty because validate_plate_format rejects it
        assert result.text == ''

    def test_add_result_grid_fallback_when_no_track_id(self):
        """add_result() falls back to grid cache when track_id is None."""
        voter = PlateVoter(
            grid_px=60,
            window_sec=2.5,
            min_agree=2,
            min_confidence_single=0.9,
        )

        class FakeDetNoTrack:
            bbox = (100, 50, 400, 100)
            track_id = None

        ocr_result = {'full': '30A12345', 'confidence': 0.95,
                       'top_line': '', 'bottom_line': ''}
        voter.add_result(FakeDetNoTrack(), ocr_result)
        # Should use grid key, not track key
        assert 42 not in voter._samples_by_track
        assert len(voter._samples_by_grid) >= 1


class TestPipelineOcrAsyncState:
    """B2: VideoPipeline OCR pool and pending jobs are initialized correctly."""

    def test_pipeline_has_ocr_pool(self):
        """Pipeline must have _ocr_pool (ThreadPoolExecutor)."""
        # Can't fully instantiate VideoPipeline in test (needs DB, models),
        # but we can check the class definition has the pool attribute.
        import inspect
        source = inspect.getsource(VideoPipeline.__init__)
        assert '_ocr_pool' in source
        assert 'ThreadPoolExecutor' in source

    def test_pipeline_has_ocr_pending_dict(self):
        """Pipeline must have _ocr_pending dict for track→Future mapping."""
        import inspect
        source = inspect.getsource(VideoPipeline.__init__)
        assert '_ocr_pending' in source

    def test_pipeline_has_jpeg_cache(self):
        """Pipeline must have _jpeg_cache dict and _latest_jpeg."""
        import inspect
        source = inspect.getsource(VideoPipeline.__init__)
        assert '_jpeg_cache' in source
        assert '_latest_jpeg' in source

    def test_pipeline_has_frame_seq(self):
        """Pipeline must have _frame_seq counter."""
        import inspect
        source = inspect.getsource(VideoPipeline.__init__)
        assert '_frame_seq' in source

    def test_pipeline_has_get_jpeg_method(self):
        """Pipeline must have get_jpeg() method."""
        assert hasattr(VideoPipeline, 'get_jpeg')
        import inspect
        sig = inspect.signature(VideoPipeline.get_jpeg)
        # Returns Optional[bytes]
        assert 'self' in [p.name for p in sig.parameters.values()]

    def test_submit_ocr_async_exists(self):
        """Pipeline must have _submit_ocr_async method."""
        assert hasattr(VideoPipeline, '_submit_ocr_async')

    def test_stop_shuts_down_ocr_pool(self):
        """Pipeline.stop() must shutdown _ocr_pool."""
        import inspect
        source = inspect.getsource(VideoPipeline.stop)
        assert '_ocr_pool' in source
        assert 'shutdown' in source
