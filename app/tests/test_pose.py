"""
pytest tests for posture detection (app/cv/pose.py).
Tests classify_posture heuristic and PostureDetector with mocked model.
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


def _kpt(x, y, conf=0.9):
    return {"x": float(x), "y": float(y), "confidence": conf}


# ─── classify_posture tests ─────────────────────────────────────────────────────

def test_classify_standing():
    """Straight leg → standing (angle ~180°)."""
    from app.cv.pose import classify_posture

    # In image coords (y increases downward): standing = hip above knee above ankle
    # left_hip(11) at (50,100), left_knee(13) at (50,120), left_ankle(15) at (50,140)
    #   v_hip=(0,-20), v_ankle=(0,20), dot=-400, |v_hip|=20, |v_ankle|=20
    #   cos=-400/400=-1, angle=180°
    kpts = [_kpt(0, 0) for _ in range(11)]  # 0-10: unused
    kpts += [
        _kpt(50, 100),  # 11: left_hip
        _kpt(50, 100),  # 12: right_hip (same position)
        _kpt(50, 120),  # 13: left_knee
        _kpt(50, 120),  # 14: right_knee
        _kpt(50, 140),  # 15: left_ankle
        _kpt(50, 140),  # 16: right_ankle
    ]
    result = classify_posture(kpts)
    assert result == "standing", f"Expected standing, got {result}"


def test_classify_riding():
    """Bent leg → riding (angle < 140°)."""
    from app.cv.pose import classify_posture

    # Hip above knee, ankle to the side → bent knee angle
    # left_hip(11) at (50,90), left_knee(13) at (50,120), left_ankle(15) at (70,130)
    #   v_hip=(0,-30), v_ankle=(20,10), dot=-300, |v_hip|=30, |v_ankle|≈22.4
    #   cos≈-0.447, angle≈116° (<140° → riding)
    kpts = [_kpt(0, 0) for _ in range(11)]  # 0-10
    kpts += [
        _kpt(50, 90),   # 11: left_hip
        _kpt(50, 90),   # 12: right_hip
        _kpt(50, 120),  # 13: left_knee
        _kpt(50, 120),  # 14: right_knee
        _kpt(70, 130),  # 15: left_ankle
        _kpt(70, 130),  # 16: right_ankle
    ]
    result = classify_posture(kpts)
    assert result == "riding", f"Expected riding, got {result}"


def test_classify_unknown_low_confidence():
    """Low-confidence keypoints → unknown."""
    from app.cv.pose import classify_posture

    kpts = [_kpt(0, 0, 0.1) for _ in range(17)]
    result = classify_posture(kpts)
    assert result == "unknown"


def test_classify_both_legs():
    """Average of both legs is used."""
    from app.cv.pose import classify_posture

    # Left leg: standing (~180°), Right leg: riding (<140°)
    # Average ~160° → unknown
    kpts = [_kpt(0, 0) for _ in range(11)]  # 0-10
    kpts += [
        _kpt(50, 100),  # 11: left_hip (standing)
        _kpt(50, 100),  # 12: right_hip (riding)
        _kpt(50, 120),  # 13: left_knee
        _kpt(50, 120),  # 14: right_knee (sharp bend below)
        _kpt(50, 140),  # 15: left_ankle (standing)
        _kpt(70, 130),  # 16: right_ankle (riding side)
    ]
    result = classify_posture(kpts)
    assert result == "unknown", f"Expected unknown, got {result}"


# ─── PostureDetector tests ──────────────────────────────────────────────────────

def test_posture_detector_empty_image():
    """Empty image returns empty list."""
    from app.cv.pose import PostureDetector

    detector = PostureDetector()
    result = detector.detect_pose(np.zeros((100, 100, 3), dtype=np.uint8))
    # Without model loaded, will fail — but should be caught
    # This tests that no exception propagates
    assert isinstance(result, list)


def test_posture_detector_isolated_exception():
    """PostureDetector raises are caught by pipeline."""
    from app.cv.pose import PostureDetector

    detector = PostureDetector()

    try:
        result = detector.detect_pose(None)
    except TypeError:
        pytest.fail("detect_pose should handle None gracefully")


def test_detect_pose_batch_one_model_call_and_order_preserved(monkeypatch):
    """N crops → 1 model call; result i maps to crop i; empty crops stay []."""
    import torch
    from types import SimpleNamespace
    from app.cv import pose
    calls = []

    def fake_model(crops, **kwargs):
        calls.append(len(crops))
        out = []
        for crop in crops:
            v = float(crop[0, 0, 0])
            data = torch.full((1, 17, 3), v)
            out.append(SimpleNamespace(keypoints=SimpleNamespace(data=data, conf=None)))
        return out

    monkeypatch.setattr(pose, '_get_pose_model', lambda: fake_model)
    crops = [np.full((40, 30, 3), 7, np.uint8), None, np.full((40, 30, 3), 9, np.uint8)]
    result = pose.PostureDetector().detect_pose_batch(crops)
    assert calls == [2]
    assert result[0][0]['x'] == 7 and result[1] == [] and result[2][0]['x'] == 9


# ─── angle_between_vectors ──────────────────────────────────────────────────────

def test_angle_between_vectors():
    from app.cv.pose import angle_between_vectors

    # 90 degree angle
    a = angle_between_vectors((1, 0), (0, 1))
    assert 89 <= a <= 91, f"Expected ~90°, got {a}"

    # 0 degree (same direction)
    a = angle_between_vectors((1, 0), (2, 0))
    assert a < 1, f"Expected ~0°, got {a}"

    # 180 degree (opposite direction)
    a = angle_between_vectors((1, 0), (-1, 0))
    assert 179 <= a <= 181, f"Expected ~180°, got {a}"
