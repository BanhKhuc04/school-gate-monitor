"""
pytest tests cho phần DB của Bước 3 (đợt 2): find_correlation_candidates,
link_violation_events, mark_correlation_unmatched — đây là tầng đụng đĩa,
chạy qua fixture client (DB test riêng, cleanup tự động).
"""
import datetime


def _add(client, plate_read, plate_matched=None, gate_id="main", status="pending",
         timestamp=None, violation_type="NO_HELMET"):
    from app.db import add_violation_event
    return add_violation_event(
        timestamp=timestamp or datetime.datetime.now().isoformat(),
        plate_read=plate_read,
        plate_matched=plate_matched,
        helmet_status="no_helmet",
        violation_type=violation_type,
        gate_id=gate_id,
        status=status,
    )


# ─── find_correlation_candidates ───────────────────────────────────────────────

def test_find_candidates_filters_by_different_gate_and_window(client):
    """Chỉ tìm event ở gate KHÁC, trong cửa sổ ±window_sec, chưa bị ghép."""
    from app.db import find_correlation_candidates
    # Event ở gate "main" vừa được insert
    new_id = _add(client, "29A12345", gate_id="main")
    new_event = {
        "id": new_id,
        "gate_id": "main",
        "timestamp": datetime.datetime.now().isoformat(),
    }
    # Ứng viên hợp lệ: gate khác + cùng timestamp
    cand_id = _add(client, "29A12345", gate_id="secondary",
                   timestamp=datetime.datetime.now().isoformat())
    # Ứng viên SAI: cùng gate "main" → bỏ
    same_gate_id = _add(client, "29A99999", gate_id="main",
                        timestamp=datetime.datetime.now().isoformat())

    candidates = find_correlation_candidates(new_event, window_sec=15)
    cand_ids = [c["id"] for c in candidates]
    assert cand_id in cand_ids
    assert same_gate_id not in cand_ids
    assert new_id not in cand_ids  # bản thân nó


def test_find_candidates_returns_empty_when_no_gate_id(client):
    """gate_id None → không ghép được, trả [] ngay (chỉ có 1 camera)."""
    from app.db import find_correlation_candidates
    new_event = {"id": 999, "gate_id": None, "timestamp": "2026-09-29T12:00:00"}
    assert find_correlation_candidates(new_event, window_sec=15) == []


def test_find_candidates_excludes_already_linked(client):
    """Ứng viên đã bị ghép với event khác (linked_violation_id IS NOT NULL) → bỏ qua."""
    from app.db import find_correlation_candidates, link_violation_events
    a = _add(client, "29A12345", gate_id="main")
    b = _add(client, "29A12345", gate_id="secondary")
    c = _add(client, "29A12345", gate_id="secondary")  # ứng viên tiềm năng

    # Ghép a <-> b trước
    assert link_violation_events(a, b) is True

    # Tìm ứng viên cho c: b đã bị linked → bỏ; còn lại chỉ a (gate khác) nhưng a đã linked
    c_event = {
        "id": c, "gate_id": "secondary",
        "timestamp": datetime.datetime.now().isoformat(),
    }
    candidates = find_correlation_candidates(c_event, window_sec=15)
    assert all(cand["linked_violation_id"] if "linked_violation_id" in cand else True for cand in candidates)
    # Chính xác: candidates phải rỗng vì cả a và b đều đã linked
    cand_ids = [cand["id"] for cand in candidates]
    assert a not in cand_ids
    assert b not in cand_ids


# ─── link_violation_events ────────────────────────────────────────────────────

def test_link_violation_events_updates_both_rows(client):
    """Ghép a <-> b: cả 2 bản ghi được set linked_violation_id trỏ sang nhau."""
    from app.db import link_violation_events, get_connection
    a = _add(client, "29A12345", gate_id="main")
    b = _add(client, "29A12345", gate_id="secondary")

    assert link_violation_events(a, b) is True

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, linked_violation_id, correlation_status FROM violation_events WHERE id IN (?, ?) ORDER BY id",
            (a, b),
        ).fetchall()
    finally:
        conn.close()
    assert rows[0]["linked_violation_id"] == b
    assert rows[0]["correlation_status"] == "matched"
    assert rows[1]["linked_violation_id"] == a
    assert rows[1]["correlation_status"] == "matched"


def test_link_violation_events_returns_false_for_same_id(client):
    """id_a == id_b → không ghép, trả False (không tự trỏ vào chính mình)."""
    from app.db import link_violation_events
    a = _add(client, "29A12345", gate_id="main")
    assert link_violation_events(a, a) is False


def test_link_violation_events_returns_false_if_one_already_linked(client):
    """Race: 1 trong 2 đã bị ghép → transaction thứ 2 rollback, trả False."""
    from app.db import link_violation_events, get_connection
    a = _add(client, "29A12345", gate_id="main")
    b = _add(client, "29A12345", gate_id="secondary")
    c = _add(client, "29A12345", gate_id="secondary")  # thêm 1 candidate

    # Ghép a <-> b trước
    assert link_violation_events(a, b) is True
    # Thử ghép a <-> c — a đã bị linked, phải fail
    assert link_violation_events(a, c) is False

    # c vẫn unlinked, không bị đụng
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT linked_violation_id, correlation_status FROM violation_events WHERE id = ?", (c,)
        ).fetchone()
    finally:
        conn.close()
    assert row["linked_violation_id"] is None
    assert row["correlation_status"] is None


def test_link_violation_events_with_needs_review_status(client):
    """Truyền status='needs_review' → cả 2 bản ghi có correlation_status='needs_review'."""
    from app.db import link_violation_events, get_connection
    a = _add(client, "29A12346", gate_id="main")
    b = _add(client, "29A12345", gate_id="secondary")  # lệch 1 ký tự

    assert link_violation_events(a, b, status="needs_review") is True

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT correlation_status FROM violation_events WHERE id IN (?, ?)", (a, b),
        ).fetchall()
    finally:
        conn.close()
    assert all(r["correlation_status"] == "needs_review" for r in rows)


# ─── mark_correlation_unmatched ───────────────────────────────────────────────

def test_mark_correlation_unmatched_only_when_still_null(client):
    """Chỉ set 'unmatched' nếu correlation_status đang NULL — không ghi đè lên 'matched'."""
    from app.db import link_violation_events, mark_correlation_unmatched, get_connection
    a = _add(client, "29A12345", gate_id="main")
    b = _add(client, "29A12345", gate_id="secondary")
    link_violation_events(a, b)  # a giờ đã correlation_status='matched'

    # mark_correlation_unmatched(a) phải KHÔNG ghi đè
    mark_correlation_unmatched(a)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT correlation_status FROM violation_events WHERE id = ?", (a,)
        ).fetchone()
    finally:
        conn.close()
    assert row["correlation_status"] == "matched"  # không bị đổi


def test_mark_correlation_unmatched_sets_unmatched_for_null(client):
    a = _add(client, "29A12345", gate_id="main")
    from app.db import mark_correlation_unmatched, get_connection
    mark_correlation_unmatched(a)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT correlation_status FROM violation_events WHERE id = ?", (a,)
        ).fetchone()
    finally:
        conn.close()
    assert row["correlation_status"] == "unmatched"


def test_mark_correlation_unmatched_accepts_needs_review_status(client):
    """Regression: mark_correlation_unmatched() từng HARDCODE 'unmatched' bất kể
    tham số truyền vào — bug này làm mất tín hiệu 'cần kiểm tra' khi
    _try_correlate() gọi nó cho case (None, 'needs_review') trả về từ
    find_correlation_candidate() (1 trong 2 bên status='needs_review' từ Bước 1,
    hoặc không đọc được biển để so). Giờ phải ghi đúng status truyền vào."""
    a = _add(client, "29A12345", gate_id="main")
    from app.db import mark_correlation_unmatched, get_connection
    mark_correlation_unmatched(a, status="needs_review")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT correlation_status FROM violation_events WHERE id = ?", (a,)
        ).fetchone()
    finally:
        conn.close()
    assert row["correlation_status"] == "needs_review"


def test_try_correlate_persists_needs_review_not_unmatched_when_step1_uncertain(client):
    """Regression end-to-end: VideoPipeline._try_correlate() với 1 event Bước 1 đã
    gắn status='needs_review' (biển đọc không chắc) + có ứng viên cùng cửa sổ thời
    gian ở gate khác → correlation_status LƯU VÀO DB phải là 'needs_review', KHÔNG
    được là 'unmatched' (bug thật đã xảy ra: _try_correlate cũ hardcode gọi
    mark_correlation_unmatched() không truyền status, luôn ghi 'unmatched' dù
    find_correlation_candidate() đã trả đúng ('needs_review')."""
    from app.cv.pipeline import VideoPipeline
    from app.db import get_connection

    new_id = _add(client, "29A12341", plate_matched=None, gate_id="main",
                  status="needs_review")
    _add(client, "29A12341", plate_matched=None, gate_id="secondary")  # ứng viên hợp lệ

    pipeline = VideoPipeline.__new__(VideoPipeline)
    new_event = {
        "id": new_id, "gate_id": "main",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "plate_read": "29A12341", "plate_matched": None, "status": "needs_review",
    }
    pipeline._try_correlate(new_event)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT correlation_status FROM violation_events WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["correlation_status"] == "needs_review"


# ─── Schema migrations đã chạy ────────────────────────────────────────────────

def test_correlation_columns_exist(client):
    """2 cột mới của Bước 3 phải tồn tại trên violation_events sau init_db."""
    from app.db import get_connection
    conn = get_connection()
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(violation_events)").fetchall()}
    finally:
        conn.close()
    assert "linked_violation_id" in cols
    assert "correlation_status" in cols
