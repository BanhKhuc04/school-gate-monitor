"""F04 regression tests (Task 1) — consensus competitive evidence + quality 0.

F04 review:
> F04 — P1: consensus chấp nhận đối chứng mạnh và crop chất lượng 0

Tái hiện:
- A(conf=.8) x2 + B(conf=.99) x1 → decide A, 2 samples (BUG: B mạnh bị bỏ qua).
- A(conf=.8) x2 + A(conf=.8) x2, cả hai quality_score=0 → decide A, 2 samples
  (BUG: crop rỗng/lỗi vẫn tính phiếu).

Sau F04 fix:
- A(0.8)x2 + B(0.99)x1 → KHÔNG confirmed, trả None (winner A nhưng có
  contender B với confidence ≥ 0.95 + quality ≥ 0.3 → needs_review).
- 2 mẫu quality_score < min_quality → KHÔNG confirmed, trả None.
"""
from __future__ import annotations

import pytest

from app.cv.plate_consensus import CropRecord, PlateConsensusStore


def _cr(frame_id, text, confidence, quality=0.5):
    """Helper tạo CropRecord normalized."""
    from app.cv.ocr import normalize_valid_plate
    return CropRecord(
        frame_id=frame_id, timestamp=0.0,
        normalized=normalize_valid_plate(text) or text,
        confidence=confidence, quality_score=quality,
    )


class TestF04ContenderBlocksConfirmation:
    """F04: A wins by 2 votes, but B has very high confidence → no confirm."""

    def test_a_two_votes_with_high_conf_b_is_not_confirmed(self):
        """A(.8)x2, B(.99)x1 → A wins by count, but B is a strong contender
        (confidence ≥ CONTENDER_CONFIDENCE). decide() returns None
        (caller translates to needs_review)."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                contender_confidence=0.95,
                                contender_min_quality=0.3)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(14, "59B67890", 0.99, quality=0.7))
        text, conf, n = s.decide(track)
        assert text is None
        assert conf == 0.0
        assert n == 0

    def test_no_contender_still_confirms(self):
        """A(.8)x2, NO contender → confirms A."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                contender_confidence=0.95,
                                contender_min_quality=0.3)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.6))
        text, conf, n = s.decide(track)
        assert text == "59A12345"
        assert n == 2
        assert conf == pytest.approx(0.8)

    def test_low_confidence_contender_does_not_block(self):
        """A(.8)x2, B(.8)x1 (same confidence as A) → B is NOT a strong
        contender (below CONTENDER_CONFIDENCE), A confirmed."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                contender_confidence=0.95,
                                contender_min_quality=0.3)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(14, "59B67890", 0.8, quality=0.6))
        text, _, n = s.decide(track)
        assert text == "59A12345"
        assert n == 2

    def test_contender_with_low_quality_does_not_block(self):
        """B(.99)x1 nhưng quality=0.1 (< contender_min_quality=0.3) → B
        không đủ tư cách contender. A wins."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                contender_confidence=0.95,
                                contender_min_quality=0.3)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(14, "59B67890", 0.99, quality=0.1))
        text, _, n = s.decide(track)
        assert text == "59A12345"


class TestF04QualityZeroBlocksConfirmation:
    """F04: chất lượng crop thực là điều kiện hợp lệ. quality_score < min_quality
    → crop không được tính là phiếu."""

    def test_two_quality_zero_samples_not_confirmed(self):
        """A(conf=.8) x2 với quality_score=0 cả hai → KHÔNG confirmed
        khi min_quality > 0 (mặc định 0.1)."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                min_quality=0.1)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.0))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.0))
        text, _, n = s.decide(track)
        assert text is None
        assert n == 0

    def test_quality_zero_filtered_in_ingest(self):
        """Crop quality=0 vẫn được ingest (để track seen_at cập nhật) nhưng
        KHÔNG tham gia vote."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                min_quality=0.1)
        track = 1
        # 1 sample quality=0.8 OK + 1 sample quality=0 bị lọc
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.8))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.0))
        text, _, n = s.decide(track)
        # Chỉ 1 sample đủ chất lượng → chưa đủ min_agree=2 → None
        assert text is None
        assert n == 0

    def test_default_min_quality_zero_still_accepts_all(self):
        """min_quality=0.0 (default cũ) → chấp nhận mọi quality_score
        kể cả 0. Backward compat."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                min_quality=0.0)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.0))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.0))
        text, _, n = s.decide(track)
        assert text == "59A12345"
        assert n == 2


class TestF04ContenderAndQualityCombined:
    """F04: Kết hợp quality + contender — winner đạt đủ mẫu, không có
    contender, nhưng chất lượng crop thấp → KHÔNG confirmed."""

    def test_winner_passes_quality_but_contender_does_not(self):
        """A(.8)x2 quality=0.6, B(.99)x1 quality=0.05 (thấp) → A wins."""
        s = PlateConsensusStore(consensus_min_agree=2,
                                min_confidence=0.55,
                                min_quality=0.1,
                                contender_confidence=0.95,
                                contender_min_quality=0.3)
        track = 1
        s.ingest_offer(track, _cr(10, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(12, "59A12345", 0.8, quality=0.6))
        s.ingest_offer(track, _cr(14, "59B67890", 0.99, quality=0.05))
        text, _, n = s.decide(track)
        # B quality thấp → không phải contender → A wins
        assert text == "59A12345"
        assert n == 2
