# Checklist: React SPA + đăng nhập phân quyền

> Đọc [docs/plans/PLAN_SPA_AUTH.md](docs/plans/PLAN_SPA_AUTH.md) trước. Giao từng bước 1 cho Cursor, test xong mới sang bước sau — đặc biệt bước 8-13 (frontend) vì mỗi trang phụ thuộc trang trước chạy đúng.

- [ ] **1** — Bảng `users` + `app/auth.py` + `seed_user.py` + `POST /api/auth/login`
- [ ] **2** — `require_role` + `GET /api/auth/me`
- [ ] **3** — Vehicle CRUD → JSON, chặn role `admin`
- [ ] **4** — `GET /api/violations` + mount `/media` + `snapshot_url`
- [ ] **5** — `get_violation_stats()` + `GET /api/stats/summary`
- [ ] **6** — Auth cho `video_feed` + `ws` (token qua query string)
- [ ] **7** — `CORSMiddleware`
- [ ] **8** — Scaffold `frontend/` (Vite+React+Tailwind) + trang Login thật
- [ ] **9** — `GuardPage` + `AlertBanner`
- [ ] **10** — `AdminVehiclesPage` + `AdminViolationsPage`
- [ ] **11** — `DashboardPage`
- [ ] **12** — Xóa route/HTML Jinja cũ
- [ ] **13** — Build production + SPA fallback trong `main.py`
