# Cursor tự chạy: hoàn thiện 24 bước trong TASKS_NEXT_ROUND.md

## Nguyên tắc (giống đợt trước, đọc lại nếu quên)

- Test xong mới commit, commit xong mới sang bước kế. Mỗi bước trong TASKS_NEXT_ROUND.md = 1 commit riêng.
- Ghi log liên tục vào `CURSOR_RUN_LOG.md` (file đã có từ đợt trước, append tiếp, đừng tạo file mới) — mỗi bước 1 mục: đã làm gì, tự test gì, kết quả gì, có gì đánh dấu **[CẦN NGƯỜI KIỂM TRA]** (đã liệt kê sẵn ở các bước 12/18/22 trong TASKS_NEXT_ROUND.md, nhưng nếu phát hiện thêm chỗ nào khác cần mắt/tai người thì đánh dấu thêm).
- Time-box mỗi bước ~30-45 phút nếu kẹt, ghi rõ đã thử gì rồi chuyển bước độc lập tiếp theo.
- Không `git push`, chỉ commit local.

## Khác với đợt trước — guardrail đã đổi

Đợt SPA/auth trước cấm đụng `app/cv/*`. **Đợt này CÓ đụng `app/cv/pipeline.py` và `app/config.py`** (thêm face recognition + pose detection, bước 17 và 21) — đây là chủ đích, không phải lỗi. Nhưng:
- **Không được sửa/xóa logic helmet/plate/OCR/group-by-person hiện có** trong `pipeline.py` — chỉ THÊM bước mới bên cạnh, đúng theo PLAN_NEXT_ROUND.md mô tả (bọc try/except riêng để lỗi face/pose không làm hỏng luồng helmet/plate đang chạy tốt).
- Vẫn không đụng `CAMERA_INDEX`, model paths của helmet/plate trong `config.py` (đã cấu hình đúng theo phần cứng OBS của người dùng).
- Vẫn không xóa `data/app.db`, không `git push`.

## Hạ tầng test đã có từ đợt trước

`POST /api/dev/trigger-test-alert` đã tồn tại (đợt trước) — dùng lại cho các test cần giả lập vi phạm. Bước 16 trong đợt này thêm `POST /api/dev/trigger-test-face-match` tương tự cho face recognition. Với pose/dắt xe (bước 19), test bằng pytest thuần với keypoint giả lập tay (không cần camera thật) — xem PLAN_NEXT_ROUND.md mục (g) để biết chính xác cách viết `classify_posture()` sao cho pure-function, dễ test.

## Thứ tự làm

Đúng theo TASKS_NEXT_ROUND.md, từ Bước 1 đến Bước 24, tuần tự — không nhảy cóc, không làm song song nhiều bước.

**Lưu ý cài đặt bước 15 (insightface)**: model `buffalo_l` tự tải lần đầu chạy `FaceAnalysis(...).prepare(...)` — cần internet, có thể mất vài phút, đừng hủy giữa chừng. Nếu môi trường chạy autonomous không có internet ổn định lúc đó, ghi rõ vào CURSOR_RUN_LOG.md và thử lại, đừng bỏ qua bước này để nhảy sang bước 16 (bước 16 phụ thuộc bước 15 chạy được).

**Nếu xong cả 24 bước còn thời gian**: viết thêm test edge-case (token hết hạn, upload ảnh sai định dạng cho enroll khuôn mặt, CSV có dòng trống), KHÔNG tự ý làm 50cc hoặc settings/config UI (đã ghi rõ ngoài phạm vi trong TASKS_NEXT_ROUND.md).
