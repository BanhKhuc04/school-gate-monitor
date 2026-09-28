"""
Cấu hình hệ thống.
Các hằng số dùng chung, không phụ thuộc gì khác.
"""
import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

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


# Loop video when reading from file — kept for backwards compat (main gate only)
CAMERA_LOOP = _gate_cfgs["main"]["loop"]

# Model paths
HELMET_MODEL_PATH = str(BASE_DIR / "models" / "helmet_best.pt")
PLATE_MODEL_PATH = str(BASE_DIR / "models" / "plate_best.pt")
# yolov8n.pt/yolov8n-pose.pt COCO - ultralytics tự tải khi khởi tạo, không cần đặt vào models/
PERSON_MODEL_PATH = "yolov8n.pt"
POSE_MODEL_PATH = "yolov8n-pose.pt"

# ponytail: đã thử export ONNX + benchmark thật (scripts/export_onnx.py,
# scripts/benchmark_inference.py) — chậm hơn .pt trên CPU này (0.3x-1.0x), không
# phải giả thuyết đúng. KHÔNG dùng ONNX. Giữ 2 script lại làm tài liệu tham khảo
# nếu sau này đổi máy/CPU khác muốn đo lại.

# Detection thresholds
HELMET_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho helmet detection
PLATE_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho plate detection
PERSON_CONF_THRESHOLD = 0.4  # Ngưỡng confidence cho person detection (COCO)

# Chở quá số người quy định — xe máy chở nhiều hơn số này bị bắt lỗi TOO_MANY_RIDERS
MAX_RIDERS_PER_MOTORCYCLE = 2

# Frame processing
FRAME_SKIP = 2  # Xử lý cách 1 frame để giảm tải CPU (1 = mọi frame, 2 = cách 1 frame)

# Database
DB_PATH = str(BASE_DIR / "data" / "app.db")

# Snapshots
SNAPSHOTS_DIR = str(BASE_DIR / "data" / "snapshots")

# Video streaming
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480

# Violation cooldown (seconds)
VIOLATION_COOLDOWN = 60  # Không cảnh báo lại cùng biển số trong 60 giây (cho DB)
ALERT_COOLDOWN = 5       # Cooldown cảnh báo WebSocket (giây)

# JWT Authentication
# secrets.token_hex(32) → hardcoded (không sinh lại mỗi lần khởi động)
JWT_SECRET_KEY = "a3f8c1b9e2d47f0a5c6e8b3d9f1e2a4c7b5d9f3e1a8c6b4d2f0e7a3c5b9d"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12
