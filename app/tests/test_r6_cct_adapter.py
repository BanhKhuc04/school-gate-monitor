"""R6 — Smoke test CCT FastPlateOCR adapter (Owner A).

Theo handoff §3 R6:
- Smoke local `models/cct/cct_s_v2_global.onnx` + YAML bằng package 1.1.0 thật.
- Kiểm dạng return/confidence/padding và finite values, RGB uint8, input
  shape/config/hash.
- Adapter KHÔNG tự chốt khi lỗi, không load pickle.

Test dùng mock recognizer để tránh load model ONNX thật, vẫn verify adapter
contract (RGB, config hash, char_confidences, valid/invalid plate).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import yaml

from app.cv.fast_plate_ocr import FastPlateOCRAdapter


# ── helpers ────────────────────────────────────────────────────────────────


def _make_model_and_config(tmp_path, color_mode="rgb", max_slots=10,
                          alphabet=None):
    """Tạo file ONNX giả + YAML config trong tmp_path."""
    if alphabet is None:
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    model_path = tmp_path / "cct.onnx"
    # ONNX thật có magic bytes; giả lập bằng binary content
    model_path.write_bytes(b"ONNX_FAKE_MODEL_" + b"\x00" * 128)
    config_path = tmp_path / "config.yaml"
    cfg = {
        "image_color_mode": color_mode,
        "max_plate_slots": max_slots,
        "alphabet": alphabet,
    }
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return model_path, config_path


# ── 1. Reject khi file ONNX / config thiếu ───────────────────────────────


def test_reject_when_model_missing(tmp_path):
    """Nếu model_path không tồn tại → raise ValueError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("image_color_mode: rgb\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ONNX"):
        FastPlateOCRAdapter(str(tmp_path / "missing.onnx"), str(config_path))


def test_reject_when_config_missing(tmp_path):
    """Nếu config_path không tồn tại → raise ValueError."""
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"ONNX_FAKE")
    with pytest.raises(ValueError, match="ONNX"):
        FastPlateOCRAdapter(str(model_path), str(tmp_path / "missing.yaml"))


# ── 2. Reject khi config sai color mode ─────────────────────────────────


def test_reject_wrong_color_mode(tmp_path):
    """Config phải có image_color_mode='rgb' (BGR không hỗ trợ)."""
    model_path, config_path = _make_model_and_config(tmp_path, color_mode="bgr")
    with pytest.raises(ValueError, match="RGB"):
        FastPlateOCRAdapter(str(model_path), str(config_path))


# ── 3. Hash SHA256 file đúng ────────────────────────────────────────────


def test_model_and_config_hashes_computed(tmp_path):
    """model_hash và config_hash phải là SHA256 hex digest của file bytes."""
    model_path, config_path = _make_model_and_config(tmp_path)
    import hashlib
    expected_model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    expected_config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

    # Patch recognizer để không load ONNX thật
    mock_recognizer_class = MagicMock()
    mock_recognizer_instance = MagicMock()
    mock_recognizer_class.return_value = mock_recognizer_instance

    adapter = FastPlateOCRAdapter(
        str(model_path), str(config_path),
        recognizer_factory=mock_recognizer_class,
    )
    assert adapter.model_hash == expected_model_hash
    assert adapter.config_hash == expected_config_hash
    assert len(adapter.model_hash) == 64  # SHA256 hex length


# ── 4. Recognizer được gọi với RGB uint8 ────────────────────────────────


def test_recognizer_called_with_rgb_uint8(tmp_path):
    """Adapter phải convert BGR→RGB và đảm bảo uint8 trước khi gọi recognizer."""
    model_path, config_path = _make_model_and_config(tmp_path)
    # Mock recognizer
    mock_recognizer = MagicMock()
    # Trả về tuple (prediction,) — prediction có plate và char_probs
    mock_prediction = MagicMock()
    mock_prediction.plate = "59A123"
    mock_prediction.char_probs = np.array([0.9, 0.9, 0.9, 0.9, 0.9, 0.9], dtype=float)
    mock_recognizer.run = MagicMock(return_value=[mock_prediction])

    mock_factory = MagicMock(return_value=mock_recognizer)
    adapter = FastPlateOCRAdapter(
        str(model_path), str(config_path),
        recognizer_factory=mock_factory,
    )

    # Tạo crop BGR uint8
    crop = np.zeros((40, 120, 3), dtype=np.uint8)
    crop[:, :, 0] = 100  # B
    crop[:, :, 1] = 150  # G
    crop[:, :, 2] = 200  # R

    adapter.read(crop)
    # Verify recognizer.run được gọi với RGB
    args, kwargs = mock_recognizer.run.call_args
    rgb_input = args[0]
    assert rgb_input.dtype == np.uint8
    assert rgb_input.shape == crop.shape
    # Verify đã convert: pixel (0, 0) R channel gốc = 200 → vị trí khác trong RGB
    # Trong BGR (0, 0, 0) = (B=100, G=150, R=200). Trong RGB = (R=200, G=150, B=100).
    assert rgb_input[0, 0, 0] == 200  # R channel trong RGB
    assert rgb_input[0, 0, 2] == 100  # B channel trong RGB


# ── 5. Return shape: dict có đủ key engine/hash/confidence ──────────────


def test_return_dict_has_required_keys(tmp_path):
    """Result dict phải có engine='FastPlateOCR', model_hash, config_hash,
    char_confidences (list), confidence (float)."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_recognizer = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.plate = "59A123"
    mock_prediction.char_probs = np.array([0.9] * 6, dtype=float)
    mock_recognizer.run = MagicMock(return_value=[mock_prediction])
    mock_factory = MagicMock(return_value=mock_recognizer)
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)

    crop = np.zeros((40, 120, 3), dtype=np.uint8)
    result = adapter.read(crop)

    assert isinstance(result, dict)
    assert result["engine"] == "FastPlateOCR"
    assert result["model_hash"] == adapter.model_hash
    assert result["config_hash"] == adapter.config_hash
    assert isinstance(result["char_confidences"], list)
    assert len(result["char_confidences"]) == 6
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["raw_text"] == "59A123"


# ── 6. Reject invalid input (None, empty, wrong dtype) ──────────────────


def test_reject_none_crop(tmp_path):
    """read(None) → raise ValueError."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_factory = MagicMock(return_value=MagicMock())
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)
    with pytest.raises(ValueError, match="uint8"):
        adapter.read(None)


def test_reject_empty_crop(tmp_path):
    """read(empty array) → raise ValueError."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_factory = MagicMock(return_value=MagicMock())
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)
    with pytest.raises(ValueError, match="uint8"):
        adapter.read(np.zeros((0, 0, 3), dtype=np.uint8))


def test_reject_non_uint8_crop(tmp_path):
    """read(float array) → raise ValueError (chỉ chấp nhận uint8)."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_factory = MagicMock(return_value=MagicMock())
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)
    with pytest.raises(ValueError, match="uint8"):
        adapter.read(np.zeros((40, 120, 3), dtype=np.float32))


def test_reject_wrong_channel_count(tmp_path):
    """read(1-channel or 4-channel) → raise ValueError (chỉ 3 channel)."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_factory = MagicMock(return_value=MagicMock())
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)
    with pytest.raises(ValueError, match="three channel"):
        adapter.read(np.zeros((40, 120), dtype=np.uint8))  # 2D
    with pytest.raises(ValueError, match="three channel"):
        adapter.read(np.zeros((40, 120, 4), dtype=np.uint8))  # 4 channel


# ── 7. needs_review khi confidence thấp ────────────────────────────────


def test_needs_review_when_low_confidence(tmp_path):
    """Plate hợp lệ nhưng char_confidence < 0.7 → needs_review=True."""
    model_path, config_path = _make_model_and_config(tmp_path)
    mock_recognizer = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.plate = "59A123"
    # 6 char, mỗi char 0.5 < 0.7
    mock_prediction.char_probs = np.array([0.5] * 6, dtype=float)
    mock_recognizer.run = MagicMock(return_value=[mock_prediction])
    mock_factory = MagicMock(return_value=mock_recognizer)
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)

    crop = np.zeros((40, 120, 3), dtype=np.uint8)
    result = adapter.read(crop)
    assert result["needs_review"] is True
    assert result["confidence"] < 0.7


# ── 8. needs_review khi length vượt max_plate_slots ────────────────────


def test_needs_review_when_plate_too_long(tmp_path):
    """Plate > max_plate_slots → needs_review=True (không tự cắt/sửa)."""
    model_path, config_path = _make_model_and_config(tmp_path, max_slots=10)
    mock_recognizer = MagicMock()
    mock_prediction = MagicMock()
    mock_prediction.plate = "12345678901"  # 11 chars > 10
    mock_prediction.char_probs = np.array([0.9] * 11, dtype=float)
    mock_recognizer.run = MagicMock(return_value=[mock_prediction])
    mock_factory = MagicMock(return_value=mock_recognizer)
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)

    crop = np.zeros((40, 120, 3), dtype=np.uint8)
    result = adapter.read(crop)
    assert result["needs_review"] is True


# ── 9. Lock cho concurrent read ────────────────────────────────────────


def test_lock_prevents_concurrent_recognizer_runs(tmp_path):
    """Adapter dùng lock để tránh concurrent run() từ nhiều thread."""
    model_path, config_path = _make_model_and_config(tmp_path)
    call_count = {"n": 0, "max_concurrent": 0, "current": 0}
    lock = threading.Lock()

    def fake_run(rgb, return_confidence=True):
        with lock:
            call_count["current"] += 1
            call_count["max_concurrent"] = max(call_count["max_concurrent"],
                                                call_count["current"])
        try:
            prediction = MagicMock()
            prediction.plate = "59A123"
            prediction.char_probs = np.array([0.9] * 6, dtype=float)
            return [prediction]
        finally:
            with lock:
                call_count["current"] -= 1

    mock_recognizer = MagicMock()
    mock_recognizer.run = MagicMock(side_effect=fake_run)
    mock_factory = MagicMock(return_value=mock_recognizer)
    adapter = FastPlateOCRAdapter(str(model_path), str(config_path),
                                  recognizer_factory=mock_factory)

    crop = np.zeros((40, 120, 3), dtype=np.uint8)

    def worker():
        for _ in range(10):
            adapter.read(crop)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count["max_concurrent"] == 1, (
        f"Lock không hoạt động: max_concurrent={call_count['max_concurrent']}"
    )
    # 4 threads × 10 reads = 40 lần
    assert mock_recognizer.run.call_count == 40
