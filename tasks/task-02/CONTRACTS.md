# TASK 2 — Hợp đồng phối hợp

> Hợp đồng giữa Task 2 và các phần còn lại của hệ thống (Task 1, contract cũ).
> Mọi thay đổi phải tương thích ngược — không âm thầm đổi shape cũ.

## 1. Đăng nhập / phiên

- `POST /api/auth/login` body `{username, password}` → 200 `{access_token, token_type,
  username, role, homeroom_class}`; đồng thời set cookie `gate_session` (HttpOnly).
- `role ∈ {"admin","security","management","teacher"}`. Role `teacher` bắt buộc có
  `homeroom_class` không rỗng sau trim (cả ở DB và JWT).
- `GET /api/auth/me` đọc từ Bearer header **hoặc** cookie — cả hai đều hoạt động.
- Demo button: Quản trị viên (`admin` / `admin123`), Bảo vệ (`security` /
  `security123`), Ban giám hiệu (`management` / `management123`), **Giáo viên**
  (`teacher` / `teacher123`, lớp `10A1`).
- **Hoãn (DEFERRED_AUTH)**: JWT revocation, cookie-only (bỏ Bearer), rate limit
  đăng nhập, session hardening, password policy.

## 2. Phạm vi dữ liệu theo vai trò

| Vai trò | Xe | Lịch sử vi phạm | Media (snapshot/clip) | Ảnh hồ sơ |
|---------|----|------------------|------------------------|------------|
| admin | Tất cả | Tất cả | Tất cả | Tất cả |
| security | Đọc (qua `/api/vaungj?status=...`) | Tất cả (qua `/api/violations`) | Tất cả | Không |
| management | Tất cả (qua `/api/vehicles`) | Tất cả | Tất cả | Không |
| teacher | Chỉ xe thuộc lớp mình (`student_class = homeroom_class`) | Chỉ vi phạm của lớp mình | Chỉ file thuộc lớp mình | Không |

- 403 khi teacher thiếu `homeroom_class` sau trim. Không suy lớp từ tên file.

## 4. Phương tiện — POST/PUT

- Request: `{plate_number, student_name, student_class, photo_path?, dob?, phone?,
  student_id?}`. Tất cả trường mở rộng được lưu đầy đủ xuống DB.
- Trùng biển (sau chuẩn hóa) → 409 với message rõ ràng, không phải 500.
- Validation: trim tên/lớp, reject lớp rỗng sau trim, phone chỉ chữ số + dấu `+`,
  dob đúng định dạng `YYYY-MM-DD` hoặc null.

## 5. Phương tiện — GET chi tiết / lịch sử

- `GET /api/vehicles/{id}` — trả full record (bao gồm photo_path, dob, phone,
  student_id). Teacher: 403 nếu không thuộc lớp mình; trả 404 để không lộ tồn tại.
- `GET /api/vehicles/{id}/violations` — server-side filter theo lớp teacher.
  Frontend dùng `limit=1..200`, `offset>=0`; total đúng. Hỗ trợ `date_from`/
  `date_to` ISO.
- `GET /api/violations` — đã có filter/sort. Frontend **reset page khi đổi vehicle
  filter**, **hủy request cũ** khi filter/page thay đổi.

## 6. Lịch sử vi phạm theo xe (provenance)

- Lịch sử JOIN theo `plate_matched` (giữ legacy data). Khi sửa biển số trong
  hồ sơ hiện tại → vi phạm cũ giữ biển lúc xảy ra. Tạm thời giữ nguyên
  hành vi legacy và thêm comment; migration sang "vehicle archive + version" thuộc
  Task 1 phối hợp.
- Dữ liệu legacy thiếu provenance: hiển thị `student_class` = `""` (không suy từ
  hồ sơ hiện tại).

## 7. CSV import/export

- Encoding: `utf-8-sig` (tự loại BOM). Hỗ trợ quoted field và newline trong
  quoted field qua `csv.DictReader` chuẩn.
- Header chấp nhận cả dấu và không dấu (`plate_number` / `biển số`); case-insensitive.
- Import preview: trả `{created, skipped, errors[], preview[]}`; preview phải
  phản ánh số thực tế sẽ tạo, không phóng đại.
- Export xe: BOM + UTF-8; columns `Biển số, Học sinh, Lớp, Mã số, Ngày sinh,
  SĐT`. Round-trip vào DB trống phải giữ được các trường đó.
- Export vi phạm: dùng filter đã áp dụng (`appliedFilters`) — bao gồm biển
  từ autocomplete, loại lỗi, ngày đã apply.
- Giới hạn ban đầu: 5 MB / 10.000 dòng; cấu hình qua env `CSV_IMPORT_MAX_*`.

## 8. Upload ảnh

- Admin: `POST /api/vehicles/upload-photo` (multipart). Tối đa 5 MB, định dạng
  JPEG/PNG/WebP, tên file UUID, không lộ timestamp.
- Public: `POST /api/register/upload-photo` chỉ hoạt động khi `PUBLIC_REGISTER_ENABLED=1`.
  Khi tắt → endpoint trả 503 + JSON `{detail, enabled: false}`.
- Decode ảnh thực (PIL); reject SVG/MIME giả mạo. UUID filename, output JPEG/PNG.

## 9. Media endpoint

- `GET /api/media/snapshots/{filename}` và `/api/media/clips/{filename}` —
  permission scope như bảng §2. Trả `FileResponse` (Starlette thực cài) hỗ trợ
  `Range` header đúng RFC 7233.
- `GET /api/media/student-photos/{filename}` — admin only.
- Validate filename: reject `..`, path separator, dotfile; resolve về root media và
  verify `is_relative_to(root)`.

## 10. SPA + production deep link

- `GET /admin/violations`, `/teacher/violations`, `/teacher/vehicles`,
  `/admin/users`, ... — production build SPA trả `index.html` (200), không 410.
- `GET /api/khong-ton-tai` → JSON 404 với `{detail}`, không fallback index.html.
- Middleware thứ tự: `/api/*` routers → static assets → SPA fallback → cuối cùng
  API 404 JSON.

## 11. URL cùng origin

- Frontend `client.js` không còn hard-code `http://localhost:8001` trong URL
  gửi đi. Mặc định để trống `baseURL` → axios dùng cùng origin (window.location).
- Dev (Vite): giữ proxy `/api`, `/media`, `/guard/...` — đã có sẵn.
- Prod: người dùng cấu hình reverse proxy bằng trỏ `/api` và `/media` về backend.

## 12. Bảng thời gian / thống kê

- Lưu UTC; hiển thị/lọc ngày theo `Asia/Bangkok` (UTC+7). Khoảng `[start, next_day_start)`.
- Stats: tách số lượt xe (encounter), số event, số issue confirmed, số issue pending.
- Đếm `issues[]` theo code; legacy dùng `violation_type` nhưng báo `legacy` cho
  record chưa populate issues_json.

## 13. Cleanup (background worker)

- Default 90 ngày cho snapshot/clip. Bỏ qua record có `evidence_state='persisted'`
  và `hold=true`.
- Validate path trong root trước khi unlink; không theo symlink ra ngoài root.
- Lỗi PermissionError/OSError: KHÔNG clear DB reference, log vào
  `system_maintenance_log`.
- Crop cùng vòng đời với snapshot full-frame; xóa từng media sau khi đã verify.

## 14. Backup

- SQLite Backup API; đo thời gian giữ `_write_lock`, không giữ lock quá 30 giây.
- Mỗi bản: DB + manifest.json + snapshot/crop/clip + ảnh hồ sơ được DB tham chiếu
  + checksum (SHA-256).
- `complete` marker chỉ ghi khi mọi phần đã verify xong; nếu fail → marker
  `incomplete`, không chọn làm bản restore mới nhất.
- Lịch riêng (BACKUP_INTERVAL_HOURS); backup không phụ thuộc cleanup.
- Restore: vào thư mục/DB riêng; verify integrity_check + media hash; KHÔNG ghi
  đè DB/media vận hành.

## 15. Public register

- Bật qua env `PUBLIC_REGISTER_ENABLED=1` (mặc định `0` khi dùng dữ liệu thật).
- Khi tắt: `/api/register/*` trả 503 với `{ "enabled": false }`; trang frontend
  `/register` hiển thị "đang tạm đóng".
- Lookup/upload/register bị tắt đồng thời khi flag off.

## 16. CI

- Backend pytest, frontend lint/build, Node tests, Playwright **fail job khi fail**.
- Bỏ `|| true` / `continue-on-error` ở command test.
- Production test build SPA rồi request deep link thật; API 404 JSON, cookie/media
  đúng quyền, clip Range theo phiên bản đang cài.

## 17. Bàn giao Tích hợp

- Mọi sửa đổi trên file dùng chung (`app/db.py`, `app/schemas.py`,
  `app/config.py`, `app/main.py`, `app/api/camera.py`, `app/api/roi.py`,
  `app/tests/conftest.py`) phải ghi vào `tasks/task-02/integration/`
  dưới dạng: tên file, baseline, patch (diff dự thảo), migration SQL (nếu có),
  test sau tích hợp, owner hiện tại.
- Patch chỉ áp dụng khi Task 1 xác nhận đã nhận + tích hợp + test pass.
- File `app/api/admin.py`, `app/api/users.py`, `app/api/media.py`, `app/api/auth.py`,
  `app/api/register.py` đã có thay đổi trong working tree từ trước. Khi sửa,
  ghi rõ `integration_pending: <field>` cho từng thay đổi phụ thuộc patch chưa
  tích hợp. Không đánh dấu hoàn tất chỉ vì test hàm riêng lẻ đạt.