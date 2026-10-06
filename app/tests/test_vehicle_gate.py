"""Real pipeline decision tests: stable tracks, separate issues and safe evidence."""
import concurrent.futures
import json
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock
import numpy as np
import pytest
from app.cv.evidence import EvidenceLedger
from app.cv.plate_voter import PlateReadResult


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    import app.cv.pipeline as module
    p = module.VideoPipeline.__new__(module.VideoPipeline)
    p.gate_id = 'main'
    p.camera_id = 'front'
    p._source_epoch = 0
    p._frame_seq = 0
    p._last_log_time = {}
    p._alert_queue = queue.Queue()
    p._clip_buffer = []
    p._plate_attempts = p._plate_successes = 0
    p._evidence_ledger = EvidenceLedger()
    p._event_manager = None
    p._read_plate_voted = MagicMock(return_value=PlateReadResult(pending=True))
    monkeypatch.setattr(module, 'SNAPSHOTS_DIR', str(tmp_path))
    monkeypatch.setattr(module.cv2, 'imwrite', lambda path, frame: ( __import__('pathlib').Path(path).write_bytes(b'fixture') or True))
    p.db_insert = MagicMock(return_value=1)
    monkeypatch.setattr(module, 'add_violation_event', p.db_insert)
    monkeypatch.setattr(module, 'get_vehicle_by_plate', lambda plate: None)
    class SyncPool:
        def submit(self, fn, *args, **kwargs):
            f = concurrent.futures.Future()
            try:
                f.set_result(fn(*args, **kwargs))
            except Exception as exc:
                f.set_exception(exc)
            return f
    p._io_pool = SyncPool()
    p._clip_pool = SyncPool()
    p.feed_time = 1000.0
    p.test_monkeypatch = monkeypatch
    return p


def feed(p, count=4, **overrides):
    import app.cv.pipeline as module
    data = dict(helmet_dets=[SimpleNamespace(class_name='Without Helmet')], plate_dets=[],
                posture_status='riding', vehicle_type='motorcycle', track_id=7,
                person_bbox=(5,5,50,60), vehicle_bbox=(2,40,62,62))
    data.update(overrides)
    for _ in range(count):
        p.feed_time += 0.2
        p.test_monkeypatch.setattr(module.time, 'time', lambda: p.feed_time)
        p._frame_seq += 1
        p._process_violations(np.zeros((64,64,3),dtype=np.uint8),frame_seq=p._frame_seq,**data)


@pytest.mark.parametrize('vehicle', [None,'bicycle'])
def test_exempt_vehicles_never_emit(pipeline, vehicle):
    feed(pipeline, vehicle_type=vehicle)
    pipeline.db_insert.assert_not_called()


@pytest.mark.parametrize('posture', ['standing','unknown','walking','pushing','stationary'])
def test_unknown_or_not_riding_never_confirms_helmet_or_crossing(pipeline, posture):
    feed(pipeline, posture_status=posture, crossed_gate=True)
    pipeline.db_insert.assert_not_called()


def test_no_track_never_bypasses_confirmation(pipeline):
    feed(pipeline, track_id=None)
    pipeline.db_insert.assert_not_called()


def test_one_wrong_frame_never_creates_event(pipeline):
    feed(pipeline, count=1)
    feed(pipeline, count=4, helmet_dets=[SimpleNamespace(class_name='With Helmet')])
    pipeline.db_insert.assert_not_called()


def test_empty_plate_is_review_not_missing_plate(pipeline):
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')])
    pipeline.db_insert.assert_not_called()


def test_helmet_confirms_four_real_samples_with_review_plate(pipeline):
    feed(pipeline)
    pipeline.db_insert.assert_called_once()
    row=pipeline.db_insert.call_args.kwargs
    assert row['violation_type']=='NO_HELMET'
    issues=json.loads(row['issues_json'])
    helmet=next(i for i in issues if i['code']=='NO_HELMET')
    assert helmet['sample_count']==4
    assert json.loads(helmet['evidence_ref'])['frame_seqs']==[1,2,3,4]
    assert next(i for i in issues if i['code']=='PLATE_LOW_CONFIDENCE')['status']=='deferred'
    assert row['status']=='pending'  # business workflow stays separate from AI review
    assert row['snapshot_path'] and row['crop_snapshot_path']
    assert pipeline._alert_queue.get_nowait()['evidence_state']=='persisted'


def test_crossing_keeps_helmet_issue(pipeline):
    feed(pipeline, crossed_gate=True)
    row=pipeline.db_insert.call_args.kwargs
    assert row['violation_type']=='MULTIPLE'
    assert {'NO_HELMET','RIDING_THROUGH_GATE'} <= {i['code'] for i in json.loads(row['issues_json'])}


def test_crossing_requires_explicit_crossing(pipeline):
    feed(pipeline, helmet_dets=[SimpleNamespace(class_name='With Helmet')], crossed_gate=False)
    pipeline.db_insert.assert_not_called()


def test_no_helmet_crossing_without_head_box_still_independent(pipeline):
    feed(pipeline, helmet_dets=[], crossed_gate=True)
    row=pipeline.db_insert.call_args.kwargs
    assert row['violation_type']=='RIDING_THROUGH_GATE'
    assert 'NO_HELMET' not in {i['code'] for i in json.loads(row['issues_json'])}


def test_two_unknown_plates_do_not_share_cooldown(pipeline):
    feed(pipeline, track_id=7)
    feed(pipeline, track_id=8)
    assert pipeline.db_insert.call_count==2
    assert len({c.kwargs['encounter_id'] for c in pipeline.db_insert.call_args_list})==2


def test_same_track_does_not_duplicate_during_cooldown(pipeline):
    feed(pipeline)
    feed(pipeline, count=8)
    pipeline.db_insert.assert_called_once()


def test_failed_persist_never_beeps_and_retries_on_fresh_sample(pipeline, monkeypatch):
    import app.cv.pipeline as module
    monkeypatch.setattr(module.cv2,'imwrite',lambda *args:False)
    feed(pipeline)
    assert pipeline._alert_queue.empty()
    assert pipeline.db_insert.call_args.kwargs['evidence_state']=='failed'
    monkeypatch.setattr(module.cv2,'imwrite',lambda path, frame: (__import__('pathlib').Path(path).write_bytes(b'fixture') or True))
    feed(pipeline,count=1)
    assert not pipeline._alert_queue.empty()
    assert pipeline._io_health['errors']==1


def test_weak_ocr_never_calls_roster_lookup(pipeline, monkeypatch):
    import app.cv.pipeline as module
    lookup=MagicMock(); monkeypatch.setattr(module,'get_vehicle_by_plate',lookup)
    pipeline._read_plate_voted.return_value=PlateReadResult(text='59A12345',confidence=.55,sample_count=1,is_confident=False)
    feed(pipeline,plate_dets=[SimpleNamespace()])
    lookup.assert_not_called()
    assert pipeline.db_insert.call_args.kwargs['plate_matched'] is None


def test_strong_ocr_preserves_registered_plate(pipeline, monkeypatch):
    import app.cv.pipeline as module
    monkeypatch.setattr(module,'get_vehicle_by_plate',lambda text:{'plate_number':text})
    pipeline._read_plate_voted.return_value=PlateReadResult(text='59A12345',confidence=.93,sample_count=2,is_confident=True)
    feed(pipeline,plate_dets=[SimpleNamespace()])
    row=pipeline.db_insert.call_args.kwargs
    assert row['plate_matched']=='59A12345'
    assert row['plate_confidence']==pytest.approx(.93)
    assert row['status']=='pending'


def test_clip_failure_does_not_delay_or_cancel_official_alert(pipeline):
    pipeline._clip_buffer=[np.zeros((64,64,3),dtype=np.uint8)]
    pipeline._write_clip=MagicMock(side_effect=OSError('fixture clip failure'))
    feed(pipeline)
    assert not pipeline._alert_queue.empty()
    assert pipeline._io_health['clip_errors']==1


def test_persist_failure_retries_are_bounded(pipeline, monkeypatch):
    import app.cv.pipeline as module
    monkeypatch.setattr(module.cv2,'imwrite',lambda *args:False)
    feed(pipeline,count=20)
    assert pipeline.db_insert.call_count == 3
    assert pipeline._alert_queue.empty()


def test_missing_file_never_returns_evidence_url(pipeline, monkeypatch):
    import app.cv.pipeline as module
    monkeypatch.setattr(module.cv2,'imwrite',lambda *args:True)
    feed(pipeline)
    assert pipeline._alert_queue.empty()
    assert pipeline.db_insert.call_args.kwargs['snapshot_path'] is None


def test_db_failure_never_alerts_and_is_observable(pipeline):
    pipeline.db_insert.side_effect = RuntimeError('fixture database busy')
    feed(pipeline,count=5)
    assert pipeline._alert_queue.empty()
    assert pipeline._io_health['errors'] >= 1


def test_full_realtime_queue_never_blocks_saved_evidence(pipeline):
    pipeline._alert_queue = queue.Queue(maxsize=1)
    pipeline._alert_queue.put({'event_id':'old'})
    feed(pipeline)
    pipeline.db_insert.assert_called_once()
    assert pipeline._alert_queue.get_nowait()['evidence_state']=='persisted'
    assert pipeline._io_health['alerts_dropped']==1
