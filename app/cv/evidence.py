"""
Bộ bằng chứng (evidence) per loại lỗi — Đợt E1.

Vấn đề giải quyết (theo plan CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md):
    EventManager hiện đếm streak "5 frame cùng label" trong window 2s — chỉ
    là 1 loại bằng chứng (đủ-tổng-quát). Plan yêu cầu:
      - Bằng chứng RIÊNG từng loại lỗi (NO_HELMET, NO_PUSH, MISSING_MIRROR,
        NO_PLATE, PLATE_OBSCURED, ...), mỗi loại có counter riêng.
      - Cửa sổ thời gian 1,5 giây (không phải 2 giây như cũ — plan note 5x
        chỉ ra "3.6 giây dù cấu hình 2 giây" là bug).
      - Cần ≥4 mẫu đồng thuận (agreement ratio ≥80%) trải dài ≥400 ms.
      - Khoảng cách mẫu tối thiểu 100 ms (chặn đếm frame trùng/cache).
      - Mẫu unknown (che/mờ/quá nhỏ) KHÔNG tính vào vote, không kéo về 0,
        không tạo phiếu.
      - Bằng chứng mâu thuẫn rõ ràng chuyển trạng thái 'conflicted' — không
        dùng đa số để che mất mâu thuẫn.
      - Chỉ đếm frame mới (frame_seq tăng), loại trùng lặp.

Thiết kế:
    - 1 EvidenceLedger per pipeline (per-gate/session). TrackState lưu evidence
      per (track_id, error_type) thay vì per (track_id) chung.
    - Mỗi FrameEvidence mới đưa vào ledger; ledger prune các mẫu quá cũ
      (ngoài window_sec). Sau prune, nếu số mẫu ≥ min_samples AND tỷ lệ
      đồng thuận (positive / total_non_unknown) ≥ min_agreement AND trải dài
      ≥ min_span_sec → ledger.commit(error_type) → trả DecisionKind.CONFIRM.
    - decision.label = error_type đã xác nhận; pipeline dùng để ghi log.
    - Nếu ledger có cả positive và negative cho cùng error_type (mâu thuẫn
      rõ) → trạng thái 'conflicted', DecisionKind.CONFLICT (không tự CONFIRM).
    - Mẫu unknown (label='unknown') KHÔNG cộng vào positive/negative, KHÔNG
      reset streak (chỉ prune theo window_sec).
    - Sau khi CONFIRM, ledger set committed_at + committed_error_types; lần
      tiếp theo cùng error_type trong grace_period_sec → DEFER (chống spam).
"""
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Ngưỡng mặc định — match docs (E1):
#   "≥4 mẫu đồng thuận trong 1,5 giây, trải dài ≥400 ms, agreement ≥80%,
#    cách mẫu ≥100 ms, chỉ đếm frame mới, unknown không tính"
DEFAULT_MIN_SAMPLES = 4
DEFAULT_WINDOW_SEC = 1.5
DEFAULT_MIN_AGREEMENT = 0.80
DEFAULT_MIN_SPAN_SEC = 0.40
DEFAULT_MIN_SAMPLE_INTERVAL_SEC = 0.10
DEFAULT_GRACE_PERIOD_SEC = 5.0


class DecisionKind(str, Enum):
    """Kết quả quyết định của EvidenceLedger.update()."""
    CONFIRM = "confirm"      # Đủ bằng chứng → pipeline được phép ghi
    DEFER = "defer"          # Chưa đủ → tiếp tục cache/OCR nhưng KHÔNG log
    CONFLICT = "conflict"    # Có mâu thuẫn rõ → cần người kiểm tra
    SKIP = "skip"            # Không có bằng chứng tích cực, không cần xét


@dataclass
class ErrorSample:
    """1 mẫu evidence về 1 error_type trong 1 frame."""
    error_type: str         # 'positive', 'negative', 'unknown'
    frame_seq: int          # để chặn đếm frame trùng
    ts: float               # timestamp từ đồng hồ đơn điệu (perf_counter hoặc time.time)
    # Nguồn gốc cụ thể: vd ('helmet', 'no_helmet') cho NO_HELMET. Dùng để phân
    # tích mâu thuẫn giữa các detector class.
    detector_class: Optional[str] = None


@dataclass
class ErrorDecision:
    """Quyết định cho 1 error_type từ EvidenceLedger.update()."""
    kind: DecisionKind
    track_id: int
    error_type: str
    # Số mẫu positive trong cửa sổ hiện tại (sau prune).
    positive_count: int = 0
    # Tổng mẫu (positive + negative, loại trừ unknown).
    decisive_count: int = 0
    # Khoảng thời gian từ mẫu positive đầu đến cuối trong cửa sổ.
    span_sec: float = 0.0
    # True nếu error_type đã được CONFIRM trước đó trong grace_period_sec.
    already_confirmed_recently: bool = False


@dataclass
class _TrackErrorState:
    """State nội bộ cho 1 (track_id, error_type) — KHÔNG export."""
    track_id: int
    error_type: str
    # deque các ErrorSample trong cửa sổ window_sec hiện tại.
    samples: deque = field(default_factory=deque)
    # True nếu EvidenceLedger đã CONFIRM cho (track_id, error_type) trong TTL.
    committed_at: Optional[float] = None
    committed_at_seq: Optional[int] = None
    last_frame_seq: Optional[int] = None


class EvidenceLedger:
    """
    Quản lý bằng chứng RIÊNG từng loại lỗi (per-track, per-error_type).

    Quy tắc quyết định (E1 — docs):
      - Sample 'unknown' (helmet/che, plate/obscured, không quan sát được):
          KHÔNG cộng vào vote, KHÔNG reset streak, chỉ prune theo window.
      - Sample 'positive' (lỗi xác nhận): cộng 1 positive, cập nhật streak.
      - Sample 'negative' (an toàn): cộng 1 negative, reset streak positive.
      - Sau prune (window_sec):
          + positive_count >= min_samples (≥4)
          + positive_count / decisive_count > min_agreement (≥0.80)
          + span (last_positive.ts - first_positive.ts) >= min_span_sec (≥0.40)
          + KHÔNG có negative trong cùng cửa sổ → CONFIRM.
          + Có negative trong cửa sổ → CONFLICT (cần người kiểm tra).
          + Không đủ → DEFER.
          + decisive_count == 0 → SKIP.
      - CONFIRM trong grace_period_sec → DEFER (chống spam).

    Thread-safety: KHÔNG thread-safe. EvidenceLedger là per-pipeline và chỉ
    được gọi từ _run_loop (1 thread duy nhất).
    """

    def __init__(
        self,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        window_sec: float = DEFAULT_WINDOW_SEC,
        min_agreement: float = DEFAULT_MIN_AGREEMENT,
        min_span_sec: float = DEFAULT_MIN_SPAN_SEC,
        min_sample_interval_sec: float = DEFAULT_MIN_SAMPLE_INTERVAL_SEC,
        grace_period_sec: float = DEFAULT_GRACE_PERIOD_SEC,
    ):
        if min_samples < 1:
            raise ValueError("min_samples phải >= 1")
        if window_sec <= 0:
            raise ValueError("window_sec phải > 0")
        if not (0 < min_agreement <= 1.0):
            raise ValueError("min_agreement phải trong (0, 1]")
        if min_span_sec < 0:
            raise ValueError("min_span_sec phải >= 0")
        if min_sample_interval_sec < 0:
            raise ValueError("min_sample_interval_sec phải >= 0")
        if grace_period_sec < 0:
            raise ValueError("grace_period_sec phải >= 0")

        self.min_samples = min_samples
        self.window_sec = window_sec
        self.min_agreement = min_agreement
        self.min_span_sec = min_span_sec
        self.min_sample_interval_sec = min_sample_interval_sec
        self.grace_period_sec = grace_period_sec
        # Keyed bởi (track_id, error_type). Mỗi entry là state riêng.
        self._tracks: dict[tuple[int, str], _TrackErrorState] = {}

    # ─── Public API ───────────────────────────────────────────────────────

    def update(
        self,
        track_id: int,
        error_type: str,
        sample: ErrorSample,
        now: Optional[float] = None,
    ) -> ErrorDecision:
        """Đưa 1 ErrorSample vào ledger cho (track_id, error_type).

        Returns ErrorDecision với kind=CONFIRM|DEFER|CONFLICT|SKIP.
        """
        if now is None:
            now = sample.ts

        key = (track_id, error_type)
        state = self._tracks.get(key)
        if state is None:
            state = _TrackErrorState(track_id=track_id, error_type=error_type)
            self._tracks[key] = state

        # Prune mẫu quá cũ (ngoài window_sec) — chỉ áp dụng cho cùng error_type.
        cutoff = now - self.window_sec
        while state.samples and state.samples[0].ts < cutoff:
            state.samples.popleft()

        # Chặn đếm frame trùng: frame_seq đã có trong state → bỏ qua.
        if state.last_frame_seq is not None and sample.frame_seq <= state.last_frame_seq:
            cur_positives = sum(1 for s in state.samples if s.error_type == 'positive')
            cur_negatives = sum(1 for s in state.samples if s.error_type == 'negative')
            return ErrorDecision(kind=DecisionKind.DEFER, track_id=track_id,
                                 error_type=error_type,
                                 positive_count=cur_positives,
                                 decisive_count=cur_positives + cur_negatives)

        # Chặn mẫu dày quá: nếu mẫu gần nhất cùng error_type cách < interval → bỏ.
        # So sánh với epsilon nhỏ (1ms) để tránh false-positive do floating point:
        # 1000.0 + 0.10 + 0.10 có thể là 1000.19999... thay vì 1000.20.
        if self.min_sample_interval_sec > 0 and state.samples:
            last_ts = state.samples[-1].ts
            if (now - last_ts) < (self.min_sample_interval_sec - 0.001):
                # Trả về số mẫu hiện tại trong state (KHÔNG bao gồm mẫu bị loại).
                cur_positives = sum(1 for s in state.samples if s.error_type == 'positive')
                cur_negatives = sum(1 for s in state.samples if s.error_type == 'negative')
                return ErrorDecision(kind=DecisionKind.DEFER, track_id=track_id,
                                     error_type=error_type,
                                     positive_count=cur_positives,
                                     decisive_count=cur_positives + cur_negatives)

        state.last_frame_seq = sample.frame_seq
        state.samples.append(sample)
        # Unknown observations never displace valid evidence. Keep five valid
        # samples plus the most recent unknown (for spacing/pruning metadata).
        valid = [s for s in state.samples if s.error_type != 'unknown'][-max(5, self.min_samples):]
        latest_unknown = [s for s in state.samples if s.error_type == 'unknown'][-1:]
        state.samples = deque(sorted(valid + latest_unknown, key=lambda s: s.ts))

        # Tính toán decision dựa trên state sau khi thêm sample.
        return self._decide(state, now=now)

    def reset(self) -> None:
        """Xóa toàn bộ state (dùng khi restart pipeline, test)."""
        self._tracks.clear()

    def active_track_count(self) -> int:
        return len(self._tracks)

    def evidence_details(self, track_id: int, error_type: str) -> dict:
        """Copy accepted samples while still on the owning pipeline thread."""
        state = self._tracks.get((track_id, error_type))
        samples = [s for s in state.samples if s.error_type == 'positive'] if state else []
        return {
            'sample_count': len(samples),
            'first_observed_at': samples[0].ts if samples else None,
            'frame_seqs': [s.frame_seq for s in samples],
        }

    def confirmed_evidence(self, track_id, error_type, now):
        """Read current valid evidence without inserting/recounting a frame."""
        state = self._tracks.get((track_id, error_type))
        if state is None:
            return False
        samples = [s for s in state.samples if s.ts >= now-self.window_sec and s.error_type != 'unknown']
        positives = [s for s in samples if s.error_type == 'positive']
        return bool(len(positives) >= self.min_samples and len(positives) == len(samples)
                    and positives[-1].ts-positives[0].ts >= self.min_span_sec)

    def release_commit(self, track_id: int, error_type: str) -> None:
        """Allow a fresh sample to retry a failed persistence operation."""
        state = self._tracks.get((track_id, error_type))
        if state:
            state.committed_at = None

    def prune_expired(self, now: float, grace_period_sec: Optional[float] = None) -> None:
        """Xóa track không xuất hiện lại trong grace_period_sec — coi như track
        đã rời khung hình. KHÔNG prune track vừa update (state.samples[-1].ts
        luôn >= now - window_sec)."""
        grace = grace_period_sec if grace_period_sec is not None else self.grace_period_sec
        cutoff = now - grace
        # Track đã rời nếu sample gần nhất cũ hơn cutoff.
        expired = [
            k for k, s in self._tracks.items()
            if not s.samples or s.samples[-1].ts < cutoff
        ]
        for k in expired:
            del self._tracks[k]

    # ─── Internal ─────────────────────────────────────────────────────────

    def _decide(self, state: _TrackErrorState, now: float) -> ErrorDecision:
        """Tính toán ErrorDecision dựa trên state hiện tại."""
        # Đếm positive/negative/unknown.
        positives = [s for s in state.samples if s.error_type == 'positive']
        negatives = [s for s in state.samples if s.error_type == 'negative']
        decisive_count = len(positives) + len(negatives)

        # A prior alert is no reason to conceal new contradictory evidence.
        if positives and negatives:
            return ErrorDecision(kind=DecisionKind.CONFLICT, track_id=state.track_id,
                                 error_type=state.error_type, positive_count=len(positives),
                                 decisive_count=decisive_count)

        # Đã CONFIRM gần đây cho (track_id, error_type) này?
        if state.committed_at is not None:
            if (now - state.committed_at) < self.grace_period_sec:
                return ErrorDecision(
                    kind=DecisionKind.DEFER,
                    track_id=state.track_id,
                    error_type=state.error_type,
                    positive_count=len(positives),
                    decisive_count=decisive_count,
                    already_confirmed_recently=True,
                )

        # Không có mẫu quyết định nào → SKIP (chỉ có unknown).
        if decisive_count == 0:
            return ErrorDecision(
                kind=DecisionKind.SKIP,
                track_id=state.track_id,
                error_type=state.error_type,
                positive_count=0,
                decisive_count=0,
            )

        # Không có positive nào (chỉ negative) → SKIP (an toàn).
        if not positives:
            return ErrorDecision(
                kind=DecisionKind.SKIP,
                track_id=state.track_id,
                error_type=state.error_type,
                positive_count=0,
                decisive_count=decisive_count,
            )

        # Tính span (khoảng thời gian positive đầu → cuối).
        span_sec = positives[-1].ts - positives[0].ts
        agreement_ratio = len(positives) / decisive_count

        # Đủ điều kiện CONFIRM?
        enough_samples = len(positives) >= self.min_samples
        enough_agreement = agreement_ratio >= self.min_agreement
        enough_span = span_sec >= self.min_span_sec

        if enough_samples and enough_agreement and enough_span:
            state.committed_at = now
            return ErrorDecision(
                kind=DecisionKind.CONFIRM,
                track_id=state.track_id,
                error_type=state.error_type,
                positive_count=len(positives),
                decisive_count=decisive_count,
                span_sec=span_sec,
            )

        # Chưa đủ → DEFER.
        return ErrorDecision(
            kind=DecisionKind.DEFER,
            track_id=state.track_id,
            error_type=state.error_type,
            positive_count=len(positives),
            decisive_count=decisive_count,
            span_sec=span_sec,
        )
