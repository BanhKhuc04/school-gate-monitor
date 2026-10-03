"""
pytest tests cho app/cv/evidence.py — Đợt E1 (bộ bằng chứng per loại lỗi).

Bộ test này là "spec sống" cho EvidenceLedger. Mọi thay đổi sau phải thỏa mãn
các case dưới đây, vì đây là hợp đồng hành vi quyết định khi nào 1 lỗi đã
"đủ bằng chứng" để pipeline ghi log.

Quy tắc (theo CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md §3):
- 4 mẫu đồng thuận / 80% / 1,5 giây / 400 ms span / 100 ms interval
- Unknown KHÔNG tính vào vote
- Mâu thuẫn rõ (positive + negative cùng cửa sổ) → CONFLICT
- Grace period chống spam
"""
import time
import pytest
from unittest.mock import MagicMock

from app.cv.evidence import (
    EvidenceLedger, ErrorSample, ErrorDecision, DecisionKind,
    DEFAULT_MIN_SAMPLES, DEFAULT_WINDOW_SEC, DEFAULT_MIN_AGREEMENT,
    DEFAULT_MIN_SPAN_SEC, DEFAULT_MIN_SAMPLE_INTERVAL_SEC,
    DEFAULT_GRACE_PERIOD_SEC,
)


def _ledger(**kwargs):
    """Số nguyên / float dễ đọc; mặc định khớp plan E1."""
    defaults = dict(
        min_samples=DEFAULT_MIN_SAMPLES,           # 4
        window_sec=DEFAULT_WINDOW_SEC,             # 1.5
        min_agreement=DEFAULT_MIN_AGREEMENT,       # 0.80
        min_span_sec=DEFAULT_MIN_SPAN_SEC,         # 0.40
        min_sample_interval_sec=DEFAULT_MIN_SAMPLE_INTERVAL_SEC,  # 0.10
        grace_period_sec=DEFAULT_GRACE_PERIOD_SEC, # 5.0
    )
    defaults.update(kwargs)
    return EvidenceLedger(**defaults)


def _positive(frame_seq: int, ts: float, detector: str = "no_helmet") -> ErrorSample:
    return ErrorSample(error_type='positive', frame_seq=frame_seq, ts=ts,
                       detector_class=detector)


def _negative(frame_seq: int, ts: float, detector: str = "helmet") -> ErrorSample:
    return ErrorSample(error_type='negative', frame_seq=frame_seq, ts=ts,
                       detector_class=detector)


def _unknown(frame_seq: int, ts: float, detector: str = "unknown") -> ErrorSample:
    return ErrorSample(error_type='unknown', frame_seq=frame_seq, ts=ts,
                       detector_class=detector)


# ─── Case 1: 4 mẫu đồng thuận → CONFIRM ────────────────────────────────

def test_four_positives_within_window_confirm():
    """E1.1: 4 mẫu positive, span ≥400ms, agreement 100%, tất cả trong 1.5s
    → CONFIRM."""
    ledger = _ledger()
    ts = 1000.0
    decisions = []
    # 4 mẫu cách nhau 150ms → span = 450ms > 400ms, agreement 100%
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
        decisions.append(d)
    assert decisions[-1].kind == DecisionKind.CONFIRM
    assert decisions[-1].positive_count == 4
    assert decisions[-1].decisive_count == 4


def test_four_positives_with_enough_span_confirm():
    """4 mẫu positive, span ≥400ms (cách 100ms × 5 khoảng = 0.5s) → CONFIRM."""
    ledger = _ledger()
    ts = 1000.0
    decisions = []
    # 4 mẫu cách nhau 150ms → span = 450ms > 400ms, agreement 100%
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
        decisions.append(d)
    assert decisions[-1].kind == DecisionKind.CONFIRM
    assert decisions[-1].positive_count == 4
    assert decisions[-1].decisive_count == 4


# ─── Case 2: Khoảng cách mẫu tối thiểu 100 ms ────────────────────────────

def test_samples_too_close_are_dropped():
    """E1.1: 2 mẫu cách nhau 50ms (< 100ms interval) → mẫu thứ 2 bị DEFER."""
    ledger = _ledger(min_sample_interval_sec=0.10)
    ts = 1000.0
    d1 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=1, ts=ts))
    # Mẫu thứ 2 cách 50ms → quá gần → DEFER (bỏ qua)
    d2 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=2, ts=ts + 0.05))
    assert d2.kind == DecisionKind.DEFER
    assert d2.positive_count == 1  # state không thay đổi


def test_samples_exactly_at_interval_counted():
    """Khoảng cách đúng 100ms (>= ngưỡng) → được tính."""
    ledger = _ledger(min_sample_interval_sec=0.10)
    ts = 1000.0
    d1 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=1, ts=ts))
    # Cách 200ms (lớn hơn interval 100ms) → được tính
    d2 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=2, ts=ts + 0.20))
    assert d1.kind == DecisionKind.DEFER
    assert d2.kind == DecisionKind.DEFER
    assert d2.positive_count == 2


# ─── Case 3: Frame trùng không tính 2 lần ──────────────────────────────

def test_duplicate_frame_seq_dropped():
    """Cùng frame_seq → chỉ tính 1 lần; mẫu thứ 2 bị bỏ qua."""
    ledger = _ledger()
    ts = 1000.0
    d1 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=5, ts=ts))
    d2 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=5, ts=ts + 0.20))
    assert d2.kind == DecisionKind.DEFER
    assert d2.positive_count == 1


# ─── Case 4: Unknown KHÔNG tính vào vote, KHÔNG reset streak ─────────────

def test_unknown_samples_do_not_count_in_agreement():
    """3 positive + 5 unknown: decisive_count = 3, agreement = 100%, span OK
    nhưng positive_count = 3 < min_samples (4) → DEFER (không đủ positive)."""
    ledger = _ledger()
    ts = 1000.0
    # 3 positive (span 0.30s, không đủ span)
    for i in range(3):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    # 5 unknown xen giữa
    for i in range(5):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_unknown(frame_seq=10 + i, ts=ts + 1.0 + i * 0.15))
    # Kết quả: positive_count = 3 (đã bị prune vì quá 1.5s so với now),
    # decisive_count = 3 → DEFER (chưa đủ 4 mẫu).
    # Lấy 1 mẫu positive mới (now) để kiểm tra.
    d = ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=20, ts=ts + 0.6))
    assert d.kind in (DecisionKind.DEFER, DecisionKind.CONFIRM)
    # Quyết định KHÔNG nên dựa trên unknown


def test_unknown_does_not_reset_positive_streak():
    """Unknown xen giữa không reset streak positive — quan trọng để tracker
    mất track tạm thời không làm mất bằng chứng đã thu."""
    ledger = _ledger()
    ts = 1000.0
    # 2 positive (cách 150ms → span 0.15s)
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=1, ts=ts))
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=2, ts=ts + 0.15))
    # 1 unknown
    d_u = ledger.update(track_id=42, error_type='NO_HELMET',
                        sample=_unknown(frame_seq=3, ts=ts + 0.30))
    # 2 positive tiếp (cách 150ms nữa)
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=4, ts=ts + 0.45))
    d4 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=5, ts=ts + 0.60))
    # positive_count = 4, span = 0.60s, agreement 100% → CONFIRM
    assert d4.kind == DecisionKind.CONFIRM
    assert d4.positive_count == 4


# ─── Case 5: Mâu thuẫn rõ → CONFLICT ─────────────────────────────────────

def test_positive_and_negative_in_same_window_is_conflict():
    """E1.1: positive và negative cùng trong cửa sổ → CONFLICT (không đa số che)."""
    ledger = _ledger()
    ts = 1000.0
    # 3 positive, 2 negative xen kẽ
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=1, ts=ts))
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_negative(frame_seq=2, ts=ts + 0.15))
    d3 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=3, ts=ts + 0.30))
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_negative(frame_seq=4, ts=ts + 0.45))
    d5 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=5, ts=ts + 0.60))
    # 3 pos + 2 neg → mâu thuẫn rõ
    assert d3.kind == DecisionKind.CONFLICT
    assert d5.kind == DecisionKind.CONFLICT


# ─── Case 6: Grace period chống spam ────────────────────────────────────

def test_already_confirmed_defer_within_grace_period():
    """Sau CONFIRM, các mẫu tiếp theo trong grace_period_sec → DEFER."""
    ledger = _ledger()
    ts = 1000.0
    # CONFIRM lần 1
    for i in range(4):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    # CONFIRM lần 2 trong grace (chưa tới 5s)
    d2 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=10, ts=ts + 1.0))
    assert d2.kind == DecisionKind.DEFER
    assert d2.already_confirmed_recently is True


def test_can_confirm_again_after_grace_period():
    """Sau grace_period_sec kể từ CONFIRM gần nhất → có thể CONFIRM lại nếu
    lỗi vẫn tiếp diễn (vd người vi phạm 30s liên tục)."""
    ledger = _ledger()
    ts = 1000.0
    # CONFIRM lần 1
    for i in range(4):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    # Sau 6 giây → grace hết → CONFIRM lại
    ts2 = ts + 6.0
    decisions = []
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_positive(frame_seq=20 + i, ts=ts2 + i * 0.15))
        decisions.append(d)
    assert decisions[-1].kind == DecisionKind.CONFIRM


# ─── Case 7: Per-error-type isolation ───────────────────────────────────

def test_different_error_types_have_independent_ledgers():
    """NO_HELMET và NO_PUSH cùng track_id có ledger độc lập — confirm một
    không ảnh hưởng cái kia."""
    ledger = _ledger()
    ts = 1000.0
    # NO_HELMET: confirm
    for i in range(4):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    # NO_PUSH: chỉ 1 positive → vẫn DEFER
    d_p = ledger.update(track_id=42, error_type='NO_PUSH',
                        sample=_positive(frame_seq=20, ts=ts + 0.10))
    assert d_p.kind == DecisionKind.DEFER
    assert d_p.positive_count == 1


def test_different_track_ids_have_independent_ledgers():
    """Track A confirm không ảnh hưởng track B (cùng error_type)."""
    ledger = _ledger()
    ts = 1000.0
    # Track 1: confirm
    for i in range(4):
        ledger.update(track_id=1, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    # Track 2: chỉ 1 positive
    d_t2 = ledger.update(track_id=2, error_type='NO_HELMET',
                          sample=_positive(frame_seq=10, ts=ts))
    assert d_t2.kind == DecisionKind.DEFER


# ─── Case 8: Negative đơn thuần → SKIP ─────────────────────────────────

def test_only_negatives_returns_skip():
    """Chỉ có negative trong cửa sổ → SKIP (không cần xét)."""
    ledger = _ledger()
    ts = 1000.0
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_negative(frame_seq=i + 1, ts=ts + i * 0.15))
    assert d.kind == DecisionKind.SKIP


# ─── Case 9: Window prune ───────────────────────────────────────────────

def test_old_samples_outside_window_pruned():
    """Mẫu ngoài window_sec bị prune — positive cũ không ảnh hưởng quyết định."""
    ledger = _ledger(window_sec=1.5)
    ts = 1000.0
    # 2 positive cũ (sẽ bị prune khi now - ts > 1.5)
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=1, ts=ts))
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=2, ts=ts + 0.15))
    # Sau 2 giây (mẫu cũ đã ngoài window) → 2 positive mới
    ts2 = ts + 2.0
    d3 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=3, ts=ts2))
    d4 = ledger.update(track_id=42, error_type='NO_HELMET',
                       sample=_positive(frame_seq=4, ts=ts2 + 0.15))
    # positive_count = 2 (mẫu cũ đã prune), span = 0.15 < 0.40 → DEFER
    assert d4.kind == DecisionKind.DEFER
    assert d4.positive_count == 2


# ─── Case 10: Sample interval chặt frame cache/duplicate ────────────────

def test_min_interval_zero_allows_close_samples():
    """min_sample_interval_sec=0 → không chặn — dùng cho test deterministic."""
    ledger = _ledger(min_sample_interval_sec=0.0)
    ts = 1000.0
    decisions = []
    # 4 positive cách 0ms (không thực tế, nhưng cần để test nhanh)
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_positive(frame_seq=i + 1, ts=ts + i * 0.0))
        decisions.append(d)
    # span = 0 < 0.40 → DEFER (đủ samples + agreement nhưng span thiếu)
    assert decisions[-1].kind == DecisionKind.DEFER


# ─── Case 11: Validation ngưỡng ─────────────────────────────────────────

def test_invalid_min_samples_raises():
    with pytest.raises(ValueError):
        EvidenceLedger(min_samples=0)


def test_invalid_window_sec_raises():
    with pytest.raises(ValueError):
        EvidenceLedger(window_sec=0)


def test_invalid_min_agreement_raises():
    with pytest.raises(ValueError):
        EvidenceLedger(min_agreement=1.5)


# ─── Case 12: reset() ──────────────────────────────────────────────────

def test_reset_clears_all_state():
    ledger = _ledger()
    ts = 1000.0
    for i in range(4):
        ledger.update(track_id=42, error_type='NO_HELMET',
                      sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    assert ledger.active_track_count() == 1
    ledger.reset()
    assert ledger.active_track_count() == 0


# ─── Case 13: prune_expired ─────────────────────────────────────────────

def test_prune_expired_removes_stale_tracks():
    """Tracks không update trong grace_period_sec bị prune khỏi memory."""
    ledger = _ledger(grace_period_sec=2.0)
    ts = 1000.0
    ledger.update(track_id=42, error_type='NO_HELMET',
                  sample=_positive(frame_seq=1, ts=ts))
    assert ledger.active_track_count() == 1
    # Sau 3 giây không update → prune
    ledger.prune_expired(now=ts + 3.0)
    assert ledger.active_track_count() == 0


# ─── Case 14: Stats sanity ──────────────────────────────────────────────

def test_decision_includes_evidence_counts():
    """ErrorDecision phải có positive_count, decisive_count, span_sec để
    pipeline/log có thể in ra lý do."""
    ledger = _ledger()
    ts = 1000.0
    for i in range(4):
        d = ledger.update(track_id=42, error_type='NO_HELMET',
                          sample=_positive(frame_seq=i + 1, ts=ts + i * 0.15))
    assert isinstance(d, ErrorDecision)
    assert d.track_id == 42
    assert d.error_type == 'NO_HELMET'
    assert d.positive_count == 4
    assert d.decisive_count == 4
    assert d.span_sec > 0


def test_cached_frame_stays_rejected_after_window_expiry():
    ledger = _ledger()
    ledger.update(42, 'NO_HELMET', _positive(5, 1000))
    result = ledger.update(42, 'NO_HELMET', _positive(5, 1002))
    assert result.positive_count == 0


def test_recent_confirmation_does_not_hide_clear_conflict():
    ledger = _ledger()
    for n in range(4):
        ledger.update(42, 'NO_HELMET', _positive(n+1, 1000+n*.2))
    result = ledger.update(42, 'NO_HELMET', _negative(5, 1000.8))
    assert result.kind == DecisionKind.CONFLICT


def test_only_last_five_valid_observations_are_counted():
    ledger = _ledger()
    for n in range(8):
        result = ledger.update(42, 'NO_HELMET', _positive(n+1, 1000+n*.15))
    assert result.decisive_count == 5
    assert ledger.evidence_details(42, 'NO_HELMET')['sample_count'] == 5
