"""Adapter for character-level YOLOv8n plate reader (36-class).

Read-only by default — never assigns a plate to a student without
human confirmation. Runtime paths only call this when CHAR_PLATE_READER_REVIEW_ONLY
is enabled in config. Errors fall back to the existing EasyOCR result;
the runtime contract for best crop / OCR attempts does not change here.

NOTE: This module does not load weights at import. `load_model()` is called
explicitly by the pipeline so the slow first-load cost is paid exactly once
when the new engine is requested. The default EasyOCR engine keeps running
unchanged on every crop.
"""
from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.cv.plate_char_tools import (
    CHARACTERS,
    decode_characters,
    read_char_crop,
)


# Path to the trained 36-class character detector. Configured via env so that
# deployments can pin a different version without code changes.
DEFAULT_CHAR_WEIGHTS = os.environ.get(
    "CHAR_PLATE_WEIGHTS",
    "runs/plate_ocr_20261001_183323/character_train_v2/weights/best.pt",
)

# The expected SHA256 of the trained weights. Verified at load time to catch
# silent replacements. If you want to swap weights, also update this constant
# AND write a migration note in docs/.
EXPECTED_SHA256 = "c30f244fca6699ac3ece5836426d704bb391ba05d259a1e3455cc6b5075ba4a6"


@dataclass
class CharReadResult:
    """Normalized output, shaped like ocr.read_plate_detailed to keep callers uniform."""
    full: str
    top_line: str
    bottom_line: str
    confidence: float
    character_count: int = 0
    engine: str = "yolov8n_char_v2"
    weights_sha256: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not (self.full or self.top_line or self.bottom_line)


class CharPlateReader:
    """Lazy-loaded YOLOv8 character detector for plate crops.

    `predict(crop)` is thread-safe via the underlying ultralytics predict()
    method. We don't share a single InferenceSession across threads because
    Ultralytics documents (and the project benchmarks confirmed) that one
    YOLO instance must not run concurrent inferences. Each pipeline owns its
    own reader instance.
    """

    def __init__(self, weights_path: str = DEFAULT_CHAR_WEIGHTS,
                 min_confidence: float = 0.25,
                 expected_sha: Optional[str] = EXPECTED_SHA256):
        self._weights_path = weights_path
        self._min_confidence = min_confidence
        self._expected_sha = expected_sha
        self._model = None
        self._lock = threading.Lock()
        self._weights_sha: Optional[str] = None
        self._load_error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def weights_sha256(self) -> Optional[str]:
        return self._weights_sha

    @property
    def weights_path(self) -> str:
        return self._weights_path

    def load_model(self) -> bool:
        """Eagerly load weights. Returns True on success, False on error.

        Failures (missing file, hash mismatch, ultralytics import error) are
        recorded in `_load_error` and surfaced through `predict()` as an
        error result — never raised. The pipeline must keep running on
        EasyOCR even if this fails.
        """
        with self._lock:
            if self._model is not None:
                return True
            if not os.path.isfile(self._weights_path):
                self._load_error = f"weights_not_found:{self._weights_path}"
                return False
            try:
                sha = hashlib.sha256(open(self._weights_path, "rb").read()).hexdigest()
            except Exception as exc:
                self._load_error = f"sha256_read_error:{type(exc).__name__}"
                return False
            if self._expected_sha and sha != self._expected_sha:
                self._load_error = f"sha256_mismatch:expected={self._expected_sha[:12]}..got={sha[:12]}.."
                return False
            self._weights_sha = sha
            try:
                from ultralytics import YOLO  # local import to avoid hard dependency at import-time
                self._model = YOLO(self._weights_path)
            except Exception as exc:
                self._load_error = f"model_load_error:{type(exc).__name__}:{exc}"
                return False
            return True

    def predict(self, crop: np.ndarray) -> CharReadResult:
        """Run the character reader on a plate crop.

        Returns a `CharReadResult` with `error` set on failure. Never raises.
        """
        if crop is None or crop.size == 0:
            return CharReadResult(
                full="", top_line="", bottom_line="", confidence=0.0,
                error="empty_crop",
            )
        if self._model is None and not self.load_model():
            return CharReadResult(
                full="", top_line="", bottom_line="", confidence=0.0,
                error=self._load_error or "model_not_loaded",
            )
        try:
            with self._lock:
                decoded = read_char_crop(self._model, crop, conf=self._min_confidence)
        except Exception as exc:
            return CharReadResult(
                full="", top_line="", bottom_line="", confidence=0.0,
                error=f"predict_error:{type(exc).__name__}",
            )
        return CharReadResult(
            full=decoded.get("full", ""),
            top_line=decoded.get("top_line", ""),
            bottom_line=decoded.get("bottom_line", ""),
            confidence=float(decoded.get("confidence", 0.0)),
            character_count=int(decoded.get("character_count", 0) or 0),
            engine="yolov8n_char_v2",
            weights_sha256=self._weights_sha,
            error=decoded.get("error"),
        )


def merge_with_easyocr(char: CharReadResult, easy: dict) -> dict:
    """Side-by-side comparison payload for review-only UIs.

    Returns a dict with both candidates and an `agreement` summary so the
    UI can flag disagreements. Does NOT overwrite the live OCR result —
    that lives in the existing pipeline/PlateVoter path.
    """
    easy_full = easy.get("full", "") if isinstance(easy, dict) else ""
    easy_conf = float(easy.get("confidence", 0.0)) if isinstance(easy, dict) else 0.0
    return {
        "char_reader": {
            "engine": char.engine,
            "weights_sha256": char.weights_sha256,
            "full": char.full,
            "top_line": char.top_line,
            "bottom_line": char.bottom_line,
            "confidence": char.confidence,
            "character_count": char.character_count,
            "error": char.error,
        },
        "easyocr": {
            "full": easy_full,
            "top_line": easy.get("top_line", "") if isinstance(easy, dict) else "",
            "bottom_line": easy.get("bottom_line", "") if isinstance(easy, dict) else "",
            "confidence": easy_conf,
            "error": easy.get("error") if isinstance(easy, dict) else None,
        },
        "agreement": {
            "match": bool(char.full and char.full == easy_full),
            "char_only": bool(char.full and not easy_full),
            "easy_only": bool(easy_full and not char.full),
        },
    }
