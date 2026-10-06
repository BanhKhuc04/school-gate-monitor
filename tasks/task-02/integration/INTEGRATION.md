# TASK 2 — Tích hợp file dùng chung (Task 1 là bên tích hợp)

> Mỗi entry dưới đây là patch Task 2 dự thảo cho file Task 1 đang giữ. **Chưa áp
> dụng** cho tới khi Task 1 xác nhận nhận và tích hợp + chạy lại test liên quan.

## Quy ước

- File đã có thay đổi chưa commit trong working tree: KHÔNG sửa trực tiếp.
- Patch đưa ra dưới dạng unified diff dự thảo + baseline (commit tham chiếu).
- Khi tích hợp xong, chuyển entry sang trạng thái `integrated` và ghi test pass.

## Index các entry

- [INT-01] — `app/db.py`: thêm migration cho enrollment_version + class_at_event (provenance)
- [INT-02] — `app/main.py`: bỏ 410 SPA fallback cho `/admin/violations` thực có trong React
- [INT-03] — `app/api/camera.py`: API mount đầy đủ cho router camera trong test_app fixture
- [INT-04] — `app/schemas.py`: bổ sung `IssueUpdate.expected_version` cho version conflict
- [INT-05] — `app/config.py`: thêm `PUBLIC_REGISTER_ENABLED`, `CSV_IMPORT_MAX_*`,
  `BACKUP_HOLD_DAYS`, `MEDIA_ROOT_ALLOW_*`

---

## [INT-01] Migration: enrollment_version + class_at_event

**Mục đích:** Task 2.4 cần provenance cho lịch sử — biết enrollment (hồ sơ hiện
tại) đã đổi bao nhiêu lần và class_at_event tại thời điểm vi phạm được xác nhận.

**Baseline:** HEAD `83a0309` (đã có `encounter_observations` từ Task 1).

**Patch dự thảo (`app/db.py::init_db`):**

```sql
-- Migration: enrollment_version cho registered_vehicles
ALTER TABLE registered_vehicles ADD COLUMN enrollment_version INTEGER NOT NULL DEFAULT 1;

-- Lưu provenance trên encounter_observations (mỗi camera đóng góp 1 obs)
ALTER TABLE encounter_observations ADD COLUMN student_class_at_event TEXT;
ALTER TABLE encounter_observations ADD COLUMN enrollment_version INTEGER;
ALTER TABLE encounter_observations ADD COLUMN student_name_at_event TEXT;

-- Tạo trigger để bump enrollment_version khi update hồ sơ
CREATE TRIGGER IF NOT EXISTS trg_vehicle_enrollment_bump
AFTER UPDATE OF plate_number, student_name, student_class, photo_path, dob, phone, student_id
ON registered_vehicles
FOR EACH ROW
BEGIN
    UPDATE registered_vehicles
    SET enrollment_version = enrollment_version + 1
    WHERE id = OLD.id;
END;

-- Index cho enrollment_version
CREATE INDEX IF NOT EXISTS idx_vehicles_enrollment_version
ON registered_vehicles(enrollment_version);
```

**Migration bổ sung cho violation_events:**

```sql
ALTER TABLE violation_events ADD COLUMN enrollment_version INTEGER;
ALTER TABLE violation_events ADD COLUMN student_class_at_event TEXT;
```

**Test sau tích hợp:**

- Sửa biển hồ sơ → enrollment_version tăng; encounter_observ cũ giữ biển cũ.
- Xóa hồ sơ (archive) → violation_events không cascade mất.
- File test: `app/tests/test_task02_provenance.py`.

**Trạng thái:** `integration_pending`.

---

## [INT-02] SPA fallback: bỏ 410 cho route SPA thực có

**Mục đích:** Task 2.2 yêu cầu production deep link `/admin/violations` trả index.html
không 410. Hiện `app/main.py` đăng ký 410 cho `/admin/violations`, `/admin`,
`/admin/vehicles/{_}` — đây là route SPA có trong React.

**Baseline:** HEAD `83a0309` — `app/main.py::old_jinja_routes`.

**Patch dự thảo:**

```python
# Xóa decorator 410 cho các route SPA có trong React; chỉ giữ cho route Jinja cũ.
# @app.get("/admin")
# @app.get("/admin/vehicles/{_}")
@app.get("/admin/violations")
async def old_admin_violations_jinja(_: str = ""):
    return JSONResponse({"detail": "Gone — frontend moved to React SPA"}, status_code=410)
```

(Sau khi tích hợp, route `/admin/violations` được SPA fallback xử lý; các route Jinja
cũ `/admin`, `/admin/vehicles/{_}` cần quyết định riêng.)

**Trạng thái:** `integration_pending`.

---

## [INT-03] Test fixture: thêm camera router

**Mục đích:** Task 2 cần test `/api/camera/...` qua fixture. Hiện fixture
`conftest.py::test_app` đã include camera_router từ HEAD — chỉ cần đảm bảo
không bị Task 1 gỡ.

**Trạng thái:** `integration_pending` (verify sau khi Task 1 chốt).

---

## [INT-04] Version conflict cho issues[]

**Mục đích:** Task 2.4 yêu cầu `update_violation_status` / `update_violation_issues`
check expected_version, trả 409 nếu lệch.

**Patch dự thảo (`app/schemas.py::ViolationIssuesUpdate`):**

```python
class ViolationIssuesUpdate(ViolationStatusUpdate):
    issues: list[Issue] = []
    encounter_id: str | None = None
    observed_at: str | None = None
    expected_version: int | None = None  # mới — Task 2.4
```

**Patch dự thảo (`app/db.py::update_violation_issues`):** thêm tham số
`expected_version`; nếu không khớp → raise `ConcurrencyError`.

**Trạng thái:** `integration_pending` — chờ DB có cột `version` (Task 1 có thể đã
thêm qua migration; verify trước).

---

## [INT-05] Config bổ sung

**Patch dự thảo (`app/config.py`):**

```python
# T2.5 — tắt mặc định khi dùng dữ liệu thật; bật khi dev/demo.
PUBLIC_REGISTER_ENABLED = os.environ.get("PUBLIC_REGISTER_ENABLED", "0") == "1"

# T2.5 — CSV import giới hạn
CSV_IMPORT_MAX_BYTES = int(os.environ.get("CSV_IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
CSV_IMPORT_MAX_ROWS = int(os.environ.get("CSV_IMPORT_MAX_ROWS", "10000"))

# T2.8 — Backup retention riêng
BACKUP_HOURLY_DAYS = int(os.environ.get("BACKUP_HOURLY_DAYS", "14"))
BACKUP_DAILY_DAYS = int(os.environ.get("BACKUP_DAILY_DAYS", "14"))

# T2.7 — Cleanup hold
CLEANUP_HOLD_DAYS = int(os.environ.get("CLEANUP_HOLD_DAYS", str(CLEANUP_RETENTION_DAYS)))
```

**Trạng thái:** `integration_pending`.