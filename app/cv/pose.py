"""
Posture detection using YOLO pose weights (POSE_MODEL_PATH, yolo11n-pose.pt).

Automatically downloads the model on first run (requires internet).
Runs on GPU (CUDA) when torch detects one, falls back to CPU otherwise —
see app.config.DEVICE.

Bike-aware side-view scoring uses pelvis, torso, overlap and temporal
association. Confident leg angles support the decision; occluded legs are
unavailable evidence. Without a bike, the legacy knee-angle classifier remains.
"""
from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, List, Tuple

import numpy as np

# YOLO forward reference for type hints only (not used at runtime here)
if TYPE_CHECKING:
    from ultralytics import YOLO

# One pose instance; all model access runs on the shared owner thread.
from app.cv.inference_worker import model_owner
_pose_model = None

# Keypoint indices (COCO 17-keypoint format used by YOLOv8-pose)
KP_LEFT_HIP, KP_RIGHT_HIP = 11, 12
KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER = 5, 6
KP_LEFT_KNEE, KP_RIGHT_KNEE = 13, 14
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16


# Person crops are rarely taller than 320 px; letterboxing each to 640x640
# made a crowded gate frame cost up to ~0.6 s.
POSE_IMGSZ = 320
POSE_MAX_BATCH = 8


def _get_pose_model() -> "YOLO":
    def load():
        global _pose_model
        if _pose_model is None:
            from app.config import POSE_MODEL_PATH
            from app.cv.detector import load_yolo
            _pose_model = load_yolo(POSE_MODEL_PATH, POSE_IMGSZ)
        return _pose_model
    return model_owner().run('pose', load)


def angle_between_vectors(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
    """Compute angle in degrees between two 2D vectors (from shared origin)."""
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cos_val = max(-1.0, min(1.0, dot / (n1 * n2)))  # clamp for float errors
    return math.degrees(math.acos(cos_val))


def hip_over_bike(
    keypoints: List[dict], threshold: float,
    bike_bbox: Tuple[float, float, float, float], offset: Tuple[float, float],
) -> Tuple[Optional[bool], Optional[float], Optional[float]]:
    """(result, dx, dy) — result=True nếu hip nằm trên/gần vùng giữa bike_bbox,
    False nếu rõ ràng lệch hẳn sang bên (đứng cạnh xe), None nếu keypoint hip
    thiếu/confidence thấp (KHÔNG được coi là False chắc chắn — xem
    classify_posture). dx/dy là độ lệch đã normalize, trả kèm để debug/tune
    RIDING_HIP_X_TOLERANCE / RIDING_HIP_Y_TOLERANCE trên camera thật
    (DEBUG_RIDING=1 vẽ 2 số này lên video).

    Toạ độ ngưỡng normalize theo bề rộng/chiều cao bike_bbox (không dùng pixel
    cố định) vì camera treo chéo, tỉ lệ xe trong khung đổi theo khoảng cách.
    """
    from app.config import RIDING_HIP_X_TOLERANCE, RIDING_HIP_Y_TOLERANCE

    hips = [keypoints[i] for i in (KP_LEFT_HIP, KP_RIGHT_HIP) if i < len(keypoints)]
    valid = [p for p in hips if p.get("confidence", 0) >= threshold]
    if not valid:
        return None, None, None
    hip_x = sum(p["x"] for p in valid) / len(valid) + offset[0]
    hip_y = sum(p["y"] for p in valid) / len(valid) + offset[1]

    bx1, by1, bx2, by2 = bike_bbox
    bw, bh = bx2 - bx1, by2 - by1
    if bw <= 0 or bh <= 0:
        return None, None, None

    dx = abs(hip_x - (bx1 + bx2) / 2) / bw
    dy = (hip_y - by1) / bh
    return (dx <= RIDING_HIP_X_TOLERANCE and dy <= RIDING_HIP_Y_TOLERANCE), dx, dy


def avg_leg_angle(keypoints: List[dict], threshold: float) -> Optional[float]:
    """Mean hip-knee-ankle angle over both legs with usable confidence, or
    None if neither leg has 3 confident keypoints. Exposed (not just internal
    to classify_posture) for the DEBUG_RIDING overlay."""
    def _leg_angle(hip_i: int, knee_i: int, ankle_i: int) -> Optional[float]:
        if hip_i >= len(keypoints) or knee_i >= len(keypoints) or ankle_i >= len(keypoints):
            return None
        h, k, a = keypoints[hip_i], keypoints[knee_i], keypoints[ankle_i]
        if (h.get("confidence", 0) < threshold or k.get("confidence", 0) < threshold
                or a.get("confidence", 0) < threshold):
            return None
        if not all(math.isfinite(p.get(coord, float("nan")))
                   for p in (h, k, a) for coord in ("x", "y")):
            return None
        v_hip = (h["x"] - k["x"], h["y"] - k["y"])
        v_ankle = (a["x"] - k["x"], a["y"] - k["y"])
        if v_hip == (0, 0) or v_ankle == (0, 0):
            return None
        return angle_between_vectors(v_hip, v_ankle)

    angles = [a for a in (
        _leg_angle(KP_LEFT_HIP, KP_LEFT_KNEE, KP_LEFT_ANKLE),
        _leg_angle(KP_RIGHT_HIP, KP_RIGHT_KNEE, KP_RIGHT_ANKLE),
    ) if a is not None]
    return sum(angles) / len(angles) if angles else None


def _valid_box(box) -> bool:
    return (box is not None and len(box) == 4 and all(math.isfinite(v) for v in box)
            and box[2] > box[0] and box[3] > box[1])


def _band_score(value, core_low, core_high, outer_low, outer_high) -> float:
    """Unit score inside the strong band, tapering to zero outside it."""
    if core_low <= value <= core_high:
        return 1.0
    if value < core_low:
        return max(0.0, (value - outer_low) / (core_low - outer_low))
    return max(0.0, (outer_high - value) / (outer_high - core_high))


def _keypoint_center(keypoints, indices, threshold, offset):
    points = [keypoints[i] for i in indices if i < len(keypoints)
              and keypoints[i].get("confidence", 0) >= threshold
              and math.isfinite(keypoints[i].get("x", float("nan")))
              and math.isfinite(keypoints[i].get("y", float("nan")))]
    if not points:
        return None
    return (sum(p["x"] for p in points) / len(points) + offset[0],
            sum(p["y"] for p in points) / len(points) + offset[1])


def _intersection_area(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _available_score(value):
    if value is None or not math.isfinite(value):
        return None
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class SideViewRidingResult:
    state: str
    score: float
    features: dict[str, Optional[float]]

    @property
    def available(self) -> dict[str, bool]:
        return {name: value is not None for name, value in self.features.items()}

    @property
    def debug(self) -> dict:
        return {"hip_score": self.features["hip"], "torso_score": self.features["torso"],
                "overlap": self.features["overlap"], "temporal": self.features["temporal"],
                "motion": self.features["motion"], "leg_score": self.features["leg"],
                "leg_status": "AVAILABLE" if self.available["leg"] else "UNAVAILABLE",
                "score": self.score, "state": self.state, "available": self.available}


class SideViewRiding:
    """Conservative side-view riding evidence in full-frame bike coordinates.

    Score = sum(weight * feature) / sum(available weights). Missing values
    are omitted. A high aggregate score alone cannot replace visible hips and
    torso. One confident side of the body is enough; two knees/ankles or a
    straddle across both sides of the bike are never required.
    """

    WEIGHTS = {"hip": 0.30, "torso": 0.25, "overlap": 0.20,
               "temporal": 0.15, "motion": 0.05, "leg": 0.05}

    def __init__(self, min_score=0.75, min_hip_score=0.75, min_torso_score=0.70,
                 min_overlap_score=0.55, min_temporal_score=0.75):
        self.min_score = min_score
        self.min_hip_score = min_hip_score
        self.min_torso_score = min_torso_score
        self.min_overlap_score = min_overlap_score
        self.min_temporal_score = min_temporal_score

    def evaluate(self, keypoints: List[dict], bike_bbox, person_bbox=None,
                 offset=(0.0, 0.0), temporal_score=None, motion_score=None,
                 threshold=0.3) -> SideViewRidingResult:
        features = dict.fromkeys(self.WEIGHTS)
        features["temporal"] = _available_score(temporal_score)
        features["motion"] = _available_score(motion_score)
        if not _valid_box(bike_bbox):
            return SideViewRidingResult("UNKNOWN", 0.0, features)

        bx1, by1, bx2, by2 = bike_bbox
        bw, bh = bx2 - bx1, by2 - by1
        from app.config import RIDING_FRONTAL_MAX_ASPECT
        if bw / bh < RIDING_FRONTAL_MAX_ASPECT:
            return _frontal_riding(keypoints, bike_bbox, offset, threshold, features)
        hip = _keypoint_center(keypoints, (KP_LEFT_HIP, KP_RIGHT_HIP), threshold, offset)
        shoulder = _keypoint_center(keypoints, (KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER), threshold, offset)
        angle = avg_leg_angle(keypoints, threshold)
        if angle is not None and math.isfinite(angle):
            features["leg"] = max(0.0, min(1.0, (160.0 - angle) / 30.0))

        hip_x = hip_y = None
        if hip is not None:
            hip_x = (hip[0] - (bx1 + bx2) / 2) / bw
            hip_y = (hip[1] - by1) / bh
            features["hip"] = min(
                _band_score(hip_x, -0.30, 0.30, -0.55, 0.55),
                _band_score(hip_y, -0.15, 0.45, -0.45, 0.75))
            # A pelvis patch above the seat supplies the main overlap evidence.
            # Whole-box overlap adds support, but cannot decide riding alone.
            pelvis = (hip[0] - 0.12 * bw, hip[1] - 0.16 * bh,
                      hip[0] + 0.12 * bw, hip[1] + 0.16 * bh)
            seat_body = (bx1, by1 - 0.18 * bh, bx2, by2)
            pelvis_overlap = _intersection_area(pelvis, seat_body) / (0.24 * bw * 0.32 * bh)
            overlap = pelvis_overlap
            if _valid_box(person_bbox):
                person_area = ((person_bbox[2] - person_bbox[0])
                               * (person_bbox[3] - person_bbox[1]))
                box_overlap = _intersection_area(person_bbox, bike_bbox) / min(person_area, bw * bh)
                overlap = 0.75 * pelvis_overlap + 0.25 * min(1.0, box_overlap / 0.25)
            features["overlap"] = max(0.0, min(1.0, overlap))

        if hip is not None and shoulder is not None:
            torso_y = ((hip[1] + shoulder[1]) / 2 - by1) / bh
            features["torso"] = min(
                _band_score((hip[1] - shoulder[1]) / bh, 0.15, 1.5, 0.04, 2.0),
                _band_score((shoulder[0] - hip[0]) / bw, -0.15, 0.15, -0.60, 0.60),
                _band_score(torso_y, -1.0, 0.20, -1.6, 0.60))

        available_weight = sum(self.WEIGHTS[name] for name, value in features.items() if value is not None)
        score = (sum(self.WEIGHTS[name] * value for name, value in features.items() if value is not None)
                 / available_weight if available_weight else 0.0)
        strong_body = all(features[name] is not None and features[name] >= minimum for name, minimum in (
            ("hip", self.min_hip_score), ("torso", self.min_torso_score),
            ("overlap", self.min_overlap_score)))
        strong_temporal = (features["temporal"] is not None
                           and features["temporal"] >= self.min_temporal_score)
        bent_leg = angle is not None and angle < 140
        state = "UNKNOWN"
        if strong_body and score >= self.min_score and (strong_temporal or bent_leg):
            state = "RIDING"
        elif (hip is not None and shoulder is not None and angle is not None
              and angle > 160 and strong_temporal and features["torso"] >= self.min_torso_score
              and 0.45 <= abs(hip_x) <= 0.95 and -0.30 <= hip_y <= 0.90):
            # Positive extended-leg + upright side-body evidence on a tracked
            # bike pair. Low riding score or missing legs never means walking.
            state = "WALKING_WITH_BIKE"
        return SideViewRidingResult(state, max(0.0, min(1.0, score)), features)


def _frontal_riding(keypoints, bike_bbox, offset, threshold, features) -> SideViewRidingResult:
    """Bike seen head-on or from behind (box taller than wide).

    The side-view cues (hip over the seat, torso above the bike) hold for a
    person walking just behind a frontal bike too: on the 04/10 gate video
    178/304 walking frames came out RIDING. Seen frontally, a rider straddles
    the bike — knees/ankles spread across its width with the hips on its
    centre line — while a person pushing it walks beside it, hips off-centre
    and legs together. Measured there: knee spread riding p10 0.31 vs walking
    p50 0.28 (of bike width), hip offset riding |x| <= 0.10 vs walking 0.12-0.30.
    """
    bx1, by1, bx2, by2 = bike_bbox
    bw = bx2 - bx1
    hip = _keypoint_center(keypoints, (KP_LEFT_HIP, KP_RIGHT_HIP), threshold, offset)
    if hip is None:
        return SideViewRidingResult("UNKNOWN", 0.0, features)

    def spread(left, right):
        a = _keypoint_center(keypoints, (left,), threshold, offset)
        b = _keypoint_center(keypoints, (right,), threshold, offset)
        return abs(a[0] - b[0]) / bw if a and b else None

    knees, ankles = spread(KP_LEFT_KNEE, KP_RIGHT_KNEE), spread(KP_LEFT_ANKLE, KP_RIGHT_ANKLE)
    hip_x = (hip[0] - (bx1 + bx2) / 2) / bw
    straddle = (knees is not None and knees >= 0.40) or (ankles is not None and ankles >= 0.45)
    together = (knees is not None and knees < 0.33) or (ankles is not None and ankles < 0.30)
    features["hip"] = _band_score(hip_x, -0.12, 0.12, -0.30, 0.30)
    leg = max(v for v in (knees, ankles, 0.0) if v is not None)
    features["leg"] = max(0.0, min(1.0, leg / 0.45))
    score = (features["hip"] + features["leg"]) / 2
    if abs(hip_x) <= 0.12 and straddle:
        state = "RIDING"
    elif (abs(hip_x) >= 0.12 and not straddle) or (together and abs(hip_x) >= 0.08):
        state = "WALKING_WITH_BIKE"
    else:
        state = "UNKNOWN"
    return SideViewRidingResult(state, score, features)


@dataclass(frozen=True)
class TemporalRidingFeatures:
    temporal_score: Optional[float]
    motion_score: Optional[float]


@dataclass
class _RidingPair:
    last_seen: float
    person_center: tuple
    bike_center: tuple
    relative_center: tuple
    frames: int


class RidingTemporalState:
    """Bounded, expiring person/vehicle/epoch association; no decision cache.

    Call once per distinct pose frame with stable tracker IDs and the source
    epoch. Stationary pairs gain association evidence with unavailable motion.
    """

    def __init__(self, max_pairs=512, max_age_seconds=3.0, min_frames=3,
                 motion_min_pixels=2.0):
        self.max_pairs = max(1, int(max_pairs))
        self.max_age_seconds = max(0.01, float(max_age_seconds))
        self.min_frames = max(2, int(min_frames))
        self.motion_min_pixels = max(0.01, float(motion_min_pixels))
        self._pairs = OrderedDict()
        self._lock = threading.RLock()

    @property
    def pair_count(self):
        with self._lock:
            return len(self._pairs)

    def clear(self):
        with self._lock:
            self._pairs.clear()

    def discard_vehicle(self, vehicle_track_id, epoch=None):
        with self._lock:
            for key in list(self._pairs):
                if key[1] == vehicle_track_id and (epoch is None or key[2] == epoch):
                    del self._pairs[key]

    def observe(self, person_track_id, vehicle_track_id, epoch, person_bbox,
                bike_bbox, timestamp) -> TemporalRidingFeatures:
        with self._lock:
            if (person_track_id is None or vehicle_track_id is None
                    or not _valid_box(person_bbox) or not _valid_box(bike_bbox)
                    or not math.isfinite(timestamp)):
                return TemporalRidingFeatures(None, None)
            for old_key, pair in list(self._pairs.items()):
                if (timestamp - pair.last_seen > self.max_age_seconds
                        or (old_key[0] == person_track_id and old_key[2] == epoch
                            and old_key[1] != vehicle_track_id)):
                    del self._pairs[old_key]
            key = (person_track_id, vehicle_track_id, epoch)
            person_center = ((person_bbox[0] + person_bbox[2]) / 2,
                             (person_bbox[1] + person_bbox[3]) / 2)
            bike_center = ((bike_bbox[0] + bike_bbox[2]) / 2,
                           (bike_bbox[1] + bike_bbox[3]) / 2)
            relative = ((person_center[0] - bike_center[0]) / (bike_bbox[2] - bike_bbox[0]),
                        (person_center[1] - bike_center[1]) / (bike_bbox[3] - bike_bbox[1]))
            previous = self._pairs.get(key)
            frames, motion = 1, None
            if previous is not None and timestamp > previous.last_seen:
                drift = math.dist(relative, previous.relative_center)
                if drift <= 0.35:
                    frames = previous.frames + 1
                person_delta = tuple(a - b for a, b in zip(person_center, previous.person_center))
                bike_delta = tuple(a - b for a, b in zip(bike_center, previous.bike_center))
                speed = max(math.hypot(*person_delta), math.hypot(*bike_delta))
                if speed >= self.motion_min_pixels:
                    motion = max(0.0, 1.0 - math.dist(person_delta, bike_delta) / speed)
            self._pairs[key] = _RidingPair(timestamp, person_center, bike_center, relative, frames)
            self._pairs.move_to_end(key)
            while len(self._pairs) > self.max_pairs:
                self._pairs.popitem(last=False)
            return TemporalRidingFeatures(min(1.0, frames / self.min_frames), motion)


def classify_posture(
    keypoints: List[dict],
    threshold: float = 0.3,
    bike_bbox: Optional[Tuple[float, float, float, float]] = None,
    offset: Tuple[float, float] = (0.0, 0.0),
    person_bbox: Optional[Tuple[float, float, float, float]] = None,
    temporal_score: Optional[float] = None,
    motion_score: Optional[float] = None,
) -> str:
    """
    Compatibility labels for posture consumers. Keypoints are crop-local;
    bike/person boxes are full-frame, translated with offset. Bike-aware
    classification delegates to SideViewRiding. "standing" represents only
    positive WALKING_WITH_BIKE evidence when a bike is supplied.
    """
    angle = avg_leg_angle(keypoints, threshold)
    leg_bent = angle < 140 if angle is not None else None
    leg_extended = angle > 160 if angle is not None else None

    if bike_bbox is None:
        if leg_bent:
            return "riding"
        if leg_extended:
            return "standing"
        return "unknown"

    result = SideViewRiding().evaluate(keypoints, bike_bbox, person_bbox, offset,
                                      temporal_score, motion_score, threshold)
    return {"RIDING": "riding", "WALKING_WITH_BIKE": "standing", "UNKNOWN": "unknown"}[result.state]


class PostureDetector:
    """
    Wrapper that runs YOLOv8-pose on person crops.

    Usage:
        detector = PostureDetector()
        keypoints = detector.detect_pose(person_crop)  # returns list of keypoints dicts
        posture = classify_posture(keypoints)

    Model dùng chung 1 instance, mọi lượt chạy đi qua luồng model-owner.
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
        return self.detect_pose_batch([person_crop])[0]

    def detect_pose_batch(self, person_crops: List[np.ndarray]) -> List[List[dict]]:
        """One model call for all crops; result i belongs to crop i.

        Batching N riders costs ~1.4x one rider instead of Nx (measured on
        RTX 3050: 3 crops 74ms -> 43ms, 5 crops 127ms -> 61ms).
        """
        out: List[List[dict]] = [[] for _ in person_crops]
        valid = [i for i, c in enumerate(person_crops)
                 if c is not None and getattr(c, 'size', 0) > 0]
        if not valid:
            return out
        crops = [person_crops[i] for i in valid]
        try:
            from app.config import POSE_CONF_THRESHOLD, USE_FP16

            def run():
                # The TensorRT engine takes at most POSE_MAX_BATCH crops a call.
                return [r for start in range(0, len(crops), POSE_MAX_BATCH)
                        for r in self.model(crops[start:start+POSE_MAX_BATCH], verbose=False,
                                            conf=POSE_CONF_THRESHOLD,
                                            quantize=16 if USE_FP16 else None, imgsz=POSE_IMGSZ)]
            results = model_owner().run(getattr(self, 'camera_id', 'pose'), run)
        except Exception as e:
            print(f"[Pose] Error during pose detection: {e}")
            return out
        for index, result in zip(valid, results or []):
            out[index] = _primary_keypoints(result)
        return out


def _primary_keypoints(result) -> List[dict]:
    kpts = getattr(result, 'keypoints', None)
    if not kpts or kpts.data is None or len(kpts.data) == 0 or len(kpts.data[0]) == 0:
        return []
    # kpts.data shape: (num_persons, 17, 3); first person is highest confidence.
    person_kpts = kpts.data[0].cpu().numpy()
    conf_array = person_kpts[:, 2] if kpts.conf is None else kpts.conf[0].cpu().numpy()
    return [{"x": float(person_kpts[i, 0]), "y": float(person_kpts[i, 1]),
             "confidence": float(conf_array[i]) if i < len(conf_array) else 0.0}
            for i in range(17)]


def detect_pose_keypoints(person_crop: np.ndarray) -> List[dict]:
    """
    Convenience function: run pose on a person crop and return keypoints.
    Returns empty list on failure.
    """
    detector = PostureDetector()
    return detector.detect_pose(person_crop)
