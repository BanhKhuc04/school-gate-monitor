# Sửa OCR pipeline — 03/10/2026

## Kết quả

- Khôi phục `list_recognition_reviews`, `get_recognition_review`, tạo review và ghi feedback trong `app/db.py`. Cả list/detail trả `version` để collector dùng trạng thái đã commit.
- Đăng ký `GET /api/training/recognition-reviews` với quyền admin, dùng chung query/filter/pagination của `/api/recognition/reviews`.
- Khôi phục `PlateReadResult.error`, các helper OCR hai dòng/chất lượng ảnh, gate-line/posture/dedup và các nhánh CV còn thiếu.
- Khôi phục `WebcamStream.read_source_frame()` để OCR đọc độ phân giải nguồn; `read_frame()` giữ giao diện preview tương thích.
- Migration bổ sung `operation`, `runner_type`, `split_hash` cho bảng job hiện có và các field candidate còn thiếu. Tên bảng thực tế của repository là **`dataset_jobs`**, trong DB riêng `data/training.db`.
- Khởi tạo/migrate DB training trong lifespan trước khi worker bắt đầu.
- Collector dùng feedback ID thật cho reconcile, chấp nhận crop fields của review DB và chỉ ACK cursor sau khi copy thành công; crop thiếu được retry.
- Frontend dùng API cùng origin qua Vite proxy, nhận session HttpOnly; WebSocket lấy host từ origin khi API base là relative.
- Fixture JWT/config và hot-reload được cách ly. Hai test collector cũ đã được cập nhật để pagination/idempotency kiểm tra trên crop copy thành công, phù hợp contract ACK.

## Căn nguyên và phạm vi khôi phục

Các file core đã quay về phiên bản cũ trong khi module/test Task 1–3 mới vẫn tồn tại. Tám lỗi collection là thiếu symbol/fixture của phiên bản mới, không phải lỗi cú pháp Python 3.

Đã tìm lại snapshot Git `bb79475` (base `83a0309`) và hợp nhất với nội dung đang có. Các bổ sung camera mapping/observation và router training hiện tại được giữ lại. Bản gốc cùng base/snapshot/merge được lưu trong `qa_logs/ocr_recovery/`; diff trước/sau nằm trong `qa_logs/ocr_review_diff/`. Trong lượt sửa lỗi, chưa reset/stage/commit; snapshot của nội dung trước khi sửa vẫn được giữ lại.

## Migration

CLI dùng SQLite online backup trước khi nâng schema:

```powershell
.\venv\Scripts\python.exe -m scripts.migrate_ocr_training
```

Có thể kiểm tra cài đặt mới bằng `--app-db`, `--training-db`, `--backup-dir` trỏ đến DB riêng. Migration tự kiểm tra integrity và chạy lại được; regression test chạy init hai lần trên job schema cũ, giữ nguyên row và state.

Đã chạy trên DB hiện tại. Backup:

- `data/backups/schema/app_20261003T051204398081Z.db`
- `data/backups/schema/training_20261003T051204398081Z.db`

Cả hai `PRAGMA integrity_check` trả `ok`. So sánh với backup giữ nguyên số bản ghi ở tất cả bảng chung, gồm 4.333 violation, 7 vehicle, 5 user, 3 review/feedback, 13 job, 2 candidate, 1 dataset. Chi tiết: `qa_logs/ocr_migration_checks.json`.

## Xác minh

- Tám module CV/OCR ban đầu, best-plate, camera capture, recognition reviews và camera mapping: 144/144 passed ở lượt kiểm tra tập trung.
- Backend full suite cuối: **1180 passed, 1 skipped, 0 failed** (1181 collected, 554,35 giây); log `qa_logs/ocr_fix_full_verified.log`, JUnit `qa_logs/ocr_fix_full_verified.xml`.
- Build frontend: `npm.cmd run build` passed (cảnh báo kích thước bundle hiện có).
- Chromium + API FastAPI thật + Vite proxy + SQLite riêng: **1/1 passed**, không có console/page error. Không dùng mock HTTP.
- Luồng browser đã kiểm tra: login 200, session sau reload, reviews API 200, tạo dataset từ UI, thêm sample qua API, xem label, tạo/hủy job từ UI, candidate có dữ liệu, mở ảnh/bbox, chỉnh bằng keyboard, PATCH 200 tăng version lên 1, refetch giữ bbox đã lưu.
- Startup QA đã chạy collector một cycle và copy crop thành công, đồng thời chạy training worker một cycle.
- Trên DB hiện tại: collector scan 3 review, reconcile_errors=0; training resume cycle chạy xong, 0 warning/error. Chi tiết: `qa_logs/ocr_live_worker_cycle.json`.
- Diff whitespace check passed (giữ line ending hiện có trong Git index).
- Test skip: `test_route_symlink_outside_root_kept` — Symlink không khả dụng trên hệ thống này.

Chạy lại browser test:

```powershell
cd frontend
node node_modules/@playwright/test/cli.js test --config playwright.ocr-live.config.js
```

Browser harness dùng DB/media QA riêng và tự dừng backend/Vite sau test. Ảnh xác minh: `qa_logs/ocr_browser/training-ui.png`, `qa_logs/ocr_browser/candidates-ui.png`; report: `qa_logs/ocr_browser/results.json`.

## Dữ liệu và giới hạn kiểm tra

Ba review trong DB hiện tại trỏ tới `snap_0.jpg`, `snap_1.jpg`, `snap_2.jpg`; các file này đang thiếu. Collector giữ cursor để retry, không đánh dấu đã copy. Đây là thiếu asset của dữ liệu cũ; không tạo ảnh thay thế cho chúng. Mẫu QA có crop đã được copy và kiểm tra bytes.

Browser dùng dữ liệu QA (candidate fixture chỉ để đọc giao diện); không promote model, không chạy train mới. Chưa kiểm chứng chất lượng OCR trên camera vật lý/RTSP trong lượt này.

Backend/Vite dự án chạy nền trước đó đã được dừng. Sau toàn bộ test, không còn process server dự án và không có listener trên 8000, 5173, 5174, 8026, 5196. Chi tiết: `qa_logs/ocr_process_cleanup.json`.

## Chuẩn bị commit và test thủ công

- Camera presets có tài khoản được chuyển sang `CAMERA_PRESETS_JSON` trong `.env` local; source mặc định chỉ có webcam/OBS. `.env.example` hướng dẫn định dạng JSON và không chứa thông tin đăng nhập thiết bị.
- Không in ephemeral JWT secret ra log.
- Vite config mặc định proxy thêm các guard API (recognition cards/log/image, plate-best, audio); `/guard` vẫn là route SPA.
- Kiểm tra bổ sung sau thay đổi cấu hình: 38/38 passed. Frontend lint exit 0, còn các warning hiện có.
- Source/module Task 1–3 cần cho bản OCR chạy độc lập được đưa vào cùng commit. Dữ liệu vận hành, model weights mới, output/log/DB QA và các file stage ngoài phạm vi được giữ local.
- Server test thủ công: backend `http://127.0.0.1:8000`, frontend `http://127.0.0.1:5173`. Dùng DB/media và cấu hình camera hiện tại; tạm tắt cleanup/backup tự động trong process test. Task 3 workers vẫn hoạt động.
- Đã kiểm tra backend OpenAPI 200, frontend login/guard HTML 200, auth/review guard API chưa login trả JSON 401 đúng qua proxy. Một nguồn camera chưa mở được ở thời điểm startup.
