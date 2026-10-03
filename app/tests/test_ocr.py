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


def test_electric_bike_md_series_registered_and_ocr_forms_match():
    from app.cv.ocr import normalize_valid_plate
    from app.db import normalize_plate as db_normalize
    registered = db_normalize("29MĐ1-123.45")
    ocr_read = normalize_plate("29MD1 123.45")
    assert registered == ocr_read == "29MD112345"
    assert validate_plate_format(ocr_read) is True
    assert normalize_valid_plate(ocr_read) == "29MD112345"


def test_normalize_then_validate_roundtrip():
    # OCR thường trả về có gạch ngang/khoảng trắng — normalize trước khi validate
    raw = "59-H1 123.45"
    normalized = normalize_plate(raw)
    assert validate_plate_format(normalized) is True
