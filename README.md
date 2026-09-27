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
|------|--------|
| `models/helmet_best.pt` | [iam-tsr/yolov8n-helmet-detection](https://huggingface.co/iam-tsr/yolov8n-helmet-detection) |
| `models/plate_best.pt` | [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection) |

Model `models/yolov8n.pt` (person COCO) sẽ tự tải lần đầu khi chạy.

Ngoài ra, 2 model AI nặng được tự động tải lần đầu khi chạy (cần internet):
- **insightface** (`buffalo_l`): nhận diện khuôn mặt — tự tải ~30MB
- **YOLOv8-pose** (`yolov8n-pose.pt`): phát hiện tư thế đi bộ vs ngồi xe — tự tải ~6MB

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
| `admin` | `admin123` | admin | CRUD xe, xem vi phạm, quản lý tài khoản, sức khỏe hệ thống |
| `security` | `security123` | security | Xem camera + cảnh báo |
| `management` | `management123` | management | Xem dashboard thống kê |

## Routes (React SPA)

| Route | Role | Mô tả |
|-------|------|--------|
| `/` | — | Redirect → login |
| `/login` | — | Đăng nhập |
| `/admin/vehicles` | admin | CRUD xe đăng ký + import CSV |
| `/admin/violations` | admin | Bảng vi phạm + ảnh snapshot + lọc + phân trang |
| `/admin/users` | admin | Quản lý tài khoản (CRUD user) |
| `/admin/health` | admin | Trạng thái pipeline + lưu trữ + dọn ảnh cũ |
| `/admin/faces` | admin | Quản lý khuôn mặt (đăng ký/enroll, danh sách, sự kiện nhận diện) |
| `/guard` | security, admin | Camera MJPEG + AlertBanner (cảnh báo thời gian thực) |
| `/dashboard` | management, admin | KPI + biểu đồ thống kê |

## API Routes (JSON)

| Route | Method | Role | Mô tả |
|-------|--------|------|--------|
| `/api/auth/login` | POST | — | Đăng nhập, trả JWT |
| `/api/auth/me` | GET | any | Thông tin user hiện tại |
| `/api/vehicles` | GET/POST | admin | List/thêm xe |
| `/api/vehicles/{id}` | PUT/DELETE | admin | Sửa/xóa xe |
| `/api/vehicles/import` | POST | admin | Import hàng loạt từ CSV |
| `/api/violations` | GET | admin | Danh sách vi phạm (lọc + phân trang) |
| `/api/users` | GET/POST | admin | List/tạo user |
| `/api/users/{id}` | PUT/DELETE | admin | Sửa/xóa user |
| `/api/stats/summary` | GET | management, admin | Thống kê vi phạm |
| `/api/system/health` | GET | admin, management | Trạng thái pipeline + storage |
| `/api/system/snapshots/cleanup` | POST | admin | Dọn ảnh vi phạm cũ |
| `/api/faces` | GET | admin | Danh sách khuôn mặt đã đăng ký |
| `/api/faces/enroll` | POST | admin | Đăng ký khuôn mặt mới (upload ảnh) |
| `/api/faces/{id}` | DELETE | admin | Xóa khuôn mặt |
| `/api/faces/events` | GET | admin, management | Sự kiện nhận diện gần nhất |
| `/guard/video_feed` | GET | security, admin | MJPEG stream (query: `?token=`) |
| `/guard/ws` | WS | security, admin | WebSocket cảnh báo (query: `?token=`) |
| `/api/dev/trigger-test-alert` | POST | security, admin | Giả lập cảnh báo vi phạm (test) |
| `/api/dev/trigger-test-face-match` | POST | security, admin | Giả lập cảnh báo nhận diện khuôn mặt (test) |
| `/media/{file}` | GET | any | Ảnh snapshot vi phạm |

## Kiến trúc

- **Frontend**: React 18 + Vite + Tailwind + React Router + axios + recharts
- **Backend**: FastAPI, xử lý webcam trong thread nền riêng
- **Video streaming**: MJPEG (`/guard/video_feed`)
- **Cảnh báo**: WebSocket + AlertBanner (banner đỏ vi phạm + banner amber nhận diện khuôn mặt + beep 800Hz)
- **Detection**: YOLOv8 (helmet + plate + person COCO) + EasyOCR + insightface (khuôn mặt cosine sim ≥0.40) + YOLOv8-pose (tư thế: <140° riding, >160° standing)
- **Auth**: JWT (12h), bcrypt password hash
- **Lưu trữ**: SQLite (data/app.db), ảnh vi phạm (`data/snapshots/`), khuôn mặt đăng ký (trong app.db)
- **Test**: pytest (`app/tests/`) + Playwright E2E (`frontend/e2e/`)

## Loại vi phạm

| Code | Mô tả |
|------|--------|
| `NO_HELMET` | Không đội mũ bảo hiểm |
| `PLATE_NOT_REGISTERED` | Biển số không có trong danh sách đăng ký |
| `PLATE_UNREADABLE` | Không đọc được biển số |
| `MULTIPLE` | Nhiều loại vi phạm cùng lúc |
| `RIDING_THROUGH_GATE` | Người ngồi trên xe đi qua cổng (tư thế riding + có mũ) |
