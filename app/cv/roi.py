"""
Vùng nhận diện (ROI) — giới hạn detect trong 1 đa giác trên khung hình, bỏ mọi
vật thể có tâm nằm ngoài vùng. Tách riêng khỏi pipeline.py để test được mà
không cần load model (giống app/cv/event_correlator.py).

Toạ độ điểm lưu dạng tỉ lệ % khung hình (0.0-1.0) để không phụ thuộc độ phân
giải camera — quy đổi sang pixel bằng to_pixel_polygon() ngay trước khi dùng.
"""
import cv2
import numpy as np

from app.cv.detector import Detection


def parse_points(raw: list) -> list[tuple[float, float]] | None:
    """Validate danh sách điểm [[x,y], ...] dạng tỉ lệ 0.0-1.0.

    [] (rỗng) → None, nghĩa là tắt ROI (không giới hạn vùng).
    < 3 điểm (mà không rỗng) hoặc điểm ngoài [0,1] → ValueError.
    """
    if not raw:
        return None
    if len(raw) < 3:
        raise ValueError("ROI polygon cần ít nhất 3 điểm")

    points = []
    for p in raw:
        if len(p) != 2:
            raise ValueError(f"Điểm không hợp lệ: {p}")
        x, y = float(p[0]), float(p[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"Toạ độ phải trong [0,1], nhận: ({x}, {y})")
        points.append((x, y))
    return points


def to_pixel_polygon(points: list[tuple[float, float]] | None, width: int, height: int) -> np.ndarray | None:
    """Quy đổi điểm tỉ lệ % sang toạ độ pixel (int32 Nx2, dùng cho cv2)."""
    if points is None:
        return None
    return np.array([[round(x * width), round(y * height)] for x, y in points], dtype=np.int32)


def _center_in_polygon(bbox: tuple, polygon_px: np.ndarray) -> bool:
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return cv2.pointPolygonTest(polygon_px, (cx, cy), False) >= 0


def filter_by_roi(dets: list[Detection], polygon_px: np.ndarray | None) -> list[Detection]:
    """Lọc dets có tâm bbox nằm trong polygon_px. None = không lọc (giữ nguyên)."""
    if polygon_px is None:
        return dets
    return [d for d in dets if _center_in_polygon(d.bbox, polygon_px)]
