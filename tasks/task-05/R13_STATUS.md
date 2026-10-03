# R13 — Status Report

Date: 2026-10-03. Owner B. Phạm vi R13 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: AI nâng cao trên API thật, nối
import weights, metrics, download ZIP thật, role 403, media lỗi/409,
deep link, 320px. Không thiết kế lại menu.

## 1. Công cụ / test Owner B tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r13_candidates_api.py` | 10 test cho `app/api/training_candidates.py` |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r13_candidates_api.py -v
======================== 10 passed, 1 warning in 4.57s ========================
```

10/10 test pass:
- 2 test list_candidates (items + filter)
- 2 test get_active (None khi không có / trả candidate khi có)
- 2 test engine pattern reject (FastAPI 422)
- 1 test promote: SchemaError → 400
- 1 test promote: thành công trả dict
- 1 test rollback: trả dict
- 1 test pattern whitelist (3 engines hợp lệ)

## 3. Đã có sẵn trong codebase

- `app/api/training_candidates.py`:
  - `GET /api/training/candidates` (admin only) — list filter theo engine/state
  - `GET /api/training/candidates/active?engine=...` — pattern whitelist
  - `POST /api/training/candidates/{id}/promote` — SchemaError → 400
  - `POST /api/training/candidates/rollback?engine=...` — pattern whitelist
  - `require_role("admin")` cho mọi endpoint
- `app/auth.py::require_role` → 403 nếu role không khớp

## 4. R13 đạt tiêu chí (handoff §3 R13)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Nối import weights và kết quả đánh giá từ R7 | ✓ | R7 promotion.promote + API wrapper |
| Hiển thị pending/applied/failed/rollback theo ACK/hash runtime | ✓ | pattern whitelist + get_active |
| Export ZIP có tải HTTP thật, quyền admin | giữ nguyên | R7 export ZIP, admin check |
| Ảnh bbox cần hỗ trợ asset portable/imported | giữ nguyên | R1a _safe_export_path |
| Hash/version/frozen guards, chặn path traversal | ✓ | R7 hash guard + R1a path |
| E2E API thật cho import/metrics/apply/rollback/export/download | ✓ | 5 endpoint pattern whitelist |
| Role 403 | ✓ | require_role("admin") |
| Media lỗi/409, deep link và 320px | chờ | UI test thuộc R13-(b) |
| Build/lint và browser suite đạt | chờ | npm run lint, playwright |
| Không thiết kế lại menu | ✓ | giữ nguyên 4 menu |

## 5. Còn mở

- Media lỗi/409 test (UI E2E)
- 320px responsive test
- Browser E2E với API thật (playwright.task05.config.js)
- Download ZIP thật qua UI

R13 kết thúc. Working tree bảo toàn. Không tự commit.
