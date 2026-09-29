"""
Ghép 1 lượt xe từ 2 camera (trước + sau) — đợt 2, Bước 3.

Tách riêng khỏi pipeline.py để dễ thay đổi logic chấm điểm sau này (ví dụ
sau này thêm yếu tố thời gian gần hơn hay thêm bounding-box similarity
khi có tracker). Hiện tại chỉ so sánh biển số — đúng theo yêu cầu của
người dùng (biển số là khóa chính).

Nguyên tắc "không tự đoán" được áp dụng ở đây:
- Plate giống hệt (sau normalize) → ghép ngay, status='matched'.
- Plate lệch ít (SequenceMatcher.ratio >= CORRELATION_MIN_SIMILARITY) →
  ghép nhưng status='needs_review' (1 trong 2 camera đọc có thể sai).
- Plate khác hẳn → không ghép, status='unmatched'.
- Bất kỳ bên nào status='needs_review' (Bước 1) → KHÔNG tự ghép, luôn
  trả 'needs_review' — vì nếu AI đã không chắc biển số 1 bên, việc so
  sánh với bên kia cũng không có ý nghĩa gì (so sánh 2 thứ đều mơ hồ).
"""
import difflib
from typing import Optional


def normalize(s: Optional[str]) -> str:
    """Uppercase + strip non-alnum — đồng bộ với db.normalize_plate."""
    if not s:
        return ""
    import re
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def find_correlation_candidate(new_event: dict, candidates: list[dict],
                                min_similarity: float) -> tuple[Optional[dict], str]:
    """
    Chấm điểm mỗi ứng viên, chọn ứng viên tốt nhất.

    Args:
        new_event: dict tối thiểu có {'plate_read', 'plate_matched', 'status'}.
            'plate_read' là biển đọc thô, 'plate_matched' là biển đã khớp
            whitelist (ưu tiên hơn vì đã qua bước normalize/validate).
        candidates: list các dict ứng viên từ db.find_correlation_candidates,
            mỗi dict có cùng các trường trên + 'id'.
        min_similarity: ngưỡng SequenceMatcher.ratio() để coi là 'tương tự'.

    Returns:
        (candidate | None, correlation_status).
        - (None, 'unmatched') nếu không có ứng viên nào đạt ngưỡng.
        - (best, 'matched') nếu best có plate giống hệt HOẶC similarity >= 0.99.
        - (best, 'needs_review') nếu best có similarity trong khoảng
          [min_similarity, 1.0) — có vẻ cùng xe nhưng đọc lệch nhau.
        - (None, 'needs_review') nếu 1 trong 2 bên status='needs_review'
          (Bước 1) → không tự ghép, báo để người kiểm tra.

    Ghi chú:
        - Dùng 'plate_matched' làm nguồn so sánh ưu tiên khi có (đã qua
          whitelist/normalize); fallback 'plate_read' nếu matched rỗng.
        - Plate rỗng ở cả 2 bên → không ghép (unmatched) — không có gì để so.
    """
    new_status = (new_event.get("status") or "").lower()
    new_plate = normalize(new_event.get("plate_matched") or new_event.get("plate_read"))

    # Bất kỳ bên nào Bước 1 đã gắn 'needs_review' → không tự ghép, để người xem
    if new_status == "needs_review":
        return None, "needs_review"

    if not new_plate or not candidates:
        # Không có biển số để so HOẶC không tìm được ứng viên nào trong window
        if candidates and not new_plate:
            # Có ứng viên nhưng phía mình không đọc được biển — cần người xem
            return None, "needs_review"
        return None, "unmatched"

    best = None
    best_ratio = 0.0
    best_exact = False
    best_candidate_status = ""

    for cand in candidates:
        cand_status = (cand.get("status") or "").lower()
        if cand_status == "needs_review":
            # Bên kia Bước 1 cũng không chắc → không ghép
            continue
        cand_plate = normalize(cand.get("plate_matched") or cand.get("plate_read"))
        if not cand_plate:
            continue
        if cand_plate == new_plate:
            # Khớp tuyệt đối → ưu tiên cao nhất, không cần xét ratio nữa
            return cand, "matched"
        ratio = difflib.SequenceMatcher(None, new_plate, cand_plate).ratio()
        if ratio > best_ratio:
            best = cand
            best_ratio = ratio
            best_exact = False
            best_candidate_status = cand_status

    if best is None:
        return None, "unmatched"

    if best_ratio >= min_similarity:
        # Có vẻ cùng xe nhưng đọc lệch nhau → ghép nhưng để người kiểm tra
        return best, "needs_review"

    return None, "unmatched"
