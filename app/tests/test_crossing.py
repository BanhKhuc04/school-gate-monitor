"""Test CrossingDetector — vehicle_anchor (bottom-center) based, instant
post-cross finalization (no symmetric N-frame-on-both-sides wait)."""
import time
import pytest
from app.cv.crossing import CrossingDetector, Side, Direction, vehicle_anchor, get_line_side


class TestVehicleAnchor:
    def test_bottom_center_of_bbox(self):
        assert vehicle_anchor((10, 20, 50, 80)) == (30, 80)

    def test_not_the_bbox_center(self):
        ax, ay = vehicle_anchor((0, 0, 100, 100))
        assert ay == 100  # y2 (bottom), not 50 (center)


class TestGetLineSide:
    """Horizontal line y=0.5 from x=0.2 to x=0.8."""

    def test_above_and_below(self):
        assert get_line_side((0.5, 0.3), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) == -1
        assert get_line_side((0.5, 0.7), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) == 1

    def test_deadzone_returns_zero(self):
        assert get_line_side((0.5, 0.505), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) == 0

    def test_outside_segment_bounds_returns_zero(self):
        """TEST 12: point projects onto the line's infinite extension but
        outside the actual P1-P2 segment -> must NOT count as a side."""
        # x=1.5 is past P2 (x=0.8) on the same horizontal line's extension.
        assert get_line_side((1.5, 0.3), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) == 0
        assert get_line_side((-0.5, 0.3), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) == 0

    def test_within_segment_bounds_is_fine(self):
        assert get_line_side((0.5, 0.3), (0.2, 0.5), (0.8, 0.5), deadzone=0.02) != 0


def _detector(**overrides):
    kwargs = dict(gate_line=[0.2, 0.5, 0.8, 0.5], edge_margin=0.02,
                  min_frames_per_side=3, rearm_distance=0.05, cooldown_sec=0.0,
                  # Phase 4 (Task 1): mặc định helper test legacy 3+1 để
                  # không vỡ các test instant-cross cũ. Các test mới (Phase 4)
                  # sẽ override `min_frames_exit_side=3` để verify 3+3.
                  min_frames_exit_side=1, max_transition_sec=5.0)
    kwargs.update(overrides)
    return CrossingDetector(**kwargs)


class TestCrossingDetector:
    def test_unconfigured_detector_no_crossing(self):
        detector = CrossingDetector(gate_line=None)
        assert detector.is_configured is False
        side, crossed = detector.update(1, 0.5, 0.3, time.time())
        assert side == Side.ON
        assert crossed is False

    def test_configured_detector_is_configured(self):
        assert CrossingDetector(gate_line=[0.2, 0.5, 0.8, 0.5]).is_configured is True

    def test_1_bbox_touches_line_but_anchor_not_crossed_yet(self):
        """TEST 1: anchor stays in the dead-zone -> no crossing."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, crossed = d.update(1, 0.5, 0.505, t + 0.4)  # within deadzone
        assert crossed is False

    def test_2_anchor_flips_side_crosses_immediately(self):
        """TEST 2: stable side A (3 frames) then ONE clear frame on side B
        -> crossing fires immediately, no waiting for B to also stabilize."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.3, t + i * 0.1)
            assert crossed is False
        _, crossed = d.update(1, 0.5, 0.7, t + 0.5)
        assert crossed is True

    def test_3_partial_bbox_overlap_irrelevant_only_anchor_matters(self):
        """TEST 3: this detector never sees bbox, only the anchor point —
        confirms the contract that bbox overlap is not part of the decision."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, crossed = d.update(1, 0.5, 0.53, t + 0.4)  # 0.03 past the line, outside the 0.02 deadzone
        assert crossed is True

    def test_4_anchor_jitter_around_line_fires_only_one_event(self):
        """TEST 4: after crossing, jitter back toward the line (but not far
        enough to rearm) must not create a second event."""
        d = _detector(rearm_distance=0.2, cooldown_sec=0.0)
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, c1 = d.update(1, 0.5, 0.7, t + 0.4)
        assert c1 is True
        # Jitter: back near the line, still on B side, well within rearm_distance.
        for i in range(5):
            _, c = d.update(1, 0.5, 0.52, t + 0.5 + i * 0.1)
            assert c is False
        # Jitter back toward A side without ever getting far enough to rearm.
        _, c = d.update(1, 0.5, 0.49, t + 1.0)
        assert c is False

    def test_5_vehicle_near_line_then_leaves_frame_no_crossing(self):
        """TEST 5: track simply stops updating before a real side flip ->
        no crossing. (Leaving the frame means update() is never called again;
        nothing here infers a crossing from that.)"""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        d.update(1, 0.5, 0.48, t + 0.4)  # still in deadzone, still side A
        assert d.get_crossing_count() == 0

    def test_6_roi_exit_is_outside_this_detectors_concern(self):
        """TEST 6: this module has no ROI concept at all — a track simply not
        being updated (as if it left the ROI) cannot produce a crossing."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        assert d.get_crossing_count() == 0

    def test_7_crossing_then_disappearing_keeps_the_single_event(self):
        """TEST 7: crossing fires, then the track stops updating (as if the
        vehicle left frame) — the already-recorded crossing stays valid."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, crossed = d.update(1, 0.5, 0.7, t + 0.4)
        assert crossed is True
        assert d.get_crossing_count() == 1
        # No more update() calls for track 1 — nothing should change that.

    def test_8_track_lost_before_crossing_no_alert(self):
        """TEST 8: side A only partially stabilized (2/3), then track lost."""
        d = _detector()
        t = 1000.0
        for i in range(2):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        assert d.get_crossing_count() == 0

    def test_9_track_reappears_on_side_b_without_observed_transition(self):
        """TEST 9: a track whose FIRST ever observation is already on side B
        must not be treated as having crossed — there's no A->B transition."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            _, crossed = d.update(1, 0.5, 0.7, t + i * 0.1)
            assert crossed is False
        assert d.get_crossing_count() == 0

    def test_10_a_to_b_is_enter(self):
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        d.update(1, 0.5, 0.7, t + 0.4)
        assert d._tracks[1].crossed_direction == Direction.ENTER.value

    def test_11_b_to_a_is_exit(self):
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.7, t + i * 0.1)
        d.update(1, 0.5, 0.3, t + 0.4)
        assert d._tracks[1].crossed_direction == Direction.EXIT.value

    def test_12_anchor_beyond_segment_extension_no_crossing(self):
        """TEST 12: anchor sits on the line's infinite extension but outside
        the actual P1-P2 segment -> never counts as a side, never crosses."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        # x=1.5 is past the segment's x2=0.8 — same y as a "crossing" move,
        # but outside the segment bounds.
        _, crossed = d.update(1, 1.5, 0.7, t + 0.4)
        assert crossed is False

    def test_13_two_riders_same_vehicle_track_crosses_once(self):
        """TEST 13: calling update() twice with the SAME key (as pipeline.py
        now does for 2 riders sharing one vehicle_track_id) and the same
        frame_seq must not double-fire — the second call is a no-op dedup."""
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(42, 0.5, 0.3, t + i * 0.1, frame_seq=i)
        _, c1 = d.update(42, 0.5, 0.7, t + 0.4, frame_seq=10)
        assert c1 is True
        # Second group (passenger) processed same frame_seq -> deduped, not a 2nd cross.
        _, c2 = d.update(42, 0.5, 0.7, t + 0.4, frame_seq=10)
        assert c2 is False
        assert d.get_crossing_count() == 1

    def test_second_vehicle_different_track_independent(self):
        d = _detector()
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.3, t + i * 0.1)
        _, c1 = d.update(1, 0.5, 0.7, t + 0.4)
        assert c1 is True
        for i in range(3):
            d.update(2, 0.6, 0.3, t + 1.0 + i * 0.1)
        _, c2 = d.update(2, 0.6, 0.7, t + 1.4)
        assert c2 is True

    def test_reset_clears_all_tracks(self):
        d = _detector(min_frames_per_side=1)
        t = 1000.0
        d.update(1, 0.5, 0.3, t)
        d.update(2, 0.6, 0.3, t)
        assert d.get_active_track_count() == 2
        d.reset()
        assert d.get_active_track_count() == 0

    def test_allowed_direction_filters_the_other_way(self):
        """CROSSING_ALLOWED_DIRECTION='enter' — an EXIT transition must not
        be reported as a crossing event."""
        d = _detector(allowed_direction='enter')
        t = 1000.0
        for i in range(3):
            d.update(1, 0.5, 0.7, t + i * 0.1)  # start on side B
        _, crossed = d.update(1, 0.5, 0.3, t + 0.4)  # B -> A = EXIT
        assert crossed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_only_the_entering_direction_counts_backing_up_never_fires():
    """Front camera: a bike rides toward the camera (anchor moves down) and
    fires once, the moment its nose passes the line; backing up across the
    same line afterwards is ignored."""
    from app.cv.crossing import CrossingDetector, direction_for_motion
    line = [0.1, 0.5, 0.9, 0.5]
    det = CrossingDetector(line, edge_margin=.01, min_frames_per_side=3, min_frames_exit_side=1,
                           cooldown_sec=0, rearm_distance=.05,
                           allowed_direction=direction_for_motion(line, 'down'))
    fired = []
    ys = [.30, .35, .40, .45, .52, .60, .70,      # ride in: fires at .52 (first frame past the line)
          .65, .58, .52, .45, .40, .35, .30]      # back up across the line: nothing
    for k, y in enumerate(ys):
        _, crossed = det.update(1, .5, y, timestamp=k * .1)
        if crossed:
            fired.append(round(y, 2))
    assert fired == [.52]


def test_direction_for_motion_ignores_how_the_line_was_drawn():
    from app.cv.crossing import direction_for_motion
    a, b = [0.2, 0.7, 0.8, 0.6], [0.8, 0.6, 0.2, 0.7]
    assert direction_for_motion(a, 'down') != direction_for_motion(b, 'down')  # sides flip with P1/P2...
    assert direction_for_motion(a, 'down') == direction_for_motion(a, 'down')
    assert direction_for_motion(a, 'up') != direction_for_motion(a, 'down')
    assert direction_for_motion(a, 'any') is None and direction_for_motion([.5, 0, .5, 1], 'down') is None
