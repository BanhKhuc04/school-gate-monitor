"""Detector engine wrapper — ultralytics YOLO baseline + helmet mapping check.

KHÔNG tự ý train detector plate từ checkpoint chỉ có helmet (hoặc ngược lại).
Class mapping version phải khớp runtime hiện tại.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.training.schemas import SchemaError


@dataclass
class DetectorPrediction:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: list[float]


class BaseDetectorEngine:
    engine_name = "base"
    model_class = "BaseDetector"

    def predict(self, image_bgr: Any, *, conf_threshold: float = 0.25) -> list[DetectorPrediction]:
        raise NotImplementedError

    def load(self) -> None:
        return None


class UltralyticsDetectorEngine(BaseDetectorEngine):
    engine_name = "ultralytics"
    model_class = "Ultralytics.YOLO"

    def __init__(self, weights_path: str, class_mapping: dict[str, str]):
        self.weights_path = weights_path
        self.class_mapping = class_mapping
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        if not Path(self.weights_path).exists():
            raise SchemaError(f"weights không tồn tại: {self.weights_path}")
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as e:
            raise SchemaError(f"ultralytics không khả dụng: {e}") from e
        self._model = YOLO(self.weights_path)
        # Bảo đảm class mapping tương thích số lượng class của checkpoint
        n_classes = len(self._model.names) if hasattr(self._model, "names") else len(self.class_mapping)
        if len(self.class_mapping) != n_classes:
            raise SchemaError(
                f"class_mapping={list(self.class_mapping)} không khớp "
                f"weights có {n_classes} class"
            )

    def predict(self, image_bgr: Any, *, conf_threshold: float = 0.25) -> list[DetectorPrediction]:
        self.load()
        results = self._model.predict(image_bgr, conf=conf_threshold, verbose=False)
        out: list[DetectorPrediction] = []
        for r in results:
            for box in r.boxes:
                cid = int(box.cls[0])
                out.append(DetectorPrediction(
                    class_id=cid,
                    class_name=str(self._model.names[cid]),
                    confidence=float(box.conf[0]),
                    bbox_xyxy=[float(v) for v in box.xyxy[0]],
                ))
        return out


def select_detector_engine(target: str, weights_path: str, class_mapping: dict[str, str]) -> BaseDetectorEngine:
    if target in {"plate_detector", "helmet"}:
        return UltralyticsDetectorEngine(weights_path=weights_path, class_mapping=class_mapping)
    raise SchemaError(f"detector engine={target!r} chưa hỗ trợ")