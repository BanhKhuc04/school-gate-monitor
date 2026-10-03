"""
pytest tests for app/cv/ocr.py — OCR initialization, readtext parameters, and error handling.

A1 (Đợt A): Fix EasyOCR allowlist/paragraph from Reader() to readtext().
  - allowlist/paragraph are readtext() parameters, NOT Reader.__init__() parameters.
  - Previously: easyocr.Reader(..., allowlist=..., paragraph=False) → TypeError.
  - Fixed: Reader() uses valid params only; allowlist/paragraph passed to readtext().
  - Error handling: exceptions from reader.readtext() return empty result, not crash.
"""
import numpy as np
import pytest
import easyocr

from app.cv.ocr import (
    normalize_plate,
    validate_plate_format,
    read_plate,
    read_plate_detailed,
    _get_reader,
    _PLATE_ALLOWLIST,
    _OCR_MIN_CONF,
)


class TestOcrInitialization:
    """A1 test: Reader must initialize WITHOUT allowlist/paragraph (they are readtext params)."""

    def test_reader_init_no_allowlist_error(self):
        """P0: Reader creation must not raise TypeError about allowlist/paragraph."""
        # Force re-init by clearing the module-level cache
        import app.cv.ocr as ocr_module
        ocr_module._reader = None

        try:
            reader = _get_reader()
            assert reader is not None
            assert isinstance(reader, easyocr.easyocr.Reader)
        finally:
            # Reset for other tests
            ocr_module._reader = None

    def test_reader_init_params_valid(self):
        """Verify EasyOCR Reader.__init__ does NOT accept allowlist/paragraph."""
        import inspect
        params = list(inspect.signature(easyocr.Reader.__init__).parameters.keys())
        assert 'allowlist' not in params, "allowlist should be readtext() param, not Reader()"
        assert 'paragraph' not in params, "paragraph should be readtext() param, not Reader()"

    def test_readtext_accepts_allowlist_and_paragraph(self):
        """Verify EasyOCR readtext() DOES accept allowlist/paragraph."""
        import inspect
        params = list(inspect.signature(easyocr.Reader.readtext).parameters.keys())
        assert 'allowlist' in params, "allowlist must be a readtext() parameter"
        assert 'paragraph' in params, "paragraph must be a readtext() parameter"


class TestOcrAllowlistConstants:
    """A1: allowlist and min_conf are constants used in readtext()."""

    def test_plate_allowlist_defined(self):
        """_PLATE_ALLOWLIST must contain VN plate characters."""
        assert _PLATE_ALLOWLIST is not None
        assert len(_PLATE_ALLOWLIST) > 0
        # VN plate: digits + letters + hyphen
        assert all(c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-' for c in _PLATE_ALLOWLIST)

    def test_ocr_min_conf_positive(self):
        """_OCR_MIN_CONF must be a positive float."""
        assert isinstance(_OCR_MIN_CONF, float)
        assert 0.0 < _OCR_MIN_CONF < 1.0


class TestOcrErrorHandling:
    """A1: Engine errors must not crash pipeline — return empty result instead."""

    def test_read_plate_none_returns_empty(self):
        """read_plate(None) must return empty string, not raise."""
        result = read_plate(None)
        assert result == ""

    def test_read_plate_empty_array_returns_empty(self):
        """read_plate(empty array) must return empty string."""
        result = read_plate(np.array([]))
        assert result == ""

    def test_read_plate_too_small_returns_empty(self):
        """read_plate(crop too small) must return empty string."""
        small = np.zeros((10, 50, 3), dtype=np.uint8)  # h=10 < 20, w=50 >= 40
        result = read_plate(small)
        assert result == ""

    def test_read_plate_detailed_none_returns_empty(self):
        """read_plate_detailed(None) must return empty dict, not raise."""
        result = read_plate_detailed(None)
        assert result == {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}

    def test_read_plate_detailed_too_small_returns_empty(self):
        """read_plate_detailed(crop too small) must return empty dict."""
        small = np.zeros((10, 50, 3), dtype=np.uint8)  # h=10 < 20, w=50 >= 40
        result = read_plate_detailed(small)
        assert result == {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}

    def test_read_plate_corrupted_image_returns_empty(self):
        """read_plate(corrupted image) must return empty string, not crash pipeline."""
        # Corrupted image: unusual dtype or weird dimensions
        corrupted = np.zeros((60, 100, 3), dtype=np.float32)  # float, not uint8
        result = read_plate(corrupted)
        # Should return "" or dict with empty strings, not raise
        assert isinstance(result, str)
        # Accept empty string as valid recovery
        assert result == ""


class TestPlateNormalization:
    """Tests for plate normalization and validation."""

    def test_normalize_uppercase(self):
        assert normalize_plate("59H112345") == "59H112345"
        assert normalize_plate("abc123") == "ABC123"

    def test_normalize_strips_whitespace_and_dash(self):
        assert normalize_plate("59-H1-12345") == "59H112345"
        assert normalize_plate("59 H1 12345") == "59H112345"

    def test_normalize_strips_special_chars(self):
        assert normalize_plate("59.H1@12345!") == "59H112345"

    def test_normalize_empty(self):
        assert normalize_plate("") == ""
        assert normalize_plate(None) == ""

    def test_validate_common_format(self):
        assert validate_plate_format("59H112345") is True
        assert validate_plate_format("30A12345") is True
        assert validate_plate_format("51F123456") is True

    def test_validate_two_letter_series(self):
        assert validate_plate_format("59AB1234") is True

    def test_validate_invalid_short(self):
        assert validate_plate_format("59H1") is False

    def test_validate_invalid_no_letters(self):
        assert validate_plate_format("59112345") is False

    def test_validate_empty(self):
        assert validate_plate_format("") is False

    def test_normalize_then_validate_roundtrip(self):
        """OCR returns raw text with dashes/spaces — must normalize before validate."""
        raw = "59-H1 123.45"
        normalized = normalize_plate(raw)
        assert validate_plate_format(normalized) is True
