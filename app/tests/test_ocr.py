"""
pytest tests for app/cv/ocr.py — validate_plate_format (Vietnamese plate regex flag).
"""
from app.cv.ocr import validate_plate_format, normalize_plate


def test_valid_common_format():
    assert validate_plate_format("59H112345") is True
    assert validate_plate_format("30A12345") is True
    assert validate_plate_format("51F123456") is True


def test_valid_two_letter_series():
    assert validate_plate_format("59AB1234") is True


def test_invalid_too_short():
    assert validate_plate_format("59H1") is False


def test_invalid_no_letters():
    assert validate_plate_format("59112345") is False


def test_empty_string():
    assert validate_plate_format("") is False
    assert validate_plate_format(None) is False


def test_normalize_then_validate_roundtrip():
    # OCR thường trả về có gạch ngang/khoảng trắng — normalize trước khi validate
    raw = "59-H1 123.45"
    normalized = normalize_plate(raw)
    assert validate_plate_format(normalized) is True


# ─── Sửa ký tự nhầm theo vị trí + gom dòng (OCR mới) ───

import os
from pathlib import Path

import numpy as np
import pytest

from app.cv.ocr import correct_plate_text, group_into_lines, _prepare_crop


def test_correct_plate_text_fixes_letter_digit_confusions():
    assert correct_plate_text("S9K165O72") == "59K165072"   # S→5 (tỉnh), O→0 (số)
    assert correct_plate_text("598165072") == "59B165072"   # 8→B ở vị trí series
    assert correct_plate_text("65H9O7I4") == "65H90714"     # O→0, I→1 ở phần số


def test_correct_plate_text_never_breaks_valid_or_unfixable_text():
    assert correct_plate_text("59K165072") == "59K165072"
    assert correct_plate_text("59AB1234") == "59AB1234"     # series 2 chữ giữ nguyên
    assert correct_plate_text("ABCDEFGH") == "ABCDEFGH"     # sửa không ra định dạng → giữ bản gốc
    assert correct_plate_text("1319") == "1319"             # quá ngắn
    assert correct_plate_text("") == ""


def test_group_into_lines_orders_two_line_plate_left_to_right():
    # (text, conf, cx, cy, h) — dòng dưới đưa vào trước, box dòng trên lệch Y nhẹ
    boxes = [
        ("650", 0.9, 30, 80, 30), ("72", 0.9, 90, 81, 30),
        ("K1", 0.9, 80, 31, 30), ("59", 0.9, 20, 29, 30),
    ]
    assert group_into_lines(boxes) == ["59K1", "65072"]


def test_group_into_lines_single_line():
    boxes = [("12345", 0.9, 120, 40, 30), ("30A", 0.9, 40, 42, 30)]
    assert group_into_lines(boxes) == ["30A12345"]
    assert group_into_lines([]) == []


def test_prepare_crop_upscales_small_and_rejects_tiny():
    small = np.zeros((30, 40, 3), dtype=np.uint8)
    out = _prepare_crop(small)
    assert out.shape[0] == 160 and abs(out.shape[1] - 213) <= 1
    assert _prepare_crop(np.zeros((8, 40, 3), dtype=np.uint8)) is None
    assert _prepare_crop(None) is None


# ─── Hồi quy trên ảnh biển số thật (chỉ chạy khi máy đã có trọng số EasyOCR) ───

_SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples" / "plates"
_TRUTH = {
    "3xemay373.jpg": "59K165072", "3xemay378.jpg": "65S21319", "3xemay395.jpg": "59T160830",
    "3xemay396.jpg": "59F123865", "3xemay403.jpg": "59T101439", "3xemay411.jpg": "65H90714",
    "3xemay417.jpg": "71B251318", "3xemay431.jpg": "59S138731", "3xemay434.jpg": "70L137096",
}
_HAS_EASYOCR_WEIGHTS = (Path.home() / ".EasyOCR" / "model" / "craft_mlt_25k.pth").exists()


@pytest.mark.skipif(not _HAS_EASYOCR_WEIGHTS, reason="chưa tải trọng số EasyOCR (chạy scripts/prepare_demo.py)")
def test_ocr_reads_real_plates_at_camera_size():
    """Biển xe máy thật thu nhỏ còn cao 45px (cỡ thường gặp trên camera cổng
    1280x720) — bản OCR cũ chỉ đọc đúng 1/9, bản hiện tại đo được 6/9."""
    import cv2
    from app.cv.ocr import read_plate
    correct = 0
    for name, truth in _TRUTH.items():
        img = cv2.imread(str(_SAMPLES / name))
        h, w = img.shape[:2]
        img = cv2.resize(img, (round(w * 45 / h), 45), interpolation=cv2.INTER_AREA)
        correct += read_plate(img) == truth
    assert correct >= 5, f"OCR chỉ đọc đúng {correct}/9 biển"
