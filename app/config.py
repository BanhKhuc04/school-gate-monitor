"""
Cấu hình hệ thống.
Các hằng số dùng chung, không phụ thuộc gì khác.
"""
import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

# Nạp biến môi trường từ file .env (nếu có) trước khi đọc bất kỳ os.environ.get
# nào bên dưới — không override biến đã set sẵn trong shell/hệ thống.
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

# Thiết bị chạy model — tự động dùng GPU nếu máy có (torch bản CUDA + driver
# NVIDIA hợp lệ), fallback về CPU nếu không. Import torch ở đây là rẻ vì
# ultralytics (dependency bắt buộc) đã kéo theo torch, không thêm chi phí gì.
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"

# Camera
CAMERA_INDEX = 1  # OBS Virtual Camera (index 0 la webcam vat ly, xac nhan qua probe)

# ─── Gates (multi-camera) ──────────────────────────────────────────────────────
#
# GATES is a dict of gate configs keyed by gate_id (string).
# Each gate has its own camera source. At least one gate must exist.
#
# Backwards-compat: CAMERA_SOURCE still works as the single-source env var;
# it is mapped to the "main" gate so existing deployments are unaffected.
#
# To add a second gate, set CAMERA_SOURCE_SECONDARY (and optionally
# GATE_SECONDARY_NAME). GATE_SECONDARY_NAME overrides the display name only;
# the key in GATES dict is always "secondary".
#
# GATE_<ID>_SOURCE   — camera source for gate <ID> (index, path, or RTSP URL)
# GATE_<ID>_LOOP     — loop video for gate <ID> when source is a file path (default "1")
# GATE_<ID>_NAME     — human-readable name for gate <ID> shown in UI

_gate_cfgs: dict[str, dict] = {}

# Primary gate (always present, matches legacy CAMERA_SOURCE behaviour)
_primary_source = os.environ.get("CAMERA_SOURCE")
if _primary_source is None:
    _default_main = CAMERA_INDEX
elif _primary_source.strip().lstrip("-").isdigit():
    _default_main = int(_primary_source)
else:
    _default_main = _primary_source

_gate_cfgs["main"] = {
    "source": _default_main,
    "loop": os.environ.get("CAMERA_LOOP", "1") == "1",
    "name": os.environ.get("GATE_MAIN_NAME", "Cổng Chính"),
}

# Secondary gate (optional — only added when CAMERA_SOURCE_SECONDARY is set)
_secondary_source = os.environ.get("CAMERA_SOURCE_SECONDARY")
if _secondary_source is not None and _secondary_source.strip() != "":
    _gate_cfgs["secondary"] = {
        "source": _secondary_source,
        "loop": os.environ.get("GATE_SECONDARY_LOOP", "1") == "1",
        "name": os.environ.get("GATE_SECONDARY_NAME", "Cổng Phụ"),
    }

# Public constant — read-only after startup
GATES: dict[str, dict] = _gate_cfgs

# Danh sách nguồn camera hay dùng — hiển thị dạng dropdown ở /admin/camera.
# Thêm nguồn mới = thêm 1 dòng ở đây, không cần UI quản lý.
CAMERA_PRESETS = [
    {"label": "Webcam laptop", "source": "0"},
    {"label": "OBS Virtual Camera", "source": "1"},
]
# Camera RTSP thật (IP + tài khoản riêng của từng nơi lắp đặt) KHÔNG được hardcode
# ở đây (sẽ lộ khi push lên git) — set qua biến môi trường CAMERA_PRESET_RTSP_*
# nếu muốn preset đó xuất hiện trong dropdown, xem .env.example.
_rtsp_label = os.environ.get("CAMERA_PRESET_RTSP_LABEL")
_rtsp_url = os.environ.get("CAMERA_PRESET_RTSP_URL")
if _rtsp_label and _rtsp_url:
    CAMERA_PRESETS.append({"label": _rtsp_label, "source": _rtsp_url})


# Loop video when reading from file — kept for backwards compat (main gate only)
CAMERA_LOOP = _gate_cfgs["main"]["loop"]

# Model paths
HELMET_MODEL_PATH = str(BASE_DIR / "models" / "helmet_best.pt")
PLATE_MODEL_PATH = str(BASE_DIR / "models" / "plate_best.pt")
# Model đọc từng ký tự biển số (YOLO) — chỉ dùng khi file tồn tại (train bằng
# scripts/train_all.py), không có thì OCR tự dùng EasyOCR như trước.
PLATE_OCR_MODEL_PATH = os.environ.get("PLATE_OCR_MODEL_PATH") or str(BASE_DIR / "models" / "plate_ocr_best.pt")
# yolov8n.pt/yolov8n-pose.pt COCO - ultralytics tự tải khi khởi tạo, không cần đặt vào models/
# Có GPU: dùng bản "s" (lớn hơn ~3x, bắt người/xe ở xa tốt hơn rõ rệt) — GPU dư sức
# chạy. CPU giữ bản "n" để không tụt FPS. Đè bằng env PERSON_MODEL_PATH nếu muốn.
PERSON_MODEL_PATH = os.environ.get("PERSON_MODEL_PATH") or ("yolov8s.pt" if DEVICE == "cuda" else "yolov8n.pt")
POSE_MODEL_PATH = os.environ.get("POSE_MODEL_PATH") or "yolov8n-pose.pt"

# ponytail: đã thử export ONNX + benchmark thật (scripts/export_onnx.py,
# scripts/benchmark_inference.py) — chậm hơn .pt trên CPU này (0.3x-1.0x), không
# phải giả thuyết đúng. KHÔNG dùng ONNX. Giữ 2 script lại làm tài liệu tham khảo
# nếu sau này đổi máy/CPU khác muốn đo lại.

# Detection thresholds
HELMET_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho helmet detection
PLATE_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho plate detection
PERSON_CONF_THRESHOLD = 0.4  # Ngưỡng confidence cho person detection (COCO)
# Hạ từ 0.5 xuống 0.3 (2026-09-29) — người ở xa/bị che một phần trong crop nhỏ
# thường không đạt 0.5, khiến pose model bỏ qua hoàn toàn (không trả khớp nào),
# posture_status rơi về 'unknown'. Đánh đổi: dễ bắt khớp sai hơn khi ảnh mờ/nhiễu.
POSE_CONF_THRESHOLD = 0.3  # Ngưỡng confidence cho pose/khớp xương (YOLOv8-pose)

# Chở quá số người quy định — xe máy chở nhiều hơn số này bị bắt lỗi TOO_MANY_RIDERS
MAX_RIDERS_PER_MOTORCYCLE = 2

# Xe/người còn đang ở SÁT MÉP khung hình (chưa vào/đang ra hết khung) → CHƯA đánh
# giá vi phạm cho nhóm đó ở frame này (không có tracker theo dõi liên tục qua nhiều
# frame, nên "còn chạm mép" là tín hiệu rẻ tiền nhất để biết vật thể chưa vào hết
# khung — tránh báo sai NO_PLATE/PLATE_OBSCURED chỉ vì biển số chưa kịp lọt vào
# khung hình, và tránh chụp snapshot khi xe/người còn bị cắt cụt ở rìa ảnh).
# Tính theo % kích thước khung hình để không phụ thuộc độ phân giải camera.
FRAME_EDGE_MARGIN_RATIO = 0.03

# Frame processing
FRAME_SKIP = 2  # Xử lý cách 1 frame để giảm tải CPU (1 = mọi frame, 2 = cách 1 frame)

# Database
DB_PATH = str(BASE_DIR / "data" / "app.db")

# Snapshots
SNAPSHOTS_DIR = str(BASE_DIR / "data" / "snapshots")

# Video streaming — độ phân giải CHỤP từ camera (càng cao, ảnh càng nét cho
# OCR/ảnh bằng chứng). Không dùng trực tiếp cho detect (xem DETECT_WIDTH/HEIGHT)
# vì detect trên ảnh to sẽ chậm đi — 2 giá trị tách riêng để vừa nhanh vừa nét.
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720

# Độ phân giải resize xuống CHỈ để chạy 3 model detect (person/helmet/plate) —
# giữ nguyên tốc độ detect như cũ dù ảnh chụp to hơn. Kết quả detect được quy
# đổi lại về tọa độ ảnh gốc (VIDEO_WIDTH/HEIGHT) ngay sau khi detect xong, nên
# OCR/vẽ box/lưu snapshot đều dùng ảnh gốc nét — đây là fix thật cho lỗi OCR
# đọc rỗng dù box detect đúng 85%: đã đo thật, cùng 1 ảnh đọc đúng "188888" ở
# độ phân giải gốc nhưng đọc rỗng khi resize xuống 640x480 trước khi OCR.
DETECT_WIDTH = 640
DETECT_HEIGHT = 480

# Violation cooldown (seconds)
VIOLATION_COOLDOWN = 60  # Không cảnh báo lại cùng biển số trong 60 giây (cho DB)
ALERT_COOLDOWN = 5       # Cooldown cảnh báo WebSocket (giây)

# Feature 2: ngưỡng "vi phạm lặp lại"
REPEAT_OFFENDER_WINDOW_DAYS = 30
REPEAT_OFFENDER_THRESHOLD = 3   # >= 3 vi phạm trong window → gắn cờ

# Feature 4: video clip ngắn
VIOLATION_CLIP_SECONDS = 4
VIOLATION_CLIP_FPS = 8          # thấp hơn hiển thị (20fps) để giảm CPU encode + dung lượng

# Đợt 2, Bước 1: vote biển số đa khung hình — xem app/cv/plate_voter.py
PLATE_VOTE_WINDOW_SEC = 2.5         # cửa sổ thời gian giữ mẫu đọc để vote
PLATE_VOTE_MIN_AGREE = 2            # cần >= N lần đọc giống nhau trong window để tin
PLATE_MIN_CONFIDENCE_SINGLE = 0.55  # HOẶC 1 lần đọc confidence >= ngưỡng này là đủ tin ngay

# Đợt 2, Bước 3: ghép 1 lượt xe từ 2 camera trước+sau — xem app/cv/event_correlator.py
CORRELATION_TIME_WINDOW_SEC = 15    # tìm ứng viên trong ±15 giây quanh timestamp
CORRELATION_MIN_SIMILARITY = 0.85  # SequenceMatcher.ratio() tối thiểu để coi là "cùng biển"

# Đợt 2, Bước 4: tự động dọn snapshot/clip cũ theo lịch — xem app/background.py::MaintenanceWorker
# Bật/tắt master switch — đặt CLEANUP_ENABLED=0 trong env để chỉ chạy cleanup khi admin bấm tay
# (vd. trên môi trường test, khi benchmark, hoặc khi muốn tắt tạm thời không phải sửa code).
CLEANUP_ENABLED = os.environ.get("CLEANUP_ENABLED", "1") == "1"
CLEANUP_INTERVAL_HOURS = int(os.environ.get("CLEANUP_INTERVAL_HOURS", "24"))
CLEANUP_RETENTION_DAYS = int(os.environ.get("CLEANUP_RETENTION_DAYS", "90"))

# Đợt 2, Bước 6: backup SQLite (đặt trước để Bước 4 không phải sửa config lại khi gọi backup job)
BACKUP_ENABLED = os.environ.get("BACKUP_ENABLED", "1") == "1"
BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_KEEP_COUNT = int(os.environ.get("BACKUP_KEEP_COUNT", "14"))
BACKUP_DIR = os.environ.get("BACKUP_DIR") or str(BASE_DIR / "data" / "backups")
BACKUP_MEDIA_ENABLED = os.environ.get("BACKUP_MEDIA_ENABLED", "0") == "1"

# Đợt 2, Bước 7: ghi hình liên tục (continuous recording)
# MẶC ĐỊNH TẮT — benchmark FPS/latency thật trước khi đề xuất bật cho máy thật
# (xem bài học _clip_buffer: ghi MP4 qua cv2.VideoWriter chiếm CPU đáng kể, có thể
# làm AI pipeline chậm). Xem docs/CURSOR_PLAN_DOT2_NANG_CAP.md mục "Bước 7".
CONTINUOUS_RECORDING_ENABLED = os.environ.get("CONTINUOUS_RECORDING_ENABLED", "0") == "1"
CONTINUOUS_RECORDING_SEGMENT_MINUTES = int(os.environ.get("CONTINUOUS_RECORDING_SEGMENT_MINUTES", "5"))
CONTINUOUS_RECORDING_FPS = int(os.environ.get("CONTINUOUS_RECORDING_FPS", "10"))
# Resolution ghi thấp hơn VIDEO_WIDTH/HEIGHT để giảm CPU encode + dung lượng (giống
# cách _clip_buffer resize xuống 640x360 trước khi ghi clip vi phạm).
CONTINUOUS_RECORDING_WIDTH = int(os.environ.get("CONTINUOUS_RECORDING_WIDTH", "854"))
CONTINUOUS_RECORDING_HEIGHT = int(os.environ.get("CONTINUOUS_RECORDING_HEIGHT", "480"))
CONTINUOUS_RECORDING_RETENTION_DAYS = int(os.environ.get("CONTINUOUS_RECORDING_RETENTION_DAYS", "7"))
CONTINUOUS_RECORDING_DIR = os.environ.get("CONTINUOUS_RECORDING_DIR") or str(BASE_DIR / "data" / "recordings")

# JWT Authentication
# BẮT BUỘC set JWT_SECRET_KEY qua biến môi trường khi deploy thật — key này
# từng bị hardcode thẳng trong file (push lên git công khai = ai cũng tự ký
# được token admin giả). Sinh key mới: python -c "import secrets; print(secrets.token_hex(32))"
_DEV_ONLY_JWT_SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or _DEV_ONLY_JWT_SECRET_KEY
if JWT_SECRET_KEY == _DEV_ONLY_JWT_SECRET_KEY:
    print("[Config] CẢNH BÁO: JWT_SECRET_KEY chưa được set qua biến môi trường — "
          "đang dùng key mặc định KHÔNG AN TOÀN, chỉ hợp lệ cho dev/test. "
          "Set JWT_SECRET_KEY trong .env trước khi chạy production.")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12
