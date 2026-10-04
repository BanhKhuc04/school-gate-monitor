"""YOLO (v8/11) detection wrapper using Ultralytics."""
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import numpy as np
from ultralytics import YOLO

from app.config import DEVICE, USE_FP16, DETECT_WIDTH
from app.cv.inference_worker import model_owner
from weakref import WeakValueDictionary

_MODELS = WeakValueDictionary()

def _load_model(path):
    key = str(Path(path).resolve())
    model = _MODELS.get(key)
    if model is None:
        model = YOLO(path)
        model.to(DEVICE)
        _MODELS[key] = model
    return model


@dataclass
class Detection:
    """Kết quả phát hiện một object."""
    class_name: str      # Tên lớp: 'helmet', 'no_helmet' (hoặc 'license-plate', 'motorcyclist' tùy model)
    confidence: float    # Độ tin cậy (0.0 - 1.0)
    bbox: tuple          # Bounding box (x1, y1, x2, y2) - tọa độ pixel
    # UT1: ID ổn định theo dõi xuyên suốt nhiều frame qua ByteTrack. None khi
    # tracker chưa confirm (vài frame đầu hoặc track vừa bị ngắt).
    track_id: Optional[int] = None


class HelmetPlateDetector:
    """Bọc ultralytics.YOLO, cung cấp method detect()."""

    def __init__(self, model_path: str, conf_threshold: float = 0.25):
        """
        Khởi tạo detector.

        Args:
            model_path: Đường dẫn đến file trọng số .pt
            conf_threshold: Ngưỡng confidence tối thiểu (0.0 - 1.0)
        """
        self.camera_id = "default"
        self._tracker = None
        self.model = model_owner().run("bootstrap", _load_model, model_path)
        print(f"[Detector] {model_path} on device={DEVICE}")
        self.conf_threshold = conf_threshold
        self._class_names = self.model.names
        yaml = getattr(self.model.model, 'yaml', {})
        yaml = yaml if isinstance(yaml, dict) else {}
        nano_v8 = (yaml.get('depth_multiple') == .33
                   and yaml.get('width_multiple') == .25 and 'C2f' in str(yaml))
        v11 = 'C3k2' in str(yaml.get('backbone', ''))
        family = ('YOLOv8n' if nano_v8 else f"YOLO11{yaml.get('scale') or ''}" if v11
                  else 'YOLO (custom)')
        self.profile = {'weights': Path(model_path).name,
                        'family': family,
                        'device': str(next(self.model.model.parameters()).device)}

    def detect(self, frame: np.ndarray) -> List[Detection]:
        return model_owner().run(self.camera_id, self._infer, frame, False)

    def detect_tracked(self, frame: np.ndarray) -> List[Detection]:
        return model_owner().run(self.camera_id, self._infer, frame, True)

    def reset_tracker(self):
        # Tracker state belongs to this camera, never to the shared predictor.
        model_owner().run(self.camera_id, self._reset_tracker)

    def _reset_tracker(self):
        if self._tracker is not None:
            self._tracker.reset()

    def _infer(self, frame, tracked):
        # Explicit imgsz: helmet_best.pt was trained at 224 and Ultralytics
        # falls back to that, shrinking the detect frame to 224 px wide —
        # it found 54 helmets on 90 gate frames instead of 213 at 640.
        # quantize replaces the deprecated half=, which logged a warning on
        # every single inference call.
        results = self.model(frame, verbose=False, conf=self.conf_threshold,
                             quantize=16 if USE_FP16 else None, imgsz=DETECT_WIDTH)
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            boxes = result.boxes.cpu().numpy()  # one transfer, not 3 per box
            if tracked:
                if self._tracker is None:
                    from ultralytics.trackers.byte_tracker import BYTETracker
                    from types import SimpleNamespace
                    # Ultralytics ≥ 8.4 renamed BYTETracker's kwarg `frame_rate`
                    # to `fps` (and the constructor now takes a single `args`
                    # namespace only). Older code passed `frame_rate=` as a
                    # second positional/kwarg, which raised
                    # `TypeError: __init__() got an unexpected keyword
                    # argument 'frame_rate'` on every tracked detection —
                    # making `ai_fps=0` and labels never render on the
                    # MJPEG stream. Put `fps` on the SimpleNamespace (matches
                    # what newer Ultralytics expects) and don't pass it as a
                    # second arg.
                    tracker_args = SimpleNamespace(track_high_thresh=.5,
                        track_low_thresh=.1, new_track_thresh=.6, track_buffer=30,
                        match_thresh=.8, fuse_score=True, fps=30)
                    self._tracker = BYTETracker(tracker_args)
                rows = self._tracker.update(boxes, frame)
                for row in rows:
                    x1, y1, x2, y2, tid, conf, cls = row[:7]
                    detections.append(Detection(self._class_names.get(int(cls), f'class_{int(cls)}'),
                        float(conf), tuple(int(v) for v in (x1,y1,x2,y2)), int(tid)))
            else:
                for bbox, conf, cls in zip(boxes.xyxy, boxes.conf, boxes.cls):
                    detections.append(Detection(self._class_names.get(int(cls), f'class_{int(cls)}'),
                        float(conf), tuple(int(v) for v in bbox)))
        return detections

    @property
    def class_names(self) -> dict:
        """Trả về dict {class_id: class_name} của model."""
        if self._class_names is None:
            # Trigger model load để lấy names
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self.detect(dummy)
        return self._class_names
