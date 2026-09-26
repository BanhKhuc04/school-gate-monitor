# Hệ thống giám sát cổng trường học — MVP (Biển số + Mũ bảo hiểm)

## Context

Trường học muốn một hệ thống giám sát cổng ra vào bằng camera để tự động: nhận diện biển số xe, phân loại xe có phải xe ≤50cc hay không, nhận diện khuôn mặt, phát hiện có đội mũ bảo hiểm hay không, và phát hiện học sinh có dắt xe (đi bộ dắt) khi vào cổng hay không — phục vụ 3 nhóm người dùng: ban giám hiệu (báo cáo/thống kê), admin (quản trị dữ liệu), và bảo vệ (giám sát thời gian thực kèm cảnh báo bằng âm thanh).

Đây là dự án hoàn toàn mới, người thực hiện mới bắt đầu với AI/Computer Vision. Sau khi trao đổi, đã thống nhất:
- **Phạm vi MVP**: chỉ làm 2 trong 5 tính năng — **nhận diện biển số** và **phát hiện mũ bảo hiểm** — để có sản phẩm chạy được sớm, ổn định, dựa trên model có sẵn thay vì phải tự huấn luyện từ đầu.
- **Phần cứng**: dùng webcam laptop để demo/thử nghiệm trước, chưa cần camera IP thật.
- **Lưu trữ**: chưa quyết định on-premise hay cloud — nhưng vì MVP **không** đụng đến dữ liệu khuôn mặt (dữ liệu nhạy cảm của trẻ vị thành niên), nên MVP dùng SQLite lưu cục bộ, không phụ thuộc cloud. Quyết định on-premise/cloud sẽ được đặt lại khi làm tới module nhận diện khuôn mặt.
- **Quy trình làm việc**: bản kế hoạch này là tài liệu **định hướng để bàn giao cho Cursor** thực thi — vì vậy được viết đủ chi tiết, cụ thể tên file/thư mục, để Cursor có thể code theo từng bước mà không cần đoán ý.

Các tính năng còn lại (phân loại 50cc, nhận diện khuôn mặt, phát hiện dắt xe, dashboard ban giám hiệu) được **cố tình để dành cho giai đoạn sau** — chỉ nêu điểm mở rộng, không thiết kế chi tiết ở đây.

## Nghiên cứu nền tảng (đã xác minh, không cần tìm lại)

- **Phát hiện mũ bảo hiểm**: dùng model YOLOv8n từ Hugging Face `iam-tsr/yolov8n-helmet-detection` (2 lớp: `With Helmet`, `Without Helmet`, mAP@50 ≈88%) — tải trực tiếp không cần đăng nhập/API key. (Ban đầu định dùng model Roboflow "NCKH 2023" 3-lớp gộp cả biển số, nhưng nguồn tải bị lỗi/yêu cầu API key; bỏ ý tưởng "1 model làm cả 2 việc" — đó chỉ là tối ưu tiện lợi, không phải yêu cầu bắt buộc.)
- **Phát hiện vùng biển số**: dùng **model YOLO riêng** (không gộp chung với model mũ bảo hiểm nữa), lấy từ repo GitHub có sẵn trọng số tải trực tiếp, không cần tài khoản/API key — ví dụ `mrzaizai2k/License-Plate-Recognition-YOLOv7-and-CNN` (trọng số đính kèm GitHub Releases) hoặc `trungdinh22/License-Plate-Recognition` (trọng số nằm sẵn trong repo). Việc này thuộc phạm vi Bước 2, chưa cần cho Bước 1.
- **OCR biển số**: chưa có model Việt hóa "tải về chạy luôn" đạt chất lượng cao. Các repo GitHub uy tín (winter2897/Real-time-Auto-License-Plate-Recognition-with-Jetson-Nano, mrzaizai2k/License-Plate-Recognition-YOLOv7-and-CNN) đều dùng cách phức tạp hơn (YOLO nhận diện từng ký tự). Với người mới bắt đầu, chọn **EasyOCR** (đơn giản, cài `pip install`, có sẵn trọng số, ~95% độ chính xác ký tự trong điều kiện tốt) làm bước khởi đầu, chấp nhận độ chính xác chưa cao, sẽ fine-tune sau.
- **Thư viện đề xuất**: `ultralytics` (YOLOv8), `easyocr`, `opencv-python` — đều cài qua pip, không cần GPU cho MVP.

## Kiến trúc hệ thống

**Backend**: FastAPI, xử lý webcam bằng 1 **thread nền riêng** (không dùng asyncio cho phần suy luận CV vì YOLO/EasyOCR là các lệnh gọi blocking — thread đơn giản hơn nhiều so với async cho người mới).

**Truyền video ra trình duyệt**: MJPEG streaming (`StreamingResponse`, `multipart/x-mixed-replace`) — frontend chỉ cần thẻ `<img src="...">`, không cần vẽ canvas/JS phức tạp. Bounding box được vẽ sẵn ở server bằng `cv2.rectangle`/`cv2.putText`.

**Cảnh báo**: WebSocket riêng (`/guard/ws`) chỉ truyền JSON nhỏ (`{"type": "violation", "plate": ..., "violation_type": ..., "timestamp": ...}`). Thread nền đẩy sự kiện vào `queue.Queue`; vòng lặp WebSocket bất đồng bộ đọc queue mỗi ~200ms và gửi cho trình duyệt. Trình duyệt phát tiếng "beep" bằng Web Audio API (tạo sóng âm bằng oscillator — không cần file âm thanh) và hiện banner đỏ.

**Luồng xử lý mỗi frame** (trong thread nền):
1. Chụp frame từ webcam (OpenCV).
2. Chạy 2 model YOLOv8 riêng: model mũ bảo hiểm → box `With Helmet`/`Without Helmet`; model biển số → box vùng biển số.
3. Suy ra trạng thái mũ bảo hiểm (có box `helmet` chồng lên vùng đầu người lái hay không).
4. Cắt vùng `license-plate`, chia đôi trên/dưới (biển số xe máy VN 2 dòng), chạy EasyOCR từng dòng, ghép lại, chuẩn hóa (viết hoa, bỏ khoảng trắng/dấu gạch).
5. Tra chuỗi biển số đã chuẩn hóa trong bảng `registered_vehicles`.
6. Xác định loại vi phạm: `NO_HELMET`, `PLATE_NOT_REGISTERED`, `PLATE_UNREADABLE`, hoặc không vi phạm.
7. Nếu có vi phạm (và không trong thời gian "cooldown" cho cùng biển số) → lưu ảnh chụp, ghi vào `violation_events`, đẩy cảnh báo qua WebSocket.
8. Vẽ box/nhãn lên frame, lưu làm "frame mới nhất" để endpoint MJPEG phục vụ.

**Frontend — 2 trang cho MVP**:
- **`/guard`** (bảo vệ): video trực tiếp có box, banner cảnh báo + danh sách cảnh báo gần nhất qua WebSocket, phát tiếng beep.
- **`/admin`**: CRUD dạng HTML thuần (form POST-redirect-GET, không cần JS framework) cho `registered_vehicles` (biển số, tên học sinh, lớp), cộng bảng xem `violation_events` gần đây kèm link ảnh chụp.
- **Dashboard ban giám hiệu**: **chưa xây**, chỉ để điểm mở rộng — sau này đọc từ chính bảng `violation_events` (đã có `timestamp`, `violation_type` đủ để thống kê) qua endpoint mới, không đụng vào pipeline hiện tại.

## Cấu trúc thư mục dự án

```
D:\Work\Project_motorbike\
├── requirements.txt
├── README.md
├── .gitignore
├── models\
│   ├── helmet_best.pt               # model mũ bảo hiểm, HF iam-tsr/yolov8n-helmet-detection (không commit git)
│   └── plate_best.pt                # model vùng biển số, thêm ở Bước 2 (không commit git)
├── data\
│   ├── app.db                      # SQLite (không commit)
│   ├── snapshots\                  # ảnh chụp vi phạm (không commit)
│   └── samples\plates\             # vài ảnh biển số mẫu để test OCR
├── app\
│   ├── __init__.py
│   ├── main.py                     # khởi tạo FastAPI(), mount router/static
│   ├── config.py                   # CAMERA_INDEX, MODEL_PATH, DB_PATH, ngưỡng, cooldown...
│   ├── db.py                       # sqlite3 + init_db() + hàm CRUD
│   ├── cv\
│   │   ├── __init__.py
│   │   ├── capture.py              # WebcamStream: bọc cv2.VideoCapture
│   │   ├── detector.py             # HelmetPlateDetector: bọc ultralytics YOLO(model_path)
│   │   ├── ocr.py                  # read_plate(crop) + normalize_plate(text)
│   │   ├── pipeline.py             # điều phối capture→detect→ocr→db→alert, chạy trong thread nền
│   │   └── smoke_test.py           # Bước 1: webcam + box YOLO trong cửa sổ cv2.imshow
│   ├── api\
│   │   ├── __init__.py
│   │   ├── schemas.py              # Pydantic models (VehicleIn/Out, ViolationOut)
│   │   ├── guard.py                # GET /guard, GET /guard/video_feed, WS /guard/ws
│   │   └── admin.py                # GET/POST /admin/vehicles..., GET /admin/violations
│   ├── templates\
│   │   ├── guard.html
│   │   └── admin.html
│   └── static\js\guard.js          # WebSocket + Web Audio beep + banner
└── scripts\
    └── ocr_test.py                 # chạy OCR trên data/samples/plates, in kết quả để kiểm tra
```

**Quan hệ import**: `app/main.py` import `app.db`, `app.cv.pipeline`, `app.api.guard`, `app.api.admin`. `app.cv.pipeline` import `app.cv.capture`, `app.cv.detector`, `app.cv.ocr`, `app.db`. `app.api.*` import `app.db` và `app.api.schemas`. `app.config` không phụ thuộc gì, được import ở bất cứ đâu cần hằng số. Nhờ vậy `smoke_test.py` và `scripts/ocr_test.py` chạy độc lập, không cần khởi động FastAPI.

## Schema database (dùng `sqlite3` thuần, không ORM)

Lý do chọn `sqlite3` thay vì SQLAlchemy: với người mới, SQL thuần trong vài hàm nhỏ dễ đọc/debug hơn, và có thể mở trực tiếp `data/app.db` bằng công cụ miễn phí "DB Browser for SQLite" để kiểm tra.

```sql
CREATE TABLE IF NOT EXISTS registered_vehicles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number  TEXT NOT NULL UNIQUE,   -- đã chuẩn hóa: viết hoa, không dấu cách/gạch
    student_name  TEXT NOT NULL,
    student_class TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS violation_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    plate_read     TEXT,                  -- kết quả OCR thô, có thể NULL/rỗng
    plate_matched  TEXT,                  -- biển số khớp trong whitelist, nếu có
    helmet_status  TEXT NOT NULL,         -- 'helmet' | 'no_helmet' | 'unknown'
    violation_type TEXT NOT NULL,         -- 'NO_HELMET' | 'PLATE_NOT_REGISTERED' | 'PLATE_UNREADABLE' | 'MULTIPLE'
    snapshot_path  TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_violation_events_timestamp ON violation_events(timestamp);
```

`app/db.py` cung cấp: `get_connection()`, `init_db()`, `add_vehicle`, `get_vehicle_by_plate`, `list_vehicles`, `update_vehicle`, `delete_vehicle`, `add_violation_event`, `list_violations(limit)`. Dùng `threading.Lock()` cấp module quanh các thao tác ghi vì cả thread pipeline lẫn request handler FastAPI đều đụng vào DB.

## requirements.txt

```
fastapi>=0.110,<0.113
uvicorn[standard]>=0.29,<0.31
opencv-python>=4.9,<4.11
ultralytics>=8.2,<8.3
easyocr>=1.7,<1.8
jinja2>=3.1,<3.2
python-multipart>=0.0.9
numpy>=1.26,<2.0
```

Lưu ý: `ultralytics` sẽ tự kéo theo `torch`/`torchvision` (bản CPU trên Windows) — lần đầu tải khá nặng (~1-2GB). `numpy<2.0` được ghim để tương thích an toàn với `opencv-python`/`easyocr`/`ultralytics` hiện tại. EasyOCR tự tải trọng số riêng lần đầu khởi tạo `easyocr.Reader(...)` — cần internet 1 lần.

## Rủi ro & giới hạn cần lường trước

- Độ chính xác OCR sẽ chưa cao trên webcam thô cho tới khi fine-tune bằng ảnh thật — EasyOCR gốc không được huấn luyện riêng cho biển số 2 dòng của Việt Nam.
- Suy luận CPU (YOLOv8n + EasyOCR mỗi frame) có thể chỉ đạt FPS thấp; nếu giật, xử lý cách frame (`FRAME_SKIP` trong config) thay vì mọi frame.
- Ánh sáng, góc camera, chói sáng ảnh hưởng mạnh đến cả detection lẫn OCR; điều kiện webcam laptop sẽ khác camera cổng cố định sau này.
- Model Roboflow chỉ train trên ~761 ảnh — có thể có nhận diện sai/sót, đặc biệt khi nhiều người hoặc góc lạ trong khung hình.
- Nên tải trọng số `.pt` về máy thay vì phụ thuộc API suy luận trực tuyến của Roboflow cho webcam liên tục — API có độ trễ, phụ thuộc internet, và giới hạn tần suất gọi ở gói miễn phí.
- SQLite phù hợp cho MVP một máy, nhưng cần cân nhắc chuyển sang PostgreSQL nếu sau này hệ thống mở rộng ra nhiều cổng/nhiều máy.

## Lộ trình giai đoạn sau (chỉ nêu, chưa thiết kế chi tiết)

- Fine-tune OCR (hoặc train model YOLO nhận diện từng ký tự) dùng ảnh biển số thật tích lũy từ log vi phạm của MVP.
- Thêm module phân loại xe ≤50cc, gắn vào chung pipeline hiện tại.
- Thêm module nhận diện khuôn mặt — **lúc này phải đặt lại quyết định on-premise vs cloud** vì liên quan dữ liệu sinh trắc học trẻ vị thành niên.
- Thêm module phát hiện "dắt xe" (đi bộ dắt vs. ngồi lái) — nhiều khả năng cần phân tích chuỗi ảnh/pose thay vì một frame đơn.
- Xây dashboard ban giám hiệu — endpoint đọc mới trên bảng `violation_events` sẵn có, không cần sửa pipeline.

## Cách dùng tài liệu này với Cursor

Mở thư mục `D:\Work\Project_motorbike` trong Cursor. Xem checklist từng bước tại [TASKS.md](TASKS.md) — giao cho Cursor **từng bước một** (không giao hết 1 lần), yêu cầu nó đọc phần kiến trúc/schema ở file này trước khi code, và chỉ đánh dấu hoàn thành khi qua được tiêu chí kiểm tra của bước đó.
