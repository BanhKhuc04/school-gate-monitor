# TASK 2 — Auth Strategy Audit (REOPEN 2026-10-02)

> Mục đích: xác nhận REOPEN chỉ thị "giữ auth hiện tại, không mở rộng
> migration" — `app/api/auth.py` không bị sửa chồng ngoài phạm vi đã đăng
> ký trong `tasks/task-02/CONTRACTS.md §1` và `tasks/task-02/EXECUTION_LOG.md
> mục T2.1`.

## Kết quả `git status` & `git log`

```
$ git status --short app/api/auth.py
 M app/api/auth.py     # chỉ modified (không staged), không có conflict marker

$ git log --oneline app/api/auth.py | Select-Object -First 5
4174e30 Add violation status/audit trail, teacher role, video clips,
         repeat-offender tracking, and 6 other guard-system features
b26ad45 Add JWT auth + role-based API, fix OBS camera backend and box flicker
```

## Kết quả `git diff HEAD -- app/api/auth.py`

Diff đầy đủ lưu tại `tasks/task-02/REOPEN_AUTH_AUDIT.diff.txt` (83 dòng).
Tóm tắt theo nhóm thay đổi:

| # | Nhóm | Trước HEAD | Sau (working tree) | Hợp đồng |
|---|------|-----------|--------------------|---------|
| 1 | Module docstring | chỉ liệt kê `POST /login` | thêm `POST /logout` + `GET /me` — bổ sung 2 route đã có sẵn từ HEAD b26ad45 (chỉ doc) | T2.1 §1 (login + me) |
| 2 | Imports | không có `Response`, không có `COOKIE_*` | thêm `Response` + `COOKIE_NAME/SECURE/SAMESITE/JWT_EXPIRE_HOURS` | D6.1 §1 (HttpOnly cookie) |
| 3 | `POST /login` signature | `def login(body)` | `def login(body, response: Response)` | D6.1 §1 |
| 4 | `POST /login` body | trả `access_token, token_type, username, role` | thêm `homeroom_class`, set cookie `gate_session` (httponly, samesite, secure, max_age=JWT_EXPIRE_HOURS*3600) | T2.1 §1, D6.1 §1 |
| 5 | `POST /login` docstring | ngắn (chỉ JSON body) | rõ ràng hơn về cookie + Bearer fallback | T2.1 |
| 6 | `POST /logout` | KHÔNG có | mới: clear `gate_session` cookie, trả `{"ok": True}` | D6.1 §1 (idle session) |
| 7 | `GET /me` docstring | "Requires Authorization: Bearer header" | "Accepts Authorization: Bearer header OR gate_session cookie" | D6.1 §1 |

## Phân tích ranh giới Task 2 vs auth-scope ngoài

- ✅ Không thêm route mới ngoài 2 route đã tồn tại từ HEAD (`/login`, `/me`).
  `/logout` đã có mặt trong HEAD chỉ thiếu doc; T2 bổ sung implementation.
- ✅ Không đổi shape `access_token` / `token_type` / `username` / `role` —
  chỉ thêm field optional `homeroom_class` đã đăng ký trong
  `CONTRACTS.md §1` ("role `teacher` bắt buộc có `homeroom_class`").
- ✅ Không động vào `app/auth.py` (verify_password/create_access_token/
  get_current_user) — verify token vẫn Bearer header hoặc cookie, không
  thêm cơ chế xác thực mới.
- ✅ Không đổi bcrypt cost factor; password policy, JWT secret, JWT
  expire hours đều từ `app/config.py` (không sửa chồng).
- ✅ `DEFERRED_AUTH.md` (đã có từ đợt T2.1) vẫn liệt kê: JWT revocation,
  cookie-only (bỏ Bearer), rate limit login, session hardening, password
  policy — đều hoãn, không bị đẩy ngầm vào đợt REOPEN.

## Các điểm "không sửa chồng" trong REOPEN

- ❌ Không thêm JWT revocation list (DEFERRED_AUTH).
- ❌ Không bỏ Bearer Authorization (vẫn nhận Bearer + cookie song song).
- ❌ Không thêm rate limit / lockout cho `/login` (DEFERRED_AUTH).
- ❌ Không thêm password policy / complexity rule (DEFERRED_AUTH).
- ❌ Không thêm session refresh / sliding window (DEFERRED_AUTH).
- ❌ Không migrate token storage (vẫn cho phép localStorage ở frontend —
  theo `AUTH.md` đã viết từ T2.1).
- ❌ Không thêm CSRF token cho cookie (HttpOnly + SameSite=Lax hiện đủ
  cho scope MVP; note trong DEFERRED_AUTH.md).

## Kết luận

`app/api/auth.py` chỉ thêm 2 thứ so với HEAD:

1. HttpOnly cookie `gate_session` được set khi `/login` thành công
   (D6.1 — đăng ký từ R5; đã document trong CONTRACTS.md §1).
2. Endpoint `POST /logout` clear cookie (D6.1).

Tất cả khớp với `tasks/task-02/CONTRACTS.md §1` và `DEFERRED_AUTH.md`.
Không có sửa chồng ngoài phạm vi Task 2 đã đăng ký. REOPEN có thể tiếp
tục với giả định auth surface giữ nguyên.

## Phụ lục — Diff thô

Đã dump đầy đủ tại `tasks/task-02/REOPEN_AUTH_AUDIT.diff.txt` (83 dòng).