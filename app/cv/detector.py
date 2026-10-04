"""YOLOv8 detector wrapper using Ultralytics."""
import re
from dataclasses import dataclass
from typing import List, Optional
import numpy as np
from ultralytics import YOLO

from app.config import DEVICE


@dataclass
class Detection:
    """Kết quả phát hiện một object."""
    class_name: str      # Tên lớp: 'With Helmet', 'Without Helmet', 'plate', 'person', 'motorcycle'...
    confidence: float    # Độ tin cậy (0.0 - 1.0)
    bbox: tuple          # Bounding box (x1, y1, x2, y2) - tọa độ pixel


def helmet_state(class_name: str) -> Optional[str]:
    """'with' / 'without' / None theo tên lớp của model mũ bảo hiểm.

    Chấp nhận nhiều kiểu đặt tên (model HuggingFace gốc dùng 'With Helmet' /
    'Without Helmet', model tự train thường dùng 'helmet' / 'no_helmet'...) để
    đổi model không phải sửa pipeline.
    """
    name = re.sub(r'[^a-z]', '', (class_name or '').lower())
    if name in ('withouthelmet', 'nohelmet', 'nonhelmet', 'withouthelmets', 'head', 'bare', 'barehead', 'without'):
        return 'without'
    if name in ('withhelmet', 'helmet', 'helmets', 'withhelmets', 'with'):
        return 'with'
    return None


class HelmetPlateDetector:
    """Bọc ultralytics.YOLO, cung cấp method detect()."""

    def __init__(self, model_path: str, conf_threshold: float = 0.25,
                 imgsz: Optional[int] = None, fallback_path: Optional[str] = None):
        """
        Args:
            model_path: Đường dẫn file trọng số .pt (hoặc tên model ultralytics, vd. 'yolov8s.pt')
            conf_threshold: Ngưỡng confidence tối thiểu (0.0 - 1.0)
            imgsz: Kích thước ảnh đưa vào model (None = mặc định 640)
            fallback_path: Model dùng thay nếu không nạp/tải được model_path (vd.
                máy demo không có mạng để tải yolov8s.pt lần đầu)
        """
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            if not fallback_path:
                raise
            print(f"[Detector] Không nạp được {model_path} ({e}) — dùng {fallback_path}")
            model_path = fallback_path
            self.model = YOLO(model_path)
        self.model.to(DEVICE)
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        # FP16 trên GPU: nhanh gần gấp đôi, độ chính xác gần như không đổi
        self.half = DEVICE == "cuda"
        self._class_names = self.model.names
        print(f"[Detector] {model_path} on device={DEVICE} imgsz={imgsz or 640} half={self.half}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Phát hiện objects trong frame (ảnh BGR từ OpenCV).

        Returns:
            List[Detection]: class_name, confidence, bbox (x1, y1, x2, y2)
        """
        kwargs = {"verbose": False, "conf": self.conf_threshold, "half": self.half}
        if self.imgsz:
            kwargs["imgsz"] = self.imgsz
        results = self.model(frame, **kwargs)

        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            for cls_id, conf, xyxy in zip(boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist()):
                cls_id = int(cls_id)
                detections.append(Detection(
                    class_name=self._class_names.get(cls_id, f"class_{cls_id}"),
                    confidence=float(conf),
                    bbox=tuple(int(v) for v in xyxy),
                ))
        return detections

    @property
    def class_names(self) -> dict:
        """Trả về dict {class_id: class_name} của model."""
        return self._class_names
