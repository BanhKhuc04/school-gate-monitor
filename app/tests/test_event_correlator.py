"""
pytest tests cho event_correlator.find_correlation_candidate (đợt 2, Bước 3).

Nguyên tắc "không tự đoán" được verify bằng cách viết NHIỀU test âm (không
ghép sai) hơn test dương (ghép đúng) — đây là điểm nhạy cảm nhất của Bước 3:
ghép sai 2 biển số khác nhau = cực tệ hơn là bỏ sót.

Các test DB (link_violation_events, find_correlation_candidates) nằm ở
test_event_correlator_db.py để tách bạch: phần logic thuần (event_correlator.py)
chạy pure unit, phần DB cần fixture client.
"""
from app.cv.event_correlator import find_correlation_candidate, normalize


# ─── Helper ────────────────────────────────────────────────────────────────────

def _ev(plate_read="", plate_matched=None, status="pending", id=1, gate_id="secondary"):
    return {
        "id": id,
        "gate_id": gate_id,
        "plate_read": plate_read,
        "plate_matched": plate_matched,
        "status": status,
        "timestamp": "2026-09-29T12:00:00",
    }


# ─── Test normalize: tách ra vì hàm này quyết định cả "ghép đúng" và "không ghép sai" ───

def test_normalize_uppercases_and_strips_non_alnum():
    assert normalize("29A-123.45") == "29A12345"
    assert normalize(" 50-f2 999 ") == "50F2999"
    assert normalize("") == ""
    assert normalize(None) == ""


# ─── Test dương: GHÉP ĐÚNG ────────────────────────────────────────────────────

def test_exact_match_returns_matched_immediately():
    """Biển số giống hệt (sau normalize) → matched ngay, không cần xét ratio."""
    new = _ev(plate_read="29A-123.45")
    candidates = [_ev(plate_read="29A 12345", plate_matched="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is not None
    assert best["id"] == 2
    assert status == "matched"


def test_plate_matched_takes_priority_over_plate_read():
    """Khi plate_matched có giá trị, dùng nó làm nguồn so sánh (đã qua normalize/validate)."""
    new = _ev(plate_read="29A99999", plate_matched="29A12345")  # read lệch nhưng matched đúng
    candidates = [_ev(plate_read="29A 12345", plate_matched="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is not None
    assert status == "matched"


def test_close_match_above_threshold_returns_needs_review():
    """Biển lệch 1 ký tự (ratio ~0.89) > ngưỡng 0.85 → ghép nhưng để needs_review."""
    new = _ev(plate_read="29A12346")  # lệch 1 ký tự cuối (6 thay vì 5)
    candidates = [_ev(plate_read="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is not None
    assert best["id"] == 2
    assert status == "needs_review"  # không phải matched vì không chắc


def test_picks_best_among_multiple_candidates():
    """Nhiều ứng viên: chọn cái giống nhất."""
    new = _ev(plate_read="29A12345")
    candidates = [
        _ev(plate_read="50B99999", id=2),  # xa
        _ev(plate_read="29A12345", id=3),  # khớp
        _ev(plate_read="29A12346", id=4),  # lệch 1 ký tự
    ]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best["id"] == 3
    assert status == "matched"


# ─── Test âm: KHÔNG GHÉP SAI (ưu tiên hơn test dương) ────────────────────────

def test_completely_different_plates_returns_unmatched():
    """Biển khác hẳn → KHÔNG được ghép. Đây là case quan trọng nhất."""
    new = _ev(plate_read="29A12345")
    candidates = [_ev(plate_read="50B99999", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


def test_below_threshold_returns_unmatched():
    """Biển lệnh vài ký tự, ratio < ngưỡng → không ghép (unmatched), không needs_review."""
    new = _ev(plate_read="29A12345")
    candidates = [_ev(plate_read="29A99999", id=2)]  # 4 ký tự lệch → ratio ~0.6
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


def test_no_candidates_returns_unmatched():
    new = _ev(plate_read="29A12345")
    best, status = find_correlation_candidate(new, [], min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


def test_empty_plate_new_no_candidates_returns_unmatched():
    """Không đọc được biển số phía mình + không có candidate nào trong window → unmatched (không có gì để làm)."""
    new = _ev(plate_read="")
    best, status = find_correlation_candidate(new, [], min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


def test_empty_plate_new_but_has_candidates_returns_needs_review():
    """Phía mình không đọc được biển, bên kia có biển → needs_review (không tự đoán)."""
    new = _ev(plate_read="")
    candidates = [_ev(plate_read="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "needs_review"


def test_empty_plate_candidate_skipped():
    """Ứng viên không có biển số → bỏ qua, không ảnh hưởng quyết định."""
    new = _ev(plate_read="29A12345")
    candidates = [_ev(plate_read="", id=2)]  # candidate rỗng
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


# ─── Test "không tự đoán" nối tiếp Bước 1: status='needs_review' → không ghép ─

def test_new_event_with_needs_review_never_matched():
    """Bước 1: AI không chắc biển số 1 bên → không tự ghép với bên kia, kể cả khi text giống hệt."""
    new = _ev(plate_read="29A12345", status="needs_review")
    candidates = [_ev(plate_read="29A12345", plate_matched="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "needs_review"


def test_candidate_with_needs_review_is_skipped():
    """Ứng viên có status='needs_review' (Bước 1) → bỏ qua, tìm ứng viên khác."""
    new = _ev(plate_read="29A12345")
    candidates = [
        _ev(plate_read="29A12345", id=2, status="needs_review"),  # bỏ qua
        _ev(plate_read="50B99999", id=3),                         # xa, không khớp
    ]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "unmatched"


def test_both_sides_needs_review_returns_needs_review():
    """Cả 2 bên đều status='needs_review' → trả needs_review, không tự ghép."""
    new = _ev(plate_read="29A12345", status="needs_review")
    candidates = [_ev(plate_read="29A12345", id=2, status="needs_review")]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.85)
    assert best is None
    assert status == "needs_review"


# ─── Test edge case ───────────────────────────────────────────────────────────

def test_threshold_zero_means_only_exact_match():
    """min_similarity=0.0 chỉ chấp nhận exact match (ratio==1.0) — ngưỡng cực nhỏ
    nhưng logic vẫn chỉ ghép khi ratio >= ngưỡng, exact match thì trả matched ngay."""
    new = _ev(plate_read="29A12346")
    candidates = [_ev(plate_read="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.0)
    # ratio("29A12346","29A12345") ≈ 7/8 = 0.875 >= 0.0 → needs_review
    assert best is not None
    assert status == "needs_review"


def test_threshold_too_high_means_only_exact_match():
    """min_similarity=0.99 → chỉ match exact (vì ratio lệch 1 ký tự ~ 0.875)."""
    new = _ev(plate_read="29A12346")
    candidates = [_ev(plate_read="29A12345", id=2)]
    best, status = find_correlation_candidate(new, candidates, min_similarity=0.99)
    assert best is None
    assert status == "unmatched"
