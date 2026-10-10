"""One selected source-resolution crop per vehicle/source/crossing sequence."""
from dataclasses import dataclass, field
from collections import OrderedDict
import time

import cv2
import numpy as np

from app.cv.ocr import normalize_valid_plate, normalize_plate
from app.cv.plate_voter import PlateReadResult


@dataclass
class PlateCandidate:
    frame_id: int
    timestamp: float
    crop: np.ndarray
    detector_conf: float
    blur_score: float
    contrast_score: float
    crop_width: int
    crop_height: int
    quality_score: float
    components: dict
    corners: object = None


def make_candidate(frame, bbox, confidence, seq, timestamp, corners=None):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bbox)
    left, top, right, bottom = max(0, x1), max(0, y1), max(0, min(w, x2)), max(0, min(h, y2))
    if right <= left or bottom <= top:
        return None
    crop = frame[top:bottom, left:right].copy()
    if crop.size == 0:
        return None
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    exposure = float(np.mean((gray > 25) & (gray < 235)))
    clipped = (cw * ch) / max(1, (x2-x1) * (y2-y1))
    clearance = min(left, top, w-right, h-bottom) / max(1, min(cw, ch)*.25)
    # An axis-aligned box cannot prove perspective quality. Only measured
    # corner geometry contributes; unavailable perspective is excluded.
    components = {'confidence': float(np.clip(confidence, 0, 1)),
                  'size': min(1., np.sqrt(cw*ch/(160*80))),
                  'sharpness': min(1., np.log1p(blur)/np.log1p(500)),
                  'contrast': min(1., contrast/55), 'exposure': exposure,
                  'complete': min(1., clipped), 'edge': float(np.clip(clearance, 0, 1))}
    weights = {'confidence': .20, 'size': .20, 'sharpness': .25,
               'contrast': .10, 'exposure': .10, 'complete': .10, 'edge': .05}
    if corners is not None:
        quad = np.asarray(corners, dtype=np.float32)
        if quad.shape == (4, 2) and cv2.isContourConvex(quad):
            lengths = np.linalg.norm(quad-np.roll(quad, -1, axis=0), axis=1)
            if lengths.min() > 4:
                components['perspective'] = min(lengths[0], lengths[2])/max(lengths[0], lengths[2]) * min(lengths[1], lengths[3])/max(lengths[1], lengths[3])
                weights['perspective'] = .10
            else:
                corners = None
        else:
            corners = None
    quality = sum(components[k]*v for k, v in weights.items())/sum(weights.values())
    return PlateCandidate(seq, timestamp, crop, confidence, blur, contrast, cw, ch,
                          quality, components, corners)


def resolve_plate(raw, min_confidence=.70):
    error = raw.get('error')
    normalized = normalize_valid_plate(raw.get('full', ''), raw.get('top_line', ''), raw.get('bottom_line', ''))
    observed = normalize_plate((raw.get('top_line', '') + raw.get('bottom_line', '')) or raw.get('full', ''))
    confident = bool(normalized and normalized == observed and not error and not raw.get('needs_review')
                     and raw.get('confidence', 0) >= min_confidence)
    return PlateReadResult(text=normalized if confident else '', confidence=raw.get('confidence', 0),
        sample_count=1, is_confident=confident, error=error, raw_text=raw.get('full', ''))


@dataclass
class _Selection:
    best: PlateCandidate
    attempts: int = 0
    technical_retries: int = 0
    future: object = None
    epoch: int = 0
    result: object = None
    raw: dict = field(default_factory=dict)
    seen_at: float = field(default_factory=time.monotonic)
    saved_path: object = None
    inflight: object = None
    completed: object = None
    first_attempt_at: object = None
    attempted_frames: set = field(default_factory=set)


class BestPlateStore:
    MAX_PENDING = 8

    def __init__(self, replace_margin=.05, min_confidence=.70, max_attempts=1, window_sec=2.0):
        self.replace_margin = replace_margin
        self.min_confidence = min_confidence
        self.max_attempts = min(5, max_attempts)
        self.window_sec = window_sec
        self._tracks = OrderedDict()

    def reset(self):
        # Running futures cannot be killed; detached old results are ignored.
        self._tracks.clear()

    def offer(self, track, candidate):
        if candidate is None or track is None:
            return False
        self.prune()
        entry = self._tracks.get(track)
        if entry:
            entry.seen_at = time.monotonic()
            if entry.future is not None or entry.attempts >= self.max_attempts or candidate.frame_id <= entry.best.frame_id:
                return False
            if entry.first_attempt_at is not None and candidate.timestamp-entry.first_attempt_at > self.window_sec:
                return False
            if not entry.attempts and candidate.quality_score < entry.best.quality_score+self.replace_margin:
                return False
            if entry.attempts and (candidate.frame_id-entry.best.frame_id < 2 or candidate.quality_score < .3):
                return False
            entry.best = candidate
        else:
            if len(self._tracks) >= 64:
                return False  # never evict a live attempt and accidentally OCR twice
            self._tracks[track] = _Selection(candidate)
        return True

    def trigger(self, track, pool, task, epoch):
        entry = self._tracks.get(track)
        if (entry is None or entry.attempts >= self.max_attempts or entry.future is not None
                or entry.best.frame_id in entry.attempted_frames
                or sum(e.future is not None for e in self._tracks.values()) >= self.MAX_PENDING):
            return False
        if entry.first_attempt_at is None:
            entry.first_attempt_at = entry.best.timestamp
        if entry.best.timestamp-entry.first_attempt_at > self.window_sec:
            return False
        entry.epoch = epoch
        entry.inflight = entry.best
        entry.future = pool.submit(task, entry.best.crop, track, entry.best.frame_id, epoch)
        entry.attempts += 1
        entry.attempted_frames.add(entry.best.frame_id)
        return True

    def collect(self, track, pool, task, epoch):
        entry = self._tracks.get(track)
        if not entry or entry.epoch != epoch or entry.future is None or not entry.future.done():
            return None
        try:
            raw = entry.future.result()
        except Exception as exc:
            raw = {'error': f'ocr_engine_error:{type(exc).__name__}'}
        entry.future = None
        candidate = entry.inflight
        if raw.get('source_epoch', epoch) != epoch or raw.get('frame_seq', candidate.frame_id) != candidate.frame_id or raw.get('track_id', track) != track:
            raw = {'error': 'ocr_metadata_mismatch'}
        if raw.get('error') and entry.technical_retries < 1 and raw.get('error') != 'ocr_metadata_mismatch':
            entry.technical_retries += 1
            entry.future = pool.submit(task, candidate.crop, track, candidate.frame_id, epoch)
            return None
        entry.raw = raw
        entry.completed = candidate
        entry.result = resolve_plate(raw, self.min_confidence)
        return entry.result

    def result(self, track):
        entry = self._tracks.get(track)
        if entry is None:
            return None
        return entry.result or PlateReadResult(pending=entry.future is not None)

    def pending(self, track):
        entry = self._tracks.get(track)
        return bool(entry and entry.future is not None)

    def candidate(self, track):
        entry = self._tracks.get(track)
        return entry.best if entry else None

    def completed_candidate(self, track):
        entry = self._tracks.get(track)
        return entry.completed if entry else None

    def raw(self, track):
        entry = self._tracks.get(track)
        return dict(entry.raw) if entry else {}

    def future(self, track):
        entry = self._tracks.get(track)
        return entry.future if entry else None

    def discard(self, track):
        self._tracks.pop(track, None)

    def touch(self, track):
        entry = self._tracks.get(track)
        if entry:
            entry.seen_at = time.monotonic()

    def debug(self, track):
        entry = self._tracks.get(track)
        if not entry:
            return {}
        best = entry.best
        return {'best_frame_id': best.frame_id, 'timestamp': best.timestamp,
            'quality': round(best.quality_score, 3), 'blur': round(best.blur_score, 2),
            'contrast': round(best.contrast_score, 2), 'size': [best.crop_width, best.crop_height],
            'detector_confidence': best.detector_conf, 'components': best.components,
            'attempts': entry.attempts, 'max_attempts': self.max_attempts, 'technical_retries': entry.technical_retries,
            'raw_top': entry.raw.get('top_line', ''), 'raw_bottom': entry.raw.get('bottom_line', ''),
            'normalized': entry.result.text if entry.result else '',
            'status': 'CONFIRMED' if entry.result and entry.result.is_confident else
                      'ERROR' if entry.result and entry.result.error else 'UNREADABLE' if entry.result else
                      'READING' if entry.future else 'SELECTING'}

    def prune(self, now=None):
        now = time.monotonic() if now is None else now
        for track, entry in list(self._tracks.items()):
            if now-entry.seen_at > 60 and (entry.future is None or entry.future.done()):
                self._tracks.pop(track)
