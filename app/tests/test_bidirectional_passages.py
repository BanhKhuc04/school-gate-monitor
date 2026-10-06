"""1 người vào + 1 người ra cùng lúc phải được đếm đúng: 1 lượt VÀO, 1 lượt RA.

Vạch ngang y=0.5; ENTER = đi xuống (phía trên -> phía dưới), EXIT = đi lên.
"""
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from app.cv.crossing import CrossingDetector
from app.cv.detector import Detection
from app.cv.gate_passage import PassageLedger


def _detector(**overrides):
    kwargs = dict(gate_line=[0.1, 0.5, 0.9, 0.5], edge_margin=0.02, min_frames_per_side=3,
                  rearm_distance=0.05, cooldown_sec=2.0, min_frames_exit_side=1,
                  max_transition_sec=5.0, allowed_direction='enter', bounce_band=0.06)
    kwargs.update(overrides)
    return CrossingDetector(**kwargs)


def _run(det, tracks, start=1000.0, dt=0.1):
    """tracks: {track_id: [(x, y), ...]} — cùng số frame, None = không thấy."""
    n = max(len(v) for v in tracks.values())
    crossed = []
    for i in range(n):
        for tid, path in tracks.items():
            if i < len(path) and path[i] is not None:
                _, c = det.update(tid, path[i][0], path[i][1], start + i * dt, frame_seq=i)
                if c:
                    crossed.append(tid)
    return crossed, det.drain_passages()


def _directions(passages):
    return sorted(p['direction'] for p in passages)


def _line(y0, step, n, x=0.5):
    return [(x, round(y0 + step * i, 4)) for i in range(n)]


class TestDetectorBothDirections:
    def test_exit_is_recorded_but_never_seals_a_violation(self):
        det = _detector()
        crossed, passages = _run(det, {1: _line(0.8, -0.05, 10)})
        assert crossed == []                       # chiều RA không tạo vi phạm/cảnh báo
        assert det._tracks[1].has_crossed is False
        assert [(p['direction'], p['allowed']) for p in passages] == [('exit', False)]

    def test_one_in_one_out_at_the_same_time(self):
        det = _detector()
        crossed, passages = _run(det, {
            1: _line(0.2, 0.05, 12, x=0.3),        # vào
            2: _line(0.8, -0.05, 12, x=0.7),       # ra, cùng lúc, làn khác
        })
        assert crossed == [1]
        assert _directions(passages) == ['enter', 'exit']
        assert {p['track_id']: p['direction'] for p in passages} == {1: 'enter', 2: 'exit'}

    def test_exit_then_immediate_turn_back_is_not_a_fake_enter(self):
        """Track vừa chốt lượt RA rồi quay đầu (hoặc bị tráo sang người đi
        vào): không được sinh lượt VÀO thứ 2 và không được seal vi phạm, kể
        cả sau khi hết cooldown."""
        det = _detector()
        path = _line(0.70, -0.05, 6) + _line(0.50, 0.05, 30)     # ra tới 0.45 rồi quay xuống tận đáy
        crossed, passages = _run(det, {1: path}, dt=0.2)
        assert crossed == []
        assert det._tracks[1].has_crossed is False
        assert _directions(passages) == ['exit']

    def test_ids_swap_exactly_at_the_meeting_point_still_counts_one_each_way(self):
        """2 người lướt qua nhau đúng tại vạch, tracker tráo ID: mỗi track
        'bật lại' về phía cũ. Không khôi phục thì mất cả 2 lượt."""
        a = _line(0.30, 0.04, 11)                  # A đi xuống: 0.30 ... 0.70
        b = _line(0.70, -0.04, 11)                 # B đi lên:   0.70 ... 0.30
        det = _detector()
        _, passages = _run(det, {1: a[:5] + b[5:], 2: b[:5] + a[5:]})
        assert _directions(passages) == ['enter', 'exit']
        assert all(p['swap_recovered'] for p in passages)

    def test_ids_swap_just_before_meeting_counts_one_each_way(self):
        a = _line(0.30, 0.04, 11)
        b = _line(0.70, -0.04, 11)
        det = _detector()
        _, passages = _run(det, {1: a[:4] + b[4:], 2: b[:4] + a[4:]})
        assert _directions(passages) == ['enter', 'exit']

    def test_single_person_turning_back_is_not_a_passage(self):
        det = _detector()
        path = _line(0.30, 0.04, 5) + _line(0.42, -0.04, 5)
        _, passages = _run(det, {1: path})
        assert passages == []

    def test_two_people_turning_back_far_apart_are_not_paired(self):
        det = _detector()
        _, passages = _run(det, {
            1: _line(0.30, 0.04, 5, x=0.15) + _line(0.42, -0.04, 5, x=0.15),
            2: _line(0.70, -0.04, 5, x=0.85) + _line(0.58, 0.04, 5, x=0.85),
        })
        assert passages == []

    def test_a_normal_crossing_is_not_also_a_bounce(self):
        det = _detector()
        _, passages = _run(det, {1: _line(0.30, 0.04, 12)})
        assert [(p['direction'], p['swap_recovered']) for p in passages] == [('enter', False)]


class TestPassageLedger:
    def test_vehicle_counts_every_person_on_it(self):
        ledger = PassageLedger()
        ledger.record_vehicle(7, 'enter', 10.0, person_track_ids=[1, 2])
        assert ledger.snapshot()['enter'] == {'pedestrian': 0, 'vehicle': 1, 'persons': 2}

    def test_pedestrian_and_bike_opposite_directions(self):
        ledger = PassageLedger(hold_sec=1.0)
        ledger.record_vehicle(7, 'enter', 10.0, person_track_ids=[1])
        ledger.record_pedestrian(5, 'exit', 10.0)
        ledger.flush(11.5)
        snap = ledger.snapshot()
        assert snap['enter']['persons'] == 1 and snap['exit']['persons'] == 1
        assert snap['exit']['pedestrian'] == 1

    def test_rider_seen_briefly_as_pedestrian_is_counted_once(self):
        ledger = PassageLedger(hold_sec=1.5)
        ledger.record_pedestrian(1, 'enter', 10.0)          # chưa ghép kịp với xe
        ledger.record_vehicle(7, 'enter', 10.4, person_track_ids=[1])
        ledger.record_pedestrian(1, 'enter', 10.6)          # đã được tính trên xe
        ledger.flush(20.0)
        assert ledger.snapshot()['enter'] == {'pedestrian': 0, 'vehicle': 1, 'persons': 1}

    def test_pedestrian_is_held_before_commit(self):
        ledger = PassageLedger(hold_sec=1.5)
        ledger.record_pedestrian(3, 'enter', 10.0)
        assert ledger.flush(10.5) == []
        assert [e['direction'] for e in ledger.flush(11.6)] == ['enter']

    def test_swap_recovered_needs_review(self):
        ledger = PassageLedger(hold_sec=0)
        ledger.record_pedestrian(3, 'exit', 10.0, swap_recovered=True)
        assert ledger.flush(10.0)[0]['status'] == 'review'


class _Pool:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append(args)
        f = Future()
        f.set_result(None)
        return f


@pytest.fixture
def pipeline(monkeypatch):
    from app.cv import pipeline as module
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p.gate_id, p.camera_id, p._frame_seq = 'test', 'front', 0
    p._crossing_detector = _detector(gate_line=[0.0, 0.5, 1.0, 0.5])
    p._passage_ledger = PassageLedger(hold_sec=0.0)
    p._io_pool = _Pool()
    clock = [1000.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    return p, clock


def _person(tid, y, x=50):
    return Detection('person', .9, (x - 10, y - 60, x + 10, y), tid)


def _bike(tid, y, x=150):
    return Detection('motorcycle', .9, (x - 20, y - 40, x + 20, y), tid)


def test_pipeline_bike_entering_while_pedestrian_exits(pipeline):
    p, clock = pipeline
    W = H = 200
    for i in range(12):
        clock[0] = 1000 + i * 0.1
        p._frame_seq = i
        bike_y, walk_y = 40 + 12 * i, 160 - 12 * i
        bike = _bike(7, bike_y)
        groups = [
            {'track_id': 1, 'vehicle_track_id': 7, '_vehicle': bike, '_person': _person(1, bike_y, 150),
             'posture_status': 'riding'},
            {'track_id': 2, 'vehicle_track_id': 7, '_vehicle': bike, '_person': _person(2, bike_y, 160),
             'posture_status': 'riding'},
            {'track_id': 3, 'vehicle_track_id': None, '_vehicle': None, '_person': _person(3, walk_y),
             'posture_status': 'walking'},
        ]
        for g in groups:
            p._update_crossing(g, W, H)
        p._update_gate_passages(groups, W, H)
    snap = p._passage_ledger.snapshot()
    assert snap['enter'] == {'pedestrian': 0, 'vehicle': 1, 'persons': 2}
    assert snap['exit'] == {'pedestrian': 1, 'vehicle': 0, 'persons': 1}
    saved = sorted((c[3], c[4], c[5]) for c in p._io_pool.calls)
    assert saved == [('enter', 'vehicle', 2), ('exit', 'pedestrian', 1)]


def test_passage_summary_round_trip():
    from app.db import init_db, add_gate_passage, get_gate_passage_summary
    init_db()
    add_gate_passage('pt-gate', 'front', '2026-10-06 01:00:00', 'enter', 'vehicle', 2, 'vehicle:7')
    add_gate_passage('pt-gate', 'front', '2026-10-06 01:00:01', 'exit', 'pedestrian', 1, 'pedestrian:3', 'review')
    out = get_gate_passage_summary('2026-10-06 00:00:00', '2026-10-07 00:00:00', 'pt-gate')
    assert out['enter'] == {'pedestrian': 0, 'vehicle': 1, 'persons': 2, 'review': 0}
    assert out['exit'] == {'pedestrian': 1, 'vehicle': 0, 'persons': 1, 'review': 1}
