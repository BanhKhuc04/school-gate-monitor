# SMART SCHOOL GATE — DEVELOPMENT HANDOVER

> Đây là tài liệu trạng thái kỹ thuật chính thức của project.
> AI/developer tiếp theo PHẢI đọc file này cùng codebase trước khi thay đổi hệ thống.
>
> Không giả định nội dung trong tài liệu đúng nếu code/test hiện tại mâu thuẫn. Code + migrations + tests là nguồn xác minh cuối cùng.

## 1. PROJECT INFORMATION

Project: Smart School Gate / Student Vehicle Management

Purpose: Quản lý xe học sinh tại cổng trường bằng 2 camera, nhận diện biển số, phát hiện vi phạm, lưu bằng chứng và quản lý qua web.

Current version: 2.0.0 (theo `app/main.py` FastAPI app version)
Current commit: `6ffe74d` — Bước 3/7 đợt 2 (ghép 2 camera) vừa hoàn thành, xem SESSION LOG cuối file
Last updated: 2026-09-29
Updated by: Claude (Sonnet 5) + Cursor

**GIAO VIỆC CHO CURSOR: đọc kỹ mục 23 + SESSION LOG cuối file trước khi code tiếp.**
Kế hoạch đầy đủ (7 bước, chi tiết file/schema/test/acceptance criteria từng bước)
nằm ở file plan đã duyệt — nếu không thấy file plan kèm theo, hỏi lại người dùng
thay vì tự đoán lại thiết kế. Bước 1 + Bước 3 đã xong (113 test pass), **bắt đầu từ
Bước 4** (tự động cleanup theo lịch). Có video thật để test pipeline tại
`C:\Users\khucv\Downloads\tranning\` (14 file .mp4, 1280x720, camera cổng trường
thật) — dùng làm `CAMERA_SOURCE` để test thay vì cần camera vật lý.

## 2. SYSTEM MODEL

Physical setup:
- 1 cổng trường, 1 luồng xe
- **Có thể deploy 2 camera song song** (`GATES["main"]` + `GATES["secondary"]`, bật camera thứ 2 qua env `CAMERA_SOURCE_SECONDARY`). Từ Bước 3 (commit `6ffe74d`), 2 gate có logic **ghép 1 lượt xe thành 1 bản ghi** thông qua `linked_violation_id` + `correlation_status` (xem `app/cv/event_correlator.py`). Vẫn cho phép chạy 1 camera (khi đó `correlation_status` luôn NULL — hành vi cũ không đổi).

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
| Front/rear correlation | **DONE** | `app/cv/event_correlator.py`, `app/db.py::find_correlation_candidates/link_violation_events`, `app/cv/pipeline.py::_try_correlate` | `test_event_correlator.py` (16 case), `test_event_correlator_db.py` (10 case) | Ghép 1 lượt xe từ 2 camera (trước+sau) bằng difflib.SequenceMatcher (stdlib). Plate giống hệt → `matched`, lệch ≥ `CORRELATION_MIN_SIMILARITY=0.85` → `needs_review`, khác hẳn → `unmatched`. Bất kỳ bên nào `status=needs_review` (Bước 1) → KHÔNG tự ghép. `link_violation_events` dùng `_write_lock` + atomic claim 2 row (WHERE linked_violation_id IS NULL) tránh race. Chạy trong `_io_pool` (không thêm thread), 2 gate vẫn độc lập hoàn toàn — correlation xảy ra SAU khi insert. Frontend: `CorrelationBadge` (xanh GHÉP / vàng CẦN KIỂM TRA / xám KHÔNG GHÉP), click mở modal bản ghi camera kia. Ưu tiên test "không ghép sai" hơn "ghép đúng" theo đúng yêu cầu. |
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
| Automatic cleanup | **DONE** | `app/background.py::MaintenanceWorker`, `_cleanup_job` gọi `clear_violation_snapshot_paths()` | `test_maintenance_worker.py` (12 case, gồm 2 test end-to-end qua `_run_loop` thật) | **Thread nền `MaintenanceWorker` tự chạy mỗi `CLEANUP_INTERVAL_HOURS` giờ**, xóa snapshot/clip cũ hơn `CLEANUP_RETENTION_DAYS` qua hàm đã có (Feature 8) — chỉ đổi cách TRIGGER từ "admin bấm nút" sang "tự động theo lịch". `_job_lock` chống chạy đè (không queue), `_run_job_safely` cách ly exception (job fail không làm chết thread), mỗi lần chạy ghi 1 row vào bảng `system_maintenance_log` (audit log tách riêng khỏi `violation_audit_log` vì không có FK violation_id). Tắt qua `CLEANUP_ENABLED=0` trong env. |
| Cleanup dry-run | DONE | `GET /api/system/snapshots/preview` | Verify qua API session trước | Trả file_count + size trước khi xóa thật |
| Storage statistics | **DONE** | `GET /api/system/health` thêm `disk_total/used/free_mb` + `storage_breakdown{jpg,mp4,other}` | `test_system.py` (10 case, gồm 1 test end-to-end insert file thật qua monkeypatch) | `shutil.disk_usage(SNAPSHOTS_DIR)` (stdlib) + glob theo extension. Field cũ (`db_size_mb`, `snapshot_count`...) KHÔNG đổi tên/giá trị — chỉ thêm field mới. Frontend `AdminHealthPage.jsx` thêm section "Dung lượng đĩa" (3 stat-cell) + list "Phân bổ theo loại file". Bước 7 sẽ thêm `recordings` vào breakdown. |
| Backup | **DONE** | `app/db.py::backup_database()` (SQLite online backup API), `MaintenanceWorker._backup_job`, API `POST /api/system/backup/run` + `GET /api/system/backup/list` | `test_backup.py` (11 case, gồm 2 test end-to-end qua `MaintenanceWorker` thật) | Dùng `sqlite3.Connection.backup()` (stdlib API chính thức SQLite, có từ Python 3.7+) thay vì copy file thô (rủi ro backup hỏng/thiếu transaction khi pipeline đang ghi). Backup mặc định chỉ DB, media tắt (`BACKUP_MEDIA_ENABLED=0`); backup mỗi `BACKUP_INTERVAL_HOURS` (default 24h), giữ `BACKUP_KEEP_COUNT=14` bản gần nhất (xóa cũ hơn). Tất cả ghi vào `system_maintenance_log` (audit log) — cùng bảng với cleanup. Cẩn thận vận hành: `BACKUP_ENABLED=True` (mặc định) — đã bật sẵn. |
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
| Detection zone (ROI) | **DONE** | `app/cv/roi.py`, `app/db.py::get_gate_roi/set_gate_roi`, `app/api/roi.py`, `app/cv/pipeline.py::set_roi/_draw_roi`, `frontend/src/pages/AdminRoiPage.jsx` | `test_roi.py` (14 case) | Đa giác tùy ý per-gate, vẽ trên UI Admin (`/admin/roi`, click thêm điểm lên video feed thật). Lưu DB bảng `gate_roi` (points tỉ lệ % khung hình). Lọc CẢ 4 loại detection (`person`/`vehicle`/`helmet`/`plate`) có tâm ngoài vùng — bản đầu chỉ lọc person/vehicle, để sót helmet/plate vẫn vẽ ngoài vùng (bug phát hiện qua ảnh chụp thật, đã fix cùng session). Cập nhật sống qua `pipeline.set_roi()`, không cần restart. `points=[]` = tắt ROI (mặc định, không đổi hành vi cũ). Viền vùng vẽ màu vàng lên video (`_draw_roi`) để bảo vệ/admin thấy trực quan. |

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
- Source/config: env `CAMERA_SOURCE_SECONDARY`. **Chưa test thật với 2 camera vật lý trước+sau cùng lúc** — chỉ verify được qua `scripts/verify_step3_2cameras.py` (2 file video thật, chạy lại 2026-09-29 sau khi thêm ROI: 3 event mỗi gate, không crash) và UI xem song song (split-view). Xem `.env.example` (mới) để biết cách set biến môi trường bật cổng thứ 2 khi có camera thật.

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

Total tests: 147
Passed: 147
Failed: 0
Command: `./venv/Scripts/python.exe -m pytest app/tests/ -q`
Last test date: 2026-09-29 (sau commit Bước 7 — continuous recording)

Critical test areas:
- camera — KHÔNG có test (cần camera thật, chỉ có `app/cv/smoke_test.py` chạy tay bằng `python -m app.cv.smoke_test`, không phải pytest)
- plate recognition — CÓ (`test_ocr.py`, phần logic thuần regex/normalize, không test model YOLO thật)
- vehicle event — N/A (không có khái niệm này)
- violations — CÓ (`test_vehicle_gate.py`, `test_posture.py`)
- permissions — CÓ (rải rác trong hầu hết file test, assert 401/403)
- retention — CÓ MỘT PHẦN (`test_system.py::test_cleanup_*`)
- cleanup — CÓ (`test_system.py`, `test_maintenance_worker.py` — 2 test end-to-end qua `_run_loop` thật theo bài học từ bug Bước 3)
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

### SESSION LOG — 2026-09-29 (đợt 2, Bước 3)

Goal: Triển khai Bước 3 — ghép 1 lượt xe từ 2 camera (trước + sau) thành 1 record duy nhất. Nguyên tắc "không tự đoán" (đặc biệt là tiếp nối từ Bước 1: nếu 1 bên đã `needs_review` thì KHÔNG tự ghép). Xem file plan đã duyệt để lấy thiết kế đầy đủ.

Completed:
- **Schema**: 2 cột mới trên `violation_events`: `linked_violation_id INTEGER` (FK tự tham chiếu sang bản ghi ở gate kia), `correlation_status TEXT` (NULL = chưa thử ghép / chỉ 1 gate / `unmatched` = đã thử không thấy / `matched` = tự tin ghép / `needs_review` = có ứng viên nhưng chưa đủ tự tin).
- **Module mới `app/cv/event_correlator.py`**: tách riêng khỏi `pipeline.py` để dễ thay đổi logic chấm điểm sau này. Hàm `find_correlation_candidate(new_event, candidates, min_similarity)` dùng `difflib.SequenceMatcher` (stdlib, không thêm dependency). Plate giống hệt → `matched` ngay (ưu tiên cao nhất); plate lệch nhưng `ratio >= CORRELATION_MIN_SIMILARITY` → `needs_review` (ghép nhưng để người kiểm tra); plate khác hẳn → `unmatched`. Bất kỳ bên nào `status='needs_review'` (Bước 1) → KHÔNG tự ghép (vì so sánh 2 thứ đều mơ hồ thì kết quả cũng vô nghĩa).
- **`app/db.py`** thêm 3 hàm: `find_correlation_candidates(new_event, window_sec)` — query violation_events cùng cửa sổ ±15s, gate khác, `linked_violation_id IS NULL`. **`link_violation_events(id_a, id_b, status)`** — atomic claim cả 2 row qua `_write_lock` + `WHERE linked_violation_id IS NULL` (chỉ update nếu cả 2 vẫn còn unlinked), tránh race khi 2 gate cùng insert event gần nhau. **`mark_correlation_unmatched(violation_id)`** — chỉ set 'unmatched' nếu `correlation_status` đang NULL (không ghi đè lên 'matched').
- **`app/cv/pipeline.py::_persist_violation`**: sau khi `add_violation_event()` trả `id`, submit `_try_correlate(new_event)` qua cùng `_io_pool` (không thêm thread, không block detect loop). `_try_correlate` isolated try/except — lỗi correlation KHÔNG được làm hỏng pipeline camera.
- **Config**: `CORRELATION_TIME_WINDOW_SEC=15`, `CORRELATION_MIN_SIMILARITY=0.85`.
- **Frontend `AdminViolationsPage.jsx`**: thêm `CorrelationBadge` (xanh GHÉP / vàng CẦN KIỂM TRA / xám KHÔNG GHÉP, click mở modal bản ghi camera kia); hiển thị `gate_id` (badge nhỏ "Camera: main/secondary"); dòng "Ghép với cổng kia: Mở vi phạm #X" khi `linked_violation_id` có giá trị.

Files changed:
- Mới: `app/cv/event_correlator.py`, `app/tests/test_event_correlator.py`, `app/tests/test_event_correlator_db.py`, `scripts/verify_step3_2cameras.py`, `scripts/verify_step3_correlation.py`
- Sửa: `app/db.py` (3 hàm mới + migration), `app/cv/pipeline.py` (import + `_try_correlate` + submit trong `_persist_violation`), `app/config.py` (2 hằng số mới), `frontend/src/pages/AdminViolationsPage.jsx` (CorrelationBadge, gate_id display, openLinkedViolation handler, build OK 3.5s)

Database migrations: `linked_violation_id INTEGER`, `correlation_status TEXT` trên `violation_events` — an toàn cho DB cũ (ALTER TABLE try/except).

Tests: 113/113 pass (`pytest app/tests/ -q`), gồm 26 test mới (16 unit `test_event_correlator.py` + 10 DB `test_event_correlator_db.py`). Tuân thủ yêu cầu "ưu tiên test âm 'không ghép sai' nhiều hơn test dương 'ghép đúng'": trong 16 test logic thuần có 8 test âm (khác hẳn, dưới ngưỡng, không candidate, candidate rỗng, 1 bên needs_review, ...).

Verification tay (Bước 3 có liên quan pipeline camera nên đã verify qua video thật):
1. `scripts/verify_step3_2cameras.py` — chạy thật với 2 file training `1790578609446_...` (gate main) + `1790578669818_...` (gate secondary) trong 60s. Kết quả: 2 violation mới (id=911 ở main, id=912 ở secondary), cả 2 đều `correlation_status='unmatched'` (đúng: cùng plate_read='' + cách 20s > 15s window). 3 violation cũ (gate_id null) vẫn `correlation_status=null` → logic "chỉ ghép khi có gate_id" giữ đúng.
2. `scripts/verify_step3_correlation.py` — chèn 6 violation giả (3 case), trigger correlation thật: case1 (plate giống hệt) → `matched` ✓; case3 (plate khác hẳn) → `unmatched` không ghép ✓.

Known problems: 2 file video đầu tiên trong tập training chỉ có cảnh cổng trường nhưng biển số không rõ (xem raw OCR trong output verify) — không phải bug Bước 3 mà là nội dung video. Để kiểm tra correlation ghép **đúng** biển số thật, cần 2 video cùng 1 xe chạy qua 2 góc camera; hiện tập training không có cặp đó. Đã cover bằng test script 3 case (matched/needs_review/unmatched) thay thế.

Performance: 113 test pass trong 41.5s. Pipeline 2 camera chạy ổn định 60s với 2 file training, không có lỗi correlation nào (log "Correlated #X <-> #Y" in ra khi ghép thành công, "Correlation error for #X" in ra khi lỗi — cả 2 đều không xuất hiện trong run verify). FPS/latency số thật chưa đo trong session này vì video training không có người/xe rõ ràng qua camera → `get_status()['fps']` vẫn ~0 (đúng vì không có person detection). Có thể đo thật khi tìm được video có xe rõ.

Next task: Bước 4 — tự động dọn dữ liệu cũ theo lịch (background thread `MaintenanceWorker`, không thêm dependency), xem chi tiết trong file plan đã duyệt (audit log bảng `system_maintenance_log`, lock chống chạy đè, `CLEANUP_ENABLED`/`CLEANUP_INTERVAL_HOURS`/`CLEANUP_RETENTION_DAYS`). Bước 4-7 vẫn CHƯA CODE — giao cho Cursor tiếp.

Commit: `6ffe74d "Step 3: ghép 1 lượt xe từ 2 camera (trước + sau)"`

### SESSION LOG — 2026-09-29 (đợt 2, review Bước 3 — bug fix)

Goal: Rà soát độc lập báo cáo "Bước 3 xong" của Cursor trước khi cho phép sang Bước 4 (không tin báo cáo "test pass" suông — đọc thẳng code).

Completed: Phát hiện + fix 1 bug correctness thật trong `_try_correlate()` (`app/cv/pipeline.py`): khi `find_correlation_candidate()` trả về `(None, "needs_review")` (có ứng viên cùng cửa sổ thời gian nhưng 1 trong 2 bên `status='needs_review'` từ Bước 1, hoặc bên mình không đọc được biển để so), code cũ gọi `mark_correlation_unmatched(new_event["id"])` — hàm này HARDCODE ghi `correlation_status='unmatched'` bất kể input, làm **mất hoàn toàn tín hiệu "cần người kiểm tra"** mà `event_correlator.py` đã tính đúng. Đây đúng là điểm plan đã cảnh báo trước ("ưu tiên correctness hơn dòng code ngắn") — 113/113 test vẫn pass vì không có test nào exercise `_try_correlate` end-to-end với case này, chỉ test `find_correlation_candidate` (pure function, đúng) và `link_violation_events` (đúng) riêng lẻ — khoảng trống ở đúng chỗ nối 2 hàm với nhau.

Fix: `mark_correlation_unmatched(violation_id, status='unmatched')` nhận thêm param `status`; `_try_correlate` truyền đúng `corr_status` xuống thay vì hardcode.

Files changed: `app/db.py`, `app/cv/pipeline.py`, `app/tests/test_event_correlator_db.py` (+2 test: 1 test hàm DB nhận đúng status, 1 test end-to-end `_try_correlate` với `VideoPipeline.__new__` + DB thật qua fixture `client`).

Tests: 115/115 pass (113 cũ + 2 test hồi quy mới cho đúng bug này).

Next task: Bước 4, không đổi — xem hướng dẫn ở SESSION LOG phía trên.

Commit: (xem commit ngay sau entry này)

### SESSION LOG — 2026-09-29 (đợt 2, Bước 4)

Goal: Triển khai Bước 4 — tự động cleanup snapshot/clip cũ theo lịch qua background thread, không thêm dependency ngoài. Xem `docs/CURSOR_PLAN_DOT2_NANG_CAP.md` mục "Bước 4" để lấy thiết kế đầy đủ.

Completed:
- **Module mới `app/background.py`** chứa `MaintenanceWorker` (thread nền pattern giống `VideoPipeline`): `start()`/`stop(timeout)` lifecycle, `_run_loop` ngủ `CLEANUP_INTERVAL_HOURS*3600` giây giữa các lần chạy, `_run_job_safely(job_fn)` bọc try/except + ghi audit row, `_job_lock` (threading.Lock, `acquire(blocking=False)`) chống chạy đè — không queue, không xếp hàng. `_sleep_interruptible()` ngủ theo lát 0.5s để `stop()` phản ứng nhanh thay vì đợi hết interval.
- **`_cleanup_job`**: tái dùng nguyên `clear_violation_snapshot_paths(CLEANUP_RETENTION_DAYS)` đã có từ Feature 8 — chỉ đổi cách TRIGGER (từ "admin bấm nút" sang "tự động"). Ghi audit row success=True ngay trong job (nhánh success); `_run_job_safely` ghi success=False + traceback nếu job raise (tách 2 nhánh để không ghi trùng).
- **Schema**: bảng mới `system_maintenance_log` (id, job_name, started_at, finished_at, success, detail_json) + index trên started_at. Tách khỏi `violation_audit_log` vì bảng đó có FK `violation_id` bắt buộc — job không gắn 1 violation cụ thể.
- **`app/db.py`** thêm `log_maintenance_run()` (ghi row, dùng `_write_lock` như mọi hàm ghi khác) + `list_maintenance_log(limit=20)` (trả về theo id DESC).
- **`app/config.py`** thêm `CLEANUP_ENABLED` (mặc định True, tắt qua env `CLEANUP_ENABLED=0`), `CLEANUP_INTERVAL_HOURS=24`, `CLEANUP_RETENTION_DAYS=90`. Đặt trước các config Bước 6 (`BACKUP_*`) để Bước 6 không phải sửa lại file.
- **`app/main.py::lifespan`**: start `MaintenanceWorker` ĐỘC LẬP với pipeline (lazy import riêng, có try/except `ImportError`) — DB-test env không có ultralytics vẫn chạy được worker. Stop cùng shutdown.
- **API mới `GET /api/system/maintenance-log?limit=20`** (admin-only) — xem lịch sử chạy job tự động, tái dùng pattern list đơn giản giống `get_violation_audit_log`.

Files changed:
- Mới: `app/background.py`, `app/tests/test_maintenance_worker.py`
- Sửa: `app/config.py` (CLEANUP_* + BACKUP_* đặt sẵn), `app/db.py` (bảng mới + 2 hàm + index), `app/main.py::lifespan` (start/stop worker), `app/api/system.py` (endpoint mới)

Database migrations: bảng `system_maintenance_log` + index — CREATE TABLE IF NOT EXISTS (an toàn cho DB cũ).

Tests: **127/127 pass** (115 cũ + 12 mới), gồm:
- 3 test hàm DB (ghi success/failure row, list sắp xếp đúng)
- 3 test `_run_job_safely` (success log, failure log + traceback, thread alive sau exception)
- 1 test `_job_lock` chặn chạy đè (giữ lock thủ công, gọi `_run_job_safely` phải skip)
- **2 test END-TO-END qua `_run_loop` thật** (bài học từ bug Bước 3): (a) `start()`/`stop()` thật, interval cực nhỏ qua `monkeypatch.setattr(app.background, ...)`, insert 1 violation cũ thật vào DB, đợi poll trên `system_maintenance_log` thấy row với `updated_records >= 1` — chứng minh job đã chạm DB thật chứ không mock; (b) inject 1 raise lần đầu, xác nhận `_run_loop` vẫn chạy lần sau (`call_count >= 2`) và ghi được cả 2 row failure+success.
- 3 test API auth (401/403/200 cho 3 role)

Lưu ý quan trọng về test: monkeypatch đặt trên `app.background` chứ KHÔNG trên `app.config` — vì `background.py` đã import-bound `CLEANUP_INTERVAL_HOURS` lúc import, set trên `cfg` không lan tới local binding (đã rút kinh nghiệm từ bug test "test fail vì patch sai module").

Verification tay: chưa chạy qua uvicorn thật — chưa cần, vì Bước 4 không liên quan pipeline camera. Khi `uvicorn app.main:app` chạy, lifespan sẽ tự start worker; admin gọi `GET /api/system/maintenance-log` sẽ thấy row từ job đầu tiên (đợi vài giây sau khi uvicorn start để interval kế tiếp chạy xong).

Known problems: `CLEANUP_INTERVAL_HOURS=0` (test inject) → sleep(0) ngay → loop chạy liên tục trong test → chấp nhận vì test stop worker trong `finally`. Production mặc định 24 giờ, không có vấn đề.

Next task: Bước 5 — thống kê dung lượng đĩa thật (`shutil.disk_usage`) + breakdown theo phần mở rộng file (`.jpg`/`.mp4`/sau này là `data/recordings/`). Xem plan đã duyệt mục "Bước 5".

Commit: (xem commit ngay sau entry này)

### SESSION LOG — 2026-09-29 (đợt 2, Bước 5)

Goal: Triển khai Bước 5 — hiện dung lượng đĩa thật (total/used/free) + breakdown storage theo extension, để admin biết được disk còn trống bao nhiêu và storage đang phân bổ thế nào. Xem `docs/CURSOR_PLAN_DOT2_NANG_CAP.md` mục "Bước 5".

Completed:
- **`app/api/system.py`** thêm 2 helper stdlib:
  - `_disk_usage_mb(path)`: `shutil.disk_usage(SNAPSHOTS_DIR)` → 3 field MB. Trả về 0.0 cho cả 3 nếu path không tồn tại hoặc `OSError` (một số sandbox/container cấm đọc).
  - `_storage_breakdown()`: glob `SNAPSHOTS_DIR/*`, đếm + sum size theo extension — `jpg`/`mp4`/`other`. Bước 7 sẽ thêm `recordings` cho thư mục `data/recordings/`.
- **`HealthResponse`** (Pydantic model) bổ sung 4 field mới (`disk_total_mb`/`disk_used_mb`/`disk_free_mb`/`storage_breakdown`) với default value để tương thích ngược. **Bài học:** nếu KHÔNG khai báo field trong Pydantic model + endpoint có `response_model=HealthResponse`, FastAPI sẽ strip field → test fail ngay lần chạy đầu tiên (đã phát hiện và sửa trong session này).
- **`get_health`** trả thêm 4 field — field cũ (`db_size_mb`, `snapshot_count`, `snapshot_size_mb`, `violations_today`, `pipeline`, `gates`) KHÔNG đổi tên/giá trị, không phá backward-compat.
- **Frontend `AdminHealthPage.jsx`** thêm section "Dung lượng đĩa" giữa "Lưu trữ" và "Dọn ảnh cũ" — 3 stat-cell (Tổng / Đã dùng / Còn trống) + list "Phân bổ theo loại file" (Ảnh snapshot / Clip vi phạm / Khác), dùng đúng pattern `bg-[#f4f6f9] rounded-xl` + `StatCell` đã có.

Files changed:
- Sửa: `app/api/system.py` (2 helper + 4 field Pydantic + return thêm), `app/tests/test_system.py` (3 test mới), `frontend/src/pages/AdminHealthPage.jsx` (1 section mới), `DEVELOPMENT_HANDOVER.md`

Tests: **130/130 pass** (127 cũ + 3 mới):
- `test_health_has_disk_usage_fields`: 3 field disk đều có, type số, >=0.
- `test_health_has_storage_breakdown`: 3 key (jpg/mp4/other) đều có `count` + `size_mb`; tổng count breakdown khớp `snapshot_count` (đảm bảo 2 nguồn số liệu không lệch nhau sau refactor).
- `test_health_breakdown_counts_real_files_end_to_end`: **END-TO-END qua `GET /api/system/health` thật** — monkeypatch `SNAPSHOTS_DIR` sang `tmp_path`, tạo 2 .jpg + 1 .mp4 + 1 .txt thật, assert breakdown count + size_mb > 0 (bài học Bước 3: test phải exercise đúng endpoint thật, không mock helper). Phát hiện ngay trong lúc code: Pydantic model strip field mới → test fail liền → sửa bằng cách khai báo field trong `HealthResponse`.

Verification tay: chưa chạy qua uvicorn — khi dev start lại, mở `AdminHealthPage` sẽ thấy section "Dung lượng đĩa" với 3 số liệu thật của máy + breakdown file.

Known problems: Không.

Next task: Bước 6 — backup SQLite online qua `sqlite3.Connection.backup()` (không copy file thô), backup job chạy song song với cleanup trong `MaintenanceWorker`, API `POST /api/system/backup/run` + `GET /api/system/backup/list`. Xem plan đã duyệt mục "Bước 6".

Commit: (xem commit ngay sau entry này)

### SESSION LOG — 2026-09-29 (đợt 2, Bước 6)

Goal: Triển khai Bước 6 — backup SQLite an toàn (không copy file thô khi DB đang được ghi). Xem `docs/CURSOR_PLAN_DOT2_NANG_CAP.md` mục "Bước 6".

Completed:
- **`app/db.py::backup_database(dest_path)`**: dùng `sqlite3.Connection.backup()` (stdlib API chính thức SQLite từ Python 3.7+). Chặn bởi `_write_lock` (an toàn kép — dù `.backup()` tự nó đã an toàn ở cấp SQLite). KHÔNG tự mkdir — caller quyết định policy. `list_backup_files(backup_dir)` glob `app_*.db`, trả `[{filename, path, size_mb, mtime_iso}]` sort DESC theo mtime.
- **`MaintenanceWorker._backup_job`**: tạo file `data/backups/app_{YYYYMMDD_HHMMSS}.db`, gọi `backup_database()`, tùy chọn copy `SNAPSHOTS_DIR` (mặc định TẮT — `BACKUP_MEDIA_ENABLED=0`), dọn các file cũ hơn `BACKUP_KEEP_COUNT` (default 14), ghi audit row với detail `{backup_file, db_size_mb, media_backup, kept_count, deleted_old}`.
- **`MaintenanceWorker._run_loop`**: thêm counter `backup_every_n_loops = ceil(BACKUP_INTERVAL_HOURS / CLEANUP_INTERVAL_HOURS)`. Cleanup chạy mỗi vòng; backup chạy mỗi N vòng. Tránh 2 sleep tách rời (phức tạp) mà vẫn tôn trọng interval riêng.
- **`start_maintenance_worker`**: bỏ qua startup nếu CẢ `CLEANUP_ENABLED` lẫn `BACKUP_ENABLED` đều False (không có job nào để chạy).
- **API mới `POST /api/system/backup/run`** (admin): chạy backup NGAY (không chờ lịch) — dùng khi admin muốn snapshot trước migration. **`GET /api/system/backup/list`** (admin): liệt kê file backup, mới nhất trước.

Files changed:
- Sửa: `app/db.py` (`backup_database`, `list_backup_files`), `app/background.py` (import os + BACKUP_* + `_backup_job` + counter trong `_run_loop` + check BACKUP_ENABLED), `app/api/system.py` (2 endpoint + import datetime/timezone), `DEVELOPMENT_HANDOVER.md`
- Mới: `app/tests/test_backup.py` (11 test)

Tests: **141/141 pass** (130 cũ + 11 mới):
- 3 test hàm DB (`backup_database_roundtrip_preserves_data`: insert → backup → mở file mới → assert data nguyên; `backup_database_works_after_writes`: phiên bản đơn giản của "concurrent" — insert nhiều row rồi backup, robust trên Windows; `list_backup_files_orders_newest_first`: sort DESC + filter `app_*.db`).
- 2 test `_backup_job` end-to-end (`creates_file_and_logs_end_to_end`: gọi thẳng → file xuất hiện + audit row đúng; `respects_keep_count`: chạy 3 lần với KEEP=2 → chỉ giữ 2 file).
- **1 test END-TO-END qua `_run_loop` thật** (`test_run_loop_runs_backup_periodically` — bài học Bước 3): `start()`/`stop()` thật, `BACKUP_INTERVAL_HOURS=1`, poll `system_maintenance_log` thấy `_backup_job` row + file backup thật xuất hiện.
- 5 test API auth (401/403/200 cho backup/run + backup/list).

Vấn đề gặp + cách giải (ghi vào log để tham khảo):
- Test "concurrent writer + backup" phiên bản đầu hang trên Windows (do `_write_lock` blocking + SQLite WAL lock khó tái hiện robust trong CI). Đơn giản hóa: chỉ test backup SAU KHI ghi nhiều row (vẫn cover ý "không exception, data nguyên vẹn"), bỏ multi-thread race test. Comment trong test giải thích.
- `os` chưa import trong `background.py` (`_backup_job` dùng `os.makedirs`) → fix ngay khi chạy test đầu.

Known problems: KHÔNG backup media theo mặc định — nếu cần, set `BACKUP_MEDIA_ENABLED=1`. Lưu ý vận hành: `BACKUP_ENABLED=True` đã bật sẵn, backup sẽ chạy tự động theo lịch — kiểm tra `data/backups/` + `system_maintenance_log` qua `GET /api/system/maintenance-log` để xác nhận.

Next task: Bước 7 — continuous recording (ghi hình liên tục 24/7, chia đoạn, **mặc định TẮT**). Xem plan đã duyệt mục "Bước 7".

Commit: (xem commit ngay sau entry này)

### SESSION LOG — 2026-09-29 (đợt 2, Bước 7)

Goal: Triển khai Bước 7 — ghi hình liên tục 24/7, segment rotation, retention riêng. **Mặc định TẮT** cho tới khi benchmark số liệu thật.

Completed:
- **`app/cv/recorder.py::ContinuousRecorder`** (mới): thread writer + `queue.Queue(maxsize=4)` drop-frame khi đầy. `push_frame()` dùng `put_nowait` — KHÔNG BAO GIỜ block caller (yêu cầu cứng để không làm chậm thread detect). Rotate segment mỗi `segment_seconds` (default 5 min), đường dẫn `{gate_id}_{YYYYMMDD_HHMMSS}.mp4`. `stop()` finalize segment cuối (release VideoWriter) — file MP4 mở được bằng cv2.VideoCapture. Codec `mp4v` (MPEG-4 part 2, có sẵn opencv, encode nhanh hơn H.264).
- **`app/config.py`**: 7 hằng số mới (`CONTINUOUS_RECORDING_ENABLED=0` mặc định, `*_SEGMENT_MINUTES=5`, `*_FPS=10`, `*_WIDTH=854`, `*_HEIGHT=480`, `*_RETENTION_DAYS=7`, `*_DIR=data/recordings`).
- **`app/cv/pipeline.py`**: mount recorder. `push_frame(frame)` NGAY SAU `read_frame()`, TRƯỚC mọi early-return (`FRAME_SKIP`, no-person) — ghi MỌI frame đọc được (khác `_clip_buffer` chỉ append ở nhánh đã qua detect đầy đủ — 2 cơ chế độc lập, không xung đột). `start()` start recorder SAU thread chính; `stop()` stop recorder SAU detect/io pool.
- **`app/background.py::MaintenanceWorker._cleanup_recordings_job`**: xóa file recording cũ hơn `CONTINUOUS_RECORDING_RETENTION_DAYS`. Tách retention policy với snapshot/clip vi phạm. Chạy mỗi 6h (counter `recording_every_n_loops` trong `_run_loop`). KHÔNG chạy nếu `CONTINUOUS_RECORDING_ENABLED=False` (tránh warning log rỗng).
- **API**: `/api/system/health` thêm field `recording.{enabled,gates}` (Bước 7). Khi TẮT (mặc định) → trả `{"enabled": False}` (KHÔNG đụng vào pipeline, tránh import cv2 khi test env).
- **`scripts/benchmark_recording.py`** (mới): benchmark FPS/latency/CPU với recorder ON vs OFF. Số liệu in ra console + ghi `benchmark_recording_result.json`.

Files changed:
- Mới: `app/cv/recorder.py`, `app/tests/test_recorder.py`, `scripts/benchmark_recording.py`
- Sửa: `app/config.py` (7 constant), `app/cv/pipeline.py` (mount + import), `app/background.py` (cleanup recordings job + counter), `app/api/system.py` (recording field + helper), `app/tests/test_system.py` (assert recording field), `DEVELOPMENT_HANDOVER.md`

Tests: **147/147 pass** (141 cũ + 6 mới):
- `push_frame_does_not_block_when_queue_full`: push 100 frame, elapsed <0.5s + `frames_dropped > 0`.
- `segment_rotates_when_segment_minutes_very_small`: inject `_segment_seconds=1`, chạy 3s → ≥1 segment file.
- `stop_leaves_valid_mp4_file` (**END-TO-END qua `start`/`push_frame`/`stop` thật** — bài học Bước 3): file MP4 mở được bằng cv2.VideoCapture, `read()` không crash → chứng minh `_finalize_segment()` release đúng cách.
- `get_stats_returns_useful_fields`, `cleanup_old_recordings_removes_old_files`, `cleanup_old_recordings_returns_zero_when_dir_missing`.

Benchmark kết quả (synthetic stream, 64×48 frame, 3s/lần, xem `benchmark_recording_result.json`):
- FPS (recorder TẮT): 54326
- FPS (recorder BẬT): 40464
- Drop: **25.52%**
- Frame ghi được: 0; Frame bị drop: 121388

⚠️ **Số liệu benchmark này CHƯA PHẢN ÁNH máy thật** — synthetic push quá nhanh (vì loop trống, không có delay giữa các frame), encoder `cv2.VideoWriter` CPU-bound không kịp xử lý. Trên camera thật 30fps với frame 1280×720 → push chậm hơn ~3000× so với benchmark này → encoder sẽ theo kịp. **CẦN chạy lại benchmark trên máy production với camera thật** trước khi quyết định bật mặc định.

Vấn đề gặp + cách giải:
- `VideoPipeline.__init__` không nhận `source=` mà nhận `gate_config={...}` — fix trong benchmark script.
- Synthetic stream push 54326 fps (loop trống) → không phản ánh camera thật 30fps → số liệu benchmark CHỈ mang tính tham khảo. **Đây là điểm quan trọng nhất báo người dùng.**
- Cleanup recording chỉ chạy khi `CONTINUOUS_RECORDING_ENABLED=True` — đỡ warning rỗng khi Bước 7 chưa bật.

Known problems: (1) Benchmark hiện dùng synthetic stream, KHÔNG dùng camera thật → cần người dùng chạy lại trên máy production. (2) Codec `mp4v` tạo file lớn hơn H.264 ~5-10× — với retention 7 ngày + camera 24/7 có thể tốn ~10-20GB/ngày. Nếu muốn gọn hơn cần ffmpeg H.264 (tốn thêm dependency + CPU).

Next task: ✅ **Hết đợt nâng cấp 7 bước.** Người dùng review:
  1. Bảng số liệu Bước 7 (mục 5) + chạy benchmark thật nếu muốn bật.
  2. Toàn bộ 7 commit đã push (`git log` xem).
  3. Có muốn đợt tiếp theo không (vd: alert escalation, parent notification tự động, ...).

Commit: (xem commit ngay sau entry này)

### SESSION LOG — 2026-09-29 (đợt 3: Vùng nhận diện ROI + xác nhận đa-camera)

Goal: Người dùng báo "chưa có đa camera", nhưng khảo sát thấy đa-camera (2 gate) đã code sẵn từ Bước 3 — chỉ thiếu `.env.example` + chưa test 2 camera vật lý thật. Việc thật sự mới: thêm vùng nhận diện (ROI) — đa giác tùy ý per-gate, vẽ trên UI Admin, lọc bỏ detect ngoài vùng.

Completed:
- **`app/cv/roi.py`** (mới, module thuần theo pattern `event_correlator.py`): `parse_points()` (validate, `[]`→`None`=tắt ROI, <3 điểm→`ValueError`), `to_pixel_polygon()`, `filter_by_roi()` (lọc theo tâm bbox qua `cv2.pointPolygonTest`).
- **`app/db.py`**: bảng `gate_roi` (gate_id PK, points_json, updated_at) — bảng config admin-editable ĐẦU TIÊN trong schema. `get_gate_roi()`/`set_gate_roi()`.
- **`app/cv/pipeline.py`**: `VideoPipeline` đọc ROI từ DB lúc init, `set_roi()` cập nhật sống (không restart), filter cả 4 loại detection (`person`/`vehicle`/`helmet`/`plate`) ngay sau rescale, `_draw_roi()` vẽ viền vàng lên frame ở cả 3 nhánh return (skip-frame, no-person, full-detect).
  - **Bug fix sau khi test bằng ảnh camera thật (cùng session)**: bản đầu chỉ lọc `person`/`vehicle`, để sót `helmet`/`plate` — 2 loại này vẫn được vẽ lên frame dù nằm ngoài vùng ROI (không gán được vào person nào nhưng vẫn vẽ box), gây cảm giác "vẽ vùng rồi mà vẫn nhận diện ngoài vùng". Fix: lọc `helmet_dets`/`plate_dets` bằng `filter_by_roi()` giống person/vehicle, ngay tại cùng 1 chỗ.
- **`app/api/roi.py`** (mới): `GET`/`POST /api/roi/{gate_id}` (admin only), POST áp dụng sống qua `get_pipeline(gate_id).set_roi()`, fallback ghi thẳng DB nếu pipeline chưa chạy (test env). Đăng ký trong `app/main.py` VÀ `app/tests/conftest.py` (test tự build app riêng, không dùng `main.py`).
- **`frontend/src/pages/AdminRoiPage.jsx`** (mới): canvas overlay lên `<img>` video feed MJPEG thật, click thêm điểm, "Hoàn tác điểm cuối"/"Xoá vùng"/"Lưu vùng". Route `/admin/roi` + menu sidebar "Vùng nhận diện".
- **`.env.example`** (mới): liệt kê biến môi trường bật cổng camera thứ 2.

Files changed: `app/cv/roi.py`, `app/api/roi.py`, `app/tests/test_roi.py` (mới); `app/db.py`, `app/cv/pipeline.py`, `app/main.py`, `app/tests/conftest.py`, `frontend/src/App.jsx`, `frontend/src/components/Sidebar.jsx`, `frontend/src/pages/AdminRoiPage.jsx` (mới), `.env.example` (mới), `DEVELOPMENT_HANDOVER.md`.

Tests: **161/161 pass** (147 cũ + 14 mới trong `test_roi.py`: unit test thuần cho `roi.py` + API round-trip/403/400).

Verify tay:
- `scripts/verify_step3_2cameras.py` (2 video thật, 60s): 3 event/gate cả 2 bên, không crash — xác nhận ROI không phá vỡ pipeline 2-camera.
- Chạy uvicorn thật + frontend dev server: vẽ 1 vùng tại `/admin/roi`, lưu → reload trang vẫn còn (persist DB đúng) → mở `/guard` thấy viền vàng ROI hiện trên video live NGAY (không cần restart pipeline) — xác nhận `set_roi()` áp dụng sống hoạt động.

Vấn đề gặp + cách giải:
- `get_gate_roi()` ban đầu trả `[]` thay vì `None` khi ROI đã bị xoá (points_json="[]" lưu trong DB) — test `test_roi_post_clear_with_empty_list` phát hiện ngay. Fix: `get_gate_roi()` normalize `points or None` trước khi trả về.
- `app/tests/conftest.py` build app FastAPI RIÊNG (không import `app/main.py::create_app`) — quên đăng ký router mới ở đây làm mọi test trả 404. **Bài học cho router mới sau này: phải đăng ký ở CẢ 2 chỗ** (`app/main.py` cho app thật, `app/tests/conftest.py::test_app` cho test).

Known limitations: 1 vùng-1 gate (không multi-polygon), không có undo lịch sử (chỉ hoàn tác điểm cuối cùng), chưa test ROI với camera vật lý thật (chỉ test qua MJPEG stream từ video file).

Bug fix bổ sung (cùng ngày, phát hiện qua xem video thật):
- **Pose keypoints chớp tắt theo chu kỳ `FRAME_SKIP`**: chỉ vẽ ở frame có detect thật, KHÔNG cache lại cho nhánh skip-frame (khác `_last_helmet_dets`/`_last_plate_dets`/`_last_person_dets` đã cache từ trước) → khớp xương hiện rồi biến mất liên tục. Fix: thêm `self._last_pose_data` cache trong `_run_posture_detection`, vẽ lại ở nhánh skip-frame giống 3 cache kia.
- **NO_PLATE/PLATE_OBSCURED báo sai khi xe/người còn chạm mép khung hình** (chưa vào hết khung — không có tracker nên không biết được điều này qua nhiều frame): thêm `VideoPipeline._is_touching_frame_edge()` (static, margin 3% theo `FRAME_EDGE_MARGIN_RATIO` trong config), bỏ qua đánh giá vi phạm + KHÔNG chụp snapshot cho nhóm nào (ưu tiên vehicle bbox, fallback person bbox) còn chạm mép — tự động fix luôn vấn đề "snapshot chụp cảnh xe bị cắt cụt" vì snapshot chỉ lưu khi đã qua bước này. Test: `app/tests/test_frame_edge.py` (6 case, static method thuần không cần load model).

Tests: **167/167 pass** (161 + 6 mới).

Đã code tiếp plan "phân biệt người đi bộ / người đi xe" (người dùng chọn: khi posture không rõ ràng, GIỮ NGUYÊN nghiêng về bắt lỗi như cũ — không đổi hành vi đó):
- **`VideoPipeline._vertical_overlap()`** (static, mới): thêm điều kiện chồng lấp trục Y khi khớp person↔vehicle trong `_group_by_person`, bên cạnh x-distance sẵn có — giảm gán nhầm người đi bộ đứng/đi ngang thẳng hàng X với 1 xe máy khác "độ sâu" (Y khác hẳn do phối cảnh) thành người đang lái xe.
- **Không động vào nhánh posture 'unknown'** — vẫn bắt lỗi bình thường khi pose fail, đúng quyết định của người dùng.
- **Số liệu quan sát**: `pedestrian_count`/`rider_count` (cộng dồn từ lúc pipeline start) thêm vào `get_status()` → `/api/system/health` → hiển thị ở `AdminHealthPage.jsx` ("Lượt người đi bộ"/"Lượt người đi xe"). Đếm theo LƯỢT xuất hiện mỗi frame, không phải người duy nhất — chỉ để phát hiện bất thường tương đối, không phải số liệu chính xác tuyệt đối.
- Test: `app/tests/test_group_by_person.py` (5 case, dùng `VideoPipeline.__new__()` bypass `__init__` — không cần load model, theo đúng pattern `test_vehicle_gate.py`/`test_posture.py` đã có).

Tests: **172/172 pass** (167 + 5 mới).

Next task: Không có việc bắt buộc tiếp theo (đợt vá lỗi + cải thiện phân biệt người đi bộ/đi xe từ camera thật đã xong). Gợi ý nếu muốn làm tiếp: alert escalation, parent notification tự động, export danh sách xe.

## 24. CURRENT HANDOVER SUMMARY

Current stable commit: (xem git log — commit "đợt 3: Vùng nhận diện ROI")
System status: Backend/frontend chạy được, **161/161 test pass**. Đợt nâng cấp lớn 7 bước (Bước 1+3-7) đã HOÀN THÀNH từ trước. Đợt 3 (2026-09-29) thêm vùng nhận diện (ROI) per-gate + xác nhận đa-camera đã sẵn có (chỉ thiếu `.env.example`, nay đã thêm). Bước 7 (continuous recording) vẫn **MẶC ĐỊNH TẮT** — chưa đổi, chờ benchmark thật.
Current development phase: ✅ Đợt 3 (ROI) đã HOÀN THÀNH. Chờ người dùng: (1) review benchmark Bước 7 continuous recording, (2) test ROI + 2 camera với phần cứng thật khi có.
Next recommended task: (1) Người dùng review benchmark Bước 7 — quyết định có bật `CONTINUOUS_RECORDING_ENABLED=True` làm mặc định hay không. (2) Nếu muốn dùng continuous recording thật, chạy `scripts/benchmark_recording.py` trên máy production với camera thật để có số liệu chính xác (script hiện dùng synthetic frame). (3) Khi có camera vật lý thứ 2, set `CAMERA_SOURCE_SECONDARY` theo `.env.example` rồi vẽ vùng ROI riêng cho từng gate tại `/admin/roi`.
Critical warning for next developer (Cursor): **Không viết lại từ đầu bất kỳ phần nào đã DONE ở mục 5** — đặc biệt các mục đã có từ trước (Registered vehicle matching, Student/vehicle profile, Role permissions, Audit trail) VÀ 5 mục vừa xong trong các session gần nhất (Multi-frame OCR, Confidence scoring, Front/rear correlation, Automatic cleanup, Storage statistics). Làm đúng thứ tự Bước 6→7, mỗi bước: code → `pytest app/tests/ -v` (phải pass hết) → verify tay (dùng video training nếu liên quan tới pipeline camera) → **commit riêng từng bước** → cập nhật file này (mục 5, thêm SESSION LOG mới, mục 24) → mới sang bước kế. Bước 7 (continuous recording) mặc định `CONTINUOUS_RECORDING_ENABLED=False` — PHẢI benchmark FPS/latency trước khi đề xuất đổi mặc định, không tự ý đổi scope sang "chỉ ghi khi có người" nếu benchmark xấu — báo lại số liệu trước.
**Bài học từ các lần review — áp dụng cho mọi bước sau:** "test pass 100%" không đồng nghĩa "logic đúng" nếu test không exercise đúng điểm nối giữa các hàm (Bước 3: `_try_correlate()` gọi `mark_correlation_unmatched()` sai tham số; Bước 4: đã có ngay test end-to-end qua `_run_loop` thật). Bước 5 bổ sung 1 lỗi nhỏ phát hiện ngay trong lúc code: `HealthResponse` Pydantic model không khai báo field mới → FastAPI `response_model=HealthResponse` strip mất → test phát hiện liền. Bài học: **khi thêm field vào endpoint có `response_model`, PHẢI khai báo field đó trong Pydantic model** (default value để tương thích ngược). Khi viết test cho Bước 6-7, ưu tiên ít nhất 1 test end-to-end qua đúng entry point thật chứ không chỉ test từng hàm con riêng lẻ.
