# Hệ thống giám sát cổng trường — MVP

Phát hiện mũ bảo hiểm + nhận diện biển số xe máy tại cổng trường học, dùng webcam và YOLOv8.

## Yêu cầu

- Python 3.9+
- pip

## Setup

```bash
# Tạo virtual environment
python -m venv venv
.\venv\Scripts\activate

# Cài dependencies
pip install -r requirements.txt
```

## Tải model

Trước khi chạy, cần tải 2 file model vào thư mục `models/`:

| File | Nguồn |
|------|-------|
| `models/helmet_best.pt` | [iam-tsr/yolov8n-helmet-detection](https://huggingface.co/iam-tsr/yolov8n-helmet-detection) |
| `models/plate_best.pt` | [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection) |

> Tải file `.pt` (weights) từ Hugging Face → đặt vào thư mục `models/`

## Chạy

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Mở trình duyệt:

| Route | Mô tả |
|-------|--------|
| `http://localhost:8000/guard` | Camera trực tiếp + cảnh báo vi phạm qua WebSocket |
| `http://localhost:8000/admin` | Quản lý danh sách xe đăng ký |
| `http://localhost:8000/admin/violations` | Xem lịch sử vi phạm kèm ảnh snapshot |

## Kiến trúc

- **Backend**: FastAPI, xử lý webcam trong thread nền riêng
- **Video streaming**: MJPEG (`/guard/video_feed`)
- **Cảnh báo**: WebSocket (`/guard/ws`), phát beep + banner đỏ ở frontend
- **Detection**: YOLOv8 (helmet + plate detection) + EasyOCR (đọc biển số)
- **Lưu trữ**: SQLite (`data/app.db`), ảnh vi phạm (`data/snapshots/`)

## MVP đã có

- Phát hiện mũ bảo hiểm (With Helmet / Without Helmet)
- Phát hiện vùng biển số
- OCR đọc biển số (EasyOCR)
- Tra whitelist biển số đã đăng ký
- Ghi log vi phạm vào DB kèm ảnh snapshot
- Cảnh báo real-time qua WebSocket
- Admin CRUD quản lý xe đăng ký
