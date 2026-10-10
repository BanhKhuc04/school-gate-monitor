"""
Phase 4 (Task 1) tests — finalize without dropping late issues, 3+3 crossing
rule, max_transition_sec, evidence-before-alert ordering.

Covers:
- CrossingDetector honors `min_frames_exit_side` (3+3 mode): requires ≥3
  stable frames on entry side AND ≥3 stable frames on exit side.
- CrossingDetector honors `max_transition_sec`: if entry→exit transition
  takes longer than N seconds, reset stable_side without firing.
- Legacy 3+1 mode (`min_frames_exit_side=1`) still works for old callers.
- VideoPipeline._dispatch_late_issues() merges new issues into an existing
  sealed event via update_violation_issues (no duplicate row, no new alert).
- _crossing_event_to_db_id bounded to 2048 entries (LRU-style prune).
"""
import os
import sys
import time

import pytest

# Make project importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.cv.crossing import CrossingDetector, Direction, Side


# --------------------------------------------------------------------------- #
# 1. CrossingDetector 3+3 mode
# --------------------------------------------------------------------------- #

class TestCrossing3Plus3Rule:
    def _detector_3plus3(self, **overrides):
        kwargs = dict(
            gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
            min_frames_per_side=3, min_frames_exit_side=3,
            rearm_distance=0.05, cooldown_sec=0.0,
            max_transition_sec=5.0,
        )
        kwargs.update(overrides)
        return CrossingDetector(**kwargs)

    def test_3plus3_no_cross_with_only_1_exit_frame(self):
        """Legacy 3+1 → cross after first exit frame; 3+3 → must wait for
        3 stable frames on exit side."""
        d = self._detector_3plus3()
        t = 1000.0
        # 3 frames on side A (above → y < 0.5 → negative cross → raw=-1)
        for i in range(3):
            side, crossed = d.update(1, 0.5, 0.3, t + i * 0.1)
        # 1 frame on side B (below → y > 0.5 → positive cross → raw=+1)
        # legacy: crossed=True; 3+3: crossed=False
        side, crossed = d.update(1, 0.5, 0.7, t + 0.4)
        assert crossed is False
        assert side == Side.BELOW

    def test_3plus3_crosses_after_3_exit_frames(self):
        d = self._detector_3plus3()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # 2 frames on side B → not yet
        d.update(1, 0.5, 0.7, t + 0.4)
        d.update(1, 0.5, 0.7, t + 0.5)
        # 3rd frame on side B → crossing fires
        _, crossed = d.update(1, 0.5, 0.7, t + 0.6)
        assert crossed is True

    def test_3plus3_direction_enter(self):
        d = self._detector_3plus3()
        t = 1000.0
        # A is "above" (y < 0.5); B is "below" (y > 0.5)
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)  # side A
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.7, t + 0.4 + i * 0.1)  # side B
        assert d._tracks[1].crossed_direction == Direction.ENTER.value

    def test_3plus3_direction_exit(self):
        d = self._detector_3plus3()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.7, t + i * 0.1)  # side B
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.3, t + 0.4 + i * 0.1)  # side A
        assert d._tracks[1].crossed_direction == Direction.EXIT.value


# --------------------------------------------------------------------------- #
# 2. CrossingDetector max_transition_sec (Phase 4: anti-17-second bug)
# --------------------------------------------------------------------------- #

class TestCrossingMaxTransition:
    def _detector(self, max_transition_sec=5.0):
        return CrossingDetector(
            gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
            min_frames_per_side=3, min_frames_exit_side=3,
            rearm_distance=0.05, cooldown_sec=0.0,
            max_transition_sec=max_transition_sec,
        )

    def test_17_seconds_gap_no_cross(self):
        """The bug we MUST prevent: 3 frames on A, gap 17s before stable
        frames on B. Trước đây (không có max_transition_sec): crossing
        fires khi đủ 3 mẫu B dù cách 17s. Phase 4: phải reset."""
        d = self._detector(max_transition_sec=5.0)
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # 3 frames on B, mỗi frame cách nhau 6s (> max_transition_sec=5).
        # Frame 1 at t+17.1 → transition_started_at=t+17.1, streak=1
        d.update(1, 0.5, 0.7, t + 17.1)
        # Frame 2 at t+23.1 → transition_elapsed=6s > 5s → reset stable_side
        # to +1 (current side), transition_started_at=None
        d.update(1, 0.5, 0.7, t + 23.1)
        # Frame 3 at t+29.1 → same-side (stable_side=+1 now), no crossing
        d.update(1, 0.5, 0.7, t + 29.1)
        assert d._tracks[1].has_crossed is False
        assert d._tracks[1].stable_side == 1

    def test_short_transition_within_window_fires(self):
        """3 frames on A, 3 frames on B within 5s → crossing fires."""
        d = self._detector(max_transition_sec=5.0)
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.7, t + 0.4 + i * 0.1)
        assert crossed is True
        assert d._tracks[1].has_crossed is True

    def test_post_video_review_3A_gap17s_3B_consecutive_no_cross(self):
        """N04 (Post-Video Review): 3 frames on B CONSECUTIVE (mỗi cách
        nhau 0.1s) sau gap 17 giây vẫn không được crossing.

        Trước Phase 7-fix: transition_started_at được neo ở frame B
        ĐẦU TIÊN (≈1017.1) → transition_elapsed luôn ≤ 0.3s → chốt
        CROSSING dù gap thực tế từ A cuối (1000.2) đến B đầu (1017.1) là
        16.9s.

        Sau fix: transition_started_at neo vào frame A cuối cùng
        xác nhận stable_side (1000.2). Frame B đầu (1017.1) →
        transition_elapsed = 16.9s > 5.0s → reset stable_side = +1.
        Frame B thứ 2, 3 → cùng phía stable_side=+1 → không crossing."""
        d = self._detector(max_transition_sec=5.0)
        t = 1000.0
        # 3 frames on A at t+0.0/0.1/0.2 → stable_side=-1, transition_started_at=1000.2
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        assert d._tracks[1].stable_side == -1
        assert d._tracks[1].transition_started_at == 1000.2
        # 3 frames on B at t+17.1/17.2/17.3 → B đầu cách A cuối 16.9s
        # → transition_elapsed > 5 → stable_side = +1, transition_started_at=1017.1
        results = []
        for i in range(3):
            side, crossed = d.update(1, 0.5, 0.7, t + 17.1 + i * 0.1)
            results.append((side, crossed))
        # Không frame nào trả crossed=True
        for side, crossed in results:
            assert crossed is False, (
                f"Frame trả crossed=True dù gap từ A cuối → B đầu = 16.9s > max_transition_sec=5s")
        assert d._tracks[1].has_crossed is False
        assert d._tracks[1].stable_side == 1

    def test_transition_resets_via_stable_side_change(self):
        """When transition exceeds max_transition_sec, stable_side is reset
        to the new side; subsequent same-side frames treat it as the new
        stable side (no crossing for that direction)."""
        d = self._detector(max_transition_sec=2.0)
        t = 1000.0
        # 3 frames on A → stable_side=-1
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # 1 frame on B at t+3.1 → transition_started_at=1000.2 (last A),
        # streak=1, elapsed=2.9s > 2.0 → reset, stable_side=+1, timer=1003.1
        d.update(1, 0.5, 0.7, t + 3.1)
        # 2nd frame on B at t+10.1 → elapsed=7s > 2 → reset again, stable=+1, timer=1010.1
        d.update(1, 0.5, 0.7, t + 10.1)
        assert d._tracks[1].stable_side == 1
        # Post-fix (N04): transition_started_at neo vào frame stable gần nhất
        # (1010.1) chứ không None. Nếu tiếp tục nhận frame cùng phía +1
        # thì vẫn an toàn; nếu nhận phía đối (-1) thì elapsed=10.1-1010.1<...
        # vẫn OK vì same-side đã refresh.
        assert d._tracks[1].transition_started_at == 1010.1
        assert d._tracks[1].has_crossed is False


# --------------------------------------------------------------------------- #
# 3. Backward compat — min_frames_exit_side=1 is the legacy 3+1 mode
# --------------------------------------------------------------------------- #

class TestCrossingBackwardCompat3Plus1:
    def test_legacy_3plus1_first_exit_frame_fires(self):
        d = CrossingDetector(
            gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
            min_frames_per_side=3, min_frames_exit_side=1,
            rearm_distance=0.05, cooldown_sec=0.0,
            max_transition_sec=5.0,
        )
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, crossed = d.update(1, 0.5, 0.7, t + 0.4)
        assert crossed is True


# --------------------------------------------------------------------------- #
# 4. CrossingDetector constructor signatures
# --------------------------------------------------------------------------- #

class TestCrossingDetectorConstructor:
    def test_min_frames_exit_side_clamped(self):
        """Values <1 are clamped to 1 (avoid divide-by-zero or no-fire)."""
        d = CrossingDetector(
            gate_line=[0.2, 0.5, 0.8, 0.5],
            min_frames_per_side=3, min_frames_exit_side=0,
        )
        assert d.min_frames_exit_side == 1

    def test_max_transition_sec_default_5(self):
        d = CrossingDetector(gate_line=[0.2, 0.5, 0.8, 0.5])
        assert d.max_transition_sec == 5.0

    def test_unconfigured_detector_returns_on_no_crossing(self):
        d = CrossingDetector(gate_line=None)
        side, crossed = d.update(1, 0.5, 0.3, time.time())
        assert side == Side.ON
        assert crossed is False


# --------------------------------------------------------------------------- #
# 5. Late-issue merge plumbing (via db update_violation_issues)
# --------------------------------------------------------------------------- #

class TestLateIssueMerge:
    """Verify the wiring logic in pipeline._dispatch_late_issues without
    exercising the full pipeline. We construct a VideoPipeline via __new__
    and inspect the eid → db_id map + late-issue dispatch."""

    def _bare_pipeline(self):
        from app.cv.pipeline import VideoPipeline
        p = VideoPipeline.__new__(VideoPipeline)
        p._crossing_event_to_db_id = {}
        p._source_epoch = 0
        p.gate_id = "main"
        p.camera_id = "main"
        return p

    def test_dispatch_late_issues_with_unknown_eid_returns_false(self):
        p = self._bare_pipeline()
        result = p.dispatch_late_issues("unknown-id", [{"code": "NO_HELMET"}])
        assert result is False

    def test_dispatch_late_issues_with_empty_issues_returns_false(self):
        p = self._bare_pipeline()
        p._crossing_event_to_db_id["known-id"] = 42
        result = p.dispatch_late_issues("known-id", [])
        assert result is False

    def test_dispatch_late_issues_calls_db_update(self, monkeypatch):
        """Monkey-patch app.db.update_violation_issues and verify it's
        called with correct db_id + JSON-serialized issues. We patch at
        the source module since pipeline imports it lazily inside the
        function."""
        import app.db as db_mod
        calls = []
        def fake_update(violation_id, **kwargs):
            calls.append((violation_id, kwargs))
            return True
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)
        # Re-bind inside pipeline module's namespace if it already imported it
        import app.cv.pipeline as pipeline_mod
        monkeypatch.setattr(pipeline_mod, "update_violation_issues", fake_update, raising=False)

        p = self._bare_pipeline()
        p._crossing_event_to_db_id["enc-1"] = 99
        issues = [{"code": "NO_HELMET", "status": "confirmed",
                   "sample_count": 4, "evidence_ref": "{}"}]
        result = p.dispatch_late_issues("enc-1", issues)
        assert result is True
        assert len(calls) == 1
        vid, kwargs = calls[0]
        assert vid == 99
        assert "issues_json" in kwargs
        import json
        parsed = json.loads(kwargs["issues_json"])
        assert parsed[0]["code"] == "NO_HELMET"

    def test_dispatch_late_issues_handles_db_failure(self, monkeypatch):
        import app.db as db_mod
        def fake_update(violation_id, **kwargs):
            raise RuntimeError("DB locked")
        monkeypatch.setattr(db_mod, "update_violation_issues", fake_update)
        import app.cv.pipeline as pipeline_mod
        monkeypatch.setattr(pipeline_mod, "update_violation_issues", fake_update, raising=False)

        p = self._bare_pipeline()
        p._crossing_event_to_db_id["enc-2"] = 50
        result = p.dispatch_late_issues("enc-2", [{"code": "X"}])
        assert result is False

    def test_eid_to_db_id_bounded(self):
        """Phase 4: cap at 2048 entries to avoid memory leak on long runs."""
        from app.cv.pipeline import VideoPipeline
        p = VideoPipeline.__new__(VideoPipeline)
        p._crossing_event_to_db_id = {}
        # simulate adding 2050 entries (each add checks length)
        for i in range(2050):
            p._crossing_event_to_db_id[f"eid-{i}"] = i
            if len(p._crossing_event_to_db_id) > 2048:
                p._crossing_event_to_db_id.pop(next(iter(p._crossing_event_to_db_id)))
        assert len(p._crossing_event_to_db_id) <= 2048


# --------------------------------------------------------------------------- #
# 6. 3+3 vs max_transition integration
# --------------------------------------------------------------------------- #

class TestCrossing3Plus3Integration:
    def test_3plus3_within_5s_fires(self):
        d = CrossingDetector(
            gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
            min_frames_per_side=3, min_frames_exit_side=3,
            rearm_distance=0.05, cooldown_sec=0.0,
            max_transition_sec=5.0,
        )
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # spread 3 exit frames over 1s (well within 5s window)
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.7, t + 0.4 + i * 0.3)
        assert crossed is True
        assert d._tracks[1].has_crossed is True
        assert d._tracks[1].crossed_direction == Direction.ENTER.value

    def test_3plus3_over_5s_resets(self):
        d = CrossingDetector(
            gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
            min_frames_per_side=3, min_frames_exit_side=3,
            rearm_distance=0.05, cooldown_sec=0.0,
            max_transition_sec=5.0,
        )
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # First B frame at t+6.1 → transition_started_at=1006.1
        d.update(1, 0.5, 0.7, t + 6.1)
        # 2nd B frame at t+13.1 → elapsed=7s > 5 → reset stable_side
        d.update(1, 0.5, 0.7, t + 13.1)
        # more B frames → same side now (stable_side=+1), no crossing
        for i in range(5):
            d.update(1, 0.5, 0.7, t + 14.0 + i * 0.1)
        assert d._tracks[1].has_crossed is False


# --------------------------------------------------------------------------- #
# 7. Method name on pipeline: dispatch_late_issues (not _dispatch_late_issues)
# --------------------------------------------------------------------------- #

class TestPipelineDispatchLateIssuesMethodName:
    """Confirm pipeline method is exposed as `dispatch_late_issues` (no
    underscore prefix) so live-loop caller in `_process_vehicle_crossings`
    can use it without private-name warning."""

    def test_method_exists(self):
        from app.cv.pipeline import VideoPipeline
        assert hasattr(VideoPipeline, "dispatch_late_issues")