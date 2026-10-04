"""
Cấu hình hệ thống.
Các hằng số dùng chung, không phụ thuộc gì khác.
"""
import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

# Nạp .env ở gốc dự án — trước đây file .env tồn tại (có CAMERA_SOURCE,
# CAMERA_SOURCE_SECONDARY...) nhưng KHÔNG được load ở đâu cả, nên sửa .env
# không có tác dụng gì (phát hiện lúc cấu hình 2 camera Imou: sửa .env xong
# GATES vẫn đọc ra giá trị cũ vì os.environ.get() không thấy gì trong .env).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Thiết bị chạy model — tự động dùng GPU nếu máy có (torch bản CUDA + driver
# NVIDIA hợp lệ), fallback về CPU nếu không. Import torch ở đây là rẻ vì
# ultralytics (dependency bắt buộc) đã kéo theo torch, không thêm chi phí gì.
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    if DEVICE == "cuda":
        # KHÔNG bật cudnn.benchmark: pose (batch N người, crop mỗi lần một cỡ)
        # và quét vùng biển đổi shape liên tục, mỗi shape mới bắt cuDNN đo lại
        # — đo thật trên video cổng trường: pose có lượt 1.2 s, AI còn 2-3 fps;
        # tắt đi thì số frame xử lý tăng 2.3x.
        torch.backends.cudnn.benchmark = False
except ImportError:
    DEVICE = "cpu"

# FP16 (half precision) cho inference GPU — nhanh hơn đáng kể trên GPU có
# Tensor Core (RTX trở lên) với độ chính xác giảm không đáng kể cho detection/
# pose. Tắt tự động trên CPU (PyTorch không hỗ trợ half trên CPU).
USE_FP16 = DEVICE == "cuda"

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

# ─── Camera roles + profiles (Phase 3 — Task 1) ───────────────────────────────
#
# Each gate gets a role + profile that decides which models to load:
#   role:
#     - "front": person + helmet + pose (full AI stack); used for the
#       primary gate watching riders approach.
#     - "rear":  plate + vehicle (lightweight OCR stack); used for the
#       secondary gate watching license plates from behind.
#     - "aux":   auto-detect from primary if missing (default).
#   profile:
#     - "full":      all models loaded (default for "front").
#     - "ocr_only": plate detector + tracker only; no helmet/pose.
#     - "minimal":   tracker only; helmet/plate disabled.
#
# Env-driven per gate:
#   GATE_<ID>_ROLE       — front | rear | aux
#   GATE_<ID>_PROFILE    — full | ocr_only | minimal
# Backwards-compat: gates không set role/profile sẽ mặc định "front" + "full".

_VALID_ROLES = {"front", "rear", "aux"}
_VALID_PROFILES = {"full", "ocr_only", "minimal"}


def _resolve_role(gate_id: str) -> str:
    role = os.environ.get(f"GATE_{gate_id.upper()}_ROLE", "").strip().lower()
    if role in _VALID_ROLES:
        return role
    # Default: "main" gate is "front" (legacy), "secondary" is "rear"
    # (matches camera mapping ở production setup).
    return "front" if gate_id == "main" else "rear"


def _resolve_profile(gate_id: str, role: str) -> str:
    prof = os.environ.get(f"GATE_{gate_id.upper()}_PROFILE", "").strip().lower()
    if prof in _VALID_PROFILES:
        return prof
    # Defaults:
    #   front role → full stack (person + helmet + pose + plate)
    #   rear role  → ocr_only (plate detector + tracker only, no helmet)
    #   aux role   → minimal (just tracker; helmet/plate optional)
    return {
        "front": "full",
        "rear": "ocr_only",
        "aux": "minimal",
    }.get(role, "full")


def get_gate_role(gate_id: str) -> str:
    """Public helper: trả role của 1 gate (front/rear/aux)."""
    return _resolve_role(gate_id)


def get_gate_profile(gate_id: str) -> str:
    """Public helper: trả profile của 1 gate (full/ocr_only/minimal)."""
    role = _resolve_role(gate_id)
    return _resolve_profile(gate_id, role)


# ─── Helmet model validation (Phase 3) ─────────────────────────────────────────
#
# HELMET_MODEL_HASH_SHA256 — sha256 của weights file đã qua QA. Nếu set và file
# hiện tại KHÔNG khớp → pipeline.start() log cảnh báo + ghi diagnostic, vẫn
# cho chạy (không refuse) để không chặn deployment. Mục đích: phát hiện sớm
# khi ai đó deploy bản weights chưa test (vd ghi đè weights cũ khi update).
# Compute hash: `certutil -hashfile models/helmet_best.pt SHA256` (Windows).
HELMET_MODEL_HASH_SHA256 = os.environ.get("HELMET_MODEL_HASH_SHA256", "").strip().lower()
HELMET_MODEL_MAPPING = os.environ.get("HELMET_MODEL_MAPPING",
                                      "0=With Helmet,1=Without Helmet")
# Mapping chuỗi "0=With Helmet,1=Without Helmet" → dict {0: "With Helmet", 1: "Without Helmet"}.
# Sai mapping hiển thị nhánh mũ lỗi (camera/plate vẫn chạy).

# Camera device credentials belong in the local .env, not source control.
def _camera_presets_from_env() -> list[dict]:
    import json
    presets = [
        {"label": "Webcam laptop", "source": "0"},
        {"label": "OBS Virtual Camera", "source": "1"},
    ]
    payload = os.environ.get("CAMERA_PRESETS_JSON", "").strip()
    if not payload:
        return presets
    try:
        extra = json.loads(payload)
    except json.JSONDecodeError:
        raise ValueError("CAMERA_PRESETS_JSON must be a JSON list of label/source objects") from None
    if not isinstance(extra, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("label"), str)
        or not isinstance(item.get("source"), str)
        for item in extra
    ):
        raise ValueError("CAMERA_PRESETS_JSON must be a JSON list of label/source objects")
    return presets + [{"label": item["label"], "source": item["source"]} for item in extra]


CAMERA_PRESETS = _camera_presets_from_env()


# Loop video when reading from file — kept for backwards compat (main gate only)
CAMERA_LOOP = _gate_cfgs["main"]["loop"]

# Model paths
HELMET_MODEL_PATH = os.environ.get("HELMET_MODEL_PATH") or str(BASE_DIR / "models" / "helmet_best.pt")
# plate_square_best.pt (Kaggle, chỉ biển vuông, 2026-10-04) đã đo trên 1447 khung
# video cổng thật: bỏ sót ~65 biển thật mà plate_best.pt bắt được, box riêng của
# nó chủ yếu là biển báo/đèn hậu — giữ plate_best.pt. Thử bằng env PLATE_MODEL_PATH.
PLATE_MODEL_PATH = os.environ.get("PLATE_MODEL_PATH") or str(BASE_DIR / "models" / "plate_best.pt")
# COCO weights ở gốc repo (gitignore). YOLO11n trên 120 khung hình cổng thật:
# bắt được 84 xe máy so với 73 của yolov8n (cùng số người), pose ra khớp
# xương 234/267 crop so với 228. Đổi lại bằng env PERSON_MODEL_PATH=yolov8n.pt.
PERSON_MODEL_PATH = os.environ.get('PERSON_MODEL_PATH', 'yolo11n.pt')
POSE_MODEL_PATH = os.environ.get('POSE_MODEL_PATH', 'yolo11n-pose.pt')

# ponytail: đã thử export ONNX + benchmark thật (scripts/export_onnx.py,
# scripts/benchmark_inference.py) — chậm hơn .pt trên CPU này (0.3x-1.0x), không
# phải giả thuyết đúng. KHÔNG dùng ONNX. Giữ 2 script lại làm tài liệu tham khảo
# nếu sau này đổi máy/CPU khác muốn đo lại.

# Detection thresholds
HELMET_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho helmet detection
# "Không đội mũ" là lời buộc tội: dưới ngưỡng này coi là chưa rõ. Duyệt tay 30
# phát hiện ở imgsz 640: các lần gán nhầm "không mũ" (mũ tối nhìn từ sau) đều
# có confidence 0.29–0.44, các lần "không mũ" đúng phần lớn >= 0.5.
HELMET_NO_HELMET_MIN_CONF = float(os.environ.get("HELMET_NO_HELMET_MIN_CONF", "0.5"))
PLATE_CONF_THRESHOLD = 0.25  # Ngưỡng confidence cho plate detection
PERSON_CONF_THRESHOLD = 0.4  # Ngưỡng confidence cho person detection (COCO)
# Xe máy/xe đạp CÓ NGƯỜI NGỒI bị che nửa nên COCO chỉ cho 0.2-0.4: ở ngưỡng 0.4
# của person, 270/472 khung đang ngồi xe (video cổng 04/10) không ghép được xe.
VEHICLE_CONF_THRESHOLD = float(os.environ.get("VEHICLE_CONF_THRESHOLD", "0.2"))
# Hạ từ 0.5 xuống 0.3 (2026-09-29) — người ở xa/bị che một phần trong crop nhỏ
# thường không đạt 0.5, khiến pose model bỏ qua hoàn toàn (không trả khớp nào),
# posture_status rơi về 'unknown'. Đánh đổi: dễ bắt khớp sai hơn khi ảnh mờ/nhiễu.
POSE_CONF_THRESHOLD = 0.3  # Ngưỡng confidence cho pose/khớp xương (YOLOv8-pose)

# classify_posture(): góc gối một mình không đáng tin (người đứng cạnh xe hơi
# chùng gối cũng ra "riding" giả, người ngồi xe duỗi thẳng chân chống đất lại
# ra "standing" giả). Khi có bike_bbox, kiểm tra thêm hip có nằm trên/gần vùng
# giữa xe không — normalize theo kích thước bike bbox vì camera treo chéo, góc
# nhìn đổi theo khoảng cách. Tune 2 số này khi test camera thật.
RIDING_HIP_X_TOLERANCE = 0.35  # hip lệch tâm xe theo X tối đa = 35% bề rộng xe
RIDING_HIP_Y_TOLERANCE = 0.75  # hip thấp hơn đỉnh xe tối đa = 75% chiều cao xe

# Giữ tên cũ để tương thích cấu hình; side-view scorer luôn coi keypoint
# chân thiếu là FEATURE_UNAVAILABLE, không dùng cờ này để suy ra dắt xe.
RIDING_NO_LEG_KEYPOINTS_MEANS_WALKING = False

# Bật để vẽ overlay debug (state + leg angle + hip dx/dy) lên video — dùng để
# soi số liệu thật trên camera thực tế rồi chỉnh 2 ngưỡng trên cho khớp.
DEBUG_RIDING = os.environ.get("DEBUG_RIDING", "0") == "1"
# Box xe hẹp hơn tỉ lệ này (rộng/cao) = xe nhìn chính diện/từ sau -> phân loại
# ngồi xe/dắt xe theo dạng chân hai bên xe + hông giữa xe (pose._frontal_riding).
# Video cổng 04/10: xe chính diện 0.52-0.94, tới 0.98 khi bị mép khung cắt;
# nhìn ngang thường > 1.2.
RIDING_FRONTAL_MAX_ASPECT = float(os.environ.get("RIDING_FRONTAL_MAX_ASPECT", "1.0"))

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
# FRAME_SKIP=1 → chạy AI trên MỌI frame (target 30 FPS khi camera capture 30 FPS).
# FRAME_SKIP=N → chỉ chạy AI trên mỗi N frame (giảm tải CPU/GPU ~Nx).
# Default 1 (2026-10-04): tăng từ 2 → 1 sau khi GPU lease sẵn + detect_ms p50
# ~52ms còn budget thời gian dư cho encode + I/O trên RTX 3050. Override qua
# env FRAME_SKIP=N nếu cần giảm tải (vd. máy yếu hoặc detect_ms > 80ms).
FRAME_SKIP = max(1, int(os.environ.get("FRAME_SKIP", "1")))
RECOGNITION_LOG_ENABLED = os.environ.get('RECOGNITION_LOG_ENABLED', '1') == '1'

# Database
DB_PATH = os.environ.get("APP_DB_PATH") or str(BASE_DIR / "data" / "app.db")

# Snapshots — QA isolation: respect SNAPSHOTS_DIR env var so QA / test runs
# don't pollute / copy the production media pool (R3.4 — prevents test
# backups from duplicating operational media + filling the disk).
SNAPSHOTS_DIR = os.environ.get("SNAPSHOTS_DIR") or str(BASE_DIR / "data" / "snapshots")

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

# Crop biển số: padding quanh bbox detector trước khi OCR — bbox detector hay
# sát ký tự, cắt thêm biên để không mất nét rìa.
PLATE_CROP_PAD_X = 0.10  # 10% bề rộng bbox
PLATE_CROP_PAD_Y = 0.12  # 12% chiều cao bbox
# Lề thêm quanh box biển trước khi cắt ảnh gốc cho OCR (BestPlateStore). Box
# detector ôm sát/hụt vài px làm mất ký tự mép: video camera sau 04/10 (biển
# 89-F1 237.92, 105 box) đọc đúng & chắc chắn 47 lần với lề 0, 95 lần với 0.15,
# 0 lần đọc sai ở mọi mức lề.
PLATE_BEST_CROP_PAD = float(os.environ.get("PLATE_BEST_CROP_PAD", "0.15"))

# Crop quá mờ thì bỏ qua, KHÔNG gửi OCR — đỡ tốn 1 lượt OCR vô ích và đỡ đưa
# text rác vào vote. Đo bằng variance of Laplacian (càng thấp càng mờ).
# Mặc định TẮT (0.0 = không chặn gì, mọi crop đều qua) vì không có số liệu
# camera thật để chọn ngưỡng an toàn — bật DEBUG_PLATE_OCR, xem cột "blur="
# trên vài phút chạy thật, rồi set số này cao hơn giá trị thấp nhất của
# những lần đọc ĐÚNG để lọc đúng crop mờ mà không chặn nhầm crop tốt.
PLATE_MIN_BLUR_SCORE = 0.0

# Bật để log mỗi kết quả OCR biển số (track, blur, raw/normalized, support,
# state) ra console — dùng để tune PLATE_MIN_BLUR_SCORE và các ngưỡng vote.
DEBUG_PLATE_OCR = os.environ.get("DEBUG_PLATE_OCR", "0") == "1"
DEBUG_PLATE_BEST_FRAME = os.environ.get("DEBUG_PLATE_BEST_FRAME", "0") == "1"
DEBUG_ALERT = os.environ.get("DEBUG_ALERT", "0") == "1"
PLATE_BEST_MIN_QUALITY = float(os.environ.get("PLATE_BEST_MIN_QUALITY", "0.65"))
PLATE_BEST_REPLACE_MARGIN = float(os.environ.get("PLATE_BEST_REPLACE_MARGIN", "0.05"))
PLATE_OCR_MIN_CONFIDENCE = float(os.environ.get("PLATE_OCR_MIN_CONFIDENCE", "0.70"))
MAX_PLATE_OCR_ATTEMPTS = 1
ALERT_MAX_PLATE_WAIT_MS = max(0, min(200, int(os.environ.get("ALERT_MAX_PLATE_WAIT_MS", "150"))))

# Phase 2 (Task 1) — multi-crop plate consensus. Top 3–5 crop từ frame
# KHÁC NHAU cùng đồng thuận trước khi kết luận biển. Bật/tắt qua env
# PLATE_CONSENSUS_ENABLED; mặc định BẬT (legacy BestPlateStore vẫn chạy song
# song để giữ fast-path trigger gần line). Consensus KHÔNG tự ý chuyển
# engine OCR — EasyOCR vẫn là reader chính; consensus chỉ vote.
PLATE_CONSENSUS_ENABLED = os.environ.get("PLATE_CONSENSUS_ENABLED", "1") == "1"
PLATE_CONSENSUS_MAX_CROPS = max(1, min(10, int(os.environ.get("PLATE_CONSENSUS_MAX_CROPS", "5"))))
PLATE_CONSENSUS_MIN_AGREE = max(1, min(5, int(os.environ.get("PLATE_CONSENSUS_MIN_AGREE", "2"))))
PLATE_CONSENSUS_MIN_CONFIDENCE = max(0.0, min(1.0,
    float(os.environ.get("PLATE_CONSENSUS_MIN_CONFIDENCE", "0.55"))))
PLATE_CONSENSUS_DIVERSITY_GAP = max(0, min(20,
    int(os.environ.get("PLATE_CONSENSUS_DIVERSITY_GAP", "2"))))
PLATE_CONSENSUS_TTL_SEC = max(1.0, float(os.environ.get("PLATE_CONSENSUS_TTL_SEC", "30.0")))
# F04 (Task 1): quality filter là điều kiện hợp lệ. Mặc định 0.1 — crop
# rỗng/lỗi/không đọc được thường có quality_score gần 0. Ngưỡng 0.1 loại
# các crop đó mà không ảnh hưởng mẫu hợp lệ (thường ≥ 0.4).
PLATE_CONSENSUS_MIN_QUALITY = max(0.0, min(1.0,
    float(os.environ.get("PLATE_CONSENSUS_MIN_QUALITY", "0.1"))))
# F04 (Task 1): chứng cớ cạnh tranh đáng tin. Một mẫu đơn lẻ có confidence
# ≥ 0.95 + quality đủ → KHÔNG cho winner confirmed, chuyển needs_review.
PLATE_CONSENSUS_CONTENDER_CONFIDENCE = max(0.0, min(1.0,
    float(os.environ.get("PLATE_CONSENSUS_CONTENDER_CONFIDENCE", "0.95"))))
PLATE_CONSENSUS_CONTENDER_MIN_QUALITY = max(0.0, min(1.0,
    float(os.environ.get("PLATE_CONSENSUS_CONTENDER_MIN_QUALITY", "0.3"))))

# Phase 3 (Task 1): 4-state posture temporal ledger. Trước đây posture đổi
# theo từng frame, dễ nhảy nhót. Giờ confirm một state chỉ khi có
# POSTURE_TEMPORAL_MIN_SAMPLES mẫu liên tiếp nhất quán trong
# POSTURE_TEMPORAL_WINDOW_SEC. Cửa sổ 1.5s × 4 mẫu = ~3Hz confirm tối thiểu.
POSTURE_TEMPORAL_WINDOW_SEC = max(0.5, float(os.environ.get("POSTURE_TEMPORAL_WINDOW_SEC", "1.5")))
POSTURE_TEMPORAL_MIN_SAMPLES = max(2, min(10,
    int(os.environ.get("POSTURE_TEMPORAL_MIN_SAMPLES", "4"))))
POSTURE_TEMPORAL_STATES = ('RIDING', 'PUSHING', 'WALKING', 'UNKNOWN')
# FR9B: mở rộng dải clamp rate TTS 1.0–1.6 (mặc định 1.45). Clamp cũ 0.9–1.4
# quá hẹp — người dùng muốn nghe nhanh hơn 1.4 trong khi vẫn không vỡ giọng.
TTS_SPEECH_RATE = max(1.0, min(1.6, float(os.environ.get("TTS_SPEECH_RATE", "1.45"))))
TTS_VOLUME = max(0., min(1., float(os.environ.get("TTS_VOLUME", "1.0"))))

# ─── Char-plate reader (FR5 — review-only) ─────────────────────────────────────
# When CHAR_PLATE_READER_REVIEW_ONLY=1, the pipeline runs the trained 36-class
# YOLOv8 character detector alongside EasyOCR on every crop. The character
# reader output is surfaced in RecognitionLogPanel for human confirmation; it
# MUST NOT be used to auto-assign plates to students. Default is off — runtime
# defaults stay on the validated EasyOCR path until a deployment-specific
# baseline proves the new reader on ≥100 confirmed real crops (per plan).
CHAR_PLATE_READER_REVIEW_ONLY = os.environ.get("CHAR_PLATE_READER_REVIEW_ONLY", "0") == "1"
CHAR_PLATE_READER_MIN_CONF = float(os.environ.get("CHAR_PLATE_READER_MIN_CONF", "0.25"))

# Biển xe máy VN 2 dòng gần như vuông (vd 89-F1 / 237.92); biển 1 dòng (ô tô,
# biển vàng...) dài hơn hẳn. crop có width/height dưới ngưỡng này -> coi là
# biển 2 dòng, OCR dòng trên/dưới RIÊNG thay vì để EasyOCR tự gộp cả crop
# (dễ lẫn 2 dòng thành 1 chuỗi sai thứ tự ký tự với biển mờ/nghiêng).
PLATE_TWO_LINE_MAX_ASPECT_RATIO = 2.0

# Crossing (vạch mốc) — xem app/cv/crossing.py. vehicle_anchor (bottom-center
# bbox xe) là điểm duy nhất dùng để xác định crossing.
CROSSING_EDGE_MARGIN = 0.02          # dead-zone quanh vạch (tỉ lệ chuẩn hóa)
CROSSING_MIN_FRAMES_PER_SIDE = 3     # phía TRƯỚC vạch cần ổn định bấy nhiêu frame mới xác nhận lần đầu
CROSSING_REARM_DISTANCE = 0.05       # xe phải rời vạch xa hơn mức này mới tính crossing LẦN MỚI
CROSSING_COOLDOWN_SEC = 2.0          # + đủ thời gian này mới rearm — chống anchor jitter tạo nhiều event
CROSSING_ALLOWED_DIRECTION = None    # None = tính cả 2 chiều; 'enter' hoặc 'exit' = chỉ tính chiều đó
# Phase 4 (Task 1): chốt lượt 3+3 — phía đích cũng cần MIN_FRAMES_PER_SIDE
# mẫu ổn định mới chốt crossing. Mặc định ON (3+3). Set 1 để legacy 3+1.
CROSSING_MIN_FRAMES_EXIT_SIDE = max(
    1, min(10, int(os.environ.get("CROSSING_MIN_FRAMES_EXIT_SIDE", "3")))
)
# Phase 4 (Task 1): cửa sổ thời gian tối đa giữa frame đầu tiên và frame cuối
# của transition (entry→exit). Nếu vượt quá → reset stable_side, không chốt.
# Trước đây không có → 17 giây giãn cách vẫn nhận crossing (lỗi nghiêm trọng).
CROSSING_MAX_TRANSITION_SEC = max(
    0.5, float(os.environ.get("CROSSING_MAX_TRANSITION_SEC", "5.0"))
)

# Bật để vẽ overlay debug lên video: bbox xe, vehicle_track_id, chấm tại
# vehicle_anchor, side hiện tại, khoảng cách tới vạch, crossing state — dùng
# để biết nên đặt vạch ở đâu trên camera thật.
DEBUG_CROSSING = os.environ.get("DEBUG_CROSSING", "0") == "1"

# Priority 1 (Event Engine): ngưỡng streak + window + grace. Match docs:
#   "≥5 frame liên tiếp cùng label vi phạm trong cửa sổ 2s mới COMMIT"
# Có thể override qua env để test/benchmark nhanh. Default lặp lại giá trị
# trong app/cv/event_manager.py (5, 2.0, 2.0) — giữ chuỗi ở đây là int/float
# để tránh circular import config ↔ event_manager.
EVENT_STREAK_MIN_FRAMES = int(os.environ.get("EVENT_STREAK_MIN_FRAMES", "5"))
EVENT_WINDOW_SEC = float(os.environ.get("EVENT_WINDOW_SEC", "2.0"))
EVENT_GRACE_PERIOD_SEC = float(os.environ.get("EVENT_GRACE_PERIOD_SEC", "2.0"))

# Đợt E1.1 (bằng chứng per-error-type) — xem app/cv/evidence.py
#   ≥4 mẫu đồng thuận / 80% / 1.5s window / 400ms span / 100ms interval
# Có thể override qua env để test/benchmark nhanh.
EVIDENCE_MIN_SAMPLES = int(os.environ.get("EVIDENCE_MIN_SAMPLES", "4"))
EVIDENCE_WINDOW_SEC = float(os.environ.get("EVIDENCE_WINDOW_SEC", "1.5"))
EVIDENCE_MIN_AGREEMENT = float(os.environ.get("EVIDENCE_MIN_AGREEMENT", "0.80"))
EVIDENCE_MIN_SPAN_SEC = float(os.environ.get("EVIDENCE_MIN_SPAN_SEC", "0.40"))
EVIDENCE_MIN_INTERVAL_SEC = float(os.environ.get("EVIDENCE_MIN_INTERVAL_SEC", "0.10"))
EVIDENCE_GRACE_PERIOD_SEC = float(os.environ.get("EVIDENCE_GRACE_PERIOD_SEC", "5.0"))

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

# ─── JWT Authentication ──────────────────────────────────────────────────────────
#
# JWT_SECRET_KEY bắt buộc phải đặt trong .env (không hardcode trong mã nguồn).
# Sinh secret mới: python -c "import secrets; print(secrets.token_hex(32))"
# Nếu không đặt, dev server vẫn chạy được nhưng sẽ cảnh báo mỗi lần khởi động.
# Production: coi JWT_SECRET_KEY chưa đặt là lỗi nghiêm trọng và KHÔNG khởi động.
import secrets as _secrets

_raw_jwt_secret = os.environ.get("JWT_SECRET_KEY", "")
_PRODUCTION = os.environ.get("ENVIRONMENT", "development") == "production"

if _raw_jwt_secret:
    JWT_SECRET_KEY = _raw_jwt_secret
elif _PRODUCTION:
    raise RuntimeError(
        "JWT_SECRET_KEY must be set in environment variables on production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
else:
    # Dev mode: one ephemeral key per process; never print it to logs.
    _generated = _secrets.token_hex(32)
    print(f"[WARNING] JWT_SECRET_KEY not set — using ephemeral key for THIS process only.")
    print(f"[WARNING] Login sessions will be lost on server restart. Set JWT_SECRET_KEY in .env:")
    JWT_SECRET_KEY = _generated

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12

# ─── Cookie session (D6.1) ─────────────────────────────────────────────────────
#
# Backend trả cookie HttpOnly cho frontend SPA. Bearer token vẫn hoạt động
# cho script hiện có trong giai đoạn chuyển tiếp.
# Secure=True chỉ bật khi ENVIRONMENT=production (yêu cầu HTTPS).
COOKIE_NAME = "gate_session"
COOKIE_SECURE = _PRODUCTION
COOKIE_SAMESITE = "lax" if _PRODUCTION else "lax"  # "strict" sau khi xác nhận cross-subdomain không cần

# ─── T2.5 — public register toggle (mặc định TẮT cho dữ liệu thật) ─────────
# Bật qua env PUBLIC_REGISTER_ENABLED=1 khi dev/demo với roster giả.
# Khi tắt, /api/register/lookup, /upload-photo, / (POST) đều trả 503 +
# {detail, enabled: false}; trang FE /register hiển thị "đang tạm đóng".
PUBLIC_REGISTER_ENABLED = os.environ.get("PUBLIC_REGISTER_ENABLED", "0") == "1"

# T2.6 — offset (giờ) cho múi giờ nghiệp vụ (Asia/Bangkok = UTC+7).
# Lưu timestamp UTC, lọc ngày theo múi giờ này. Đổi qua env STATS_TZ_OFFSET_HOURS
# nếu triển khai ở múi khác; KHÔNG đoán từ system localtime.
STATS_TZ_OFFSET_HOURS = int(os.environ.get("STATS_TZ_OFFSET_HOURS", "7"))
STATS_TZ_OFFSET_MINUTES = STATS_TZ_OFFSET_HOURS * 60

# CSV import size limits — dùng để giới hạn admin CSV upload.
CSV_IMPORT_MAX_BYTES = int(os.environ.get("CSV_IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
CSV_IMPORT_MAX_ROWS = int(os.environ.get("CSV_IMPORT_MAX_ROWS", "10000"))
