"""
OCR cho biển số xe Việt Nam.

2 engine, chọn tự động:
- YOLO đọc từng ký tự (models/plate_ocr_best.pt, train bằng scripts/train_all.py
  trên datasets/plate_char_ocr) — chính xác hơn hẳn với biển xe máy 2 dòng. Chỉ
  dùng khi file model tồn tại.
- EasyOCR — luôn có sẵn, dùng làm dự phòng khi chưa train model ký tự hoặc model
  ký tự đọc ra chuỗi sai định dạng.

Các bước chung: phóng to crop nhỏ → đọc → gom box thành dòng (trên/dưới) và xếp
trái→phải trong từng dòng → chuẩn hóa (A-Z0-9) → sửa ký tự nhầm theo vị trí
(O↔0, I↔1, B↔8...) khi việc sửa giúp chuỗi khớp định dạng biển số VN.
"""
import os
import re
import threading

import cv2
import numpy as np

from app.config import DEVICE, PLATE_OCR_MODEL_PATH


# Lazy initialization của EasyOCR Reader
_reader = None
_reader_lock = threading.Lock()

# Ký tự có thể xuất hiện trên biển số (gồm '-' '.' để EasyOCR không phải "ép"
# dấu gạch/chấm thành 1 chữ cái — normalize_plate sẽ bỏ chúng đi sau đó).
# Bỏ I, J, O, Q, R, W: biển số dân sự VN không dùng các chữ này, và chúng là
# nguồn nhầm lẫn chính với 1/0.
_EASYOCR_ALLOWLIST = "0123456789ABCDEFGHKLMNPSTUVXYZ-."

# Crop biển số nhỏ hơn chiều cao này sẽ được phóng to trước khi OCR — biển xe máy
# ở camera cổng trường thường chỉ cao 25-50px, quá nhỏ cho bước dò chữ của EasyOCR.
_OCR_TARGET_HEIGHT = 160
# Nhỏ hơn mức này thì không còn đủ thông tin để đọc, bỏ qua luôn.
MIN_PLATE_CROP_HEIGHT = 12
MIN_PLATE_CROP_WIDTH = 20


def _get_reader():
    """Lazy init EasyOCR Reader (tải trọng số lần đầu)."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                use_gpu = DEVICE == "cuda"
                print(f"[OCR] Đang khởi tạo EasyOCR Reader (lần đầu tải trọng số, gpu={use_gpu})...")
                _reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
                print("[OCR] EasyOCR Reader đã sẵn sàng.")
    return _reader


def normalize_plate(text: str) -> str:
    """Viết hoa, chỉ giữ A-Z và 0-9 (bỏ khoảng trắng, gạch ngang, dấu chấm...)."""
    if not text:
        return ""
    return re.sub(r'[^A-Z0-9]', '', text.upper())


# Biển số VN sau khi normalize_plate (đã bỏ khoảng trắng/gạch ngang, chỉ còn A-Z0-9):
# 2 số tỉnh + 1-2 chữ (series) + 4-6 số. Bao quát cả 1 dòng và 2 dòng ghép lại,
# biển thường (1 chữ) và biển mới/rơ-moóc/điện (đôi khi 2 chữ) — cố ý rộng vì
# đây chỉ dùng để GẮN CỜ nghi ngờ, không dùng để loại bỏ kết quả OCR.
_PLATE_FORMAT_RE = re.compile(r'^\d{2}[A-Z]{1,2}\d{4,6}$')


def validate_plate_format(text: str) -> bool:
    """
    Kiểm tra chuỗi biển số (đã normalize) có khớp định dạng VN phổ biến không.

    Đây chỉ là một cờ tham khảo cho bảo vệ xem lại — không dùng để loại bỏ
    kết quả OCR, vì biển số hiếm (rơ-moóc, xe điện, ngoại giao...) có thể
    không khớp regex này dù vẫn là biển thật.
    """
    if not text:
        return False
    return bool(_PLATE_FORMAT_RE.match(text))


# Nhầm lẫn hình dạng hay gặp của OCR: chữ ↔ số
_TO_DIGIT = {'O': '0', 'D': '0', 'Q': '0', 'U': '0', 'I': '1', 'J': '1', 'L': '1',
             'T': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '6', 'A': '4'}
_TO_LETTER = {'0': 'D', '8': 'B', '5': 'S', '2': 'Z', '6': 'G', '4': 'A', '1': 'T', '7': 'T'}


def correct_plate_text(text: str) -> str:
    """Sửa ký tự nhầm theo vị trí trong biển số VN: 2 ký tự đầu là số (mã tỉnh),
    ký tự thứ 3 là chữ (series), từ ký tự thứ 5 trở đi là số. Ký tự thứ 4 có thể
    là chữ hoặc số (series 2 chữ / series chữ+số) — chỉ sửa I/O (không bao giờ là
    chữ trên biển) về số.

    Chỉ trả về bản đã sửa khi bản đó khớp định dạng mà bản gốc thì không — không
    bao giờ làm hỏng một chuỗi vốn đã hợp lệ.
    """
    if not text or validate_plate_format(text) or not 7 <= len(text) <= 10:
        return text
    chars = list(text)
    for i in (0, 1):
        chars[i] = _TO_DIGIT.get(chars[i], chars[i])
    chars[2] = _TO_LETTER.get(chars[2], chars[2])
    if chars[3] in ('I', 'O'):
        chars[3] = _TO_DIGIT[chars[3]]
    for i in range(4, len(chars)):
        chars[i] = _TO_DIGIT.get(chars[i], chars[i])
    candidate = ''.join(chars)
    return candidate if validate_plate_format(candidate) else text


def group_into_lines(boxes: list[tuple[str, float, float, float, float]]) -> list[str]:
    """Gom các box (text, conf, cx, cy, h) thành dòng theo trục Y, xếp trái→phải
    trong từng dòng, trả về text từng dòng từ trên xuống.

    1 box thuộc dòng hiện tại nếu tâm Y lệch không quá nửa chiều cao box — đủ
    phân biệt 2 dòng của biển xe máy (cách nhau ~1 chiều cao ký tự) nhưng vẫn
    giữ chung 1 dòng khi box hơi lệch nhau do biển nghiêng.
    """
    if not boxes:
        return []
    lines: list[list[tuple]] = []
    for box in sorted(boxes, key=lambda b: b[3]):
        if lines:
            line = lines[-1]
            line_cy = sum(b[3] for b in line) / len(line)
            line_h = max(b[4] for b in line)
            if abs(box[3] - line_cy) <= 0.5 * max(line_h, box[4]):
                line.append(box)
                continue
        lines.append([box])
    return [''.join(b[0] for b in sorted(line, key=lambda b: b[2])) for line in lines]


def _prepare_crop(crop: np.ndarray) -> np.ndarray | None:
    """Bỏ crop quá nhỏ; phóng to crop nhỏ lên ~_OCR_TARGET_HEIGHT px."""
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    if h < MIN_PLATE_CROP_HEIGHT or w < MIN_PLATE_CROP_WIDTH:
        return None
    if h < _OCR_TARGET_HEIGHT:
        scale = _OCR_TARGET_HEIGHT / h
        crop = cv2.resize(crop, (round(w * scale), _OCR_TARGET_HEIGHT), interpolation=cv2.INTER_CUBIC)
    return crop


def _empty_result() -> dict:
    return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}


def _result_from_lines(lines: list[str], confidences: list[float]) -> dict:
    top_line = lines[0] if lines else ''
    bottom_line = ''.join(lines[1:])
    full = correct_plate_text(normalize_plate(top_line + bottom_line))
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return {'full': full, 'top_line': top_line, 'bottom_line': bottom_line, 'confidence': avg_conf}


def _read_with_easyocr(crop: np.ndarray) -> dict:
    results = _get_reader().readtext(crop, allowlist=_EASYOCR_ALLOWLIST)
    boxes = []
    confidences = []
    for bbox, text, conf in results:
        if conf < 0.3:
            continue
        normalized = normalize_plate(text)
        if not normalized:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        boxes.append((normalized, conf, sum(xs) / len(xs), sum(ys) / len(ys), max(ys) - min(ys)))
        confidences.append(conf)
    if not boxes:
        return _empty_result()
    return _result_from_lines(group_into_lines(boxes), confidences)


# ─── YOLO đọc từng ký tự (tùy chọn — chỉ khi đã train models/plate_ocr_best.pt) ──

_char_model = None
_char_model_lock = threading.Lock()
_char_model_failed = False


def _get_char_model():
    global _char_model, _char_model_failed
    if _char_model is None and not _char_model_failed and os.path.exists(PLATE_OCR_MODEL_PATH):
        with _char_model_lock:
            if _char_model is None and not _char_model_failed:
                try:
                    from ultralytics import YOLO
                    model = YOLO(PLATE_OCR_MODEL_PATH)
                    model.to(DEVICE)
                    _char_model = model
                    print(f"[OCR] Dùng model đọc ký tự {PLATE_OCR_MODEL_PATH} (device={DEVICE})")
                except Exception as e:
                    _char_model_failed = True
                    print(f"[OCR] Không nạp được model ký tự ({e}) — dùng EasyOCR")
    return _char_model


def _read_with_char_model(model, crop: np.ndarray) -> dict:
    results = model(crop, imgsz=320, conf=0.35, verbose=False, half=DEVICE == "cuda")
    boxes = []
    confidences = []
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            name = str(model.names.get(int(box.cls.item()), ''))
            char = normalize_plate(name)
            if len(char) != 1:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf.item())
            boxes.append((char, conf, (x1 + x2) / 2, (y1 + y2) / 2, y2 - y1))
            confidences.append(conf)
    if not boxes:
        return _empty_result()
    return _result_from_lines(group_into_lines(boxes), confidences)


def read_plate_detailed(crop: np.ndarray) -> dict:
    """
    Đọc biển số từ crop vùng biển số.

    Returns:
        dict: 'full' (chuỗi đã chuẩn hóa, '' nếu không đọc được), 'top_line',
        'bottom_line', 'confidence' (0.0-1.0)
    """
    crop = _prepare_crop(crop)
    if crop is None:
        return _empty_result()

    char_model = _get_char_model()
    if char_model is not None:
        try:
            result = _read_with_char_model(char_model, crop)
            if validate_plate_format(result['full']):
                return result
        except Exception as e:
            print(f"[OCR] Lỗi model ký tự, chuyển sang EasyOCR: {e}")

    return _read_with_easyocr(crop)


def read_plate(crop: np.ndarray) -> str:
    """Đọc biển số, chỉ trả về chuỗi đã chuẩn hóa ('' nếu không đọc được)."""
    return read_plate_detailed(crop)['full']


def warm_up() -> None:
    """Nạp sẵn engine OCR (gọi ở thread nền lúc khởi động) để lần đọc biển số
    đầu tiên khi có xe không bị chậm vài giây do tải/khởi tạo model."""
    try:
        _get_char_model()
        reader = _get_reader()
        reader.readtext(np.full((64, 160, 3), 255, dtype=np.uint8))
    except Exception as e:
        print(f"[OCR] Warm-up thất bại (sẽ thử lại khi đọc biển số đầu tiên): {e}")
