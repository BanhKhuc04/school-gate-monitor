"""
OCR cho biển số xe Việt Nam.

- Chia đôi vùng crop (dòng trên/dưới cho biển 2 dòng)
- EasyOCR từng dòng
- Chuẩn hóa: viết hoa, bỏ khoảng trắng/gạch ngang
"""
import re
import cv2
import numpy as np
import easyocr
import threading

from app.config import DEVICE
from app.cv.plate_preprocess import enhance_plate, rectify_plate

# Các tham số OCR dùng chung cho mọi lần readtext().
# allowlist: chỉ nhận diện ký tự biển số VN (số + chữ cái + gạch ngang)
# paragraph=False: không gộp text thành đoạn (tránh đọc nhầm text gần nhau)
_PLATE_ALLOWLIST = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-'
_OCR_MIN_CONF = 0.3   # confidence tối thiểu từ EasyOCR để chấp nhận ký tự
_OCR_TARGET_WIDTH = 240  # phóng to crop tới tối thiểu chừng này (px) trước khi OCR


def compute_blur_score(crop: np.ndarray) -> float:
    """Variance of Laplacian — số càng thấp càng mờ. Dùng để bỏ qua crop mờ
    TRƯỚC khi submit OCR (đỡ tốn 1 lượt OCR + đỡ đưa text rác vào vote), xem
    PLATE_MIN_BLUR_SCORE. Trả 0.0 cho input rỗng/lỗi (coi như mờ nhất)."""
    if crop is None or crop.size == 0:
        return 0.0
    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return 0.0


def _preprocess_plate_crop(crop: np.ndarray) -> np.ndarray:
    """Phóng to + tăng tương phản crop biển số trước khi đưa vào EasyOCR.

    Crop biển số thực tế thường chỉ rộng vài chục px trong ảnh gốc (camera
    xa, độ phân giải detect thấp) — EasyOCR đọc rất kém trên ảnh nhỏ/tương
    phản thấp. Phóng to bằng nội suy cubic + CLAHE (tăng tương phản cục bộ)
    cải thiện tỉ lệ đọc đúng mà không cần đổi engine OCR.
    """
    try:
        h, w = crop.shape[:2]
        scale = min(3.0, max(2.0, _OCR_TARGET_WIDTH / max(1, w)), 2048 / max(h, w))
        crop = cv2.resize(crop, (max(1, int(w * scale)), max(1, int(h * scale))),
                           interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        if gray.dtype != np.uint8:
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    except Exception:
        # Ảnh đầu vào bất thường (dtype lạ, corrupted...) — bỏ qua tiền xử lý,
        # để nguyên crop gốc cho EasyOCR (vốn đã tự catch lỗi riêng của nó).
        return crop


def plate_variants(crop: np.ndarray):
    """Two correlated variants at most; never synthesize missing characters."""
    yield 'original', _preprocess_plate_crop(crop)
    rectified = rectify_plate(crop)
    yield 'perspective_contrast' if rectified is not crop else 'bilateral_contrast', enhance_plate(rectified)


def is_two_line_plate(crop: np.ndarray) -> bool:
    """True nếu tỉ lệ width/height của crop gợi ý biển 2 dòng (gần vuông) —
    xem PLATE_TWO_LINE_MAX_ASPECT_RATIO. Đo trên crop GỐC (trước upscale, vì
    upscale giữ nguyên tỉ lệ nên không ảnh hưởng kết quả)."""
    from app.config import PLATE_TWO_LINE_MAX_ASPECT_RATIO
    if crop is None or crop.size == 0:
        return False
    h, w = crop.shape[:2]
    if h <= 0:
        return False
    return (w / h) < PLATE_TWO_LINE_MAX_ASPECT_RATIO


def split_two_line_plate(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cắt crop (đã tiền xử lý) thành 2 vùng trên/dưới với overlap nhẹ quanh
    giữa — overlap để không cắt đúng giữa ký tự nằm sát ranh giới 2 dòng."""
    h = crop.shape[0]
    top = crop[0:int(h * 0.56), :]
    bottom = crop[int(h * 0.44):, :]
    return top, bottom


def _ocr_region(reader, region: np.ndarray) -> tuple[str, float]:
    """OCR 1 vùng ảnh đã tiền xử lý — ghép các mảnh text trái→phải, trả
    (text đã normalize, confidence trung bình). Rỗng nếu không đọc được gì
    đủ tin. Dùng chung cho cả 2 vùng (top/bottom) của biển 2 dòng."""
    if region is None or region.size == 0:
        return '', 0.0
    results = reader.readtext(region, allowlist=_PLATE_ALLOWLIST, paragraph=False)
    parts = []
    confidences = []
    for bbox, text, conf in results:
        if conf < _OCR_MIN_CONF:
            continue
        normalized = normalize_plate(text)
        if normalized:
            avg_x = sum(p[0] for p in bbox) / len(bbox) if bbox else 0
            parts.append((normalized, avg_x))
            confidences.append(conf)
    parts.sort(key=lambda p: p[1])
    text = ''.join(p[0] for p in parts)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, avg_conf


# Lazy initialization của EasyOCR Reader
_reader = None
_reader_lock = threading.RLock()


def _get_reader():
    with _reader_lock:
        return _initialize_reader()


def _initialize_reader():
    """Lazy init EasyOCR Reader (tải trọng số lần đầu)."""
    global _reader
    if _reader is None:
        use_gpu = DEVICE == "cuda"
        print(f"[OCR] Đang khởi tạo EasyOCR Reader (lần đầu tải trọng số, gpu={use_gpu})...")
        # allowlist và paragraph KHÔNG phải tham số của Reader.__init__() — chúng
        # là tham số của readtext(). Việc truyền vào Reader() gây TypeError.
        # Đây là P0 fix: chỉ truyền các tham số hợp lệ của Reader.__init__().
        _reader = easyocr.Reader(
            ['en'],
            gpu=use_gpu,
            verbose=False,
        )
        print("[OCR] EasyOCR Reader đã sẵn sàng.")
    return _reader


def normalize_plate(text: str) -> str:
    """
    Chuẩn hóa chuỗi biển số:
    - Viết hoa
    - Bỏ khoảng trắng
    - Bỏ dấu gạch ngang
    - Bỏ các ký tự đặc biệt khác (chỉ giữ A-Z, 0-9)

    Args:
        text: Chuỗi thô từ OCR

    Returns:
        Chuỗi đã chuẩn hóa, hoặc empty string nếu không có ký tự hợp lệ
    """
    if not text:
        return ""

    # Viết hoa
    text = text.upper()

    # Seri xe máy điện "MĐ": Đ phải thành D (OCR không có Đ, đọc ra D), nếu
    # bị xóa thì biển đăng ký sẽ không bao giờ khớp biển camera đọc được.
    text = text.replace('Đ', 'D')

    # Chỉ giữ A-Z và 0-9
    text = re.sub(r'[^A-Z0-9]', '', text)

    return text


# Biển số VN sau khi normalize_plate (đã bỏ khoảng trắng/gạch ngang, chỉ còn A-Z0-9):
# 2 số tỉnh + series (chữ, chữ-số, hai chữ, hoặc hai chữ-số như "MĐ1" của
# xe máy điện) + 4–5 số.
# Live best-crop recognition requires a complete supported format before DB
# lookup. Uncommon formats remain unreadable/review rather than guessed.
_PLATE_FORMAT_RE = re.compile(r'^\d{2}(?:[A-Z]\d?|[A-Z]{2}\d?)\d{4,5}$')


def normalize_valid_plate(text, top='', bottom=''):
    """Correct only forced positions; refuse competing corrected formats."""
    text = normalize_plate(text)
    top, bottom = normalize_plate(top), normalize_plate(bottom)
    to_digit = {'O': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '6'}
    to_letter = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '6': 'G'}
    patterns = ['DD' + series + 'D'*n for series in ('A', 'AD', 'AA', 'AAD') for n in (4, 5)]
    if top and bottom:
        text = top + bottom
        patterns = [p for p in patterns if len(p)-len(bottom) == len(top) and len(bottom) in (4, 5)]
    matches = []
    for pattern in patterns:
        if len(pattern) != len(text):
            continue
        corrected, changes = [], 0
        for char, kind in zip(text, pattern):
            if (kind == 'D' and char.isdigit()) or (kind == 'A' and char.isalpha()):
                corrected.append(char)
            else:
                replacement = (to_digit if kind == 'D' else to_letter).get(char)
                if replacement is None:
                    break
                corrected.append(replacement); changes += 1
        else:
            value = ''.join(corrected)
            if validate_plate_format(value):
                matches.append((changes, value))
    if not matches:
        return ''
    minimum = min(n for n, _ in matches)
    values = {value for n, value in matches if n == minimum}
    return next(iter(values)) if len(values) == 1 else ''


def validate_plate_format(text: str) -> bool:
    """
    Kiểm tra chuỗi biển số (đã normalize) có khớp định dạng VN phổ biến không.

    Đây là kiểm tra cấu trúc, không chứng minh OCR đã đọc đúng biển thật.
    Format chưa hỗ trợ không được lookup hoặc tự kết luận chưa đăng ký.
    """
    if not text:
        return False
    return bool(_PLATE_FORMAT_RE.match(text))


def read_plate(crop: np.ndarray) -> str:
    """
    Đọc biển số từ ảnh crop đã cắt vùng biển số.

    Args:
        crop: Ảnh numpy array (BGR hoặc RGB), vùng biển số đã cắt

    Returns:
        Chuỗi biển số đã chuẩn hóa, hoặc empty string nếu không đọc được.
        Lỗi engine OCR được catch và trả empty string — không làm crash pipeline.
    """
    if crop is None or crop.size == 0:
        return ""

    reader = _get_reader()

    # Lấy kích thước
    h, w = crop.shape[:2]

    if h < 20 or w < 40:
        # Ảnh quá nhỏ, không đọc được
        return ""

    crop = _preprocess_plate_crop(crop)

    # EasyOCR đọc toàn bộ ảnh — truyền allowlist/paragraph vào readtext()
    try:
        results = reader.readtext(
            crop,
            allowlist=_PLATE_ALLOWLIST,
            paragraph=False,
        )
    except Exception:
        # Lỗi engine OCR (ví dụ: CUDA OOM, corrupted image) — không crash pipeline.
        # Biển không đọc được sẽ được phân biệt ở pipeline bằng trạng thái
        # "unreadable" khác với "plate not visible" (không có box biển).
        return ""

    if not results:
        return ""

    # Xử lý từng kết quả
    lines = []
    for bbox, text, conf in results:
        if conf < _OCR_MIN_CONF:  # Bỏ qua kết quả confidence thấp
            continue

        normalized = normalize_plate(text)
        if normalized:
            lines.append((normalized, conf, bbox[0][1] if bbox else 0))  # (text, conf, y_position)

    if not lines:
        return ""

    # Sắp xếp theo vị trí y (từ trên xuống)
    lines.sort(key=lambda x: x[2])

    # Ghép các dòng lại (xử lý cả biển 1 dòng và 2 dòng)
    # Biển số Việt Nam 2 dòng: dòng trên (4-5 ký tự), dòng dưới (5-7 ký tự)
    all_text = ''.join(line[0] for line in lines)

    return all_text


def read_plate_detailed(crop: np.ndarray) -> dict:
    import os
    if os.environ.get('PLATE_OCR_ENGINE', 'easyocr') == 'cct':
        from app.cv.fast_plate_ocr import configured_reader
        try:
            return configured_reader().read(crop)
        except Exception as exc:
            return {'full': '', 'confidence': 0.0, 'needs_review': True,
                    'engine': 'FastPlateOCR', 'error': f'ocr_engine_error:{type(exc).__name__}'}
    from app.cv.inference_worker import model_owner
    return model_owner().run('ocr', _read_easyocr_locked, crop)


def _read_easyocr_locked(crop):
    # Both cameras share EasyOCR's reader; serialize engine access, not capture.
    with _reader_lock:
        try:
            result = _read_plate_detailed(crop)
            result.update(engine='EasyOCR', raw_text=result.get('full', ''),
                          normalized_text=normalize_plate(result.get('full', '')), char_confidences=None)
            return result
        except Exception as exc:
            return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0,
                    'error': f'ocr_engine_error:{type(exc).__name__}'}


def _read_plate_detailed(crop: np.ndarray) -> dict:
    """
    Đọc biển số, trả về chi tiết hơn (gồm cả 2 dòng riêng).

    Args:
        crop: Ảnh numpy array, vùng biển số đã cắt

    Returns:
        dict với keys:
        - 'full': chuỗi ghép đầy đủ
        - 'top_line': dòng trên (nếu có)
        - 'bottom_line': dòng dưới (nếu có)
        - 'confidence': confidence trung bình

        Lỗi engine OCR được catch và trả dict rỗng — không làm crash pipeline.
    """
    if crop is None or crop.size == 0:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}

    h, w = crop.shape[:2]

    if h < 20 or w < 40:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}

    reader = _get_reader()
    attempts = []
    for name, prepared in plate_variants(crop):
        result = _read_prepared_plate(reader, prepared)
        if result.get('error'):
            return result  # An engine failure is technical, not an unreadable plate.
        attempts.append((name, result))
        if len(attempts) == 1 and name == 'original' and normalize_valid_plate(result['full']) and result['confidence'] >= .7:
            break
    valid = [(name, result) for name, result in attempts if normalize_valid_plate(result['full'])]
    name, result = max(valid or attempts, key=lambda item: item[1]['confidence'])
    result = dict(result, preprocessing=name, preprocessing_attempts=len(attempts))
    texts = {normalize_valid_plate(item['full']) for _, item in valid}
    if len(texts) > 1:
        # Variants are correlated observations of one crop, never extra votes.
        result.update(confidence=0.0, needs_review=True, candidate_texts=sorted(texts))
    elif len(attempts) > 1 and len(valid) < 2:
        # A single newly confident enhancement is insufficient to auto-accept.
        result.update(confidence=0.0, needs_review=True)
    return result


def _read_prepared_plate(reader, crop: np.ndarray) -> dict:
    """Read a prepared image without recursively preprocessing/retrying it."""
    # Biển 2 dòng (gần vuông): cắt riêng vùng trên/dưới rồi OCR RIÊNG từng
    # vùng — tránh EasyOCR gộp/lẫn thứ tự ký tự 2 dòng thành 1 chuỗi sai khi
    # biển mờ/nghiêng (lúc đó việc tự tách theo y-position của box detect bên
    # dưới không đáng tin). Geometry may change after perspective correction.
    two_line = is_two_line_plate(crop)
    h, w = crop.shape[:2]

    if two_line:
        top_region, bottom_region = split_two_line_plate(crop)
        top_line, top_conf = _ocr_region(reader, top_region)
        bottom_line, bottom_conf = _ocr_region(reader, bottom_region)
        return {
            'full': top_line + bottom_line,
            'top_line': top_line,
            'bottom_line': bottom_line,
            'confidence': min(top_conf, bottom_conf),
        }

    try:
        results = reader.readtext(
            crop,
            allowlist=_PLATE_ALLOWLIST,
            paragraph=False,
        )
    except Exception as exc:
        # Lỗi engine OCR — trả kết quả rỗng + đánh dấu error để R4 phân biệt
        # lỗi kỹ thuật (không tạo kết luận vi phạm) với OCR rỗng tự nhiên.
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0,
                'error': f'ocr_engine_error:{type(exc).__name__}'}

    if not results:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}

    # Phân tách dòng trên/dưới bằng vị trí y
    mid_y = h // 2

    top_parts = []
    bottom_parts = []
    confidences = []

    for bbox, text, conf in results:
        if conf < _OCR_MIN_CONF:
            continue

        # Lấy y trung bình (để tách dòng trên/dưới) và x trung bình (để sắp
        # xếp trái-phải trong cùng 1 dòng) của bbox
        ys = [p[1] for p in bbox]
        xs = [p[0] for p in bbox]
        avg_y = sum(ys) / len(ys)
        avg_x = sum(xs) / len(xs)

        normalized = normalize_plate(text)
        if normalized:
            confidences.append(conf)
            if avg_y < mid_y:
                top_parts.append((normalized, avg_x))
            else:
                bottom_parts.append((normalized, avg_x))

    # Sắp xếp theo x (trái sang phải)
    top_parts.sort(key=lambda x: x[1])
    bottom_parts.sort(key=lambda x: x[1])

    top_line = ''.join(p[0] for p in top_parts)
    bottom_line = ''.join(p[0] for p in bottom_parts)
    full = top_line + bottom_line

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        'full': full,
        'top_line': top_line,
        'bottom_line': bottom_line,
        'confidence': avg_conf
    }
