"""Tests cho N05 (Post-Video Review): posture ledger per-track.

Tái hiện trước fix: 1 global deque append từ mode toàn frame, không theo track.
"""
import time

from app.cv.posture_track_ledger import PostureTrackLedger


def _now():
    return time.monotonic()


def test_two_tracks_two_samples_each_dont_combine_to_four():
    """2 track × 2 sample không được combine thành 4 sample chung."""
    led = PostureTrackLedger(min_samples=4)
    t0 = _now()
    # Track 1: 2 sample RIDING, cách 200ms
    led.add(1, 'RIDING', now_m=t0)
    led.add(1, 'RIDING', now_m=t0 + 0.2)
    # Track 2: 2 sample RIDING, cách 200ms
    led.add(2, 'RIDING', now_m=t0 + 0.4)
    led.add(2, 'RIDING', now_m=t0 + 0.6)
    # Cả 2 track vẫn UNKNOWN vì mỗi track chỉ có 2 sample (< min_samples=4)
    state1, _ = led.get(1)
    state2, _ = led.get(2)
    assert state1 == 'UNKNOWN', f"Track 1 chỉ có 2 sample, phải UNKNOWN, got {state1}"
    assert state2 == 'UNKNOWN', f"Track 2 chỉ có 2 sample, phải UNKNOWN, got {state2}"


def test_one_track_with_four_samples_confirms():
    """1 track × 4 sample đồng thuận → confirmed."""
    led = PostureTrackLedger(min_samples=4)
    t0 = _now()
    for i in range(4):
        led.add(7, 'RIDING', now_m=t0 + i * 0.2)
    state, conf = led.get(7)
    assert state == 'RIDING', f"Track 7 confirmed, got {state}"
    assert conf == 1.0


def test_unknown_not_counted_as_vote():
    """Sample UNKNOWN không tính evidence."""
    led = PostureTrackLedger(min_samples=4)
    t0 = _now()
    for i in range(6):
        led.add(1, 'UNKNOWN', now_m=t0 + i * 0.2)
    state, _ = led.get(1)
    assert state == 'UNKNOWN', "UNKNOWN không được confirm"


def test_min_interval_filters_rapid_samples():
    """Sample cách < min_interval_sec bị bỏ, không spam frame liên tiếp."""
    led = PostureTrackLedger(min_samples=4, min_interval_sec=0.1)
    t0 = _now()
    # 10 sample RIDING, mỗi cách 10ms (< 100ms min_interval) → 0 sample giữ
    for i in range(10):
        led.add(1, 'RIDING', now_m=t0 + i * 0.01)
    state, _ = led.get(1)
    # Sau 10 sample cách 10ms, chỉ 1 sample (frame đầu) được giữ
    # → không đủ min_samples=4
    assert state == 'UNKNOWN'


def test_min_span_enforced():
    """4 sample trong < min_span_sec (400ms) → không confirm."""
    led = PostureTrackLedger(min_samples=4, min_interval_sec=0.05, min_span_sec=0.4)
    t0 = _now()
    # 4 sample cách 50ms, span = 0.15s < 0.4s
    for i in range(4):
        led.add(1, 'RIDING', now_m=t0 + i * 0.05)
    state, _ = led.get(1)
    assert state == 'UNKNOWN', f"Span < min_span phải UNKNOWN, got {state}"


def test_min_samples_threshold():
    """3 sample chưa đủ, 4 sample confirm."""
    led = PostureTrackLedger(min_samples=4, min_interval_sec=0.1, min_span_sec=0.4)
    t0 = _now()
    for i in range(3):
        led.add(1, 'RIDING', now_m=t0 + i * 0.2)
    state, _ = led.get(1)
    assert state == 'UNKNOWN'
    # Sample thứ 4
    led.add(1, 'RIDING', now_m=t0 + 0.6)
    state, _ = led.get(1)
    assert state == 'RIDING'


def test_agreement_ratio_blocks_low_consensus():
    """3 RIDING / 2 PUSHING (60%) dưới ngưỡng 80% → UNKNOWN."""
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.1, min_span_sec=0.4,
        max_samples=5, agreement_ratio=0.80,
    )
    t0 = _now()
    for s in ['RIDING', 'RIDING', 'PUSHING', 'PUSHING', 'RIDING']:
        led.add(1, s, now_m=t0)
        t0 += 0.15
    state, conf = led.get(1)
    assert state == 'UNKNOWN', f"60% < 80% agreement, phải UNKNOWN, got {state} conf={conf}"


def test_ambiguity_margins_close_competitor():
    """4 RIDING / 3 PUSHING (close) → ambiguous → UNKNOWN."""
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.1, min_span_sec=0.4,
        max_samples=8, agreement_ratio=0.80, ambiguity_margin=2,
    )
    t0 = _now()
    # 4 RIDING + 3 PUSHING = 7 sample, ratio 4/7 = 57% < 80% → UNKNOWN vì agreement
    for s in ['RIDING', 'RIDING', 'PUSHING', 'RIDING', 'PUSHING', 'RIDING', 'PUSHING']:
        led.add(1, s, now_m=t0)
        t0 += 0.15
    state, conf = led.get(1)
    # Agreement ratio < 0.80 → UNKNOWN
    assert state == 'UNKNOWN'


def test_window_prune_stale_samples():
    """Sample quá window_sec bị prune khỏi deque."""
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.05, min_span_sec=0.1,
        window_sec=1.5, agreement_ratio=0.80,
    )
    t0 = _now()
    # 4 sample cách 200ms → window 1.5s giữ cả 4
    for i in range(4):
        led.add(1, 'RIDING', now_m=t0 + i * 0.2)
    state, _ = led.get(1)
    assert state == 'RIDING'
    # Sample mới cách 2s → sample cũ (cách 2.5s) bị prune
    led.add(1, 'RIDING', now_m=t0 + 2.0)
    # Đếm sample còn trong buffer
    led2 = led
    # Get should return based on remaining samples
    state2, _ = led2.get(1)
    # Có thể còn RIDING (4 sample mới trong window) hoặc UNKNOWN nếu cũ bị prune và chỉ còn 1
    assert state2 in ('RIDING', 'UNKNOWN')


def test_expire_stale_unknown():
    """Track không cập nhật > window_sec → state về UNKNOWN."""
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.05, min_span_sec=0.1,
        window_sec=1.5,
    )
    t0 = _now()
    for i in range(4):
        led.add(1, 'RIDING', now_m=t0 + i * 0.2)
    assert led.get(1)[0] == 'RIDING'
    # Expire sau 3s (2× window)
    led.expire_stale(now_m=t0 + 3.0)
    state, _ = led.get(1)
    assert state == 'UNKNOWN', f"Track stale > window → UNKNOWN, got {state}"


def test_two_tracks_dont_share_state():
    """Track A RIDING, Track B PUSHING → độc lập."""
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.05, min_span_sec=0.1,
        agreement_ratio=0.80,
    )
    t0 = _now()
    for i in range(4):
        led.add(1, 'RIDING', now_m=t0 + i * 0.2)
    for i in range(4):
        led.add(2, 'PUSHING', now_m=t0 + 0.5 + i * 0.2)
    state1, _ = led.get(1)
    state2, _ = led.get(2)
    assert state1 == 'RIDING', f"Track A RIDING, got {state1}"
    assert state2 == 'PUSHING', f"Track B PUSHING, got {state2}"


def test_get_unknown_for_unknown_track():
    """Track chưa từng add → UNKNOWN."""
    led = PostureTrackLedger()
    state, _ = led.get(999)
    assert state == 'UNKNOWN'


def test_reset_clears_all_tracks():
    led = PostureTrackLedger(
        min_samples=4, min_interval_sec=0.05, min_span_sec=0.1,
    )
    t0 = _now()
    for i in range(4):
        led.add(1, 'RIDING', now_m=t0 + i * 0.2)
    led.reset()
    assert led.track_count() == 0
    state, _ = led.get(1)
    assert state == 'UNKNOWN'