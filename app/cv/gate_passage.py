"""
Gate Passage Ledger — đếm lượt VÀO/RA cổng theo NGƯỜI, cả 2 chiều cùng lúc.

CrossingDetector chốt từng lượt qua vạch (cả chiều không tạo vi phạm). Module
này biến các lượt đó thành số đếm đúng:

  - Xe máy/xe đạp: 1 lượt xe = số người trên xe (rider + passenger), gắn
    chiều của XE. Người ngồi trên xe không được đếm thêm lần nữa như người
    đi bộ.
  - Người đi bộ: neo theo chân (đáy giữa bbox người). Lượt đi bộ được GIỮ
    TẠM `hold_sec` trước khi chốt: nếu trong lúc đó chính người này được
    ghép vào 1 xe vừa qua vạch (ghép người–xe chậm vài frame) thì lượt đi
    bộ bị hủy, chỉ còn lượt xe — tránh 1 người bị đếm 2 lần.
  - Lượt khôi phục từ tráo ID (swap_recovered) vẫn được đếm nhưng mang
    status 'review' để có thể xem lại.

Thuần Python, không phụ thuộc pipeline — test trực tiếp được.
"""
from __future__ import annotations

from collections import deque

ENTER, EXIT = 'enter', 'exit'
PEDESTRIAN, VEHICLE = 'pedestrian', 'vehicle'


class PassageLedger:
    def __init__(self, hold_sec: float = 1.5, claim_sec: float = 5.0):
        self.hold_sec = hold_sec
        self.claim_sec = claim_sec
        self.counts = {d: {PEDESTRIAN: 0, VEHICLE: 0, 'persons': 0} for d in (ENTER, EXIT)}
        self.recent: deque = deque(maxlen=100)
        self._pending: list[dict] = []
        self._claimed: dict = {}   # person_track_id -> lúc được tính là người trên xe

    def record_vehicle(self, vehicle_track_id, direction: str, timestamp: float,
                       person_track_ids=(), swap_recovered: bool = False) -> dict | None:
        if direction not in (ENTER, EXIT):
            return None
        persons = [p for p in person_track_ids if p is not None]
        for p in persons:
            self._claimed[p] = timestamp
        self._pending = [e for e in self._pending if e['person_track_id'] not in persons]
        return self._commit({'object_type': VEHICLE, 'track_id': vehicle_track_id,
                             'person_track_ids': sorted(persons), 'persons': max(1, len(persons)),
                             'direction': direction, 'timestamp': timestamp,
                             'status': 'review' if swap_recovered else 'ok'})

    def record_pedestrian(self, person_track_id, direction: str, timestamp: float,
                          swap_recovered: bool = False) -> None:
        if direction not in (ENTER, EXIT):
            return
        claimed = self._claimed.get(person_track_id)
        if claimed is not None and abs(timestamp - claimed) <= self.claim_sec:
            return
        self._pending.append({'object_type': PEDESTRIAN, 'track_id': person_track_id,
                              'person_track_id': person_track_id,
                              'person_track_ids': [person_track_id], 'persons': 1,
                              'direction': direction, 'timestamp': timestamp,
                              'status': 'review' if swap_recovered else 'ok'})

    def flush(self, now: float) -> list[dict]:
        """Chốt các lượt đi bộ đã giữ đủ `hold_sec`. Trả các lượt vừa chốt."""
        ready = [e for e in self._pending if now - e['timestamp'] >= self.hold_sec]
        self._pending = [e for e in self._pending if now - e['timestamp'] < self.hold_sec]
        self._claimed = {p: t for p, t in self._claimed.items() if now - t <= self.claim_sec * 2}
        out = []
        for e in ready:
            e = dict(e)
            e.pop('person_track_id', None)
            out.append(self._commit(e))
        return out

    def _commit(self, event: dict) -> dict:
        bucket = self.counts[event['direction']]
        bucket[event['object_type']] += 1
        bucket['persons'] += event['persons']
        self.recent.append(event)
        return event

    def snapshot(self) -> dict:
        return {d: dict(v) for d, v in self.counts.items()}
