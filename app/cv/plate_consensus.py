"""Plate consensus store — top N crops from DIFFERENT frames.

Phase 2 (Task 1) — Mục tiêu: thay vì chỉ OCR 1 crop tốt nhất (BestPlateStore),
giữ top 3–5 crop từ frame KHÁC NHAU, có quality/diversity scoring + cap
bytes/TTL. Consensus khi:
  - ≥2 mẫu đồng thuận (cùng chuỗi normalize) với confidence cao hơn ngưỡng
  - KHÔNG có mẫu cạnh tranh đáng tin (khác chuỗi, confidence ≥ ngưỡng)
  - quality của các mẫu đồng thuận >= ngưỡng tối thiểu

Thiết kế tách biệt khỏi BestPlateStore để:
  - BestPlateStore vẫn giữ 1 crop best (legacy code không vỡ).
  - Consensus store tận dụng các crop đã offer sẵn — `ingest_offer()` nhận
    candidate từ BestPlateStore.offer() hoặc trực tiếp từ detector.

Không duplicate EasyOCR reader: OCR qua `_ocr_task` (đã có trong pipeline).
Plate consensus KHÔNG làm thay chức năng OCR chính — nó chỉ vote kết quả
đã có từ `_ocr_task` futures.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.cv.ocr import normalize_valid_plate


@dataclass
class CropRecord:
    """Một crop đã được OCR xong, lưu kết quả + metadata để vote."""
    frame_id: int
    timestamp: float
    normalized: str          # chuỗi đã normalize, "" nếu không đọc được
    confidence: float
    quality_score: float     # quality từ make_candidate
    raw: dict = field(default_factory=dict)
    error: Optional[str] = None  # 'ocr_engine_error:RuntimeError' vv

    @property
    def is_readable(self) -> bool:
        return bool(self.normalized) and self.error is None


@dataclass
class _TrackBuffer:
    """Bộ đệm cho 1 vehicle track."""
    crops: list[CropRecord] = field(default_factory=list)
    seen_at: float = field(default_factory=time.monotonic)
    finalized: Optional[str] = None  # kết quả đã chốt, hoặc None
    finalized_at: Optional[float] = None


class PlateConsensusStore:
    """Top-N crop consensus từ các frame khác nhau.

    Cấu hình mặc định:
      - max_crops_per_track: 5     (top 3–5 crop khác frame)
      - consensus_min_agree: 2     (≥2 mẫu đồng thuận)
      - min_confidence: 0.55       (ngưỡng tối thiểu cho 1 mẫu được tính)
      - diversity_min_frame_gap: 2 (crop mới phải cách crop cũ ≥ N frame_seq)
      - ttl_sec: 30.0              (entry cũ bị prune sau khi không update)
      - max_tracks: 64             (cap bộ nhớ)
      - max_total_bytes: 100MB     (cap bytes gộp — dù không giữ crop ở đây,
                                    vẫn track ước lượng để không vượt budget)
    """

    MAX_CROPS = 5
    MIN_AGREE = 2
    MIN_CONFIDENCE = 0.55
    DIVERSITY_MIN_FRAME_GAP = 2
    TTL_SEC = 30.0
    MAX_TRACKS = 64
    # F04 (Task 1): chất lượng thực là điều kiện hợp lệ. quality_score=0 là
    # crop rỗng/lỗi/không đọc được → loại. Nếu MIN_QUALITY > 0, các mẫu
    # dưới ngưỡng bị bỏ qua trong decide() — không tính phiếu.
    MIN_QUALITY = 0.0
    # F04 (Task 1): chứng cớ cạnh tranh ĐÁNG TIN. Một mẫu đơn lẻ có
    # confidence ≥ CONTENDER_CONFIDENCE mà khác chuỗi với winner vẫn được
    # coi là "đối chứng mạnh" → winner KHÔNG confirmed, chuyển needs_review.
    # Trước F04: A(0.8)x2 + B(0.99)x1 → A wins (2 votes) dù B có
    # confidence cao hơn nhiều. Sau F04: A wins + B là contender → NOT
    # confirmed (None), caller chuyển sang needs_review.
    CONTENDER_CONFIDENCE = 0.95
    CONTENDER_MIN_QUALITY = 0.3

    def __init__(self, *,
                 max_crops_per_track: int = MAX_CROPS,
                 consensus_min_agree: int = MIN_AGREE,
                 min_confidence: float = MIN_CONFIDENCE,
                 diversity_min_frame_gap: int = DIVERSITY_MIN_FRAME_GAP,
                 ttl_sec: float = TTL_SEC,
                 max_tracks: int = MAX_TRACKS,
                 min_quality: float = MIN_QUALITY,
                 contender_confidence: float = CONTENDER_CONFIDENCE,
                 contender_min_quality: float = CONTENDER_MIN_QUALITY):
        self.max_crops_per_track = max(1, int(max_crops_per_track))
        self.consensus_min_agree = max(1, int(consensus_min_agree))
        self.min_confidence = float(min_confidence)
        self.diversity_min_frame_gap = max(0, int(diversity_min_frame_gap))
        self.ttl_sec = float(ttl_sec)
        self.max_tracks = max(1, int(max_tracks))
        self.min_quality = max(0.0, float(min_quality))
        self.contender_confidence = max(0.0, min(1.0, float(contender_confidence)))
        self.contender_min_quality = max(0.0, float(contender_min_quality))
        self._tracks: "OrderedDict[int, _TrackBuffer]" = OrderedDict()

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    def ingest_offer(self, track: int, crop_record: CropRecord) -> bool:
        """Nhận 1 crop đã OCR xong. Trả True nếu buffer có thêm entry.

        Phase 2:
          - Bỏ qua crop lặp frame (frame_id trùng với crop gần nhất).
          - Bỏ qua crop không đủ cách frame (diversity_min_frame_gap).
          - Bỏ qua crop không đọc được (normalized='' hoặc error).
          - Bỏ qua crop có confidence < min_confidence.
          - Giữ tối đa max_crops_per_track mẫu MỚI NHẤT.
          - Bỏ qua nếu buffer đã final.
        """
        if track is None:
            return False
        self.prune()
        if len(self._tracks) >= self.max_tracks:
            # evict track cũ nhất không phải final
            for old_track in list(self._tracks.keys()):
                buf = self._tracks[old_track]
                if buf.finalized is None:
                    self._tracks.pop(old_track, None)
                    break
            else:
                return False

        buf = self._tracks.setdefault(track, _TrackBuffer())
        if buf.finalized is not None:
            return False
        if not crop_record.is_readable:
            # vẫn cập nhật seen_at + track error crop để không vĩnh viễn mở
            buf.crops.append(crop_record)
            buf.seen_at = time.monotonic()
            # cap size: nếu đọc fail nhiều → chỉ giữ vài mẫu gần nhất
            if len(buf.crops) > self.max_crops_per_track:
                buf.crops = buf.crops[-self.max_crops_per_track:]
            return False
        if crop_record.confidence < self.min_confidence:
            buf.seen_at = time.monotonic()
            return False

        # Diversity: bỏ nếu frame_id quá gần frame gần nhất
        if buf.crops:
            latest_frame = max(c.frame_id for c in buf.crops)
            if crop_record.frame_id - latest_frame < self.diversity_min_frame_gap:
                buf.seen_at = time.monotonic()
                return False
            # Bỏ nếu trùng frame_id
            if any(c.frame_id == crop_record.frame_id for c in buf.crops):
                buf.seen_at = time.monotonic()
                return False

        buf.crops.append(crop_record)
        buf.seen_at = time.monotonic()
        # Cap size: giữ max_crops_per_track mẫu mới nhất
        if len(buf.crops) > self.max_crops_per_track:
            buf.crops = buf.crops[-self.max_crops_per_track:]
        return True

    # ------------------------------------------------------------------ #
    # Consensus decision
    # ------------------------------------------------------------------ #

    def decide(self, track: int) -> tuple[Optional[str], float, int]:
        """Trả (text_confirmed, confidence, sample_count) cho track.

        - text_confirmed = None → chưa consensus (cần thêm mẫu / mâu thuẫn /
          có chứng cớ cạnh tranh đáng tin)
        - text_confirmed = '' → consensus rỗng (engine error đủ nhiều)
        - text_confirmed = '59H12345' → biển đã đồng thuận

        Quy tắc (F04 cập nhật):
          - Bỏ qua crop có normalized='' hoặc error.
          - F04: bỏ qua crop có quality_score < min_quality (mặc định 0.0 →
            không lọc; production với `min_quality=0.3` sẽ loại crop rỗng/mờ).
          - Bỏ qua crop có confidence < min_confidence.
          - Group theo normalized, đếm sample_count + max confidence mỗi nhóm.
          - Nhóm nào có ≥ consensus_min_agree mẫu (tất cả confidence ≥
            min_confidence, quality ≥ min_quality) là candidate.
          - Nếu ≥ 2 nhóm cạnh tranh có ≥ min_agree mẫu đủ confidence → None.
          - F04: nếu 1 nhóm dominate (≥ min_agree) nhưng TỒN TẠI nhóm khác
            có ≥ 1 mẫu với confidence ≥ contender_confidence (mặc định 0.95)
            + quality ≥ contender_min_quality → None (chuyển needs_review
            — đối chứng mạnh không cho phép xác nhận mù).
          - Nếu 1 nhóm dominate và không có contender → finalize.
          - Nếu 0 nhóm đạt → None.
        """
        buf = self._tracks.get(track)
        if buf is None:
            return None, 0.0, 0
        if buf.finalized is not None:
            return buf.finalized, 0.0, 0  # already finalized

        # F04: quality filter là điều kiện hợp lệ — crop quality_score < min_quality
        # KHÔNG được tính là phiếu (trước đây chỉ filter confidence, để lọt
        # crop quality=0 vẫn tham gia vote).
        readable = [c for c in buf.crops if c.is_readable
                    and c.confidence >= self.min_confidence
                    and c.quality_score >= self.min_quality]
        if not readable:
            return None, 0.0, 0

        # Group by normalized
        groups: dict[str, list[CropRecord]] = {}
        for c in readable:
            groups.setdefault(c.normalized, []).append(c)

        # Tính cho mỗi group: sample_count, max_conf, avg_quality
        scored: list[tuple[str, int, float, float]] = []
        for text, items in groups.items():
            sample_count = len(items)
            max_conf = max(c.confidence for c in items)
            avg_quality = sum(c.quality_score for c in items) / sample_count
            scored.append((text, sample_count, max_conf, avg_quality))

        # Chỉ nhóm đạt min_agree
        qualified = [s for s in scored if s[1] >= self.consensus_min_agree]
        if len(qualified) == 0:
            return None, 0.0, 0
        if len(qualified) > 1:
            # Mâu thuẫn: không chốt
            return None, 0.0, 0

        # F04: kiểm tra chứng cớ cạnh tranh đáng tin. Tất cả các nhóm
        # (không bao gồm nhóm winner) có bất kỳ mẫu nào với
        # confidence >= contender_confidence + quality >= contender_min_quality
        # → winner KHÔNG được xác nhận (trả None, caller chuyển needs_review).
        winner_text = qualified[0][0]
        for text, items in groups.items():
            if text == winner_text:
                continue
            for c in items:
                if (c.confidence >= self.contender_confidence
                        and c.quality_score >= self.contender_min_quality):
                    # Contender mạnh, winner không đủ sạch → trả None.
                    # Caller xem (None, 0.0, 0) → chuyển sang needs_review.
                    return None, 0.0, 0

        text, sample_count, max_conf, _avg_q = qualified[0]
        return text, max_conf, sample_count

    def finalize(self, track: int) -> Optional[str]:
        """Đánh dấu track đã chốt với consensus hiện tại. Sau khi finalize
        sẽ KHÔNG nhận thêm crop. Trả về text_confirmed hoặc None nếu chưa
        đủ điều kiện."""
        text, conf, n = self.decide(track)
        if text is None:
            return None
        buf = self._tracks.get(track)
        if buf is None:
            return None
        # Normalize lần cuối (giả định readable đã qua normalize_valid_plate)
        normalized = normalize_valid_plate(text)
        buf.finalized = normalized or text
        buf.finalized_at = time.monotonic()
        return buf.finalized

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def is_finalized(self, track: int) -> bool:
        buf = self._tracks.get(track)
        return buf is not None and buf.finalized is not None

    def finalized_text(self, track: int) -> Optional[str]:
        buf = self._tracks.get(track)
        return buf.finalized if buf else None

    def progress(self, track: int) -> dict:
        """Trả về dict mô tả trạng thái hiện tại của track (debug/diagnostic)."""
        buf = self._tracks.get(track)
        if buf is None:
            return {"known": False}
        readable = [c for c in buf.crops if c.is_readable]
        return {
            "known": True,
            "crops_total": len(buf.crops),
            "crops_readable": len(readable),
            "frame_ids": [c.frame_id for c in buf.crops],
            "candidates": sorted({c.normalized for c in readable}),
            "finalized": buf.finalized,
            "elapsed_sec": round(time.monotonic() - buf.seen_at, 2),
        }

    def discard(self, track: int) -> None:
        self._tracks.pop(track, None)

    def reset(self) -> None:
        self._tracks.clear()

    def prune(self, now: Optional[float] = None) -> None:
        """Bỏ track quá hạn (không update + không có finalized mới)."""
        now = time.monotonic() if now is None else now
        for t in list(self._tracks.keys()):
            buf = self._tracks[t]
            if now - buf.seen_at > self.ttl_sec and buf.finalized is None:
                self._tracks.pop(t, None)

    # ------------------------------------------------------------------ #
    # Iteration (testing)
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self._tracks)
