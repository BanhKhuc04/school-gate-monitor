"""R5 — Voting ký tự + metadata xuyên luồng (Owner A).

Theo handoff §3 R5:
- Giữ tối đa 5 crop khác frame trong cửa sổ 2 giây.
- Hai frame độc lập mới có thể chốt.
- 1 nhóm dominate + contender mạnh (≥ 0.95 conf) → None (cần review).
- 2 nhóm cạnh tranh đều đủ min_agree → None (mâu thuẫn).
- Quality dưới ngưỡng bị loại.
- Finalized không ingest thêm.

Test tập trung vào `PlateConsensusStore` — voting logic cốt lõi.
"""
from __future__ import annotations

import time

import pytest

from app.cv.plate_consensus import (
    CropRecord,
    PlateConsensusStore,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _crop(frame_id: int, normalized: str, confidence: float = 0.9,
          quality_score: float = 0.5, error: str = None) -> CropRecord:
    return CropRecord(
        frame_id=frame_id,
        timestamp=time.monotonic(),
        normalized=normalized,
        confidence=confidence,
        quality_score=quality_score,
        error=error,
    )


# ── 1. Hai mẫu đồng thuận → chốt ─────────────────────────────────────────


def test_two_agreeing_samples_finalize():
    """2 mẫu cùng normalized, đủ confidence, khác frame → chốt."""
    store = PlateConsensusStore()
    assert store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    assert store.ingest_offer(1, _crop(5, "59A123", confidence=0.85))
    text, conf, count = store.decide(1)
    assert text == "59A123"
    assert count == 2
    assert conf >= 0.8


# ── 2. Một mẫu không chốt ────────────────────────────────────────────────


def test_single_sample_does_not_finalize():
    """1 mẫu duy nhất KHÔNG đủ để chốt (cần ≥ 2 theo min_agree).

    Với min_agree=2 mặc định, group có 1 mẫu KHÔNG qualify → trả (None, 0.0, 0).
    """
    store = PlateConsensusStore()
    assert store.ingest_offer(1, _crop(1, "59A123", confidence=0.9))
    text, conf, count = store.decide(1)
    assert text is None
    # count là số mẫu của qualified group; không qualify nên = 0
    assert count == 0


# ── 3. Cap tối đa 5 crop ────────────────────────────────────────────────


def test_max_5_crops_per_track():
    """Sau 6 crop khác frame, chỉ giữ 5 mới nhất."""
    store = PlateConsensusStore(max_crops_per_track=5)
    for i in range(7):
        store.ingest_offer(1, _crop(i * 10, "59A123", confidence=0.8))
    # Lấy buffer nội bộ qua decide: count = 5
    text, conf, count = store.decide(1)
    assert count == 5


# ── 4. Diversity frame gap ──────────────────────────────────────────────


def test_diversity_frame_gap_filters_close_frames():
    """Crop cách frame gần nhất < diversity_min_frame_gap bị loại."""
    store = PlateConsensusStore(diversity_min_frame_gap=3)
    # Frame 1: ingest OK
    assert store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    # Frame 2: gap = 1 < 3 → drop
    assert not store.ingest_offer(1, _crop(2, "59A123", confidence=0.8))
    # Frame 5: gap = 4 >= 3 → OK
    assert store.ingest_offer(1, _crop(5, "59A123", confidence=0.85))
    text, conf, count = store.decide(1)
    assert count == 2  # chỉ 2 mẫu được giữ


# ── 5. 2 nhóm cạnh tranh đều đủ min_agree → None (mâu thuẫn) ──────────


def test_two_competing_groups_both_min_agree_returns_none():
    """2 nhóm cùng có ≥ min_agree mẫu, đủ confidence → mâu thuẫn, không chốt."""
    store = PlateConsensusStore(consensus_min_agree=2)
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    store.ingest_offer(1, _crop(5, "59A123", confidence=0.85))
    store.ingest_offer(1, _crop(10, "59B456", confidence=0.8))
    store.ingest_offer(1, _crop(15, "59B456", confidence=0.85))
    text, conf, count = store.decide(1)
    assert text is None, "Hai nhóm cạnh tranh đều đủ vote → None"


# ── 6. Contender mạnh (≥ 0.95 conf) chặn winner ─────────────────────────


def test_strong_contender_blocks_winner():
    """Nhóm A có 2 phiếu (đủ) nhưng tồn tại nhóm B với 1 mẫu conf ≥ 0.95 →
    chuyển needs_review (None), KHÔNG chốt A.
    """
    store = PlateConsensusStore(consensus_min_agree=2, contender_confidence=0.95)
    # Nhóm A: 2 phiếu đồng thuận
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.7))
    store.ingest_offer(1, _crop(5, "59A123", confidence=0.75))
    # Nhóm B: 1 mẫu conf rất cao → contender
    store.ingest_offer(1, _crop(10, "59B999", confidence=0.97))
    text, conf, count = store.decide(1)
    assert text is None, "Contender 0.95+ phải chặn winner"


# ── 7. Quality thấp bị loại ────────────────────────────────────────────


def test_low_quality_filtered():
    """Crop có quality_score < min_quality bị loại khi decide → không chốt."""
    store = PlateConsensusStore(min_quality=0.3, consensus_min_agree=2)
    # 2 mẫu: 1 OK, 1 quality thấp → readable list chỉ có 1 → count=0
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.9, quality_score=0.5))
    store.ingest_offer(1, _crop(5, "59A123", confidence=0.9, quality_score=0.1))
    text, conf, count = store.decide(1)
    assert text is None
    assert count == 0


# ── 8. Confidence dưới ngưỡng bị loại ───────────────────────────────────


def test_low_confidence_not_ingested():
    """Crop có confidence < min_confidence KHÔNG được ingest như crop hợp lệ."""
    store = PlateConsensusStore(min_confidence=0.6)
    # Confidence 0.5 < 0.6 → return False
    assert not store.ingest_offer(1, _crop(1, "59A123", confidence=0.5))
    # Crop đầu tiên KHÔNG được lưu
    text, conf, count = store.decide(1)
    assert text is None
    assert count == 0


# ── 9. Finalized track không nhận thêm crop ─────────────────────────────


def test_finalized_track_ignores_new_crops():
    """Sau khi finalize, track KHÔNG nhận thêm crop mới (tránh overwrite)."""
    store = PlateConsensusStore()
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    store.ingest_offer(1, _crop(5, "59A123", confidence=0.85))
    text1, _, _ = store.decide(1)
    assert text1 == "59A123"
    # Gọi finalize() — bắt buộc để chuyển finalized state
    finalized = store.finalize(1)
    assert finalized == "59A123"
    # Crop mới với chuỗi khác — phải bị từ chối
    new = _crop(10, "59ZZZ", confidence=0.99)
    assert not store.ingest_offer(1, new), "Finalized track phải từ chối crop mới"


# ── 10. Crop lỗi (error) KHÔNG tính phiếu ──────────────────────────────


def test_error_crop_does_not_count_as_vote():
    """Crop có error='ocr_engine_error:...' KHÔNG được tính trong decide.

    Crop lỗi KHÔNG qualify (is_readable=False), group không đủ min_agree=2.
    """
    store = PlateConsensusStore(consensus_min_agree=2)
    # 1 mẫu OK + 1 mẫu lỗi → readable = 1 → count=0
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.9))
    store.ingest_offer(1, _crop(5, "", confidence=0.0, error="ocr_engine_error:RuntimeError"))
    text, conf, count = store.decide(1)
    assert text is None
    assert count == 0


# ── 11. TTL prune entries cũ ────────────────────────────────────────────


def test_ttl_prune_drops_old_track(monkeypatch):
    """Track không update trong ttl_sec → bị prune khỏi store."""
    store = PlateConsensusStore(ttl_sec=0.1)
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    # Move time forward
    real_monotonic = time.monotonic
    target_time = real_monotonic() + 1.0
    monkeypatch.setattr("app.cv.plate_consensus.time.monotonic", lambda: target_time)
    # Decide sau TTL → track đã prune → count=0
    text, conf, count = store.decide(1)
    assert text is None
    assert count == 0


# ── 12. Multiple tracks isolated ────────────────────────────────────────


def test_multiple_tracks_isolated():
    """Track A và B có vote riêng; finalize A không ảnh hưởng B."""
    store = PlateConsensusStore(consensus_min_agree=2)
    # Track 1: chốt
    store.ingest_offer(1, _crop(1, "59A123", confidence=0.8))
    store.ingest_offer(1, _crop(5, "59A123", confidence=0.85))
    # Track 2: chỉ 1 mẫu → count=0 (không qualify)
    store.ingest_offer(2, _crop(1, "59B456", confidence=0.9))
    t1, _, c1 = store.decide(1)
    t2, _, c2 = store.decide(2)
    assert t1 == "59A123"
    assert c1 == 2
    assert t2 is None
    assert c2 == 0  # group chỉ có 1 mẫu < min_agree=2
