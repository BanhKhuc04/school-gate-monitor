# Hệ thống giám sát cổng trường — React SPA

Phát hiện mũ bảo hiểm + nhận diện biển số xe máy tại cổng trường học, dùng webcam và YOLOv8, giao diện React SPA với đăng nhập phân quyền.

## Yêu cầu

- Python 3.9+
- Node.js 18+

## Setup

```bash
# Backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Tải model

Trước khi chạy, tải 2 file model vào thư mục `models/`:

| File | Nguồn |
|------|-------|
| `models/helmet_best.pt` | [iam-tsr/yolov8n-helmet-detection](https://huggingface.co/iam-tsr/yolov8n-helmet-detection) |
| `models/plate_best.pt` | [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection) |

## Chạy (Development)

```bash
# Terminal 1: Backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

Mở trình duyệt: `http://localhost:5173`

## Chạy (Production — một process duy nhất)

```bash
cd frontend && npm run build && cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mở trình duyệt: `http://localhost:8000`

## Users (seed mặc định)

| Username | Password | Role | Mô tả |
|----------|----------|------|--------|
| `admin` | `admin123` | admin | CRUD xe, xem vi phạm, xem camera |
| `security` | `security123` | security | Xem camera + cảnh báo |
| `management` | `management123` | management | Xem dashboard thống kê |

## Routes (React SPA)

| Route | Role | Mô tả |
|-------|------|--------|
| `/` | — | Redirect → login |
| `/login` | — | Đăng nhập |
| `/admin/vehicles` | admin | CRUD xe đăng ký |
| `/admin/violations` | admin | Bảng vi phạm + ảnh snapshot |
| `/guard` | security, admin | Camera MJPEG + AlertBanner |
| `/dashboard` | management, admin | KPI + biểu đồ thống kê |

## API Routes (JSON)

| Route | Method | Role | Mô tả |
|-------|--------|------|--------|
| `/api/auth/login` | POST | — | Đăng nhập, trả JWT |
| `/api/auth/me` | GET | any | Thông tin user hiện tại |
| `/api/vehicles` | GET/POST | admin | List/thêm xe |
| `/api/vehicles/{id}` | PUT/DELETE | admin | Sửa/xóa xe |
| `/api/violations` | GET | admin | Danh sách vi phạm |
| `/api/stats/summary` | GET | management, admin | Thống kê vi phạm |
| `/guard/video_feed` | GET | security, admin | MJPEG stream (query: `?token=`) |
| `/guard/ws` | WS | security, admin | WebSocket cảnh báo (query: `?token=`) |
| `/media/{file}` | GET | any | Ảnh snapshot vi phạm |

## Kiến trúc

- **Frontend**: React 18 + Vite + Tailwind + React Router + axios + recharts
- **Backend**: FastAPI, xử lý webcam trong thread nền riêng
- **Video streaming**: MJPEG (`/guard/video_feed`)
- **Cảnh báo**: WebSocket + AlertBanner (banner đỏ + beep)
- **Detection**: YOLOv8 (helmet + plate) + EasyOCR
- **Auth**: JWT (12h), bcrypt password hash
- **Lưu trữ**: SQLite, ảnh vi phạm (`data/snapshots/`)
