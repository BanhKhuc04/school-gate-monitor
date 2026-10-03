"""Regression tests for the real recognition path, without RTSP/model loads."""
from concurrent.futures import Future
from unittest.mock import MagicMock

import numpy as np
import pytest


def test_track_survives_resize_roi_and_actual_grouping():
    from app.cv.pipeline import VideoPipeline
    from app.cv.detector import Detection
    from app.cv.roi import filter_by_roi
    people = [Detection('person', .9, (20, 10, 70, 80), track_id=42)]
    vehicles = [Detection('motorcycle', .9, (10, 45, 90, 95), track_id=7)]
    p = VideoPipeline.__new__(VideoPipeline)
    people = filter_by_roi(p._rescale_dets(people, 2, 2), np.array([[0,0],[200,0],[200,200],[0,200]]))
    vehicles = p._rescale_dets(vehicles, 2, 2)
    group = p._group_by_person(people, [], [], vehicles)[0][0]
    assert people[0].track_id == group['track_id'] == 42
    assert group['vehicle_track_id'] == 7


def test_busy_ocr_future_is_not_overwritten(monkeypatch):
    from app.tests.test_dot_R import _build_pipeline_with_mocks, _FakeDet
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    pending = Future()
    p._ocr_pending[42] = pending
    pool = p._ocr_pool
    p._ocr_pool = MagicMock()
    try:
        for seq in range(4):
            p._ocr_submit_with_epoch(np.zeros((100,100,3),dtype=np.uint8), _FakeDet('plate',(10,10,70,50)),42,seq,0)
        p._ocr_pool.submit.assert_not_called()
        assert p._ocr_pending[42] is pending
    finally:
        pool.shutdown(wait=True)


def test_helmet_class_contract_rejects_plate_and_accepts_backup():
    from app.cv.helmet_contract import validate_helmet_classes
    assert not validate_helmet_classes({0:'plate'})
    assert validate_helmet_classes({0:'With Helmet',1:'Without Helmet'})
    assert not validate_helmet_classes({0:'With Helmet'})


def test_handheld_helmet_and_ambiguous_plate_are_not_assigned():
    from app.cv.pipeline import VideoPipeline
    from app.cv.detector import Detection as D
    p = VideoPipeline.__new__(VideoPipeline)
    people=[D('person',.9,(10,10,80,130),track_id=1),D('person',.9,(90,10,160,130),track_id=2)]
    vehicles=[D('motorcycle',.9,(0,60,100,170),track_id=10),D('motorcycle',.9,(80,60,180,170),track_id=20)]
    helmets=[D('With Helmet',.9,(20,90,40,110))]
    plates=[D('plate',.9,(85,135,95,150))]
    groups,_=p._group_by_person(people,helmets,plates,vehicles)
    assert all(not g['helmet_dets'] for g in groups)
    assert all(not g['plate_dets'] for g in groups)
    assert any('plate_association_ambiguous' in g['association_reasons'] for g in groups)


def test_async_votes_require_unique_frames_and_reject_competing_text():
    from app.cv.plate_voter import PlateVoter
    from app.cv.detector import Detection
    v=PlateVoter(60,2.5,2,.55)
    d=Detection('plate',.9,(0,0,100,50),track_id=1)
    def result(text,seq):return {'full':text,'confidence':.9,'frame_seq':seq,'source_epoch':0}
    assert not v.add_result(d,result('89F165123',1)).is_confident
    assert not v.add_result(d,result('89F165123',1)).is_confident
    assert v.add_result(d,result('89F165123',2)).is_confident
    assert not v.add_result(d,result('89F165128',3)).is_confident
    assert not v.add_result(d,result('89F165123',4)).is_confident


def test_ocr_engine_failure_is_visible_and_never_a_plate_vote():
    from app.cv.plate_voter import PlateVoter
    from app.cv.detector import Detection
    v = PlateVoter(60, 2.5, 2, .55)
    result = v.add_result(Detection('plate', .9, (0, 0, 100, 50), 1),
                          {'full': '89F165123', 'confidence': .99, 'error': 'ocr_engine_error:RuntimeError'})
    assert result.error == 'ocr_engine_error:RuntimeError'
    assert not result.text and not result.is_confident and result.sample_count == 0


def test_wrong_helmet_model_disables_only_helmet(monkeypatch):
    from types import SimpleNamespace
    import app.cv.pipeline as module
    detectors = [SimpleNamespace(class_names={0: 'plate'}),
                 SimpleNamespace(class_names={0: 'plate'}),
                 SimpleNamespace(class_names={0: 'person', 1: 'motorcycle'})]
    monkeypatch.setattr(module, 'HelmetPlateDetector', lambda *args, **kwargs: detectors.pop(0))
    monkeypatch.setattr(module, 'get_gate_roi', lambda gate: None)
    monkeypatch.setattr(module, 'get_gate_line', lambda gate: None)
    monkeypatch.setattr(module, 'CONTINUOUS_RECORDING_ENABLED', False)
    # Phase 3 (Task 1): trong test này class_names là {0: 'plate'} — không
    # chứa {"With Helmet", "Without Helmet"}. Mapping check phát hiện sai
    # ngay từ đầu nên reason = 'helmet_model_wrong_mapping' (an toàn hơn
    # 'wrong_classes' vì phát hiện sớm trước khi khởi chạy detector).
    # Phase 3 (Task 1): mapping check chạy trước classes check; trong test
    # này class_names {0: 'plate'} không khớp mapping mặc định → lỗi ở
    # mapping check.
    p = module.VideoPipeline('main', {'source': 'fake'})
    try:
        assert p._helmet_detector is None
        assert p._plate_detector is not None and p._person_detector is not None
        assert p.recognition_snapshot()['models']['helmet']['reason'] in (
            'helmet_model_wrong_classes', 'helmet_model_wrong_mapping',
        )
    finally:
        for pool in [p._detect_pool, p._ocr_pool, p._io_pool, p._clip_pool]:
            pool.shutdown(wait=True)


def test_completed_ocr_is_shown_even_when_plate_box_disappears(monkeypatch):
    import time
    from app.tests.test_dot_R import _build_pipeline_with_mocks
    from app.cv.detector import Detection
    from app.cv.best_plate import BestPlateStore, make_candidate
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    p._best_plates = BestPlateStore()
    done = Future()
    done.set_result({'full': '89F165123', 'confidence': .9, 'track_id': 7, 'frame_seq': 7, 'source_epoch': 0})
    p._best_plates.offer(7, make_candidate(np.zeros((100,100,3),np.uint8),(10,10,70,50),.9,7,time.time()))
    fakepool=MagicMock();fakepool.submit.return_value=done
    p._best_plates.trigger(7,fakepool,lambda *_:None,0)
    person = Detection('person', .9, (0, 0, 100, 100), 42)
    vehicle=Detection('motorcycle',.9,(0,50,100,100),7)
    group = p._group_by_person([person], [], [], [vehicle])[0][0]
    p._plate_approach={}
    from app.cv.crossing import CrossingDetector
    p._crossing_detector=CrossingDetector(None)
    try:
        p._observe_group(np.zeros((100, 100, 3), dtype=np.uint8), group)
        assert not p._best_plates.pending(7)
        rows = p._recognition_log.snapshot()['items']
        assert any(row.get('plate_text') == '89F165123' for row in rows)
        assert not group['_plate_result'].is_confident  # one frame stays review-only
        assert group['_plate_result'].sample_count == 1
    finally:
        p._ocr_pool.shutdown(wait=True)


@pytest.mark.parametrize('change', ['track', 'frame', 'expired'])
def test_mismatched_or_expired_ocr_is_not_a_vote(monkeypatch, change):
    import time
    from app.tests.test_dot_R import _build_pipeline_with_mocks
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    result = {'full': '89F165123', 'confidence': .9, 'track_id': 42, 'frame_seq': 7, 'source_epoch': 0}
    if change == 'track': result['track_id'] = 43
    if change == 'frame': result['frame_seq'] = 8
    done = Future(); done.set_result(result)
    p._ocr_pending[42] = done
    p._ocr_submit_meta[42] = {'ts': time.time() - (60 if change == 'expired' else 0),
                             'frame_seq': 7, 'source_epoch': 0, 'plate_bbox': (10, 10, 70, 50)}
    try:
        assert p._collect_plate_vote(42) is None
        assert not getattr(p, '_recognition_results', {})
        assert p._ocr_health['stale_dropped'] == 1
    finally:
        p._ocr_pool.shutdown(wait=True)


def test_log_rejects_late_evidence_from_old_source():
    from app.cv.recognition_log import RecognitionLog
    log = RecognitionLog('main', 'front')
    log.reset(2)
    log.append(1, 40, 1, 'io', 'error', 'evidence_write_failed', {})
    assert log.snapshot()['items'] == []
    assert log.source_epoch == 2


def test_log_is_bounded_throttled_and_non_destructive_for_viewers():
    from app.cv.recognition_log import RecognitionLog
    log=RecognitionLog('main','front')
    log.append(1,1,0,'ocr','pending','ocr_pending',{'plate_text':''},now=10)
    log.append(1,2,0,'ocr','pending','ocr_pending',{'plate_text':''},now=10.1)
    assert len(log.snapshot()['items'])==1
    log.append(1,3,0,'ocr','confirmed','plate_confirmed',{'plate_text':'89F165123'},now=10.2)
    for i in range(510):log.append(i,i,0,'detect','observed','objects_detected',{},now=11+i)
    a=log.snapshot(limit=100);b=log.snapshot(limit=100)
    assert a==b
    assert log.size==500
    assert len(a['items'])==100
    log.reset(1)
    assert not log.snapshot()['items']
    assert log.snapshot()['source_epoch']==1


@pytest.mark.parametrize('role',['admin','security','management'])
def test_diagnostic_endpoint_does_not_create_pipeline(client,monkeypatch,role):
    from app.tests.conftest import auth_headers
    import app.cv.pipeline as module
    monkeypatch.setattr(module,'_pipelines',{})
    constructor=MagicMock(side_effect=AssertionError('Read-only diagnostics must not initialize'))
    monkeypatch.setattr(module,'VideoPipeline',constructor)
    r=client.get('/guard/recognition_log?gate=main',headers=auth_headers(client,role))
    assert r.status_code==200
    assert r.json()['status']=='not_started'
    constructor.assert_not_called()


def test_diagnostic_access_and_limits(client):
    from app.tests.conftest import auth_headers
    assert client.get('/guard/recognition_log').status_code==401
    assert client.get('/guard/recognition_log',headers=auth_headers(client,'teacher')).status_code==403
    h=auth_headers(client)
    assert client.get('/guard/recognition_log?limit=101',headers=h).status_code==422
    assert client.get('/guard/recognition_log?gate=missing',headers=h).status_code==404


def test_real_loop_reads_plate_and_logs_helmet_without_violation(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    import time
    from app.tests.test_dot_R import _build_pipeline_with_mocks
    import app.cv.pipeline as module
    from app.cv.detector import Detection as D
    from app.cv.crossing import CrossingDetector
    from app.cv.evidence import EvidenceLedger
    from app.cv.plate_voter import PlateVoter
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    p._detect_pool = ThreadPoolExecutor(max_workers=3)
    p._person_detector = SimpleNamespace(detect_tracked=lambda f:[D('person',.9,(100,60,300,380),42),D('motorcycle',.9,(90,170,330,440),7)])
    p._helmet_detector = SimpleNamespace(detect=lambda f:[D('With Helmet',.9,(150,50,230,105))])
    p._plate_detector = SimpleNamespace(detect=lambda f:[D('plate',.9,(170,350,245,400))])
    p._plate_voter = PlateVoter(60,2.5,2,.55)
    p._crossing_detector = CrossingDetector(None)
    from app.cv.best_plate import BestPlateStore
    p._best_plates=BestPlateStore();p._plate_approach={};p._crossing_jobs={};p._crossing_sealed={}
    p._evidence_ledger = EvidenceLedger()
    p._io_pool = MagicMock(side_effect=AssertionError('No violation should be saved'))
    crops=[]
    def ocr(crop,track,seq,epoch):
        crops.append(crop.copy())
        return {'full':'89F165123','confidence':.9,'track_id':track,'frame_seq':seq,'source_epoch':epoch}
    monkeypatch.setattr(module,'_ocr_task',ocr)
    monkeypatch.setattr(module,'get_vehicle_by_plate',lambda text:{'plate_number':text})
    monkeypatch.setattr(module,'FRAME_SKIP',2)
    def posture(frame,groups):
        frame[:]=255  # overlays must never contaminate OCR crops
        for group in groups:group['posture_status']='riding'
        return groups
    p._run_posture_detection=posture
    p._draw_detection=MagicMock()
    class Source:
        count=0
        def read_frame(self):
            self.count+=1;time.sleep(.015)
            if self.count==12:p._running=False
            return np.full((120,180,3),100,dtype=np.uint8)
        def release(self):pass
    p._open_webcam=lambda config:Source()
    try:
        p._run_loop()
        rows=p._recognition_log.snapshot(limit=100)['items']
        assert any(row.get('helmet')=='helmet' and row['track_id']==42 for row in rows)
        assert any(row['reason_code']=='gate_line_missing' for row in rows)
        assert not crops  # no configured crossing line => select crops but do not invent an OCR trigger
        p._io_pool.submit.assert_not_called()
    finally:
        p._detect_pool.shutdown(wait=True);p._ocr_pool.shutdown(wait=True)
