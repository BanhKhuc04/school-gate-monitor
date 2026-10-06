"""Vietnamese 2-line motorbike plates (e.g. "89-F1" / "237.92") OCR'd as ONE
crop can scramble line order on blur/skew. is_two_line_plate() gates a
dedicated top/bottom split + independent OCR per region instead of trusting
EasyOCR's own line grouping for square-ish crops.
"""
import numpy as np
import app.cv.ocr as ocr_module
from app.cv.ocr import is_two_line_plate, split_two_line_plate, read_plate_detailed


def test_is_two_line_plate_square_crop_is_two_line():
    square = np.zeros((100, 140, 3), dtype=np.uint8)  # w/h = 1.4 < 2.0
    assert is_two_line_plate(square) is True


def test_is_two_line_plate_wide_crop_is_single_line():
    wide = np.zeros((40, 200, 3), dtype=np.uint8)  # w/h = 5.0 >= 2.0
    assert is_two_line_plate(wide) is False


def test_split_two_line_plate_overlaps_the_middle():
    crop = np.zeros((100, 140, 3), dtype=np.uint8)
    top, bottom = split_two_line_plate(crop)
    assert top.shape[0] == 56  # 0..56%
    assert bottom.shape[0] == 56  # 44%..100%
    # The overlap band (44%-56%) must be included in BOTH halves, not cut away.
    assert top.shape[0] + bottom.shape[0] > crop.shape[0]


class _FakeReader:
    """Returns a different canned result per call, in call order — lets a
    test tell the top-region OCR call apart from the bottom-region call."""
    def __init__(self, results_per_call):
        self.results_per_call = list(results_per_call)
        self.regions_seen = []

    def readtext(self, region, allowlist=None, paragraph=False):
        self.regions_seen.append(region.shape)
        return self.results_per_call.pop(0)


def test_read_plate_detailed_two_line_ocrs_top_and_bottom_separately(monkeypatch):
    fake = _FakeReader([
        [([[0, 0], [60, 0], [60, 20], [0, 20]], '89-F1', 0.9)],   # top region call
        [([[0, 0], [60, 0], [60, 20], [0, 20]], '237.92', 0.8)],  # bottom region call
    ])
    monkeypatch.setattr(ocr_module, '_get_reader', lambda: fake)
    crop = np.full((100, 140, 3), 120, dtype=np.uint8)  # square-ish -> two-line path
    result = read_plate_detailed(crop)
    assert result['top_line'] == '89F1'
    assert result['bottom_line'] == '23792'
    assert result['full'] == '89F123792'
    assert len(fake.regions_seen) == 2  # exactly one OCR call per region, not a 3rd whole-crop call


def test_read_plate_detailed_single_line_keeps_whole_crop_path(monkeypatch):
    """A wide (1-line) crop must NOT take the split path — still one readtext()
    call over the whole crop, exercising the existing y-position split logic."""
    calls = []

    class _WholeCropReader:
        def readtext(self, region, allowlist=None, paragraph=False):
            calls.append(region.shape)
            return [([[0, 0], [60, 0], [60, 20], [0, 20]], '59H12345', 0.9)]

    monkeypatch.setattr(ocr_module, '_get_reader', lambda: _WholeCropReader())
    crop = np.full((40, 240, 3), 120, dtype=np.uint8)  # wide -> single-line path
    result = read_plate_detailed(crop)
    assert result['full'] == '59H12345'
    assert len(calls) == 1
