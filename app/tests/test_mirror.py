from app.cv.mirror import MISSING, PRESENT, UNKNOWN, MirrorVote, rider_side

BIKE = (100, 100, 400, 500)          # rộng 300 px
IMG_LEFT = (110, 120, 140, 150)      # gương nằm bên TRÁI ảnh
IMG_RIGHT = (360, 120, 390, 150)     # gương nằm bên PHẢI ảnh


def test_rider_left_is_image_right_when_coming_toward_camera():
    assert rider_side(IMG_RIGHT, BIKE, toward_camera=True) == 'left'
    assert rider_side(IMG_LEFT, BIKE, toward_camera=True) == 'right'


def test_rider_left_is_image_left_when_going_away():
    assert rider_side(IMG_LEFT, BIKE, toward_camera=False) == 'left'


def _vote(frames, **kw):
    vote = MirrorVote(k=5, min_present=2, **kw)
    for mirrors, occluded in frames:
        vote.observe(BIKE, mirrors, toward_camera=True, left_occluded=occluded)
    return vote.decide()


def test_present_when_left_mirror_seen_twice():
    assert _vote([([IMG_RIGHT], False), ([], False), ([IMG_RIGHT, IMG_LEFT], False)]) == PRESENT


def test_missing_needs_five_clear_frames_without_left_mirror():
    only_right = ([IMG_LEFT], False)
    assert _vote([only_right] * 5) == MISSING
    assert _vote([only_right] * 4) == UNKNOWN


def test_occluded_frames_never_prove_missing():
    assert _vote([([], False)] * 4 + [([], True)] * 3) == UNKNOWN


def test_single_sighting_is_not_enough_either_way():
    assert _vote([([IMG_RIGHT], False)] + [([], False)] * 6) == UNKNOWN


def test_small_bikes_are_ignored():
    vote = MirrorVote(min_vehicle_px=250)
    small = (100, 100, 200, 200)
    for _ in range(10):
        assert vote.observe(small, [], toward_camera=True) is False
    assert vote.decide() == UNKNOWN
