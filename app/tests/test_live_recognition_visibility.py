"""Verify what viewers receive and finished OCR on an unchanged plate."""
from concurrent.futures import Future
from queue import Queue
import threading
import time

import cv2
import numpy as np
import pytest

from app.cv.detector import Detection
from app.cv.pipeline import VideoPipeline


@pytest.mark.parametrize('age,epoch,visible', [(0, 0, True), (3, 0, False), (0, 1, False)])
def test_preview_jpeg_shows_only_recent_detections_from_current_camera(age, epoch, visible):
    p = VideoPipeline.__new__(VideoPipeline)
    p._source_epoch = 0
    p._preview_overlay = (epoch, time.monotonic()-age,
                          ((Detection('plate', .9, (20, 20, 70, 60)), (255, 255, 0), (255, 255, 0)),))
    p._roi_polygon_px = None
    p._crossing_detector = None
    p._preview_stop = threading.Event()
    p._preview_frame_queue = Queue(maxsize=2)
    output = []
    def publish(frame, seq):
        ok, jpeg = cv2.imencode('.jpg', frame)
        assert ok
        output.append(cv2.imdecode(jpeg, cv2.IMREAD_COLOR))
        p._preview_stop.set()
    p._publish_frame_jpeg = publish
    p._preview_frame_queue.put((np.zeros((90, 110, 3), np.uint8), 2))
    worker = threading.Thread(target=p._preview_loop)
    worker.start()
    worker.join(timeout=3)
    p._preview_stop.set()
    assert not worker.is_alive()
    assert bool(np.any(output[0][19:22, 25:65] > 100)) == visible


class CompletedPool:
    def submit(self, task, crop, track, seq, epoch):
        future = Future()
        future.set_result({'full':'89F123792', 'top_line':'89-F1', 'bottom_line':'237.92',
                           'confidence':.99, 'track_id':track, 'frame_seq':seq, 'source_epoch':epoch})
        return future


def test_plate_only_collects_finished_ocr_when_crop_does_not_improve():
    from app.tests.test_task01_post_video_rear_ocr import _build_pipeline
    from app.cv.best_plate import make_candidate
    p = _build_pipeline()
    p._ocr_pool = CompletedPool()
    p._frame_seq = 1
    frame = np.random.default_rng(5).integers(30, 225, (180, 240, 3), dtype=np.uint8)
    plate = Detection('plate', .99, (20, 40, 170, 130))
    candidate = make_candidate(frame, plate.bbox, plate.confidence, 1, time.time())
    track = -(int(95//32)*10000+int(85//32)+1)
    p._best_plates.offer(track, candidate)
    p._best_plates.trigger(track, p._ocr_pool, None, 0)
    p._frame_seq = 2
    p._observe_plate_only(frame, [plate])
    assert p._ocr_health['completed'] == 1
    assert p._best_plates.result(track).text == '89F123792'
    assert len(p._plate_consensus) == 1


def test_plate_only_card_shows_ocr_crop_without_person_identity():
    from app.cv.recognition_cards import RecognitionCards
    from app.cv.best_plate import make_candidate
    from app.cv.plate_voter import PlateReadResult
    store = RecognitionCards('main', 'front')
    frame = np.full((160, 200, 3), 140, np.uint8)
    best = make_candidate(frame, (20, 40, 170, 130), .99, 1, 10)
    result = PlateReadResult(text='89F123792', confidence=.99, sample_count=1, is_confident=True)
    try:
        store.observe_plate(-20003, best, result, {'attempts':1, 'best_frame_id':1}, 2, 0, now=10)
        for future in list(store._pending.values()):
            future.result(timeout=3)
        card = store.snapshot(now=10)['cards'][0]
        assert card['kind'] == 'plate'
        assert card['track_id'] is None and card['vehicle_track_id'] is None
        assert card['plate']['text'] == '89F123792'
        assert card['plate']['association'] == 'unverified'
        assert card['plate']['state'] == 'candidate'
        assert set(card['images']) == {'plate'}
        assert store.image(card['images']['plate']['id'])
        store.reset(1)
        store.observe_plate(-20003, best, result, {}, 3, 0, now=10)
        assert store.snapshot(now=10)['cards'] == []
    finally:
        store.close(wait=True)
