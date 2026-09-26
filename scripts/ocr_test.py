"""
Test OCR trên ảnh biển số mẫu.

Chạy: python scripts/ocr_test.py

Ảnh mẫu: data/samples/plates/*.jpg (hoặc *.png)
Kết quả: In ra chuỗi OCR cho từng ảnh.
"""
import sys
import os

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cv2
from app.cv.ocr import read_plate, read_plate_detailed


def find_plate_images():
    """Tìm tất cả ảnh trong data/samples/plates/."""
    plates_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'data', 'samples', 'plates'
    )
    
    if not os.path.exists(plates_dir):
        return []
    
    extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    images = []
    
    for fname in os.listdir(plates_dir):
        ext = os.path.splitext(fname)[1].lower()
        if ext in extensions:
            images.append(os.path.join(plates_dir, fname))
    
    return sorted(images)


def main():
    print("=" * 60)
    print("OCR Test - License Plate Recognition")
    print("=" * 60)
    
    # Tìm ảnh mẫu
    images = find_plate_images()
    
    if not images:
        print("\n[WARNING] Không tìm thấy ảnh nào trong data/samples/plates/")
        print("Vui lòng thêm ảnh biển số vào thư mục đó.")
        print("Hỗ trợ: .jpg, .jpeg, .png, .bmp")
        print()
        print("Hoặc chạy thử với 1 ảnh cụ thể:")
        print("  python scripts/ocr_test.py <đường_dẫn_ảnh>")
        return
    
    print(f"\nTìm thấy {len(images)} ảnh:\n")
    
    for i, img_path in enumerate(images, 1):
        print("-" * 60)
        print(f"[{i}/{len(images)}] {os.path.basename(img_path)}")
        
        # Đọc ảnh
        img = cv2.imread(img_path)
        if img is None:
            print(f"  [ERROR] Không đọc được ảnh")
            continue
        
        h, w = img.shape[:2]
        print(f"  Kích thước: {w}x{h}")
        
        # OCR đơn giản
        result = read_plate(img)
        print(f"  Kết quả OCR: '{result}'")
        
        # OCR chi tiết
        detailed = read_plate_detailed(img)
        if detailed['confidence'] > 0:
            print(f"  Dòng trên:  '{detailed['top_line']}'")
            print(f"  Dòng dưới: '{detailed['bottom_line']}'")
            print(f"  Confidence:  {detailed['confidence']:.2%}")
        
        print()
    
    print("=" * 60)
    print("Test hoàn tất!")


if __name__ == '__main__':
    # Cho phép chạy với 1 ảnh cụ thể làm argument
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        print(f"Testing single image: {img_path}\n")
        
        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Không đọc được ảnh: {img_path}")
            sys.exit(1)
        
        print(f"Ảnh: {img_path}")
        print(f"Kích thước: {img.shape[1]}x{img.shape[0]}\n")
        
        result = read_plate(img)
        print(f"Kết quả OCR: '{result}'")
        
        detailed = read_plate_detailed(img)
        if detailed['confidence'] > 0:
            print(f"Dòng trên:  '{detailed['top_line']}'")
            print(f"Dòng dưới: '{detailed['bottom_line']}'")
            print(f"Confidence:  {detailed['confidence']:.2%}")
    else:
        main()
