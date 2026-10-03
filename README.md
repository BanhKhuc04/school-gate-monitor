# Hệ thống giám sát cổng trường — React SPA

Phát hiện mũ bảo hiểm + nhận diện biển số xe máy tại cổng trường học, dùng webcam và YOLOv8, giao diện React SPA với đăng nhập phân quyền.

## License

[AGPL-3.0](LICENSE). Dự án dùng [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) (chính nó cũng license AGPL-3.0) — nếu phát hành bản sửa đổi của dự án này dưới dạng dịch vụ mạng (SaaS) mà không public source, hoặc muốn phân phối dưới license khác (vd. thương mại hóa đóng nguồn), cần mua [Ultralytics Enterprise License](https://ultralytics.com/license) để không bị ràng buộc điều khoản copyleft của AGPL.

## Tiến độ phát triển hiện tại

**Đã xong (chạy được):**
- Pipeline nhận diện: người (COCO) → mũ bảo hiểm → biển số (YOLOv8n) → OCR (EasyOCR) → tra whitelist → ghi log vi phạm.
- Phát hiện tư thế (YOLOv8-pose): phân biệt đi bộ vs đang ngồi trên xe, để bắt lỗi `RIDING_THROUGH_GATE`.
- Lọc người đi bộ / xe đạp thường khỏi luật bắt mũ + biển số (chỉ áp dụng cho xe máy).
- Auth JWT phân quyền 3 role (admin / security / management), CRUD xe đăng ký, quản lý user, thống kê dashboard, dọn ảnh vi phạm cũ.
- Giao diện đã restyle theo design "Vanguard Campus Security" (landing page, login).

**Đã sửa (trước đây ghi là "bug đã biết"):**
- `/guard/ws` cảnh báo không tới client: đã thêm test tự động `app/tests/test_guard_ws.py` tái hiện đúng kịch bản điều tra trong `HANDOFF_CURSOR.md` (1 client, 2 client đồng thời + trigger dồn dập) — cả hai đều PASS với code hiện tại. Nhân tiện sửa 2 vấn đề thật tìm thấy trong `app/api/guard.py`: (1) thiếu try/except quanh `decode_access_token` khiến token hết hạn/sai làm WS đóng đột ngột không rõ lý do; (2) `_clients_lock` dùng `threading.Lock` (blocking thật) thay vì `asyncio.Lock` trong code async — tiềm ẩn treo cứng event loop nếu 2 client broadcast trùng lúc. Nếu vẫn gặp alert không hiện trên UI thật, nhiều khả năng do nguyên nhân khác (nhiều process backend chạy song song trên cùng port, trình duyệt cụ thể) — báo lại kèm bước tái hiện để điều tra tiếp.

**Đã bỏ:**
- **Nhận diện khuôn mặt** — gỡ hoàn toàn (commit `d4d8dc4`): mở khẩu trang không đeo mặt nạ vẫn xâm phạm dữ liệu sinh trắc học trẻ vị thành niên, rủi ro pháp lý không đáng đánh đổi. Không còn `app/api/faces.py`, `app/cv/face.py`, bảng `face_embeddings`/`face_match_events`, trang `AdminFacesPage`.

**Chưa làm (kế hoạch, chưa có code):**
- Chạy 2 camera song song (cổng vào/cổng ra) — hiện pipeline chỉ đọc **1 nguồn camera duy nhất** (`CAMERA_SOURCE` trong `app/config.py`), chưa có route/logic phân biệt hướng vào/ra.
- Deploy lên VPS (103.101.162.111, 1 vCPU/1GB/15GB) — VPS mới có, chưa cấu hình gì; kế hoạch là chỉ host API + DB + frontend static, inference vẫn chạy ở máy edge tại chỗ.
- Mua/lắp camera IP thật tại cổng — đang khảo giá (Hikvision dòng IP "CD", Imou), chưa chốt.
- OCR (EasyOCR) và model helmet vẫn dùng pretrained public, chưa fine-tune bằng dữ liệu thật của trường (model plate đã fine-tune, xem mục "Model" bên trên).

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

## Model

`models/helmet_best.pt` và `models/plate_best.pt` đã nằm sẵn trong repo (clone
về là chạy được ngay, không cần tải thêm) — đây là 2 file model **dành riêng
cho dự án**, không phải bản pretrained public gốc:
- `helmet_best.pt`: bản pretrained gốc từ [iam-tsr/yolov8n-helmet-detection](https://huggingface.co/iam-tsr/yolov8n-helmet-detection) (thử fine-tune lại trên dữ liệu thật nhưng kết quả tệ hơn nên giữ nguyên bản gốc, xem commit `d631432`).
- `plate_best.pt`: **đã fine-tune** trên 8259 ảnh biển số xe máy Việt Nam thật (`scripts/train_plate.py`) — tỉ lệ nhận diện trên khung hình xe máy thật tăng từ ~0% lên ~70% so với bản gốc [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection). **Không tải bản gốc từ HuggingFace để thay thế file này** — sẽ làm chất lượng nhận diện biển số giảm mạnh.

Model `models/yolov8n.pt` (person COCO) và `yolov8n-pose.pt` (tư thế đi bộ vs ngồi xe) vẫn tự tải lần đầu khi chạy (cần internet, ~6MB, không commit vì tải lại y hệt được).

## Biến môi trường

Copy `.env.example` → `.env` rồi điền. Bắt buộc với production:
- `JWT_SECRET_KEY` — nếu để trống, app tự dùng key dev không an toàn (in cảnh báo ra log) và **bất kỳ ai đọc được source code cũng tự ký được token admin giả**. Sinh key mới: `python -c "import secrets; print(secrets.token_hex(32))"`.

Cũng nên đổi mật khẩu của các tài khoản seed mặc định (xem bảng "Users" bên dưới) trước khi dùng thật — đây là mật khẩu demo công khai trong README.

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
| `/guard/video_feed` | GET | security, admin | MJPEG stream (query: `?token=`) |
| `/guard/ws` | WS | security, admin | WebSocket cảnh báo (query: `?token=`) |
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
