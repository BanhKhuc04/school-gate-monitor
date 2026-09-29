# SMART SCHOOL GATE — DEVELOPMENT HANDOVER

> Đây là tài liệu trạng thái kỹ thuật chính thức của project.
> AI/developer tiếp theo PHẢI đọc file này cùng codebase trước khi thay đổi hệ thống.
>
> Không giả định nội dung trong tài liệu đúng nếu code/test hiện tại mâu thuẫn. Code + migrations + tests là nguồn xác minh cuối cùng.

## 1. PROJECT INFORMATION

Project: Smart School Gate / Student Vehicle Management

Purpose: Quản lý xe học sinh tại cổng trường bằng 2 camera, nhận diện biển số, phát hiện vi phạm, lưu bằng chứng và quản lý qua web.

Current version: 2.0.0 (theo `app/main.py` FastAPI app version)
Current commit: (chuẩn bị commit) — Bước 1/7 đợt 2 vừa hoàn thành, xem SESSION LOG cuối file
Last updated: 2026-09-29
Updated by: Claude (Sonnet 5)

**GIAO VIỆC CHO CURSOR: đọc kỹ mục 23 + SESSION LOG cuối file trước khi code tiếp.**
Kế hoạch đầy đủ (7 bước, chi tiết file/schema/test/acceptance criteria từng bước)
nằm ở file plan đã duyệt — nếu không thấy file plan kèm theo, hỏi lại người dùng
thay vì tự đoán lại thiết kế. Bước 1 đã xong (code + 87 test pass), **bắt đầu từ
Bước 3** (ghép 2 camera). Có video thật để test pipeline tại
`C:\Users\khucv\Downloads\tranning\` (14 file .mp4, 1280x720, camera cổng trường
thật) — dùng làm `CAMERA_SOURCE` để test thay vì cần camera vật lý.

## 2. SYSTEM MODEL

Physical setup:
- 1 cổng trường, 1 luồng xe
- **Hiện tại chỉ deploy thật 1 camera** (`GATES["main"]`). `GATES["secondary"]` (camera thứ 2) đã có sẵn cơ chế trong code (bật bằng env `CAMERA_SOURCE_SECONDARY`) nhưng **chưa được kiểm thử với camera trước+sau thật cùng lúc**, và **chưa có logic hợp nhất 1 lượt xe từ 2 camera thành 1 bản ghi** — mỗi camera hiện ghi `violation_events` độc lập, không liên kết với nhau.

Primary identification: LICENSE PLATE (đúng như thiết kế — `plate_matched`/`plate_read` là khóa chính để nối vào `registered_vehicles`)

Not used as primary identification:
- Face recognition — **đã từng có, đã bị GỠ HOÀN TOÀN** (commit `d4d8dc4 "Remove face recognition entirely (masks defeat it, not worth the biometric-data liability)"`). Không còn code face trong nhánh hiện tại.
- Person ReID — chưa từng có.

Out of scope (xác nhận đúng theo code hiện tại):
- Person counting — có đếm số người/xe (`_count_riders_per_vehicle` cho `TOO_MANY_RIDERS`) nhưng không phải "đếm người" tổng quát.
- Wrong-way detection — không có.
- Mobile application — không có.
- AI chatbot/search — không có.
- Camera map — không có.
- Complex camera-health AI — health hiện tại chỉ là số liệu thô (FPS/latency/uptime), không có AI phân tích.

## 3. CURRENT ARCHITECTURE

Frontend: React 19 + Vite 8 + Tailwind CSS v4 (CSS-based theme, không có `tailwind.config.js`), `react-router-dom` v7, `axios`, `recharts` (chỉ dùng ở Dashboard). Không có UI kit (không shadcn/MUI/antd) — toàn bộ tự viết bằng Tailwind + SVG inline.
Backend: FastAPI (Python), Uvicorn ASGI server.
Database: SQLite (`data/app.db`), truy cập qua `sqlite3` module thuần (không ORM).
AI/CV: Ultralytics YOLOv8 (helmet detector, plate detector, person detector dùng COCO `yolov8n.pt`, pose detector dùng `yolov8n-pose.pt`), EasyOCR cho đọc biển số. Chạy CPU hoặc CUDA tự động (`app/config.py::DEVICE`).
Camera: OpenCV `cv2.VideoCapture` (`app/cv/capture.py::WebcamStream`), hỗ trợ index thiết bị / đường dẫn file / RTSP URL.
Storage: Filesystem cục bộ (`data/snapshots/` cho ảnh JPG + clip MP4), SQLite cho metadata.
Background jobs: **Không có job scheduler thật** (không Celery/cron/APScheduler). Mỗi gate camera chạy 1 `threading.Thread` daemon riêng trong tiến trình FastAPI (`VideoPipeline._run_loop`), khởi động qua FastAPI `lifespan`. Dọn dẹp snapshot/clip cũ là **thao tác thủ công qua nút bấm admin**, không tự chạy theo lịch.
Authentication: JWT (PyJWT, HS256), bcrypt hash password, `JWT_SECRET_KEY` hiện **hardcode trong `app/config.py`** (không đọc từ env — technical debt, xem mục 18).
Deployment: **Chưa deploy** — README ghi VPS (103.101.162.111, 1 vCPU/1GB/15GB) đã thuê nhưng chưa cấu hình gì. Dự kiến VPS chỉ chạy API+DB+frontend static, inference (camera+AI) chạy tại máy edge ở cổng trường.

## 4. CURRENT DATA FLOW

ACTUAL IMPLEMENTED FLOW (đã verify qua đọc code `app/cv/pipeline.py::_run_loop`):

```
Camera (1 gate, WebcamStream.read_frame)
  → FRAME_SKIP throttle (bỏ bớt frame để giảm tải)
  → resize xuống DETECT_WIDTH×DETECT_HEIGHT cho detect (giữ frame gốc VIDEO_WIDTH×HEIGHT để lưu evidence)
  → 3 model YOLO chạy song song qua ThreadPoolExecutor (_detect_pool): person, helmet, plate
  → nếu không có person nào → bỏ qua frame (không xử lý tiếp)
  → _group_by_person: gán helmet/plate/vehicle gần nhất cho từng người
  → _count_riders_per_vehicle: đếm số người/1 xe → gắn cờ TOO_MANY_RIDERS
  → _run_posture_detection (YOLOv8-pose, song song qua cùng _detect_pool): riding/standing/unknown
  → _process_violations (mỗi group riêng biệt):
      - đọc biển số qua _read_plate_cached (cache theo vị trí + TTL 1.5s, tránh OCR lặp)
      - so khớp registered_vehicles
      - quyết định violation_type (xem mục 8)
      - cooldown 60s/biển số (chặn ghi DB lặp) + cooldown 5s riêng cho alert WS
      - nếu có vi phạm mới: submit vào _io_pool (thread nền) → _persist_violation
  → _persist_violation: ghi ảnh JPG (cv2.imwrite) + clip MP4 4s từ ring-buffer 32 frame (_write_clip) + INSERT violation_events (status mặc định 'pending')
  → _push_alert: đẩy JSON qua WebSocket tới mọi client /guard/ws đang mở (cooldown riêng)
  → Frontend GuardPage/AlertBanner: nhận WS, phát âm thanh theo mức ưu tiên + TTS, hiện banner
  → Frontend AdminViolationsPage: người có quyền xem danh sách, đổi status (pending→reviewed→resolved), mọi thay đổi ghi vào violation_audit_log
```

**Điểm khác biệt so với flow "kiểu mẫu" trong file gốc:** không có bước "Multi-frame Aggregation" độc lập trước khi tạo Vehicle Event — mỗi frame xử lý violation ngay lập tức (chỉ có cache OCR theo vị trí để tránh chạy lại EasyOCR, KHÔNG phải aggregation đa khung hình để tăng độ tin cậy biển số). Cũng không có khái niệm "Vehicle Event" tách biệt khỏi "Violation" — hệ thống hiện tại chỉ ghi record khi **có vi phạm**, xe đi qua bình thường (không vi phạm) **không được ghi log** ở đâu cả (không có bảng "mọi lượt xe qua cổng", chỉ có bảng vi phạm).

## 5. FEATURE STATUS

| Feature | Status | Main files | Tests | Notes |
|---|---|---|---|---|
| License plate detection | DONE | `app/cv/detector.py`, `app/config.py::PLATE_MODEL_PATH` | — | YOLO box, không có test riêng cho detector |
| OCR | DONE | `app/cv/ocr.py::read_plate` | `test_ocr.py` | EasyOCR, ngưỡng conf 0.3/text-box hardcode |
| Multi-frame OCR | **DONE** | `app/cv/plate_voter.py::PlateVoter`, `app/cv/pipeline.py::_read_plate_voted` | `test_plate_voter.py` (15 case), `test_vehicle_gate.py` | Vote theo vị trí + cửa sổ 2.5s (`PLATE_VOTE_WINDOW_SEC`); confident nếu ≥2 lần đọc giống nhau HOẶC 1 lần confidence ≥0.55 |
| Confidence scoring | **DONE** | `app/cv/ocr.py::read_plate_detailed` (nay được gọi qua `PlateVoter`), cột `violation_events.plate_confidence` | `test_plate_confidence_db.py` | Không confident → **KHÔNG tra whitelist** (`get_vehicle_by_plate` bị bỏ qua), violation_type = `PLATE_LOW_CONFIDENCE`, status = `needs_review` (tái dùng UI/audit trail Feature 10 có sẵn, không xây review subsystem riêng) |
| Duplicate suppression | PARTIAL | `_process_violations` (VIOLATION_COOLDOWN 60s) | — | Chặn ghi trùng theo (biển số, 60s), không phải theo "1 lượt xe qua cổng" thật sự (không có khái niệm event boundary) |
| Front/rear correlation | NOT STARTED | — | — | 2 gate chạy hoàn toàn độc lập, không có logic ghép 1 xe từ cả 2 camera thành 1 record |
| Helmet detection | DONE | `app/cv/detector.py`, `app/cv/pipeline.py` | `test_vehicle_gate.py` | Có "With Helmet"/"Without Helmet"; trạng thái "không chắc chắn" chưa tách riêng (nếu không detect được thì coi như không vi phạm, không có nhãn UNKNOWN cho helmet) |
| Registered vehicle matching | DONE | `app/db.py::get_vehicle_by_plate` | `test_vehicles.py` | — |
| Unregistered vehicle | DONE | `PLATE_NOT_REGISTERED` violation type | `test_vehicle_gate.py` | — |
| NO_PLATE | DONE | `_process_violations` | `test_vehicle_gate.py` | Thêm session này (không có box biển số nào) |
| PLATE_OBSCURED | DONE | `_process_violations` | `test_vehicle_gate.py` | Thêm session này (có box nhưng OCR đọc rỗng) |
| Event evidence | PARTIAL | ảnh JPG + clip MP4 mỗi vi phạm | — | Chỉ lưu khi CÓ vi phạm, không lưu evidence cho lượt xe hợp lệ |
| Event video | DONE | `_write_clip`, clip 4s/8fps, `VIOLATION_CLIP_SECONDS/FPS` | — | Chỉ có clip ngắn quanh thời điểm vi phạm |
| Continuous recording | NOT STARTED | — | — | Không có ghi hình liên tục 24/7, chỉ có ring-buffer 32 frame trong RAM dùng để cắt clip vi phạm |
| Recording segmentation | NOT STARTED | — | — | Phụ thuộc continuous recording, chưa có |
| Retention policy | PARTIAL | `REPEAT_OFFENDER_WINDOW_DAYS` không liên quan; cleanup dùng 1 mốc `older_than_days` chung cho cả ảnh+clip | `test_system.py` | Chưa phân tầng theo loại dữ liệu (video thường/vi phạm/lịch sử) như yêu cầu #6 |
| Automatic cleanup | PARTIAL | `POST /api/system/snapshots/cleanup` | `test_system.py` | **Chỉ chạy khi admin bấm nút thủ công**, không có lịch tự động (không cron/scheduler) |
| Cleanup dry-run | DONE | `GET /api/system/snapshots/preview` | Verify qua API session trước | Trả file_count + size trước khi xóa thật |
| Storage statistics | PARTIAL | `GET /api/system/health` (db_size_mb, snapshot_count, snapshot_size_mb) | `test_system.py` | Chưa có dung lượng đĩa tổng/còn trống, chưa phân bổ theo loại (video thường vs vi phạm) |
| Backup | NOT STARTED | — | — | Không có script/cron backup DB hay snapshot |
| Dashboard | DONE | `DashboardPage.jsx` | — | Có trend/by-class chart (`recharts`), chưa có "tổng xe hôm nay/đăng ký/chưa đăng ký/cần kiểm tra" như yêu cầu #7 |
| Live camera | DONE | `GuardPage.jsx` (kể cả xem song song 2 camera), `guard.py::video_feed` | — | MJPEG qua `<img>`, rate-limit 20fps |
| Vehicle events UI | NOT STARTED | — | — | Không có khái niệm "vehicle event" riêng khỏi violation trong UI |
| Event detail | DONE (dạng violation) | `ViolationDetailModal` trong `AdminViolationsPage.jsx` | — | Xem ảnh/video + trạng thái + audit log |
| Violations | DONE | `AdminViolationsPage.jsx`, `app/api/admin.py` | `test_vehicle_gate.py`, `test_posture.py`, `test_violation_status.py` | — |
| Student/vehicle profile | DONE | `StudentViolationHistoryPage.jsx`, `get_student_violation_summary`, `get_violations_by_vehicle` | `test_repeat_offender.py` | Có lịch sử vi phạm theo học sinh + cờ tái phạm (≥3 lần/30 ngày) |
| Reports | PARTIAL | `GET /api/stats/summary` (today/week/trend 14 ngày/by_class) | `test_stats.py` | Chưa có báo cáo cấu trúc theo ngày/tuần/tháng riêng biệt, chỉ có 1 endpoint tổng hợp |
| Export | DONE | CSV export vehicles + violations (`GET /api/vehicles/export`, `GET /api/violations/export`) | — | Chưa có export Excel (.xlsx), chỉ CSV |
| Role permissions | DONE | `app/auth.py::require_role`, 4 role: admin/security/management/teacher | Toàn bộ test file có auth | Management vừa được mở quyền xem camera+vi phạm+xe (commit `9d81244`) |
| Audit trail | DONE | `violation_audit_log` table, `PATCH /violations/{id}/status` | `test_violation_status.py` | Append-only, ghi actor+action+note+thời gian |

## 6. DATABASE

Database engine: SQLite 3, file `data/app.db`
Migration system: **Không có framework migration** (không Alembic). Pattern thủ công trong `app/db.py::init_db()`: `CREATE TABLE IF NOT EXISTS` cho bảng mới + `ALTER TABLE ... ADD COLUMN` bọc `try/except sqlite3.OperationalError: pass` cho cột mới trên bảng cũ. Riêng đổi CHECK constraint (thêm role 'teacher') phải rebuild bảng `users` thủ công (tạo bảng mới, copy data, rename).

### Students
Table/model: **Không có bảng `students` riêng.** Học sinh là 2 cột text (`student_name`, `student_class`) gắn thẳng trên `registered_vehicles` — mô hình 1 xe = 1 học sinh, không chuẩn hóa.

### Vehicles
Table/model: `registered_vehicles`
Important fields: `id`, `plate_number` (UNIQUE), `student_name`, `student_class`, `created_at`

### Vehicle Events
Table/model: **Không có bảng riêng.** Không có khái niệm "mọi lượt xe qua cổng" — chỉ ghi khi có vi phạm (xem `violation_events`).

### Violations
Table/model: `violation_events`
Important fields: `id`, `timestamp`, `plate_read`, `plate_matched`, `helmet_status`, `violation_type` (7 giá trị, xem mục 8), `snapshot_path`, `clip_path`, `posture_status`, `plate_format_valid`, `status` (pending/reviewed/resolved/reopened), `created_at`

### Evidence
Table/model: Không tách bảng riêng — `snapshot_path`/`clip_path` là cột trực tiếp trên `violation_events`, file vật lý trong `data/snapshots/`, phục vụ qua static mount `/media` (StaticFiles, **không có auth trên route `/media`** — ai có URL cũng xem được, xem mục 18).

### Storage / Cleanup
Table/model: Không có bảng cleanup log. `clear_violation_snapshot_paths(older_than_days)` xóa file rồi `UPDATE violation_events SET snapshot_path=NULL, clip_path=NULL` — record vi phạm vẫn giữ, chỉ mất file.

Ngoài ra có `violation_audit_log` (id, violation_id, actor_username, action, note, created_at) và `users` (id, username, password_hash, role CHECK IN admin/security/management/teacher, homeroom_class nullable, created_at).

Do not remove or rename existing schema without migration.

## 7. CAMERA CONFIGURATION

Camera Front (gate "main"):
- Purpose: Camera chính, luôn tồn tại.
- Source/config: env `CAMERA_SOURCE` (index/path/RTSP), mặc định `CAMERA_INDEX=1` trong `app/config.py`.

Camera Rear (gate "secondary"):
- Purpose: Camera phụ, **tùy chọn** — chỉ tạo pipeline nếu set env.
- Source/config: env `CAMERA_SOURCE_SECONDARY`. **Chưa test thật với 2 camera vật lý trước+sau cùng lúc trong session này** — chỉ verify được code path tồn tại và UI xem song song (split-view) hoạt động.

Resolution: Capture `VIDEO_WIDTH×VIDEO_HEIGHT` = 1280×720 (dùng cho lưu evidence/OCR); detect resize xuống `DETECT_WIDTH×HEIGHT` = 640×480 (dùng riêng cho 3 model YOLO, map tọa độ ngược lại sau khi detect).
FPS: Video feed stream giới hạn 20fps (`app/api/guard.py`). FPS xử lý AI thật đo qua `get_status()['fps']` (rolling window 30 frame) — **chưa có số liệu thật vì chưa test với người/xe đi qua camera thật trong session dev này**.
Reconnect behavior: Có — `_run_loop` đếm lỗi đọc frame liên tiếp, sau `_RECONNECT_AFTER` (5) lần thì tự reconnect camera với backoff 2s. Nếu file nguồn (không phải camera vật lý) đọc hết thì tự loop lại từ đầu nếu `loop=True`.
Known issues: Port mismatch từng gặp giữa `app/main.py` (default port 8000) và `frontend/vite.config.js`/`api/client.js` (hardcode 8001) — đã set port 8001 thống nhất khi chạy dev, nhưng **chưa sửa tận gốc trong code** (vẫn còn 2 giá trị khác nhau nằm rải rác).

## 8. AI PIPELINE

Vehicle detector: YOLOv8n COCO chuẩn (`yolov8n.pt`, tự tải), lọc class `motorcycle`/`bicycle`, ngưỡng `PERSON_CONF_THRESHOLD=0.4` dùng chung cho person+vehicle vì cùng 1 model COCO.
Plate detector: YOLO custom `models/plate_best.pt`, ngưỡng `PLATE_CONF_THRESHOLD=0.25`. **Confidence của từng box KHÔNG được đọc/dùng ở tầng quyết định vi phạm** — chỉ dùng bbox để crop OCR.
OCR: EasyOCR (`app/cv/ocr.py`), ngưỡng per-text-box `conf < 0.3` bị loại, có `_PLATE_FORMAT_RE` để gắn cờ `plate_format_valid` (chỉ advisory, không loại kết quả).
Helmet detector: YOLO custom `models/helmet_best.pt`, ngưỡng `HELMET_CONF_THRESHOLD=0.25`, 2 class "With Helmet"/"Without Helmet".
Tracking/event correlation: **Không có** — không có object tracking giữa các frame, không có correlation giữa 2 camera.
Multi-frame method: Chỉ có cache OCR theo vị trí (grid) + TTL 1.5s để tránh chạy lại EasyOCR liên tục cho cùng 1 xe đứng yên trong khung hình — **không phải** kỹ thuật tăng độ tin cậy qua nhiều lần đọc (vote/aggregate).
Plate normalization: `normalize_plate()` — uppercase, strip mọi ký tự ngoài A-Z0-9.
Confidence calculation: `read_plate_detailed()` có tính trung bình confidence các text-box nhưng **không được gọi** trong luồng chính; `Detection.confidence` (từ YOLO box) cũng tồn tại nhưng không đọc ở `_process_violations`.
Thresholds: Xem `app/config.py` — `HELMET_CONF_THRESHOLD=0.25`, `PLATE_CONF_THRESHOLD=0.25`, `PERSON_CONF_THRESHOLD=0.4`, EasyOCR text conf `0.3` (hardcode trong `ocr.py`, không phải config.py), `MAX_RIDERS_PER_MOTORCYCLE=2`.
Known failure cases: Chưa có bộ test đo tỉ lệ đọc sai/trùng biển số thật; `plate_read_success_rate` trong `get_status()` mới đo được "tỉ lệ OCR trả về non-empty", không đo "đọc ĐÚNG" (không có ground-truth so sánh).

## 9. STORAGE

Storage root: `data/` (`DB_PATH=data/app.db`, `SNAPSHOTS_DIR=data/snapshots/`)
Current layout: Phẳng — mọi ảnh JPG + clip MP4 nằm chung 1 thư mục `data/snapshots/`, đặt tên `{timestamp}_{violation_type}.jpg`/`.mp4`, không phân thư mục theo ngày/loại/camera.

### Data classes
Continuous recordings: Không tồn tại (xem mục 5).
Event clips: `data/snapshots/*.mp4`, 4 giây, 8fps, resize 640×360 trước khi ghi để giảm RAM/dung lượng.
Snapshots: `data/snapshots/*.jpg`, full-res `VIDEO_WIDTH×HEIGHT` (1280×720).
Plate crops: Không lưu riêng — chỉ crop tạm trong RAM để OCR, không ghi ra đĩa.
Violation evidence: = snapshot + clip ở trên, gắn vào `violation_events.snapshot_path`/`clip_path`.

### Retention

| Data | Current retention |
|---|---:|
| Continuous recording | N/A (không tồn tại) |
| Normal snapshots | Không phân biệt "thường" — mọi ảnh/clip đều là ảnh vi phạm, cùng 1 policy xóa theo `older_than_days` (mặc định preset UI: >30/>90/>180 ngày, admin tự chọn) |
| Violation evidence | Như trên — chưa tách riêng thời hạn dài hơn cho vi phạm |
| Event metadata | Record DB giữ **vĩnh viễn** kể cả sau khi cleanup xóa file (chỉ null hóa path) |

Cleanup schedule: **Không có lịch tự động** — chỉ chạy khi admin bấm nút hoặc gọi API thủ công.
Last cleanup: Không track trong DB/health — không có trường "last cleanup time" ở đâu.
Dry-run supported: YES (`GET /api/system/snapshots/preview`)
Protected evidence supported: NO — không có cờ "khóa không cho xóa" cho bằng chứng quan trọng; cleanup theo `older_than_days` sẽ xóa mọi thứ cũ hơn mốc, không phân biệt mức độ nghiêm trọng vi phạm.

## 10. WEB UI

Main pages currently implemented:
- `/login` — đăng nhập, có nút demo theo role
- `/guard` — camera trực tiếp (đơn hoặc song song 2 gate) + banner cảnh báo
- `/admin/vehicles` (+ `/teacher/vehicles` scoped theo lớp) — CRUD xe, import/export CSV (dry-run preview), autocomplete tìm học sinh
- `/admin/violations` (+ `/teacher/violations` scoped) — danh sách vi phạm, filter, modal chi tiết (ảnh/video/status/audit log)
- `/admin/students/:vehicleId/violations` — lịch sử vi phạm 1 học sinh dạng timeline + cờ tái phạm
- `/admin/users` — quản lý tài khoản, gán role + lớp chủ nhiệm cho giáo viên
- `/admin/health` — FPS/latency/tỉ lệ đọc biển số/trạng thái pipeline mỗi gate + dọn snapshot (preview + preset)
- `/dashboard` — thống kê trend 14 ngày + theo lớp (recharts)

Dashboard: Có, nhưng chưa có 5 số liệu tổng quan yêu cầu #7 ("tổng xe hôm nay/đăng ký/chưa đăng ký/vi phạm/cần kiểm tra") — hiện dashboard chỉ có trend/by-class.
Live cameras: DONE, kể cả xem song song 2 gate.
Vehicle events: Không tồn tại như 1 trang riêng (chỉ có Violations).
Violations: DONE.
Students/vehicles: DONE (AdminVehiclesPage + StudentViolationHistoryPage).
Reports: PARTIAL — chỉ có Dashboard, chưa có trang "Báo cáo" riêng theo ngày/tuần/tháng dạng xuất được.
Storage: PARTIAL — nằm trong AdminHealthPage, chưa phải trang Storage độc lập với phân bổ theo loại dữ liệu.
Settings: **Không tồn tại** — không có trang cấu hình retention/ngưỡng nào qua UI (mọi ngưỡng nằm cứng trong `app/config.py`, phải sửa code + restart).

Known UI issues: `TopStatusBar` từng poll `/api/system/health` cho cả role không có quyền (đã fix riêng cho teacher, **chưa audit hết** các nơi khác có thể gọi API mà role không có quyền).

## 11. API

| Method | Endpoint | Purpose | Permission |
|---|---|---|---|
| POST | `/api/auth/login` | Đăng nhập, trả JWT | Public |
| GET | `/api/auth/me` | Thông tin user hiện tại | Authenticated |
| GET | `/api/vehicles` | Danh sách xe (teacher/management scoped) | admin, teacher, management |
| POST | `/api/vehicles` | Thêm xe | admin |
| PUT | `/api/vehicles/{id}` | Sửa xe | admin |
| DELETE | `/api/vehicles/{id}` | Xóa xe | admin |
| POST | `/api/vehicles/import` | Import CSV (có `?dry_run=true`) | admin |
| GET | `/api/vehicles/export` | Export CSV | admin |
| GET | `/api/vehicles/violations-summary` | Tổng hợp vi phạm/xe + cờ tái phạm | admin, management, teacher |
| GET | `/api/vehicles/{id}/violations` | Lịch sử vi phạm 1 xe | admin, management, security, teacher |
| GET | `/api/violations` | Danh sách vi phạm (scoped) | admin, teacher, management |
| GET | `/api/violations/export` | Export CSV vi phạm | admin |
| PATCH | `/api/violations/{id}/status` | Đổi trạng thái xử lý | admin, security, management |
| GET | `/api/violations/{id}/audit-log` | Lịch sử xử lý | admin, security, management |
| GET | `/api/stats/summary` | Thống kê dashboard | admin, management |
| GET | `/api/system/health` | Trạng thái pipeline/storage | admin, management, security |
| POST | `/api/system/snapshots/cleanup` | Dọn ảnh/clip cũ | admin |
| GET | `/api/system/snapshots/preview` | Xem trước trước khi dọn | admin |
| GET | `/api/users` | Danh sách tài khoản | admin |
| POST/PUT/DELETE | `/api/users`, `/api/users/{id}` | CRUD tài khoản | admin |
| GET | `/guard/video_feed` | MJPEG stream | admin, security, management (token param) |
| WS | `/guard/ws` | Cảnh báo real-time | admin, security, management (token param) |

Breaking API changes since previous handover: Không có "previous handover" thật (file này là lần đầu điền dữ liệu thật).

## 12. ROLES & PERMISSIONS

Roles currently implemented: `admin`, `security`, `management`, `teacher` (CHECK constraint trong bảng `users`)

| Feature | Admin | Management | Teacher | Security |
|---|---|---|---|---|
| Dashboard | ✅ | ✅ | ❌ | ❌ |
| Live camera | ✅ | ✅ | ❌ | ✅ |
| Events (=Violations) | ✅ | ✅ | ✅ (chỉ lớp mình) | ❌ (không có route xem danh sách, chỉ đổi status) |
| Violations status update | ✅ | ✅ | ❌ (chỉ đọc) | ✅ |
| Student vehicles | ✅ (CRUD) | ✅ (xem) | ✅ (chỉ lớp mình, xem) | ❌ |
| Storage (health page) | ✅ | ✅ | ❌ | ✅ |
| Settings | N/A — trang chưa tồn tại cho bất kỳ role nào | | | |

Use actual roles from codebase — bảng trên đã verify qua `grep require_role` toàn bộ `app/api/`.

## 13. TEST STATUS

Total tests: 64
Passed: 64
Failed: 0
Command: `./venv/Scripts/python.exe -m pytest app/tests/ -q`
Last test date: 2026-09-29 (sau commit `9d81244`)

Critical test areas:
- camera — KHÔNG có test (cần camera thật, chỉ có `app/cv/smoke_test.py` chạy tay bằng `python -m app.cv.smoke_test`, không phải pytest)
- plate recognition — CÓ (`test_ocr.py`, phần logic thuần regex/normalize, không test model YOLO thật)
- vehicle event — N/A (không có khái niệm này)
- violations — CÓ (`test_vehicle_gate.py`, `test_posture.py`)
- permissions — CÓ (rải rác trong hầu hết file test, assert 401/403)
- retention — CÓ MỘT PHẦN (`test_system.py::test_cleanup_*`)
- cleanup — CÓ (`test_system.py`)
- storage — CÓ MỘT PHẦN (`test_system.py::test_health_*` chỉ check response shape, không check số liệu thật)

Known untested areas: Model YOLO/EasyOCR thật (mọi test dùng mock), 2 camera đồng thời thật, ghi video clip với camera thật (chỉ test bằng frame giả `np.zeros`), performance/FPS thật với người đi qua camera, frontend không có unit test tự động (chỉ verify tay qua browser trong các session trước — Playwright config tồn tại ở `frontend/playwright.config.js` nhưng chưa chạy trong session này).

## 14. PERFORMANCE

Test environment: Máy dev Windows, camera OBS Virtual Camera / webcam vật lý (không có camera IP thật).
Number of cameras: Code hỗ trợ 2 (`main`+`secondary`), **thực tế session dev chỉ chạy 1 camera có tín hiệu**.
Observed FPS: **Chưa đo được số thật** — trong các lần verify trước, `fps` luôn ra `0.0` vì không có người/xe nào đi qua khung hình camera test (không có detection nào xảy ra để tính rolling FPS).
Recognition latency: Tương tự — `avg_process_latency_ms` chưa có số liệu thật vì chưa có frame nào chạy hết pipeline detect (cần có person trong khung hình).
CPU: Không đo.
GPU: Không đo — code tự dùng CUDA nếu có, môi trường dev hiện tại chưa xác nhận có GPU hay không.
RAM: Không đo.
Storage growth/day: Không đo (chưa chạy đủ lâu với dữ liệu thật để tính).
Known bottlenecks: Theo comment trong code — vòng lặp MJPEG stream trước đây từng chạy full tốc độ tranh CPU với thread detect (đã fix bằng rate-limit 20fps, xem `app/api/guard.py`); resize 2 tầng (VIDEO vs DETECT resolution) đã là fix có chủ đích cho vấn đề OCR đọc rỗng khi ảnh detect quá nhỏ (xem comment trong `app/config.py`).

## 15. COMPLETED DEVELOPMENT

Lịch sử theo commit thật (không theo khuôn Phase 0-6 vì project không phát triển theo đúng khuôn đó):

- Xây pipeline CV cơ bản (helmet/plate/OCR/gate helmet theo vehicle_type), face recognition (sau đó gỡ bỏ hoàn toàn), posture detection (riding/standing), multi-rider detection, fine-tune model biển số VN thật.
- Restyle toàn bộ UI theo 1 design system ("School Gate Monitor"), thêm landing page, SPA auth.
- **Session gần nhất (commit `4174e30` + `9d81244`)**: 11 tính năng theo kế hoạch `docs/CURSOR_PLAN_11_FEATURES.md` (NO_PLATE/PLATE_OBSCURED, lịch sử vi phạm học sinh + tái phạm, âm thanh ưu tiên, video clip, autocomplete, timeline, health mở rộng, cleanup preview, vai trò giáo viên, audit trail, CSV dry-run) + mở quyền Ban giám hiệu xem camera/vi phạm/xe. Đã fix 2 bug thật phát hiện qua verify tay: AdminHealthPage crash trắng trang, AdminVehiclesPage lộ nút admin cho giáo viên.

Commit hiện tại: `9d81244`

## 16. CURRENT TODO

Priority P0 — Critical (chặn yêu cầu mới nhất của người dùng, theo đúng thứ tự ưu tiên họ nêu):
- Nâng độ tin cậy đọc biển số: dùng `read_plate_detailed()`'s confidence (đã có sẵn, chưa nối vào pipeline) + multi-frame aggregation thật (vote/trung bình qua N frame liên tiếp cùng 1 xe) + trạng thái "cần kiểm tra" riêng biệt (không tự đoán khi confidence thấp)
- Hợp nhất 1 lượt xe từ camera trước+sau thành 1 record duy nhất (hiện 2 gate ghi độc lập) — cần thiết kế bảng `vehicle_events` mới hoặc cột liên kết trên `violation_events`

Priority P1 — Important:
- Retention phân tầng theo loại dữ liệu (không phải 1 mốc chung `older_than_days`) + configurable qua Settings UI (hiện không có trang Settings)
- Tự động hóa cleanup theo lịch (hiện chỉ trigger tay) — cần thêm cơ chế scheduler (APScheduler hoặc thread định kỳ trong app, tránh thêm dependency ngoài nếu không cần thiết)
- Storage dashboard: tổng dung lượng đĩa + còn trống + phân bổ theo loại dữ liệu
- Backup DB/snapshot

Priority P2 — Improvement:
- Báo cáo ngày/tuần/tháng dạng riêng + export Excel (hiện chỉ CSV)
- Dashboard 5 số liệu tổng quan (tổng xe hôm nay/đăng ký/chưa đăng ký/vi phạm/cần kiểm tra)
- Continuous recording chia đoạn (lớn, tốn tài nguyên — cần xác nhận lại với người dùng trước khi làm, xem cảnh báo mục 24)
- Audit toàn bộ nơi gọi API theo role để tránh 403 dư thừa (đã fix 1 chỗ cho teacher, chưa rà hết)

## 17. KNOWN BUGS

| ID | Severity | Description | Reproduction | Status |
|---|---|---|---|---|
| — | — | Không có bug mở đã biết tại thời điểm viết tài liệu này (64/64 test pass, đã verify tay qua browser) | — | — |

## 18. TECHNICAL DEBT

- **Hardcoded configuration**: `JWT_SECRET_KEY` hardcode trong `app/config.py` (không đọc từ env) — verify được qua đọc trực tiếp file.
- **Secrets**: Như trên, `JWT_SECRET_KEY` nằm trong source control.
- **Duplicate camera polling**: Không phát hiện polling trùng lặp.
- **Storage cleanup safety**: Cleanup xóa theo `older_than_days` không phân biệt mức độ nghiêm trọng vi phạm, không có cờ "protected" — verify qua `clear_violation_snapshot_paths()`.
- **Large media directories**: `data/snapshots/` phẳng, không phân thư mục — có thể chậm khi số file lớn (verify qua cấu trúc lưu file trong `_persist_violation`).
- **Database indexes**: Chỉ có 2 index xác nhận (`idx_violation_events_timestamp`, `idx_audit_log_violation`) — chưa có index trên `plate_matched`/`student_class` dù các cột này được filter thường xuyên trong `list_violations`/`get_student_violation_summary`.
- **Frontend polling**: `TopStatusBar` poll health mỗi 10s, `GuardPage` poll health mỗi 5s, `AdminHealthPage` poll mỗi 5s — nhiều nơi tự poll độc lập cùng 1 endpoint, chưa gộp.
- **Background worker isolation**: **Đây là điểm TỐT, không phải nợ** — mỗi gate chạy pipeline/thread riêng, 1 gate lỗi không ảnh hưởng gate còn lại (verify qua cấu trúc `_pipelines` dict theo `gate_id` trong `app/cv/pipeline.py`).
- **Không có migration framework** — rủi ro khi schema phức tạp dần (xem mục 6).
- **`yolov8n.pt` (6.5MB) bị track nhầm vào git** dù `.gitignore` có loại trừ — file cũ đã được track từ trước khi thêm rule. Đã loại khỏi zip snapshot, chưa `git rm --cached`.
- **Nhiều file `PLAN*.md`/`TASKS*.md` rời rạc ở root** chưa gom — đã đề xuất ở review trước, chưa làm.

Do not list something as technical debt unless verified from code. *(Toàn bộ mục trên đã verify qua đọc code/cấu trúc file thật trong session này hoặc session trước liền kề.)*

## 19. IMPORTANT DESIGN DECISIONS

1. License plate is the primary vehicle/student identification mechanism.
2. Face recognition is not required. *(Đã gỡ khỏi code thật, không chỉ "không cần" mà đã xóa hẳn.)*
3. Two cameras provide complementary evidence. *(Code hỗ trợ, chưa test thật đồng thời.)*
4. One physical vehicle passage should correspond to one logical vehicle event. **← CHƯA ĐÚNG trong code hiện tại nếu bật 2 camera — mỗi camera ghi record riêng.**
5. Low-confidence AI results must not be silently treated as correct. **← CHƯA ĐÚNG đầy đủ — confidence có sẵn (`read_plate_detailed`) nhưng chưa dùng để quyết định "cần kiểm tra".**
6. UNREADABLE is different from NO_PLATE. **← ĐÃ ĐÚNG** — `PLATE_OBSCURED`/`PLATE_UNREADABLE` (lịch sử) khác `NO_PLATE`.
7. Helmet UNKNOWN is different from NO_HELMET. **← CHƯA có trạng thái UNKNOWN riêng cho helmet.**
8. Media and metadata have different retention policies. **← CHƯA — cùng 1 mốc `older_than_days`.**
9. Continuous recording is short-retention data. N/A — continuous recording chưa tồn tại.
10. Violation evidence has longer retention. **← CHƯA phân biệt.**
11. Student/vehicle profiles must not be deleted by media cleanup. **← ĐÚNG** — cleanup chỉ null hóa `snapshot_path`/`clip_path`, không đụng `registered_vehicles`/`violation_events` record.
12. Destructive cleanup requires safety checks. **← MỘT PHẦN** — có dry-run/preview, nhưng không có "protected evidence" flag.

*(Các dòng "←" là do người viết tài liệu này (Claude) đối chiếu quyết định thiết kế với code thật — nhiều quyết định trong danh sách gốc CHƯA được hiện thực đầy đủ, đây chính là gap thật cần làm, không phải đã xong.)*

## 20. IMPORTANT FILES

Architecture: Không có `ARCHITECTURE.md` — dùng chính file này (mục 3-4) làm nguồn kiến trúc.
Backend entry: `app/main.py` (FastAPI app + lifespan khởi động pipeline)
Frontend entry: `frontend/src/main.jsx` → `App.jsx`
Camera: `app/cv/capture.py`
AI: `app/cv/detector.py`, `app/cv/ocr.py`, `app/cv/pose.py`, `app/cv/pipeline.py` (điều phối chính)
Models: `models/helmet_best.pt`, `models/plate_best.pt` (custom, cần tải riêng — xem README mục "Tải model"); `yolov8n.pt`, `yolov8n-pose.pt` (COCO, ultralytics tự tải)
API: `app/api/{admin,auth,dev,guard,system,users}.py`
Storage: `app/db.py` (schema + query), `data/snapshots/` (file vật lý)
Cleanup: `app/db.py::get_old_violation_snapshot_paths/clear_violation_snapshot_paths`, `app/api/system.py`
Tests: `app/tests/`
Config: `app/config.py` (mọi hằng số — không có `.env`)

## 21. ENVIRONMENT / CONFIGURATION

Required environment variables (đều optional, có default trong `app/config.py`):
- `CAMERA_SOURCE`, `CAMERA_LOOP` — camera chính
- `CAMERA_SOURCE_SECONDARY`, `GATE_SECONDARY_NAME`, `GATE_SECONDARY_LOOP`, `GATE_MAIN_NAME` — camera phụ
- Không có biến env cho JWT secret/port/DB path — toàn bộ hardcode.

Do NOT write secrets into this document. *(Không có secret nào được ghi ở đây.)*

External services: Không có — hệ thống chạy hoàn toàn local/edge, không gọi API bên ngoài nào.
Model files required: Xem mục 20 "Models".
Runtime dependencies: Xem `requirements.txt` — fastapi, uvicorn, opencv-python, ultralytics, easyocr, PyJWT, bcrypt, onnxruntime, pytest, httpx, python-multipart, numpy, jinja2.

## 22. HOW TO RUN

Backend: `./venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload` (chạy `--reload` để tự áp dụng khi sửa code — session trước từng quên flag này, phải restart tay).
Frontend: `npm run dev --prefix frontend` (Vite, cổng 5173, proxy `/api`+`/media`+`/guard/*` sang `localhost:8001`).
Camera worker: Không tách riêng — chạy chung tiến trình backend qua `lifespan` (`start_all_pipelines()`).
Background worker: Không có (xem mục 3).
Tests: `./venv/Scripts/python.exe -m pytest app/tests/ -q` (từ thư mục gốc; cần chạy trong môi trường không giới hạn RAM quá thấp — từng gặp `MemoryError` khi import `matplotlib`/`ultralytics` trong sandbox mặc định).
Production: **Chưa cấu hình** — xem README mục "Chạy (Production)" cho hướng dẫn build 1 process duy nhất (frontend build tĩnh + FastAPI serve), nhưng chưa deploy thật lên VPS.

## 23. HANDOVER INSTRUCTIONS FOR NEXT AI/DEVELOPER

*(Giữ nguyên checklist gốc — vẫn đúng, không cần sửa.)*

### SESSION LOG — 2026-09-29 (đợt 2, Bước 1)

Goal: Triển khai Bước 1 của kế hoạch đợt 2 — đa khung hình + confidence score cho biển số + trạng thái "cần kiểm tra" (không tự đoán). Xem file plan đã duyệt (7 bước) cho toàn bộ thiết kế.

Completed:
- `PlateVoter` (module mới, tách riêng khỏi pipeline.py để dễ thay implementation sau này) — vote biển số qua nhiều khung hình theo vị trí + cửa sổ thời gian, có confidence.
- `_process_violations()`: khi đọc biển số không đủ tin cậy (`is_confident=False`) → **bỏ qua tra whitelist hoàn toàn**, gắn `violation_type=PLATE_LOW_CONFIDENCE`, `status=needs_review`. Đây là chỗ áp dụng "không tự đoán" theo đúng yêu cầu.
- `needs_review` TÁI DÙNG nguyên `status` column + `STATUS_COLORS` + `PATCH /violations/{id}/status` + audit log đã có từ Feature 10 — không tạo bảng/route/UI mới.
- Thêm 2 cột nền tảng cho Bước 3: `violation_events.plate_confidence`, `violation_events.gate_id` (migration ALTER TABLE, pattern try/except như cũ).
- `GET /api/violations` thêm filter `status`.

Files changed:
- Mới: `app/cv/plate_voter.py`, `app/tests/test_plate_voter.py`, `app/tests/test_plate_confidence_db.py`
- Sửa: `app/cv/pipeline.py` (`_read_plate_cached`→`_read_plate_voted`, `_process_violations`, `_persist_violation`), `app/db.py` (`add_violation_event`, `list_violations`, migration), `app/config.py` (3 hằng số `PLATE_VOTE_*`), `app/api/admin.py` (filter `status`, nhãn `PLATE_LOW_CONFIDENCE`), `frontend/src/pages/AdminViolationsPage.jsx` (badge màu tím cho `PLATE_LOW_CONFIDENCE`/`needs_review`, hiện % confidence trong modal), `frontend/src/utils/violationLabels.js`, `app/tests/test_vehicle_gate.py` (cập nhật mock theo API mới + 2 test case needs_review mới)

Database migrations: `plate_confidence REAL`, `gate_id TEXT` trên `violation_events` — an toàn cho DB cũ (ALTER TABLE try/except), không cần backfill.

Tests: 87/87 pass (`pytest app/tests/ -q`), gồm 23 test mới (15 `test_plate_voter.py` + 2 `test_vehicle_gate.py` + 6 `test_plate_confidence_db.py`).

Performance: Chưa đo — cần camera/video thật có xe đi qua để có số liệu FPS/latency thật (môi trường dev hiện tại camera trống). Có video thật tại `C:\Users\khucv\Downloads\tranning\` (14 file, 1280x720, camera cổng trường) chưa dùng để test integration — khuyến nghị Cursor dùng làm `CAMERA_SOURCE` khi verify Bước 3+.

Known problems: Chưa verify tay qua browser (chỉ verify qua pytest) — cần bật pipeline với 1 trong các video training để thấy `PLATE_LOW_CONFIDENCE`/badge tím thật trên UI.

Next task: Bước 3 — ghép 1 lượt xe từ 2 camera (trước+sau), xem chi tiết đầy đủ trong file plan đã duyệt (schema `linked_violation_id`/`correlation_status`, module `app/cv/event_correlator.py`, `difflib.SequenceMatcher` cho similarity, ưu tiên correctness — test case "không ghép sai" phải nhiều hơn test "ghép đúng").

Commit: (xem commit ngay sau entry này trong git log)

## 24. CURRENT HANDOVER SUMMARY

Current stable commit: (xem git log — commit ngay sau `9d81244`, message nhắc "Bước 1")
System status: Backend/frontend chạy được, 87/87 test pass. Bước 1 (đa khung hình + confidence biển số) đã code xong và có test, NHƯNG chưa verify tay qua browser với dữ liệu thật (pipeline dev hiện tại không có xe đi qua camera). Có 14 video thật (`C:\Users\khucv\Downloads\tranning\`) chưa dùng để test integration.
Safe to deploy: UNKNOWN — chưa deploy thử lên VPS, `JWT_SECRET_KEY` hardcode là rủi ro nếu deploy production như hiện trạng.
Current development phase: Đang triển khai đợt nâng cấp lớn theo kế hoạch 7 bước đã duyệt (file plan riêng). **Bước 1/7 xong. Bước 3-7 CHƯA CODE — giao cho Cursor.**
Next recommended task: Bước 3 (ghép 2 camera) — xem SESSION LOG ngay phía trên và file plan đã duyệt để lấy thiết kế đầy đủ (schema, module, test, acceptance criteria). Sau Bước 3 → Bước 4 (auto cleanup) → Bước 5 (disk stats) → Bước 6 (backup SQLite) → Bước 7 (continuous recording, nặng nhất, mặc định TẮT tới khi có benchmark).
Critical warning for next developer (Cursor): **Không viết lại từ đầu bất kỳ phần nào đã DONE ở mục 5** — đặc biệt các mục đã có từ trước (Registered vehicle matching, Student/vehicle profile, Role permissions, Audit trail) VÀ 2 mục vừa xong trong session này (Multi-frame OCR, Confidence scoring). Làm đúng thứ tự Bước 3→4→5→6→7, mỗi bước: code → `pytest app/tests/ -v` (phải pass hết) → verify tay (dùng video training nếu liên quan tới pipeline camera) → **commit riêng từng bước** → cập nhật file này (mục 5, thêm SESSION LOG mới, mục 24) → mới sang bước kế. Bước 7 (continuous recording) mặc định `CONTINUOUS_RECORDING_ENABLED=False` — PHẢI benchmark FPS/latency trước khi đề xuất đổi mặc định, không tự ý đổi scope sang "chỉ ghi khi có người" nếu benchmark xấu — báo lại số liệu trước.
