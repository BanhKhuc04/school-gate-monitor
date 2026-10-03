# TASK 2 — Ownership (đăng ký phạm vi file)

> Đăng ký: 02/10/2026 01:05 ICT (UTC+7).
> Branch: `dot-4-all-12`, HEAD `83a0309`.
> Làm việc ngay trong working tree hiện tại (Task 1 đã đăng ký cùng chiến lược).
> Working tree có nhiều thay đổi chưa commit của các task khác — Task 2 **không tự
> stash/reset/clean** và sẽ bảo vệ phần đó.

## Phạm vi Task 2 — file chính (đọc kỹ trước khi sửa)

### Backend (đọc/sửa trực tiếp)
- `app/api/admin.py`
- `app/api/register.py`
- `app/api/media.py`
- `app/api/users.py`
- `app/api/auth.py` (chỉ sửa phản hồi trả về `homeroom_class` — đã làm ở HEAD, kiểm tra bổ sung)
- `app/background.py` (cleanup/backup nhưng cẩn trọng vì file dùng chung — phối hợp Task 1)
- `app/main.py` (chỉ phần SPA fallback + production deep-link)
- `app/db.py` (chỉ migration helper — xem mục "File dùng chung")

### Frontend (đọc/sửa)
- `frontend/src/pages/LoginPage.jsx` (thêm nút demo Teacher)
- `frontend/src/pages/AdminVehiclesPage.jsx`, `StudentViolationHistoryPage.jsx`,
  `AdminRosterPage.jsx`, `AdminUsersPage.jsx`, `AdminViolationsPage.jsx`,
  `PublicRegisterPage.jsx`, `DashboardPage.jsx`
- `frontend/src/api/client.js` (chỉ sửa `API_BASE_URL` từ hard-code localhost sang
  cùng origin; giữ axios client + interceptor + cookie)
- `frontend/vite.config.js` (giữ nguyên; chỉ kiểm tra proxy vẫn hoạt động)
- `frontend/src/App.jsx`, `Sidebar`, `RequireRole` (chỉ điều hướng & phân quyền;
  KHÔNG đổi component giám sát của Task 1)
- `frontend/src/auth/AuthContext.jsx` (chỉ thêm `homeroom_class` khi lưu user; KHÔNG
  đổi cách lưu/xác thực token)

### Scripts / tests / docs (Task 2 tự quản)
- Mở rộng `scripts/seed_user.py` hỗ trợ teacher (idempotent, không ghi đè)
- Mới: `scripts/seed_demo.py` — tạo bộ dữ liệu demo (2 lớp, teacher + roster,
  1 số vi phạm) cho dev/demo
- Mới: `app/tests/test_task02_*` — test riêng Task 2 (login teacher, scope filter,
  CSV BOM/quoted, public register off, cleanup safety, backup restore)
- Tài liệu Task 2: `tasks/task-02/OWNERSHIP.md`, `CONTRACTS.md`, `EXECUTION_LOG.md`,
  `ACCEPTANCE_REPORT.md`, `DEFERRED_AUTH.md`, `integration/` (patch bàn giao)

### File dùng chung — Task 1 đang là bên tích hợp

- `app/db.py`, `app/schemas.py`, `app/config.py`, `app/main.py`,
  `app/api/camera.py`, `app/api/roi.py`, fixture chung `app/tests/conftest.py`.
- **Nguyên tắc**: KHÔNG đồng thời ghi các file này. Nhu cầu, hợp đồng, migration
  và patch dự thảo phải ghi vào `tasks/task-02/integration/` để Task 1 tiếp nhận.
- Trong working tree hiện tại, các file `app/api/admin.py`, `app/api/users.py`,
  `app/api/auth.py`, `app/api/media.py`, `app/api/register.py`, `app/db.py`,
  `app/main.py`, `app/schemas.py`, `app/config.py`, `app/tests/conftest.py` đã có
  thay đổi chưa commit. Trước khi sửa, đối chiếu `git diff -- <file>` để biết
  ranh giới giữa các task. Khi xung đột không rõ, ghi vào mục bên dưới.

## File KHÔNG thuộc phạm vi Task 2 (Task 1 giữ)

- `app/cv/*` (CV runtime — pipeline, detector, ocr, pose, plate_voter, recorder, roi...)
- `app/api/guard.py` (luồng giám sát trực tiếp)
- `frontend/src/pages/GuardPage.jsx`, `RecognitionLogPanel`, `PlateReviewPanel`,
  `AlertBanner`, `utils/speak.js`, `alertAudio.js`, `alertFilter.js`,
  `useAudioLease.js`
- Benchmark / training pipeline của Task 1

## Xung đột / cần đối chiếu với các task khác

| File | Trạng thái hiện tại | Ghi chú Task 2 |
|------|----------------------|-----------------|
| `app/api/admin.py` | Modified, +stub Teacher trong violations/encounters/vehicle detail | Thuộc scope Task 2. Đã có teacher class-scope từ Task 1/T2 trước. Đối chiếu diff trước khi sửa thêm. |
| `app/api/auth.py` | Modified, trả `homeroom_class` từ login | Task 2 xác nhận đủ (không cần sửa thêm) — đã xong ở HEAD. |
| `app/api/users.py` | Modified, có thêm `teacher` + `homeroom_class` | Thuộc scope Task 2 — sẽ bổ sung normalize homeroom_class, idempotency cho admin cập nhật. |
| `app/db.py` | Modified, đã có init_db() với nhiều migration | Thuộc file dùng chung — Task 2 chỉ ghi migration mới (e.g. trạng thái vi phạc versioning) qua `tasks/task-02/integration/`. |
| `app/main.py` | Modified, có SPA fallback | Thuộc file dùng chung — Task 2 bàn giao bất kỳ thay đổi nào qua `tasks/task-02/integration/`. |
| `app/tests/conftest.py` | Modified, đã seed 4 role | Task 2 dùng lại; không tự ý thay fixture chung. Thêm seed/fixture riêng trong test_task02_*. |

## Quy tắc làm việc

- Một file tại một thời điểm chỉ có một task ghi. Khi cần sửa file dùng chung, ghi
  nhu cầu vào `tasks/task-02/integration/` và **không sửa trực tiếp**.
- Khi cần, chạy `git diff -- <file>` để chứng minh ranh giới trước/sau.
- Không commit toàn bộ thay đổi của working tree. Chỉ commit file thuộc scope Task 2
  sau khi self-review.
- Không push, deploy, ghi đè DB/media/video/log người dùng.