# Vòng phát triển tiếp theo: model biển số + đa camera + deploy VPS

## Context

Test thật trên `data/snapshots/*.jpg` cho thấy `models/plate_best.pt` (pretrained, chưa fine-tune) **detect được 0/5 ảnh** — đây là lỗi nghiêm trọng nhất hiện tại, không phải lỗi code mà là model không khớp domain (VN, camera cổng trường). `models/helmet_best.pt` test tương tự cho kết quả khá hơn (4/5), không cấp bách bằng.

Đang fine-tune `plate_best.pt` trên Kaggle (GPU T4 free) bằng dataset VN thật 8259 ảnh (`datasets/vn_plate_detect/`, nguồn winter2897/Real-time-Auto-License-Plate-Recognition-with-Jetson-Nano, đã tách train/val 90/10 sẵn, script `scripts/train_plate_kaggle.ipynb`). Có thể có thêm `helmet_best.pt` fine-tune song song bằng dataset Roboflow "non-bao-hiem" (VN riêng) nếu người dùng đã chạy phần đó.

Giao diện đã dựng lại theo bộ mockup Stitch mới ("School Gate Monitor" — Sidebar trái + TopStatusBar, 7/8 trang, bỏ hẳn trang khuôn mặt) — **không cần làm lại phần này**, chỉ số liệu thật, không bịa (đã cố tình bỏ RFID/thi đua/GPU Jetson vì không có backend).

VPS `103.101.162.111` đã có script deploy sẵn (`scripts/deploy_vps.sh`) nhưng **chưa từng chạy thật** — cần người dùng tự SSH (Claude không được phép tự đăng nhập vào server thật bằng mật khẩu).

Camera thật (Imou F52P) đang đặt mua, chưa lắp — pipeline hiện tại chỉ đọc **1 nguồn camera duy nhất** (biến `CAMERA_SOURCE` trong `app/config.py`, singleton `_pipeline` trong `app/cv/pipeline.py`), chưa hỗ trợ 2 cổng vào/ra.

## Ghi chú nền tảng đã xác minh (đọc code thật, không đoán)

- `app/cv/pipeline.py`: `get_pipeline()` trả về 1 singleton toàn cục `_pipeline`, không nhận tham số. Muốn nhiều camera phải đổi sang dict theo key, không đổi logic detect bên trong `VideoPipeline`.
- `app/api/guard.py`: `/guard/video_feed` và `/guard/ws` gọi thẳng `get_pipeline()` không tham số — cần thêm query param để chọn đúng instance.
- `venv` chỉ có `torch` CPU — model mới tải về từ Kaggle vẫn phải chạy được trên CPU (không đổi kiến trúc yolov8n sang bản nặng hơn).
- Dataset Vietnam plate ở `datasets/vn_plate_detect/` là ảnh biển số thật VN (xe máy + ô tô + quân đội/ngoại giao) — không phải ảnh crop sát như `datasets/plate_char_ocr/` (dataset đó dùng cho OCR ký tự, khác mục đích).

## (a) Nhận kết quả model từ Kaggle — làm trước tiên

1. Người dùng gửi file `best.pt` tải từ Kaggle Output (`plate_finetune_v1/weights/best.pt`, và `helmet_finetune_v1/weights/best.pt` nếu có).
2. Viết `scripts/eval_model_real.py`: load model ứng viên, chạy `detect()` trên toàn bộ `data/snapshots/*.jpg`, in tỉ lệ ảnh có ≥1 detection, so sánh với model cũ (test bằng cách chạy cả 2 model qua cùng bộ ảnh, in bảng so sánh).
3. Nếu tốt hơn rõ rệt: thay `models/plate_best.pt` (backup bản cũ thành `models/plate_best.pt.bak` trước khi ghi đè), chạy lại toàn bộ `pytest app/tests/` (hiện 44 test) đảm bảo không vỡ gì.
4. Trigger thử alert thật qua GuardPage (dev endpoint `/api/dev/trigger-test-alert`) để xác nhận UI vẫn hoạt động với model mới.

## (b) Hỗ trợ nhiều camera (vào/ra)

Chuẩn bị trước phần code (không cần đợi camera thật tới), cấu hình mặc định vẫn 1 cổng để không phá vỡ hành vi hiện tại:

1. `app/config.py`: đổi `CAMERA_SOURCE` đơn thành `GATES = {"main": {...}}` đọc từ env, hỗ trợ thêm gate thứ 2 qua `CAMERA_SOURCE_SECONDARY`/`GATE_SECONDARY_NAME` nếu được set, không set thì chỉ có 1 gate như hiện tại.
2. `app/cv/pipeline.py`: đổi `_pipeline` singleton toàn cục thành `_pipelines: dict[str, VideoPipeline]`, `get_pipeline(gate_id="main")`.
3. `app/api/guard.py`: `/guard/video_feed?gate=main` và `/guard/ws?gate=main` — mặc định `gate=main` để tương thích ngược với code/test hiện tại.
4. `frontend/src/pages/GuardPage.jsx`: chỉ hiện dropdown chọn cổng nếu backend báo có >1 gate (gọi `/api/system/health` mở rộng thêm field `gates: [...]`) — ẩn hoàn toàn dropdown khi chỉ có 1 cổng, không hiện UI thừa.
5. Test: `app/tests/test_smoke.py` thêm case gọi `/guard/video_feed?gate=main` xác nhận vẫn hoạt động y hệt trước khi đổi.

## (c) Deploy VPS thật — cần người dùng tự làm

`scripts/deploy_vps.sh` đã viết sẵn, tự SSH `root@103.101.162.111` rồi chạy script. Sau khi xong: đổi mật khẩu VPS (đã lộ trong lịch sử chat), test truy cập `http://103.101.162.111/` từ trình duyệt ngoài.

## (d) KHÔNG làm đợt này

- **Class xe đạp điện riêng** — không có dataset ảnh thật tải được (đã tìm, chỉ có 1 bài báo nghiên cứu không public data). Chờ tự quay video tại cổng trường thật rồi mới làm.
- **Còi/loa vật lý (GPIO)** — chưa có phần cứng, đã ghi chú `ponytail:` trong `AlertBanner.jsx`.
- **Nhận diện khuôn mặt** — đã bỏ hẳn (quyết định pháp lý, không làm lại).
