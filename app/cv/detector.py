"""YOLO (v8/11) detection wrapper using Ultralytics."""
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import numpy as np
from ultralytics import YOLO

from app.config import DEVICE, USE_FP16, USE_TENSORRT, DETECT_WIDTH
from app.cv.inference_worker import model_lock, model_owner
from weakref import WeakValueDictionary

_MODELS = WeakValueDictionary()


def engine_path(weights, imgsz) -> Path:
    """TensorRT engine built by scripts/export_tensorrt.py for this size."""
    weights = Path(weights)
    return weights.with_name(f'{weights.stem}-{imgsz}.engine')


def usable_engine(weights, imgsz) -> Optional[Path]:
    # An engine older than its .pt was built from replaced weights.
    engine = engine_path(weights, imgsz)
    if (USE_TENSORRT and DEVICE == 'cuda' and engine.is_file() and Path(weights).is_file()
            and engine.stat().st_mtime >= Path(weights).stat().st_mtime):
        return engine
    return None


def load_yolo(path, imgsz):
    """YOLO for `path` at `imgsz`: its TensorRT engine when one is usable."""
    engine = usable_engine(path, imgsz)
    if engine is not None:
        try:
            # Ultralytics captures a static engine into a CUDA graph at load.
            # Any CUDA call from another thread mid-capture (OCR, VRAM sampler)
            # poisons it and every later inference fails; the graph only saves
            # ~50 us a call, so run the engine plainly.
            from ultralytics.nn.backends import tensorrt as trt_backend
            trt_backend.TORCH_1_10 = False
        except ImportError:
            pass
        try:
            model = YOLO(str(engine))
            model.predict(np.zeros((imgsz, imgsz, 3), np.uint8), imgsz=imgsz, verbose=False)
            return model
        except Exception as exc:
            print(f'[Detector] {engine.name} unusable ({exc}); using {Path(path).name}')
    model = YOLO(path)
    model.to(DEVICE)
    return model


def _load_model(path, imgsz):
    key = f'{Path(path).resolve()}@{imgsz}'
    model = _MODELS.get(key)
    if model is None:
        model = load_yolo(path, imgsz)
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

    def __init__(self, model_path: str, conf_threshold: float = 0.25,
                 class_conf: Optional[dict] = None, imgsz: Optional[int] = None):
        """
        Khởi tạo detector.

        Args:
            model_path: Đường dẫn đến file trọng số .pt
            conf_threshold: Ngưỡng confidence tối thiểu (0.0 - 1.0)
            class_conf: ngưỡng riêng theo tên lớp, vd {'motorcycle': .2}. Các lớp
                này có tracker riêng với ngưỡng tạo track thấp tương ứng.
            imgsz: kích thước suy luận; None = DETECT_WIDTH.
        """
        self.imgsz = imgsz
        self.camera_id = "default"
        self._tracker = None
        self._class_tracker = None
        self.class_conf = dict(class_conf or {})
        self.model = model_owner().run("bootstrap", _load_model, model_path,
                                       imgsz or DETECT_WIDTH)
        engine = self.model.model if isinstance(self.model.model, str) else None
        print(f"[Detector] {engine or model_path} on device={DEVICE}")
        self.conf_threshold = conf_threshold
        self._class_names = self.model.names
        if engine:
            self.profile = {'weights': Path(engine).name, 'family': 'TensorRT FP16',
                            'device': DEVICE}
            return
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
        for tracker in (self._tracker, self._class_tracker):
            if tracker is not None:
                tracker.reset()

    @staticmethod
    def _new_tracker(high, low, new):
        from ultralytics.trackers.byte_tracker import BYTETracker
        from types import SimpleNamespace
        # Ultralytics ≥ 8.4 takes a single args namespace with `fps` (the old
        # `frame_rate=` kwarg raised TypeError on every tracked detection).
        return BYTETracker(SimpleNamespace(track_high_thresh=high, track_low_thresh=low,
            new_track_thresh=new, track_buffer=30, match_thresh=.8, fuse_score=True, fps=30))

    def _track(self, tracker, boxes, frame, detections):
        for row in tracker.update(boxes, frame):
            x1, y1, x2, y2, tid, conf, cls = row[:7]
            detections.append(Detection(self._class_names.get(int(cls), f'class_{int(cls)}'),
                float(conf), tuple(int(v) for v in (x1,y1,x2,y2)), int(tid)))

    def _infer(self, frame, tracked):
        # Explicit imgsz: helmet_best.pt was trained at 224 and Ultralytics
        # falls back to that, shrinking the detect frame to 224 px wide —
        # it found 54 helmets on 90 gate frames instead of 213 at 640.
        # quantize replaces the deprecated half=, which logged a warning on
        # every single inference call.
        # A ridden motorcycle is half hidden by its rider: COCO scores it
        # 0.2-0.4, under the person threshold, so it was dropped and the rider
        # was never paired with a bike (270/472 riding frames on gate video).
        floor = min([self.conf_threshold, *self.class_conf.values()])
        with model_lock(self.model):
            results = self.model(frame, verbose=False, conf=floor,
                                 quantize=16 if USE_FP16 else None,
                                 imgsz=getattr(self, 'imgsz', None) or DETECT_WIDTH)
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            boxes = result.boxes.cpu().numpy()  # one transfer, not 3 per box
            special = {i for i, n in self._class_names.items() if n in self.class_conf}
            in_class = np.isin(boxes.cls.astype(int), list(special))
            minimum = np.array([self.class_conf.get(self._class_names.get(int(c)), self.conf_threshold)
                                for c in boxes.cls])
            keep = boxes.conf >= minimum
            if tracked:
                if self._tracker is None:
                    # BYTETracker() resets the global track-id counter, so both
                    # trackers are built before either hands out an id; after
                    # that they share the counter and ids never collide.
                    self._tracker = self._new_tracker(.5, .1, .6)
                    if special:
                        floor_c = min(self.class_conf.values())
                        self._class_tracker = self._new_tracker(floor_c, .1, floor_c + .05)
                self._track(self._tracker, boxes[keep & ~in_class], frame, detections)
                if self._class_tracker is not None:
                    self._track(self._class_tracker, boxes[keep & in_class], frame, detections)
            else:
                for bbox, conf, cls in zip(boxes.xyxy[keep], boxes.conf[keep], boxes.cls[keep]):
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
