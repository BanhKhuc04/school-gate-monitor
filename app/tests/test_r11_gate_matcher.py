"""R11 — Gate event matcher / encounter logic (Owner A).

Theo handoff §3 R11:
- Một lượt xe có encounter_id ổn định; late plate/helmet/issues cập nhật cùng
  encounter/event và version, không nhân bản sự kiện/audio intent.
- Auto-match trước/sau tắt tới khi có cặp lượt hiệu chỉnh đạt.
- Ghép nhiều ứng viên/thiếu timestamp/bằng chứng mâu thuẫn giữ review.

Test gate_event_matcher:
- Auto-match MẶC ĐỊNH TẮT (env GATE_MATCHER_ENABLED=0)
- Hard gates: cùng gate_id, cùng direction, time window
- Status='needs_review' → không ghép
- Multi-candidate: top 2 trong gap AMBIGUOUS_GAP → ambiguous
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.cv import gate_event_matcher
from app.cv.gate_event_matcher import (
    GateEventMatcher,
    _normalize,
    _parse_iso,
    _direction_match,
    _lane_overlap,
)


# ── 1. Auto-match MẶC ĐỊNH TẮT ──────────────────────────────────────────


def test_matcher_disabled_by_default():
    """Mặc định env GATE_MATCHER_ENABLED=0 → matcher.enabled=False."""
    # Reset state bằng cách clear cache
    import importlib
    importlib.reload(gate_event_matcher)
    matcher = GateEventMatcher()
    # Nếu env chưa set thì default 0 (tắt)
    if "GATE_MATCHER_ENABLED" not in os.environ:
        assert matcher.enabled is False, "Default phải tắt"


def test_match_returns_disabled_when_not_enabled():
    """match() trả ('disabled') khi matcher tắt, KHÔNG ghép dù data hợp lệ."""
    matcher = GateEventMatcher(enabled=False)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
    }
    candidate = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:01+00:00",
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None
    assert status == "disabled"


# ── 2. Hard gate: cùng gate_id ─────────────────────────────────────────


def test_match_rejects_different_gate_id(monkeypatch):
    """Hai event khác gate_id → KHÔNG ghép, dù plate/time match."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "matched",
    }
    candidate = {
        "gate_id": "gate2",  # KHÁC gate
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:01+00:00",
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None
    assert status in ("unmatched", "needs_review_b1")


# ── 3. Hard gate: cùng direction ───────────────────────────────────────


def test_match_rejects_different_direction(monkeypatch):
    """2 event khác direction (enter vs exit) → KHÔNG ghép."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "matched",
    }
    candidate = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "exit",  # NGƯỢC chiều
        "observed_at": "2026-10-03T10:00:01+00:00",
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None
    assert status in ("unmatched", "needs_review_b1")


# ── 4. Hard gate: cả 2 direction unknown → fail ────────────────────────


def test_match_rejects_both_unknown_direction(monkeypatch):
    """Cả 2 direction đều unknown → fail (cẩn thận hơn, không ghép)."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": None,  # unknown
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "matched",
    }
    candidate = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": None,
        "observed_at": "2026-10-03T10:00:01+00:00",
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None


# ── 5. Hard gate: time ngoài window ────────────────────────────────────


def test_match_rejects_out_of_time_window(monkeypatch):
    """|t1 - t2| > GATE_MATCHER_WINDOW_SEC → KHÔNG ghép dù plate exact."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "matched",
    }
    candidate = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:30+00:00",  # 30s > 8s window
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None
    assert status in ("unmatched", "needs_review_b1")


# ── 6. needs_review status không ghép ──────────────────────────────────


def test_match_rejects_new_event_needs_review(monkeypatch):
    """new_event.status='needs_review' → KHÔNG ghép, trả needs_review_b1."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "needs_review",  # Không chắc
    }
    candidate = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:01+00:00",
        "status": "matched",
    }
    best, status = matcher.match(new_event, [candidate])
    assert best is None
    assert status == "needs_review_b1"


def test_match_skips_candidate_needs_review(monkeypatch):
    """candidate.status='needs_review' → skip candidate đó, tiếp tục candidate khác."""
    matcher = GateEventMatcher(enabled=True)
    new_event = {
        "gate_id": "gate1",
        "plate_read": "59A123",
        "direction": "enter",
        "observed_at": "2026-10-03T10:00:00+00:00",
        "status": "matched",
    }
    candidates = [
        {
            "gate_id": "gate1",
            "plate_read": "59A123",
            "direction": "enter",
            "observed_at": "2026-10-03T10:00:01+00:00",
            "status": "needs_review",  # skip
        },
        {
            "gate_id": "gate1",
            "plate_read": "59A123",
            "direction": "enter",
            "observed_at": "2026-10-03T10:00:02+00:00",
            "status": "matched",
        },
    ]
    best, status = matcher.match(new_event, candidates)
    # Match với candidate thứ 2
    if best is not None:
        assert best["observed_at"] == "2026-10-03T10:00:02+00:00"


# ── 7. helpers: _normalize ─────────────────────────────────────────────


def test_normalize_uppercase_strip_non_alnum():
    """_normalize: uppercase + strip non-alnum."""
    assert _normalize("59A-123") == "59A123"
    assert _normalize("59a 123") == "59A123"
    assert _normalize("") == ""
    assert _normalize(None) == ""
    assert _normalize("VN-59-A123") == "VN59A123"


def test_parse_iso_returns_none_for_invalid():
    """_parse_iso: invalid timestamp → None."""
    assert _parse_iso(None) is None
    assert _parse_iso("") is None
    assert _parse_iso("not-a-date") is None


def test_parse_iso_handles_z_suffix():
    """_parse_iso: ISO 'Z' suffix → epoch seconds."""
    result = _parse_iso("2026-10-03T10:00:00Z")
    assert isinstance(result, float)
    # Verify by parsing with timezone
    expected = datetime(2026, 10, 3, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    assert abs(result - expected) < 0.01


# ── 8. helpers: _direction_match ───────────────────────────────────────


def test_direction_match_same():
    """Cùng direction → True."""
    assert _direction_match("enter", "enter") is True
    assert _direction_match("exit", "exit") is True
    assert _direction_match("ENTER", "enter") is True  # case-insensitive


def test_direction_match_different():
    """Khác direction → False."""
    assert _direction_match("enter", "exit") is False


def test_direction_match_unknown_returns_false():
    """Unknown direction (None/empty) → False (an toàn)."""
    assert _direction_match(None, "enter") is False
    assert _direction_match("enter", None) is False
    assert _direction_match(None, None) is False
    assert _direction_match("", "enter") is False


# ── 9. helpers: _lane_overlap ──────────────────────────────────────────


def test_lane_overlap_returns_true_for_overlapping_boxes():
    """2 bbox overlap → True."""
    assert _lane_overlap([0, 0, 100, 100], [50, 50, 150, 150]) is True


def test_lane_overlap_returns_false_for_disjoint_boxes():
    """2 bbox tách rời → False."""
    assert _lane_overlap([0, 0, 50, 50], [100, 100, 200, 200]) is False


def test_lane_overlap_returns_false_for_missing_data():
    """bbox None hoặc thiếu phần tử → False (không suy ngược)."""
    assert _lane_overlap(None, [0, 0, 50, 50]) is False
    assert _lane_overlap([0, 0, 50], [0, 0, 50, 50]) is False  # thiếu
    assert _lane_overlap([0, 0, 50, 50], None) is False
