"""Time pairing of a front-camera event with the rear camera's plate."""
import json
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.cv import gate_pairing as gp


@pytest.fixture(autouse=True)
def clean():
    gp.reset()
    yield
    gp.reset()


def test_simultaneous_rear_plate_pairs_and_own_gate_is_ignored():
    gp.record_plate('secondary', '89F123792', .9, ts=100)
    gp.record_plate('main', '30A12345', .9, ts=100)
    assert gp.pair(101, 'main')[::2] == ('89F123792', 'paired')


def test_misreads_of_one_plate_still_pair_to_the_most_seen_spelling():
    for ts in (100, 100.5, 101):
        gp.record_plate('secondary', '89F123792', .9, ts=ts)
    gp.record_plate('secondary', '89F123192', .8, ts=101.2)
    assert gp.pair(100.8, 'main')[0] == '89F123792'


def test_two_vehicles_in_window_never_guess():
    gp.record_plate('secondary', '89F123792', .9, ts=100)
    gp.record_plate('secondary', '30A12345', .9, ts=101)
    assert gp.pair(100.5, 'main') == (None, 0.0, 'ambiguous')


def test_outside_window_is_unpaired():
    gp.record_plate('secondary', '89F123792', .9, ts=100)
    assert gp.pair(100 + gp.WINDOW_SEC + 1, 'main')[2] == 'none'


def test_plate_arriving_after_the_event_is_delivered_once():
    got = []
    gp.wait_for_plate(200, 'main', lambda *args: got.append(args))
    gp.record_plate('secondary', '89F123792', .9, ts=202)
    gp.record_plate('secondary', '89F123792', .9, ts=203)
    assert got == [('89F123792', .9, 'paired')]


def test_waiting_expires_after_window():
    got = []
    gp.wait_for_plate(200, 'main', lambda *args: got.append(args))
    gp.record_plate('secondary', '89F123792', .9, ts=200 + gp.WINDOW_SEC + 5)
    assert got == []


def _front_pipeline(monkeypatch):
    from app.cv.pipeline import VideoPipeline
    import app.cv.pipeline as module
    p = VideoPipeline.__new__(VideoPipeline)
    p.gate_id, p.role, p._source_epoch = 'main', 'front', 0
    p._persist_violation = MagicMock(return_value=True)
    monkeypatch.setattr(module, 'get_vehicle_by_plate', lambda plate: None)
    return p


def _frozen(ts):
    return {'event_id': 'e1', 'vehicle_track_id': 7, 'source_epoch': 0, 'camera_id': 'main',
            'frame_seq': 5, 'observed_at': '2026-10-04T00:00:00+00:00', 'observed_ts': ts,
            'issues': [{'code': 'RIDING_THROUGH_GATE', 'status': 'confirmed'}], 'plate': None,
            'future': None, 'deadline': 0, 'helmet_status': 'unknown', 'posture_status': 'riding'}


def test_front_event_takes_the_rear_plate_seen_at_the_same_time(monkeypatch):
    p = _front_pipeline(monkeypatch)
    gp.record_plate('secondary', '89F123792', .93, ts=500)
    frame = np.zeros((10, 10, 3), np.uint8)
    p._finish_crossing_event(_frozen(500.4), frame, frame, [])
    args = p._persist_violation.call_args
    issues = {i['code']: i['status'] for i in json.loads(args.args[13])}
    assert args.args[3] == '89F123792'
    assert issues == {'RIDING_THROUGH_GATE': 'confirmed', 'PLATE_NOT_REGISTERED': 'confirmed',
                      'PLATE_FROM_REAR_CAMERA': 'info'}
    assert args.kwargs['plate_status'] == 'CONFIRMED'


def test_rear_plate_arriving_late_updates_the_saved_event(monkeypatch):
    import app.db as db
    p = _front_pipeline(monkeypatch)
    p._alert_queue = queue.Queue()
    p._crossing_event_to_db_id = {'e1': 42}
    saved = {}
    monkeypatch.setattr(db, 'update_violation_plate',
                        lambda *a: saved.setdefault('args', a) is not None)
    monkeypatch.setattr(db, 'get_connection', lambda: SimpleNamespace(
        execute=lambda *a: SimpleNamespace(fetchone=lambda: {'issues_json': json.dumps(
            [{'code': 'PLATE_UNREADABLE', 'status': 'needs_review'}])}),
        close=lambda: None))
    frame = np.zeros((10, 10, 3), np.uint8)
    p._finish_crossing_event(_frozen(700), frame, frame, [])
    assert p._persist_violation.call_args.args[3] == ''
    gp.record_plate('secondary', '89F123792', .9, ts=702)
    vid, plate, matched, conf, issues = saved['args']
    assert (vid, plate, matched) == (42, '89F123792', None)
    assert [i['code'] for i in json.loads(issues)] == ['PLATE_FROM_REAR_CAMERA', 'PLATE_NOT_REGISTERED']
    notice = p._alert_queue.get_nowait()
    assert notice['type'] == 'plate_paired' and notice['plate_read'] == '89F123792'
