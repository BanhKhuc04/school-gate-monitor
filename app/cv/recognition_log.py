"""Bounded, read-only diagnostic snapshots, separate from violation events."""
from collections import deque, OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
import uuid


class RecognitionLog:
    def __init__(self, gate_id, camera_id):
        self.gate_id, self.camera_id = gate_id, camera_id
        self.run_id = uuid.uuid4().hex
        self.source_epoch = 0
        self._seq = 0
        self._items = deque(maxlen=500)
        self._last = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self):
        with self._lock:
            return len(self._items)

    def reset(self, epoch):
        with self._lock:
            self.source_epoch = epoch
            self._items.clear()
            self._last.clear()

    def append(self, track_id, frame_seq, epoch, stage, status, reason, details, now=None):
        now = time.time() if now is None else now
        # Never accept arbitrary exception/request bodies into telemetry.
        allowed = {'vehicle_track_id', 'objects', 'helmet', 'plate_text', 'plate_samples',
                   'confidence', 'posture', 'samples', 'required_samples', 'issue', 'reasons'}
        data = {k: v for k, v in details.items() if k in allowed}
        fingerprint = (status, reason, repr({k:v for k,v in data.items() if k!='confidence'}))
        key = (track_id, stage, data.get("issue"))
        with self._lock:
            if epoch < self.source_epoch:
                return  # delayed IO from an earlier camera source is not current recognition
            previous = self._last.get(key)
            if previous and previous[0] == fingerprint and now-previous[1] < 1:
                return
            self._last[key] = (fingerprint, now)
            self._last.move_to_end(key)
            if len(self._last) > 500:
                self._last.popitem(last=False)
            self.source_epoch = epoch
            self._seq += 1
            self._items.append({'seq': self._seq, 'timestamp': datetime.fromtimestamp(now,timezone.utc).isoformat(),
                'gate_id': self.gate_id, 'camera_id': self.camera_id, 'source_epoch': epoch,
                'frame_seq': frame_seq, 'track_id': track_id, 'stage': stage,
                'status': status, 'reason_code': reason, **data})

    def snapshot(self, after_seq=0, limit=50):
        limit = max(1, min(100, limit))
        with self._lock:
            rows = list(self._items)
            reset = bool(after_seq and (after_seq > self._seq or (rows and after_seq < rows[0]['seq']-1)))
            if after_seq and not reset:
                rows = [row for row in rows if row['seq'] > after_seq][:limit]
            else:
                rows = rows[-limit:]
            return {'run_id': self.run_id, 'source_epoch': self.source_epoch, 'reset': reset,
                'cursor': rows[-1]['seq'] if rows else self._seq, 'items': deepcopy(rows)}
