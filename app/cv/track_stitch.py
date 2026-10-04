"""Give a re-detected object back the track id it lost a moment ago.

ByteTrack starts a new id whenever it cannot match a box to the predicted one.
On the front camera a person walking to the far end has their head cut by the
top edge, the box shrinks from 213 to 55 px in a few frames, and the same
person came back as a new id 5-6 times in 100 s (each id = a new live card,
a new helmet/plate vote, a new posture ledger).

A new id takes over a lost one only when, conservatively:
  * the old id is not visible in this frame and was last seen <= max_gap_sec ago,
  * the centres are within max_dist x the larger box side of either box,
  * no other new id claimed it first (one-to-one).
Two students crossing where one just vanished can still be merged; keep
max_gap_sec short for that reason.
"""


class TrackStitcher:
    def __init__(self, max_gap_sec=4.0, max_dist=1.0):
        self.max_gap_sec = max_gap_sec
        self.max_dist = max_dist
        self._alias = {}   # raw tracker id -> canonical id
        self._last = {}    # canonical id -> (timestamp, bbox)

    def reset(self):
        self._alias.clear()
        self._last.clear()

    def apply(self, dets, now):
        """Rewrite det.track_id in place to canonical ids; returns dets."""
        raw_ids = [d.track_id for d in dets if d.track_id is not None]
        claimed = {self._alias[r] for r in raw_ids if r in self._alias}
        for det in dets:
            tid = det.track_id
            if tid is None:
                continue
            if tid not in self._alias:
                canonical = self._match(det.bbox, now, claimed)
                self._alias[tid] = tid if canonical is None else canonical
                claimed.add(self._alias[tid])
            det.track_id = self._alias[tid]
            self._last[det.track_id] = (now, det.bbox)
        self._prune(now)
        return dets

    def _match(self, bbox, now, claimed):
        best = None
        x1, y1, x2, y2 = bbox
        for canonical, (seen, old) in self._last.items():
            if canonical in claimed or not 0 < now - seen <= self.max_gap_sec:
                continue
            size = max(x2 - x1, y2 - y1, old[2] - old[0], old[3] - old[1], 1)
            dx = (x1 + x2 - old[0] - old[2]) / 2
            dy = (y1 + y2 - old[1] - old[3]) / 2
            distance = (dx * dx + dy * dy) ** .5 / size
            if distance <= self.max_dist and (best is None or distance < best[0]):
                best = (distance, canonical)
        return None if best is None else best[1]

    def _prune(self, now):
        expired = {c for c, (seen, _) in self._last.items() if now - seen > 3 * self.max_gap_sec}
        for canonical in expired:
            del self._last[canonical]
        if expired:
            self._alias = {r: c for r, c in self._alias.items() if c not in expired}
