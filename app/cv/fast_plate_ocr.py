"""FastPlateOCR challenger. Requires a local ONNX plus its matching config."""
import hashlib
import os
from pathlib import Path
import threading

import cv2
import numpy as np
import yaml


class FastPlateOCRAdapter:
    def __init__(self, model_path, config_path, recognizer_factory=None):
        model, config = Path(model_path), Path(config_path)
        if not model.is_file() or not config.is_file():
            raise ValueError('local ONNX and matching plate config required')
        self.config = yaml.safe_load(config.read_text(encoding='utf-8'))
        if self.config.get('image_color_mode') != 'rgb':
            raise ValueError('expected RGB model config')
        self.model_hash = hashlib.sha256(model.read_bytes()).hexdigest()
        self.config_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        if recognizer_factory is None:
            from fast_plate_ocr import LicensePlateRecognizer
            recognizer_factory = LicensePlateRecognizer
        # CPU first. CUDA is a separate measured deployment with matched ORT DLLs.
        self.reader = recognizer_factory(onnx_model_path=model, plate_config_path=config,
                                        device='cpu', providers=['CPUExecutionProvider'])
        self._lock = threading.Lock()

    def read(self, crop):
        from app.cv.ocr import is_two_line_plate, normalize_plate, validate_plate_format
        if crop is None or crop.size == 0 or crop.dtype != np.uint8:
            raise ValueError('nonempty uint8 BGR crop required')
        if crop.ndim != 3 or crop.shape[2] != 3:
            raise ValueError('three channel BGR crop required')
        # Two rows become one strip, preserving top-bottom character order.
        prepared = crop
        if is_two_line_plate(crop):
            mid = crop.shape[0]//2
            top, bottom = crop[:mid], crop[mid:]
            height = max(top.shape[0], bottom.shape[0])
            prepared = np.concatenate([cv2.resize(row, (row.shape[1], height)) for row in (top, bottom)], axis=1)
        rgb = cv2.cvtColor(prepared, cv2.COLOR_BGR2RGB)
        with self._lock:
            prediction = self.reader.run(rgb, return_confidence=True)[0]
        raw = prediction.plate
        normalized = normalize_plate(raw)
        probabilities = np.asarray(prediction.char_probs if prediction.char_probs is not None else [], dtype=float).ravel()
        # Reject length/config mismatches instead of inventing missing slots.
        valid = (len(probabilities) == len(raw) and validate_plate_format(normalized)
                 and len(raw) <= self.config['max_plate_slots'] and np.isfinite(probabilities).all())
        confidence = float(probabilities.min()) if valid and probabilities.size else 0.0
        return {'full': raw, 'raw_text': raw, 'normalized_text': normalized,
                'top_line': '', 'bottom_line': '', 'confidence': confidence,
                'char_confidences': probabilities.tolist(), 'engine': 'FastPlateOCR',
                'model_hash': self.model_hash, 'config_hash': self.config_hash,
                'needs_review': not valid or confidence < .7}


_configured = None
_config_lock = threading.Lock()


def configured_reader():
    global _configured
    with _config_lock:
        if _configured is None:
            _configured = FastPlateOCRAdapter(os.environ.get('CCT_MODEL_PATH', ''),
                                             os.environ.get('CCT_CONFIG_PATH', ''))
        return _configured
