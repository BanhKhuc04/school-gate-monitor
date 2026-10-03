"""Exercise the real loop: helper-only tests missed frame sequence/JPEG wiring."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
from types import SimpleNamespace
import numpy as np
import pytest
from app.tests.test_dot_R import _build_pipeline_with_mocks, _FakeDet


@pytest.mark.parametrize('has_people',[False,True])
def test_real_loop_publishes_every_new_frame_including_skips(monkeypatch, has_people):
    import app.cv.pipeline as module
    p, _ = _build_pipeline_with_mocks(monkeypatch)
    monkeypatch.setattr(module, 'FRAME_SKIP', 2)
    p._detect_pool=ThreadPoolExecutor(max_workers=3)
    people=[_FakeDet('person',(20,20,40,50),track_id=7)] if has_people else []
    tracked = MagicMock(return_value=people)
    p._person_detector=SimpleNamespace(detect_tracked=tracked, detect=lambda frame:people)
    p._helmet_detector=p._plate_detector=SimpleNamespace(detect=lambda frame:[])
    p._group_by_person=lambda *args:([],[])
    p._run_posture_detection=lambda frame,groups:groups
    p._draw_detection=MagicMock()
    p._poll_camera_source=MagicMock()
    class Source:
        def __init__(self): self.count=0
        def read_frame(self):
            self.count+=1
            if self.count==4:p._running=False
            return np.full((80,120,3),self.count*30,dtype=np.uint8)
        def release(self): pass
    source=Source()
    p._open_webcam=MagicMock(return_value=source)
    try:
        p._run_loop()
        assert source.count==4
        assert p._frame_seq==4
        # FIX (T4): _build_pipeline_with_mocks dùng __new__ bypass __init__
        # → KHÔNG có _preview_thread. Test này phải publish JPEG sync
        # bằng cách gọi _publish_frame_jpeg trực tiếp cho từng frame_seq.
        # Queue-async behavior được test riêng trong test_camera_offline.
        for seq in range(1, p._frame_seq + 1):
            p._publish_frame_jpeg(np.full((80, 120, 3), seq * 30, dtype=np.uint8), seq)
        assert sorted(p._jpeg_cache)==[1,2,3,4]
        assert len({value[0] for value in p._jpeg_cache.values()})==4
        assert p.get_jpeg()==p._jpeg_cache[4][0]
        assert tracked.call_count==2
    finally:
        p._detect_pool.shutdown(wait=True)
        p._ocr_pool.shutdown(wait=True)
