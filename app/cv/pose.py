"""
Posture detection using YOLOv8-pose (yolov8n-pose.pt).

Automatically downloads the model on first run (requires internet).
Runs on GPU (CUDA) when torch detects one, falls back to CPU otherwise —
see app.config.DEVICE.

Keypoints used for posture classification:
  - 11: left_hip
  - 12: right_hip
  - 13: left_knee
  - 14: right_knee
  - 15: left_ankle
  - 16: right_ankle

Heuristic:
  - angle(hip-knee-ankle) < 140° → "riding" (bent at knee)
  - angle(hip-knee-ankle) > 160° → "standing" (extended)
  - otherwise → "unknown"
"""
from __future__ import annotations

import os
import math
import threading
from typing import Optional, List, Tuple

import numpy as np

# Model instance theo từng thread (thread-local), KHÔNG dùng 1 instance dùng
# chung nữa — pose detection giờ chạy song song cho nhiều person trong cùng 1
# frame (xem VideoPipeline._run_posture_detection), và ultralytics YOLO không
# đảm bảo thread-safe khi nhiều thread gọi CÙNG 1 instance đồng thời (internal
# predictor state có thể bị race). Mỗi worker thread tự load model riêng (nhẹ,
# ~6MB, chỉ load 1 lần/thread) để chạy đồng thời an toàn.
_pose_local = threading.local()

# Keypoint indices (COCO 17-keypoint format used by YOLOv8-pose)
KP_LEFT_HIP, KP_RIGHT_HIP = 11, 12
KP_LEFT_KNEE, KP_RIGHT_KNEE = 13, 14
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16


def _get_pose_model() -> "YOLO":
    """Get or initialize the YOLO pose model for the CURRENT thread."""
    model = getattr(_pose_local, "model", None)
    if model is None:
        from ultralytics import YOLO
        from app.config import DEVICE
        print(f"[Pose] Loading yolov8n-pose.pt on thread {threading.current_thread().name} (device={DEVICE})...")
        # Download + cache automatically (first run ~6MB)
        model = YOLO("yolov8n-pose.pt")
        model.to(DEVICE)
        _pose_local.model = model
        print("[Pose] Pose model loaded")
    return model


def angle_between_vectors(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
    """Compute angle in degrees between two 2D vectors (from shared origin)."""
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cos_val = max(-1.0, min(1.0, dot / (n1 * n2)))  # clamp for float errors
    return math.degrees(math.acos(cos_val))


def classify_posture(
    keypoints: List[dict],
    threshold: float = 0.3,
) -> str:
    """
    Classify posture from COCO 17-keypoint pose keypoints.

    Uses the mean angle of both legs (left and right) for robustness.

    Args:
        keypoints: list of {x, y, confidence} dicts (COCO order, 17 items)
        threshold: minimum confidence to use a keypoint

    Returns:
        "riding"  — angle(hip-knee-ankle) < 140°
        "standing" — angle(hip-knee-ankle) > 160°
        "unknown"  — inconclusive
    """
    def _leg_angle(hip_i: int, knee_i: int, ankle_i: int) -> Optional[float]:
        if hip_i >= len(keypoints) or knee_i >= len(keypoints) or ankle_i >= len(keypoints):
            return None
        h = keypoints[hip_i]
        k = keypoints[knee_i]
        a = keypoints[ankle_i]
        if (
            h.get("confidence", 0) < threshold
            or k.get("confidence", 0) < threshold
            or a.get("confidence", 0) < threshold
        ):
            return None
        # Vector from knee to hip, and from knee to ankle
        v_hip = (h["x"] - k["x"], h["y"] - k["y"])
        v_ankle = (a["x"] - k["x"], a["y"] - k["y"])
        return angle_between_vectors(v_hip, v_ankle)

    left_angle = _leg_angle(KP_LEFT_HIP, KP_LEFT_KNEE, KP_LEFT_ANKLE)
    right_angle = _leg_angle(KP_RIGHT_HIP, KP_RIGHT_KNEE, KP_RIGHT_ANKLE)

    # Average of valid legs
    angles = [a for a in [left_angle, right_angle] if a is not None]
    if not angles:
        return "unknown"

    avg_angle = sum(angles) / len(angles)

    if avg_angle < 140:
        return "riding"
    elif avg_angle > 160:
        return "standing"
    else:
        return "unknown"


class PostureDetector:
    """
    Wrapper that runs YOLOv8-pose on person crops.

    Usage:
        detector = PostureDetector()
        keypoints = detector.detect_pose(person_crop)  # returns list of keypoints dicts
        posture = classify_posture(keypoints)

    Một instance CÓ THỂ được dùng đồng thời từ nhiều thread (pipeline submit
    detector.detect_pose() cho nhiều person song song qua ThreadPoolExecutor).
    Vì vậy KHÔNG cache model vào self ở đây — self là state DÙNG CHUNG giữa các
    thread, cache vào đó sẽ làm thread thứ 2 trở đi vô tình dùng lại model của
    thread đầu tiên thay vì model thread-local của chính nó. `model` luôn gọi
    thẳng `_get_pose_model()`, nơi cache thật sự nằm ở threading.local().
    """

    @property
    def model(self):
        return _get_pose_model()

    def detect_pose(self, person_crop: np.ndarray) -> List[dict]:
        """
        Run pose estimation on a person crop image (BGR numpy).

        Returns list of keypoints dicts for the primary person in the crop,
        in COCO 17-keypoint format:
            [{x, y, confidence}, ...]  (17 items)
        Returns empty list if no person/keypoints detected.
        """
        if person_crop is None or (hasattr(person_crop, 'size') and person_crop.size == 0):
            return []
        try:
            from app.config import POSE_CONF_THRESHOLD
            results = self.model(person_crop, verbose=False, conf=POSE_CONF_THRESHOLD)
        except Exception as e:
            print(f"[Pose] Error during pose detection: {e}")
            return []

        if not results or not results[0].keypoints:
            return []

        kpts = results[0].keypoints
        if kpts.data is None or len(kpts.data) == 0:
            return []
        if len(kpts.data[0]) == 0:
            return []

        # Get first person (highest confidence)
        # kpts.data shape: (num_persons, 17, 3) → x, y, conf
        person_kpts = kpts.data[0].cpu().numpy()  # (17, 3)

        # kpts.conf can be None or have wrong shape — fall back to person_kpts[:, 2]
        conf_array = person_kpts[:, 2] if kpts.conf is None else kpts.conf[0].cpu().numpy()

        result = []
        for i in range(17):
            x, y = float(person_kpts[i, 0]), float(person_kpts[i, 1])
            conf = float(conf_array[i]) if i < len(conf_array) else 0.0
            result.append({"x": x, "y": y, "confidence": conf})

        return result


def detect_pose_keypoints(person_crop: np.ndarray) -> List[dict]:
    """
    Convenience function: run pose on a person crop and return keypoints.
    Returns empty list on failure.
    """
    detector = PostureDetector()
    return detector.detect_pose(person_crop)
