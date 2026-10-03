"""Tests for app.cv.char_plate_reader.

Covers:
- Adapter contract (no weights loaded at import)
- Lazy load fails gracefully on missing file / hash mismatch
- predict() returns error envelope, never raises
- merge_with_easyocr shapes agreement metadata
- Hash check pins the trained weights
"""
import os
import sys
import tempfile
import types

import numpy as np
import pytest


# Force-import without triggering ultralytics. The reader is lazy.
def test_import_does_not_load_weights():
    """Importing the module must not load the model. ultralytics may already be
    imported by other tests in the suite (e.g. detector tests); we only assert
    that the reader module itself starts with an unloaded model."""
    # Drop cached module to assert clean import
    sys.modules.pop("app.cv.char_plate_reader", None)
    import app.cv.char_plate_reader as mod
    reader = mod.CharPlateReader()
    assert mod.CharPlateReader is not None
    # The reader must report itself unloaded at construction time.
    assert reader.is_loaded is False
    assert reader._model is None


def test_reader_predict_empty_crop_returns_error_envelope(monkeypatch):
    """Empty crop must yield error envelope, never raise."""
    import app.cv.char_plate_reader as mod
    reader = mod.CharPlateReader(weights_path="/nonexistent/path.pt")
    result = reader.predict(None)
    assert result.error == "empty_crop"
    assert result.full == ""


def test_reader_load_missing_file_records_error_not_raise():
    import app.cv.char_plate_reader as mod
    reader = mod.CharPlateReader(weights_path="/no/such/file.pt")
    ok = reader.load_model()
    assert ok is False
    assert reader.is_loaded is False
    assert reader.load_error and reader.load_error.startswith("weights_not_found")
    # predict() must still respond gracefully
    result = reader.predict(np.zeros((50, 200, 3), dtype=np.uint8))
    assert result.error and result.error.startswith("weights_not_found")


def test_reader_load_hash_mismatch_refuses_weights(tmp_path, monkeypatch):
    """A weights file with wrong SHA must NOT load and must record mismatch."""
    import app.cv.char_plate_reader as mod
    bad = tmp_path / "bad.pt"
    bad.write_bytes(b"not-a-real-weights-file")
    reader = mod.CharPlateReader(
        weights_path=str(bad),
        expected_sha="0" * 64,  # some other expected hash
    )
    ok = reader.load_model()
    assert ok is False
    assert reader.load_error and reader.load_error.startswith("sha256_mismatch")
    # And predict() must surface that
    res = reader.predict(np.zeros((50, 200, 3), dtype=np.uint8))
    assert res.error and res.error.startswith("sha256_mismatch")


def test_reader_with_matching_hash_calls_predict(tmp_path, monkeypatch):
    """When hash matches and we stub out ultralytics, predict() must succeed."""
    import app.cv.char_plate_reader as mod

    fake_weights = tmp_path / "ok.pt"
    fake_weights.write_bytes(b"fake-weights-bytes")
    sha = _sha256_of(fake_weights)

    # Stub ultralytics.YOLO before reader instantiation so load_model works.
    fake_yolo = types.SimpleNamespace()
    captured = {}
    class _FakeTensor:
        """Behaves like a torch tensor on .cpu().tolist() for zero arrays."""
        def cpu(self):
            return self
        def tolist(self):
            return []
    class _FakeBoxes:
        xywhn = _FakeTensor()
        cls = _FakeTensor()
        conf = _FakeTensor()
    class _FakeResult:
        boxes = _FakeBoxes()
    class _FakeModel:
        def __init__(self, path):
            captured["path"] = path
        def predict(self, *args, **kwargs):
            captured["called"] = (args, kwargs)
            return [_FakeResult()]
    fake_yolo.YOLO = _FakeModel
    sys.modules["ultralytics"] = fake_yolo

    try:
        reader = mod.CharPlateReader(weights_path=str(fake_weights), expected_sha=sha)
        assert reader.load_model() is True
        assert reader.weights_sha256 == sha
        # predict() goes through read_char_crop which expects xywhn tensors;
        # our stub returns empty arrays — decode returns empty dict (no boxes).
        res = reader.predict(np.zeros((80, 240, 3), dtype=np.uint8))
        assert res.error is None
        assert res.full == ""
        assert res.engine == "yolov8n_char_v2"
        assert res.weights_sha256 == sha
        assert captured.get("path") == str(fake_weights)
    finally:
        sys.modules.pop("ultralytics", None)


def test_merge_with_easyocr_shapes_payload():
    """merge_with_easyocr must include both candidates and an agreement summary."""
    import app.cv.char_plate_reader as mod
    char = mod.CharReadResult(
        full="89F123792", top_line="89F1", bottom_line="23792",
        confidence=0.83, character_count=8, weights_sha256="abc",
    )
    easy = {"full": "89F123792", "top_line": "89F1", "bottom_line": "23792",
            "confidence": 0.61, "error": None}
    merged = mod.merge_with_easyocr(char, easy)
    assert merged["char_reader"]["full"] == "89F123792"
    assert merged["easyocr"]["full"] == "89F123792"
    assert merged["agreement"]["match"] is True
    assert merged["agreement"]["char_only"] is False
    assert merged["agreement"]["easy_only"] is False


def test_merge_disagreement_marks_char_only_or_easy_only():
    import app.cv.char_plate_reader as mod
    char = mod.CharReadResult(full="89F123792", top_line="89F1", bottom_line="23792",
                              confidence=0.83, character_count=8, weights_sha256="abc")
    easy = {"full": "", "confidence": 0.0}
    merged = mod.merge_with_easyocr(char, easy)
    assert merged["agreement"]["match"] is False
    assert merged["agreement"]["char_only"] is True
    assert merged["agreement"]["easy_only"] is False

    char2 = mod.CharReadResult(full="", top_line="", bottom_line="", confidence=0.0, weights_sha256="abc")
    easy2 = {"full": "59F199999", "confidence": 0.7}
    merged2 = mod.merge_with_easyocr(char2, easy2)
    assert merged2["agreement"]["match"] is False
    assert merged2["agreement"]["char_only"] is False
    # When the character reader also has empty `top_line`/`bottom_line`, easy_only wins.
    assert merged2["agreement"]["easy_only"] is True


def test_config_flag_defaults_off():
    """Default config must NOT auto-enable the new reader — review-only contract."""
    from app.config import CHAR_PLATE_READER_REVIEW_ONLY
    # The flag is read from env; without CHAR_PLATE_READER_REVIEW_ONLY=1 it is False.
    assert CHAR_PLATE_READER_REVIEW_ONLY is False


def _sha256_of(path):
    import hashlib
    return hashlib.sha256(open(str(path), "rb").read()).hexdigest()
