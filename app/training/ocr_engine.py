"""OCR engine wrapper — EasyOCR baseline + adapter cho custom training.

KHÔNG tự ý đổi engine runtime. Engine runtime (cv/pipeline.py) đang dùng
EasyOCR + proposal_raw/canonical trong recognition_reviews. Adapter này chỉ
phục vụ training job (load custom model nếu có), và phải tương thích với
chữ ký reader.readtext(bgr) -> list of (bbox, text, conf).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.training.schemas import SchemaError


@dataclass
class OCRRead:
    text: str
    confidence: float
    bbox: list[tuple[float, float]]


class BaseOCREngine:
    engine_name = "base"
    model_class = "BaseOCREngine"
    model_sha256 = ""

    def read(self, image_bgr: Any) -> list[OCRRead]:
        raise NotImplementedError

    def load(self) -> None:
        return None

    @staticmethod
    def _canonical(text: str) -> str:
        from app.training import provenance
        return provenance.normalize_plate_text(text)


class EasyOCREngine(BaseOCREngine):
    """Engine runtime đang chạy (app/cv/ocr.py dùng). Mặc định."""
    engine_name = "easyocr"
    model_class = "EasyOCR.Reader"

    def __init__(self, langs: tuple[str, ...] = ("en",), gpu: bool = False):
        self.langs = langs
        self.gpu = gpu
        self._reader = None

    def load(self) -> None:
        if self._reader is not None:
            return
        try:
            import easyocr  # type: ignore
        except ImportError as e:
            raise SchemaError(f"EasyOCR không khả dụng: {e}") from e
        self._reader = easyocr.Reader(list(self.langs), gpu=self.gpu)

    def read(self, image_bgr: Any) -> list[OCRRead]:
        self.load()
        results = self._reader.readtext(image_bgr)
        out = []
        for (bbox, text, conf) in results:
            out.append(OCRRead(text=text, confidence=float(conf),
                              bbox=[(float(p[0]), float(p[1])) for p in bbox]))
        return out


def select_ocr_engine(name: str = "easyocr", **kwargs) -> BaseOCREngine:
    """Factory cho OCR engine. KHÔNG tự ý đổi khi runtime đang dùng.

    Custom trainer engine (sau khi đo đạc trên QA) sẽ thêm vào đây, vẫn giữ
    EasyOCR làm baseline để đối chứng.
    """
    if name == "easyocr":
        gpu = bool(kwargs.get("gpu", False))
        return EasyOCREngine(langs=kwargs.get("langs", ("en",)), gpu=gpu)
    raise SchemaError(f"OCR engine={name!r} chưa hỗ trợ")