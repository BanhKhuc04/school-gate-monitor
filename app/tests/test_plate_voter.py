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
    """Detection giả — chỉ cần .bbox, PlateVoter không đọc field nào khác."""
    return MagicMock(bbox=bbox)


def _frame():
    return np.zeros((200, 200, 3), dtype=np.uint8)


def _voter(**overrides):
    defaults = dict(grid_px=60, window_sec=2.5, min_agree=2, min_confidence_single=0.55)
    defaults.update(overrides)
    return PlateVoter(**defaults)


# ─── Case: đọc rõ ngay từ lần đầu (confidence cao) → tin ngay, không cần vote ───

def test_single_high_confidence_read_is_confident_immediately():
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.9})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.text == "29A12345"
    assert result.is_confident is True
    assert result.sample_count == 1
    ocr_fn.assert_called_once()


def test_single_low_confidence_read_is_not_confident():
    voter = _voter()
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.text == "29A12345"
    assert result.is_confident is False


def test_confidence_exactly_at_threshold_counts_as_confident():
    """Ngưỡng là >=, không phải >."""
    voter = _voter(min_confidence_single=0.55)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.55})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.is_confident is True


def test_confidence_just_below_threshold_is_not_confident():
    voter = _voter(min_confidence_single=0.55)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.549})
    result = voter.read(_frame(), _det(), ocr_fn)
    assert result.is_confident is False


# ─── Case: vote qua nhiều lần đọc giống nhau (confidence thấp mỗi lần) ───

def test_two_matching_low_confidence_reads_become_confident_via_vote():
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    ocr_fn = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    det = _det()
    r1 = voter.read(_frame(), det, ocr_fn)
    assert r1.is_confident is False  # lần đầu chưa đủ vote
    r2 = voter.read(_frame(), det, ocr_fn)
    assert r2.is_confident is True   # lần 2 giống hệt → đủ vote
    assert r2.sample_count == 2


def test_min_agree_three_requires_three_matching_reads():
    voter = _voter(min_agree=3, min_confidence_single=0.9)
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


def test_two_matching_reads_with_different_noise_between_still_agree():
    """Biển đọc đúng 2 lần (không liên tiếp — có 1 lần đọc nhiễu xen giữa) vẫn
    phải được tính là đủ vote, vì vote đếm theo 'số lần text X xuất hiện trong
    window', không yêu cầu 2 lần đó phải LIÊN TIẾP nhau."""
    voter = _voter(min_agree=2, min_confidence_single=0.9)
    det = _det()
    ocr_correct = MagicMock(return_value={"full": "29A12345", "confidence": 0.3})
    ocr_noise = MagicMock(return_value={"full": "29A99999", "confidence": 0.3})
    voter.read(_frame(), det, ocr_correct)   # lần 1: đúng
    voter.read(_frame(), det, ocr_noise)     # lần 2: nhiễu — không liên quan
    result = voter.read(_frame(), det, ocr_correct)  # lần 3: đúng lại
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
    ocr_a = MagicMock(return_value={"full": "AAAAAAAA", "confidence": 0.3})
    voter.read(_frame(), det, ocr_a)
    voter.read(_frame(), det, ocr_a)  # AAAAAAAA đã đủ vote (2 lần)

    ocr_b = MagicMock(return_value={"full": "BBBBBBBB", "confidence": 0.3})
    result = voter.read(_frame(), det, ocr_b)
    assert result.sample_count == 1
    assert result.is_confident is False


# ─── Case: cache không phình vô hạn ───

def test_cache_prunes_when_exceeding_max_size():
    voter = _voter()
    voter._MAX_CACHE_SIZE = 5
    ocr_fn = MagicMock(return_value={"full": "X", "confidence": 0.9})
    for i in range(20):
        det = _det(bbox=(i * 100, i * 100, i * 100 + 40, i * 100 + 30))
        voter.read(_frame(), det, ocr_fn)
    assert len(voter._samples) <= voter._MAX_CACHE_SIZE + 1  # dọn ngay khi vượt ngưỡng


# ─── PlateReadResult dataclass — giá trị mặc định an toàn ───

def test_plate_read_result_default_values_are_safe():
    r = PlateReadResult()
    assert r.text == ""
    assert r.confidence == 0.0
    assert r.sample_count == 0
    assert r.is_confident is False
