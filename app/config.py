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

# Model paths
HELMET_MODEL_PATH = str(BASE_DIR / "models" / "helmet_best.pt")
PLATE_MODEL_PATH = str(BASE_DIR / "models" / "plate_best.pt")
# yolov8n.pt COCO - ultralytics tự tải khi khởi tạo, không cần đặt vào models/
PERSON_MODEL_PATH = "yolov8n.pt"

# Detection thresholds
HELMET_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho helmet detection
PLATE_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho plate detection
PERSON_CONF_THRESHOLD = 0.4  # Ngưỡng confidence cho person detection (COCO)

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
