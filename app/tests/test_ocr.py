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


def test_char_engine_is_default_and_falls_back_to_easyocr(monkeypatch):
    import app.cv.ocr as ocr
    from types import SimpleNamespace
    monkeypatch.delenv('PLATE_OCR_ENGINE', raising=False)
    loaded = SimpleNamespace(is_loaded=True, predict=lambda crop: SimpleNamespace(
        full='89F123792', top_line='89F1', bottom_line='23792', confidence=.91,
        engine='yolov8n_char_v2', error=None))
    monkeypatch.setattr(ocr, '_char_reader', loaded)
    result = ocr.read_plate_detailed(object())
    assert result['engine'] == 'yolov8n_char_v2' and result['full'] == '89F123792'

    monkeypatch.setattr(ocr, '_char_reader', SimpleNamespace(is_loaded=False))
    monkeypatch.setattr(ocr, '_read_easyocr_locked', lambda crop: {'full': 'X', 'engine': 'EasyOCR'})
    assert ocr.read_plate_detailed(object())['engine'] == 'EasyOCR'


def test_char_engine_ambiguous_characters_need_review_not_engine_error(monkeypatch):
    import app.cv.ocr as ocr
    from types import SimpleNamespace
    monkeypatch.delenv('PLATE_OCR_ENGINE', raising=False)
    monkeypatch.setattr(ocr, '_char_reader', SimpleNamespace(is_loaded=True, predict=lambda crop: SimpleNamespace(
        full='', top_line='', bottom_line='', confidence=0.0, engine='yolov8n_char_v2',
        error='ambiguous_characters')))
    result = ocr.read_plate_detailed(object())
    assert result['needs_review'] is True and 'error' not in result


def test_normalize_then_validate_roundtrip():
    # OCR thường trả về có gạch ngang/khoảng trắng — normalize trước khi validate
    raw = "59-H1 123.45"
    normalized = normalize_plate(raw)
    assert validate_plate_format(normalized) is True
