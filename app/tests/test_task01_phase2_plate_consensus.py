"""Task 1 — Phase 2 (Multi-crop plate consensus, top 3-5 different frames).

Phase 2 closes three concrete failure modes from the audit:

1. **Single-crop brittleness** — `BestPlateStore` OCR-ed exactly one crop per
   vehicle. If the crop was blurry, partial, or had the wrong moment of the
   bike's travel, the entire OCR result was that single noisy vote.
   `PlateConsensusStore` keeps the top N crops from different frames and
   only finalizes a plate text when ≥2 crops agree.

2. **No-frame-diversity gate** — The audit demanded "top 3–5 crops from
   DIFFERENT frames". A naive vote that allows the same frame_seq twice
   would inflate agreement. Phase 2 enforces
   `diversity_min_frame_gap` between consecutive samples and rejects
   same-frame duplicates.

3. **Competitive results ignored** — When two different plates both had
   ≥2 votes, the result should NOT be silently picked; instead it stays
   undecided. This is a defensive-in-depth: an ambiguous OCR must not
   auto-pick a winner that becomes a "confirmed" plate read.

These tests are unit/regression tests on `PlateConsensusStore` and the
`pipeline.consensus_decide()` helper. They do not touch live cameras or
the operational DB.

Run:
    cd D:/Work/Project_motorbike
    venv\\Scripts\\python.exe -m pytest app/tests/test_task01_phase2_plate_consensus.py -v
"""
from __future__ import annotations

import time

import pytest


# --------------------------------------------------------------------------- #
# Direct tests on PlateConsensusStore (unit)
# --------------------------------------------------------------------------- #


class TestPlateConsensusUnit:
    """Phase 2 — `PlateConsensusStore` đơn vị."""

    def _store(self, **overrides):
        from app.cv.plate_consensus import PlateConsensusStore
        defaults = dict(
            max_crops_per_track=5,
            consensus_min_agree=2,
            min_confidence=0.55,
            diversity_min_frame_gap=2,
            ttl_sec=30.0,
            max_tracks=64,
        )
        defaults.update(overrides)
        return PlateConsensusStore(**defaults)

    def _record(self, frame_id, text, confidence=0.7, quality=0.7, error=None):
        from app.cv.plate_consensus import CropRecord
        return CropRecord(
            frame_id=frame_id,
            timestamp=time.time(),
            normalized=text,
            confidence=confidence,
            quality_score=quality,
            error=error,
        )

    # ----- empty store ------------------------------------------------------ #

    def test_empty_store_returns_none(self):
        s = self._store()
        text, conf, n = s.decide(99)
        assert text is None
        assert n == 0
        assert s.is_finalized(99) is False

    # ----- 1 sample insufficient ------------------------------------------- #

    def test_one_sample_is_not_enough(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345"))
        text, conf, n = s.decide(1)
        assert text is None
        assert n == 0

    # ----- 2 agreeing samples → finalize ----------------------------------- #

    def test_two_agreeing_samples_finalize(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345", confidence=0.8))
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.7))
        text, conf, n = s.decide(1)
        assert text == "59H12345"
        assert n == 2
        assert conf == pytest.approx(0.8)

    def test_finalize_marks_track_done(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345", confidence=0.8))
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.7))
        result = s.finalize(1)
        assert result == "59H12345"
        assert s.is_finalized(1) is True
        # Sau finalize, ingest thêm phải bị bỏ qua
        s.ingest_offer(1, self._record(14, "59H12345", confidence=0.9))
        text, _, n = s.decide(1)
        # vẫn finalize cũ; ingest sau finalize bị bỏ qua
        assert n == 0

    # ----- competitive disagreement ---------------------------------------- #

    def test_two_competing_results_remain_undecided(self):
        """Khi 2 chuỗi khác nhau đều có ≥2 mẫu → KHÔNG chốt."""
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345", confidence=0.8))
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.7))
        s.ingest_offer(1, self._record(14, "59H12346", confidence=0.75))
        s.ingest_offer(1, self._record(16, "59H12346", confidence=0.7))
        text, conf, n = s.decide(1)
        assert text is None  # không chốt
        assert n == 0

    def test_one_strong_one_weak_consensus_winner(self):
        """Khi 1 chuỗi đủ min_agree, chuỗi khác chỉ có 1 mẫu → chốt theo mẫu
        đủ điều kiện (chuỗi 1 mẫu bị loại vì không đủ min_agree)."""
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345", confidence=0.8))
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.7))
        s.ingest_offer(1, self._record(14, "59H12346", confidence=0.7))
        text, conf, n = s.decide(1)
        assert text == "59H12345"
        assert n == 2

    # ----- low-confidence filter ------------------------------------------- #

    def test_low_confidence_sample_rejected(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345", confidence=0.4))  # below min
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.4))  # below min
        text, _, n = s.decide(1)
        assert text is None
        assert n == 0

    # ----- diversity -------------------------------------------------------- #

    def test_same_frame_id_duplicate_dropped(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345"))
        s.ingest_offer(1, self._record(10, "59H12345"))  # same frame_id
        s.ingest_offer(1, self._record(12, "59H12345"))  # this one OK
        text, _, n = s.decide(1)
        assert n == 2  # not 3

    def test_frame_gap_enforced(self):
        s = self._store(diversity_min_frame_gap=3)
        s.ingest_offer(1, self._record(10, "59H12345"))
        s.ingest_offer(1, self._record(11, "59H12345"))  # gap=1, too small
        s.ingest_offer(1, self._record(12, "59H12345"))  # gap=1, too small
        # only frame 10 was accepted
        progress = s.progress(1)
        assert progress["crops_readable"] == 1
        assert progress["frame_ids"] == [10]

    # ----- empty/error handling -------------------------------------------- #

    def test_unreadable_crop_kept_for_diagnostics(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "", confidence=0.0, error="ocr_engine_error"))
        s.ingest_offer(1, self._record(12, "59H12345", confidence=0.7))
        # readable-only count used for vote
        text, _, n = s.decide(1)
        # 1 readable chưa đủ min_agree=2 → text=None, n=0
        assert n == 0
        assert text is None
        progress = s.progress(1)
        assert progress["crops_total"] == 2
        assert progress["crops_readable"] == 1

    # ----- cap -------------------------------------------------------------- #

    def test_max_crops_cap_enforced(self):
        s = self._store(max_crops_per_track=3)
        for fid in (10, 12, 14, 16, 18, 20):
            s.ingest_offer(1, self._record(fid, "59H12345"))
        progress = s.progress(1)
        assert len(progress["frame_ids"]) == 3
        # Giữ 3 frame mới nhất: 16, 18, 20
        assert progress["frame_ids"] == [16, 18, 20]

    # ----- TTL -------------------------------------------------------------- #

    def test_prune_drops_stale_tracks(self):
        s = self._store(ttl_sec=1.0)
        s.ingest_offer(1, self._record(10, "59H12345"))
        time.sleep(1.2)
        s.prune()
        assert len(s) == 0

    def test_max_tracks_cap(self):
        s = self._store(max_tracks=2)
        s.ingest_offer(1, self._record(10, "A"))
        s.ingest_offer(2, self._record(10, "B"))
        s.ingest_offer(3, self._record(10, "C"))  # should evict track 1
        assert len(s) <= 2

    # ----- progress debug -------------------------------------------------- #

    def test_progress_includes_candidates(self):
        s = self._store()
        s.ingest_offer(1, self._record(10, "59H12345"))
        s.ingest_offer(1, self._record(12, "59H12346"))
        progress = s.progress(1)
        assert progress["known"] is True
        assert sorted(progress["candidates"]) == ["59H12345", "59H12346"]


# --------------------------------------------------------------------------- #
# Source-code contract tests (defense in depth)
# --------------------------------------------------------------------------- #


class TestPipelineWiring:
    """Verify pipeline.py thực sự wire PlateConsensusStore và config."""

    def test_pipeline_uses_consensus(self):
        """`pipeline.py` phải import và khởi tạo PlateConsensusStore."""
        # PlateConsensusStore is imported lazily inside __init__ to keep the
        # top-level import graph light. Verify it appears in the source.
        import inspect
        from app.cv import pipeline as pm
        src = inspect.getsource(pm.VideoPipeline.__init__)
        assert "PlateConsensusStore" in src

    def test_pipeline_ingests_into_consensus(self):
        """`_observe_best_plate` phải gọi `_consensus_ingest`."""
        import inspect
        from app.cv import pipeline as pm
        src = inspect.getsource(pm.VideoPipeline._observe_best_plate)
        assert "_consensus_ingest" in src

    def test_consensus_ingest_helper_exists(self):
        from app.cv import pipeline as pm
        assert hasattr(pm.VideoPipeline, "_consensus_ingest")
        assert hasattr(pm.VideoPipeline, "consensus_decide")

    def test_camera_change_resets_consensus(self):
        """Source-change reset phải reset `_plate_consensus`."""
        import inspect
        from app.cv import pipeline as pm
        src = inspect.getsource(pm.VideoPipeline._apply_camera_change)
        assert "_plate_consensus" in src

    def test_get_status_exposes_plate_consensus(self):
        """`get_status()` phải có `metrics.plate_consensus`."""
        import inspect
        from app.cv import pipeline as pm
        src = inspect.getsource(pm.VideoPipeline.get_status)
        assert '"plate_consensus"' in src

    def test_config_has_consensus_settings(self):
        from app import config
        for name in ("PLATE_CONSENSUS_ENABLED", "PLATE_CONSENSUS_MAX_CROPS",
                     "PLATE_CONSENSUS_MIN_AGREE", "PLATE_CONSENSUS_MIN_CONFIDENCE",
                     "PLATE_CONSENSUS_DIVERSITY_GAP", "PLATE_CONSENSUS_TTL_SEC"):
            assert hasattr(config, name), f"missing config {name}"


# --------------------------------------------------------------------------- #
# PlateConsensusStore + pipeline integration (mocked)
# --------------------------------------------------------------------------- #


class TestConsensusIntegration:
    """End-to-end (mocked): pipeline._consensus_ingest + consensus_decide."""

    def _build(self, monkeypatch):
        import threading
        from unittest.mock import MagicMock
        from app.cv import pipeline as pm
        from app.cv.plate_consensus import PlateConsensusStore

        class FakeWebcam:
            def __init__(self):
                self._opened = True

            def read_frame(self):
                import numpy as np
                return np.zeros((480, 640, 3), dtype=np.uint8)

            def release(self):
                self._opened = False

            @property
            def is_opened(self):
                return self._opened

        monkeypatch.setattr(pm, "HelmetPlateDetector", MagicMock(), raising=False)
        monkeypatch.setattr(pm, "PersonPoseDetector", MagicMock(), raising=False)
        monkeypatch.setattr(pm, "WebcamStream", FakeWebcam, raising=False)
        monkeypatch.setattr(pm, "set_gate_camera_source", lambda *a, **kw: None, raising=False)
        monkeypatch.setattr(pm, "set_gate_roi", lambda *a, **kw: None, raising=False)
        monkeypatch.setattr(pm, "set_gate_line", lambda *a, **kw: None, raising=False)
        monkeypatch.setattr(pm, "get_gate_roi", lambda *a, **kw: None, raising=False)
        monkeypatch.setattr(pm, "get_gate_line", lambda *a, **kw: None, raising=False)

        p = pm.VideoPipeline.__new__(pm.VideoPipeline)
        p.gate_id = "phase2-test"
        p._source_epoch = 0
        p._lock = threading.Lock()
        p._plate_consensus = PlateConsensusStore(
            max_crops_per_track=5,
            consensus_min_agree=2,
            min_confidence=0.55,
            diversity_min_frame_gap=2,
            ttl_sec=30.0,
        )
        return p

    def test_consensus_ingest_with_finished_result(self, monkeypatch):
        p = self._build(monkeypatch)
        # Mock BestPlateStore result + candidate
        from app.cv.plate_voter import PlateReadResult
        from app.cv.best_plate import PlateCandidate
        result = PlateReadResult(text="59H12345", confidence=0.8,
                                  sample_count=1, is_confident=True)
        candidate = PlateCandidate(
            frame_id=10, timestamp=time.time(),
            crop=None, detector_conf=0.85, blur_score=120.0, contrast_score=60.0,
            crop_width=120, crop_height=40, quality_score=0.78, components={},
        )
        p._consensus_ingest(1, result, candidate)
        # 1 sample chưa đủ → decide trả None
        text, conf, n = p.consensus_decide(1)
        assert text is None
        assert n == 0

    def test_consensus_ingest_two_results_finalize(self, monkeypatch):
        p = self._build(monkeypatch)
        from app.cv.plate_voter import PlateReadResult
        from app.cv.best_plate import PlateCandidate
        for fid in (10, 12):
            result = PlateReadResult(text="59H12345", confidence=0.8,
                                      sample_count=1, is_confident=True)
            candidate = PlateCandidate(
                frame_id=fid, timestamp=time.time(),
                crop=None, detector_conf=0.85, blur_score=120.0, contrast_score=60.0,
                crop_width=120, crop_height=40, quality_score=0.78, components={},
            )
            p._consensus_ingest(1, result, candidate)
        text, conf, n = p.consensus_decide(1)
        assert text == "59H12345"
        assert n == 2
        # finalize marks done
        assert p._plate_consensus.is_finalized(1) is False
        assert p._plate_consensus.finalize(1) == "59H12345"

    def test_consensus_ingest_with_error_does_not_finalize(self, monkeypatch):
        p = self._build(monkeypatch)
        from app.cv.plate_voter import PlateReadResult
        from app.cv.best_plate import PlateCandidate
        for fid in (10, 12):
            result = PlateReadResult(text="", confidence=0.0,
                                      sample_count=0, is_confident=False,
                                      error="ocr_engine_error:RuntimeError")
            candidate = PlateCandidate(
                frame_id=fid, timestamp=time.time(),
                crop=None, detector_conf=0.85, blur_score=120.0, contrast_score=60.0,
                crop_width=120, crop_height=40, quality_score=0.78, components={},
            )
            p._consensus_ingest(1, result, candidate)
        text, conf, n = p.consensus_decide(1)
        assert text is None
        assert n == 0
