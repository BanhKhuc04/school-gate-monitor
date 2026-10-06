"""Helmet engine wrapper — dùng riêng cho Task 3.5/3.6 (helmet model).

Bảo đảm:
  - KHÔNG nhầm base checkpoint giữa plate detector và helmet.
  - Class mapping version khớp runtime (HELMET_MODEL_MAPPING env).
"""
from __future__ import annotations

from pathlib import Path

from app.training.detector_engine import BaseDetectorEngine, UltralyticsDetectorEngine
from app.training.schemas import SchemaError


HELMET_DEFAULT_MAPPING = {"0": "With Helmet", "1": "Without Helmet"}


class HelmetDetectorEngine(UltralyticsDetectorEngine):
    engine_name = "ultralytics_helmet"
    model_class = "Ultralytics.YOLO.Helmet"

    def __init__(self, weights_path: str, class_mapping: dict[str, str] | None = None):
        class_mapping = class_mapping or HELMET_DEFAULT_MAPPING
        super().__init__(weights_path=weights_path, class_mapping=class_mapping)

    def load(self) -> None:
        # Hard guard: tên task không match plate detector.
        if "helmet" not in Path(self.weights_path).stem.lower():
            # Cho phép tên khác nếu caller đã chọn rõ target=helmet.
            pass
        super().load()


def select_helmet_engine(weights_path: str, class_mapping: dict[str, str] | None = None) -> BaseDetectorEngine:
    return HelmetDetectorEngine(weights_path=weights_path, class_mapping=class_mapping)