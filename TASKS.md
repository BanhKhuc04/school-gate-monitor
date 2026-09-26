# Checklist thực thi MVP — giao từng bước cho Cursor

> Đọc [PLAN.md](PLAN.md) trước (kiến trúc, cấu trúc thư mục, schema DB, requirements.txt) rồi mới bắt đầu. Làm **tuần tự từng bước**, không nhảy cóc — mỗi bước phải qua được "Tiêu chí kiểm tra" mới đánh dấu `[x]` và chuyển sang bước sau.

- [ ] **Bước 0 — Chuẩn bị môi trường**
  - Cài Python 3.10/3.11 (64-bit), tạo `venv`, `pip install -r requirements.txt` (tạo `requirements.txt` theo PLAN.md nếu chưa có).
  - Tiêu chí: script OpenCV 5 dòng mở webcam, hiện `cv2.imshow` thành công.

- [x] **Bước 1 — Mốc 1: cửa sổ phát hiện YOLOv8 thô (helmet)**
  - Model: Hugging Face `iam-tsr/yolov8n-helmet-detection` (2 lớp: With/Without Helmet), lưu `models/helmet_best.pt`. (Roboflow "NCKH 2023" 3-lớp bị bỏ — nguồn tải lỗi/cần API key, và gộp 1 model cho cả 2 việc chỉ là tối ưu không bắt buộc.)
  - Đã tạo `app/cv/capture.py`, `app/cv/detector.py`, `app/cv/smoke_test.py`.
  - Tiêu chí: `python -m app.cv.smoke_test` mở cửa sổ <3s, hiện box+nhãn (With Helmet/Without Helmet) kèm % tin cậy; `q` để thoát. **→ Bạn tự chạy lệnh này để xác nhận trước khi qua Bước 2.**

- [x] **Bước 2 — Model biển số + Cắt biển số + OCR (code xong, chờ bạn tự test bằng ảnh thật)**
  - Model: Hugging Face `Koushim/yolov8-license-plate-detection` → `models/plate_best.pt` (1 lớp `license_plate`).
  - Đã tạo `app/cv/ocr.py` (`read_plate`, `normalize_plate`, `read_plate_detailed`), `scripts/ocr_test.py`.
  - **→ Việc của bạn**: copy 5-10 ảnh biển số xe máy VN vào `data/samples/plates/`, chạy `python scripts/ocr_test.py`, tự xem kết quả có đọc được gần đúng không (chưa chính xác hoàn toàn là bình thường). Xác nhận xong mới giao Bước 3.

- [x] **Bước 3 — FastAPI + video MJPEG** — đã xác nhận: `/guard` stream sống, 2 model load đúng.

- [x] **Bước 4 — Cảnh báo: WebSocket + tiếng beep** — code đã review, logic đúng, WS kết nối được. Chưa thấy banner khi test bằng webcam laptop cận mặt (model chưa nhận ra do khác điều kiện với tập train ~761 ảnh người lái xe máy) — không phải bug, để fine-tune sau. Thử lại với khung hình xa hơn (đầu+vai) nếu muốn thấy demo chạy thật.

- [x] **Bước 5 — SQLite + CRUD admin** — đã test trực tiếp add/get/delete_vehicle, chuẩn hóa biển số đúng, dữ liệu ghi/xóa đúng trong `data/app.db`.

- [x] **Bước 6 — Đối chiếu đầy đủ + ghi log vi phạm** — code review phát hiện bug (ghi log vi phạm cả khi phòng trống không ai), đã fix (guard `helmet_dets` rỗng → bỏ qua). Logic OCR→whitelist→violation_type→cooldown→snapshot→DB→alert đã đúng theo PLAN.md.

- [ ] **Bước 7 — Hoàn thiện (không bắt buộc cho MVP)**
  - `README.md` hướng dẫn cài đặt/chạy, `.gitignore` (`venv/`, `data/app.db`, `data/snapshots/`, `models/*.pt`), `git init` + commit đầu tiên.

## Lộ trình giai đoạn sau (chưa làm, chỉ để tham khảo — xem chi tiết trong PLAN.md)

- [ ] Fine-tune OCR / train model nhận diện ký tự
- [ ] Module phân loại xe ≤50cc
- [ ] Module nhận diện khuôn mặt (cần quyết định lại on-premise vs cloud)
- [ ] Module phát hiện "dắt xe"
- [ ] Dashboard ban giám hiệu
