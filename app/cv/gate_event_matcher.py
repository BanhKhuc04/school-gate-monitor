"""
Gate Event Matcher — Phase 5 (Task 1) ghép 2 camera (front + rear) cùng cổng
vật lý vào 1 encounter chia sẻ.

KHÔNG dùng chỉ 1 yếu tố (thời gian, track ID, fuzzy plate). Mọi quyết
định ghép phải dựa trên ≥3 yếu tố đồng thuận:

1. **Time-corrected window**: |t1 - t2| <= FLOOR_WINDOW_SEC (mặc định 8s)
   SAU khi hiệu chỉnh skew giữa 2 camera (skew_sec ≈ observed_at lệch).
2. **Direction consistency**: 2 event có cùng direction (enter/exit) — xe
   cùng chiều đi qua cổng. Ngược chiều → loại (xe ngược là 2 xe khác).
3. **Lane/region overlap**: nếu có ROI/lane polygon metadata, bbox của 2
   sự kiện phải overlap. Không có → skip yếu tố này (không suy ngược).
4. **Plate exact**: SequenceMatcher.ratio() == 1.0 (plate giống hệt
   SAU normalize). Yếu tố này có trọng số cao nhất — nếu exact match
   + time OK → MATCH.
5. **Plate fuzzy**: ratio >= MATCH_MIN_SIMILARITY (mặc định 0.9) → MATCH
   nhưng status = 'needs_review'.
6. **Multi-candidate rejection**: nếu ≥2 candidate đạt cùng điểm cao nhất
   → KHÔNG ghép, status = 'ambiguous' (tránh nhầm xe).

Trạng thái:
  - 'matched'   : ghép chắc chắn (≥3 yếu tố đồng thuận, plate exact).
  - 'needs_review' : ghép có điều kiện (plate fuzzy, thời gian OK) — để
                    người xem confirm.
  - 'unmatched' : không có ứng viên đạt ngưỡng.
  - 'ambiguous' : nhiều ứng viên đạt cùng điểm → không tự ghép.

QUY TẮC AN TOÀN (Task 1):
  - Auto-match MẶC ĐỊNH TẮT (env GATE_MATCHER_ENABLED=0) cho đến khi
    có calibration đủ cặp lượt có nhãn. Khi tắt, matcher trả
    'disabled' cho MỌI lời gọi → caller biết không được ghép.
  - Một bên status='needs_review' (Bước 1 không chắc) → KHÔNG ghép, trả
    'needs_review' (giữ nguyên từ event_correlator).
"""
from __future__ import annotations

import difflib
import os
import re
from typing import Optional


# --------------------------------------------------------------------------- #
# Config (env-driven; default OFF)
# --------------------------------------------------------------------------- #

GATE_MATCHER_ENABLED = os.environ.get("GATE_MATCHER_ENABLED", "0") == "1"
GATE_MATCHER_WINDOW_SEC = max(1.0, float(
    os.environ.get("GATE_MATCHER_WINDOW_SEC", "8.0")))
GATE_MATCHER_MIN_SIMILARITY = max(0.0, min(1.0, float(
    os.environ.get("GATE_MATCHER_MIN_SIMILARITY", "0.9"))))
# Trọng số cho scoring — chỉ dùng nội bộ, không expose config
_W_TIME = 1.0
_W_DIRECTION = 2.0
_W_PLATE_EXACT = 5.0
_W_PLATE_FUZZY = 2.0
_W_LANE_OVERLAP = 1.5


def _normalize(s: Optional[str]) -> str:
    """Uppercase + strip non-alnum — đồng bộ với db.normalize_plate."""
    if not s:
        return ""
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def _parse_iso(ts: Optional[str]) -> Optional[float]:
    """Parse ISO timestamp → epoch seconds. Trả None nếu lỗi."""
    if not ts:
        return None
    try:
        from datetime import datetime
        # Python 3.11+: fromisoformat handles 'Z' suffix
        return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
    except (ValueError, AttributeError):
        return None


def _direction_match(d1: Optional[str], d2: Optional[str]) -> bool:
    """Cùng direction (enter/exit) hay cả 2 đều unknown? Unknown coi
    như KHÔNG match để an toàn (mâu thuẫn dữ liệu → không ghép)."""
    d1n = (d1 or "").strip().lower()
    d2n = (d2 or "").strip().lower()
    if not d1n or not d2n:
        return False
    return d1n == d2n


def _lane_overlap(b1: Optional[list], b2: Optional[list]) -> bool:
    """Bbox IoU > 0 nếu 2 region overlap. Trả False nếu thiếu data."""
    if not b1 or not b2 or len(b1) != 4 or len(b2) != 4:
        return False
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    return x2 > x1 and y2 > y1


def _score_pair(a: dict, b: dict) -> tuple[float, str]:
    """Trả (score, status_hint). Status hint là 'exact' / 'fuzzy' / 'none'
    để caller quyết định matched/needs_review."""
    score = 0.0

    # 1. Time-corrected window
    ta = _parse_iso(a.get('observed_at'))
    tb = _parse_iso(b.get('observed_at'))
    if ta is not None and tb is not None:
        dt = abs(ta - tb)
        if dt <= GATE_MATCHER_WINDOW_SEC:
            # Linear score: 1.0 at 0s → 0.0 at window
            score += _W_TIME * (1.0 - dt / GATE_MATCHER_WINDOW_SEC)

    # 2. Direction
    if _direction_match(a.get('direction'), b.get('direction')):
        score += _W_DIRECTION

    # 3. Lane overlap
    if _lane_overlap(a.get('bbox'), b.get('bbox')):
        score += _W_LANE_OVERLAP

    # 4/5. Plate exact or fuzzy
    pa = _normalize(a.get('plate_matched') or a.get('plate_read'))
    pb = _normalize(b.get('plate_matched') or b.get('plate_read'))
    if pa and pb:
        if pa == pb:
            score += _W_PLATE_EXACT
            return score, 'exact'
        ratio = difflib.SequenceMatcher(None, pa, pb).ratio()
        if ratio >= GATE_MATCHER_MIN_SIMILARITY:
            score += _W_PLATE_FUZZY * ratio
            return score, 'fuzzy'

    return score, 'none'


# Threshold tối thiểu để một candidate đủ điều kiện MATCH
MIN_MATCH_SCORE = 4.0  # plate exact (5) + direction (2) = 7 > 4
# Plate fuzzy (2 * 0.9 = 1.8) + direction (2) + time (1) = 4.8 > 4
MIN_MATCH_SCORE_FUZZY = 4.0

# Ngưỡng "ambiguous" — nếu 2 candidate đạt điểm trong khoảng AMBIGUOUS_GAP
# của top → không ghép.
AMBIGUOUS_GAP = 1.0


class GateEventMatcher:
    """Phase 5 (Task 1): matcher cho 2 camera cùng cổng vật lý.

    Usage:
        matcher = GateEventMatcher()
        best, status = matcher.match(new_event, candidates)

    Auto-match mặc định TẮT — set env GATE_MATCHER_ENABLED=1 để bật.
    """

    def __init__(self, enabled: bool | None = None):
        if enabled is None:
            self.enabled = GATE_MATCHER_ENABLED
        else:
            self.enabled = bool(enabled)
        self.last_call_count = 0  # metric for get_status()
        self.last_disabled_count = 0

    def match(
        self, new_event: dict, candidates: list[dict],
        now: float | None = None,
    ) -> tuple[Optional[dict], str]:
        """Trả (best_candidate | None, status).

        status ∈ {'disabled', 'unmatched', 'matched', 'needs_review',
                  'ambiguous', 'needs_review_b1'}.

        F08 (Task 1) — chính sách strict:
        - Hard gates (BẮT BUỘC trước scoring):
          * Cùng physical gate (`gate_id` khớp) — khác gate_id → bỏ qua
            candidate hoàn toàn (gate_id lịch sử không đổi).
          * Cùng camera role (front/rear) HOẶC nếu calibration chưa có → bỏ
            role check (giữ an toàn nhưng vẫn cho phép match khi không có
            metadata role).
          * Time-corrected window: |t1 - t2| <= FLOOR_WINDOW_SEC. Ngoài
            window → bỏ qua candidate. KHÔNG short-circuit exact plate
            khi ngoài window — exact plate vẫn phải qua time gate.
          * Direction: cả 2 bên phải có direction known VÀ bằng nhau.
            Unknown direction KHÔNG coi là "cùng hướng" với bất kỳ bên
            nào (cả 2 đều unknown → fail). Ngược chiều → fail.
          * Bước 1 status: 'needs_review' (bất kỳ bên nào) → không ghép.

        - Scoring: chỉ chạy SAU khi qua hết hard gates.
          * Plate exact → score cộng cao, vẫn phải có time/direction OK.
          * Plate fuzzy → score thấp hơn, status = needs_review.
          * Single factor (chỉ plate, chỉ time) → không đạt ngưỡng.

        - Multi-candidate: ứng viên nào đạt điểm cao nhất là top. Nếu ≥2
          ứng viên đạt điểm trong AMBIGUOUS_GAP của top → ambiguous (KHÔNG
          ghép dù top có exact plate).
        """
        self.last_call_count += 1
        if not self.enabled:
            self.last_disabled_count += 1
            return None, 'disabled'

        # Bước 1 status check — bất kỳ bên nào không chắc → không ghép
        new_status = (new_event.get("status") or "").lower()
        if new_status == "needs_review":
            return None, 'needs_review_b1'

        # F08: same physical gate hard-gate
        new_gate = new_event.get("gate_id")
        # Direction hard-gate: chỉ chấp nhận khi cả 2 đều known + bằng nhau
        new_dir = (new_event.get("direction") or "").strip().lower()

        scored: list[tuple[float, str, dict]] = []
        for cand in candidates:
            cand_status = (cand.get("status") or "").lower()
            if cand_status == "needs_review":
                continue

            # F08: hard gate — cùng gate
            if new_gate is not None and cand.get("gate_id") is not None:
                if new_gate != cand.get("gate_id"):
                    continue

            # F08: hard gate — time window (PHẢI check trước scoring, KHÔNG
            # short-circuit exact plate khi ngoài window).
            ta = _parse_iso(new_event.get('observed_at'))
            tb = _parse_iso(cand.get('observed_at'))
            if ta is not None and tb is not None:
                if abs(ta - tb) > GATE_MATCHER_WINDOW_SEC:
                    continue  # ngoài window → bỏ candidate

            # F08: hard gate — direction. Unknown KHÔNG match với bất kỳ bên
            # nào (kể cả unknown ↔ unknown → fail để an toàn).
            cand_dir = (cand.get("direction") or "").strip().lower()
            if not new_dir or not cand_dir:
                continue  # thiếu direction → bỏ qua
            if new_dir != cand_dir:
                continue  # ngược chiều → bỏ qua

            score, hint = _score_pair(new_event, cand)
            if score >= MIN_MATCH_SCORE:
                scored.append((score, hint, cand))

        if not scored:
            return None, 'unmatched'

        # F08: sort + AMBIGUOUS check TRƯỚC khi return matched (kể cả top
        # có exact plate).
        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_hint, top_cand = scored[0]

        if len(scored) > 1 and (scored[0][0] - scored[1][0]) < AMBIGUOUS_GAP:
            return None, 'ambiguous'

        if top_hint == 'fuzzy' and top_score >= MIN_MATCH_SCORE_FUZZY:
            return top_cand, 'needs_review'

        if top_score >= MIN_MATCH_SCORE:
            return top_cand, 'matched'

        return None, 'unmatched'

    def status(self) -> dict:
        """Expose matcher state cho /api/system/health."""
        return {
            'enabled': self.enabled,
            'calls': self.last_call_count,
            'disabled_calls': self.last_disabled_count,
            'window_sec': GATE_MATCHER_WINDOW_SEC,
            'min_similarity': GATE_MATCHER_MIN_SIMILARITY,
        }


__all__ = ["GateEventMatcher", "GATE_MATCHER_ENABLED"]