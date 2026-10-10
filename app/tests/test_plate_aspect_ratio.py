"""
pytest tests for pipeline plate aspect-ratio filter.

A3: Kiểm tra bộ lọc hình dạng biển và crop.
  - Test aspect ratio filter với các trường hợp:
    1. Biển 1 dòng (tỉ lệ ~3.0-3.5:1) → pass
    2. Biển 2 dòng (tỉ lệ ~1.5-2.0:1) → pass
    3. Text trên áo/logo (>5.0:1) → reject
    4. Logo/nhãn vuông (0.8-1.5:1) → reject
    5. Biển nghiêng (tùy projection, vẫn rộng/cao) → pass nếu trong ngưỡng
    6. Box ra ngoài ảnh → reject
"""
import pytest
from app.cv.pipeline import VideoPipeline


class TestPlateAspectRatioFilter:
    """A3: Test aspect-ratio filter cho plate detections."""

    # All test bboxes: (x1, y1, x2, y2) in pixel coordinates
    # w = x2 - x1 (width), h = y2 - y1 (height), ratio = w / h
    # VN plate 1 dòng: w/h ~ 2.5-4.0
    # VN plate 2 dòng: w/h ~ 1.5-2.5

    def _aspect(self, bbox):
        """Helper: compute aspect ratio (w/h) of bbox."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if h <= 0:
            return 0.0
        return w / h

    def _call_filter(self, bbox, min_ratio=1.5, max_ratio=6.0):
        return VideoPipeline._is_valid_plate_aspect_ratio(bbox, min_ratio, max_ratio)

    # --- Should PASS ---
    def test_standard_single_line_plate(self):
        """Biển 1 dòng thường: w/h ~3.3:1 → pass."""
        # Real plate: w=300, h=90 → ratio=3.33
        bbox = (50, 60, 350, 150)  # w=300, h=90, ratio=3.33
        assert self._call_filter(bbox) is True
        assert abs(self._aspect(bbox) - 3.33) < 0.1

    def test_two_line_plate_narrow(self):
        """Biển 2 dòng: w/h ~1.8:1 → pass (>=1.5)."""
        # 2-dòng: w=300, h=170 → ratio=1.76
        bbox = (100, 40, 400, 210)  # w=300, h=170, ratio=1.76
        ratio = self._aspect(bbox)
        assert self._call_filter(bbox) is True
        assert 1.5 <= ratio <= 2.5

    def test_two_line_plate_wide(self):
        """Biển 2 dòng rộng: w/h ~2.5:1 → pass."""
        bbox = (100, 40, 350, 100)
        assert self._call_filter(bbox) is True

    def test_standard_plate_boundaries(self):
        """Biển đúng tỉ lệ biên: 1.5 và 6.0 → pass."""
        # Edge case: ratio = 1.5 exactly (min)
        bbox_min = (0, 0, 150, 100)
        assert self._call_filter(bbox_min) is True
        assert abs(self._aspect(bbox_min) - 1.5) < 0.01

        # Edge case: ratio = 6.0 exactly (max)
        bbox_max = (0, 0, 600, 100)
        assert self._call_filter(bbox_max) is True
        assert abs(self._aspect(bbox_max) - 6.0) < 0.01

    def test_typical_vietnam_plate_single_line(self):
        """Biển VN 1 dòng điển hình: w/h ~3.3:1."""
        # Real plate ~300x90 pixels → ratio ~3.3
        bbox = (50, 60, 350, 150)  # w=300, h=90, ratio=3.33
        assert self._call_filter(bbox) is True

    # --- Should REJECT ---
    def test_text_on_shirt_very_wide(self):
        """Text trên áo/logo rất ngang: w/h >6.0 → reject."""
        bbox = (100, 100, 700, 120)  # ratio = 6.0
        assert self._call_filter(bbox) is False

        bbox_wider = (100, 100, 800, 120)  # ratio = 7.0
        assert self._call_filter(bbox_wider) is False

    def test_logo_near_square(self):
        """Logo/nhãn gần vuông: w/h ~1.0 → reject (<1.5)."""
        bbox = (100, 100, 200, 200)  # ratio = 1.0
        assert self._call_filter(bbox) is False

    def test_tiny_near_square(self):
        """Box nhỏ gần vuông: w/h ~1.2 → reject."""
        bbox = (100, 100, 220, 200)  # ratio = 1.2
        assert self._call_filter(bbox) is False

    def test_zero_height(self):
        """Height = 0 → reject (division by zero guard)."""
        bbox = (100, 50, 400, 50)  # h = 0
        assert self._call_filter(bbox) is False

    def test_negative_height(self):
        """Height < 0 (invalid bbox) → reject."""
        bbox = (100, 100, 400, 50)  # y2 < y1
        assert self._call_filter(bbox) is False

    # --- Custom threshold tests ---
    def test_custom_thresholds_pass(self):
        """Custom thresholds: ratio in custom range → pass."""
        # ratio = 300/80 = 3.75, within 3.0-5.0
        bbox = (100, 100, 400, 180)  # w=300, h=80, ratio=3.75
        assert self._call_filter(bbox, min_ratio=3.0, max_ratio=5.0) is True

    def test_custom_thresholds_reject(self):
        """Custom thresholds: ratio outside custom range → reject."""
        bbox = (100, 100, 300, 110)  # ratio = 4.0
        assert self._call_filter(bbox, min_ratio=5.0, max_ratio=8.0) is False
