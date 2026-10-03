"""YOLOv8 helmet detection wrapper using Ultralytics."""
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
import numpy as np
from ultralytics import YOLO

from app.config import DEVICE, USE_FP16


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
        self.model = YOLO(model_path)
        self.model.to(DEVICE)
        print(f"[Detector] {model_path} on device={DEVICE}")
        self.conf_threshold = conf_threshold
        self._class_names = self.model.names
        yaml = getattr(self.model.model, 'yaml', {})
        nano_v8 = (isinstance(yaml, dict) and yaml.get('depth_multiple') == .33
                   and yaml.get('width_multiple') == .25 and 'C2f' in str(yaml))
        self.profile = {'weights': Path(model_path).name,
                        'family': 'YOLOv8n' if nano_v8 else 'YOLO (custom)',
                        'device': str(next(self.model.model.parameters()).device)}

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Phát hiện objects trong frame.

        Args:
            frame: Ảnh BGR numpy array từ OpenCV (height, width, 3)

        Returns:
            List[Detection]: Danh sách các detection, mỗi detection gồm:
                - class_name: tên lớp (str)
                - confidence: độ tin cậy (float)
                - bbox: tuple (x1, y1, x2, y2)
        """
        # Chạy inference
        results = self.model(frame, verbose=False, conf=self.conf_threshold, half=USE_FP16)

        detections = []
        if self._class_names is None:
            self._class_names = self.model.names

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                # Lấy thông tin
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                xyxy = box.xyxy[0].cpu().numpy()  # (x1, y1, x2, y2)

                # Tên lớp
                class_name = self._class_names.get(cls_id, f"class_{cls_id}")

                detections.append(Detection(
                    class_name=class_name,
                    confidence=conf,
                    bbox=tuple(int(v) for v in xyxy)
                ))

        return detections

    def detect_tracked(self, frame: np.ndarray) -> List[Detection]:
        """
        UT1: Phát hiện objects CÓ tracking ID xuyên suốt nhiều frame (ByteTrack).

        Dùng cho person detector (model COCO) — track_id của person giữ ổn định
        cho cả xe máy/xe đạp vì cùng 1 lần model.track() trả về ID riêng biệt
        cho mỗi class (person, motorcycle, bicycle).

        `box.id` có thể None vài frame đầu tracker chưa confirm → trả track_id=None,
        các bước sau vẫn chạy bình thường bằng nearest-neighbor cho tới khi có ID.

        Args:
            frame: Ảnh BGR numpy array từ OpenCV.

        Returns:
            List[Detection]: danh sách detection với track_id (hoặc None).
        """
        results = self.model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf_threshold,
            tracker="bytetrack.yaml",
            half=USE_FP16,
        )

        detections: List[Detection] = []
        if self._class_names is None:
            self._class_names = self.model.names

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                xyxy = box.xyxy[0].cpu().numpy()  # (x1, y1, x2, y2)

                # box.id là tensor có thể là None (frame đầu tracker chưa confirm).
                # Lấy .item() chỉ khi id tensor không None.
                tid = None
                if box.id is not None:
                    try:
                        tid = int(box.id.item())
                    except (ValueError, AttributeError):
                        tid = None

                class_name = self._class_names.get(cls_id, f"class_{cls_id}")

                detections.append(Detection(
                    class_name=class_name,
                    confidence=conf,
                    bbox=tuple(int(v) for v in xyxy),
                    track_id=tid,
                ))

        return detections

    @property
    def class_names(self) -> dict:
        """Trả về dict {class_id: class_name} của model."""
        if self._class_names is None:
            # Trigger model load để lấy names
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self.detect(dummy)
        return self._class_names
