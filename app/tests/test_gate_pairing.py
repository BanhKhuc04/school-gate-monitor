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


def test_shared_line_takes_the_plate_that_crossed_at_the_same_moment():
    """Once the rear camera reports line crossings, a plate merely seen in the
    8 s window (another bike parked nearby) no longer competes."""
    gp.record_plate('secondary', '30A12345', .9, ts=97)                       # seen, never crossed
    gp.record_plate('secondary', '89F123792', .9, ts=100.4, crossing_ts=100.4)
    assert gp.pair_detail(100, 'main') == ('89F123792', .9, 'paired', 'line')


def test_shared_line_plate_crossing_seconds_later_is_another_vehicle():
    gp.record_plate('secondary', '89F123792', .9, ts=106, crossing_ts=106)
    assert gp.pair_detail(100, 'main')[2:] == ('none', 'line')


def test_two_plates_crossing_together_are_never_guessed():
    gp.record_plate('secondary', '89F123792', .9, ts=100.2, crossing_ts=100.2)
    gp.record_plate('secondary', '30A12345', .9, ts=100.9, crossing_ts=100.9)
    assert gp.pair_detail(100, 'main')[2] == 'ambiguous'


def test_camera_delay_is_learned_from_unique_pairs():
    """Rear stream 3.5 s behind: outside the 2.5 s window until learned."""
    for k in range(gp.MIN_OFFSET_SAMPLES):
        t = 1000 + 30 * k
        gp.record_event('main', t)
        gp.record_plate('secondary', f'89F12{k:04d}', .9, ts=t + 3.5, crossing_ts=t + 3.5)
    assert abs(gp.offset() - 3.5) < 1e-9
    gp.record_plate('secondary', '29B12345', .9, ts=2003.6, crossing_ts=2003.6)
    assert gp.pair_detail(2000, 'main')[::2] == ('29B12345', 'paired')
    assert gp.wait_budget() >= 3.5 + gp.LINE_WINDOW_SEC - 1e-9


def test_rear_pipeline_reports_the_wall_time_a_plate_crosses_its_line(monkeypatch):
    from app.cv import pipeline as module
    from app.cv.crossing import CrossingDetector
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p._crossing_detector = CrossingDetector([0, .5, 1, .5], edge_margin=.01, min_frames_per_side=2,
                                            min_frames_exit_side=2)
    clock = {'t': 0.0}
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock['t'])
    monkeypatch.setattr(module.time, 'time', lambda: 5000 + clock['t'])
    for k, y in enumerate((100, 140, 180, 260, 300, 340)):  # plate box moving down past y=200
        clock['t'] = k * .1
        p._frame_seq = k
        p._update_plate_crossing(7, (100, y - 30, 160, y), 400, 400)
    first = p._plate_crossed_wall[7]
    assert 5000.3 <= first <= 5000.5  # right after the plate passed the line
    clock['t'] = .6; p._frame_seq = 6
    p._update_plate_crossing(7, (100, 350, 160, 380), 400, 400)
    assert p._plate_crossed_wall[7] == first  # latched: one crossing per pass


def test_violation_waits_for_the_rear_plate_crossing_and_speaks_once_with_it(monkeypatch):
    """The rear plate crosses 1 s after the front event: the alert waits and
    carries the plate instead of going out plateless."""
    import threading
    from app.cv import pipeline as module
    from app.cv.plate_voter import PlateReadResult
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p.role, p.gate_id, p._source_epoch = 'front', 'main', 0
    saved = {}
    p._persist_violation = lambda *a, **k: saved.update(plate=a[3], issues=json.loads(a[13])) or True
    monkeypatch.setattr(module, 'get_vehicle_by_plate', lambda plate: {'plate_number': plate})
    now = module.time.time()
    threading.Timer(.4, lambda: gp.record_plate('secondary', '89F123792', .9, crossing_ts=now + .4)).start()
    frozen = {'event_id': 'e1', 'vehicle_track_id': 7, 'source_epoch': 0, 'camera_id': 'main', 'frame_seq': 1,
              'observed_at': 'x', 'observed_ts': now, 'issues': [{'code': 'NO_HELMET', 'status': 'confirmed'}],
              'plate': PlateReadResult(), 'future': None, 'deadline': 0, 'helmet_status': 'no_helmet',
              'posture_status': 'riding'}
    assert p._finish_crossing_event(frozen, np.zeros((4, 4, 3), np.uint8), None, [])
    assert saved['plate'] == '89F123792'
    assert {'code': 'PLATE_FROM_REAR_CAMERA', 'status': 'info', 'method': 'line'} in saved['issues']


def test_rear_plate_notice_only_after_it_crossed_the_line(monkeypatch):
    """A parked or reversing bike in the rear view must not pop a plate notice."""
    import queue as _q
    from app.cv import pipeline as module
    from app.cv.plate_voter import PlateReadResult
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p.role, p.gate_id, p._source_epoch, p._frame_seq = 'rear', 'secondary', 0, 1
    p._alert_queue = _q.Queue()
    monkeypatch.setattr(p, '_consensus_result', lambda tid, single: PlateReadResult(
        text='89F123792', confidence=.9, sample_count=2, is_confident=True), raising=False)
    monkeypatch.setattr(module, 'get_vehicle_by_plate', lambda plate: None)
    p._announce_plate(5, None)
    assert p._alert_queue.empty()
    p._plate_crossed_wall = {5: 123.0}
    p._announce_plate(5, None)
    assert p._alert_queue.get_nowait()['plate_read'] == '89F123792'
