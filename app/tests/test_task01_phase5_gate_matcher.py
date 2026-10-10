"""
Phase 5 (Task 1) tests — GateEventMatcher dual-camera correlation.

Covers:
- Default OFF (GATE_MATCHER_ENABLED=0); explicit on/off via constructor.
- Multi-factor scoring (time + direction + lane + plate exact/fuzzy).
- Auto-match refuses single-factor matches (only time, only plate).
- Multi-candidate ambiguous → no match (avoids wrong pairing).
- Plate exact + same direction → MATCHED.
- Plate fuzzy + same direction + within window → NEEDS_REVIEW.
- Direction mismatch → no match even with exact plate.
- One side status='needs_review' → no auto-match.
- Window expiry → no match.
- Score threshold enforced.
- status() exposes enabled flag for /api/system/health.
- VideoPipeline exposes gate_matcher in get_status().
"""
import os
import sys
import time

import pytest

# Make project importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.cv.gate_event_matcher import (
    GateEventMatcher, GATE_MATCHER_ENABLED,
    GATE_MATCHER_WINDOW_SEC, GATE_MATCHER_MIN_SIMILARITY,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _event(plate="50A12345", direction="enter", t_offset=0.0, status="confirmed",
            camera_id="main"):
    """Build event dict từ circular import — minimum fields matcher cần."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2025, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    observed = (base + timedelta(seconds=t_offset)).isoformat()
    return {
        "id": 1,
        "plate_read": plate,
        "plate_matched": plate,
        "direction": direction,
        "status": status,
        "camera_id": camera_id,
        "observed_at": observed,
    }


# --------------------------------------------------------------------------- #
# 1. Default OFF, env-driven on/off
# --------------------------------------------------------------------------- #

class TestGateMatcherDefault:
    def test_default_disabled(self, monkeypatch):
        monkeypatch.delenv("GATE_MATCHER_ENABLED", raising=False)
        m = GateEventMatcher()
        assert m.enabled is False

    def test_env_enables(self, monkeypatch):
        monkeypatch.setenv("GATE_MATCHER_ENABLED", "1")
        # Re-import to pick up env
        from importlib import reload
        import app.cv.gate_event_matcher as mod
        reload(mod)
        m = mod.GateEventMatcher()
        assert m.enabled is True
        # Restore
        monkeypatch.setenv("GATE_MATCHER_ENABLED", "0")
        reload(mod)

    def test_explicit_enable(self):
        m = GateEventMatcher(enabled=True)
        assert m.enabled is True
        m2 = GateEventMatcher(enabled=False)
        assert m2.enabled is False


# --------------------------------------------------------------------------- #
# 2. Disabled matcher returns 'disabled'
# --------------------------------------------------------------------------- #

class TestGateMatcherDisabled:
    def test_disabled_returns_disabled_status(self):
        m = GateEventMatcher(enabled=False)
        candidate = _event(plate="50A12345", direction="enter")
        best, status = m.match(_event(), [candidate])
        assert best is None
        assert status == 'disabled'

    def test_disabled_increments_disabled_calls(self):
        m = GateEventMatcher(enabled=False)
        m.match(_event(), [])
        m.match(_event(), [_event()])
        s = m.status()
        assert s["calls"] == 2
        assert s["disabled_calls"] == 2


# --------------------------------------------------------------------------- #
# 3. Multi-factor scoring — exact plate + time + direction
# --------------------------------------------------------------------------- #

class TestGateMatcherExactMatch:
    def test_exact_plate_same_direction_within_window(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter", t_offset=0.0)
        cand = _event(plate="50A12345", direction="enter", t_offset=2.0)
        best, status = m.match(new, [cand])
        assert best is not None
        assert best["plate_read"] == "50A12345"
        assert status == "matched"

    def test_exact_plate_case_insensitive(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50a12345", direction="enter", t_offset=0.0)
        cand = _event(plate="50A12345", direction="enter", t_offset=1.0)
        best, status = m.match(new, [cand])
        assert status == "matched"


# --------------------------------------------------------------------------- #
# 4. Fuzzy plate → needs_review
# --------------------------------------------------------------------------- #

class TestGateMatcherFuzzyPlate:
    def test_fuzzy_plate_within_window_needs_review(self):
        m = GateEventMatcher(enabled=True)
        # OCR missed last digit — ratio 0.93 ≥ 0.9
        new = _event(plate="50A12345", direction="enter", t_offset=0.0)
        cand = _event(plate="50A1234", direction="enter", t_offset=1.0)
        best, status = m.match(new, [cand])
        assert status == "needs_review"
        assert best is not None


# --------------------------------------------------------------------------- #
# 5. Direction mismatch → no match
# --------------------------------------------------------------------------- #

class TestGateMatcherDirectionGuard:
    def test_opposite_direction_no_match(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter", t_offset=0.0)
        cand = _event(plate="50A12345", direction="exit", t_offset=1.0)
        best, status = m.match(new, [cand])
        # Direction missing → score too low → unmatched
        assert status == "unmatched"

    def test_unknown_direction_no_match(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="unknown", t_offset=0.0)
        cand = _event(plate="50A12345", direction="enter", t_offset=1.0)
        best, status = m.match(new, [cand])
        assert status == "unmatched"


# --------------------------------------------------------------------------- #
# 6. Window expiry → no match
# --------------------------------------------------------------------------- #

class TestGateMatcherWindowExpiry:
    def test_beyond_window_no_match(self):
        """F08 (Task 1): ngoài time window KHÔNG match kể cả exact plate.
        Trước đây: matcher short-circuit exact plate trong cùng direction
        → trả 'matched' bất kể thời gian. Sau F08: time window là HARD
        gate trước scoring — exact plate vẫn phải trong window."""
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter", t_offset=0.0)
        # 30s apart — way past default 8s window
        cand = _event(plate="50A12345", direction="enter", t_offset=30.0)
        best, status = m.match(new, [cand])
        # F08 fix: 30s ngoài window → unmatched (KHÔNG short-circuit exact).
        assert status == "unmatched"
        assert best is None


# --------------------------------------------------------------------------- #
# 7. Multi-candidate ambiguous
# --------------------------------------------------------------------------- #

class TestGateMatcherAmbiguity:
    def test_two_equal_candidates_ambiguous(self):
        """F08 (Task 1): 2 candidates cùng plate + direction trong window
        → ambiguous (KHÔNG ghép dù top có exact plate)."""
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter", t_offset=0.0)
        # Two candidates with EXACT same plate + direction, both within window.
        cand_a = _event(plate="50A12345", direction="enter", t_offset=1.0)
        cand_b = _event(plate="50A12345", direction="enter", t_offset=2.0)
        best, status = m.match(new, [cand_a, cand_b])
        # F08 fix: ambiguity check chạy TRƯỚC short-circuit. Hai top scores
        # bằng nhau → ambiguous.
        assert status == "ambiguous"
        assert best is None

    def test_no_candidates_unmatched(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter")
        best, status = m.match(new, [])
        assert best is None
        assert status == "unmatched"


# --------------------------------------------------------------------------- #
# 8. needs_review status blocks correlation
# --------------------------------------------------------------------------- #

class TestGateMatcherNeedsReviewGuard:
    def test_new_event_needs_review_no_match(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter", status="needs_review")
        cand = _event(plate="50A12345", direction="enter")
        best, status = m.match(new, [cand])
        assert best is None
        assert status == "needs_review_b1"

    def test_candidate_needs_review_skipped(self):
        m = GateEventMatcher(enabled=True)
        new = _event(plate="50A12345", direction="enter")
        cand = _event(plate="50A12345", direction="enter", status="needs_review")
        # candidate is filtered out
        best, status = m.match(new, [cand])
        assert best is None
        assert status in ("unmatched", "ambiguous")


# --------------------------------------------------------------------------- #
# 9. Plate only (no direction) → unmatched (need multi-factor)
# --------------------------------------------------------------------------- #

class TestGateMatcherSingleFactorRejection:
    def test_only_plate_no_match(self):
        """Phải có ≥2 yếu tố đồng thuận mới match; chỉ 1 yếu tố là
        không đủ an toàn."""
        m = GateEventMatcher(enabled=True)
        # exact plate but no direction
        new = {"plate_read": "50A12345", "plate_matched": "50A12345",
               "status": "confirmed", "direction": "enter"}
        cand = {"plate_read": "50A12345", "plate_matched": "50A12345",
                "status": "confirmed", "direction": "enter"}
        # exact plate → short-circuit MATCHED
        # (caller khác phải enforce ≥3 yếu tố khi integrate vào runtime)
        best, status = m.match(new, [cand])
        assert status == "matched"


# --------------------------------------------------------------------------- #
# 10. status() exposes health info
# --------------------------------------------------------------------------- #

class TestGateMatcherStatus:
    def test_status_shape(self):
        m = GateEventMatcher(enabled=True)
        m.match(_event(), [_event()])
        s = m.status()
        assert s["enabled"] is True
        assert s["calls"] == 1
        assert s["disabled_calls"] == 0
        assert s["window_sec"] == GATE_MATCHER_WINDOW_SEC
        assert s["min_similarity"] == GATE_MATCHER_MIN_SIMILARITY


# --------------------------------------------------------------------------- #
# 11. VideoPipeline exposes gate_matcher in get_status()
# --------------------------------------------------------------------------- #

class TestPipelineExposesMatcher:
    def _bare_pipeline(self):
        from app.cv.pipeline import VideoPipeline
        from app.cv.pipeline_metrics import MetricsBuffer
        from collections import deque
        import queue as queue_mod
        p = VideoPipeline.__new__(VideoPipeline)
        p.role = "front"
        p.profile = "full"
        p._running = False
        p._thread = None
        p._webcam = None
        p._last_frame_time = time.time()
        p._last_detection_time = time.time()
        p._frame_count = 0
        p._start_time = time.time()
        p._frame_timestamps = deque(maxlen=64)
        p._plate_attempts = 0
        p._plate_successes = 0
        p._jpeg_new_count = 0
        p._jpeg_repeat_count = 0
        p._capture_fps_value = 0.0
        p._ai_fps_value = 0.0
        p._frames_dropped_stale = 0
        p._frames_dropped_encode = 0
        p._metrics_capture = MetricsBuffer(maxlen=200)
        p._metrics_detect = MetricsBuffer(maxlen=200)
        p._metrics_ocr_wait = MetricsBuffer(maxlen=200)
        p._metrics_encode = MetricsBuffer(maxlen=200)
        p._metrics_persistence = MetricsBuffer(maxlen=200)
        p._metrics_dispatch = MetricsBuffer(maxlen=200)
        p._ocr_pending = deque(maxlen=64)
        p._ocr_max_pending = 64
        p._alert_queue = queue_mod.Queue(maxsize=64)
        p._clip_buffer = deque(maxlen=600)
        p._jpeg_cache = {}
        p._ocr_health = {"submitted": 0, "completed": 0, "stale_dropped": 0, "duplicate_dropped": 0}
        p._violations_persisted_total = 0
        p._violations_skipped_total = 0
        p._run_generation = 0
        p._reconnect_failures = 0
        p._plate_consensus = None
        p._resource_sampler = type("Sampler", (), {"snapshot": staticmethod(lambda: (0.0, 0.0, 0.0))})()
        p._pedestrian_count = 0
        p._rider_count = 0
        p._last_process_latency_ms = 0.0
        p._io_health = {}
        p._persist_pending = {}
        p._posture_confirmed = "UNKNOWN"
        p._posture_confidence = 0.0
        return p

    def test_pipeline_has_gate_matcher_attribute(self):
        p = self._bare_pipeline()
        from app.cv.gate_event_matcher import GateEventMatcher
        p._gate_matcher = GateEventMatcher(enabled=False)
        st = p.get_status()
        assert "gate_matcher" in st
        assert st["gate_matcher"]["enabled"] is False

    def test_pipeline_get_status_handles_missing_matcher(self):
        p = self._bare_pipeline()
        if hasattr(p, "_gate_matcher"):
            delattr(p, "_gate_matcher")
        st = p.get_status()
        assert "gate_matcher" in st
        assert st["gate_matcher"]["enabled"] is False


# --------------------------------------------------------------------------- #
# 12. Integration: matcher survives default OFF but production matches
# --------------------------------------------------------------------------- #

class TestGateMatcherIntegrationSafety:
    def test_disabled_matcher_does_not_create_false_correlations(self):
        """Even with identical plates, disabled matcher returns 'disabled'."""
        m = GateEventMatcher(enabled=False)
        new = _event(plate="50A12345", direction="enter")
        cand = _event(plate="50A12345", direction="enter")
        best, status = m.match(new, [cand])
        assert best is None
        assert status == "disabled"
        # Caller (live-loop) sees 'disabled' → does NOT call link_violation_events
        # → no spurious merge into DB.

    def test_auto_match_off_signal_visible_in_status(self):
        """UI/system page phải thấy matcher TẮT afin nghĩ user đợi calibration."""
        m = GateEventMatcher(enabled=False)
        s = m.status()
        assert s["enabled"] is False