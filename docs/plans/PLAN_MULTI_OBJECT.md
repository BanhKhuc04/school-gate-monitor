# Nâng cấp: Nhận diện chính xác nhiều đối tượng trong 1 khung hình (quy mô trường học)

## Context

MVP hiện tại (xem [docs/plans/PLAN.md](docs/plans/PLAN.md)) hoạt động đúng với **1 người/1 xe trong khung hình** (test bằng webcam). Ở quy mô trường học thật, giờ cao điểm có nhiều xe xếp hàng cùng lúc qua cổng. `VideoPipeline._process_violations()` hiện dùng `any()` toàn cục (không phân biệt xe nào với xe nào) + chỉ lấy 1 biển số confidence cao nhất — sai hoàn toàn khi có ≥2 xe trong khung hình.

Đây là hạ tầng bắt buộc phải có **trước** khi mở rộng các tính năng khác (50cc, khuôn mặt, dắt xe) vì tất cả đều cần biết "phát hiện này thuộc về xe/người nào" ở cùng 1 khung hình.

## Kiến trúc thay đổi

Thêm **model thứ 3**: `yolov8n.pt` chuẩn COCO (ultralytics tự tải khi khởi tạo `YOLO('yolov8n.pt')`, không cần tải tay như 2 model trước), dùng lớp có sẵn `HelmetPlateDetector` (không viết class mới), chỉ lọc lấy class `person` (id=0 trong COCO).

**Luồng xử lý mới trong `VideoPipeline`**:
1. Chạy 3 detector: person, helmet, plate (như cũ, chỉ thêm 1 lệnh `.detect()`).
2. Với mỗi box `person` → tạo 1 "nhóm" (group).
3. Gán mỗi box `helmet`/`no-helmet` vào nhóm có box người chứa/overlap nó nhiều nhất (tính theo tâm điểm box helmet có nằm trong box person hay không — người đội mũ thì box mũ luôn nằm trong/sát phần trên box người).
4. Gán mỗi box `plate` vào nhóm có box người gần nhất theo trục ngang (x-center), vì biển số luôn nằm dưới thân xe, ngay dưới vị trí người ngồi.
5. Chạy lại đúng logic `_process_violations` hiện tại (OCR, tra whitelist, xác định violation_type, cooldown, ghi log, cảnh báo) **cho từng nhóm riêng biệt** thay vì 1 lần cho cả khung hình.
6. Helmet/plate không thuộc nhóm nào (không có person box gần) → bỏ qua, không tính vi phạm (tránh nhiễu từ người đi bộ ngoài lề khung hình).

**Không đổi**: schema DB, cooldown key (`plate_matched hoặc "UNKNOWN"` + `violation_type`) đã đúng cấu trúc để dùng lại nguyên vẹn cho từng nhóm — chỉ cần gọi hàm cũ nhiều lần thay vì 1 lần.

## File cần sửa

- `app/config.py`: thêm `PERSON_MODEL_PATH = "yolov8n.pt"` (ultralytics tự tải, không cần đặt vào `models/`), `PERSON_CONF_THRESHOLD`.
- `app/cv/pipeline.py`: 
  - Thêm `self._person_detector = HelmetPlateDetector(PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD)` — model COCO có rất nhiều class, cần lọc `class_name == 'person'` khi dùng.
  - Thêm hàm `_group_by_person(person_dets, helmet_dets, plate_dets) -> list[dict]` — trả về danh sách nhóm, mỗi nhóm có `helmet_dets` và `plate_dets` con thuộc về 1 người.
  - Sửa `_run_loop`: thay vì gọi `_process_violations(frame, helmet_dets, plate_dets)` 1 lần, gọi `_group_by_person(...)` trước, rồi loop qua từng nhóm gọi `_process_violations(frame, group['helmet_dets'], group['plate_dets'])`.
- Không cần sửa `app/db.py`, `app/cv/ocr.py`, `app/api/*` — không đổi schema hay route nào.

## Rủi ro cần lường trước

- `yolov8n.pt` COCO không được train riêng cho người ngồi trên xe máy — vẫn detect người tốt trong hầu hết góc nhìn vì "person" là 1 trong những class phổ biến/chính xác nhất của COCO.
- Model COCO có 80 class, không phải chỉ "person" — nhớ lọc đúng `class_name == 'person'`, bỏ qua các class khác (xe hơi, xe đạp... không dùng ở bước này).
- Thêm 1 model chạy mỗi frame → tăng tải CPU. Nếu giật nhiều, tăng `FRAME_SKIP` trong config.py.
- Ngưỡng "helmet nằm trong box person" là heuristic đơn giản (không phải pose estimation thật) — vẫn có thể sai khi 2 người đứng sát/che nhau. Đủ tốt cho MVP mở rộng, không phải giải pháp hoàn hảo — nếu sau này cần chính xác hơn nữa (nhiều xe chen chúc), cân nhắc model tracking (ByteTrack/DeepSORT) tích hợp sẵn trong `ultralytics` (`model.track()` thay vì `model()`).

## Kiểm tra

Đứng 2 người trước webcam cùng lúc (nếu có thể, 1 người xa/1 gần để giả lập nhiều xe), 1 người che đầu (giả "without helmet") người kia để đầu trần bình thường qua model. Xác nhận `/admin/violations` ghi **đúng số lượng vi phạm tách biệt** (không gộp thành 1 dòng `MULTIPLE` sai), và log không nhầm biển số của người này sang vi phạm của người kia (nếu test được với 2 biển số khác nhau).
