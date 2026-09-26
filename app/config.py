"""
Cấu hình hệ thống.
Các hằng số dùng chung, không phụ thuộc gì khác.
"""
import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

# Camera
CAMERA_INDEX = 0  # webcam mặc định

# Model paths
HELMET_MODEL_PATH = str(BASE_DIR / "models" / "helmet_best.pt")
PLATE_MODEL_PATH = str(BASE_DIR / "models" / "plate_best.pt")

# Detection thresholds
HELMET_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho helmet detection
PLATE_CONF_THRESHOLD = 0.25   # Ngưỡng confidence cho plate detection

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
