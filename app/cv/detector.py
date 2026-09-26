"""YOLOv8 helmet detection wrapper using Ultralytics."""
from dataclasses import dataclass
from typing import List
import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    """Kết quả phát hiện một object."""
    class_name: str      # Tên lớp: 'helmet', 'no_helmet' (hoặc 'license-plate', 'motorcyclist' tùy model)
    confidence: float    # Độ tin cậy (0.0 - 1.0)
    bbox: tuple          # Bounding box (x1, y1, x2, y2) - tọa độ pixel


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
        self.conf_threshold = conf_threshold
        self._class_names = None
    
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
        results = self.model(frame, verbose=False, conf=self.conf_threshold)
        
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
    
    @property
    def class_names(self) -> dict:
        """Trả về dict {class_id: class_name} của model."""
        if self._class_names is None:
            # Trigger model load để lấy names
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self.detect(dummy)
        return self._class_names
