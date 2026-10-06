# Hệ thống giám sát cổng trường — React SPA

Phát hiện mũ bảo hiểm + nhận diện biển số xe máy tại cổng trường học, dùng webcam và YOLOv8, giao diện React SPA với đăng nhập phân quyền.

## Cài đặt (dành cho máy chưa có gì cả)

Hướng dẫn này giả sử máy bạn **chưa cài Python, Node.js hay Git** — làm theo đúng thứ tự là chạy được, không cần biết lập trình. Các bước dưới viết cho **Windows** (có ghi chú riêng cho macOS/Linux ở bước nào khác biệt).

### Bước 1 — Cài 3 phần mềm nền tảng

| Phần mềm | Tải ở đâu | Lưu ý khi cài |
|---|---|---|
| **Git** | [git-scm.com/downloads](https://git-scm.com/downloads) | Cứ Next hết, không cần đổi gì |
| **Python 3.9 trở lên** | [python.org/downloads](https://www.python.org/downloads/) | ⚠️ **Tick vào ô "Add python.exe to PATH"** ở màn hình cài đặt đầu tiên — rất dễ quên, quên là bước sau lỗi ngay |
| **Node.js 18 trở lên** (bản LTS) | [nodejs.org](https://nodejs.org/) | Cứ Next hết |

Cài xong, **mở lại** cửa sổ dòng lệnh (PowerShell/Terminal) để nó nhận phần mềm vừa cài, rồi gõ lần lượt 3 lệnh sau để kiểm tra (mỗi lệnh phải ra số phiên bản, không phải lỗi "not recognized"):

```bash
git --version
python --version
node --version
```

### Bước 2 — Tải mã nguồn về máy

```bash
git clone https://github.com/BanhKhuc04/school-gate-monitor.git
cd school-gate-monitor
```

### Bước 3 — Cài phần backend (Python)

```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Trên macOS/Linux, dòng thứ 2 đổi thành `source venv/bin/activate`.

Lệnh `pip install` tải khá nhiều thư viện AI (YOLOv8, EasyOCR...) nên có thể mất **5–15 phút** tùy mạng — thấy đứng im là bình thường, cứ đợi. Mỗi lần mở cửa sổ dòng lệnh MỚI để chạy dự án sau này, luôn phải gõ lại `.\venv\Scripts\activate` trước (dấu hiệu đã bật đúng: đầu dòng lệnh hiện chữ `(venv)`).

### Bước 4 — Cài phần giao diện (Node.js)

```bash
cd frontend
npm install
cd ..
```

### Bước 5 — Tạo file cấu hình riêng (`.env`)

File `.env` chứa các thiết lập riêng của máy bạn (không được chia sẻ công khai, đã bị `.gitignore` chặn commit).

```bash
copy .env.example .env
```

Trên macOS/Linux dùng `cp .env.example .env`.

Mở file `.env` vừa tạo bằng Notepad (hoặc bất kỳ trình soạn thảo nào), điền dòng `JWT_SECRET_KEY=` — đây là "chìa khóa" để hệ thống tự ký phiên đăng nhập, **bắt buộc phải có giá trị riêng**, không để trống hay dùng chung với ai khác. Sinh 1 giá trị ngẫu nhiên bằng lệnh:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy chuỗi ký tự nó in ra, dán vào sau dấu `=`, ví dụ: `JWT_SECRET_KEY=a1b2c3...` (không có dấu cách, không có dấu nháy). Lưu file lại.

Các dòng còn lại trong `.env` (camera, cổng phụ...) để nguyên mặc định là chạy được với webcam laptop — chỉ cần sửa nếu bạn có camera IP/RTSP thật (xem chú thích ngay trong file).

### Bước 6 — Chạy thử

Mở **2 cửa sổ dòng lệnh** (2 tab/terminal riêng), cả hai đều đứng ở thư mục `school-gate-monitor`:

```bash
# Cửa sổ 1 — Backend (nhớ .\venv\Scripts\activate trước nếu là cửa sổ mới)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Cửa sổ 2 — Frontend
cd frontend
npm run dev
```

Mở trình duyệt vào `http://localhost:5173`, đăng nhập bằng 1 trong các tài khoản có sẵn ở mục "Users" bên dưới (ví dụ `admin` / `admin123`).

### Lỗi thường gặp

| Thông báo lỗi | Nguyên nhân & cách sửa |
|---|---|
| `'python' is not recognized...` | Quên tick "Add to PATH" lúc cài Python — gỡ cài rồi cài lại, nhớ tick ô đó |
| `pip install` báo lỗi liên quan `torch`/`opencv` | Kiểm tra lại đã `.\venv\Scripts\activate` chưa (đầu dòng lệnh phải có chữ `(venv)`) trước khi chạy `pip install` |
| Trang web load được nhưng không thấy hình camera | Máy không có webcam, hoặc đang bị app khác (Zoom, Teams...) chiếm camera — đóng app đó lại |
| `address already in use` khi chạy `uvicorn` | Cổng 8000 đang bị chiếm bởi 1 tiến trình backend cũ — tắt cửa sổ dòng lệnh cũ đang chạy nó rồi thử lại |
| Trang trắng hoặc lỗi CORS trên `localhost:5173` | Backend (cửa sổ 1) chưa chạy hoặc bị lỗi — xem log ở cửa sổ 1 trước |

Máy không có GPU NVIDIA vẫn chạy được bình thường (tự động dùng CPU, chỉ chậm hơn), không cần cài thêm gì.

## Tiến độ phát triển hiện tại

**Đã xong (chạy được):**
- Pipeline nhận diện: người (COCO) → mũ bảo hiểm → biển số (YOLOv8n) → OCR (EasyOCR) → tra whitelist → ghi log vi phạm.
- Phát hiện tư thế (YOLOv8-pose): phân biệt đi bộ vs đang ngồi trên xe, để bắt lỗi `RIDING_THROUGH_GATE`.
- Lọc người đi bộ / xe đạp thường khỏi luật bắt mũ + biển số (chỉ áp dụng cho xe máy).
- Auth JWT phân quyền 3 role (admin / security / management), CRUD xe đăng ký, quản lý user, thống kê dashboard, dọn ảnh vi phạm cũ.
- Giao diện đã restyle theo design "Vanguard Campus Security" (landing page, login).

**Đã sửa (trước đây ghi là "bug đã biết"):**
- `/guard/ws` cảnh báo không tới client: đã thêm test tự động `app/tests/test_guard_ws.py` tái hiện đúng kịch bản điều tra trong `docs/handover/HANDOFF_CURSOR.md` (1 client, 2 client đồng thời + trigger dồn dập) — cả hai đều PASS với code hiện tại. Nhân tiện sửa 2 vấn đề thật tìm thấy trong `app/api/guard.py`: (1) thiếu try/except quanh `decode_access_token` khiến token hết hạn/sai làm WS đóng đột ngột không rõ lý do; (2) `_clients_lock` dùng `threading.Lock` (blocking thật) thay vì `asyncio.Lock` trong code async — tiềm ẩn treo cứng event loop nếu 2 client broadcast trùng lúc. Nếu vẫn gặp alert không hiện trên UI thật, nhiều khả năng do nguyên nhân khác (nhiều process backend chạy song song trên cùng port, trình duyệt cụ thể) — báo lại kèm bước tái hiện để điều tra tiếp.

**Đã bỏ:**
- **Nhận diện khuôn mặt** — gỡ hoàn toàn (commit `d4d8dc4`): mở khẩu trang không đeo mặt nạ vẫn xâm phạm dữ liệu sinh trắc học trẻ vị thành niên, rủi ro pháp lý không đáng đánh đổi. Không còn `app/api/faces.py`, `app/cv/face.py`, bảng `face_embeddings`/`face_match_events`, trang `AdminFacesPage`.

**Chưa làm (kế hoạch, chưa có code):**
- Chạy 2 camera song song (cổng vào/cổng ra) — hiện pipeline chỉ đọc **1 nguồn camera duy nhất** (`CAMERA_SOURCE` trong `app/config.py`), chưa có route/logic phân biệt hướng vào/ra.
- Deploy lên VPS (103.101.162.111, 1 vCPU/1GB/15GB) — VPS mới có, chưa cấu hình gì; kế hoạch là chỉ host API + DB + frontend static, inference vẫn chạy ở máy edge tại chỗ.
- Mua/lắp camera IP thật tại cổng — đang khảo giá (Hikvision dòng IP "CD", Imou), chưa chốt.
- OCR (EasyOCR) và model helmet vẫn dùng pretrained public, chưa fine-tune bằng dữ liệu thật của trường (model plate đã fine-tune, xem mục "Model" bên trên).

## Model

`models/helmet_best.pt` và `models/plate_best.pt` đã nằm sẵn trong repo (clone
về là chạy được ngay, không cần tải thêm) — đây là 2 file model **dành riêng
cho dự án**, không phải bản pretrained public gốc:
- `helmet_best.pt`: bản pretrained gốc từ [iam-tsr/yolov8n-helmet-detection](https://huggingface.co/iam-tsr/yolov8n-helmet-detection) (thử fine-tune lại trên dữ liệu thật nhưng kết quả tệ hơn nên giữ nguyên bản gốc, xem commit `d631432`).
- `plate_best.pt`: **đã fine-tune** trên 8259 ảnh biển số xe máy Việt Nam thật (`scripts/train_plate.py`) — tỉ lệ nhận diện trên khung hình xe máy thật tăng từ ~0% lên ~70% so với bản gốc [Koushim/yolov8-license-plate-detection](https://huggingface.co/Koushim/yolov8-license-plate-detection). **Không tải bản gốc từ HuggingFace để thay thế file này** — sẽ làm chất lượng nhận diện biển số giảm mạnh.

Model `models/yolov8n.pt` (person COCO) và `yolov8n-pose.pt` (tư thế đi bộ vs ngồi xe) vẫn tự tải lần đầu khi chạy (cần internet, ~6MB, không commit vì tải lại y hệt được).

## Biến môi trường

Xem chi tiết từng biến (camera, cổng phụ, JWT...) trong file `.env.example` — đã có chú thích đầy đủ. Bước cài đặt ở trên (Bước 5) đã hướng dẫn tạo `.env` và set `JWT_SECRET_KEY`. Nên đổi luôn mật khẩu của các tài khoản seed mặc định (xem bảng "Users" bên dưới) trước khi dùng thật — đây là mật khẩu demo công khai trong README.

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

## Cấu trúc thư mục

```
app/            Backend FastAPI (api/, cv/ pipeline nhận diện, tests/)
frontend/       Giao diện React (Vite) + e2e Playwright
models/         Model đã fine-tune (helmet_best.pt, plate_best.pt)
datasets/       Cấu hình dataset huấn luyện (data.yaml) — ảnh không commit
scripts/        Script tiện ích: seed user, train, benchmark, kiểm tra camera
tests/          Test tích hợp gọi API thật (cần backend đang chạy)
marketing/      Trang giới thiệu tĩnh
docs/plans/     Kế hoạch, danh sách task các đợt phát triển
docs/handover/  Tài liệu bàn giao, nhật ký chạy, việc phần cứng
data/           Dữ liệu runtime (DB, snapshot, backup) — tự tạo khi chạy, không commit
```

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

## License

[AGPL-3.0](LICENSE). Dự án dùng [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) (chính nó cũng license AGPL-3.0) — nếu phát hành bản sửa đổi của dự án này dưới dạng dịch vụ mạng (SaaS) mà không public source, hoặc muốn phân phối dưới license khác (vd. thương mại hóa đóng nguồn), cần mua [Ultralytics Enterprise License](https://ultralytics.com/license) để không bị ràng buộc điều khoản copyleft của AGPL.
