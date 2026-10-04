"""IouTracker — gán ID ổn định cho người qua nhiều khung hình (app/cv/tracker.py)."""
from app.cv.tracker import IouTracker, iou


def test_iou_basic():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (5, 0, 15, 10)) - 50 / 150) < 1e-9


def test_same_person_moving_keeps_id():
    t = IouTracker()
    box = (100, 100, 200, 400)
    first = t.update([box], now=0.0)[0]
    for step in range(1, 10):  # đi ngang 25px mỗi lần detect
        moved = (100 + 25 * step, 100, 200 + 25 * step, 400)
        assert t.update([moved], now=step * 0.2)[0] == first


def test_two_people_get_distinct_stable_ids():
    t = IouTracker()
    a, b = (0, 0, 100, 300), (500, 0, 600, 300)
    id_a, id_b = t.update([a, b], now=0.0)
    assert id_a != id_b
    # thứ tự box đầu vào đảo ngược — ID vẫn bám đúng người
    assert t.update([b, a], now=0.2) == [id_b, id_a]


def test_fast_move_matched_by_center_distance():
    t = IouTracker()
    first = t.update([(100, 100, 200, 400)], now=0.0)[0]
    # nhảy 110px — gần như không còn chồng lấp, vẫn là cùng người
    assert t.update([(210, 100, 310, 400)], now=0.2)[0] == first


def test_track_expires_and_new_person_gets_new_id():
    t = IouTracker(max_age_sec=1.0)
    first = t.update([(100, 100, 200, 400)], now=0.0)[0]
    later = t.update([(100, 100, 200, 400)], now=5.0)[0]
    assert later != first
    assert t.active_ids() == {later}


def test_far_and_near_people_not_merged():
    t = IouTracker()
    near = t.update([(100, 100, 300, 700)], now=0.0)[0]
    # box nhỏ hơn hẳn ở gần đó (người ở xa, khác độ sâu) → không ghép
    far = t.update([(150, 100, 190, 180)], now=0.2)[0]
    assert far != near
