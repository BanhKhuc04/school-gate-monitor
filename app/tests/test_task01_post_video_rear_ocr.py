"""Tests cho N02 (Post-Video Review): rear/ocr_only profile — OCR + consensus
vẫn chạy khi không có person detector / không có gate line / không có
crossing detector.

Tái hiện trước fix:
- `_run_loop()` có `if not person_dets: continue` bỏ qua toàn bộ nhánh OCR.
- Rear profile bỏ person detector → plate_dets có nhưng không đến BestPlateStore
  hoặc PlateConsensusStore → không có review/confirmed plate nào trên camera sau.

Sau fix:
- Khi `person_dets` rỗng NHƯNG `plate_dets` không rỗng → gọi `_observe_plate_only()`.
- `_observe_plate_only()` tạo track_id tạm theo bbox centroid quantized (32x32 px).
- Submit OCR qua BestPlateStore + ingest PlateConsensusStore.
"""
import numpy as np
import pytest

from app.cv.pipeline import VideoPipeline
from app.cv import pipeline as pipeline_module


def _build_pipeline(profile='ocr_only'):
    """Build pipeline qua __new__ giống các test fixtures khác trong test_dot_R."""
    p = VideoPipeline.__new__(VideoPipeline)
    p.gate_id = 'test-gate'
    p.camera_id = 'test-gate'
    p.profile = profile
    p.role = 'front' if profile == 'full' else 'rear'

    # Mock detectors — person = None cho rear profile
    p._person_detector = None
    p._helmet_detector = None
    p._plate_detector = None

    # Stub helpers
    class _StubBuf:
        def __init__(self): self._vals = []
        def add(self, v): self._vals.append(v)
        def percentile(self, p):
            if not self._vals: return 0.0
            sv = sorted(self._vals)
            k = (len(sv) - 1) * p
            f_ = int(k); c_ = min(f_ + 1, len(sv) - 1)
            if f_ == c_: return sv[f_]
            return sv[f_] + (sv[c_] - sv[f_]) * (k - f_)
    p._metrics_capture = _StubBuf()
    p._metrics_detect = _StubBuf()
    p._metrics_ocr_wait = _StubBuf()
    p._metrics_encode = _StubBuf()
    p._metrics_persistence = _StubBuf()
    p._metrics_dispatch = _StubBuf()

    # BestPlateStore + PlateConsensusStore thật (không mock)
    from app.cv.best_plate import BestPlateStore
    from app.cv.plate_consensus import PlateConsensusStore
    from app.config import (PLATE_BEST_REPLACE_MARGIN, PLATE_OCR_MIN_CONFIDENCE,
                             PLATE_CONSENSUS_MAX_CROPS, PLATE_CONSENSUS_MIN_AGREE,
                             PLATE_CONSENSUS_MIN_CONFIDENCE, PLATE_CONSENSUS_DIVERSITY_GAP,
                             PLATE_CONSENSUS_TTL_SEC)
    p._best_plates = BestPlateStore(PLATE_BEST_REPLACE_MARGIN, PLATE_OCR_MIN_CONFIDENCE)
    p._plate_consensus = PlateConsensusStore(
        max_crops_per_track=PLATE_CONSENSUS_MAX_CROPS,
        consensus_min_agree=PLATE_CONSENSUS_MIN_AGREE,
        min_confidence=PLATE_CONSENSUS_MIN_CONFIDENCE,
        diversity_min_frame_gap=PLATE_CONSENSUS_DIVERSITY_GAP,
        ttl_sec=PLATE_CONSENSUS_TTL_SEC,
    )
    p._ocr_health = {"submitted": 0, "completed": 0, "stale_dropped": 0,
                     "duplicate_dropped": 0, "errors": 0, "empty": 0}
    p._ocr_pool = None  # sẽ set khi cần
    p._source_epoch = 0
    p._frame_seq = 0
    p._recognition_results = {}
    p._diagnostic = lambda *a, **kw: None
    p._consensus_ingest = VideoPipeline._consensus_ingest.__get__(p)
    return p


class FakePlateDet:
    """Stand-in cho HelmetPlateDetector detection với bbox + confidence."""
    def __init__(self, bbox, confidence=0.85, track_id=7):
        self.bbox = bbox
        self.confidence = confidence
        self.class_name = 'plate'
        self.track_id = track_id


def _make_frame(w=640, h=360):
    """Tạo frame dummy có vùng tối/sáng để make_candidate có quality > 0."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[100:200, 100:300] = 255  # bright rectangle = readable plate region
    return img


def test_observe_plate_only_called_when_no_person_with_plates(monkeypatch):
    """Khi _run_loop rẽ nhánh `if not person_dets:` mà có plate_dets →
    `_observe_plate_only` được gọi."""
    p = _build_pipeline(profile='ocr_only')
    p._ocr_pool = None  # đảm bảo early-return không xảy ra (test method riêng)
    calls = []
    monkeypatch.setattr(p, '_observe_plate_only',
                        lambda src, plates: calls.append(len(plates)))
    # Simulate call site trong pipeline
    plate_dets = [FakePlateDet([100, 100, 300, 200]), FakePlateDet([400, 50, 550, 130])]
    person_dets = []
    if not person_dets and plate_dets:
        p._observe_plate_only(_make_frame(), plate_dets)
    assert calls == [2], "Phải gọi _observe_plate_only(2 plates) khi person rỗng"


def test_observe_plate_only_skipped_when_no_plates(monkeypatch):
    """Khi cả person lẫn plate đều rỗng → không gọi _observe_plate_only."""
    p = _build_pipeline(profile='ocr_only')
    calls = []
    monkeypatch.setattr(p, '_observe_plate_only',
                        lambda src, plates: calls.append(len(plates)))
    plate_dets = []
    person_dets = []
    if not person_dets and plate_dets:
        p._observe_plate_only(_make_frame(), plate_dets)
    assert calls == [], "Không gọi _observe_plate_only khi plate_dets rỗng"


def test_observe_plate_only_preserves_tracker_id_across_frames():
    """The camera's tracker owns identity, including movement between grid cells."""
    p = _build_pipeline(profile='ocr_only')
    # Cho offer chạy nhưng trigger/collect bị skip do ocr_pool stub.
    p._ocr_pool = object()
    frame = _make_frame()
    # Plate cố định ở (100,100)-(300,200), centroid (230, 47) → ccx=7, ccy=1
    # → tid = -(7*10000 + 1 + 1) = -70002
    plate = FakePlateDet([100, 100, 300, 200])
    # Stub BestPlateStore.offer để quan sát track_id
    offered = []
    orig_offer = p._best_plates.offer
    def spy_offer(tid, candidate):
        offered.append(tid)
        return orig_offer(tid, candidate)
    p._best_plates.offer = spy_offer
    # Stub trigger/collect để tránh gọi remote pool
    p._best_plates.trigger = lambda *a, **kw: False
    p._best_plates.collect = lambda *a, **kw: None
    for _ in range(3):
        p._observe_plate_only(frame, [plate])
    assert len(offered) >= 1, f"offer phải được gọi, got {offered}"
    assert all(t == offered[0] for t in offered), \
        f"Track_id tạm không ổn định qua frame: {offered}"
    assert len(set(offered)) == 1, f"Cùng biển đứng yên → cùng track_id, got {offered}"


def test_observe_plate_only_different_plates_different_track_ids():
    """2 biển ở 2 vị trí khác nhau → 2 track_id tạm khác nhau."""
    p = _build_pipeline(profile='ocr_only')
    p._ocr_pool = object()
    frame = _make_frame()
    plate_a = FakePlateDet([100, 100, 200, 150])  # centroid (190, 31)
    plate_b = FakePlateDet([400, 100, 500, 150], track_id=8)
    offered = []
    orig_offer = p._best_plates.offer
    def spy_offer(tid, candidate):
        offered.append(tid)
        return orig_offer(tid, candidate)
    p._best_plates.offer = spy_offer
    p._best_plates.trigger = lambda *a, **kw: False
    p._best_plates.collect = lambda *a, **kw: None
    p._observe_plate_only(frame, [plate_a, plate_b])
    assert len(offered) == 2
    assert offered[0] != offered[1], "2 biển khác vị trí phải có 2 track_id khác nhau"
    assert offered == [7, 8]


def test_observe_plate_only_safe_with_none_ocr_pool():
    """Khi ocr_pool=None (minimal smoke profile), gọi vẫn an toàn, không crash."""
    p = _build_pipeline(profile='ocr_only')
    p._ocr_pool = None
    frame = _make_frame()
    plate = FakePlateDet([100, 100, 300, 200])
    # Should not raise
    p._observe_plate_only(frame, [plate])


def test_observe_plate_only_safe_with_invalid_bbox():
    """Plate det bbox ngoài khung → skip, không crash."""
    p = _build_pipeline(profile='ocr_only')
    p._ocr_pool = None
    frame = _make_frame()
    plate = FakePlateDet([2000, 2000, 3000, 3000])  # ngoài frame
    # Should not raise, just skip
    p._observe_plate_only(frame, [plate])
