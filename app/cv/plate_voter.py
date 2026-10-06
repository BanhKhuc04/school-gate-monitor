"""
Vote biển số qua nhiều lần đọc gần nhau về thời gian + vị trí (Bước 1, đợt 2).

Thay logic cache đơn giản cũ trong pipeline.py (1 giá trị text/vị trí, không có
confidence) bằng rolling window nhiều mẫu/vị trí — vẫn dùng chung khái niệm "ô
lưới vị trí" (grid_px) đã có trong _OCR_CACHE_GRID cũ, không đổi cách nhóm.

Thiết kế tách riêng khỏi pipeline.py và tiêm ocr_fn qua tham số (không import
cứng read_plate_detailed) để sau này đổi OCR engine chỉ cần đổi callable truyền
vào, không phải sửa lại pipeline.py.
"""
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.cv.ocr import validate_plate_format


@dataclass
class PlateReadResult:
    text: str = ""              # biển số đã normalize, "" nếu không đọc được
    confidence: float = 0.0     # 0.0-1.0, từ ocr_fn (trung bình EasyOCR box confidence)
    sample_count: int = 0       # số lần đọc GIỐNG NHAU trong cửa sổ voting hiện tại
    is_confident: bool = False  # True nếu đủ điều kiện để tin dùng (tra whitelist)
    # R2: pending=True khi OCR async đang chạy, chưa có kết quả fresh.
    # Caller KHÔNG nên commit biển số khi pending=True (R4).
    pending: bool = False
    # R4: error key từ OCR engine (vd 'ocr_engine_error:RuntimeError'). Caller
    # dùng để phân biệt lỗi kỹ thuật với OCR rỗng tự nhiên.
    error: Optional[str] = None
    # Diagnostic text may be incomplete; it must never be used for matching.
    raw_text: str = ''


@dataclass
class _Sample:
    text: str
    confidence: float
    ts: float
    frame_key: tuple | None = None


class PlateVoter:
    """
    UT2: Vote biển số theo track_id (danh tính) thay vì vị trí lưới.

    Lý do đổi: vị trí lưới (grid_px) thất bại khi xe đi nhanh qua nhiều ô lưới
    trong 2.5s — không đủ mẫu vote cùng 1 ô để đạt `min_agree`, rơi về ngưỡng
    đơn (không đạt vì ảnh mờ do chuyển động). Track_id ổn định xuyên suốt
    phiên xuất hiện trước cổng → mọi lần đọc dù ở vị trí nào cũng gộp vào
    cùng "làn" vote cho người/xe đó.

    Hỗ trợ cả 2 key song song:
      - track_id (ưu tiên) — ổn định khi đối tượng đi qua nhiều vị trí
      - grid_px (fallback) — dùng khi track_id chưa confirm (None) để vote
        theo vị trí như cũ, đảm bảo vẫn hoạt động khi tracker đang warm-up
        hoặc gặp người đứng yên không tạo track.

    is_confident = True khi:
      cùng 1 text xuất hiện qua ít nhất hai mẫu đủ confidence trong window_sec.
    Kết quả async còn kiểm tra frame riêng biệt và kết quả cạnh tranh đáng tin cậy.
    Ngược lại is_confident = False — pipeline.py PHẢI bỏ qua bước tra whitelist
    khi is_confident=False (không tự đoán học sinh từ 1 lần đọc mơ hồ).
    """

    def __init__(self, grid_px: int, window_sec: float, min_agree: int, min_confidence_single: float):
        self.grid_px = grid_px
        self.window_sec = window_sec
        self.min_agree = min_agree
        self.min_confidence_single = min_confidence_single
        # UT2: 2 cache tách biệt — key là track_id (ưu tiên) hoặc grid_key (fallback).
        # Tách thay vì gộp để dọn rác độc lập + tránh nhầm key.
        self._samples_by_track: dict[int, list[_Sample]] = {}
        self._samples_by_grid: dict[tuple[int, int], list[_Sample]] = {}
        self._MAX_CACHE_SIZE = 200

    def _grid_key(self, bbox: tuple[int, int, int, int]) -> tuple[int, int]:
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        return (cx // self.grid_px, cy // self.grid_px)

    def _get_history(self, plate_det):
        """UT2: chọn cache theo track_id (ưu tiên) hoặc grid (fallback)."""
        tid = getattr(plate_det, "track_id", None)
        if tid is not None:
            return self._samples_by_track.setdefault(tid, [])
        return self._samples_by_grid.setdefault(self._grid_key(plate_det.bbox), [])

    def read(self, frame, plate_det, ocr_fn: Callable[[object], dict]) -> PlateReadResult:
        """
        ocr_fn(crop) -> {'full': str, 'confidence': float} — thường là
        app.cv.ocr.read_plate_detailed, tiêm từ ngoài vào (xem docstring module).
        UT2: plate_det phải có thuộc tính track_id (None nếu tracker chưa confirm).

        R4: KHÔNG commit từ 1 lần đọc confidence cao — cần ≥2 crop khác frame
        đồng thuận (`sample_count >= min_agree`) HOẶC ≥2 lần đọc rõ ràng
        (`confidence >= min_confidence_single` AND sample_count >= 2).
        """
        history = self._get_history(plate_det)
        now = time.time()
        # Bỏ mẫu đã quá cũ (ngoài window) trước khi đọc mẫu mới
        history[:] = [s for s in history if now - s.ts < self.window_sec]

        x1, y1, x2, y2 = plate_det.bbox
        crop = frame[y1:y2, x1:x2]
        text = ""
        confidence = 0.0
        if crop.size > 0 and crop.shape[0] > 20 and crop.shape[1] > 40:
            result = ocr_fn(crop)
            text = result.get('full', '') or ''
            confidence = result.get('confidence', 0.0) or 0.0
            # R4: nếu OCR engine báo lỗi → set text rỗng nhưng KHÔNG tăng
            # sample_count (lỗi kỹ thuật không phải bằng chứng biển không rõ)
            if result.get('error'):
                text = ""
                confidence = 0.0

        # Loại thẳng các chuỗi không khớp định dạng biển VN trước khi đưa vào vote
        # (chữ nền/logo áo/label debug như "AHAMOVE", "PERSON89" không match regex
        # nên không bao giờ được coi là 1 lần đọc hợp lệ để cộng dồn sample_count).
        if text and not validate_plate_format(text):
            text = ""
            confidence = 0.0

        if text:
            history.append(_Sample(text=text, confidence=confidence, ts=now))

        self._maybe_prune(now)

        if not text:
            return PlateReadResult(text="", confidence=0.0, sample_count=0, is_confident=False)

        agreeing = [s for s in history if s.text == text]
        sample_count = len(agreeing)
        best_confidence = max((s.confidence for s in agreeing), default=confidence)

        # R4: is_confident yêu cầu tối thiểu 2 mẫu (khác frame) đồng thuận
        # VÀ confidence >= min_confidence_single. Không có đường tắt "2
        # mẫu đồng thuận là đủ" — biển số Việt Nam dễ đọc nhầm ký tự
        # liên tiếp (8↔B, 0↔D, …), 2 lần đọc cùng sai vẫn là sai.
        is_confident = (
            sample_count >= self.min_agree
            and best_confidence >= self.min_confidence_single
        )

        return PlateReadResult(
            text=text,
            confidence=best_confidence,
            sample_count=sample_count,
            is_confident=is_confident,
        )

    def _maybe_prune(self, now: float):
        if len(self._samples_by_track) + len(self._samples_by_grid) <= self._MAX_CACHE_SIZE:
            return
        # Dọn theo 2 cache độc lập, mỗi cache giữ lại key có mẫu trong window
        self._samples_by_track = {
            k: v for k, v in self._samples_by_track.items()
            if v and now - v[-1].ts < self.window_sec
        }
        self._samples_by_grid = {
            k: v for k, v in self._samples_by_grid.items()
            if v and now - v[-1].ts < self.window_sec
        }

    def add_result(self, plate_det, ocr_result: dict) -> PlateReadResult:
        """B2: Nhận kết quả OCR đã tính (từ async worker), vote và cache.

        Đây là phiên bản đồng bộ của read() — dùng khi OCR chạy async
        trong worker thread và kết quả đã có sẵn (từ Future.result()).
        Không gọi ocr_fn(); loại frame lặp, phiên cũ và không xác nhận khi
        có kết quả cạnh tranh đủ confidence trong cửa sổ.

        R4: Giống read(), KHÔNG commit từ 1 lần đọc. Cần ≥2 mẫu đồng thuận
        trong window_sec.
        """
        history = self._get_history(plate_det)
        now = time.time()
        history[:] = [s for s in history if now - s.ts < self.window_sec]
        seq = ocr_result.get('frame_seq')
        epoch = ocr_result.get('source_epoch', 0)
        frame_key = (epoch, seq) if seq is not None else None
        if frame_key is not None:
            history[:] = [s for s in history if s.frame_key is None or s.frame_key[0] == epoch]

        text = ocr_result.get('full', '') or ''
        confidence = ocr_result.get('confidence', 0.0) or 0.0
        # R4: OCR lỗi engine → không phải "không đọc được biển" — text=""
        if ocr_result.get('error'):
            text = ""
            confidence = 0.0

        if text and not validate_plate_format(text):
            text = ""
            confidence = 0.0

        if text and not (frame_key is not None and any(s.frame_key == frame_key for s in history)):
            history.append(_Sample(text=text, confidence=confidence, ts=now, frame_key=frame_key))

        self._maybe_prune(now)

        if not text:
            return PlateReadResult(text="", confidence=0.0, sample_count=0, is_confident=False,
                                   error=ocr_result.get("error"), raw_text=ocr_result.get('full', '') or '')

        agreeing = [s for s in history if s.text == text]
        sample_count = len(agreeing)
        best_confidence = max((s.confidence for s in agreeing), default=confidence)

        # R4: ≥2 mẫu đồng thuận (sample_count >= min_agree) VÀ confidence >=
        # min_confidence_single. Cả hai điều kiện đều cần thiết — không
        # đường tắt.
        is_confident = (
            len([s for s in agreeing if s.confidence >= self.min_confidence_single]) >= max(2, self.min_agree)
            and not any(s.text != text and s.confidence >= self.min_confidence_single for s in history)
        )

        return PlateReadResult(
            text=text,
            confidence=best_confidence,
            sample_count=sample_count,
            is_confident=is_confident,
        )
