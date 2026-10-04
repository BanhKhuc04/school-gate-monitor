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
    return VideoPipeline.__new__(VideoPipeline)  # skip __init__ (no camera/models)


def _det(class_name, bbox):
    return Detection(class_name=class_name, confidence=0.9, bbox=bbox)


def test_vertical_overlap_true_when_y_ranges_intersect():
    assert VideoPipeline._vertical_overlap((0, 100, 50, 200), (10, 150, 60, 250)) is True


def test_vertical_overlap_false_when_y_ranges_disjoint():
    assert VideoPipeline._vertical_overlap((0, 0, 50, 50), (0, 500, 50, 600)) is False


def test_rider_matched_when_x_close_and_y_overlaps():
    """Người thật sự đứng/ngồi trên xe — box person và vehicle chồng lấp cả X lẫn Y."""
    person = _det("person", (100, 100, 200, 300))
    vehicle = _det("motorcycle", (90, 150, 210, 320))
    groups = _pipeline()._group_by_person([person], [], [], [vehicle])
    assert groups[0]["vehicle_type"] == "motorcycle"


def test_pedestrian_not_matched_to_vehicle_at_different_depth():
    """Người đi bộ thẳng hàng X với 1 xe máy nhưng ở 'độ sâu' khác (Y disjoint hẳn)
    — trước đây bị gán nhầm thành người đi xe chỉ vì gần theo X, giờ không còn nữa."""
    person = _det("person", (100, 500, 200, 700))       # gần đáy khung (gần camera)
    vehicle = _det("motorcycle", (100, 50, 200, 150))    # xa tít đỉnh khung (xa camera)
    groups = _pipeline()._group_by_person([person], [], [], [vehicle])
    assert groups[0]["vehicle_type"] is None
    assert groups[0]["_vehicle"] is None


def test_no_vehicle_nearby_stays_pedestrian():
    person = _det("person", (100, 100, 200, 300))
    groups = _pipeline()._group_by_person([person], [], [], [])
    assert groups[0]["vehicle_type"] is None


def test_rider_detected_by_plate_when_motorcycle_missed():
    """COCO bỏ sót xe máy (bị che) nhưng có biển số ngay dưới người → vẫn là
    người đi xe máy, không bị coi là người đi bộ (mất hết vi phạm)."""
    person = _det("person", (100, 100, 200, 400))
    plate = _det("plate", (130, 380, 170, 410))   # dưới chân, trong bề ngang người
    groups = _pipeline()._group_by_person([person], [], [plate], [])
    assert groups[0]["vehicle_type"] == "motorcycle"


def test_plate_far_above_person_does_not_make_rider():
    """Biển số ở tận phía trên đầu người (xe khác ở xa) → vẫn là người đi bộ."""
    person = _det("person", (100, 300, 200, 600))
    plate = _det("plate", (130, 100, 170, 130))
    groups = _pipeline()._group_by_person([person], [], [plate], [])
    assert groups[0]["vehicle_type"] is None
