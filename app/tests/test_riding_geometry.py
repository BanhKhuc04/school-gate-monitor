"""Side-view riding requires positive body-to-bike evidence under occlusion."""
import pytest

from app.cv.pose import classify_posture

BIKE_BBOX = (0, 0, 100, 100)  # full-frame coords


def _kp(x, y, conf=0.9):
    return {"x": x, "y": y, "confidence": conf}


def _keypoints(hip, knee, ankle, conf=0.9):
    kps = [_kp(0, 0, 0.0) for _ in range(17)]
    for i in (11, 12):
        kps[i] = _kp(*hip, conf)
    for i in (13, 14):
        kps[i] = _kp(*knee, conf)
    for i in (15, 16):
        kps[i] = _kp(*ankle, conf)
    for i in (5, 6):
        kps[i] = _kp(hip[0], hip[1] - 50, conf)
    return kps


def test_no_bike_bbox_keeps_old_knee_angle_behavior():
    bent = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(80, 50))
    extended = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(50, 80))
    assert classify_posture(bent) == "riding"
    assert classify_posture(extended) == "standing"


def test_bent_knee_over_bike_center_is_riding():
    kps = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(80, 50))
    assert classify_posture(kps, bike_bbox=BIKE_BBOX) == "riding"


def test_bent_knee_cannot_override_body_beside_the_bike():
    """A pedestrian's bent step is not riding an unrelated nearby bike."""
    kps = _keypoints(hip=(250, 20), knee=(250, 50), ankle=(280, 50))
    assert classify_posture(kps, bike_bbox=BIKE_BBOX) == "unknown"


def test_feet_flat_on_ground_while_seated_is_still_riding():
    """Straight legs (feet down) would read as 'standing' on angle alone,
    but hip still sits over the bike -> riding."""
    kps = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(50, 80))
    assert classify_posture(kps, bike_bbox=BIKE_BBOX, temporal_score=1.0) == "riding"


def test_low_confidence_everything_is_unknown_even_with_legacy_override(monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, "RIDING_NO_LEG_KEYPOINTS_MEANS_WALKING", True)
    kps = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(80, 50), conf=0.1)
    assert classify_posture(kps, bike_bbox=BIKE_BBOX, threshold=0.3) == "unknown"


def test_low_confidence_everything_is_unknown_when_heuristic_disabled(monkeypatch):
    """With a different camera angle where this assumption doesn't hold,
    turning the flag off restores the conservative 'never guess' behavior."""
    import app.config as config
    monkeypatch.setattr(config, "RIDING_NO_LEG_KEYPOINTS_MEANS_WALKING", False)
    kps = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(80, 50), conf=0.1)
    assert classify_posture(kps, bike_bbox=BIKE_BBOX, threshold=0.3) == "unknown"


def _side_pose(*, hip=(50, 20), legs=False, one_side=False):
    kps = _keypoints(hip, (hip[0], hip[1] + 30), (hip[0] + 30, hip[1] + 30))
    if not legs:
        for i in (13, 14, 15, 16):
            kps[i]["confidence"] = 0.1
    if one_side:
        for i in (5, 11, 13, 15):
            kps[i]["confidence"] = 0.0
    return kps


def _score(kps, **kwargs):
    from app.cv.pose import SideViewRiding
    return SideViewRiding().evaluate(
        kps, bike_bbox=BIKE_BBOX,
        person_bbox=kwargs.pop("person_bbox", (30, -40, 80, 90)), **kwargs,
    )


def test_occluded_legs_allow_riding_with_strong_upper_body_and_temporal_evidence():
    result = _score(_side_pose(), temporal_score=1.0)
    assert result.state == "RIDING"
    assert result.score > 0.95
    assert result.features["leg"] is None
    assert result.available["leg"] is False
    assert result.debug["leg_status"] == "UNAVAILABLE"


def test_right_side_hip_and_shoulder_are_sufficient_when_left_side_hidden():
    result = _score(_side_pose(one_side=True), temporal_score=1.0, motion_score=1.0)
    assert result.state == "RIDING"
    assert result.available["hip"] is True
    assert result.available["torso"] is True


def test_one_visible_bent_leg_supports_strong_body_geometry():
    result = _score(_side_pose(legs=True, one_side=True))
    assert result.state == "RIDING"
    assert result.available["leg"] is True


@pytest.mark.parametrize("bad_leg", ["collapsed", "nonfinite"])
def test_unusable_leg_coordinates_do_not_supply_bent_knee_evidence(bad_leg):
    kps = _side_pose(legs=True)
    for index in (13, 14):
        kps[index] = _kp(50, 20) if bad_leg == "collapsed" else _kp(float("nan"), 50)
    result = _score(kps)
    assert result.state == "UNKNOWN"
    assert result.available["leg"] is False


@pytest.mark.parametrize("temporal", [None, 0.0, 0.4])
def test_occluded_legs_need_temporal_association(temporal):
    result = _score(_side_pose(), temporal_score=temporal, motion_score=1.0)
    assert result.state == "UNKNOWN"


def test_hidden_hips_and_torso_are_unknown_even_with_overlap_and_matching_motion():
    kps = [_kp(0, 0, 0.1) for _ in range(17)]
    result = _score(kps, temporal_score=1.0, motion_score=1.0)
    assert result.state == "UNKNOWN"
    assert result.available["hip"] is False
    assert result.available["torso"] is False
    assert result.available["leg"] is False


def test_hips_without_visible_shoulders_are_insufficient_for_riding():
    kps = _side_pose()
    for i in (5, 6):
        kps[i]["confidence"] = 0.1
    assert _score(kps, temporal_score=1.0, motion_score=1.0).state == "UNKNOWN"


def test_missing_legs_do_not_confirm_walking_when_body_is_beside_bike():
    result = _score(_side_pose(hip=(125, 20)), person_bbox=(110, -40, 150, 100),
                    temporal_score=1.0, motion_score=1.0)
    assert result.state == "UNKNOWN"


def test_visible_upright_walker_beside_associated_bike_is_walking():
    kps = _keypoints(hip=(125, 20), knee=(125, 60), ankle=(125, 100))
    result = _score(kps, person_bbox=(110, -40, 150, 100),
                    temporal_score=1.0, motion_score=1.0)
    assert result.state == "WALKING_WITH_BIKE"


def test_extended_legs_beside_bike_without_association_do_not_confirm_walking():
    kps = _keypoints(hip=(125, 20), knee=(125, 60), ankle=(125, 100))
    assert _score(kps, person_bbox=(110, -40, 150, 100), motion_score=1.0).state == "UNKNOWN"


def test_bent_step_beside_bike_cannot_be_confirmed_riding():
    result = _score(_side_pose(hip=(125, 20), legs=True),
                    person_bbox=(110, -40, 150, 100), temporal_score=1.0, motion_score=1.0)
    assert result.state == "UNKNOWN"


def test_feet_down_on_ground_still_riding_with_strong_body_relation():
    kps = _keypoints(hip=(50, 20), knee=(50, 50), ankle=(50, 100))
    result = _score(kps, temporal_score=1.0, motion_score=1.0)
    assert result.state == "RIDING"
    assert result.available["leg"] is True
    assert result.score < _score(_side_pose(), temporal_score=1.0, motion_score=1.0).score


def test_bent_legs_far_below_seat_do_not_confirm_riding():
    result = _score(_side_pose(hip=(50, 140), legs=True),
                    person_bbox=(30, 80, 80, 190), temporal_score=1.0, motion_score=1.0)
    assert result.state == "UNKNOWN"


def test_crop_offset_preserves_full_frame_geometry():
    full = _side_pose()
    crop = [dict(p, x=p["x"] - 25, y=p["y"] + 40) for p in full]
    before = _score(full, temporal_score=1.0)
    after = _score(crop, offset=(25, -40), temporal_score=1.0)
    assert after.state == before.state == "RIDING"
    assert after.score == pytest.approx(before.score)


def test_degenerate_bike_bbox_is_unknown():
    from app.cv.pose import SideViewRiding
    assert SideViewRiding().evaluate(_side_pose(), bike_bbox=(1, 1, 1, 1),
                                    person_bbox=(0, 0, 10, 10), temporal_score=1).state == "UNKNOWN"


def _move(box, dx):
    x1, y1, x2, y2 = box
    return (x1 + dx, y1, x2 + dx, y2)


def test_temporal_pair_becomes_strong_after_repeated_stable_observations():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState(min_frames=3)
    person = (30, -40, 80, 90)
    first = state.observe(7, 12, 1, person, BIKE_BBOX, 1.0)
    state.observe(7, 12, 1, _move(person, 10), _move(BIKE_BBOX, 10), 1.1)
    last = state.observe(7, 12, 1, _move(person, 20), _move(BIKE_BBOX, 20), 1.2)
    assert first.temporal_score < 0.65
    assert first.motion_score is None
    assert last.temporal_score == pytest.approx(1.0)
    assert last.motion_score == pytest.approx(1.0)


def test_motion_mismatch_is_supporting_evidence_and_not_a_decision():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState()
    person = (30, -40, 80, 90)
    state.observe(7, 12, 1, person, BIKE_BBOX, 1.0)
    features = state.observe(7, 12, 1, _move(person, 10), BIKE_BBOX, 1.1)
    assert features.motion_score == pytest.approx(0.0)
    assert _score(_side_pose(), temporal_score=1.0, motion_score=0.0).state == "RIDING"


def test_stationary_pair_has_available_temporal_and_unavailable_motion():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState()
    for index in range(3):
        features = state.observe(7, 12, 1, (30, -40, 80, 90), BIKE_BBOX, 1.0 + index / 10)
    assert features.temporal_score == pytest.approx(1.0)
    assert features.motion_score is None
    assert _score(_side_pose(), temporal_score=features.temporal_score,
                  motion_score=features.motion_score).state == "RIDING"


def test_changed_person_vehicle_or_epoch_starts_fresh_association():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState()
    person = (30, -40, 80, 90)
    for index in range(3):
        state.observe(7, 12, 1, person, BIKE_BBOX, 1.0 + index / 10)
    for person_id, vehicle_id, epoch in [(8, 12, 1), (7, 13, 1), (7, 12, 2)]:
        features = state.observe(person_id, vehicle_id, epoch, person, BIKE_BBOX, 1.4)
        assert features.temporal_score < 0.65
        assert features.motion_score is None


def test_repeated_timestamp_does_not_confirm_a_new_frame():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState()
    for _ in range(5):
        features = state.observe(7, 12, 1, (30, -40, 80, 90), BIKE_BBOX, 1.0)
    assert features.temporal_score < 0.65


def test_temporal_memory_is_bounded_and_expires_old_pairs():
    from app.cv.pose import RidingTemporalState
    state = RidingTemporalState(max_pairs=2, max_age_seconds=1.0)
    person = (30, -40, 80, 90)
    for index in range(5):
        state.observe(index, index, 1, person, BIKE_BBOX, 1.0)
    assert state.pair_count == 2
    features = state.observe(4, 4, 1, person, BIKE_BBOX, 3.0)
    assert state.pair_count == 1
    assert features.temporal_score < 0.65
    state.discard_vehicle(4)
    assert state.pair_count == 0


def _frontal_pose(hip_x, knee_spread, ankle_spread):
    """Bike seen head-on: box (40,40)-(100,160), 60 wide x 120 tall."""
    from app.cv.pose import KP_LEFT_HIP, KP_RIGHT_HIP, KP_LEFT_KNEE, KP_RIGHT_KNEE, KP_LEFT_ANKLE, KP_RIGHT_ANKLE
    kps = [_kp(0, 0, 0.0) for _ in range(17)]
    kps[KP_LEFT_HIP] = kps[KP_RIGHT_HIP] = _kp(hip_x, 70)
    kps[KP_LEFT_KNEE], kps[KP_RIGHT_KNEE] = _kp(hip_x - knee_spread / 2, 100), _kp(hip_x + knee_spread / 2, 100)
    kps[KP_LEFT_ANKLE], kps[KP_RIGHT_ANKLE] = _kp(hip_x - ankle_spread / 2, 150), _kp(hip_x + ankle_spread / 2, 150)
    return kps


FRONTAL_BIKE = (40, 40, 100, 160)


def test_frontal_straddle_on_centre_is_riding():
    from app.cv.pose import SideViewRiding
    result = SideViewRiding().evaluate(_frontal_pose(70, 36, 40), bike_bbox=FRONTAL_BIKE)
    assert result.state == "RIDING"


def test_frontal_person_beside_bike_with_legs_together_is_walking():
    """Pushing a bike seen head-on: hips off the centre line, legs together.
    The side-view rules called this RIDING (hips 'over the seat')."""
    from app.cv.pose import SideViewRiding
    result = SideViewRiding().evaluate(_frontal_pose(84, 10, 8), bike_bbox=FRONTAL_BIKE,
                                       temporal_score=1.0)
    assert result.state == "WALKING_WITH_BIKE"


def test_frontal_centered_without_legs_stays_unknown():
    from app.cv.pose import SideViewRiding, KP_LEFT_HIP, KP_RIGHT_HIP
    kps = [_kp(0, 0, 0.0) for _ in range(17)]
    kps[KP_LEFT_HIP] = kps[KP_RIGHT_HIP] = _kp(70, 70)
    assert SideViewRiding().evaluate(kps, bike_bbox=FRONTAL_BIKE).state == "UNKNOWN"
