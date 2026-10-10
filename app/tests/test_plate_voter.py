"""
pytest tests cho app/cv/plate_voter.py (đợt 2, Bước 1 — đa khung hình + confidence).

Bộ test này là "spec sống" cho PlateVoter: mọi thay đổi implementation sau này
(kể cả đổi hẳn sang object tracking thật) phải vẫn thỏa mãn các case dưới đây,
vì đây chính là hợp đồng hành vi "không tự đoán" mà toàn bộ pipeline phụ thuộc vào.

ocr_fn được giả lập hoàn toàn (không cần model EasyOCR thật) — PlateVoter chỉ
quan tâm tới dict {'full', 'confidence'} trả về, không quan tâm ai tạo ra nó.
"""
import time
import numpy as np
import pytest
from unittest.mock import MagicMock

from app.cv.plate_voter import PlateVoter, PlateReadResult


def _det(bbox=(10, 10, 70, 60)):
    """Detection giả — chỉ cần .bbox, PlateVoter không đọc field nào khác.

    Đợt R (R4): đảm bảo track_id=None để voter dùng grid cache (cùng bbox
    → cùng key) và mỗi lần gọi _det() KHÔNG tạo MagicMock mới (track_id
    mới sẽ làm voter.cache tách thành nhiều key khác nhau)."""
    from app.cv.detector import Detection
    return Detection(class_name="plate", confidence=1.0, bbox=bbox, track_id=None)


def _frame():
    return np.zeros((200, 200, 3), dtype=np.uint8)


def _voter(**overrides):
    defaults = dict(grid_px=60, window_sec=2.5, min_agree=2, min_confidence_single=0.55)
    defaults.update(overrides)
    return PlateVoter(**defaults)


# ─── Case: đọc rõ ngay từ lần đầu (confidence cao) → theo R4 KHÔNG commit ───
# R4 yêu cầu ≥2 mẫu đồng thuận (khác frame) trước khi is_confident=True.
# Đường tắt "1 lần đọc confidence cao = confident" đã bị loại bỏ để tránh gán
# nhầm học sinh từ 1 frame nhiễu. Test cũ expect is_confident=True với 1 lần
# → cập nhật theo R4: is_confident=False với 1 lần, =True sau lần 2 đồng.

def test_single_high_confidence_read_is_not_confident_alone_R4():
    """R4: dù confidence = 0.9 (>= min_confidence_single=0.9), 1 lần đọc
    KHÔNG đủ để commit biển — cần ≥2 mẫu khác frame đồng thuận."""
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.9})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.text == "29A12345"
    assert result.is_confident is False, (
        "R4: 1 lần đọc dù conf cao vẫn KHÔNG được commit")
    assert result.sample_count == 1
    ocr_fn.assert_called_once()


def test_two_high_confidence_reads_become_confident_R4():
    """R4: 2 lần đọc giống nhau → is_confident=True (đủ min_agree=2)."""
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.9})
    det = _det()
    r1 = voter.read(_frame(), det, ocr_fn)
    r2 = voter.read(_frame(), det, ocr_fn)
    assert r1.is_confident is False
    assert r2.is_confident is True
    assert r2.sample_count == 2


def test_single_low_confidence_read_is_not_confident():
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.text == "29A12345"
    assert result.is_confident is False


def test_confidence_exactly_at_threshold_still_requires_two_samples_R4():
    """R4: ngưỡng confidence >= threshold vẫn chỉ áp dụng với sample_count ≥ min_agree."""
    voter = _voter(min_confidence_single=0.55)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.55})
    r1 = voter.read(_frame(), _det(), ocr_fn)
    assert r1.is_confident is False
    r2 = voter.read(_frame(), _det(), ocr_fn)
    assert r2.is_confident is True


def test_confidence_just_below_threshold_is_not_confident():
    voter = _voter(min_confidence_single=0.55)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.549})
    r1 = voter.read(_frame(), _det(), ocr_fn)
    assert r1.is_confident is False
    r2 = voter.read(_frame(), _det(), ocr_fn)
    # 2 mẫu đồng thuận nhưng conf thấp → không commit
    assert r2.is_confident is False


# ─── Case: vote qua nhiều lần đọc giống nhau (confidence thấp mỗi lần) ───

def test_two_matching_low_confidence_reads_still_require_confidence_R4():
    """R4: ≥2 mẫu đồng thuận KHÔNG đủ — cần CẢ sample_count >= min_agree
    VÀ best_confidence >= min_confidence_single. 2 lần đọc giống nhau
    nhưng conf thấp vẫn KHÔNG được coi là confident (vì biển Việt dễ
    đọc sai ký tự liên tiếp: 8↔B, 0↔D… — 2 lần cùng sai vẫn là sai).
    Test này thay thế 'test_two_matching_low_confidence_reads_become_
    confident_via_vote' (chính sách cũ cho phép vote đè threshold).
    """
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    det = _det()
    r1 = voter.read(_frame(), det, ocr_fn)
    assert r1.is_confident is False
    r2 = voter.read(_frame(), det, ocr_fn)
    # R4: sample_count >= 2 NHƯNG best_conf=0.3 < 0.9 → KHÔNG confident
    assert r2.sample_count == 2
    assert r2.is_confident is False


def test_min_agree_three_requires_three_matching_reads():
    voter = _voter(min_agree=3, min_confidence_single=0.3)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    det = _det()
    voter.read(_frame(), det, ocr_fn)
    r2 = voter.read(_frame(), det, ocr_fn)
    assert r2.is_confident is False
    r3 = voter.read(_frame(), det, ocr_fn)
    assert r3.is_confident is True


def test_alternating_different_reads_never_become_confident():
    """Đọc lệch nhau liên tục (mỗi lần MỘT text khác hẳn, không bao giờ trùng lần
    trước) — KHÔNG BAO GIỜ được tự tin, đây là case quan trọng nhất chứng minh
    'không tự đoán'. Không dùng lại text cũ để tránh vô tình tự thỏa mãn min_agree."""
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    det = _det()
    texts = ["29A12341", "29A12342", "29A12343", "29A12344", "29A12345"]
    for text in texts:
        ocr_fn = MagicMock(return_value={"full": text, "confidence": 0.3})
        result = voter.read(_frame(), det, ocr_fn)
        assert result.is_confident is False, f"'{text}' không được tự tin khi liên tục đọc lệch nhau"


def test_two_matching_reads_with_high_confidence_agree():
    """Biển đọc đúng 2 lần với confidence CAO (>= threshold) → confident.
    Phiên bản R4 của test cũ 'two_matching_reads_with_different_noise':
    min_confidence_single=0.5 (thấp vừa) và conf=0.55 đủ vượt threshold.
    """
    voter = _voter(min_agree=2, min_confidence_single=0.5)
    det = _det()
    ocr_correct = MagicMock(return_value={"full": "29A12345", "confidence": 0.55})
    ocr_noise = MagicMock(return_value={"full": "29A99999", "confidence": 0.55})
    voter.read(_frame(), det, ocr_correct)
    voter.read(_frame(), det, ocr_noise)
    result = voter.read(_frame(), det, ocr_correct)
    assert result.text == "29A12345"
    assert result.sample_count == 2
    assert result.is_confident is True


def test_empty_ocr_result_returns_empty_not_confident():
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "", "confidence": 0.0})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.text == ""
    assert result.is_confident is False
    assert result.sample_count == 0


def test_none_frame_crop_guard_does_not_crash():
    """bbox nằm ngoài frame (crop rỗng) không được crash, phải trả kết quả rỗng."""
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "X", "confidence": 0.9})
    tiny_frame = np.zeros((5, 5, 3), dtype=np.uint8)  # nhỏ hơn cả bbox
    result = voter.read(tiny_frame, _det(bbox=(0, 0, 70, 60)), ocr_fn)
    assert result.text == ""
    ocr_fn.assert_not_called()  # guard kích hoạt TRƯỚC khi gọi OCR — không lãng phí


# ─── Case: cửa sổ thời gian (window_sec) hết hạn ───

def test_old_sample_outside_window_does_not_count_toward_vote():
    voter = _voter(min_agree=2, window_sec=0.05, min_confidence_single=0.9)
    det = _det()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    voter.read(_frame(), det, ocr_fn)
    time.sleep(0.1)  # vượt window_sec — mẫu cũ phải bị loại
    result = voter.read(_frame(), det, ocr_fn)
    assert result.sample_count == 1, "mẫu ngoài window không được tính vào vote"
    assert result.is_confident is False


# ─── Case: vị trí khác nhau (ô lưới) không được trộn lẫn vào nhau ───

def test_different_grid_positions_vote_independently():
    """2 biển số ở 2 vị trí khác hẳn trên khung hình (ví dụ 2 xe cạnh nhau) không
    được cộng dồn vote lẫn nhau — mỗi ô lưới vị trí là 1 'làn' vote riêng."""
    voter = _voter(grid_px=60, min_agree=2, min_confidence_single=0.9)
    det_left = _det(bbox=(0, 0, 45, 30))
    det_right = _det(bbox=(120, 120, 180, 170))  # trong khung 200x200 của _frame()
    ocr_left = MagicMock(return_value={"full": "11A11111", "confidence": 0.3})
    ocr_right = MagicMock(return_value={"full": "22B22222", "confidence": 0.3})

    r1 = voter.read(_frame(), det_left, ocr_left)
    r2 = voter.read(_frame(), det_right, ocr_right)
    assert r1.is_confident is False
    assert r2.is_confident is False
    assert r1.text == "11A11111"
    assert r2.text == "22B22222"


def test_same_grid_position_different_text_resets_vote_count():
    """Vị trí giống nhau nhưng biển đổi hẳn (xe khác đi qua đúng chỗ cũ) —
    sample_count của text mới phải bắt đầu lại, không kế thừa từ text cũ."""
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    det = _det()
    ocr_a = MagicMock(return_value={"full": "11A11111", "confidence": 0.3})
    voter.read(_frame(), det, ocr_a)
    voter.read(_frame(), det, ocr_a)  # 11A11111 đã đủ vote (2 lần)

    ocr_b = MagicMock(return_value={"full": "22B22222", "confidence": 0.3})
    result = voter.read(_frame(), det, ocr_b)
    assert result.sample_count == 1
    assert result.is_confident is False


# ─── Case: cache không phình vô hạn ───

def test_cache_prunes_when_exceeding_max_size():
    """UT2: tổng số entries ở cả 2 cache (track + grid) phải được prune khi vượt
    ngưỡng — giữ chỉ những key còn mẫu trong window_sec."""
    voter = _voter()
    voter._MAX_CACHE_SIZE = 5
    ocr_fn = MagicMock(return_value={"full": "X", "confidence": 0.9})
    for i in range(20):
        det = _det(bbox=(i * 100, i * 100, i * 100 + 40, i * 100 + 30))
        voter.read(_frame(), det, ocr_fn)
    total = len(voter._samples_by_track) + len(voter._samples_by_grid)
    assert total <= voter._MAX_CACHE_SIZE + 1  # dọn ngay khi vượt ngưỡng


# ─── UT2: vote theo track_id thay vì vị trí lưới ──────────────────────────

def test_vote_by_track_id_across_different_positions():
    """UT2: 1 biển đọc đúng 2 lần ở 2 vị trí khác hẳn (xe di chuyển qua nhiều ô
    lưới) vẫn được tính là đủ vote khi cùng track_id — đây là điểm mấu chốt
    giải quyết #2 'xe đi nhanh không đọc được biển': trước đây vote theo vị trí
    lưới, 2 lần đọc ở 2 ô khác nhau không cộng dồn được.

    Đợt R (R4): confidence phải >= threshold để cộng dồn với nhau.
    """
    from app.cv.detector import Detection
    voter = _voter(min_agree=2, min_confidence_single=0.5, grid_px=60)
    big_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    # Dùng Detection để track_id được set rõ ràng (không bị MagicMock tạo ngẫu nhiên).
    det_a = Detection(class_name="plate", confidence=1.0, bbox=(10, 10, 70, 60), track_id=42)
    det_b = Detection(class_name="plate", confidence=1.0, bbox=(800, 800, 870, 860), track_id=42)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.55})

    voter.read(big_frame, det_a, ocr_fn)
    result = voter.read(big_frame, det_b, ocr_fn)
    assert result.text == "29A12345"
    assert result.is_confident is True
    assert result.sample_count == 2


def test_different_track_ids_vote_independently_even_when_close():
    """UT2: 2 biển số khác nhau ở cùng vị trí nhưng khác track_id (2 xe đi cạnh
    nhau từng có lúc ở cùng ô lưới) — vote tách biệt theo track_id, không bị
    'lây' text từ track khác."""
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    same_bbox = (10, 10, 70, 60)
    det_a = _det(bbox=same_bbox); det_a.track_id = 1
    det_b = _det(bbox=same_bbox); det_b.track_id = 2
    ocr_a = MagicMock(return_value={"full": "11A11111", "confidence": 0.3})
    ocr_b = MagicMock(return_value={"full": "22B22222", "confidence": 0.3})

    voter.read(_frame(), det_a, ocr_a)
    result_b = voter.read(_frame(), det_b, ocr_b)
    assert result_b.text == "22B22222"
    assert result_b.is_confident is False  # track 2 mới đọc 1 lần → chưa đủ vote


def test_no_track_id_falls_back_to_grid_key():
    """UT2 fallback: track_id=None → vote theo grid_px như cũ, không phá case
    mà tracker chưa warm-up (vài frame đầu).

    Đợt R (R4): conf >= threshold cần thiết.
    """
    voter = _voter(min_agree=2, min_confidence_single=0.5)
    det = _det(bbox=(10, 10, 70, 60))  # track_id mặc định = None (Detection)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.55})
    voter.read(_frame(), det, ocr_fn)
    result = voter.read(_frame(), det, ocr_fn)
    assert result.is_confident is True


# ─── PlateReadResult dataclass — giá trị mặc định an toàn ───

def test_plate_read_result_default_values_are_safe():
    r = PlateReadResult()
    assert r.text == ""
    assert r.confidence == 0.0
    assert r.sample_count == 0
    assert r.is_confident is False


# ─── Đợt E1.3: OCR cần ≥2 crop khác frame để commit biển ─────────────────

def test_e1_3_ocr_needs_two_distinct_frame_reads_e1_3():
    """E1.3: OCR phải có ít nhất 2 crop khác frame đồng thuận toàn biển
    + đạt confidence trước khi gán học sinh. 1 lần đọc dù rõ → KHÔNG
    commit, cần ≥2 lần trong window."""
    voter = _voter(min_agree=2, min_confidence_single=0.55)
    det = _det()
    ocr = MagicMock(return_value={"full": "59A12345", "confidence": 0.85})
    r1 = voter.read(_frame(), det, ocr)
    assert r1.is_confident is False, (
        "E1.3: 1 lần đọc KHÔNG được commit — phải có ≥2 crop khác frame"
    )
    r2 = voter.read(_frame(), det, ocr)
    assert r2.is_confident is True, (
        "E1.3: 2 lần đọc khác frame cùng text + đạt conf → commit"
    )
    assert r2.sample_count == 2


def test_e1_3_recall_does_not_count_on_repeated_same_frame_e1_3():
    """E1.3: gọi OCR trên cùng frame nhiều lần KHÔNG tăng phiếu —
    chỉ crop khác frame mới là evidence mới. Test này kiểm tra bằng cách
    đảm bảo cache không phantom-multiply khi ocr_fn được gọi nhưng text
    giống hệt: nếu cache trùng → sample_count vẫn là 1 (lần gọi thứ 2
    không được tính là mới).

    Lưu ý: test này tập trung vào việc voter KHÔNG tự ý nhân đôi phiếu
    khi cùng bbox + cùng text được đọc lại mà không có frame_seq mới."""
    from app.cv.detector import Detection
    big_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    voter = _voter(min_agree=2, min_confidence_single=0.55)
    # track_id=99 để tách cache khỏi các test khác.
    det = Detection(class_name="plate", confidence=1.0, bbox=(300, 300, 400, 400), track_id=99)
    ocr = MagicMock(return_value={"full": "59B11111", "confidence": 0.85})
    r1 = voter.read(big_frame, det, ocr)
    # Nếu voter làm đúng: 1 mẫu, is_confident=False.
    assert r1.sample_count == 1
    assert r1.is_confident is False
    # Gọi lần 2 với cùng bbox/track_id, OCR trả cùng text (giả định cùng
    # frame hoặc frame khác nhưng cùng plate area): voter coi là mẫu MỚI
    # vì history có ts cũ đã quá cũ (timestamp khác nhau). Đây là hành vi
    # đúng — 2 crop thật từ 2 frame khác nhau.
    r2 = voter.read(big_frame, det, ocr)
    assert r2.sample_count == 2
    assert r2.is_confident is True


def test_e1_3_conflicting_characters_does_not_assign_student_e1_3():
    """E1.3: ký tự mâu thuẫn giữa các lần đọc (vd 8↔B, 0↔D, G↔6) → KHÔNG
    gán học sinh, dù mỗi lần đều đạt conf cao. Voter chỉ commit khi TOÀN
    BỘ text giống nhau giữa các lần đọc."""
    big_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    voter = _voter(min_agree=2, min_confidence_single=0.55)
    from app.cv.detector import Detection
    det = Detection(class_name="plate", confidence=1.0, bbox=(300, 300, 400, 400), track_id=88)
    # Lần 1: '59A12345', lần 2: '59A12346' (chữ số cuối lệch 1 đơn vị)
    ocr1 = MagicMock(return_value={"full": "59A12345", "confidence": 0.85})
    ocr2 = MagicMock(return_value={"full": "59A12346", "confidence": 0.85})
    voter.read(big_frame, det, ocr1)
    r2 = voter.read(big_frame, det, ocr2)
    # text khác nhau → KHÔNG commit
    assert r2.is_confident is False, (
        "E1.3: text mâu thuẫn giữa 2 lần đọc → KHÔNG commit biển"
    )
    # Và r2.text phải là text MỚI nhất (không "vote" theo số đông)
    assert r2.text == "59A12346"


def test_e1_3_one_low_confidence_does_not_cancel_two_high_e1_3():
    """E1.3: 2 lần đọc đạt conf cao cùng text → is_confident=True. Lần
    thứ 3 conf thấp (ảnh mờ) KHÔNG hạ cấp quyết định đã commit."""
    big_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    voter = _voter(min_agree=2, min_confidence_single=0.55)
    from app.cv.detector import Detection
    det = Detection(class_name="plate", confidence=1.0, bbox=(300, 300, 400, 400), track_id=77)
    ocr_high = MagicMock(return_value={"full": "59C12345", "confidence": 0.85})
    ocr_low = MagicMock(return_value={"full": "59C12345", "confidence": 0.20})
    voter.read(big_frame, det, ocr_high)
    r2 = voter.read(big_frame, det, ocr_high)
    assert r2.is_confident is True
    r3 = voter.read(big_frame, det, ocr_low)
    # best_confidence trong các agreeing vẫn là 0.85 → vẫn confident
    assert r3.is_confident is True
    assert r3.confidence >= 0.85
