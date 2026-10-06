"""Ephemeral visual observations; no roster lookup or official alerts."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
import uuid

import cv2

from app.cv.evidence import EvidenceLedger, ErrorSample, DecisionKind


class RecognitionCards:
    MAX_CARDS = 24
    MAX_IMAGES = 192
    TTL = 15

    def __init__(self, gate_id, camera_id):
        self.gate_id, self.camera_id = gate_id, camera_id
        self.run_id = uuid.uuid4().hex
        self.source_epoch = 0
        self._cards, self._images = OrderedDict(), OrderedDict()
        self._ledger = EvidenceLedger()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='recognition-crops')
        self._pending = {}

    def reset(self, epoch):
        with self._lock:
            self.source_epoch = epoch
            self._cards.clear(); self._images.clear(); self._ledger.reset()

    def close(self, wait=False):
        self._pool.shutdown(wait=wait, cancel_futures=True)

    def _confirmation(self, key, code, observation, seq, now, previous):
        decision = self._ledger.update(key, code, ErrorSample(observation, seq, now, code), now=now)
        if decision.kind == DecisionKind.CONFLICT:
            state = 'review'
        elif observation == 'positive' and (decision.kind == DecisionKind.CONFIRM or
                (previous == 'confirmed' and decision.positive_count >= self._ledger.min_samples and
                 decision.positive_count == decision.decisive_count)):
            state = 'confirmed'
        else:
            state = 'checking'
        return {'state': state, 'samples': decision.positive_count,
                'required_samples': self._ledger.min_samples}

    def observe(self, frame, group, frame_seq, epoch, now=None):
        now = time.time() if now is None else now
        track = group.get('track_id')
        key = f'person:{track}' if track is not None else f"untracked:{frame_seq}:{group['_person'].bbox}"
        yes = any(d.class_name == 'With Helmet' for d in group['helmet_dets'])
        no = any(d.class_name == 'Without Helmet' for d in group['helmet_dets'])
        value = 'helmet' if yes and not no else 'no_helmet' if no and not yes else 'unknown'
        with self._lock:
            if epoch != self.source_epoch:
                return
            # Unknown identities are frame-local previews, never a history of
            # fictitious people or a spatial guess pretending to be tracking.
            for other, card in list(self._cards.items()):
                if other.startswith('untracked:') and card['frame_seq'] != frame_seq:
                    self._cards.pop(other)
            old = self._cards.get(key, {})
            if old.get('frame_seq') == frame_seq:
                return
            person = self._confirmation(key, 'person', 'positive' if track is not None else 'unknown',
                                        frame_seq, now, old.get('person', {}).get('state'))
            if track is None:
                person['state'] = 'review'
            helmet = {'state': 'checking', 'samples': 0, 'required_samples': self._ledger.min_samples}
            for observed in ['helmet', 'no_helmet']:
                observation = 'positive' if value == observed else 'unknown' if value == 'unknown' else 'negative'
                vote = self._confirmation(key, observed, observation, frame_seq, now,
                                         old.get('helmet', {}).get('state') if old.get('helmet', {}).get('value') == observed else None)
                if value == observed:
                    helmet = vote
                if vote['state'] == 'review' or (yes and no):
                    helmet['state'] = 'review'
            helmet['value'] = value
            if track is None:
                helmet['state'] = 'review'
            if group.get('_helmet_model_error'):
                helmet.update(state='error', value='unknown', samples=0)
            plate_result = group.get('_plate_result') or group.get('_preview_plate_result')
            linked = bool(group.get('plate_dets') and group.get('_vehicle') is not None)
            best_debug = group.get('_plate_debug', {})
            plate = {'state': 'missing', 'text': '', 'samples': 0, 'required_samples': 1 if best_debug else 2,
                     'association': 'linked' if linked else 'unverified'}
            if plate_result:
                raw_text = getattr(plate_result, 'raw_text', '')
                plate.update(text=plate_result.text or raw_text, samples=plate_result.sample_count,
                    state='error' if plate_result.error else 'reading' if plate_result.pending else
                          'confirmed' if linked and plate_result.is_confident else 'candidate' if plate_result.text else
                          'partial' if raw_text else 'unreadable')
            elif group.get('plate_dets') or group.get('_preview_plate'):
                plate['state'] = 'reading' if track is not None else 'review'
            if best_debug.get('status') == 'SELECTING':
                plate['state'] = 'selecting'
            if best_debug:
                plate['samples'] = best_debug.get('attempts', 0)
            timestamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
            reasons = list(dict.fromkeys(group.get('association_reasons', []) +
                           (['track_missing'] if track is None else []) +
                           (['vehicle_not_associated'] if group.get('_vehicle') is None else [])))
            self._cards[key] = {'card_id': f'{self.run_id}:{epoch}:{key}', 'track_id': track,
                'vehicle_track_id': group.get('vehicle_track_id'), 'camera_id': self.camera_id,
                'gate_id': self.gate_id, 'source_epoch': epoch, 'frame_seq': frame_seq,
                'last_seen': timestamp, '_seen_at': now, 'person': person, 'helmet': helmet,
                'plate': plate, 'reasons': reasons, 'images': old.get('images', {}),
                'plate_debug': best_debug, 'riding': group.get('_riding_debug', {}),
                'images_state': old.get('images_state', 'pending'),
                '_plate_image_at': old.get('_plate_image_at', 0),
                '_image_at': old.get('_image_at', 0)}
            self._cards.move_to_end(key)
            self._prune(now)
            self._pending = {k: f for k, f in self._pending.items() if not f.done()}
            plate_available = bool(group.get('plate_dets') or group.get('_preview_plate'))
            new_plate = plate_available and now-old.get('_plate_image_at', 0) >= .5
            can_encode = ((now-old.get('_image_at', 0) >= .5 or new_plate)
                          and key not in self._pending and len(self._pending) < 2)
            if track is None:
                can_encode = can_encode and now-getattr(self, '_untracked_image_at', 0) >= .5
            if can_encode:
                self._cards[key]['_image_at'] = now
                if track is None:
                    self._untracked_image_at = now
                if plate_available:
                    self._cards[key]['_plate_image_at'] = now
        if can_encode:
            person_box = group['_person'].bbox
            head_box = group['helmet_dets'][0].bbox if group['helmet_dets'] else (
                person_box[0], person_box[1], person_box[2], person_box[1]+int((person_box[3]-person_box[1])*.3))
            plate_det = group['plate_dets'][0] if group['plate_dets'] else group.get('_preview_plate')
            boxes = {'person': person_box, 'head': head_box}
            if plate_det is not None:
                boxes['plate'] = plate_det.bbox
            crops = {}
            height, width = frame.shape[:2]
            for kind, (x1, y1, x2, y2) in boxes.items():
                crop = frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
                if crop.size:
                    crops[kind] = crop.copy()
            if group.get('_best_plate_crop') is not None:
                crops['plate'] = group['_best_plate_crop'].copy()
            plate_meta = {'frame_seq': best_debug.get('best_frame_id', frame_seq),
                          'timestamp': datetime.fromtimestamp(best_debug.get('timestamp', now), timezone.utc).isoformat()}
            self._pending[key] = self._pool.submit(self._encode, key, epoch, frame_seq, timestamp, crops, plate_meta)

    def observe_plate(self, track, best, result, debug, frame_seq, epoch, now=None):
        """Show an independent plate observation without inventing a person/vehicle."""
        now = time.time() if now is None else now
        key = f'plate:{track}'
        timestamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
        text = (result.text or getattr(result, 'raw_text', '')) if result else ''
        state = ('error' if result and result.error else 'reading' if result and result.pending
                 else 'candidate' if result and result.text else 'partial' if text
                 else 'unreadable' if result and result.sample_count else 'review')
        with self._lock:
            if epoch != self.source_epoch:
                return
            old = self._cards.get(key, {})
            self._cards[key] = {'card_id': f'{self.run_id}:{epoch}:{key}', 'kind': 'plate',
                'track_id': None, 'vehicle_track_id': None, 'ocr_track_id': track,
                'camera_id': self.camera_id, 'gate_id': self.gate_id, 'source_epoch': epoch,
                'frame_seq': frame_seq, 'last_seen': timestamp, '_seen_at': now,
                'plate': {'state': state, 'text': text, 'association': 'unverified',
                          'samples': result.sample_count if result else 0, 'required_samples': 1},
                'plate_debug': debug, 'reasons': ['vehicle_not_associated'],
                'images': old.get('images', {}), 'images_state': old.get('images_state', 'pending'),
                '_image_at': old.get('_image_at', 0)}
            self._cards.move_to_end(key)
            self._prune(now)
            self._pending = {k: f for k, f in self._pending.items() if not f.done()}
            can_encode = now-old.get('_image_at', 0) >= .5 and key not in self._pending and len(self._pending) < 2
            if can_encode:
                self._cards[key]['_image_at'] = now
        if can_encode:
            meta = {'frame_seq': best.frame_id,
                    'timestamp': datetime.fromtimestamp(best.timestamp, timezone.utc).isoformat()}
            self._pending[key] = self._pool.submit(self._encode, key, epoch, frame_seq, timestamp,
                                                 {'plate': best.crop.copy()}, meta)

    def _encode(self, key, epoch, seq, timestamp, crops, plate_meta=None):
        encoded = {}
        for kind, crop in crops.items():
            height, width = crop.shape[:2]
            scale = min(1, 360/max(height, width))
            if scale < 1:
                crop = cv2.resize(crop, (max(1, round(width*scale)), max(1, round(height*scale))))
            try:
                ok, jpeg = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
            except cv2.error:
                ok, jpeg = False, None
            if ok and len(jpeg) <= 65536:
                encoded[kind] = (uuid.uuid4().hex, jpeg.tobytes())
        with self._lock:
            card = self._cards.get(key)
            if epoch != self.source_epoch or card is None:
                return
            images = {}
            for kind, (image_id, body) in encoded.items():
                self._images[image_id] = body
                images[kind] = {'id': image_id, 'url': f'/guard/recognition_image/{image_id}?gate={self.gate_id}',
                                'frame_seq': seq, 'timestamp': timestamp}
                if kind == 'plate' and plate_meta:
                    images[kind].update(plate_meta)
            # Keep the last plate crop when the next detector frame misses it.
            if 'plate' not in images and 'plate' in card['images']:
                images['plate'] = card['images']['plate']
            card['images'] = images
            card['images_state'] = 'ready' if len(encoded) == len(crops) else 'partial' if encoded else 'error'
            protected = {image['id'] for item in self._cards.values() for image in item['images'].values()}
            while len(self._images) > self.MAX_IMAGES:
                victim = next(image_id for image_id in self._images if image_id not in protected)
                self._images.pop(victim)

    def _prune(self, now):
        for key, card in list(self._cards.items()):
            if now-card['_seen_at'] > self.TTL:
                self._cards.pop(key, None)
        while len(self._cards) > self.MAX_CARDS:
            self._cards.popitem(last=False)
        self._ledger.prune_expired(now, grace_period_sec=self.TTL)

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            cards = []
            for card in reversed(list(self._cards.values())):
                if now-card['_seen_at'] <= self.TTL:
                    item = {k: v for k, v in card.items() if not k.startswith('_')}
                    item['age_sec'] = max(0, round(now-card['_seen_at'], 2))
                    cards.append(deepcopy(item))
            return {'run_id': self.run_id, 'source_epoch': self.source_epoch, 'cards': cards}

    def image(self, image_id):
        with self._lock:
            return self._images.get(image_id)
