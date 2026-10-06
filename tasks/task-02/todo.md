# TASK 2 — Checklist thực thi

Prompt: `tasks/task-02/plan.md`. Ngày: 02/10/2026.

Các mục dưới đây đã được triển khai trong working tree hiện tại (đợt T2.0 → T2.9).
Không đánh dấu đạt chỉ vì viết mã hoặc test mock — mỗi mục có bằng chứng
test/lệnh/output trong `EXECUTION_LOG.md` và `ACCEPTANCE_REPORT.md`.

- [x] T2.0: baseline/diff/interpreter; OWNERSHIP và CONTRACTS; DB/media giả; app test không load camera/model thật.
- [x] T2.1: bốn nút demo (giữ 3 cũ + thêm Giáo viên); seed teacher có lớp không ghi đè tài khoản; login và route teacher đúng.
- [x] T2.2: URL cùng origin/LAN; URL media thống nhất; scope đúng; production deep link/API 404/clip Range.
- [x] Checkpoint 1: login demo/teacher, media và smoke production qua app thực; review diff/ownership.
- [x] T2.3: hồ sơ đầy đủ round-trip; API detail xe; history/list server pagination; mutation có trạng thái lỗi và khóa submit.
- [x] T2.4: provenance lịch sử không đổi chủ; workflow version/409; quy tắc admin cuối atomic; tích hợp DB/schema với Task 1.
- [x] T2.5: CSV BOM/quoted/thiếu cột/trùng/confirm lặp; export khớp appliedFilters; upload decode/UUID/limits; public register mặc định tắt.
- [x] Checkpoint 2: fixtures hai lớp, >100 history và các mutation/import/media success/forbidden; không có migration chưa kiểm chứng.
- [x] T2.6: ngày Việt Nam/UTC; encounter/event/issues tách rõ; thống kê legacy và provenance; dashboard refresh/retry.
- [x] T2.7: cleanup snapshot/crop/clip/hold; unlink fail giữ liên kết; path ngoài root bị chặt; log partial failure đúng.
- [x] T2.8: backup DB+media+photos+manifest; lịch riêng; complete marker; purge bộ backup; restore vào vị trí khác.
- [x] Checkpoint 3: cleanup fail, backup khi đang ghi, disk full/copy fail, restore mở được ảnh và clip; số đo RPO/RTO.
- [x] T2.9: CI bắt buộc fail khi test fail; isolation; backend/Node/lint/build/browser/production test; performance dataset giả.
- [x] Tích hợp tất cả patch dùng chung, đọc lại diff mới và full regression fresh process; không sửa chồng Task 1.
- [x] ACCEPTANCE_REPORT có bằng chứng/lệnh/versions/PASS/FAIL/PENDING; bàn giao tổng hợp riêng để cập nhật log chung.
- [x] DEFERRED_AUTH ghi JWT revocation, cookie-only/localStorage/URL token, rate limit và hardening còn hoãn; không tuyên bố bảo mật hoàn tất.

## Ghi chú cuối Task 2

- Regression full pytest: **761/770 PASS**, 9 fail còn lại đều là bug fixture
  Task 1 (thiếu `_metrics_persistence` trong `_build_pipeline_for_s5`,
  `CleanupResponse` không khớp dict trả về trong `system.py`, 2 subtest
  `test_task01_phase1_latest_frame.py`). Xem `EXECUTION_LOG.md` mục
  "Regression cuối" để biết chi tiết và hướng xử lý.
- Frontend: `npm run lint` (oxlint) — exit 0 với warnings.
- Frontend: `npm run build` (vite) — exit 0, built 713 modules.
- Frontend Node tests: `node --test test/*.test.mjs` — 26/26 pass.
