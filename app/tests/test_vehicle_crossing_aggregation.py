import queue
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock
import numpy as np
import pytest

from app.cv.pipeline import VideoPipeline
from app.cv.best_plate import BestPlateStore
from app.cv.evidence import EvidenceLedger
from app.cv.detector import Detection


@pytest.fixture
def pipeline():
    p = VideoPipeline.__new__(VideoPipeline)
    p.gate_id='test'; p.camera_id='front'; p._source_epoch=0; p._frame_seq=0
    p._encounter_session_id='test-session'; p._best_plates=BestPlateStore()
    p._crossing_sealed={}; p._crossing_jobs={}; p._crossing_detector=SimpleNamespace(_tracks={})
    p._evidence_ledger=EvidenceLedger(); p._clip_buffer=[]
    p._crossing_pool=ThreadPoolExecutor(1); p._ocr_pool=ThreadPoolExecutor(1)
    p._persist_violation=MagicMock(return_value=True); p._diagnostic=MagicMock()
    p._io_health={'errors':0}; p._alert_queue=queue.Queue()
    yield p
    p._crossing_pool.shutdown(wait=True); p._ocr_pool.shutdown(wait=True)


def group(person=9, vehicle=7, posture='riding', helmet='Without Helmet'):
    return {'track_id':person,'vehicle_track_id':vehicle,'posture_status':posture,'vehicle_type':'motorcycle',
            '_person':Detection('person',.9,(30,10,80,95),person),
            '_vehicle':Detection('motorcycle',.9,(10,50,110,100),vehicle),
            'helmet_dets':[Detection(helmet,.9,(40,10,60,30))], 'plate_dets':[]}


def feed(p, groups, monkeypatch):
    import app.cv.pipeline as module
    clock=[1000.]
    monkeypatch.setattr(module.time, 'time', lambda: clock[0])
    frame=np.full((120,160,3),120,np.uint8)
    for seq in range(1,5):
        clock[0]=1000+seq*.2; p._frame_seq=seq
        p._process_vehicle_crossings(frame,groups)
    return frame


def test_only_crossing_seals_one_vehicle_event_for_two_people(pipeline,monkeypatch):
    p=pipeline; groups=[group(), group(person=10)]
    frame=feed(p,groups,monkeypatch)
    p._persist_violation.assert_not_called()
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._frame_seq=5; p._process_vehicle_crossings(frame,groups)
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    assert p._persist_violation.call_count==1
    args, kwargs=p._persist_violation.call_args
    assert kwargs['track_id']==7
    import json
    issues=json.loads(args[13])
    assert {i['code'] for i in issues}=={'NO_HELMET','RIDING_THROUGH_GATE','PLATE_UNREADABLE'}
    p._frame_seq=6; p._process_vehicle_crossings(frame,groups)
    assert p._persist_violation.call_count==1


def test_bike_labelled_bicycle_still_raises_riding_event(pipeline,monkeypatch):
    import json
    p=pipeline; g=group(); g['vehicle_type']='bicycle'
    frame=feed(p,[g],monkeypatch)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._frame_seq=5; p._process_vehicle_crossings(frame,[g])
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    assert 'RIDING_THROUGH_GATE' in {i['code'] for i in json.loads(p._persist_violation.call_args.args[13])}


def test_front_camera_walked_bike_with_unread_plate_raises_nothing(pipeline,monkeypatch):
    p=pipeline; p.role='front'; groups=[group(posture='unknown')]
    frame=feed(p,groups,monkeypatch)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._process_vehicle_crossings(frame,groups)
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    p._persist_violation.assert_not_called()


def test_missing_gate_line_falls_back_to_default_so_crossings_happen():
    from app.cv.pipeline import _DEFAULT_GATE_LINE
    detector=VideoPipeline._make_crossing_detector(None)
    assert detector.is_configured and detector.gate_line==list(_DEFAULT_GATE_LINE)


def test_unknown_crossing_never_riding_and_partial_never_lookup(pipeline,monkeypatch):
    import app.cv.pipeline as module
    lookup=MagicMock(); monkeypatch.setattr(module,'get_vehicle_by_plate',lookup)
    p=pipeline; groups=[group(posture='unknown')]
    frame=feed(p,groups,monkeypatch)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._process_vehicle_crossings(frame,groups)
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    lookup.assert_not_called()
    import json
    assert [i['code'] for i in json.loads(p._persist_violation.call_args.args[13])]==['PLATE_UNREADABLE']


def test_slow_ocr_never_blocks_capture_thread(pipeline,monkeypatch):
    import time
    p=pipeline; frame=feed(p,[group()],monkeypatch)
    slow=Future(); monkeypatch.setattr(p._best_plates,'future',lambda _:slow)
    monkeypatch.setattr(p._best_plates,'pending',lambda _:True)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    start=time.perf_counter(); p._process_vehicle_crossings(frame,[group()])
    assert time.perf_counter()-start<.05
    for f in p._crossing_jobs.values():
        f.result(timeout=1)
    assert time.perf_counter()-start<.5
    assert p._persist_violation.call_count==1


def test_actual_observation_crops_source_pixels_before_display_resize(pipeline):
    p=pipeline; p._plate_approach={}; p._ocr_health={'completed':0,'submitted':0,'errors':0,'empty':0}
    p._crossing_detector=None; p._frame_seq=1
    p._original_source_frame=np.arange(200*300*3,dtype=np.uint8).reshape(200,300,3)
    g=group();g['plate_dets']=[Detection('plate',.9,(20,30,60,70))]
    p._observe_best_plate(np.zeros((100,100,3),np.uint8),g)
    best=p._best_plates.candidate(7)
    # Source box (60,60)-(180,140), plus the OCR margin on every side.
    from app.config import PLATE_BEST_CROP_PAD as pad
    x1,y1,x2,y2=int(60-120*pad),int(60-80*pad),int(180+120*pad),int(140+80*pad)
    assert best.crop.shape==(y2-y1,x2-x1,3)
    assert np.array_equal(best.crop,p._original_source_frame[y1:y2,x1:x2])
    assert p._best_plates.debug(7)['attempts']==0


def test_partial_result_at_crossing_does_not_lookup_database(pipeline,monkeypatch):
    import app.cv.pipeline as module
    from app.cv.plate_voter import PlateReadResult
    lookup=MagicMock();monkeypatch.setattr(module,'get_vehicle_by_plate',lookup)
    p=pipeline; frame=feed(p,[group()],monkeypatch)
    done=Future();done.set_result({'full':'23792','confidence':.99,'source_epoch':0})
    monkeypatch.setattr(p._best_plates,'future',lambda _:done)
    monkeypatch.setattr(p._best_plates,'result',lambda _:PlateReadResult(pending=True))
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._process_vehicle_crossings(frame,[group()])
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    lookup.assert_not_called()
    assert p._persist_violation.call_args.args[3]==''


def test_expired_sealed_id_still_cannot_reseal_same_crossing(pipeline,monkeypatch):
    p=pipeline;frame=feed(p,[group()],monkeypatch)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._process_vehicle_crossings(frame,[group()])
    for f in p._crossing_jobs.values():
        f.result(timeout=2)
    p._crossing_sealed.clear()
    p._process_vehicle_crossings(frame,[group()])
    assert p._persist_violation.call_count==1


@pytest.mark.parametrize('metadata', [
    {'completed_monotonic': 21.},
    {'track_id': 99},
    {'frame_seq': 99},
])
def test_late_or_wrong_crop_result_cannot_enter_frozen_alert(pipeline,monkeypatch,metadata):
    import app.cv.pipeline as module
    lookup=MagicMock();monkeypatch.setattr(module,'get_vehicle_by_plate',lookup)
    done=Future()
    done.set_result({'full':'89F123792','confidence':.99,'source_epoch':0,
                     'track_id':7,'frame_seq':4,'completed_monotonic':19.,**metadata})
    frozen={'plate':None,'future':done,'deadline':20.,'plate_frame_id':4,
            'vehicle_track_id':7,'source_epoch':0,'camera_id':'front','frame_seq':5,
            'event_id':'frozen','issues':[{'code':'NO_HELMET','status':'confirmed'}],
            'helmet_status':'no_helmet','posture_status':'riding','observed_at':'2026-10-01T00:00:00Z'}
    frame=np.zeros((120,160,3),np.uint8)
    assert pipeline._finish_crossing_event(frozen,frame,frame,[])
    lookup.assert_not_called()
    assert pipeline._persist_violation.call_args.args[3]==''


def test_two_line_recognition_uses_one_crop_two_engine_reads(monkeypatch):
    import app.cv.ocr as module
    calls=[]
    class Reader:
        def readtext(self,image,**_):
            calls.append(image.copy())
            text='89-F1' if len(calls)==1 else '237.92'
            return [([[0,0],[60,0],[60,20],[0,20]],text,.99)]
    monkeypatch.setattr(module,'_get_reader',lambda:Reader())
    crop=np.zeros((80,100,3),np.uint8)
    crop[:40]=60;crop[40:]=180
    raw=module.read_plate_detailed(crop)
    from app.cv.best_plate import resolve_plate
    assert len(calls)==2
    assert raw['top_line']=='89F1' and raw['bottom_line']=='23792'
    assert resolve_plate(raw).text=='89F123792'


def test_existing_rider_count_rule_joins_same_crossing_event(pipeline,monkeypatch):
    import json
    p=pipeline;groups=[group(person=i) for i in (9,10,11)]
    frame=feed(p,groups,monkeypatch)
    p._crossing_detector._tracks[7]=SimpleNamespace(has_crossed=True,crossed_at=5,rearmed=False)
    p._process_vehicle_crossings(frame,groups)
    for future in p._crossing_jobs.values():
        future.result(timeout=2)
    assert p._persist_violation.call_count==1
    issues=json.loads(p._persist_violation.call_args.args[13])
    assert 'TOO_MANY_RIDERS' in {issue['code'] for issue in issues}


def test_plate_announced_once_per_plate_and_only_after_consensus(pipeline):
    import queue as _queue
    from app.cv.plate_voter import PlateReadResult
    p = pipeline
    p._alert_queue = _queue.Queue()
    reads = {}
    p._consensus_result = lambda tid, single: reads.get(tid, PlateReadResult())
    single = PlateReadResult(text='89F123792', confidence=.9, sample_count=1, is_confident=True)
    p._announce_plate(7, single)
    assert p._alert_queue.empty()  # one read is not enough
    reads[7] = reads[8] = PlateReadResult(text='89F123792', confidence=.9, sample_count=2, is_confident=True)
    p._announce_plate(7, single)
    p._announce_plate(8, single)  # same bike on a plate-only track
    message = p._alert_queue.get_nowait()
    assert message['type'] == 'plate_recognized' and message['plate_read'] == '89F123792'
    assert message['registered'] is False
    assert p._alert_queue.empty()
