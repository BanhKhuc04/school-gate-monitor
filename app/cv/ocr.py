"""
OCR cho biển số xe Việt Nam.

- Chia đôi vùng crop (dòng trên/dưới cho biển 2 dòng)
- EasyOCR từng dòng
- Chuẩn hóa: viết hoa, bỏ khoảng trắng/gạch ngang
"""
import re
import numpy as np
import easyocr

from app.config import DEVICE


# Lazy initialization của EasyOCR Reader
_reader = None


def _get_reader():
    """Lazy init EasyOCR Reader (tải trọng số lần đầu)."""
    global _reader
    if _reader is None:
        use_gpu = DEVICE == "cuda"
        print(f"[OCR] Đang khởi tạo EasyOCR Reader (lần đầu tải trọng số, gpu={use_gpu})...")
        # 'en' cho ký tự Latin, có thể thêm 'vi' nếu cần
        _reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
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
    
    # Chỉ giữ A-Z và 0-9
    text = re.sub(r'[^A-Z0-9]', '', text)
    
    return text


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


def read_plate(crop: np.ndarray) -> str:
    """
    Đọc biển số từ ảnh crop đã cắt vùng biển số.
    
    Args:
        crop: Ảnh numpy array (BGR hoặc RGB), vùng biển số đã cắt
        
    Returns:
        Chuỗi biển số đã chuẩn hóa, hoặc empty string nếu không đọc được
    """
    if crop is None or crop.size == 0:
        return ""
    
    reader = _get_reader()
    
    # Lấy kích thước
    h, w = crop.shape[:2]
    
    if h < 20 or w < 40:
        # Ảnh quá nhỏ, không đọc được
        return ""
    
    # EasyOCR đọc toàn bộ ảnh
    results = reader.readtext(crop)
    
    if not results:
        return ""
    
    # Xử lý từng kết quả
    lines = []
    for bbox, text, conf in results:
        if conf < 0.3:  # Bỏ qua kết quả confidence thấp
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
    
    # Hoặc có thể trả về chuỗi ghép với khoảng trắng giữa các dòng
    # để giữ thông tin vị trí
    return all_text


def read_plate_detailed(crop: np.ndarray) -> dict:
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
    """
    if crop is None or crop.size == 0:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}
    
    reader = _get_reader()
    h, w = crop.shape[:2]
    
    if h < 20 or w < 40:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}
    
    results = reader.readtext(crop)
    
    if not results:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0}
    
    # Phân tách dòng trên/dưới bằng vị trí y
    mid_y = h // 2
    
    top_parts = []
    bottom_parts = []
    confidences = []
    
    for bbox, text, conf in results:
        if conf < 0.3:
            continue
        
        # Lấy y trung bình của bbox
        ys = [p[1] for p in bbox]
        avg_y = sum(ys) / len(ys)
        
        normalized = normalize_plate(text)
        if normalized:
            confidences.append(conf)
            if avg_y < mid_y:
                top_parts.append((normalized, avg_y))
            else:
                bottom_parts.append((normalized, avg_y))
    
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
