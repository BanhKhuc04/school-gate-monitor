from concurrent.futures import Future

import numpy as np
import pytest

from app.cv.best_plate import BestPlateStore, make_candidate, resolve_plate


class Pool:
    def __init__(self):
        self.calls = []
    def submit(self, fn, *args):
        future = Future()
        self.calls.append((fn, args, future))
        return future


def candidate(seq, quality):
    image = np.full((40, 60, 3), seq, np.uint8)
    result = make_candidate(image, (0, 0, 60, 40), .9, seq, seq * .1)
    result.quality_score = quality
    return result


def test_ten_crops_only_best_is_sent_once_and_frozen():
    store, pool = BestPlateStore(), Pool()
    for seq in range(1, 11):
        store.offer(7, candidate(seq, seq / 10))
    assert store.trigger(7, pool, lambda *_: None, 3)
    assert pool.calls[0][1][0][0, 0, 0] == 10
    for seq in range(11, 20):
        store.offer(7, candidate(seq, 1))
        assert not store.trigger(7, pool, lambda *_: None, 3)
    assert len(pool.calls) == 1
    assert store.debug(7)['attempts'] == 1
    assert store.debug(7)['best_frame_id'] == 10


def test_worse_or_marginal_crop_does_not_replace_better_crop_does():
    store = BestPlateStore(replace_margin=.05)
    assert store.offer(1, candidate(1, .5))
    assert not store.offer(1, candidate(2, .3))
    assert not store.offer(1, candidate(3, .53))
    assert store.offer(1, candidate(4, .7))
    assert store.debug(1)['best_frame_id'] == 4


def test_candidate_uses_original_pixels_without_sharing_memory():
    frame = np.arange(120 * 200 * 3, dtype=np.uint8).reshape(120, 200, 3)
    result = make_candidate(frame, (30, 20, 150, 100), .8, 5, 1)
    assert result.crop.shape == (80, 120, 3)
    assert np.array_equal(result.crop, frame[20:100, 30:150])
    assert not np.shares_memory(result.crop, frame)
    assert all(0 <= v <= 1 for v in result.components.values())


def test_partial_plate_is_unreadable_and_valid_full_plate_is_confirmed():
    assert not resolve_plate({'full': '23792', 'confidence': .99}).is_confident
    assert resolve_plate({'full': '23792', 'confidence': .99}).text == ''
    plate = resolve_plate({'top_line': '89-F1', 'bottom_line': '237.92', 'full': '89F123792', 'confidence': .9})
    assert plate.text == '89F123792' and plate.is_confident
    assert plate.sample_count == 1


def test_engine_failure_retries_same_crop_once_not_unreadable_result():
    store, pool = BestPlateStore(), Pool()
    store.offer(7, candidate(1, .8)); store.trigger(7, pool, lambda *_: None, 0)
    pool.calls[0][2].set_result({'error': 'ocr_engine_error:RuntimeError'})
    store.collect(7, pool, lambda *_: None, 0)
    assert len(pool.calls) == 2
    assert pool.calls[0][1][0] is pool.calls[1][1][0]
    pool.calls[1][2].set_result({'full': '23792', 'confidence': .9})
    result = store.collect(7, pool, lambda *_: None, 0)
    assert result.text == '' and not result.is_confident
    assert not store.trigger(7, pool, lambda *_: None, 0)
    assert store.debug(7)['attempts'] == 1
    assert store.debug(7)['technical_retries'] == 1


def test_old_epoch_and_repeated_frame_do_not_become_new_result():
    store, pool = BestPlateStore(), Pool()
    store.offer(1, candidate(1, .8)); store.trigger(1, pool, lambda *_: None, 2)
    pool.calls[0][2].set_result({'full': '89F123792', 'confidence': .99})
    assert store.collect(1, pool, lambda *_: None, 3) is None
    store.reset()
    assert store.debug(1) == {}


@pytest.mark.parametrize('text', ['23792', '89F1', '', '123456789'])
def test_incomplete_never_confirms(text):
    assert not resolve_plate({'full': text, 'confidence': 1}).is_confident


def test_runtime_gets_two_independent_samples_and_bounds_five_in_two_seconds():
    from app.cv.plate_consensus import PlateConsensusStore, CropRecord
    store, pool, votes = BestPlateStore(max_attempts=5), Pool(), PlateConsensusStore()
    for i in range(5):
        seq = 1+i*2
        assert store.offer(7, candidate(seq, .8))
        assert store.trigger(7, pool, lambda *_: None, 3)
        assert not store.offer(7, candidate(seq+1, 1))  # pending crop immutable
        pool.calls[-1][2].set_result({'full': '89F123792', 'confidence': .9,
                                     'frame_seq': seq, 'source_epoch': 3, 'track_id': 7})
        result = store.collect(7, pool, lambda *_: None, 3)
        sample = store.completed_candidate(7)
        assert sample.frame_id == seq
        votes.ingest_offer(7, CropRecord(seq, sample.timestamp, result.text, .9, .8))
        if i == 0:
            assert votes.decide(7)[0] is None
        else:
            assert votes.decide(7)[0] == '89F123792'
        assert not store.trigger(7, pool, lambda *_: None, 3)  # same frame never a new vote
    assert not store.offer(7, candidate(12, .9))
    assert len(pool.calls) == 5


def test_crop_after_window_cannot_be_a_new_vote_and_validator_never_invents_characters():
    store, pool = BestPlateStore(max_attempts=5), Pool()
    store.offer(7, candidate(1, .8)); store.trigger(7, pool, lambda *_: None, 0)
    pool.calls[-1][2].set_result({'full': '89F123792', 'confidence': .9})
    store.collect(7, pool, lambda *_: None, 0)
    assert not store.offer(7, candidate(30, .9))
    assert not resolve_plate({'full': '89F12O792', 'confidence': .99}).is_confident


def test_position_correction_keeps_letters_and_forces_only_numeric_positions():
    from app.cv.ocr import normalize_valid_plate
    assert normalize_valid_plate('89-S1 2O7.92','89-S1','2O7.92')=='89S120792'
    assert normalize_valid_plate('89-FI 237.92','89-FI','237.92')=='89FI23792'  # valid two-letter series is not globally rewritten
    assert normalize_valid_plate('23792')==''
    assert normalize_valid_plate('89F1')==''


def test_network_native_read_retains_decoded_resolution(monkeypatch):
    import app.cv.capture as module
    raw=np.full((1080,1920,3),77,np.uint8)
    class Capture:
        def isOpened(self):return True
        def read(self):return True,raw
        def set(self,*_):return False
        def release(self):pass
    monkeypatch.setattr(module.cv2,'VideoCapture',lambda *_:Capture())
    stream=module.WebcamStream('rtsp://test.invalid/source',width=640,height=480)
    try:
        native=stream.read_source_frame()
        assert native.shape==raw.shape and np.array_equal(native,raw)
        assert stream.read_frame().shape==(480,640,3)  # compatibility accessor
    finally:
        stream.release()


def test_two_line_engine_exception_is_technical_not_empty(monkeypatch):
    import app.cv.ocr as module
    class Reader:
        def readtext(self,*_,**__):raise RuntimeError('test')
    monkeypatch.setattr(module,'_get_reader',lambda:Reader())
    result=module.read_plate_detailed(np.full((60,90,3),120,np.uint8))
    assert result['error']=='ocr_engine_error:RuntimeError'


def test_clipped_box_cannot_extract_unrelated_negative_index_pixels():
    assert make_candidate(np.zeros((100,100,3),np.uint8),(-20,10,-1,30),.9,1,0) is None


def test_plate_crop_box_is_padded_inside_the_frame():
    """A tight detector box clips edge characters; the OCR crop gets a margin
    (rear-camera video: 47 -> 95 of 105 boxes read correctly), never past the frame."""
    from app.cv.pipeline import VideoPipeline
    from app.config import PLATE_BEST_CROP_PAD as pad
    assert VideoPipeline._padded_plate_box((100, 100, 200, 160), 1000, 1000) == (
        100 - 100 * pad, 100 - 60 * pad, 200 + 100 * pad, 160 + 60 * pad)
    assert VideoPipeline._padded_plate_box((0, 0, 50, 40), 55, 42) == (0, 0, 55, 42)
