# Nâng cấp giao diện: React SPA + đăng nhập phân quyền 3 vai trò

## Context

Hệ thống giám sát cổng trường (MVP + multi-object) đang chạy tốt về mặt CV (helmet/plate/person detection, OCR, ghi log vi phạm), nhưng giao diện web hiện tại rất thô: HTML thuần server-render (Jinja2), không CSS framework, không có nav dùng chung, và **hoàn toàn không có đăng nhập/phân quyền** — ai mở link cũng vào sửa được danh sách xe đăng ký.

Theo đúng định hướng ban đầu (3 phần mềm riêng cho ban giám hiệu/admin/bảo vệ), và các quyết định đã chốt:
- **Làm UI trước**, các tính năng CV còn lại (50cc, khuôn mặt, dắt xe) làm sau.
- **SPA thật bằng React** (không phải chỉ style lại HTML cũ).
- **Khuôn mặt lưu on-premise** khi làm sau (không ảnh hưởng plan này).
- **Cần đăng nhập phân quyền 3 vai trò**: `admin` (quản lý xe đăng ký), `security`/bảo vệ (chỉ xem camera + cảnh báo), `management`/ban giám hiệu (chỉ xem thống kê).

Phát hiện thêm khi rà lại code: `admin_violations.html` đang link `/{{ snapshot_path }}` nhưng `app/main.py` chỉ mount `/static`, không mount `/data` — **link xem ảnh vi phạm đang bị hỏng từ trước**, plan này tiện sửa luôn.

**Kiến trúc: React + Vite**, JWT bearer token, giữ nguyên toàn bộ logic CV/DB hiện có.

## Auth

Bảng mới `users` trong `app/db.py`:
```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'security', 'management')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
)
```
Hàm mới: `create_user`, `get_user_by_username`, `get_violation_stats()`.

`app/auth.py` mới: `bcrypt` cho hash mật khẩu, `PyJWT` cho token (12h, không refresh/revoke — đủ cho 3 tài khoản nội bộ). `hash_password`, `verify_password`, `create_access_token`, `decode_access_token`, `get_current_user`, `require_role(*roles)`.

`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS` thêm vào `app/config.py`.

`scripts/seed_user.py` — CLI tạo user theo role.

## API JSON

`app/api/auth.py`: `POST /api/auth/login`, `GET /api/auth/me`.

`app/api/admin.py` → JSON: `GET/POST /api/vehicles`, `PUT/DELETE /api/vehicles/{id}` (role admin), `GET /api/violations` (thêm `snapshot_url`, sửa bug link hỏng). Mount `/media` → `SNAPSHOTS_DIR`.

`GET /api/stats/summary` (role management, admin) dùng `get_violation_stats()`.

`app/api/guard.py`: giữ nguyên MJPEG + WebSocket, thêm auth qua **query string `?token=`** (vì `<img>`/`WebSocket()` không gửi được header).

`CORSMiddleware` cho `http://localhost:5173`.

## React app (`frontend/`)

Vite + React + Tailwind + React Router + axios (interceptor gắn token, tự logout khi 401) + recharts.

`AuthContext`, `RequireRole` (UX only — chặn thật ở server), `NavBar`, 4 trang: `LoginPage`, `GuardPage` (+ `AlertBanner` port từ `guard.js`), `AdminVehiclesPage` + `AdminViolationsPage`, `DashboardPage`.

## Dev & deploy

Dev: `uvicorn` (`:8000`) + `npm run dev` (`:5173`), CORS nối.
Production: `npm run build` → `frontend/dist/`, `main.py` mount static + route catch-all SPA fallback **đăng ký sau cùng** (sau mọi router khác).

## Không đổi

`app/cv/*`, toàn bộ hàm cũ trong `app/db.py`. `app/templates/*.html` + `guard.js` cũ xóa ở bước cuối, không xóa dần.

## Rủi ro

- Token `localStorage`, không revoke được (đợi hết hạn 12h).
- Token qua query string cho video/WS — lộ trong log/history, chấp nhận vì LAN nội bộ.
- `/media` không auth-protect.
- `JWT_SECRET_KEY` cứng trong code — chuyển ra `.env` nếu repo public sau này.
- Route catch-all SPA fallback sai thứ tự sẽ nuốt mất API.

## Xem chi tiết 13 bước build → [docs/plans/TASKS_SPA_AUTH.md](docs/plans/TASKS_SPA_AUTH.md)
