"""
Test cho việc gán phương tiện (motorcycle/bicycle) vào person trong
`VideoPipeline._group_by_person` — thêm điều kiện chồng lấp trục Y (Bước
cải thiện phân biệt người đi bộ / người đi xe) bên cạnh điều kiện x-distance
sẵn có, để giảm gán nhầm người đi bộ đứng gần 1 xe máy khác "độ sâu" trong
khung hình thành người đang lái xe.
"""
from app.cv.detector import Detection
from app.cv.pipeline import VideoPipeline


def _pipeline():
    """Tạo instance không qua __init__ (bypass camera/model) + khởi tạo dict cần cho test."""
    p = VideoPipeline.__new__(VideoPipeline)
    p._track_vehicle_history = {}
    p._vehicle_vote_window_sec = 2.5
    p._vehicle_vote_min_samples = 3
    return p


def _det(class_name, bbox):
    return Detection(class_name=class_name, confidence=0.9, bbox=bbox)


def test_tracked_bike_seen_as_motorcycle_stays_motorcycle_when_coco_says_bicycle():
    p = _pipeline()
    person = Detection('person', .9, (100, 100, 200, 300), track_id=1)
    first, _ = p._group_by_person([person], [], [], [Detection('motorcycle', .9, (90, 150, 210, 320), track_id=5)])
    later, _ = p._group_by_person([person], [], [], [Detection('bicycle', .9, (90, 150, 210, 320), track_id=5)])
    other, _ = p._group_by_person([person], [], [], [Detection('bicycle', .9, (90, 150, 210, 320), track_id=6)])
    assert first[0]['vehicle_type'] == later[0]['vehicle_type'] == 'motorcycle'
    assert other[0]['vehicle_type'] == 'bicycle'


def test_vertical_overlap_true_when_y_ranges_intersect():
    assert VideoPipeline._vertical_overlap((0, 100, 50, 200), (10, 150, 60, 250)) is True


def test_vertical_overlap_false_when_y_ranges_disjoint():
    assert VideoPipeline._vertical_overlap((0, 0, 50, 50), (0, 500, 50, 600)) is False


def test_rider_matched_when_x_close_and_y_overlaps():
    """Người thật sự đứng/ngồi trên xe — box person và vehicle chồng lấp cả X lẫn Y."""
    person = _det("person", (100, 100, 200, 300))
    vehicle = _det("motorcycle", (90, 150, 210, 320))
    groups, _ = _pipeline()._group_by_person([person], [], [], [vehicle])
    assert groups[0]["vehicle_type"] == "motorcycle"


def test_pedestrian_not_matched_to_vehicle_at_different_depth():
    """Người đi bộ thẳng hàng X với 1 xe máy nhưng ở 'độ sâu' khác (Y disjoint hẳn)
    — trước đây bị gán nhầm thành người đi xe chỉ vì gần theo X, giờ không còn nữa."""
    person = _det("person", (100, 500, 200, 700))       # gần đáy khung (gần camera)
    vehicle = _det("motorcycle", (100, 50, 200, 150))    # xa tít đỉnh khung (xa camera)
    groups, _ = _pipeline()._group_by_person([person], [], [], [vehicle])
    assert groups[0]["vehicle_type"] is None
    assert groups[0]["_vehicle"] is None


def test_no_vehicle_nearby_stays_pedestrian():
    person = _det("person", (100, 100, 200, 300))
    groups, _ = _pipeline()._group_by_person([person], [], [], [])
    assert groups[0]["vehicle_type"] is None


# ─── UT3: vote vehicle_type theo track_id qua nhiều frame ────────────────────

import time


def _pipeline():
    """Tạo instance không qua __init__ (bypass camera/model) + khởi tạo dict cần cho test."""
    p = VideoPipeline.__new__(VideoPipeline)
    p._track_vehicle_history = {}
    p._vehicle_vote_window_sec = 2.5
    p._vehicle_vote_min_samples = 3
    return p


def _make_group(vehicle_type, track_id):
    """Tạo group giả chỉ chứa các field _smooth_vehicle_type cần đọc."""
    return {
        '_person': _det('person', (100, 100, 200, 300)),
        '_vehicle': None,
        'track_id': track_id,
        'helmet_dets': [],
        'plate_dets': [],
        'vehicle_type': vehicle_type,
    }


def test_smooth_vote_majority_corrects_one_off_misassignment():
    """UT3: track_id đã vote đúng 'motorcycle' 3 frame liên tiếp, frame thứ 4 bị
    gán nhầm 'bicycle' (do nearest-neighbor lệch) — vote đa số phải giữ được
    'motorcycle' thay vì bị 1 frame lỗi lấn át."""
    p = _pipeline()
    tid = 7
    groups_hist = [
        _make_group('motorcycle', tid),
        _make_group('motorcycle', tid),
        _make_group('motorcycle', tid),
        _make_group('bicycle', tid),   # frame lỗi
    ]
    t = time.time()
    for i, g in enumerate(groups_hist):
        p._smooth_vehicle_type([g], now=t + i * 0.1)
    assert groups_hist[-1]['vehicle_type'] == 'motorcycle'


def test_smooth_vote_corrects_pedestrian_mislabeled_as_motorcycle():
    """UT3: 1 frame gán nhầm người đi bộ thành motorcycle (do gần xe máy khác ở
    cùng 'độ sâu') — nhưng 4 frame trước đều đúng None → vote đa số phải trả
    None (người đi bộ)."""
    p = _pipeline()
    tid = 9
    g_none = _make_group(None, tid)
    g_err = _make_group('motorcycle', tid)
    t = time.time()
    # 4 frame đúng + 1 frame lỗi
    for i, g in enumerate([g_none, g_none, g_none, g_none, g_err]):
        p._smooth_vehicle_type([g], now=t + i * 0.1)
    assert g_err['vehicle_type'] is None


def test_smooth_vote_keeps_first_frame_until_enough_samples():
    """UT3: khi mới có < min_samples mẫu → KHÔNG vote, giữ nguyên kết quả
    frame hiện tại (tránh đổi vehicle_type khi tracker vừa xuất hiện)."""
    p = _pipeline()
    tid = 11
    g = _make_group('motorcycle', tid)
    t = time.time()
    p._smooth_vehicle_type([g], now=t)
    # chỉ có 1 mẫu < min_samples (3) → không đổi
    assert g['vehicle_type'] == 'motorcycle'


def test_smooth_vote_skips_when_no_track_id():
    """UT3 fallback: track_id=None → không vote (giữ nguyên kết quả frame)."""
    p = _pipeline()
    g = _make_group('motorcycle', None)
    p._smooth_vehicle_type([g], now=time.time())
    assert g['vehicle_type'] == 'motorcycle'


def test_smooth_vote_expires_old_samples_outside_window():
    """UT3: mẫu quá cũ (> window_sec) bị loại khỏi vote, tránh trường hợp
    người đi bộ từ 30s trước vẫn ảnh hưởng vote hiện tại."""
    p = _pipeline()
    tid = 13
    g_old = _make_group('motorcycle', tid)
    g_new = _make_group(None, tid)
    t = time.time()
    p._smooth_vehicle_type([g_old], now=t)
    # Sau window_sec+epsilon chỉ còn g_new là hợp lệ (< min_samples nên giữ)
    p._smooth_vehicle_type([g_new], now=t + p._vehicle_vote_window_sec + 0.5)
    assert g_new['vehicle_type'] is None


# ─── C2: plate assignment và needs_review ─────────────────────────────────────

def test_plate_not_shared_between_two_nearby_vehicles():
    """C2: hai xe ở gần nhau không dùng chung biển số. Mỗi xe phải có biển
    riêng được gán đúng vào group của nó, không nhầm lẫn biển của xe bên cạnh."""
    # Xe 1 ở bên trái
    person1 = _det("person", (80, 100, 160, 300))
    vehicle1 = _det("motorcycle", (70, 150, 170, 310))
    plate1 = _det("license-plate", (75, 200, 165, 230))  # biển xe 1

    # Xe 2 ở bên phải, rất gần xe 1
    person2 = _det("person", (200, 100, 280, 300))
    vehicle2 = _det("motorcycle", (190, 150, 290, 310))
    plate2 = _det("license-plate", (195, 200, 285, 230))  # biển xe 2

    groups, _ = _pipeline()._group_by_person(
        [person1, person2], [], [plate1, plate2], [vehicle1, vehicle2]
    )

    # Mỗi group có đúng 1 plate, không phải 2
    assert len(groups) == 2
    for g in groups:
        assert len(g['plate_dets']) == 1

    # Plate gần nhất với xe 1 không bị gán vào xe 2
    g1 = next(g for g in groups if g['_person'].bbox[0] < 180)
    assert g1['_vehicle'] is not None
    assert g1['_vehicle'].bbox[0] < 180  # vehicle bên trái

    g2 = next(g for g in groups if g['_person'].bbox[0] > 180)
    assert g2['_vehicle'] is not None
    assert g2['_vehicle'].bbox[0] > 180  # vehicle bên phải

    # Plate bên trái thuộc group bên trái
    assert g1['plate_dets'][0].bbox[0] < 180
    # Plate bên phải thuộc group bên phải
    assert g2['plate_dets'][0].bbox[0] > 180


def test_helmet_on_head_cut_by_top_edge_is_not_judged():
    """Person box at the frame top: the 'head' region is chin/neck, so no
    helmet call (either way) — it was a coin toss on the gate recording."""
    p = _pipeline()
    cut = _det('person', (100, 0, 200, 300))
    whole = _det('person', (300, 40, 400, 340))
    helmets = [_det('With Helmet', (130, 5, 170, 40)), _det('Without Helmet', (330, 45, 370, 80))]
    groups, matched = p._group_by_person([cut, whole], helmets, [], [])
    assert groups[0]['helmet_dets'] == [] and 'head_cut_by_frame' in groups[0]['association_reasons']
    assert [d.class_name for d in groups[1]['helmet_dets']] == ['Without Helmet']
    assert [d.class_name for d in matched] == ['Without Helmet']
