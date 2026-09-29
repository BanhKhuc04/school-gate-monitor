"""
Test cho `VideoPipeline._is_touching_frame_edge` — bỏ qua đánh giá vi phạm khi
xe/người còn chạm mép khung hình (có thể chưa vào/đang ra hết khung), tránh báo
sai NO_PLATE/PLATE_OBSCURED chỉ vì biển số chưa kịp lọt vào khung hình.

Static method, không cần load model YOLO nào để test.
"""
from app.cv.pipeline import VideoPipeline


FRAME_W, FRAME_H = 1000, 1000  # margin 3% => 30px mỗi cạnh


def test_bbox_fully_inside_frame_is_not_touching_edge():
    assert VideoPipeline._is_touching_frame_edge((100, 100, 900, 900), FRAME_W, FRAME_H) is False


def test_bbox_touching_left_edge():
    assert VideoPipeline._is_touching_frame_edge((0, 400, 200, 600), FRAME_W, FRAME_H) is True


def test_bbox_touching_right_edge():
    assert VideoPipeline._is_touching_frame_edge((800, 400, 1000, 600), FRAME_W, FRAME_H) is True


def test_bbox_touching_top_edge():
    assert VideoPipeline._is_touching_frame_edge((400, 0, 600, 200), FRAME_W, FRAME_H) is True


def test_bbox_touching_bottom_edge():
    assert VideoPipeline._is_touching_frame_edge((400, 800, 600, 1000), FRAME_W, FRAME_H) is True


def test_bbox_just_inside_margin_is_not_touching():
    # Margin = 30px (3% của 1000) — bbox cách mép 31px là AN TOÀN, chưa chạm.
    assert VideoPipeline._is_touching_frame_edge((31, 31, 969, 969), FRAME_W, FRAME_H) is False
