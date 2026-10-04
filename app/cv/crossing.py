"""
Gate Crossing Detector — phát hiện xe CÁN QUA vạch mốc bằng MỘT điểm neo cố
định của xe (vehicle_anchor), không dùng bbox overlap/toàn bộ bbox qua vạch.

Nguyên tắc (thay thế bản cũ đối xứng "3 frame mỗi phía"):
  - Anchor = bottom-center bbox xe (vehicle_anchor()) — KHÔNG phải tâm bbox,
    KHÔNG phải person. Camera nhìn chéo nên bottom-center bám sát điểm bánh
    xe chạm đất hơn tâm hình học của cả bbox.
  - Side xác định bằng get_line_side(): signed cross product so với ĐOẠN
    THẲNG P1→P2 (không phải đường thẳng vô hạn) — anchor chiếu ra ngoài đoạn
    [P1,P2] thì side=0 (không quan sát được lúc này, không đổi state gì cả).
  - Dead-zone quanh line (edge_margin): anchor trong dead-zone → side=0,
    không đổi stable_side, không reset streak phía đang đếm.
  - Phía TRƯỚC vạch (stable_side) cần ≥min_frames_per_side frame liên tiếp
    mới được xác nhận lần đầu. NHƯNG sau khi đã có stable_side, CHỈ CẦN 1
    frame quan sát rõ ràng (ngoài dead-zone) ở phía đối diện là CHỐT
    CROSSING NGAY — không đợi phía mới cũng ổn định thêm N frame. Bản cũ đối
    xứng 3+3 luôn trễ ~N frame SAU khi xe đã thực sự qua vạch mới công nhận;
    đây chính là độ trễ cần loại bỏ.
  - Track biến mất (không gọi update() nữa) KHÔNG BAO GIỜ được coi là
    crossing — thuật toán chỉ có thể fire BÊN TRONG một lời gọi update()
    thành công, không có suy luận nào từ việc track hết hạn/bị prune.
  - Sau khi crossing 1 lần: latch (không crossing lại) cho tới khi anchor
    thực sự rời xa line ≥ rearm_distance VÀ qua cooldown_sec — tránh anchor
    rung nhẹ quanh line (YOLO bbox jitter) tạo liên tiếp nhiều event cho
    cùng 1 lượt xe đi qua.
  - Direction: ENTER (phía ABOVE→BELOW) / EXIT (BELOW→ABOVE) — pipeline có
    thể lọc theo allowed_direction nếu chỉ muốn cảnh báo 1 chiều.

ROI và biên khung hình KHÔNG thuộc phạm vi module này — detector chỉ biết
anchor + đường cắt, không biết gì về ROI polygon hay mép ảnh (xem comment ở
app/cv/pipeline.py _is_touching_frame_edge/_update_crossing).
"""
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    """Phía của xe so với đường cắt."""
    ABOVE = "above"   # Phía "âm" (cross product < 0)
    ON = "on"          # Trong dead-zone HOẶC chiếu ra ngoài đoạn P1-P2
    BELOW = "below"    # Phía "dương" (cross product > 0)


class Direction(str, Enum):
    ENTER = "enter"    # ABOVE -> BELOW
    EXIT = "exit"      # BELOW -> ABOVE
    UNKNOWN = "unknown"


def vehicle_anchor(bbox: tuple) -> tuple[float, float]:
    """Điểm đại diện CỐ ĐỊNH của xe dùng để xác định crossing — bottom-center
    bbox, tính lại mỗi frame cho cùng 1 vehicle_track_id. KHÔNG dùng tâm
    bbox, KHÔNG dùng bbox của person."""
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, y2


def _signed_side_and_projection(px, py, x1, y1, x2, y2):
    """(normalized_signed_distance, segment_length, t). t=0 tại P1, t=1 tại
    P2 — dùng để loại điểm chiếu ra NGOÀI đoạn thẳng thật sự (xem TEST 12)."""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return 0.0, 0.0, 0.0
    tx, ty = px - x1, py - y1
    cross = dx * ty - dy * tx
    length = length_sq ** 0.5
    t = (tx * dx + ty * dy) / length_sq
    return cross / length, length, t


def get_line_side(point: tuple, line_p1: tuple, line_p2: tuple,
                  deadzone: float = 0.0, segment_margin: float = 0.0) -> int:
    """Phía của `point` so với ĐOẠN THẲNG line_p1→line_p2. Trả -1 / 0 / +1.

    0 nghĩa là "không xác định được side lúc này" — xảy ra khi: (a) điểm nằm
    trong dead-zone quanh line, HOẶC (b) điểm chiếu ra ngoài đoạn [P1,P2]
    (cho phép nới nhẹ `segment_margin`, mặc định 0 = đúng y hệt đoạn gốc).
    Cả 2 trường hợp đều KHÔNG được dùng để đổi stable_side hay suy ra
    crossing — caller phải coi như "chưa quan sát được" frame này.
    """
    px, py = point
    x1, y1 = line_p1
    x2, y2 = line_p2
    normalized_dist, length, t = _signed_side_and_projection(px, py, x1, y1, x2, y2)
    if length == 0:
        return 0
    if t < -segment_margin or t > 1 + segment_margin:
        return 0
    if abs(normalized_dist) <= deadzone:
        return 0
    return -1 if normalized_dist < 0 else 1


_SIDE_ENUM = {-1: Side.ABOVE, 0: Side.ON, 1: Side.BELOW}


def direction_for_motion(gate_line, motion):
    """'enter'/'exit' meaning "anchor moves down" or "up" in the image across
    this line, or None for 'any' / a near-vertical line (no up/down sense)."""
    if motion not in ('down', 'up') or not gate_line:
        return None
    x1, y1, x2, y2 = gate_line
    if abs(x2 - x1) < 1e-6:
        return None
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    below = get_line_side((mx, my + .01), (x1, y1), (x2, y2))
    if below == 0:
        return None
    down = Direction.ENTER.value if below == 1 else Direction.EXIT.value  # ENTER = -1 -> +1
    up = Direction.EXIT.value if down == Direction.ENTER.value else Direction.ENTER.value
    return down if motion == 'down' else up


@dataclass
class _TrackState:
    track_id: int
    stable_side: int = 0           # phía đã XÁC NHẬN ổn định; 0 = chưa biết
    streak_value: int = 0          # side thô đang được đếm streak
    streak_count: int = 0
    last_seen: float = 0.0
    last_frame_seq: int | None = None
    has_crossed: bool = False      # tên giữ nguyên để tương thích chỗ gọi cũ (hist.has_crossed)
    crossed_at: float | None = None
    crossed_direction: str = Direction.UNKNOWN.value
    crossing_latched: bool = False
    rearmed: bool = True           # True = sẵn sàng cho 1 lần crossing MỚI
    max_dist_since_crossing: float = 0.0
    # Phase 4 (Task 1): timestamp lần đầu tiên anchor rời khỏi phía ổn định
    # — dùng để enforce `max_transition_sec`. Nếu streak phía đích chưa đủ
    # mẫu trong cửa sổ → reset, không chốt.
    transition_started_at: float | None = None


class CrossingDetector:
    """
    Theo dõi vehicle_anchor qua các frame và phát hiện crossing qua gate_line.

    Usage:
        detector = CrossingDetector(gate_line=[x1,y1,x2,y2], edge_margin=0.02)
        for group in groups:
            ax, ay = vehicle_anchor(group['_vehicle'].bbox)
            side, crossed = detector.update(track_id, ax/frame_w, ay/frame_h, now)
    """

    def __init__(
        self,
        gate_line: list | None,  # [x1,y1,x2,y2] normalized [0,1]
        edge_margin: float = 0.02,
        min_frames_per_side: int = 3,
        max_crossing_sec: float = 5.0,  # vestigial — giữ cho tương thích constructor cũ, không dùng trong thuật toán instant-post-cross (xem docstring module)
        rearm_distance: float = 0.05,
        cooldown_sec: float = 2.0,
        allowed_direction: str | None = None,  # None = cả 2 chiều; 'enter'/'exit' = chỉ tính chiều đó
        segment_margin: float = 0.0,
        # Phase 4 (Task 1): chốt lượt đúng 3+3. Phía đích cũng cần
        # `min_frames_exit_side` mẫu ổn định (mặc định 3) — KHÔNG chốt
        # ngay frame đầu tiên ra khỏi dead-zone. Set =1 để legacy 3+1.
        min_frames_exit_side: int = 3,
        # Phase 4 (Task 1): tổng thời gian từ "xác nhận phía đầu" đến
        # "xác nhận phía đích" tối đa 5s — quá → reset stable_side, không
        # chốt. Trước đây không có → 17 giây giãn cách vẫn nhận crossing.
        max_transition_sec: float = 5.0,
    ):
        self.gate_line = gate_line  # None = chưa cấu hình → không crossing
        self.edge_margin = edge_margin
        self.min_frames_per_side = min_frames_per_side
        self.min_frames_exit_side = max(1, min_frames_exit_side)
        self.max_crossing_sec = max_crossing_sec
        self.max_transition_sec = max_transition_sec
        self.rearm_distance = rearm_distance
        self.cooldown_sec = cooldown_sec
        self.allowed_direction = allowed_direction
        self.segment_margin = segment_margin
        self._tracks: dict[int, _TrackState] = {}

    @property
    def is_configured(self) -> bool:
        """True nếu đã có cấu hình gate_line."""
        return self.gate_line is not None

    def update(
        self, track_id: int, cx_normalized: float, cy_normalized: float,
        timestamp: float, frame_seq: int | None = None,
        frame_size: tuple[int, int] | None = None,
    ) -> tuple[Side, bool]:
        """Cập nhật vị trí anchor hiện tại của track_id và trả (side, crossed).

        `frame_size` không còn dùng để tính pixel margin (dead-zone giờ tính
        thuần theo tọa độ chuẩn hóa) — tham số giữ lại để tương thích chữ ký
        lời gọi cũ trong pipeline.py.
        """
        if not self.is_configured:
            return Side.ON, False
        x1, y1, x2, y2 = self.gate_line

        state = self._tracks.get(track_id)
        if state is None:
            state = _TrackState(track_id=track_id)
            self._tracks[track_id] = state
        elif (timestamp <= state.last_seen or
              (frame_seq is not None and state.last_frame_seq is not None
               and frame_seq <= state.last_frame_seq)):
            # Mẫu trùng/cũ (cache frame skip gọi lại) — không xử lý lại.
            return _SIDE_ENUM.get(state.stable_side, Side.ON), False

        state.last_seen = timestamp
        state.last_frame_seq = frame_seq

        # Dead-zone theo % ĐƯỜNG CHÉO khung hình thật (không phải % cạnh
        # normalized 0-1) — khung hình thường không vuông (vd 1920x1080), áp
        # margin thuần trong không gian normalized sẽ méo (hình elip thay vì
        # tròn theo pixel thật). Quy đổi sang pixel khi có frame_size, giữ
        # nguyên normalized nếu không có (test thuần thuật toán).
        if frame_size:
            w, h = frame_size
            side_point = (cx_normalized * w, cy_normalized * h)
            side_line = ((x1 * w, y1 * h), (x2 * w, y2 * h))
            deadzone = self.edge_margin * (w * w + h * h) ** 0.5
        else:
            side_point = (cx_normalized, cy_normalized)
            side_line = ((x1, y1), (x2, y2))
            deadzone = self.edge_margin
        raw = get_line_side(side_point, *side_line,
                            deadzone=deadzone, segment_margin=self.segment_margin)

        crossed = False
        if raw != 0:
            if raw == state.streak_value:
                state.streak_count += 1
            else:
                state.streak_value = raw
                state.streak_count = 1

            if state.stable_side == 0:
                # Chưa từng xác định phía — cần đủ streak mới thiết lập lần đầu.
                if state.streak_count >= self.min_frames_per_side:
                    state.stable_side = raw
                    # N04 (Post-Video Review): transition_started_at phải
                    # neo vào thời điểm `stable_side` được xác nhận, không
                    # phải frame xung đối đầu tiên. Khoảng "transition" =
                    # từ frame ổn định cuối cùng ở phía đầu đến frame hiện
                    # tại. Trước đây neo vào frame B đầu tiên nên 3A → gap
                    # 17s → 3B liên tiếp vẫn CROSSING vì timer chỉ mới
                    # được tính từ frame B đầu (≈0.1s ago).
                    state.transition_started_at = timestamp
            elif raw != state.stable_side:
                # Phía đối lập với phía đã ổn định. KHÔNG chốt crossing
                # ngay nếu `min_frames_exit_side` > 1 — đợi đủ mẫu ổn định
                # phía đích. Đồng thời enforce `max_transition_sec` đo từ
                # `transition_started_at` (lần cuối xác nhận stable_side):
                # nếu đã quá thời gian cho phép → reset, không chốt.
                transition_elapsed = timestamp - (state.transition_started_at or timestamp)
                if transition_elapsed > self.max_transition_sec:
                    # Quá thời gian → reset; coi như phía đầu chưa ổn định
                    state.stable_side = raw  # lấy phía mới làm baseline
                    state.streak_value = raw
                    state.streak_count = 1
                    state.transition_started_at = timestamp  # neo timer mới
                elif state.streak_count >= self.min_frames_exit_side:
                    if not (state.crossing_latched and not state.rearmed):
                        direction = self._direction(state.stable_side, raw)
                        if self.allowed_direction is None or direction == self.allowed_direction:
                            crossed = True
                            state.has_crossed = True
                            state.crossed_at = timestamp
                            state.crossed_direction = direction
                            state.crossing_latched = True
                            state.rearmed = False
                            state.max_dist_since_crossing = 0.0
                        state.stable_side = raw
                        state.streak_value = raw
                        state.streak_count = 1
                        state.transition_started_at = timestamp  # neo timer mới
                # else: chưa đủ mẫu phía đích → tiếp tục đếm, KHÔNG reset
                # stable_side để chờ thêm frame cùng phía đích.
            else:
                # raw == stable_side: cùng phía đã biết, "làm mới" timer
                # transition. Đây là neo để khoảng cách phía đầu cuối
                # cùng → phía đích được đo từ frame xác nhận gần nhất.
                state.transition_started_at = timestamp

        if state.crossing_latched and not state.rearmed:
            dist, _, _ = _signed_side_and_projection(cx_normalized, cy_normalized, x1, y1, x2, y2)
            state.max_dist_since_crossing = max(state.max_dist_since_crossing, abs(dist))
            if (state.max_dist_since_crossing >= self.rearm_distance
                    and timestamp - (state.crossed_at or timestamp) >= self.cooldown_sec):
                state.rearmed = True
                state.crossing_latched = False

        return _SIDE_ENUM.get(raw if raw != 0 else state.stable_side, Side.ON), crossed

    @staticmethod
    def _direction(from_side: int, to_side: int) -> str:
        if from_side == -1 and to_side == 1:
            return Direction.ENTER.value
        if from_side == 1 and to_side == -1:
            return Direction.EXIT.value
        return Direction.UNKNOWN.value

    def reset(self) -> None:
        """Xóa toàn bộ track history (dùng khi restart pipeline hoặc đổi gate_line)."""
        self._tracks.clear()

    def get_crossing_count(self) -> int:
        """Số track đã crossing (cho debug/health)."""
        return sum(1 for s in self._tracks.values() if s.has_crossed)

    def get_active_track_count(self) -> int:
        """Số track đang theo dõi."""
        return len(self._tracks)
