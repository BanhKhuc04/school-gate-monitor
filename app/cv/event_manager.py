"""
Event Engine — quản lý trạng thái đối tượng xuyên thời gian thay vì xử lý
vi phạm theo từng frame.

Vấn đề giải quyết (Priority 1, docs):
    Pipeline cũ xử lý mỗi frame độc lập:
        Frame → Detect → Violation → DB
    1 frame lỗi (YOLO nhầm nhãn, OCR đọc sai) tạo violation ngay lập tức
    dù các frame khác của cùng track_id đều đúng → log đầy rác, bảo vệ
    mất niềm tin vào hệ thống.

Luồng mới:
        Frame → Detect → Tracking → TrackState → EventDecision → Violation
    TrackState lưu lịch sử nhãn từng frame cho MỖI track_id; EventDecision
    chỉ ghi log khi đủ bằng chứng (streak N frame liên tiếp cùng nhãn
    vi phạm trong cửa sổ T).

Thiết kế:
    - 1 EventManager instance / pipeline (per-pipeline, KHÔNG global) — track
      của gate A không liên quan gate B.
    - TrackState là rolling window lưu (label, timestamp, plate_read) cho
      TỪNG track_id. TTL = grace_period_sec (mặc định 2s): track_id không
      xuất hiện lại trong TTL sẽ bị prune khỏi bộ nhớ.
    - update(track_id, frame_evidence) được gọi mỗi frame detect; trả về
      `EventDecision` (commit | defer | skip) để pipeline biết phải làm gì.
    - Hàm `commit()` chỉ là QUYẾT ĐỊNH — không ghi DB. Pipeline vẫn giữ
      trách nhiệm _process_violations / _persist_violation (tách rõ
      "quyết định" và "hành động" để test được logic quyết định độc lập).

Lưu ý:
    - EventManager KHÔNG thay thế PlateVoter / _smooth_vehicle_type — những
      module đó vẫn chạy trên từng frame để lấy best-estimate cho frame hiện
      tại. EventManager chỉ thêm 1 lớp "đủ bằng chứng chưa" trước khi cho
      phép log.
    - Nếu track_id = None (tracker chưa confirm), track đó KHÔNG qua
      EventManager — pipeline vẫn xử lý per-frame như cũ (giữ hành vi
      cũ cho đường fallback, không tạo thêm ràng buộc mới).
"""
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# Ngưỡng mặc định — match docs (Priority 1):
#   "≥5 frame NO_HELMET liên tiếp trong cửa sổ 2 giây"
DEFAULT_STREAK_MIN_FRAMES = 5
DEFAULT_WINDOW_SEC = 2.0
DEFAULT_GRACE_PERIOD_SEC = 2.0


class DecisionKind(str, Enum):
    """Kết quả quyết định của EventManager.update()."""
    COMMIT = "commit"    # Đủ bằng chứng → pipeline được phép ghi violation
    DEFER = "defer"      # Chưa đủ → pipeline vẫn xử lý frame (cache, OCR) nhưng KHÔNG log
    SKIP = "skip"        # Track này không có vi phạm (label an toàn) → pipeline bỏ qua


@dataclass
class FrameEvidence:
    """Bằng chứng 1 frame về 1 track_id — do pipeline thu thập, EventManager
    chỉ đọc. Tách thành dataclass riêng để test dễ (không phải mock cả group)."""
    track_id: int
    violation_label: Optional[str]  # label vi phạm của frame này, None = an toàn
    plate_read: str = ""
    helmet_status: str = "unknown"
    ts: float = field(default_factory=time.time)


@dataclass
class EventDecision:
    """Quyết định trả về cho pipeline sau khi EventManager xem xét evidence."""
    kind: DecisionKind
    track_id: int
    # Khi COMMIT: label đã đủ bằng chứng (vd. 'NO_HELMET'). Khi DEFER/SKIP: None.
    label: Optional[str] = None
    # Số frame liên tiếp cùng label trong cửa sổ hiện tại (cho debug/log).
    streak: int = 0
    # Biển số ổn định nhất trong cửa sổ (vote từ các frame gần nhất). Khi
    # COMMIT, pipeline dùng plate_read này thay vì OCR frame hiện tại để
    # giảm log biển đọc nhầm 1-frame.
    plate_read: str = ""


@dataclass
class _TrackState:
    """State nội bộ cho 1 track_id — KHÔNG export."""
    track_id: int
    first_seen: float
    last_seen: float
    # deque các (label, ts, plate_read) trong cửa sổ window_sec hiện tại.
    evidence: deque = field(default_factory=deque)
    # True nếu EventManager đã COMMIT cho track này trong TTL cooldown —
    # chặn COMMIT lại lần nữa cho cùng 1 lần xuất hiện (vd. 1 người vi phạm
    # 30 frame liên tiếp không được ghi 6 lần).
    committed_at: Optional[float] = None
    committed_label: Optional[str] = None

    # Đếm streak frame liên tiếp cùng label vi phạm gần nhất (cho debug).
    current_streak_label: Optional[str] = None
    current_streak_count: int = 0


class EventManager:
    """
    Quản lý trạng thái đối tượng xuyên thời gian + quyết định khi nào
    vi phạm đủ căn cứ để ghi log.

    Quy tắc quyết định (Priority 1 — docs):
        - Label None (an toàn) → reset streak, decision = SKIP.
        - Label có giá trị X:
            + Nếu frame hiện tại là X, tăng streak.
            + Nếu frame hiện tại KHÁC X, reset streak về 1.
            + Nếu streak >= streak_min_frames VÀ trong window_sec → COMMIT.
            + Sau khi COMMIT, set committed_at; lần tiếp theo cùng streak
              sẽ trả DEFER cho tới khi track_id biến mất (TTL) hoặc đổi
              sang label khác → reset cooldown, cho phép COMMIT lại nếu
              label mới đạt streak.
        - TTL (grace_period_sec): track_id không xuất hiện trong TTL sẽ
          bị prune khỏi _tracks, lần xuất hiện lại sau đó coi như track mới
          (reset streak, reset committed_at).

    Thread-safety: KHÔNG thread-safe. EventManager là per-pipeline và chỉ
    được gọi từ _run_loop của pipeline (1 thread duy nhất).
    """

    def __init__(
        self,
        streak_min_frames: int = DEFAULT_STREAK_MIN_FRAMES,
        window_sec: float = DEFAULT_WINDOW_SEC,
        grace_period_sec: float = DEFAULT_GRACE_PERIOD_SEC,
    ):
        if streak_min_frames < 1:
            raise ValueError("streak_min_frames phải >= 1")
        if window_sec <= 0:
            raise ValueError("window_sec phải > 0")
        if grace_period_sec <= 0:
            raise ValueError("grace_period_sec phải > 0")

        self.streak_min_frames = streak_min_frames
        self.window_sec = window_sec
        self.grace_period_sec = grace_period_sec
        self._tracks: dict[int, _TrackState] = {}

    # ─── Public API ───────────────────────────────────────────────────────

    def update(self, evidence: FrameEvidence, now: Optional[float] = None) -> EventDecision:
        """Đưa bằng chứng 1 frame về 1 track_id vào bộ nhớ, trả về quyết định.

        Hàm này KHÔNG ghi DB, KHÔNG gọi IO. Pipeline dựa vào `decision.kind`
        để biết phải làm gì tiếp theo:
            - COMMIT  → đủ bằng chứng, được phép ghi violation
            - DEFER   → chưa đủ, tiếp tục cache/OCR nhưng không log
            - SKIP    → label an toàn, bỏ qua hoàn toàn
        """
        if now is None:
            now = evidence.ts

        # 1. Prune track_id đã hết TTL
        self._prune_expired(now)

        # 2. Lấy/ tạo state cho track_id này
        state = self._tracks.get(evidence.track_id)
        if state is None:
            state = _TrackState(
                track_id=evidence.track_id,
                first_seen=now,
                last_seen=now,
            )
            self._tracks[evidence.track_id] = state

        # 3. Cập nhật evidence window
        state.last_seen = now
        state.evidence.append((evidence.violation_label, now, evidence.plate_read))
        # Bỏ mẫu quá cũ (ngoài window_sec)
        cutoff = now - self.window_sec
        while state.evidence and state.evidence[0][1] < cutoff:
            state.evidence.popleft()

        # 4. Cập nhật streak
        label = evidence.violation_label
        if label is None:
            # Frame an toàn → reset streak, reset committed_at (nếu có)
            # để lần vi phạm SAU này được coi là sự kiện mới.
            state.current_streak_label = None
            state.current_streak_count = 0
            state.committed_at = None
            state.committed_label = None
            return EventDecision(kind=DecisionKind.SKIP, track_id=evidence.track_id)

        if state.current_streak_label == label:
            state.current_streak_count += 1
        else:
            # Đổi label → reset streak, reset committed_at để label mới
            # có cơ hội COMMIT nếu đạt streak.
            state.current_streak_label = label
            state.current_streak_count = 1
            if state.committed_label != label:
                state.committed_at = None
                state.committed_label = None

        # 5. Quyết định
        enough_streak = state.current_streak_count >= self.streak_min_frames
        # Đã commit cho label này trong grace_period? → DEFER (chặn spam log
        # khi 1 người vi phạm 30 frame liên tiếp).
        if state.committed_at is not None and state.committed_label == label:
            already_committed_recently = (now - state.committed_at) < self.grace_period_sec
            if already_committed_recently:
                return EventDecision(
                    kind=DecisionKind.DEFER,
                    track_id=evidence.track_id,
                    label=label,
                    streak=state.current_streak_count,
                    plate_read=self._vote_plate(state),
                )

        if enough_streak:
            state.committed_at = now
            state.committed_label = label
            return EventDecision(
                kind=DecisionKind.COMMIT,
                track_id=evidence.track_id,
                label=label,
                streak=state.current_streak_count,
                plate_read=self._vote_plate(state),
            )

        return EventDecision(
            kind=DecisionKind.DEFER,
            track_id=evidence.track_id,
            label=label,
            streak=state.current_streak_count,
            plate_read=self._vote_plate(state),
        )

    def reset(self) -> None:
        """Xóa toàn bộ state (dùng khi restart pipeline, test)."""
        self._tracks.clear()

    def active_track_count(self) -> int:
        """Số track đang theo dõi (cho debug/health)."""
        return len(self._tracks)

    # ─── Internal ─────────────────────────────────────────────────────────

    def _prune_expired(self, now: float) -> None:
        """Xóa track không xuất hiện lại trong grace_period_sec — coi như
        track đã rời khung hình. KHÔNG prune track vừa update ở step trên
        (last_seen = now sẽ luôn >= now - grace)."""
        cutoff = now - self.grace_period_sec
        expired = [tid for tid, s in self._tracks.items() if s.last_seen < cutoff]
        for tid in expired:
            del self._tracks[tid]

    @staticmethod
    def _vote_plate(state: _TrackState) -> str:
        """Trả về plate_read xuất hiện nhiều nhất trong evidence window.
        Ưu tiên majority vote — giảm log biển đọc nhầm 1-frame."""
        counts: dict[str, int] = {}
        for _label, _ts, plate in state.evidence:
            if plate:
                counts[plate] = counts.get(plate, 0) + 1
        if not counts:
            return ""
        return max(counts.items(), key=lambda kv: kv[1])[0]
