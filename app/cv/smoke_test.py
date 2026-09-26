"""
Smoke test: webcam + YOLOv8 detection + cv2.imshow.

Chạy: python -m app.cv.smoke_test

Quy tắc vẽ box:
- helmet:    xanh lá  (BGR: 0, 255, 0)
- no_helmet: đỏ      (BGR: 0, 0, 255)
- license-plate, motorcyclist, person, bike, motorcycle: vàng (BGR: 0, 255, 255)
"""
import sys
import os

# Thêm thư mục gốc vào path để import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import cv2
from app.cv.capture import WebcamStream
from app.cv.detector import HelmetPlateDetector


# Màu cho từng loại class
CLASS_COLORS = {
    'with helmet':       (0, 255, 0),    # xanh lá
    'without helmet':    (0, 0, 255),    # đỏ
    # Các class khác (license-plate, motorcyclist, person, bike, motorcycle...)
    'default':           (0, 255, 255),   # vàng
}


def get_color(class_name: str) -> tuple:
    """Lấy màu cho class."""
    return CLASS_COLORS.get(class_name.lower(), CLASS_COLORS['default'])


def draw_detections(frame, detections):
    """Vẽ bounding boxes, nhãn và % confidence lên frame."""
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        color = get_color(det.class_name)
        conf_pct = det.confidence * 100
        
        # Vẽ box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Vẽ nhãn
        label = f"{det.class_name} {conf_pct:.1f}%"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 8), (x1 + label_size[0], y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)


def main():
    # Đường dẫn model
    model_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'models', 'helmet_best.pt'
    )
    
    if not os.path.exists(model_path):
        print(f"LỖI: Không tìm thấy model tại: {model_path}")
        print("Vui lòng kiểm tra lại đường dẫn model.")
        sys.exit(1)
    
    print(f"Model: {model_path}")
    print("Đang khởi tạo detector...")
    
    try:
        detector = HelmetPlateDetector(model_path)
        print(f"Model loaded. Classes: {detector.class_names}")
    except Exception as e:
        print(f"LỖI khi load model: {e}")
        sys.exit(1)
    
    print("Đang mở webcam...")
    
    try:
        webcam = WebcamStream(source=0)
        print("Webcam mở thành công!")
    except Exception as e:
        print(f"LỖI khi mở webcam: {e}")
        sys.exit(1)
    
    print("\n=== Hướng dẫn ===")
    print("- Nhấn 'q' để thoát")
    print("- Cửa sổ hiển thị sẽ xuất hiện")
    print("================\n")
    
    try:
        while True:
            # Đọc frame
            frame = webcam.read_frame()
            
            # Phát hiện objects
            detections = detector.detect(frame)
            
            # Vẽ bounding boxes
            draw_detections(frame, detections)
            
            # Hiển thị
            cv2.imshow("Helmet Detection - Press 'q' to quit", frame)
            
            # Thoát khi nhấn 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        print("\nĐang dừng...")
    except Exception as e:
        print(f"LỖI trong vòng lặp: {e}")
    finally:
        webcam.release()
        cv2.destroyAllWindows()
        print("Đã giải phóng tài nguyên.")


if __name__ == '__main__':
    main()
