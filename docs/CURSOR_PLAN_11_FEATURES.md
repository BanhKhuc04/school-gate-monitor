# Kế hoạch phát triển 11 tính năng — School Gate Monitor

## Context

Dự án `D:\Work\Project_motorbike` là hệ thống giám sát cổng trường bằng CV (helmet/plate/pose detection qua YOLO + EasyOCR), backend FastAPI + SQLite, frontend React/Vite/Tailwind v4. Người dùng thấy phần mềm hiện tại "đơn giản, đơn điệu" và muốn bổ sung 11 tính năng đã liệt kê trước đó để tăng sức hút và giá trị thực tế (điều tra vi phạm, phân quyền giáo viên, audit trail, v.v.).

Tài liệu này là **spec kỹ thuật chi tiết để giao cho Cursor thực thi liên tục** — không phải mô tả mơ hồ. Mỗi mục nêu rõ: file nào, hàm/route nào, logic chính xác, và lý do chọn cách làm đó (để Cursor không tự sáng tạo lệch hướng). Toàn bộ thiết kế **tái dùng pattern đã có trong repo** (migration `ALTER TABLE` try/except, `require_role`, `_write_lock`, style component React hiện tại, `recharts` đã cài sẵn...) — không thêm thư viện/framework mới trừ khi ghi rõ.

Đã xác nhận với người dùng: mục "xem lại video" sẽ quay **clip ngắn 3-5s thật** (không chỉ nâng cấp xem ảnh tĩnh), chấp nhận tốn thêm CPU/RAM/disk.

Nghiên cứu nền tảng đã thực hiện đầy đủ trên: `app/db.py`, `app/schemas.py`, `app/api/{admin,users,system,guard}.py`, `app/auth.py`, `app/config.py`, toàn bộ `app/cv/{detector,ocr,pipeline,pose,capture}.py`, và toàn bộ frontend liên quan (`App.jsx`, `AuthContext`, `RequireRole`, `api/client.js`, tất cả `pages/Admin*.jsx`, `Layout/Sidebar`, `utils/*`, `index.css`, `package.json`). Các quyết định dưới đây bám sát cấu trúc thật đã đọc, không suy đoán.

## Thứ tự thực thi (Cursor phải làm THEO ĐÚNG THỨ TỰ NÀY — mỗi phase phụ thuộc phase trước)

1. **Phase 0 — Nền tảng schema & config** (bắt buộc làm trước tiên, mọi feature khác phụ thuộc vào đây)
2. **Phase 1 — CV pipeline** (Feature 1, 7-backend, 4-backend) — vì cả 3 đều sửa `app/cv/pipeline.py`, làm chung 1 đợt để tránh conflict merge lặp lại
3. **Phase 2 — Backend API/business logic** (Feature 10, 2, 9, 8-backend, 11-backend)
4. **Phase 3 — Frontend** (tất cả UI, theo thứ tự 1→11 liệt kê bên dưới, vì nhiều page frontend tái dùng component của nhau)

Sau MỖI feature, Cursor phải: viết/chạy test liên quan (`pytest app/tests/` cho backend, không có test frontend tự động — verify bằng cách chạy dev server + click qua UI), rồi mới sang feature tiếp theo. Không gộp nhiều feature vào 1 commit lớn.

---

## Phase 0 — Nền tảng schema & config

### 0.1. `app/db.py` — migrations mới (dùng đúng pattern try/except ALTER TABLE đã có ở dòng 71-81)

Thêm vào `init_db()`, sau các migration hiện có:

```python
# Feature 10: audit trail — trạng thái xử lý vi phạm
try:
    cursor.execute("ALTER TABLE violation_events ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
except sqlite3.OperationalError:
    pass

# Feature 4: video clip ngắn kèm ảnh
try:
    cursor.execute("ALTER TABLE violation_events ADD COLUMN clip_path TEXT")
except sqlite3.OperationalError:
    pass

# Feature 9: giáo viên chủ nhiệm chỉ xem lớp mình
try:
    cursor.execute("ALTER TABLE users ADD COLUMN homeroom_class TEXT")
except sqlite3.OperationalError:
    pass
```

Bảng mới (Feature 10 — audit log dạng append-only, KHÔNG ghi đè `handled_by` 1 lần vì cần giữ lịch sử đầy đủ ai đã làm gì):

```python
cursor.execute('''
    CREATE TABLE IF NOT EXISTS violation_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        violation_id INTEGER NOT NULL,
        actor_username TEXT NOT NULL,
        action TEXT NOT NULL,        -- 'reviewed' | 'resolved' | 'reopened'
        note TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (violation_id) REFERENCES violation_events(id)
    )
''')
cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_audit_log_violation
    ON violation_audit_log(violation_id)
''')
```

Users `role` hiện là `CHECK (role IN ('admin','security','management'))` — SQLite không hỗ trợ `ALTER TABLE ... DROP CONSTRAINT`, và CHECK constraint đã tồn tại từ `CREATE TABLE IF NOT EXISTS` sẽ không tự cập nhật cho DB cũ. Cursor cần: sửa `CHECK` trong định nghĩa `CREATE TABLE IF NOT EXISTS users` thành `CHECK (role IN ('admin','security','management','teacher'))` — áp dụng cho DB mới. Với DB đã tồn tại (file `data/app.db` hiện có), CHECK cũ vẫn còn hiệu lực và sẽ chặn insert role='teacher'; do đó **phải thêm 1 migration chạy 1 lần** kiểm tra và rebuild bảng `users` nếu CHECK cũ chưa cho phép 'teacher' (pattern chuẩn SQLite: tạo bảng `users_new` với CHECK mới → copy dữ liệu → drop bảng cũ → rename). Viết migration này cẩn thận, bọc trong try/except và log rõ, chỉ chạy nếu phát hiện role 'teacher' bị chặn (thử insert thử nghiệm trong transaction rollback, hoặc đơn giản hơn: luôn thực hiện rebuild-if-needed bằng cách đọc `sqlite_master.sql` của bảng `users` và kiểm tra chuỗi `'teacher'` có trong đó chưa).

### 0.2. `app/config.py` — hằng số mới

```python
# Feature 2: ngưỡng "vi phạm lặp lại"
REPEAT_OFFENDER_WINDOW_DAYS = 30
REPEAT_OFFENDER_THRESHOLD = 3   # >= 3 vi phạm trong window → gắn cờ

# Feature 4: video clip ngắn
VIOLATION_CLIP_SECONDS = 4
VIOLATION_CLIP_FPS = 8          # thấp hơn hiển thị (20fps) để giảm CPU encode + dung lượng
```

### 0.3. `app/schemas.py`

Thêm các model dùng chung (giữ đúng convention: model đơn giản trong `schemas.py`, model đặc thù route vẫn có thể để inline như `users.py` đang làm):

```python
class ViolationStatusUpdate(BaseModel):
    status: str          # 'reviewed' | 'resolved' | 'reopened'
    note: str | None = None
```

**Verify Phase 0**: xóa `data/app.db` test (KHÔNG xóa DB thật của user — dùng DB test riêng qua `conftest.py` fixture đã có), chạy `pytest app/tests/ -x`, đảm bảo toàn bộ test cũ vẫn pass (migration không phá schema cũ).

---

## Phase 1 — CV Pipeline (`app/cv/`)

### Feature 1: Phát hiện xe không biển số / biển số bị che

**File**: `app/cv/pipeline.py`, hàm `_process_violations()` (dòng ~495-636 theo bản đọc hiện tại).

**Logic chính xác cần đổi** — tách nhánh `PLATE_UNREADABLE` hiện tại (`if not plate_dets or not plate_read`) thành 2 case dùng đúng 2 tín hiệu đã có sẵn (không cần thêm ngưỡng confidence mới, không cần model mới — đây là lý do chọn cách này: đơn giản, dùng dữ liệu đã tính sẵn, không cần tune thêm):

```python
if not plate_dets:
    violation_types.append("NO_PLATE")          # không có box biển số nào trong khung hình
elif not plate_read:
    violation_types.append("PLATE_OBSCURED")     # có box nhưng OCR đọc rỗng — nghi che/mờ/hỏng
```

Giữ nguyên toàn bộ phần còn lại của hàm (`PLATE_NOT_REGISTERED`, `NO_HELMET`, `RIDING_THROUGH_GATE`, `TOO_MANY_RIDERS`, gộp `MULTIPLE`) — không đổi.

**Cập nhật mọi nơi liệt kê violation_type** (bắt buộc đồng bộ, nếu bỏ sót sẽ hiện label rỗng/lỗi ở UI):
- `app/api/admin.py::VIOLATION_TYPE_LABELS` — thêm `"NO_PLATE": "Không có biển số"`, `"PLATE_OBSCURED": "Biển số bị che/mờ"`. Giữ `"PLATE_UNREADABLE"` trong map (dữ liệu lịch sử cũ vẫn cần hiển thị đúng label), chỉ không còn được sinh ra mới.
- `frontend/src/utils/violationLabels.js::VIOLATION_LABELS` — thêm 2 key tương ứng, tiếng Việt giống hệt bên backend.
- `frontend/src/pages/AdminViolationsPage.jsx::VIOLATION_COLORS` — thêm entry cho `NO_PLATE`/`PLATE_OBSCURED` (nhân tiện thêm luôn `TOO_MANY_RIDERS` đang bị thiếu — đã phát hiện qua research, hiện fallback sai màu `NO_HELMET`).
- `frontend/src/components/AlertBanner.jsx::ALERT_SOUNDS` và `buildSpeechText()` — thêm case cho 2 type mới (âm thanh/câu TTS riêng, ví dụ: "Cảnh báo: xe không có biển số" / "Cảnh báo: biển số xe bị che, không đọc được").

**Test**: mở rộng `app/tests/test_vehicle_gate.py` (đang test `_process_violations` qua `VideoPipeline.__new__` + mock) — thêm 2 case: (a) `plate_dets=[]` → assert `violation_type == "NO_PLATE"`; (b) `plate_dets` có 1 box, mock `_read_plate_cached` trả `""` → assert `violation_type == "PLATE_OBSCURED"`.

### Feature 7 (backend): FPS / latency / tỉ lệ nhận diện đúng

**File**: `app/cv/pipeline.py`, constructor + `_run_loop()` + `get_status()`.

Constructor thêm state mới (cạnh `self._frame_count` dòng ~213 khu vực init):
```python
from collections import deque
self._frame_timestamps = deque(maxlen=30)      # cho tính FPS trượt
self._last_process_latency_ms = 0.0
self._plate_attempts = 0
self._plate_successes = 0
```

Trong `_run_loop()`, mỗi lần xử lý 1 frame đầy đủ (không phải frame bị `FRAME_SKIP`): bọc đoạn từ lúc resize tới lúc vẽ xong bằng `t0 = time.perf_counter()` ở đầu, `self._last_process_latency_ms = (time.perf_counter() - t0) * 1000` ở cuối; đồng thời `self._frame_timestamps.append(time.time())` mỗi lần frame được xử lý (không tính frame bị skip, để FPS phản ánh đúng tốc độ detect thật chứ không phải tốc độ đọc camera).

Trong `_process_violations()`: mỗi lần có `plate_dets` (tức có thử đọc biển số), `self._plate_attempts += 1`; nếu `plate_read` khác rỗng, `self._plate_successes += 1`. Đây chính là định nghĩa "tỉ lệ nhận diện đúng" — % lần đọc biển số thành công trên tổng lần thử, tính từ lúc pipeline khởi động (đơn giản, không cần rolling window phức tạp — nhất quán với `_frame_count` hiện tại cũng là cumulative).

`get_status()` — thêm field mới vào dict trả về (không đổi field cũ, để tương thích ngược):
```python
fps = 0.0
if len(self._frame_timestamps) >= 2:
    span = self._frame_timestamps[-1] - self._frame_timestamps[0]
    fps = round((len(self._frame_timestamps) - 1) / span, 1) if span > 0 else 0.0

plate_success_rate = (
    round(self._plate_successes / self._plate_attempts, 3)
    if self._plate_attempts > 0 else None
)

return {
    ... # giữ nguyên các field cũ
    "fps": fps,
    "avg_process_latency_ms": round(self._last_process_latency_ms, 1),
    "plate_read_success_rate": plate_success_rate,
}
```

**Test**: mở rộng test hiện có cho `get_status()` (nếu chưa có test riêng, thêm vào `test_posture.py` hoặc file mới `test_pipeline_status.py`) — dựng `VideoPipeline.__new__`, set thủ công `_frame_timestamps`/`_plate_attempts`/`_plate_successes`, assert `get_status()` trả đúng `fps`/`plate_read_success_rate`.

### Feature 4 (backend): Video clip ngắn 3-5s

**File**: `app/cv/pipeline.py`.

Ring buffer: constructor thêm
```python
self._clip_buffer = deque(maxlen=VIOLATION_CLIP_SECONDS * VIOLATION_CLIP_FPS)  # (timestamp, frame) tuples
```
Trong `_run_loop()`, mỗi frame được xử lý đầy đủ (cùng chỗ append `_frame_timestamps` ở Feature 7): `self._clip_buffer.append(frame.copy())` — lưu frame ĐÃ vẽ box (giống ảnh snapshot hiện tại đang lưu) để clip có annotation giống ảnh bằng chứng. **Lưu ý bộ nhớ**: `VIDEO_WIDTH x VIDEO_HEIGHT` = 1280x720x3 bytes ≈ 2.7MB/frame; với `maxlen = 4*8 = 32` frame ≈ 86MB RAM cố định thêm — chấp nhận được, nhưng Cursor PHẢI resize frame xuống nhỏ hơn trước khi đưa vào buffer để tránh tốn RAM/encode chậm: dùng `cv2.resize(frame, (640, 360))` khi push vào `_clip_buffer` (đủ để xem lại, không cần full-res cho video review).

Ghi clip khi có vi phạm (trong `_persist_violation()`, dòng ~637-656, chạy trong `self._io_pool` — TÁI DÙNG pool đã có, không tạo thread mới):
```python
def _write_clip(self, frames: list, out_path: str):
    if not frames:
        return
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, VIOLATION_CLIP_FPS, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()
```
Gọi `self._io_pool.submit(self._write_clip, list(self._clip_buffer), clip_path)` cùng lúc với snapshot save hiện có, với `clip_path = snapshot_path.replace('.jpg', '.mp4')` (cùng thư mục `SNAPSHOTS_DIR`, cùng naming convention timestamp đã có). Truyền `clip_path` xuống `add_violation_event(..., clip_path=clip_path)`.

**Backend API**: `app/db.py::add_violation_event()` thêm param `clip_path: str = None`, insert vào cột mới. `list_violations()` thêm `clip_url` vào kết quả trả về giống cách `snapshot_url` đang được build trong `app/api/admin.py::GET /api/violations` (dòng xử lý `snapshot_url = f'/media/{filename}'`) — làm y hệt cho `clip_path` → `clip_url`.

**Dọn dẹp**: `clear_violation_snapshot_paths()` trong `db.py` hiện chỉ xóa `snapshot_path` — mở rộng để xóa luôn file `clip_path` tương ứng và set `clip_path = NULL`, giữ đúng logic best-effort try/except OSError đã có.

**Test**: unit test `_write_clip()` với list frame giả (numpy zeros), assert file `.mp4` được tạo và có kích thước > 0. Test `_persist_violation` gọi đúng `add_violation_event` với `clip_path` kwarg (mock giống `test_vehicle_gate.py` đang làm).

**Verify Phase 1**: chạy `python -m app.cv.smoke_test` thủ công (không phải pytest) để xác nhận pipeline không crash với các thay đổi mới; chạy `pytest app/tests/test_vehicle_gate.py app/tests/test_posture.py -v`.

---

## Phase 2 — Backend API / business logic

### Feature 10: Audit trail — ai xử lý vi phạm nào

**File**: `app/db.py` — hàm mới:
```python
def update_violation_status(violation_id: int, status: str, actor_username: str, note: str = None) -> bool:
    # UPDATE violation_events SET status = ? WHERE id = ?  (dùng _write_lock như các hàm ghi khác)
    # INSERT vào violation_audit_log (violation_id, actor_username, action=status, note)
    # return False nếu violation_id không tồn tại

def get_violation_audit_log(violation_id: int) -> list[dict]:
    # SELECT * FROM violation_audit_log WHERE violation_id = ? ORDER BY created_at ASC
```

**File**: `app/api/admin.py` (thêm vào `violations_router` đã có, prefix `/api`):
```python
@violations_router.patch("/violations/{violation_id}/status")
def set_violation_status(
    violation_id: int,
    body: ViolationStatusUpdate,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    # validate body.status in ('reviewed', 'resolved', 'reopened') → 422 nếu không hợp lệ
    # ok = db.update_violation_status(violation_id, body.status, current_user["username"], body.note)
    # 404 nếu không tồn tại
    # return {"status": "ok"}

@violations_router.get("/violations/{violation_id}/audit-log")
def get_violation_audit(
    violation_id: int,
    current_user: dict = Depends(require_role("admin", "security", "management")),
):
    # return db.get_violation_audit_log(violation_id)
```

`GET /api/violations` (route đã có) — thêm `status` vào output mỗi item (đã có cột DB, chỉ cần `SELECT` bao gồm nó trong `list_violations()`, việc này tự động vì hàm dùng `SELECT ve.*`).

**Test**: file mới `app/tests/test_violation_status.py` — theo pattern `conftest.py::auth_headers`. Case: security cập nhật status → 200, log xuất hiện đúng actor; role không được phép (không có, vì 3 role đều được phép — test riêng role chưa đăng nhập → 401); status không hợp lệ → 422; violation_id không tồn tại → 404.

### Feature 2: Lịch sử vi phạm theo học sinh + cờ "vi phạm lặp lại"

**File**: `app/db.py` — hàm mới:
```python
def get_student_violation_summary(student_class: str = None) -> list[dict]:
    """
    Group violation_events theo plate_matched, JOIN registered_vehicles.
    Trả về mỗi xe đã đăng ký: {vehicle_id, plate_number, student_name, student_class,
                                total_violations, violations_in_window, is_repeat_offender, last_violation_at}
    is_repeat_offender = violations_in_window >= REPEAT_OFFENDER_THRESHOLD
    (dùng REPEAT_OFFENDER_WINDOW_DAYS từ config cho khoảng "gần đây")
    Nếu student_class truyền vào, filter theo đúng lớp đó (dùng cho Feature 9 — giáo viên).
    Xe chưa từng vi phạm vẫn xuất hiện với count=0 (LEFT JOIN từ registered_vehicles, không phải từ violation_events).
    """

def get_violations_by_vehicle(vehicle_id: int, limit: int = 100) -> list[dict]:
    """Toàn bộ lịch sử vi phạm của 1 xe/học sinh, sắp theo timestamp DESC — dùng cho trang timeline (Feature 6)."""
```

**File**: `app/api/admin.py` — thêm route mới trong `vehicles_router` (đã có, prefix `/api/vehicles`):
```python
@vehicles_router.get("/violations-summary")
def violations_summary(
    current_user: dict = Depends(require_role("admin", "management", "teacher")),
):
    class_filter = current_user["homeroom_class"] if current_user["role"] == "teacher" else None
    return db.get_student_violation_summary(student_class=class_filter)

@vehicles_router.get("/{vehicle_id}/violations")
def vehicle_violation_history(
    vehicle_id: int,
    current_user: dict = Depends(require_role("admin", "management", "security", "teacher")),
):
    # nếu current_user["role"] == "teacher": phải verify xe này thuộc đúng homeroom_class của giáo viên đó
    # trước khi trả data (403 nếu không), KHÔNG được dựa vào query param — luôn lấy student_class thật
    # của vehicle_id từ DB rồi so với current_user["homeroom_class"]
    return db.get_violations_by_vehicle(vehicle_id)
```

Lưu ý quan trọng cho Cursor: route `/{vehicle_id}/violations` phải đặt SAU route tĩnh cụ thể hơn nếu có trùng prefix (FastAPI khớp theo thứ tự khai báo) — kiểm tra không xung đột với `/violations-summary` (khác path nên an toàn, nhưng phải khai báo `/violations-summary` trước `/{vehicle_id}` nếu chúng chung 1 router path pattern tương tự, để tránh FastAPI hiểu nhầm "violations-summary" là 1 `vehicle_id`).

**Test**: `app/tests/test_repeat_offender.py` mới — seed 4 vi phạm cho 1 biển số trong window 30 ngày → assert `is_repeat_offender == True`; seed 2 vi phạm → `False`; test route trả 403 khi teacher xem xe không thuộc lớp mình.

### Feature 9: Vai trò giáo viên chủ nhiệm

**File**: `app/api/users.py` — `UserCreate`/`UserUpdate` thêm field `homeroom_class: str | None = None`; validate `role in (..., "teacher")`; nếu `role == "teacher"` thì `homeroom_class` bắt buộc khác None (422 nếu thiếu — giáo viên phải gắn với 1 lớp cụ thể để scope hoạt động).

**File**: `app/api/admin.py` — sửa `GET /api/violations` và `GET /api/vehicles` để tự động ép filter theo lớp khi `current_user["role"] == "teacher"`:
```python
# GET /api/violations — đổi require_role("admin") thành require_role("admin", "teacher")
# nếu current_user["role"] == "teacher": ép student_class filter = current_user["homeroom_class"]
#   (ghi đè, KHÔNG cho phép giáo viên truyền query param student_class khác — server-side enforce,
#    đúng nguyên tắc đã ghi chú trong RequireRole.jsx: "Real enforcement is always done on the server")
```
Việc này cần `list_violations()` trong `db.py` hỗ trợ filter theo `student_class` (hiện chưa có — chỉ có `plate` LIKE filter). Thêm param `student_class: str = None` vào `list_violations()`, join sẵn có với `registered_vehicles rv` đã tồn tại (dòng JOIN hiện tại) nên chỉ cần thêm điều kiện `WHERE rv.student_class = ?` vào `conditions` list theo đúng pattern động đã có.

`GET /api/vehicles` tương tự — đổi `require_role("admin")` → `require_role("admin", "teacher")`, và `list_vehicles()` thêm param `student_class: str = None` để lọc.

**Test**: đăng nhập user role teacher (cần thêm seed user teacher trong `conftest.py` — Cursor phải sửa `conftest.py::test_app` fixture để seed thêm 1 user `teacher`/`homeroom_class="10A1"`, và `auth_headers(client, role="teacher")` phải hoạt động được). Assert: `GET /api/violations` với teacher chỉ trả bản ghi lớp `10A1` dù không truyền filter; assert giáo viên không được vào `/api/users`, `/api/system/snapshots/cleanup` (403).

### Feature 8 (backend): Xem trước trước khi dọn snapshot

**File**: `app/api/system.py` — route mới:
```python
@router.get("/snapshots/preview")
def preview_snapshot_cleanup(
    older_than_days: int = Query(90, ge=1, le=3650),
    current_user: dict = Depends(require_role("admin")),
):
    paths = db.get_old_violation_snapshot_paths(older_than_days)  # hàm đã có, chỉ đọc
    total_size = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
    return {"file_count": len(paths), "total_size_mb": round(total_size / (1024*1024), 2)}
```
Tái dùng 100% `get_old_violation_snapshot_paths()` đã có sẵn (chỉ đọc, không đổi) — route mới chỉ là read-only wrapper, không cần đổi gì trong `db.py`.

### Feature 11 (backend): Import CSV có bước xem trước (dry-run)

**File**: `app/api/admin.py` — route `POST /api/vehicles/import` hiện có (đọc kỹ logic `col_map` + `add_with_retry` đã research). Thêm query param `dry_run: bool = False`. Khi `dry_run=True`: chạy toàn bộ logic parse + validate (kiểm tra trùng plate, thiếu cột, format) NHƯNG bỏ qua bước gọi `add_vehicle()` thật — thay vào đó chỉ đếm `would_create`/`would_skip` và liệt kê lỗi y hệt response hiện tại. Cursor cần refactor hàm import hiện tại để phần "parse + validate" và phần "ghi DB" tách rời rõ ràng (1 hàm helper `_parse_and_validate_csv(file_content) -> (valid_rows, errors)` dùng chung cho cả 2 nhánh dry-run và ghi thật) — tránh trùng lặp code.

**Verify Phase 2**: `pytest app/tests/ -v` toàn bộ, đảm bảo không có test cũ nào fail do đổi `require_role`/`list_violations`/`list_vehicles` signature (kiểm tra `test_vehicles.py`, `test_stats.py`, `test_system.py` vẫn pass với tham số mới có default None).

---

## Phase 3 — Frontend

Thứ tự làm theo đúng số thứ tự feature người dùng liệt kê, vì các page sau tái dùng component/util của page trước.

### Feature 1 (frontend): đã liệt kê ở Phase 1 (label/color/TTS) — làm cùng lúc với phần backend của Feature 1, không tách riêng.

### Feature 7 (frontend): Trang sức khỏe hệ thống mở rộng

**File**: `frontend/src/pages/AdminHealthPage.jsx`. Thêm vào đúng lưới 3-cột stat-cell đang có (pattern `bg-[#f4f6f9] rounded-xl` đã research) 3 cell mới: FPS (`health.pipeline.fps`), Độ trễ xử lý (`health.pipeline.avg_process_latency_ms` + "ms"), Tỉ lệ đọc biển số thành công (`health.pipeline.plate_read_success_rate` — format `%`, hiển thị "Chưa có dữ liệu" nếu `null`). Với hệ thống 2 gate (đã làm ở feature trước), các số liệu này đọc từ `health.gates[].pipeline` per-gate giống cách `last_frame_age_sec` đang hiển thị per-gate ở `GuardPage.jsx` split-view — nhất quán.

### Feature 4 (frontend): Video player trong modal

**File**: `frontend/src/pages/AdminViolationsPage.jsx`, component `ViolationDetailModal` đã có. Thêm: nếu `v.clip_url` tồn tại, render `<video controls muted className="w-full max-h-[50vh] bg-black rounded" src={`${API_BASE_URL}${v.clip_url}`} />` THAY CHO `<img>` snapshot hiện tại (không hiển thị cả 2 cùng lúc — video clip đã chứa đủ ngữ cảnh, ảnh JPG chỉ nên fallback khi `clip_url` là `null`, tức bản ghi cũ trước khi feature này triển khai). Giữ nguyên nút "Đọc to thông tin" (TTS) không liên quan tới video.

### Feature 10 (frontend): Trạng thái xử lý + audit log trong modal

**File**: `frontend/src/pages/AdminViolationsPage.jsx`. Trong `ViolationDetailModal`: thêm badge trạng thái (`v.status`: pending/reviewed/resolved — tái dùng pattern màu `{bg,text,border,dot}` giống `VIOLATION_COLORS`/`ROLE_COLORS` đã có, tạo `STATUS_COLORS` map mới cùng file). Thêm 2 nút "Đánh dấu đã xem"/"Đánh dấu đã xử lý" gọi `client.patch(`/api/violations/${v.id}/status`, {status: '...'})`, sau đó `load()` lại danh sách. Thêm khu vực nhỏ liệt kê audit log (`GET /api/violations/{id}/audit-log`, gọi khi mở modal) — mỗi dòng: `{actor_username} đã {action} lúc {formatDate(created_at)}` (dùng `formatDate` từ `utils/format.js` — đã có sẵn, TÁI DÙNG thay vì viết format ngày mới). Ẩn 2 nút hành động nếu `user.role === 'teacher'` (chỉ đọc, không được đổi trạng thái — theo scope Feature 9 đã quyết ở Phase 2).

Cũng thêm cột "Trạng thái" vào bảng chính (không chỉ modal) để không phải mở từng dòng mới biết.

### Feature 2 + 6: Lịch sử vi phạm theo học sinh, cờ vi phạm lặp lại, timeline trực quan

Gộp 2 mục này vì cùng 1 trang — timeline CHÍNH LÀ cách hiển thị lịch sử vi phạm.

**File mới**: `frontend/src/pages/StudentViolationHistoryPage.jsx`. Route mới trong `App.jsx`: `/admin/students/:vehicleId/violations` (roles: admin, management, security, teacher — theo đúng `require_role` backend đã set ở Phase 2).

Nội dung trang:
- Header: tên học sinh, lớp, biển số (fetch từ `GET /api/vehicles/{id}` — **route này CHƯA tồn tại**, Cursor cần thêm `GET /api/vehicles/{vehicle_id}` đơn giản vào `admin.py` nếu chưa có get-by-id, kiểm tra lại — nếu không có sẵn thì bổ sung, dùng `get_vehicle_by_plate` không đủ vì cần lookup theo id, cần hàm `db.get_vehicle_by_id(vehicle_id)` mới, pattern y hệt `get_vehicle_by_plate`).
- Badge "Vi phạm lặp lại" (đỏ, nổi bật) nếu summary trả `is_repeat_offender: true` — dùng lại từ `GET /api/vehicles/violations-summary`, filter theo `vehicle_id` phía client (danh sách này thường nhỏ — vài trăm xe — filter client OK, KHÔNG cần route riêng theo id).
- **Timeline component** (component mới `frontend/src/components/ViolationTimeline.jsx`, tái dùng cho cả trang này lẫn có thể nhúng vào chỗ khác sau này): danh sách dọc, mỗi vi phạm là 1 "node" — chấm tròn màu theo `VIOLATION_COLORS`, nối bằng đường thẳng đứng (thuần CSS, KHÔNG cần thư viện timeline — border-left + padding trên từng item là đủ, giống style hiện có toàn hand-rolled Tailwind), mỗi node hiển thị: giờ, badge loại vi phạm, badge trạng thái (Feature 10), thumbnail ảnh nhỏ, click mở `ViolationDetailModal` đã có (import lại từ `AdminViolationsPage.jsx` — nếu component đó chưa export, Cursor cần tách `ViolationDetailModal` ra file riêng `frontend/src/components/ViolationDetailModal.jsx` để dùng chung, tránh copy-paste code).

**File sửa**: `frontend/src/pages/AdminVehiclesPage.jsx` — thêm cột/nút "Lịch sử vi phạm" trên mỗi dòng xe, link tới `/admin/students/{id}/violations`; thêm badge nhỏ "Lặp lại" ngay trong bảng nếu xe đó đang bị flag (cần gọi `violations-summary` 1 lần khi load trang, map theo `vehicle_id`).

**Sidebar**: thêm mục nav "Lịch sử vi phạm HS" nếu cần entry riêng, hoặc chỉ truy cập qua nút trong bảng Vehicles — quyết định: KHÔNG thêm mục sidebar riêng (tránh phình menu), chỉ truy cập từ bảng Vehicles/từ trang giáo viên (Feature 9 dưới).

### Feature 5: Tìm kiếm nhanh học sinh (autocomplete)

**File mới**: `frontend/src/components/StudentAutocomplete.jsx` — component dùng chung. Input text + dropdown gợi ý hiện dưới, KHÔNG gọi API riêng (lý do đơn giản hóa: danh sách xe đăng ký của 1 trường thường vài trăm–vài nghìn dòng, đã có sẵn `GET /api/vehicles` trả full list — filter phía client bằng debounce 200ms là đủ nhanh, tránh phải viết + test 1 endpoint search mới). Props: `vehicles` (list đã fetch sẵn từ page cha, tránh fetch trùng lặp), `onSelect(vehicle)`. Filter: match không phân biệt hoa/thường trên `plate_number`, `student_name`, `student_class` (dùng `normalize_plate`-style strip khoảng trắng cho biển số, so khớp substring cho tên/lớp).

Gắn vào: `AdminVehiclesPage.jsx` (thanh tìm kiếm phía trên bảng — hiện CHƯA có search/filter nào theo research, đây là bổ sung mới hoàn toàn) và `AdminViolationsPage.jsx` (thay ô input plate filter hiện tại bằng component này để gợi ý tên/lớp luôn, không chỉ gõ đúng biển số).

### Feature 3: Cảnh báo âm thanh phân loại theo mức độ

**File mới**: `frontend/src/utils/alertPriority.js`:
```js
export const ALERT_PRIORITY = {
  NO_HELMET: 'high',
  RIDING_THROUGH_GATE: 'high',
  TOO_MANY_RIDERS: 'high',
  NO_PLATE: 'medium',
  PLATE_OBSCURED: 'medium',
  PLATE_NOT_REGISTERED: 'medium',
  MULTIPLE: 'high',   // gộp nhiều lỗi luôn coi là ưu tiên cao
  default: 'medium',
};
export function getAlertPriority(violationType) {
  return ALERT_PRIORITY[violationType] || ALERT_PRIORITY.default;
}
```

**File sửa**: `frontend/src/utils/speak.js` — đổi signature `speakVietnamese(text, options = {})` với `options.rate`/`options.pitch`/`options.volume` (mặc định giữ nguyên hành vi cũ nếu không truyền options — không phá code gọi cũ). Priority `high` → `rate: 1.15, pitch: 1.1, volume: 1.0`; `medium` → giữ mặc định hiện tại.

**File sửa**: `frontend/src/components/AlertBanner.jsx` — `handleAlert()` tính `priority = getAlertPriority(data.violation_type)`, truyền vào `speakVietnamese(text, {rate: priority==='high'?1.15:1, ...})`; banner nền đổi màu theo priority (`high` giữ đỏ `#c92035` hiện tại, `medium` đổi sang màu amber cảnh báo đã có sẵn trong design system — `#f59e0b`, đã dùng cho nút dọn 90-ngày). `ALERT_SOUNDS` — priority `high` lặp beep nhiều hơn (đã có sẵn differentiation theo `violation_type`, chỉ cần đảm bảo 2 type mới `NO_PLATE`/`PLATE_OBSCURED` map vào đúng nhóm âm thanh "medium" phù hợp, dùng lại preset `PLATE_UNREADABLE` cũ cho cả 2 — không cần preset mới).

### Feature 9 (frontend): Giao diện giáo viên chủ nhiệm

**File sửa**: `frontend/src/auth/RequireRole.jsx` — thêm `teacher` vào `defaults` map, trỏ `/teacher/violations`.
**File sửa**: `frontend/src/components/Sidebar.jsx` — thêm nhánh `if (user.role === 'teacher')` push link "Vi phạm lớp tôi" → `/teacher/violations`, "Danh sách xe lớp tôi" → `/teacher/vehicles` (tái dùng đúng 2 page Admin hiện có ở chế độ giới hạn — server đã tự filter theo `homeroom_class`, nên KHÔNG cần viết page riêng cho teacher, chỉ cần route `/teacher/violations` và `/teacher/vehicles` trỏ thẳng tới `AdminViolationsPage`/`AdminVehiclesPage` với cùng component, ẩn đi các nút chỉ-admin (import/export/sửa/xóa) bằng check `user.role !== 'admin'` đã có sẵn pattern ẩn nút theo role rải rác trong 2 file này — Cursor cần audit lại từng nút "Sửa"/"Xóa"/"Nhập CSV"/"Xuất CSV" trong 2 trang và bọc điều kiện `{user.role === 'admin' && (...)}`).
**File sửa**: `frontend/src/App.jsx` — thêm 2 route `/teacher/violations` (allow: teacher), `/teacher/vehicles` (allow: teacher), dùng lại `<AdminViolationsPage/>`/`<AdminVehiclesPage/>`.
**File sửa**: `frontend/src/pages/AdminUsersPage.jsx` — `ROLES` thêm `'teacher'`, `ROLE_LABELS`/`ROLE_COLORS` thêm entry; form thêm input "Lớp chủ nhiệm" (`homeroom_class`) CHỈ hiện khi role đang chọn là `teacher` (giống pattern ẩn/hiện field theo lựa chọn khác nếu đã có, nếu chưa có thì dùng `{form.role === 'teacher' && <input .../>}` đơn giản).

### Feature 8 (frontend): UI xem trước khi dọn snapshot

**File sửa**: `frontend/src/pages/AdminHealthPage.jsx` — khu vực dọn snapshot hiện có 3 nút preset (`>30/>90/>180`). Thêm: input số ngày tùy chỉnh + nút "Xem trước" gọi `GET /api/system/snapshots/preview?older_than_days=N`, hiển thị kết quả (`file_count`, `total_size_mb`) trong dialog xác nhận TRƯỚC KHI hiện `confirm()` xóa thật (thay vì `confirm()` chỉ có text tĩnh như hiện tại — giờ hiện đúng số liệu thật). Giữ nguyên 3 nút preset cũ, chỉ thêm luồng preview cho input tùy chỉnh mới.

### Feature 11 (frontend): Import CSV có bước xem trước

**File sửa**: `frontend/src/pages/AdminVehiclesPage.jsx` — luồng import hiện tại (chọn file → POST ngay → alert kết quả) đổi thành 2 bước: (1) chọn file → gọi `POST /api/vehicles/import?dry_run=true` → hiện bảng preview (số dòng hợp lệ/lỗi, liệt kê lỗi như hiện tại đang alert) trong 1 modal mới nhỏ; (2) nút "Xác nhận nhập" trong modal đó mới gọi lại `POST /api/vehicles/import` (không kèm `dry_run`, hoặc `dry_run=false`) để ghi thật, dùng LẠI CÙNG FormData/file đã chọn (giữ `file` trong state thay vì chỉ trong input, để gọi lại được lần 2 không cần chọn lại file).

**Verify Phase 3**: chạy `npm run dev --prefix frontend` (dùng `preview_start` tool, KHÔNG chạy tay qua Bash), đăng nhập lần lượt 4 role (admin/security/management/teacher — cần tạo user teacher thử qua `AdminUsersPage` hoặc seed script), click qua từng trang mới/sửa, xác nhận không có console error, screenshot các màn hình chính (Health page mới, Violation modal có video+status+audit log, Student history timeline, teacher-restricted view) để xác nhận bằng mắt trước khi báo hoàn thành.

---

## Ghi chú tổng quát cho Cursor

- **Không tạo bảng/route/component thừa** ngoài những gì liệt kê ở trên — mọi quyết định "route mới hay tái dùng route cũ" đã được cân nhắc dựa trên code thật đọc được, không phải mặc định thêm mới cho "đẹp".
- Mọi hàm ghi DB mới PHẢI bọc trong `with _write_lock:` giống 100% hàm ghi hiện có trong `db.py` — đây là cơ chế đồng bộ duy nhất của file (SQLite + nhiều thread).
- Mọi route mới PHẢI dùng `Depends(require_role(...))` — không tạo cơ chế RBAC song song.
- Giữ nguyên convention: số/timestamp/biển số dùng `font-mono` trong UI; snapshot/clip lưu trong `SNAPSHOTS_DIR`, phục vụ qua mount `/media` có sẵn.
- Sau khi xong TOÀN BỘ Phase 0-3, chạy lại `pytest app/tests/ -v` lần cuối để đảm bảo không có regression, và liệt kê rõ trong báo cáo cuối cùng feature nào đã xong/còn thiếu.
