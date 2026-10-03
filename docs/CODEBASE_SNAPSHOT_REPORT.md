# Báo cáo snapshot codebase — `project_motorbike_codebase.zip`

| | |
|---|---|
| Ngày tạo | 2026-09-29 11:19 GMT+7 |
| Commit | `9d81244` (`Give management (ban giám hiệu) full view access...`) |
| Nguồn | `git archive HEAD` — chỉ chứa file đã commit, không lẫn rác debug/dataset/venv |
| Số file | 297 |
| Dung lượng | ~1.0 MB (zip cũ 415 KB nhưng thiếu code phase mới; zip cũ hơn cũng lỡ kẹt `yolov8n.pt` 6.5MB, đã loại khỏi bản này) |

## Đã sửa so với bản zip cũ (tạo lúc 00:09, trước khi làm 11 tính năng)

- Zip cũ chỉ có code tại thời điểm **trước** toàn bộ Phase 0-3 (11 tính năng) và trước khi mở quyền cho Ban giám hiệu — thiếu ~2970 dòng code mới.
- Zip cũ vô tình nhét theo `yolov8n.pt` (~6.5MB, model weight COCO tự tải, không phải source) do file này bị track nhầm vào git từ trước — bản mới đã loại trừ khi zip. **Khuyến nghị riêng:** chạy `git rm --cached yolov8n.pt` để gỡ hẳn khỏi git tracking (ultralytics tự tải lại khi cần, không cần commit).

## Trạng thái tính năng trong snapshot này

| # | Tính năng | Trạng thái | Test |
|---|---|---|---|
| 1 | Phát hiện không biển số / biển số bị che (`NO_PLATE`/`PLATE_OBSCURED`) | ✅ | `test_vehicle_gate.py` |
| 2 | Lịch sử vi phạm theo học sinh + cờ tái phạm | ✅ | `test_repeat_offender.py` |
| 3 | Cảnh báo âm thanh phân loại theo mức độ ưu tiên | ✅ | Verify thủ công qua browser |
| 4 | Video clip 4s kèm ảnh vi phạm | ✅ | Test trực tiếp ghi file `.mp4` |
| 5 | Tìm kiếm nhanh học sinh (autocomplete) | ✅ | Verify UI |
| 6 | Timeline trực quan vi phạm theo học sinh | ✅ | Verify API + UI |
| 7 | Sức khỏe hệ thống mở rộng (FPS/độ trễ/tỉ lệ đọc) | ✅ (đã fix 1 crash) | `test_system.py` + browser |
| 8 | Xem trước trước khi dọn snapshot/clip cũ | ✅ | Verify API |
| 9 | Vai trò giáo viên chủ nhiệm (chỉ xem lớp mình) | ✅ (đã fix lộ nút admin) | `test_repeat_offender.py` + browser |
| 10 | Audit trail — trạng thái xử lý + ai xử lý | ✅ | `test_violation_status.py` + browser |
| 11 | Import CSV có bước xem trước (dry-run) | ✅ | Verify API |
| 12 | Mở quyền Ban giám hiệu: xem camera + vi phạm + xe đăng ký | ✅ | `test_vehicles.py`, `test_violation_status.py` + browser |

**Test suite:** 64/64 pytest pass tại commit `9d81244`.

## Chưa nằm trong snapshot này (việc còn tồn đọng, xem `docs/CURSOR_PLAN_11_FEATURES.md`)

| Việc | Ghi chú |
|---|---|
| `TopStatusBar` vẫn poll `/api/system/health` dư thừa cho vài role không cần | Đã fix cho riêng giáo viên, chưa audit hết các role khác |
| Dọn `.gitignore` cho rác debug (`debug_raw_*.jpg`, `*.zip`, `datasets/cvat_review`, notebook auto-label) | Đề xuất ở lượt review trước, chưa làm |
| Gom các file `PLAN*.md`/`TASKS*.md` rời rạc ở root vào `docs/archive/` | Đề xuất ở lượt review trước, chưa làm |
| Tách secret/port ra `.env` thay vì hardcode trong `app/config.py` | Đề xuất ở lượt review trước, chưa làm |
| CI tự động chạy pytest khi push | Chưa có |
