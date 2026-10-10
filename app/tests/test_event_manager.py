"""
Tests cho EventManager (Priority 1 — Event Engine).

Phạm vi: quyết định COMMIT/DEFER/SKIP dựa trên streak + window + grace period.
KHÔNG test pipeline (đã có test_vehicle_gate.py), KHÔNG test DB.
"""
import time

import pytest

from app.cv.event_manager import (
    DEFAULT_GRACE_PERIOD_SEC,
    DEFAULT_STREAK_MIN_FRAMES,
    DEFAULT_WINDOW_SEC,
    DecisionKind,
    EventManager,
    FrameEvidence,
)


def _ev(track_id: int, label, plate: str = "", ts: float = 0.0) -> FrameEvidence:
    """Helper tạo FrameEvidence với ts mặc định 0 (test tự truyền now)."""
    return FrameEvidence(
        track_id=track_id,
        violation_label=label,
        plate_read=plate,
        ts=ts,
    )


# ─── 1. Cấu hình hợp lệ ────────────────────────────────────────────────────


def test_init_rejects_invalid_streak_min_frames():
    with pytest.raises(ValueError):
        EventManager(streak_min_frames=0)
    with pytest.raises(ValueError):
        EventManager(streak_min_frames=-1)


def test_init_rejects_invalid_window_sec():
    with pytest.raises(ValueError):
        EventManager(window_sec=0)
    with pytest.raises(ValueError):
        EventManager(window_sec=-1.0)


def test_init_rejects_invalid_grace_period_sec():
    with pytest.raises(ValueError):
        EventManager(grace_period_sec=0)


# ─── 2. SKIP khi label None (frame an toàn) ────────────────────────────────


def test_safe_label_returns_skip_and_resets_streak():
    """Label None (an toàn) → SKIP; đồng thời reset streak đang đếm dở."""
    em = EventManager(streak_min_frames=3, window_sec=2.0, grace_period_sec=2.0)
    # 2 frame vi phạm trước (streak=2, chưa đủ 3)
    d1 = em.update(_ev(1, "NO_HELMET", ts=0.0))
    d2 = em.update(_ev(1, "NO_HELMET", ts=0.1))
    assert d1.kind == DecisionKind.DEFER
    assert d2.kind == DecisionKind.DEFER
    assert d2.streak == 2
    # 1 frame an toàn → reset streak
    d3 = em.update(_ev(1, None, ts=0.2))
    assert d3.kind == DecisionKind.SKIP
    # Sau đó phải đếm lại từ 1
    d4 = em.update(_ev(1, "NO_HELMET", ts=0.3))
    assert d4.kind == DecisionKind.DEFER
    assert d4.streak == 1


# ─── 3. DEFER khi streak chưa đủ ───────────────────────────────────────────


def test_defer_when_streak_below_minimum():
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    # 4 frame liên tiếp → chưa đạt 5
    for i in range(4):
        d = em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
        assert d.kind == DecisionKind.DEFER
        assert d.streak == i + 1


# ─── 4. COMMIT khi streak đạt ngưỡng ───────────────────────────────────────


def test_commit_when_streak_reaches_minimum():
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    for i in range(4):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    d = em.update(_ev(1, "NO_HELMET", ts=0.5))  # streak = 5
    assert d.kind == DecisionKind.COMMIT
    assert d.label == "NO_HELMET"
    assert d.streak == 5


# ─── 5. Đổi label → reset streak ───────────────────────────────────────────


def test_label_change_resets_streak():
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    # 4 frame NO_HELMET
    for i in range(4):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    # Đổi sang PLATE_NOT_REGISTERED → streak reset về 1
    d = em.update(_ev(1, "PLATE_NOT_REGISTERED", ts=0.5))
    assert d.kind == DecisionKind.DEFER
    assert d.streak == 1


# ─── 6. Sau COMMIT: tiếp tục cùng label → DEFER (chặn spam log) ────────────


def test_already_committed_returns_defer_within_grace_period():
    """1 người vi phạm 30 frame liên tiếp không được log 6 lần — sau COMMIT
    đầu tiên, các frame tiếp theo cùng label trong grace_period phải DEFER."""
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    # Frame 1-5: đạt streak=5 → COMMIT ở frame 5
    for i in range(5):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    # Frame 6-10 cùng label, trong grace_period → DEFER
    for i in range(5, 15):
        d = em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
        assert d.kind == DecisionKind.DEFER, f"frame {i} phải DEFER, được {d.kind}"


def test_after_grace_period_same_label_can_commit_again():
    """Sau khi track_id biến mất quá grace_period (TTL prune), track_id
    xuất hiện lại với cùng label → coi là track mới, có thể COMMIT lại.

    Test: commit → grace_period trôi qua (track_id bị prune vì không update) →
    xuất hiện lại → streak đếm lại từ 1 → COMMIT khi đạt min.
    """
    em = EventManager(
        streak_min_frames=3, window_sec=2.0, grace_period_sec=1.0,
    )
    # Track xuất hiện, commit
    for i in range(3):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    assert em.active_track_count() == 1

    # Không update trong > grace_period (1s) → bị prune khi update tiếp
    # dùng now > grace_period kể từ frame cuối
    last_ts = 0.2
    later_ts = last_ts + 1.5  # > grace_period
    d = em.update(_ev(1, "NO_HELMET", ts=later_ts))
    # Track đã bị prune + tạo lại → streak = 1, chưa commit
    assert d.kind == DecisionKind.DEFER
    assert d.streak == 1


# ─── 7. Đổi label sau COMMIT → có thể COMMIT lại ngay (label khác) ────────


def test_label_change_after_commit_allows_new_commit():
    em = EventManager(streak_min_frames=3, window_sec=2.0, grace_period_sec=2.0)
    # Commit NO_HELMET
    for i in range(3):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    # Đổi sang PLATE_NOT_REGISTERED → reset streak, đếm lại
    for i in range(3, 6):
        d = em.update(_ev(1, "PLATE_NOT_REGISTERED", ts=i * 0.1))
    assert d.kind == DecisionKind.COMMIT
    assert d.label == "PLATE_NOT_REGISTERED"


# ─── 8. Track_id khác nhau quản lý độc lập ────────────────────────────────


def test_different_track_ids_decide_independently():
    em = EventManager(streak_min_frames=3, window_sec=2.0, grace_period_sec=2.0)
    # Track 1: 2 frame vi phạm (DEFER)
    em.update(_ev(1, "NO_HELMET", ts=0.0))
    em.update(_ev(1, "NO_HELMET", ts=0.1))
    # Track 2: 3 frame vi phạm (COMMIT) — độc lập với track 1
    d2a = em.update(_ev(2, "NO_HELMET", ts=0.0))
    d2b = em.update(_ev(2, "NO_HELMET", ts=0.1))
    d2c = em.update(_ev(2, "NO_HELMET", ts=0.2))
    assert d2a.kind == DecisionKind.DEFER
    assert d2b.kind == DecisionKind.DEFER
    assert d2c.kind == DecisionKind.COMMIT
    # Track 1 vẫn ở streak=2
    assert em.active_track_count() == 2


# ─── 9. TTL prune ──────────────────────────────────────────────────────────


def test_track_pruned_after_grace_period_without_updates():
    em = EventManager(streak_min_frames=3, window_sec=2.0, grace_period_sec=1.0)
    em.update(_ev(1, "NO_HELMET", ts=0.0))
    em.update(_ev(1, "NO_HELMET", ts=0.1))
    assert em.active_track_count() == 1
    # Update track khác với now > grace_period từ lần cuối của track 1
    em.update(_ev(2, "NO_HELMET", ts=2.0))  # now=2.0, track 1 last_seen=0.1 → expired
    assert em.active_track_count() == 1  # track 1 bị prune, track 2 ở lại


def test_reset_clears_all_state():
    em = EventManager()
    em.update(_ev(1, "NO_HELMET"))
    em.update(_ev(2, "NO_HELMET"))
    assert em.active_track_count() == 2
    em.reset()
    assert em.active_track_count() == 0


# ─── 10. Plate vote trả về plate xuất hiện nhiều nhất trong window ─────────


def test_plate_vote_returns_most_common_in_window():
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    # 3 frame NO_HELMET với plate "29A111", 1 frame plate "29A222"
    em.update(_ev(1, "NO_HELMET", plate="29A111", ts=0.0))
    em.update(_ev(1, "NO_HELMET", plate="29A111", ts=0.1))
    em.update(_ev(1, "NO_HELMET", plate="29A222", ts=0.2))
    d = em.update(_ev(1, "NO_HELMET", plate="29A111", ts=0.3))
    # Plate đa số là "29A111"
    assert d.plate_read == "29A111"


def test_plate_vote_empty_when_no_plate_in_evidence():
    em = EventManager(streak_min_frames=5, window_sec=2.0, grace_period_sec=2.0)
    for i in range(4):
        em.update(_ev(1, "NO_HELMET", plate="", ts=i * 0.1))
    d = em.update(_ev(1, "NO_HELMET", plate="", ts=0.5))
    assert d.plate_read == ""


# ─── 11. Mẫu quá cũ (> window_sec) không tính vào streak ──────────────────


def test_old_evidence_outside_window_dropped_from_streak():
    """Frame quá cũ (> window_sec) bị prune khỏi evidence deque. Khi track_id
    xuất hiện lại SAU grace_period (track bị prune + tạo lại), streak đếm
    lại từ 1 — chứng minh cả window prune và TTL prune hoạt động."""
    em = EventManager(streak_min_frames=3, window_sec=1.0, grace_period_sec=1.0)
    # 4 frame vi phạm từ ts=0 → 0.3
    for i in range(4):
        em.update(_ev(1, "NO_HELMET", ts=i * 0.1))
    # Update ở ts=2.0 (> grace_period từ frame cuối 0.3): track bị prune,
    # xuất hiện lại coi như track mới → streak=1, DEFER.
    d = em.update(_ev(1, "NO_HELMET", ts=2.0))
    assert d.kind == DecisionKind.DEFER
    assert d.streak == 1


# ─── 12. now mặc định = evidence.ts (hành vi ngầm định) ───────────────────


def test_now_defaults_to_evidence_ts():
    """Khi không truyền now → dùng evidence.ts. Cho phép test không cần
    tính now riêng."""
    em = EventManager(streak_min_frames=3, window_sec=2.0, grace_period_sec=2.0)
    d = em.update(_ev(1, "NO_HELMET", ts=100.0))
    assert d.kind == DecisionKind.DEFER
    assert d.streak == 1
    # active_track_count phải tính đúng dù ts rất lớn
    assert em.active_track_count() == 1


# ─── 13. Ngưỡng mặc định khớp docs (Priority 1 spec) ───────────────────────


def test_default_thresholds_match_docs_spec():
    """docs yêu cầu: ≥5 frame liên tiếp trong cửa sổ 2s, grace 2s."""
    assert DEFAULT_STREAK_MIN_FRAMES == 5
    assert DEFAULT_WINDOW_SEC == 2.0
    assert DEFAULT_GRACE_PERIOD_SEC == 2.0


def test_default_event_manager_uses_doc_thresholds():
    """EventManager() mặc định dùng đúng ngưỡng docs (≥5 frame trong 2s)."""
    em = EventManager()
    assert em.streak_min_frames == 5
    assert em.window_sec == 2.0
    assert em.grace_period_sec == 2.0
    # Verify hành vi: 4 frame DEFER, 5 frame COMMIT
    for i in range(4):
        assert em.update(_ev(99, "X", ts=i * 0.1)).kind == DecisionKind.DEFER
    assert em.update(_ev(99, "X", ts=0.5)).kind == DecisionKind.COMMIT
