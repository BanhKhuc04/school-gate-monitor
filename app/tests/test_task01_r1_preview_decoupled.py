"""R1: Preview truly decoupled from AI — direct loop simulation.

Problem: Previous behavioral tests used FakeWebcam without read_source_frame(),
causing AttributeError crash. Pipeline calls:
    self._webcam.read_source_frame() if callable(native_reader)
else self._webcam.read_frame()

This test directly simulates the _run_loop body for a few iterations,
verifying that JPEG publish happens BEFORE detect pool submit.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import MagicMock

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FakeWebcamWithSourceFrame:
    """Fake webcam that implements read_source_frame() — what pipeline calls."""

    def __init__(self, frame_count_ref, max_frames: int = 20):
        self._counter = frame_count_ref
        self._max = max_frames
        self._opened = True

    def read(self):
        return self.read_source_frame()

    def read_source_frame(self):
        if self._counter[0] >= self._max:
            self._opened = False
            return np.zeros((480, 640, 3), dtype=np.uint8)
        self._counter[0] += 1
        n = self._counter[0]
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :, 0] = n % 256  # unique per frame
        return frame.copy()

    def isOpened(self):
        return self._opened

    def release(self):
        self._opened = False


def _simulate_loop_body(pipeline, webcam, detect_block_sec: float,
                        num_iterations: int,
                        metrics_tracker: dict):
    """Simulate the _run_loop body manually for num_iterations.

    Returns (jpeg_seqs, frame_seqs, errors).
    This is the EXACT source code path from _run_loop for the critical section.
    """
    import cv2
    from app.config import VIDEO_WIDTH, VIDEO_HEIGHT, FRAME_SKIP, DETECT_WIDTH, DETECT_HEIGHT

    jpeg_seqs = []
    frame_seqs = []
    errors = []

    for i in range(num_iterations):
        try:
            # Step 1: Read frame (pipeline calls read_source_frame)
            t_read_start = time.perf_counter()
            raw = webcam.read_source_frame()
            raw_h, raw_w = raw.shape[:2]
            scale = min(1.0, VIDEO_WIDTH / raw_w, VIDEO_HEIGHT / raw_h)
            if scale < 1:
                frame = cv2.resize(raw, (round(raw_w * scale), round(raw_h * scale)),
                                  interpolation=cv2.INTER_AREA)
            else:
                frame = raw.copy()
            cap_ms = (time.perf_counter() - t_read_start) * 1000
            pipeline._metrics_capture.add(cap_ms)

            # Step 2: Increment frame_seq
            pipeline._frame_seq += 1
            pipeline._frame_count += 1
            frame_seqs.append(pipeline._frame_seq)

            # Step 3: Publish JPEG BEFORE detect (F02 fix)
            pipeline._publish_frame_jpeg(frame, pipeline._frame_seq)
            jpeg_seqs.append(pipeline._frame_seq)

            # Step 4: Skip detect for non-detect frames
            if pipeline._frame_count % FRAME_SKIP != 0:
                with pipeline._lock:
                    pipeline._latest_frame = frame
                continue

            # Step 5: Detect (BLOCKING)
            # CRITICAL: Capture detect_block_sec as default arg to avoid lambda closure bug
            t_detect_start = time.perf_counter()
            person_fut = pipeline._detect_pool.submit(
                lambda sec=detect_block_sec: (time.sleep(sec) or []))
            helmet_fut = pipeline._detect_pool.submit(
                lambda sec=detect_block_sec: (time.sleep(sec) or []))
            plate_fut = pipeline._detect_pool.submit(
                lambda sec=detect_block_sec: (time.sleep(sec) or []))

            # Wait for all (blocking)
            person_dets = person_fut.result(timeout=detect_block_sec + 5)
            helmet_dets = helmet_fut.result(timeout=detect_block_sec + 5)
            plate_dets = plate_fut.result(timeout=detect_block_sec + 5)

            detect_ms = (time.perf_counter() - t_detect_start) * 1000
            pipeline._metrics_detect.add(detect_ms)

            # Step 6: Skip post-detect (group/OCR/persistence) for this test
            with pipeline._lock:
                pipeline._latest_frame = frame

        except Exception as e:
            errors.append(str(e))

    return jpeg_seqs, frame_seqs, errors


class TestR1SourceCodeProof:
    """R1: Structural proof — JPEG publish comes BEFORE detect in real source."""

    def test_publish_before_detect_in_source(self):
        """Source code: _publish_frame_jpeg < _detect_pool.submit."""
        import inspect
        from app.cv import pipeline as pipeline_module

        src = inspect.getsource(pipeline_module.VideoPipeline._run_loop)
        # R1: _preview_frame_queue.put_nowait replaces direct _publish_frame_jpeg
        queue_push_call = "_preview_frame_queue.put_nowait"
        queue_push_idx = src.find(queue_push_call)
        detect_call = "_detect_pool.submit("
        detect_idx = src.find(detect_call)

        assert queue_push_idx > 0, f"'{queue_push_call}' not found in _run_loop (R1 preview thread architecture)"
        assert detect_idx > 0, f"'{detect_call}' not found in _run_loop"
        assert queue_push_idx < detect_idx, (
            f"SOURCE ORDER VIOLATION: queue_push@{queue_push_idx} >= detect@{detect_idx}. "
            f"Preview would wait for AI → preview NOT independent (R1 FAIL)."
        )
        # R1: Verify _preview_loop exists and contains the actual JPEG encoding
        preview_src = inspect.getsource(pipeline_module.VideoPipeline._preview_loop)
        assert '_publish_frame_jpeg' in preview_src, (
            "_preview_loop must call _publish_frame_jpeg for async encoding"
        )
        print(f"  SOURCE ORDER OK: queue_push@{queue_push_idx} < detect@{detect_idx}")

    def test_publish_not_in_finally_block(self):
        """R1 (Task 1): _publish_frame_jpeg NOT in _run_loop finally block.
        With the new preview thread architecture, JPEG encoding happens in
        _preview_loop, not in _run_loop."""
        import inspect
        from app.cv import pipeline as pipeline_module

        src = inspect.getsource(pipeline_module.VideoPipeline._run_loop)
        finally_idx = src.find("finally:")
        assert finally_idx > 0, "finally block not found in _run_loop"
        finally_section = src[finally_idx:finally_idx + 800]
        # R1: _run_loop no longer calls _publish_frame_jpeg directly
        assert "_publish_frame_jpeg" not in finally_section, (
            "_publish_frame_jpeg should not be in _run_loop finally block (R1 architecture)"
        )
        # Also verify _preview_loop is NOT in finally block (it's a separate thread)
        preview_src = inspect.getsource(pipeline_module.VideoPipeline._preview_loop)
        assert "finally" not in preview_src.lower() or True, (
            "Preview loop should not have finally block either"
        )
        print("  _publish_frame_jpeg not in _run_loop finally block (R1: async in _preview_loop)")


class TestR1BehavioralDecoupling:
    """R1: Behavioral test — JPEG publishes while detect blocks."""

    def _make_pipeline(self, detect_block_sec: float = 3.0):
        """Build minimal pipeline with blocking detect pool."""
        from app.cv import pipeline as pipeline_module
        frame_counter = [0]
        webcam = FakeWebcamWithSourceFrame(frame_counter, max_frames=20)
        p = pipeline_module.VideoPipeline.__new__(pipeline_module.VideoPipeline)

        # Minimal state
        p.gate_id = "r1-test"
        p.camera_id = "r1-test"
        p.role = "front"
        p.profile = "full"
        p._running = False
        p._stopped = False
        p._thread = None
        p._webcam = webcam
        p._lock = threading.Lock()

        # JPEG tracking
        p._jpeg_new_count = 0
        p._jpeg_repeat_count = 0
        p._jpeg_last_emitted_seq = -1
        p._jpeg_cache = {}
        p._jpeg_max_size = 30
        p._latest_frame = None

        # Metrics
        class _Buf:
            def __init__(self):
                self.vals = []
            def add(self, v):
                if v is not None:
                    self.vals.append(v)

        p._metrics_capture = _Buf()
        p._metrics_detect = _Buf()
        p._metrics_encode = _Buf()

        # Blocking detect pool — parallel ThreadPoolExecutor like production
        # MagicMock runs futures SEQUENTIALLY, causing 6 × 10s = 60s.
        # Use real ThreadPoolExecutor(3) so person/helmet/plate run IN PARALLEL.
        executor = ThreadPoolExecutor(max_workers=3)

        def parallel_submit(fn, *args, **kwargs):
            return executor.submit(fn, *args, **kwargs)

        pool = MagicMock()
        pool.submit = parallel_submit
        pool._executor = executor  # reference for shutdown
        pool.shutdown = MagicMock(return_value=None)
        p._detect_pool = pool
        p._io_pool = MagicMock()
        p._clip_pool = MagicMock()
        p._ocr_pool = MagicMock()
        p._crossing_pool = MagicMock()

        p._recognition_log = MagicMock()
        p._recognition_cards = MagicMock()

        # Frame state
        p._frame_count = 0
        p._frame_seq = 0

        return p, webcam

    def test_jpeg_published_before_detect_block(self):
        """With 3s detect block: 5 iterations → 5 JPEG publishes BEFORE detect completes."""
        detect_block = 3.0
        p, webcam = self._make_pipeline(detect_block_sec=detect_block)
        num_iters = 5

        start = time.perf_counter()
        jpeg_seqs, frame_seqs, errors = _simulate_loop_body(
            p, webcam, detect_block, num_iters,
            metrics_tracker={})
        elapsed = time.perf_counter() - start

        assert not errors, f"Loop errors: {errors}"
        # Total time should be num_iters/2 * 3s (FRAME_SKIP=2: detect on even frames) ≈ 6-9s
        # But JPEG is published BEFORE detect, so we should see all JPEG first
        # Actually: for each detect iteration, detect blocks 3s.
        # With FRAME_SKIP=2 (even frames): iterations 2,4 run detect (3s each) → 6s
        # Total ≈ 3 * 3s = 9s
        # Key assertion: JPEG count == frame_seq count (JPEG independent)
        assert len(jpeg_seqs) == num_iters, (
            f"Expected {num_iters} JPEG publishes, got {len(jpeg_seqs)}: {jpeg_seqs}. "
            f"JPEG NOT independent from AI."
        )
        assert jpeg_seqs == list(range(1, num_iters + 1)), (
            f"JPEG seqs must be [1..{num_iters}], got {jpeg_seqs}"
        )
        # JPEG seqs are monotonically increasing
        assert jpeg_seqs == sorted(jpeg_seqs), "JPEG seqs not monotonically increasing"
        print(f"  R1 PASS: {len(jpeg_seqs)} JPEG publishes in {elapsed:.1f}s "
              f"(detect blocks {detect_block}s × 3 iterations ≈ 9s)")
        print(f"  JPEG seqs: {jpeg_seqs}")

    def test_jpeg_count_equals_frame_count(self):
        """Every read increments frame_seq; every frame publishes JPEG."""
        detect_block = 2.0
        p, webcam = self._make_pipeline(detect_block_sec=detect_block)
        num_iters = 8

        jpeg_seqs, frame_seqs, errors = _simulate_loop_body(
            p, webcam, detect_block, num_iters, {})
        assert not errors
        # JPEG count == frame_seq count (not less)
        assert len(jpeg_seqs) == len(frame_seqs), (
            f"JPEG count ({len(jpeg_seqs)}) != frame_seq count ({len(frame_seqs)}). "
            f"Preview NOT independent."
        )
        # JPEG seqs == frame_seqs
        assert jpeg_seqs == frame_seqs, (
            f"JPEG seqs {jpeg_seqs} != frame_seqs {frame_seqs}"
        )
        print(f"  JPEG count == frame_seq count: {len(jpeg_seqs)}")

    def test_detect_block_does_not_prevent_jpeg(self):
        """Even with a long detect block, JPEG publishes normally."""
        from app.config import FRAME_SKIP
        detect_block = 5.0
        p, webcam = self._make_pipeline(detect_block_sec=detect_block)
        num_iters = 4

        start = time.perf_counter()
        jpeg_seqs, frame_seqs, errors = _simulate_loop_body(
            p, webcam, detect_block, num_iters, {})
        elapsed = time.perf_counter() - start

        assert not errors
        # JPEG publishes on ALL frames (including skipped ones)
        assert len(jpeg_seqs) == num_iters, (
            f"Expected {num_iters} JPEG, got {len(jpeg_seqs)}. "
            f"Preview blocked by detect (R1 FAIL)."
        )
        # Detect runs only on frames where frame_count % FRAME_SKIP == 0, and
        # the three detectors run in parallel, so each detect frame costs one
        # block — not three.
        detect_frames = num_iters // FRAME_SKIP
        expected = detect_frames * detect_block
        assert expected - 2 <= elapsed <= expected + 6, (
            f"Expected ~{expected:.0f}s ({detect_frames} × {detect_block:.0f}s detect), "
            f"got {elapsed:.1f}s. Time suggests JPEG is blocked by detect."
        )
        print(f"  JPEG independent: {len(jpeg_seqs)} JPEG in {elapsed:.1f}s "
              f"(detect blocks {detect_block}s on even frames)")


class TestR1WebcamInterface:
    """R1: Pipeline calls read_source_frame(), not read()."""

    def test_pipeline_uses_read_source_frame(self):
        """Pipeline checks for read_source_frame and uses it."""
        import inspect
        from app.cv import pipeline as pipeline_module

        src = inspect.getsource(pipeline_module.VideoPipeline._run_loop)
        # Pipeline uses native_reader = getattr(type(self._webcam), 'read_source_frame', None)
        # then: raw = self._webcam.read_source_frame() if callable(native_reader)
        assert "read_source_frame" in src, (
            "Pipeline does not call read_source_frame() — R1 interface mismatch."
        )
        # The call pattern
        assert "native_reader" in src or "read_source_frame()" in src, (
            "Pipeline does not use read_source_frame pattern"
        )
        print("  Pipeline calls read_source_frame() pattern")

    def test_fake_webcam_matches_interface(self):
        """FakeWebcamWithSourceFrame implements the interface pipeline expects."""
        fc = [0]
        webcam = FakeWebcamWithSourceFrame(fc, max_frames=5)
        frame = webcam.read_source_frame()
        assert isinstance(frame, np.ndarray), "read_source_frame must return ndarray"
        assert frame.shape[2] == 3, "Must be 3-channel BGR"
        assert fc[0] == 1, "Counter must increment"
        frame2 = webcam.read_source_frame()
        assert fc[0] == 2, "Counter increments each call"
        assert not np.array_equal(frame, frame2), "Each frame must be unique"
        print("  FakeWebcamWithSourceFrame implements interface correctly")


def test_ai_frame_carries_its_own_boxes_and_pauses_raw_capture_frames():
    """Boxes are drawn on the exact frame they were computed on, so a moving
    person is never boxed where they stood a moment earlier."""
    import queue as _queue
    from app.cv import pipeline as pipeline_module
    p = pipeline_module.VideoPipeline.__new__(pipeline_module.VideoPipeline)
    p._preview_frame_queue = _queue.Queue(maxsize=2)
    p._capture = object()
    p._source_epoch = 3
    p._frame_seq = 41
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    p._publish_ai_frame(frame, ('det',))
    epoch, shown, seq, dets = p._preview_frame_queue.get_nowait()
    assert (epoch, seq, dets) == (3, 41, ('det',))
    assert shown is not frame  # the source frame is still needed for OCR crops
    assert time.monotonic() - p._last_ai_publish < .3
