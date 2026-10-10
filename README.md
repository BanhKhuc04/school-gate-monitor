# Hệ thống giám sát cổng trường — React SPA

Phát hiện mũ bảo hiểm + nhận diện biển số xe máy tại cổng trường học, dùng webcam và YOLOv8, giao diện React SPA với đăng nhập phân quyền.

## Tiến độ phát triển hiện tại

**Đã xong (chạy được):**
- Pipeline nhận diện: người (COCO) → mũ bảo hiểm → biển số (YOLOv8n) → OCR (EasyOCR) → tra whitelist → ghi log vi phạm.
- Phát hiện tư thế (YOLOv8-pose): phân biệt đi bộ vs đang ngồi trên xe, để bắt lỗi `RIDING_THROUGH_GATE`.
- Lọc người đi bộ / xe đạp thường khỏi luật bắt mũ + biển số (chỉ áp dụng cho xe máy).
- Auth JWT phân quyền 3 role (admin / security / management), CRUD xe đăng ký, quản lý user, thống kê dashboard, dọn ảnh vi phạm cũ.
- Giao diện đã restyle theo design "Vanguard Campus Security" (landing page, login).

**Đang làm dở (WIP):**
- Restyle `GuardPage` (trang bảo vệ xem camera + cảnh báo) theo design system mới — **còn bug đã biết: cảnh báo WebSocket (`/guard/ws`) không hiển thị lên UI**, đang sửa ở `app/api/guard.py` (xem `git status`/commit `3c19125`).

**Đã bỏ:**
- **Nhận diện khuôn mặt** — gỡ hoàn toàn (commit `d4d8dc4`): mở khẩu trang không đeo mặt nạ vẫn xâm phạm dữ liệu sinh trắc học trẻ vị thành niên, rủi ro pháp lý không đáng đánh đổi. Không còn `app/api/faces.py`, `app/cv/face.py`, bảng `face_embeddings`/`face_match_events`, trang `AdminFacesPage`.

**Chưa làm (kế hoạch, chưa có code):**
- Chạy 2 camera song song (cổng vào/cổng ra) — hiện pipeline chỉ đọc **1 nguồn camera duy nhất** (`CAMERA_SOURCE` trong `app/config.py`), chưa có route/logic phân biệt hướng vào/ra.
- Deploy lên VPS (103.101.162.111, 1 vCPU/1GB/15GB) — VPS mới có, chưa cấu hình gì; kế hoạch là chỉ host API + DB + frontend static, inference vẫn chạy ở máy edge tại chỗ.
- Mua/lắp camera IP thật tại cổng — đang khảo giá (Hikvision dòng IP "CD", Imou), chưa chốt.
- Chưa fine-tune lại model helmet/plate/OCR bằng dữ liệu thật của trường (đang dùng model pretrained public, xem mục "Loại vi phạm" & giới hạn model bên dưới).

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

Model `models/yolov8n.pt` (person COCO) và `yolov8n-pose.pt` (tư thế đi bộ vs ngồi xe) sẽ tự tải lần đầu khi chạy (cần internet, ~6MB).

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
| `/guard` | security, admin | Camera MJPEG + AlertBanner (cảnh báo thời gian thực) — **đang có bug WS, xem "Tiến độ phát triển"** |
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
| `/guard/video_feed` | GET | security, admin | MJPEG stream (query: `?token=`) |
| `/guard/ws` | WS | security, admin | WebSocket cảnh báo (query: `?token=`) — **bug đang sửa: alert không tới UI** |
| `/api/dev/trigger-test-alert` | POST | security, admin | Giả lập cảnh báo vi phạm (test) |
| `/media/{file}` | GET | any | Ảnh snapshot vi phạm |

## Kiến trúc

- **Frontend**: React 18 + Vite + Tailwind + React Router + axios + recharts
- **Backend**: FastAPI, xử lý webcam trong thread nền riêng
- **Video streaming**: MJPEG (`/guard/video_feed`)
- **Cảnh báo**: WebSocket + AlertBanner (banner đỏ vi phạm + beep 800Hz)
- **Detection**: YOLOv8 (helmet + plate + person COCO) + EasyOCR + YOLOv8-pose (tư thế: <140° riding, >160° standing)
- **Auth**: JWT (12h), bcrypt password hash
- **Lưu trữ**: SQLite (data/app.db), ảnh vi phạm (`data/snapshots/`)
- **Test**: pytest (`app/tests/`) + Playwright E2E (`frontend/e2e/`)

## Loại vi phạm

| Code | Mô tả |
|------|--------|
| `NO_HELMET` | Không đội mũ bảo hiểm |
| `PLATE_NOT_REGISTERED` | Biển số không có trong danh sách đăng ký |
| `PLATE_UNREADABLE` | Không đọc được biển số |
| `MULTIPLE` | Nhiều loại vi phạm cùng lúc |
| `RIDING_THROUGH_GATE` | Người ngồi trên xe đi qua cổng (tư thế riding + có mũ) |
