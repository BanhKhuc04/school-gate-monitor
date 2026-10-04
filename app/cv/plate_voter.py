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


@dataclass
class PlateReadResult:
    text: str = ""              # biển số đã normalize, "" nếu không đọc được
    confidence: float = 0.0     # 0.0-1.0, từ ocr_fn (trung bình EasyOCR box confidence)
    sample_count: int = 0       # số lần đọc GIỐNG NHAU trong cửa sổ voting hiện tại
    is_confident: bool = False  # True nếu đủ điều kiện để tin dùng (tra whitelist)


@dataclass
class _Sample:
    text: str
    confidence: float
    ts: float


class PlateVoter:
    """
    Vote biển số theo vị trí (ô lưới thô quanh tâm bbox) + cửa sổ thời gian ngắn.

    is_confident = True khi:
      (a) cùng 1 text xuất hiện >= min_agree lần trong window_sec gần nhất, HOẶC
      (b) 1 lần đọc có confidence >= min_confidence_single (đọc rõ ngay từ đầu).
    Ngược lại is_confident = False — pipeline.py PHẢI bỏ qua bước tra whitelist
    khi is_confident=False (không tự đoán học sinh từ 1 lần đọc mơ hồ).
    """

    def __init__(self, grid_px: int, window_sec: float, min_agree: int, min_confidence_single: float):
        self.grid_px = grid_px
        self.window_sec = window_sec
        self.min_agree = min_agree
        self.min_confidence_single = min_confidence_single
        self._samples: dict[tuple[int, int], list[_Sample]] = {}
        self._MAX_CACHE_SIZE = 200  # dọn cache để không phình vô hạn, giống pattern cũ

    def _key(self, bbox: tuple[int, int, int, int]) -> tuple[int, int]:
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        return (cx // self.grid_px, cy // self.grid_px)

    def read(self, frame, plate_det, ocr_fn: Callable[[object], dict], key=None) -> PlateReadResult:
        """
        ocr_fn(crop) -> {'full': str, 'confidence': float} — thường là
        app.cv.ocr.read_plate_detailed, tiêm từ ngoài vào (xem docstring module).

        key: khóa gom phiếu — pipeline truyền ID theo dõi của xe (app/cv/tracker.py)
        để gom được phiếu của xe ĐANG CHẠY (vị trí đổi ô lưới liên tục). Không
        truyền thì gom theo ô lưới vị trí như cũ.
        """
        if key is None:
            key = self._key(plate_det.bbox)
        now = time.time()
        history = self._samples.setdefault(key, [])
        # Bỏ mẫu đã quá cũ (ngoài window) trước khi đọc mẫu mới
        history[:] = [s for s in history if now - s.ts < self.window_sec]

        # Nới box thêm 6% mỗi phía: box detect thường cắt sát mép, làm mất nét
        # chữ ở rìa biển số (ký tự đầu/cuối bị đọc sai hoặc mất hẳn).
        x1, y1, x2, y2 = plate_det.bbox
        pad_x = round((x2 - x1) * 0.06)
        pad_y = round((y2 - y1) * 0.06)
        frame_h, frame_w = frame.shape[:2]
        x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        x2, y2 = min(frame_w, x2 + pad_x), min(frame_h, y2 + pad_y)
        crop = frame[y1:y2, x1:x2]
        text = ""
        confidence = 0.0
        # Biển nhỏ (xe ở xa) vẫn được đọc — OCR tự phóng to crop trước khi đọc
        if crop.size > 0 and crop.shape[0] >= 12 and crop.shape[1] >= 20:
            result = ocr_fn(crop)
            text = result.get('full', '') or ''
            confidence = result.get('confidence', 0.0) or 0.0

        if text:
            history.append(_Sample(text=text, confidence=confidence, ts=now))

        self._maybe_prune(now)

        if not text:
            return PlateReadResult(text="", confidence=0.0, sample_count=0, is_confident=False)

        agreeing = [s for s in history if s.text == text]
        sample_count = len(agreeing)
        best_confidence = max((s.confidence for s in agreeing), default=confidence)

        is_confident = (
            sample_count >= self.min_agree
            or best_confidence >= self.min_confidence_single
        )

        return PlateReadResult(
            text=text,
            confidence=best_confidence,
            sample_count=sample_count,
            is_confident=is_confident,
        )

    def _maybe_prune(self, now: float):
        if len(self._samples) <= self._MAX_CACHE_SIZE:
            return
        self._samples = {
            k: v for k, v in self._samples.items()
            if v and now - v[-1].ts < self.window_sec
        }
