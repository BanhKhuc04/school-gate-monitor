import threading
import time

import numpy as np
import pytest

from app.cv.capture import LatestFrameCapture


class Source:
    def __init__(self):
        self.count = 0

    def read_source_frame(self):
        time.sleep(.01)
        self.count += 1
        return np.full((8, 12, 3), self.count % 255, np.uint8)


def test_capture_keeps_receiving_while_ai_is_blocked_three_seconds():
    source = Source()
    seen = []
    capture = LatestFrameCapture(source, on_frame=lambda packet: seen.append(packet.seq))
    capture.start()
    try:
        first = capture.read_latest(timeout=1)
        time.sleep(3)  # no AI consumer during this interval
        latest = capture.read_latest(after=first.seq, timeout=1)
        assert latest.seq > first.seq + 100
        assert len(seen) > 100
        assert capture.buffered_frames == 1
        assert latest.image[0, 0, 0] == latest.seq % 255
    finally:
        assert capture.stop()


def test_stop_joins_reader_and_does_not_return_stale_frame():
    capture = LatestFrameCapture(Source())
    capture.start()
    packet = capture.read_latest(timeout=1)
    assert capture.stop()
    with pytest.raises(RuntimeError, match='stopped'):
        capture.read_latest(after=packet.seq, timeout=.1)


def test_capture_read_failure_reaches_consumer():
    class Broken:
        def read_source_frame(self):
            raise RuntimeError('offline')
    capture = LatestFrameCapture(Broken())
    capture.start()
    with pytest.raises(RuntimeError, match='offline'):
        capture.read_latest(timeout=1)
    assert capture.stop()


def test_preview_encodes_new_frames_above_fifteen_fps_without_ai():
    from queue import Queue
    from app.cv.pipeline import VideoPipeline
    pipeline = VideoPipeline.__new__(VideoPipeline)
    pipeline._source_epoch = 2
    pipeline._preview_stop = threading.Event()
    pipeline._preview_frame_queue = Queue(maxsize=2)
    pipeline._draw_roi = lambda frame: None
    pipeline._draw_crossing_line_debug = lambda frame: None
    seen = []
    pipeline._publish_frame_jpeg = lambda frame, seq, **kw: seen.append(seq)
    worker = threading.Thread(target=pipeline._preview_loop)
    worker.start()
    try:
        for seq in range(30):
            pipeline._preview_frame_queue.put((2, np.zeros((8, 12, 3), np.uint8), seq))
            time.sleep(.02)
        assert len(set(seen)) >= 20  # old fixed 100ms encoder cannot achieve this
        pipeline._preview_frame_queue.put((1, np.zeros((8, 12, 3), np.uint8), 999))
        time.sleep(.05)
        assert 999 not in seen
    finally:
        pipeline._preview_stop.set()
        worker.join(1)
