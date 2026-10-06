"""Visual observations never imply student identity or official violations."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock
import time

import cv2
import numpy as np


def group(track=42, helmet='With Helmet'):
    from app.cv.detector import Detection as D
    return {'track_id': track, 'vehicle_track_id': None, 'vehicle_type': None,
            '_person': D('person', .9, (10, 10, 90, 110), track), '_vehicle': None,
            'helmet_dets': [D(helmet, .9, (30, 5, 60, 30))] if helmet else [],
            'plate_dets': [], 'association_reasons': [], 'posture_status': 'unknown'}


def test_cards_update_same_track_and_require_distinct_frames():
    from app.cv.recognition_cards import RecognitionCards
    store = RecognitionCards('main', 'front')
    frame = np.full((140, 120, 3), 100, np.uint8)
    try:
        store.observe(frame, group(), 1, 0, now=10)
        card = store.snapshot(now=10)['cards'][0]
        assert card['person']['state'] == 'checking' and card['person']['samples'] == 1
        store.observe(frame, group(), 1, 0, now=10.3)
        assert store.snapshot(now=10.3)['cards'][0]['person']['samples'] == 1
        for seq, ts in [(2, 10.21), (3, 10.42), (4, 10.63)]:
            store.observe(frame, group(), seq, 0, now=ts)
        cards = store.snapshot(now=10.63)['cards']
        assert len(cards) == 1
        assert cards[0]['person']['state'] == 'confirmed'
        assert cards[0]['helmet']['state'] == 'confirmed'
        assert cards[0]['helmet']['samples'] == 4
        assert 'student_id' not in cards[0]
    finally:
        store.close(wait=True)


def test_conflicting_head_and_untracked_person_cannot_be_confirmed():
    from app.cv.recognition_cards import RecognitionCards
    store = RecognitionCards('main', 'front')
    frame = np.zeros((140, 120, 3), np.uint8)
    try:
        store.observe(frame, group(), 1, 0, now=10)
        store.observe(frame, group(helmet='Without Helmet'), 2, 0, now=10.2)
        assert store.snapshot(now=10.2)['cards'][0]['helmet']['state'] == 'review'
        store.observe(frame, group(track=None), 3, 0, now=10.4)
        assert any(c['person']['state'] == 'review' for c in store.snapshot(now=10.4)['cards'])
        store.reset(1)
        store.observe(frame, group(), 4, 0, now=10.6)
        assert store.snapshot(now=10.6)['cards'] == []
    finally:
        store.close(wait=True)


def test_crops_are_bounded_raw_images_and_old_epoch_is_invalidated():
    from app.cv.recognition_cards import RecognitionCards
    store = RecognitionCards('main', 'front')
    frame = np.full((140, 120, 3), 100, np.uint8)
    try:
        store.observe(frame, group(), 1, 0)
        for future in list(store._pending.values()): future.result(timeout=3)
        card = store.snapshot()['cards'][0]
        body = store.image(card['images']['person']['id'])
        decoded = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None and abs(float(decoded.mean()) - 100) < 2
        assert max(decoded.shape[:2]) <= 360
        store.reset(1)
        assert store.image(card['images']['person']['id']) is None
    finally:
        store.close(wait=True)


def test_unassociated_plate_is_preview_only_without_ocr_attempt(monkeypatch):
    from app.tests.test_dot_R import _build_pipeline_with_mocks
    from app.cv.detector import Detection as D
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    from app.cv.plate_voter import PlateVoter
    p._plate_voter = PlateVoter(100, 2.5, 2, .8)
    people = [D('person', .9, (10, 10, 90, 110), 42)]
    plate = D('plate', .9, (30, 85, 70, 105), 1)
    groups, _ = p._group_by_person(people, [], [plate], [])
    assert groups[0].get('_preview_plate') is plate
    done = Future()
    done.set_result({'full': '89F165123', 'confidence': .9, 'track_id': -43, 'frame_seq': 7, 'source_epoch': 0})
    p._ocr_pending[-43] = done
    p._ocr_submit_meta[-43] = {'ts': time.time(), 'frame_seq': 7, 'source_epoch': 0,
                              'plate_bbox': plate.bbox, 'plate_class': 'plate', 'plate_confidence': .9}
    original = p._ocr_pool; p._ocr_pool = MagicMock()
    try:
        p._observe_group(np.zeros((140, 120, 3), np.uint8), groups[0])
        assert groups[0].get('_preview_plate_result') is None
        assert groups[0]['_plate_result'] is None
        assert not groups[0]['plate_dets'] and groups[0]['vehicle_type'] is None
        assert p._ocr_pool.submit.call_count == 0
    finally:
        original.shutdown(wait=True)


def test_ambiguous_plate_is_not_preview_assigned():
    from app.cv.pipeline import VideoPipeline
    from app.cv.detector import Detection as D
    p = VideoPipeline.__new__(VideoPipeline)
    people = [D('person', .9, (0, 0, 80, 120), 1), D('person', .9, (40, 0, 120, 120), 2)]
    plate = D('plate', .9, (50, 85, 70, 105))
    groups, _ = p._group_by_person(people, [], [plate], [])
    assert all(g.get('_preview_plate') is None for g in groups)


def test_card_endpoints_are_read_only_and_images_require_role(client, monkeypatch):
    from app.tests.conftest import auth_headers
    import app.cv.pipeline as module
    store = SimpleNamespace(snapshot=lambda: {'cards': [], 'run_id': 'fixture', 'source_epoch': 0},
                            image=lambda image_id: b'jpeg' if image_id == 'known' else None)
    fake = SimpleNamespace(_recognition_cards=store, _running=True, recognition_models=lambda: {})
    monkeypatch.setattr(module, '_pipelines', {'main': fake})
    monkeypatch.setattr(module, 'VideoPipeline', MagicMock(side_effect=AssertionError('must not initialize')))
    h = auth_headers(client)
    assert client.get('/guard/recognition_cards?gate=main', headers=h).status_code == 200
    r = client.get('/guard/recognition_image/known?gate=main', headers=h)
    assert r.status_code == 200 and r.content == b'jpeg' and r.headers['content-type'] == 'image/jpeg'
    assert client.get('/guard/recognition_image/unknown?gate=main', headers=h).status_code == 404
    client.cookies.clear()
    assert client.get('/guard/recognition_image/known?gate=main').status_code == 401
    assert client.get('/guard/recognition_cards', headers=auth_headers(client, 'teacher')).status_code == 403
    assert client.get('/guard/recognition_cards?gate=missing', headers=h).status_code == 404


def test_plate_region_scan_uses_raw_crop_maps_coordinates_and_is_rate_limited(monkeypatch):
    from app.cv.pipeline import VideoPipeline
    from app.cv.detector import Detection as D
    p = VideoPipeline.__new__(VideoPipeline)
    p._plate_detector = MagicMock()
    p._plate_detector.detect.return_value = [D('plate', .9, (5, 10, 35, 40))]
    vehicle = D('motorcycle', .9, (20, 40, 100, 120), 7)
    frame = np.full((140, 120, 3), 100, np.uint8)
    monkeypatch.setattr('app.cv.pipeline.time.monotonic', lambda: 10)
    result = p._scan_plate_region(frame, [vehicle], [])
    assert result[0].bbox == (17, 42, 47, 72)
    assert result[0].track_id is None
    assert abs(float(p._plate_detector.detect.call_args.args[0].mean())-100) < .01
    assert p._scan_plate_region(frame, [vehicle], []) == []
    assert p._plate_detector.detect.call_count == 1


def test_card_buffer_is_bounded_and_expired_observations_are_not_confirmed():
    from app.cv.recognition_cards import RecognitionCards
    store = RecognitionCards('main', 'front')
    frame = np.zeros((140, 120, 3), np.uint8)
    try:
        for seq, ts in [(1, 10), (2, 10.2), (3, 10.4), (4, 12.1)]:
            store.observe(frame, group(), seq, 0, now=ts)
        assert store.snapshot(now=12.1)['cards'][0]['helmet']['state'] == 'checking'
        for track in range(30):
            store.observe(frame, group(track), track+10, 0, now=13)
        assert len(store.snapshot(now=13)['cards']) == 24
        assert len(store._pending) <= 2
        assert len(store._images) <= store.MAX_IMAGES
        assert store.snapshot(now=29)['cards'] == []
    finally:
        store.close(wait=True)


def test_partial_ocr_is_visible_but_never_confirmed_or_used_for_matching():
    from app.cv.plate_voter import PlateVoter
    from app.cv.detector import Detection
    from app.cv.recognition_cards import RecognitionCards
    voter = PlateVoter(100, 2.5, 2, .8)
    plate = Detection('plate', .9, (30, 85, 70, 105), 42)
    for seq in (1, 2, 3):
        read = voter.add_result(plate, {'full':'63035', 'confidence':.9, 'frame_seq':seq})
    assert read.text == '' and not read.is_confident and read.raw_text == '63035'
    store = RecognitionCards('main', 'front')
    g = group(); g['_preview_plate'] = plate; g['_preview_plate_result'] = read
    try:
        store.observe(np.zeros((140, 120, 3), np.uint8), g, 4, 0)
        result = store.snapshot()['cards'][0]['plate']
        assert result['state'] == 'partial' and result['text'] == '63035'
        assert result['association'] == 'unverified'
    finally:
        store.close(wait=True)


def test_failed_crop_encode_does_not_publish_fake_image_urls(monkeypatch):
    from app.cv.recognition_cards import RecognitionCards
    store = RecognitionCards('main', 'front')
    monkeypatch.setattr(cv2, 'imencode', lambda *args: (False, None))
    try:
        store.observe(np.zeros((140, 120, 3), np.uint8), group(), 1, 0)
        for future in list(store._pending.values()): future.result(timeout=3)
        card = store.snapshot()['cards'][0]
        assert card['images'] == {} and card['images_state'] == 'error'
    finally:
        store.close(wait=True)


def test_untracked_previews_do_not_flood_cards_or_merge_two_people():
    from app.cv.recognition_cards import RecognitionCards
    from app.cv.detector import Detection
    store = RecognitionCards('main', 'front')
    frame = np.zeros((140, 120, 3), np.uint8)
    try:
        for seq in range(1, 8):
            store.observe(frame, group(track=None), seq, 0, now=10+seq*.2)
        assert len(store.snapshot(now=11.4)['cards']) == 1
        other = group(track=None)
        other['_person'] = Detection('person', .9, (90, 10, 120, 110))
        store.observe(frame, other, 7, 0, now=11.4)
        cards = store.snapshot(now=11.4)['cards']
        assert len(cards) == 2 and all(c['person']['state'] == 'review' for c in cards)
        assert len({c['card_id'] for c in cards}) == 2
    finally:
        store.close(wait=True)
