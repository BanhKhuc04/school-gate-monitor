"""A person whose box ByteTrack loses for a few seconds keeps one id."""
from types import SimpleNamespace

from app.cv.track_stitch import TrackStitcher


def det(tid, box):
    return SimpleNamespace(track_id=tid, bbox=box)


def test_new_id_near_recently_lost_one_takes_it_over():
    st = TrackStitcher(max_gap_sec=5, max_dist=1.0)
    st.apply([det(4, (300, 0, 340, 100))], 0.0)
    st.apply([], 2.0)
    out = st.apply([det(54, (310, 0, 370, 110))], 3.5)
    assert out[0].track_id == 4
    assert st.apply([det(54, (312, 0, 372, 112))], 3.6)[0].track_id == 4


def test_visible_old_id_is_never_taken_over():
    """Two people side by side: the second one keeps its own id."""
    st = TrackStitcher()
    st.apply([det(1, (100, 0, 140, 100))], 0.0)
    out = st.apply([det(1, (100, 0, 140, 100)), det(2, (150, 0, 190, 100))], 0.1)
    assert [d.track_id for d in out] == [1, 2]


def test_far_away_or_too_late_gets_a_new_id():
    st = TrackStitcher(max_gap_sec=5, max_dist=1.0)
    st.apply([det(1, (0, 0, 40, 100))], 0.0)
    assert st.apply([det(2, (400, 0, 440, 100))], 1.0)[0].track_id == 2
    st2 = TrackStitcher(max_gap_sec=5, max_dist=1.0)
    st2.apply([det(1, (0, 0, 40, 100))], 0.0)
    assert st2.apply([det(3, (5, 0, 45, 100))], 6.0)[0].track_id == 3


def test_one_lost_id_is_claimed_by_one_new_id_only():
    st = TrackStitcher()
    st.apply([det(1, (100, 0, 140, 100))], 0.0)
    out = st.apply([det(7, (105, 0, 145, 100)), det(8, (95, 0, 135, 100))], 1.0)
    assert sorted(d.track_id for d in out) in ([1, 7], [1, 8])


def test_untracked_detections_pass_through_and_reset_forgets():
    st = TrackStitcher()
    assert st.apply([det(None, (0, 0, 10, 10))], 0.0)[0].track_id is None
    st.apply([det(1, (0, 0, 40, 100))], 0.0)
    st.reset()
    assert st.apply([det(2, (0, 0, 40, 100))], 1.0)[0].track_id == 2
