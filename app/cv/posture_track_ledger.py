"""Posture ledger PER-TRACK (N05 — Post-Video Review).

Khối temporal posture trước đây là một deque chung cho cả pipeline
(`self._posture_window`), lấy mode của `frame_states` rồi append vào
deque chung. Điều này không phải ledger theo track/lượt xe — 2 xe trong
cùng frame có thể đẩy cùng state vào 1 pool chung, và kết quả cuối
cùng áp cho mọi xe.

Module này cung cấp `PostureTrackLedger`:
- Mỗi track/lượt xe có ledger riêng (deque các sample).
- Áp dụng cửa sổ 1.5s, tối đa 5 quan sát, ≥4 đồng thuận, tỷ lệ ≥80%,
  span ≥400ms, cách mẫu ≥100ms (đúng contract).
- 'unknown' không là phiếu có/không lỗi.
- Hết hạn chuyển state thành 'unknown'.
- Mâu thuẫn đáng tin (top1 - top2 ≤ MARGIN) → 'unknown' (review).
"""
from collections import deque, Counter
import time
from dataclasses import dataclass, field


POSTURE_TEMPORAL_WINDOW_SEC_DEFAULT = 1.5
POSTURE_TEMPORAL_MIN_SAMPLES_DEFAULT = 4
POSTURE_TEMPORAL_MAX_SAMPLES_DEFAULT = 5
POSTURE_TEMPORAL_AGREEMENT_RATIO_DEFAULT = 0.80
POSTURE_TEMPORAL_MIN_SPAN_SEC_DEFAULT = 0.4
POSTURE_TEMPORAL_MIN_INTERVAL_SEC_DEFAULT = 0.1
POSTURE_TEMPORAL_AMBIGUITY_MARGIN_DEFAULT = 1  # top1 - top2 < 2 → ambiguous


@dataclass
class _Sample:
    t: float  # monotonic time
    state: str


@dataclass
class _TrackLedger:
    track_id: int
    samples: deque = field(default_factory=lambda: deque(maxlen=POSTURE_TEMPORAL_MAX_SAMPLES_DEFAULT))
    last_seen: float = 0.0
    confirmed: str = 'UNKNOWN'
    confidence: float = 0.0


class PostureTrackLedger:
    """Per-track posture temporal ledger. Mỗi track có sample deque riêng."""

    def __init__(self,
                 window_sec: float = POSTURE_TEMPORAL_WINDOW_SEC_DEFAULT,
                 min_samples: int = POSTURE_TEMPORAL_MIN_SAMPLES_DEFAULT,
                 max_samples: int = POSTURE_TEMPORAL_MAX_SAMPLES_DEFAULT,
                 agreement_ratio: float = POSTURE_TEMPORAL_AGREEMENT_RATIO_DEFAULT,
                 min_span_sec: float = POSTURE_TEMPORAL_MIN_SPAN_SEC_DEFAULT,
                 min_interval_sec: float = POSTURE_TEMPORAL_MIN_INTERVAL_SEC_DEFAULT,
                 ambiguity_margin: int = 1,
                 ):
        self.window_sec = window_sec
        self.min_samples = min_samples
        self.max_samples = max_samples
        self.agreement_ratio = agreement_ratio
        self.min_span_sec = min_span_sec
        self.min_interval_sec = min_interval_sec
        self.ambiguity_margin = ambiguity_margin
        self._tracks: dict[int, _TrackLedger] = {}

    def _get_or_create(self, track_id: int) -> _TrackLedger:
        led = self._tracks.get(track_id)
        if led is None:
            led = _TrackLedger(track_id=track_id)
            led.samples = deque(maxlen=self.max_samples)
            self._tracks[track_id] = led
        return led

    def add(self, track_id: int, state: str, now_m: float | None = None) -> None:
        """Append một sample cho track. 'UNKNOWN' không được tính evidence."""
        if track_id is None:
            return
        now = now_m if now_m is not None else time.monotonic()
        state_u = (state or 'UNKNOWN').upper()
        led = self._get_or_create(track_id)
        led.last_seen = now
        if state_u == 'UNKNOWN':
            return  # không phải evidence
        # Enforce min_interval giữa 2 sample liên tiếp (không spam frame kế)
        if led.samples and (now - led.samples[-1].t) < self.min_interval_sec:
            return
        led.samples.append(_Sample(t=now, state=state_u))
        # Prune samples vượt window
        while led.samples and (now - led.samples[0].t) > self.window_sec:
            led.samples.popleft()
        # Recompute confirm
        self._recompute(led, now)

    def _recompute(self, led: _TrackLedger, now: float) -> None:
        if not led.samples:
            led.confirmed = 'UNKNOWN'
            led.confidence = 0.0
            return
        counts = Counter(s.state for s in led.samples)
        total = sum(counts.values())
        if total < self.min_samples:
            led.confirmed = 'UNKNOWN'
            led.confidence = round(counts.most_common(1)[0][1] / max(1, total), 3)
            return
        # Span check (khoảng thời gian từ sample cũ nhất đến mới nhất)
        span = led.samples[-1].t - led.samples[0].t
        if span < self.min_span_sec:
            led.confirmed = 'UNKNOWN'
            led.confidence = round(counts.most_common(1)[0][1] / max(1, total), 3)
            return
        # Top 2 states
        common = counts.most_common(2)
        top_state, top_count = common[0]
        second_count = common[1][1] if len(common) > 1 else 0
        ratio = top_count / total
        if ratio < self.agreement_ratio:
            led.confirmed = 'UNKNOWN'
            led.confidence = round(ratio, 3)
            return
        if (top_count - second_count) < self.ambiguity_margin:
            # mâu thuẫn đáng tin (đối thủ gần bằng)
            led.confirmed = 'UNKNOWN'
            led.confidence = round(ratio, 3)
            return
        led.confirmed = top_state
        led.confidence = round(ratio, 3)

    def expire_stale(self, now_m: float | None = None) -> None:
        """Tracks không cập nhật quá window_sec → set UNKNOWN, prune."""
        now = now_m if now_m is not None else time.monotonic()
        for tid, led in list(self._tracks.items()):
            # Drop samples vượt window
            while led.samples and (now - led.samples[0].t) > self.window_sec:
                led.samples.popleft()
            # Nếu không có sample mới > window → reset về UNKNOWN
            if now - led.last_seen > self.window_sec:
                led.confirmed = 'UNKNOWN'
                led.confidence = 0.0
                # Sau một khoảng rất dài không có update, có thể pop track
                if now - led.last_seen > self.window_sec * 4:
                    self._tracks.pop(tid, None)

    def get(self, track_id: int) -> tuple[str, float]:
        """Trả (state, confidence) cho track. UNKNOWN nếu chưa đủ evidence."""
        led = self._tracks.get(track_id)
        if led is None:
            return 'UNKNOWN', 0.0
        return led.confirmed, led.confidence

    def reset(self) -> None:
        self._tracks.clear()

    def track_count(self) -> int:
        return len(self._tracks)