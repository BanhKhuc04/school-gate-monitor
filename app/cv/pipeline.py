"""
Pipeline xử lý video trong thread nền.

Luồng: đọc frame → detect helmet → detect plate → OCR → tra DB → ghi log vi phạm → vẽ box → lưu frame.
Có thêm queue cho cảnh báo vi phạm (Bước 4) và ghi log vi phạm vào DB (Bước 6).
"""
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, Future
import time
import queue
import datetime
import os
import uuid
import json
import hashlib
import cv2
import numpy as np
from typing import Optional

from app.config import (
    GATES, HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, HELMET_NO_HELMET_MIN_CONF, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
    FRAME_SKIP, VIDEO_WIDTH, VIDEO_HEIGHT, DETECT_WIDTH, DETECT_HEIGHT, RECOGNITION_LOG_ENABLED,
    ALERT_COOLDOWN, VIOLATION_COOLDOWN, SNAPSHOTS_DIR, MAX_RIDERS_PER_MOTORCYCLE,
    VIOLATION_CLIP_SECONDS, VIOLATION_CLIP_FPS,
    PLATE_VOTE_WINDOW_SEC, PLATE_VOTE_MIN_AGREE, PLATE_MIN_CONFIDENCE_SINGLE,
    PLATE_CROP_PAD_X, PLATE_CROP_PAD_Y, PLATE_MIN_BLUR_SCORE, DEBUG_PLATE_OCR,
    CROSSING_EDGE_MARGIN, CROSSING_MIN_FRAMES_PER_SIDE, CROSSING_REARM_DISTANCE,
    CROSSING_COOLDOWN_SEC, CROSSING_ALLOWED_DIRECTION, DEBUG_CROSSING,
    CROSSING_MIN_FRAMES_EXIT_SIDE, CROSSING_MAX_TRANSITION_SEC,
    CORRELATION_TIME_WINDOW_SEC, CORRELATION_MIN_SIMILARITY,
    CONTINUOUS_RECORDING_ENABLED, CONTINUOUS_RECORDING_SEGMENT_MINUTES,
    CONTINUOUS_RECORDING_FPS, CONTINUOUS_RECORDING_WIDTH, CONTINUOUS_RECORDING_HEIGHT,
    CONTINUOUS_RECORDING_DIR, FRAME_EDGE_MARGIN_RATIO,
    HELMET_MODEL_HASH_SHA256, HELMET_MODEL_MAPPING,
    get_gate_role, get_gate_profile,
    DEBUG_ALERT,
)
from app.cv.capture import WebcamStream, LatestFrameCapture
from app.cv.detector import HelmetPlateDetector, Detection
from pathlib import Path  # noqa: E402, used in hot-reload methods
from app.cv.ocr import read_plate_detailed, validate_plate_format, compute_blur_score
from app.cv.plate_voter import PlateVoter
from app.cv.event_correlator import find_correlation_candidate
from app.cv.roi import to_pixel_polygon, filter_by_roi
from app.cv.pipeline_metrics import (
    MetricsBuffer,
    PipelineMetrics as _PipelineMetrics,
    ResourceSampler,
)
from app.db import (
    get_vehicle_by_plate, add_violation_event, find_correlation_candidates,
    link_violation_events, mark_correlation_unmatched, get_connection,
    get_gate_roi, set_gate_roi, get_gate_camera_source, set_gate_camera_source, get_gate_line,
)


# Màu vẽ bounding box
COLOR_HELMET = (0, 255, 0)      # Xanh lá - có mũ
COLOR_NO_HELMET = (0, 0, 255)   # Đỏ - không mũ
COLOR_PLATE = (255, 255, 0)     # Cyan - biển số
COLOR_PERSON = (255, 128, 0)    # Cam - người (COCO)
THICKNESS = 2
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Vạch mốc mặc định (ngang giữa khung hình) dùng cho cảnh báo loa SỚM khi
# admin chưa tự vẽ gate_line riêng — chỉ dùng cho tín hiệu nhắc nhở tức thời,
# KHÔNG dùng cho quyết định vi phạm RIDING_THROUGH_GATE chính thức.
# Camera nhìn xe tiến lại: mặt đường chiếm nửa dưới khung hình, nên vạch mặc
# định đặt giữa vùng mặt đường (y=0.5 trùng mép xa của sân demo, xe không bao
# giờ cắt qua). Admin vẫn vẽ lại vạch thật ở trang ROI.
_DEFAULT_GATE_LINE = (0.0, 0.65, 1.0, 0.65)


def _sha256_file(path: str, chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Compute SHA256 hex digest of a file. Returns None nếu file không tồn tại
    hoặc không đọc được. Phase 3 (Task 1): dùng cho helmet weights hash check."""
    if not path:
        return None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                h.update(chunk)
        return h.hexdigest().lower()
    except (OSError, IOError):
        return None


def _ocr_task(crop: np.ndarray, track_id: int, frame_seq: int, source_epoch: int = 0):
    """B2 OCR task chạy trong worker thread. Nhận crop đã cắt (bản sao), trả
    dict kết quả + metadata source_epoch/frame_seq/track_id. Lỗi engine →
    trả dict có key 'error' để R4 phân biệt lỗi kỹ thuật vs rỗng tự nhiên."""
    from app.cv.ocr import read_plate_detailed
    base = {'source_epoch': source_epoch, 'frame_seq': frame_seq,
            'track_id': track_id}
    try:
        result = read_plate_detailed(crop)
    except Exception as exc:
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0,
                **base, 'completed_monotonic': time.monotonic(),
                'error': f'ocr_engine_error:{type(exc).__name__}'}
    if not isinstance(result, dict):
        return {'full': '', 'top_line': '', 'bottom_line': '', 'confidence': 0.0,
                **base, 'completed_monotonic': time.monotonic(), 'error': 'ocr_invalid_return'}
    result.setdefault('source_epoch', source_epoch)
    result.setdefault('frame_seq', frame_seq)
    result.setdefault('track_id', track_id)
    result['completed_monotonic'] = time.monotonic()
    return result


class VideoPipeline:
    """
    Thread nền xử lý webcam + YOLO detection + vẽ box cho MỘT gate.

    Frame đã xử lý được lưu vào biến dùng chung, có Lock bảo vệ.
    Có queue cho cảnh báo vi phạm qua WebSocket.
    """

    def __init__(self, gate_id: str, gate_config: dict):
        self.gate_id = gate_id
        self.gate_name = gate_config.get("name", gate_id)
        # Phase 3 (Task 1) — runtime camera/role mapping. Each gate gets:
        #   - role: front (full AI), rear (OCR-only), aux (minimal)
        #   - profile: full, ocr_only, minimal — decides which models to load.
        # Front cameras watch riders (person + helmet + pose + plate).
        # Rear cameras watch license plates (plate detector + tracker only).
        self.role = get_gate_role(gate_id)
        self.profile = get_gate_profile(gate_id)
        self._camera_role_health: dict = {
            'role': self.role,
            'profile': self.profile,
            'expected_models': {
                'helmet': self.profile == 'full',
                'plate': self.profile in ('full', 'ocr_only'),
                'person': self.profile == 'full',
                'pose': self.profile == 'full',
            },
        }

        # Đợt 1 (System Stability): mỗi gate có thể có nhiều camera. Mặc
        # định camera_id = gate_id (hành vi cũ — 1 camera = 1 gate) để
        # bản ghi cũ vẫn hợp lệ. Khi có cấu hình camera cụ thể (qua
        # `upsert_camera()`), set self.camera_id = row.camera_id tương
        # ứng với role front.
        self.camera_id: str = gate_config.get("camera_id", gate_id)
        self._encounter_session_id = uuid.uuid4().hex
        # Phase 5 (Task 1): GateEventMatcher — ghép 2 camera cùng cổng vật
        # lý vào 1 encounter chia sẻ. Auto-match mặc định TẮT cho đến khi
        # có calibration + cặp lượt có nhãn (GATE_MATCHER_ENABLED=1 env).
        from app.cv.gate_event_matcher import GateEventMatcher
        self._gate_matcher = GateEventMatcher()
        # Phase 6 (Task 1): GPU profiler — sample VRAM mỗi 1s, rolling
        # 600 samples (10 phút lịch sử). Cung cấp percentile cho UI.
        from app.cv.gpu_profiler import GpuMemoryProfiler
        self._gpu_profiler = GpuMemoryProfiler(maxlen=600)
        from app.cv.recognition_log import RecognitionLog
        self._recognition_log = RecognitionLog(gate_id, self.camera_id)
        from app.cv.recognition_cards import RecognitionCards
        self._recognition_cards = RecognitionCards(gate_id, self.camera_id)
        self._recognition_results = {}
        self._recognition_logging_enabled = RECOGNITION_LOG_ENABLED
        self._persist_pending = {}
        self._io_health = {"errors": 0, "clip_errors": 0}
        self._event_versions = {}
        # Source epoch của camera hiện tại. Đổi nguồn thành công → tăng.
        self._source_epoch: int = 0

        # Lock bảo vệ frame
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None

        # Queue cho cảnh báo vi phạm
        # One per-gate distributor consumes this. Saved history is in SQLite;
        # absent viewers must not grow memory or block evidence IO.
        self._alert_queue: queue.Queue = queue.Queue(maxsize=256)

        # Trạng thái
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Khởi tạo webcam
        self._webcam: Optional[WebcamStream] = None

        # Khởi tạo detectors
        print(f"[Pipeline] Loading helmet model (profile={self.profile})...")
        from app.cv.helmet_contract import validate_helmet_classes
        self._helmet_detector = None
        # Phase 3 (Task 1): profile 'ocr_only' (rear camera) → skip helmet
        # model hoàn toàn để tiết kiệm GPU/RAM; nó không có ý nghĩa ở camera
        # sau (không nhìn thấy đầu người từ góc sau). Lưu ý: profile 'minimal'
        # cũng bỏ qua (aux cameras không cần helmet).
        if self.profile != 'full':
            self._helmet_health = {'status': 'disabled', 'reason': 'profile_not_full',
                                   'profile': self.profile}
            print(f"[Pipeline] Helmet model skipped: profile={self.profile} (no helmet detection needed)")
        else:
            self._helmet_health = {'status': 'error', 'reason': 'helmet_model_unavailable'}
            try:
                candidate = HelmetPlateDetector(HELMET_MODEL_PATH, conf_threshold=HELMET_CONF_THRESHOLD)
                names = candidate.class_names
                # Phase 3 (Task 1): mapping check — nếu env HELMET_MODEL_MAPPING set
                # và mapping không khớp thứ tự class thực tế của weights → từ chối
                # detector (sai mapping = "Without Helmet" bị gán thành "With Helmet"
                # là nguy hiểm nhất — sai detection). pipeline KHÔNG tự suy mapping
                # từ tên class vì dataset khác nhau có thể đảo thứ tự.
                from app.cv.helmet_contract import validate_helmet_mapping
                expected_mapping = HELMET_MODEL_MAPPING
                if not validate_helmet_mapping(names, expected_mapping):
                    self._helmet_health = {'status': 'error', 'reason': 'helmet_model_wrong_mapping',
                                           'expected': expected_mapping, 'actual': list(names)}
                    print(f'[Pipeline] Helmet model disabled: mapping mismatch (expected={expected_mapping}, got={list(names)})')
                elif validate_helmet_classes(names):
                    self._helmet_detector = candidate
                    self._helmet_health = {'status': 'ready', 'classes': names}
                    # Phase 3: SHA256 hash check (optional via env). Phát hiện sớm
                    # nếu weights bị overwrite bằng bản chưa test. Log warning thay
                    # vì refuse để không chặn production.
                    if HELMET_MODEL_HASH_SHA256:
                        actual_hash = _sha256_file(HELMET_MODEL_PATH)
                        if actual_hash and actual_hash != HELMET_MODEL_HASH_SHA256:
                            self._helmet_health['hash_mismatch'] = True
                            self._helmet_health['hash_expected'] = HELMET_MODEL_HASH_SHA256
                            self._helmet_health['hash_actual'] = actual_hash
                            print(f'[Pipeline] WARNING helmet weights hash mismatch '
                                  f'(expected {HELMET_MODEL_HASH_SHA256[:12]}..., '
                                  f'got {actual_hash[:12]}...). Detector vẫn chạy.')
                else:
                    self._helmet_health = {'status': 'error', 'reason': 'helmet_model_wrong_classes'}
                    print('[Pipeline] Helmet model disabled: incompatible classes')
            except Exception as exc:
                self._helmet_health['error_type'] = type(exc).__name__
                print(f'[Pipeline] Helmet model unavailable: {type(exc).__name__}')

        # Phase 3 (Task 1): profile 'minimal' → skip plate detector (aux
        # cameras chỉ cần tracker, không OCR).
        print(f"[Pipeline] Loading plate model (profile={self.profile})...")
        self._plate_detector = None
        if self.profile == 'minimal':
            print(f"[Pipeline] Plate model skipped: profile={self.profile} (aux camera)")
        else:
            self._plate_detector = HelmetPlateDetector(
                PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD
            )
            print("[Pipeline] Plate model loaded:", self._plate_detector.class_names)

        print(f"[Pipeline] Loading person model (COCO, profile={self.profile})...")
        self._person_detector = None
        if self.profile != 'full':
            print(f"[Pipeline] Person model skipped: profile={self.profile} (no person detection)")
        else:
            self._person_detector = HelmetPlateDetector(
                PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD
            )
            print("[Pipeline] Person model loaded:", self._person_detector.class_names)

        # Chạy 3 model (person/helmet/plate) song song trên frame — đo thật:
        # 304ms -> 172ms/frame (1.77x), vì PyTorch nhả GIL lúc tính toán nặng nên
        # 3 luồng CPU chạy được cùng lúc. Tạo 1 lần, dùng lại mỗi frame.
        # Phase 3 (Task 1): pool size khớp với profile để tránh thread ngồi không
        # tiêu RAM (rear/aux thường chỉ 1-2 model).
        if self.profile == 'full':
            _detect_workers = 3
        elif self.profile == 'ocr_only':
            _detect_workers = 1  # chỉ plate detector
        else:  # minimal / aux
            _detect_workers = 0  # không có detector, không cần pool
        self._detect_pool = ThreadPoolExecutor(
            max_workers=_detect_workers,
            thread_name_prefix=f"detect-{gate_id}",
        ) if _detect_workers > 0 else None

        # Pool riêng cho việc lưu snapshot (cv2.imwrite) + ghi log vi phạm vào DB —
        # 2 việc này là I/O (đĩa + sqlite), không cần chờ xong mới đọc frame tiếp
        # theo. Tách khỏi _detect_pool để không tranh chỗ với việc detect model.
        self._io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"io-{gate_id}")
        self._clip_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"clip-{gate_id}")
        self._clip_jobs = []

        # B2: OCR worker — chạy EasyOCR trong thread riêng để không block capture.
        # Đợt R: mỗi track chỉ có tối đa 1 pending OCR job; future cũ đang chạy
        # KHÔNG cancel() (cancel không dừng task đã chạy) — kết quả sẽ bị lọc
        # theo `source_epoch` ở consume-time.
        self._ocr_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"ocr-{gate_id}")
        self._ocr_pending: dict[int, Future] = {}
        self._ocr_submit_meta: dict[int, dict] = {}
        self._ocr_max_pending: int = 8
        from app.cv.best_plate import BestPlateStore
        from app.cv.plate_consensus import PlateConsensusStore
        from app.config import (
            PLATE_BEST_REPLACE_MARGIN, PLATE_OCR_MIN_CONFIDENCE,
            PLATE_CONSENSUS_MIN_AGREE, PLATE_CONSENSUS_MIN_CONFIDENCE,
            PLATE_CONSENSUS_MAX_CROPS, PLATE_CONSENSUS_DIVERSITY_GAP,
            PLATE_CONSENSUS_TTL_SEC,
            POSTURE_TEMPORAL_WINDOW_SEC, POSTURE_TEMPORAL_MIN_SAMPLES,
            POSTURE_TEMPORAL_STATES,
        )
        self._best_plates = BestPlateStore(PLATE_BEST_REPLACE_MARGIN, PLATE_OCR_MIN_CONFIDENCE, max_attempts=5)
        # Phase 2: top-N multi-crop consensus — keeps top 3–5 crop từ
        # frame KHÁC NHAU, vote ≥2 đồng thuận. Bổ sung cho BestPlateStore
        # (vẫn giữ 1 crop tốt nhất cho fast-path trigger gần line).
        from app.config import (
            PLATE_CONSENSUS_MIN_QUALITY, PLATE_CONSENSUS_CONTENDER_CONFIDENCE,
            PLATE_CONSENSUS_CONTENDER_MIN_QUALITY,
        )
        self._plate_consensus = PlateConsensusStore(
            max_crops_per_track=PLATE_CONSENSUS_MAX_CROPS,
            consensus_min_agree=PLATE_CONSENSUS_MIN_AGREE,
            min_confidence=PLATE_CONSENSUS_MIN_CONFIDENCE,
            diversity_min_frame_gap=PLATE_CONSENSUS_DIVERSITY_GAP,
            ttl_sec=PLATE_CONSENSUS_TTL_SEC,
            # F04 (Task 1): quality filter + chứng cớ cạnh tranh đáng tin
            min_quality=PLATE_CONSENSUS_MIN_QUALITY,
            contender_confidence=PLATE_CONSENSUS_CONTENDER_CONFIDENCE,
            contender_min_quality=PLATE_CONSENSUS_CONTENDER_MIN_QUALITY,
        )
        self._plate_approach = {}
        self._crossing_jobs = {}
        self._crossing_sealed = {}
        self._plate_last_crossing = {}
        self._last_sealed_crossing = {}
        # Phase 4 (Task 1): map eid → DB row id để late issues có thể
        # UPDATE vào cùng event qua update_violation_issues(). Trước đây
        # evidence đến trễ bị bỏ — chốt lượt xong là SEAL cứng, mũ đủ mẫu
        # 100ms sau crossing đã không được vào event.
        self._crossing_event_to_db_id: dict[str, int] = {}
        self._crossing_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'crossing-{gate_id}')
        self._ocr_health: dict = {
            "errors": 0, "empty": 0, "submitted": 0, "completed": 0,
            "stale_dropped": 0, "sync_fallbacks": 0, "duplicate_dropped": 0,
            "blur_skipped": 0, "confirmed_skipped": 0,
        }

        # B2: JPEG cache theo frame_seq — encode 1 lần, chia sẻ cho mọi viewer.
        self._jpeg_cache: dict[int, tuple[bytes, float]] = {}
        self._jpeg_max_size: int = 30
        self._frame_seq: int = 0
        with self._lock:
            self._latest_jpeg: Optional[bytes] = None

        # Đợt R1: source_epoch tăng khi đổi camera thành công. Mỗi OCR submit
        # mang theo epoch; khi collect kiểm tra epoch còn khớp epoch hiện tại
        # không — nếu không thì kết quả đến trễ của phiên cũ bị loại.
        self._source_epoch: int = 0

        # Đợt R1: CameraSwitch wrapper (lazy import — module có thể chưa sẵn
        # trong test).
        try:
            from app.cv.camera_switch import CameraSwitch
            self.camera_switch = CameraSwitch(gate_config.get("source"))
        except Exception:
            self.camera_switch = None
        self._active_source = gate_config.get("source")

        # Đợt R: các state tracking theo track_id/giờ — reset khi đổi nguồn.
        self._prev_track_bbox: dict[int, tuple] = {}
        self._fast_track_active: bool = False
        self._fast_movement_px: int = 80
        self._track_vehicle_history: dict[int, list] = {}
        self._vehicle_vote_window_sec: float = 2.5
        self._vehicle_vote_min_samples: int = 3

        # EventManager + PlateVoter khởi tạo sẵn (có thể reset khi đổi nguồn).
        try:
            from app.cv.event_manager import EventManager
            from app.config import (EVENT_STREAK_MIN_FRAMES, EVENT_WINDOW_SEC,
                                     EVENT_GRACE_PERIOD_SEC)
            self._event_manager = EventManager(
                streak_min_frames=EVENT_STREAK_MIN_FRAMES,
                window_sec=EVENT_WINDOW_SEC,
                grace_period_sec=EVENT_GRACE_PERIOD_SEC,
            )
        except Exception:
            self._event_manager = None

        # Đợt E1.1: bộ bằng chứng RIÊNG từng loại lỗi (per-track, per-error_type)
        # với ngưỡng 4 mẫu / 80% agreement / 1.5s window / 400ms span / 100ms interval.
        try:
            from app.cv.evidence import EvidenceLedger
            from app.config import (EVIDENCE_MIN_SAMPLES, EVIDENCE_WINDOW_SEC,
                                     EVIDENCE_MIN_AGREEMENT, EVIDENCE_MIN_SPAN_SEC,
                                     EVIDENCE_MIN_INTERVAL_SEC,
                                     EVIDENCE_GRACE_PERIOD_SEC)
            self._evidence_ledger = EvidenceLedger(
                min_samples=EVIDENCE_MIN_SAMPLES,
                window_sec=EVIDENCE_WINDOW_SEC,
                min_agreement=EVIDENCE_MIN_AGREEMENT,
                min_span_sec=EVIDENCE_MIN_SPAN_SEC,
                min_sample_interval_sec=EVIDENCE_MIN_INTERVAL_SEC,
                grace_period_sec=EVIDENCE_GRACE_PERIOD_SEC,
            )
        except Exception:
            self._evidence_ledger = None

        # Frame counter cho FRAME_SKIP
        self._frame_count = 0

        # Cache kết quả detect để vẽ box mượt giữa các lần detect thật
        self._last_person_dets: list = []
        self._last_helmet_dets: list = []
        self._last_plate_dets: list = []

        # Cooldown cho cảnh báo WebSocket
        self._last_alert_time: float = 0.0

        # Cooldown cho ghi log vi phạm vào DB: {(plate_type, violation_type): last_time}
        self._last_log_time: dict = {}

        # Vote biển số qua nhiều lần đọc gần nhau (vị trí + thời gian) — thay cho
        # cache 1-giá-trị cũ. EasyOCR CPU tốn 300-800ms/lần nên vẫn cache theo vị
        # trí như trước, nhưng giờ giữ nhiều mẫu để tính confidence + biết khi nào
        # KHÔNG chắc chắn (đọc lệch nhau liên tục) thay vì tin tuyệt đối 1 lần đọc.
        self._plate_voter = PlateVoter(
            grid_px=60,
            window_sec=PLATE_VOTE_WINDOW_SEC,
            min_agree=PLATE_VOTE_MIN_AGREE,
            min_confidence_single=PLATE_MIN_CONFIDENCE_SINGLE,
        )

        # Timestamps for health monitoring
        self._start_time: float = time.time()
        self._last_frame_time: float = self._start_time
        self._last_detection_time: float = self._start_time

        # Feature 7: FPS / latency / plate read success rate tracking
        from collections import deque
        self._frame_timestamps = deque(maxlen=30)      # sliding window for FPS
        self._last_process_latency_ms = 0.0
        self._plate_attempts = 0
        self._plate_successes = 0

        # Đếm người đi bộ / người đi xe — cộng dồn từ lúc pipeline start, dùng để
        # quan sát tỉ lệ khớp person↔vehicle qua thời gian (không có cách nào biết
        # được ngoài xem video thủ công trước đây). Đếm theo LƯỢT xuất hiện mỗi
        # frame, không phải người duy nhất (1 người ở lại nhiều frame bị đếm nhiều
        # lần) — chỉ mang tính tương đối để phát hiện bất thường, không phải số liệu
        # chính xác tuyệt đối.
        self._pedestrian_count = 0
        self._rider_count = 0

        # Phase 3 (Task 1): 4-state posture temporal ledger (RIDING, PUSHING,
        # WALKING, UNKNOWN). Trước đây posture_status thay đổi theo từng frame,
        # dễ nhảy nhót. Giờ tích lũy samples trong cửa sổ thời gian
        # (`POSTURE_TEMPORAL_WINDOW_SEC`, mặc định 1.5s), chỉ xác nhận khi
        # đủ `POSTURE_TEMPORAL_MIN_SAMPLES` (mặc định 4) mẫu nhất quán.
        self._posture_window: deque = deque(
            maxlen=int(POSTURE_TEMPORAL_WINDOW_SEC * 30)
        )  # ~30fps, đủ dài cho 1.5s
        self._posture_confirmed = 'UNKNOWN'
        self._posture_confidence = 0.0

        # N05 (Post-Video Review): per-track posture ledger. Cùng dữ liệu
        # contract với _posture_window nhưng tách theo track_id — 2 xe không
        # chia mẫu. Ledger mới là nguồn quyết định riding cho từng lượt xe;
        # `_posture_window` (cũ) giữ cho health/summary, KHÔNG quyết định
        # violation từng track.
        from app.cv.posture_track_ledger import PostureTrackLedger
        self._posture_track_ledger = PostureTrackLedger(
            window_sec=POSTURE_TEMPORAL_WINDOW_SEC,
            min_samples=POSTURE_TEMPORAL_MIN_SAMPLES,
            agreement_ratio=0.80,
            min_span_sec=0.4,
            min_interval_sec=0.1,
        )

        # Feature 4: ring buffer for violation video clips
        self._clip_buffer: deque = deque(maxlen=VIOLATION_CLIP_SECONDS * VIOLATION_CLIP_FPS)

        # Cache khớp xương (pose keypoints) của lần detect gần nhất — dùng để vẽ lại
        # ở nhánh frame bị SKIP (giống _last_helmet_dets/_last_plate_dets/_last_person_dets).
        # Thiếu cache này trước đây làm khớp xương CHỚP TẮT theo đúng chu kỳ FRAME_SKIP
        # (chỉ vẽ ở frame có detect thật, biến mất ở frame skip) — bug phát hiện qua
        # quan sát video thật.
        self._last_pose_data: list[tuple[list, tuple]] = []

        # Vùng nhận diện (ROI) — polygon tỉ lệ % lưu trong DB, tính sẵn sang
        # pixel 1 lần ở đây. None = không giới hạn vùng (mặc định, không đổi
        # hành vi cũ). set_roi() cập nhật sống khi admin lưu vùng mới, không
        # cần restart pipeline.
        self._crossing_detector = self._make_crossing_detector(get_gate_line(gate_id))
        self._roi_points = get_gate_roi(gate_id)
        self._roi_polygon_px = to_pixel_polygon(self._roi_points, VIDEO_WIDTH, VIDEO_HEIGHT)

        # Cảnh báo loa SỚM ngay khi xe cán qua vạch — thay vì đợi evidence
        # ledger gom đủ N frame nhận diện mũ/biển rồi mới phát (gây delay
        # nghe rõ). Khi admin ĐÃ cấu hình gate_line, tái dùng kết quả
        # _crossing_detector sẵn có (free). Khi CHƯA cấu hình (đa số gate),
        # dùng _midline_track_state — so sánh tâm Y nhẹ, KHÔNG dùng thêm 1
        # CrossingDetector đầy đủ (từng gây tụt FPS do cấp phát list/dict mỗi
        # frame cho mọi xe — xem _check_default_midline_crossing).
        self._midline_track_state: dict = {}
        self._instant_alerted_tracks: set = set()

        # Đợt 2, Bước 7: continuous recorder — None nếu TẮT (mặc định).
        # Đặt SAU clip_buffer để 2 cơ chế ghi hình độc lập nhau không xung đột.
        self._recorder = None
        if CONTINUOUS_RECORDING_ENABLED:
            from app.cv.recorder import ContinuousRecorder
            self._recorder = ContinuousRecorder(
                gate_id=self.gate_id,
                segment_minutes=CONTINUOUS_RECORDING_SEGMENT_MINUTES,
                fps=CONTINUOUS_RECORDING_FPS,
                width=CONTINUOUS_RECORDING_WIDTH,
                height=CONTINUOUS_RECORDING_HEIGHT,
                output_dir=CONTINUOUS_RECORDING_DIR,
            )

        # ── Phase 0 (Task 1): bounded metrics buffers + resource sampler ──
        # Trước Phase 0 chỉ có 1 deque chung (`_frame_timestamps`) + 1 float
        # `_last_process_latency_ms`. Phase 0 thay bằng:
        #   - 6 MetricsBuffer (capture / detect / ocr_wait / encode /
        #     persistence / dispatch) — mỗi buffer bounded 60 mẫu;
        #   - ResourceSampler (RSS qua psutil + VRAM quy torch) chạy nền theo
        #     interval (mặc định 1s) — không gọi nvidia-smi mỗi frame;
        #   - Counter rõ ràng (jpeg_new, jpeg_repeat, frames_dropped_stale,
        #     frames_dropped_encode, ocr_submitted_total, ...).
        # Phục vụ get_status() (cho /api/system/health) và debug latency qua
        # log khi benchmark.
        self._metrics_capture = MetricsBuffer()
        self._metrics_detect = MetricsBuffer()
        self._metrics_ocr_wait = MetricsBuffer()
        self._metrics_encode = MetricsBuffer()
        self._metrics_persistence = MetricsBuffer()
        self._metrics_dispatch = MetricsBuffer()
        self._resource_sampler = ResourceSampler()
        # Capture FPS = số frame mới đọc về/giây (ĐẾM frame_seq tăng).
        # Khác với AI FPS = số frame ĐÃ QUA detect/giây.
        self._capture_frame_seq_last: int = 0
        self._capture_fps_value: float = 0.0
        self._ai_fps_value: float = 0.0
        self._fps_compute_at: float = time.monotonic()
        self._fps_capture_window: int = 0
        self._fps_ai_window: int = 0
        # Đếm riêng "JPEG mới" vs "JPEG lặp (cùng frame_seq)".
        # Trước đây mỗi encode đều đẩy 1 JPEG vào _jpeg_cache và ghi đè
        # _latest_jpeg — frontend viewer cứ 2-3 giây refresh vẫn nhận 1
        # JPEG mới dù pipeline không có frame mới từ camera. Phase 0 phân
        # biệt để dashboard không đếm nhầm.
        self._jpeg_new_count: int = 0
        self._jpeg_repeat_count: int = 0
        self._jpeg_last_emitted_seq: int = -1
        self._frames_dropped_stale: int = 0
        self._frames_dropped_encode: int = 0
        self._violations_persisted_total: int = 0
        self._violations_skipped_total: int = 0

        # Phase 1 (Task 1) — generation + stop-guard:
        # `start()` tăng generation; `_run_loop`, `_persist_violation` và
        # `_finish_crossing_event` capture generation tại THỜI ĐIỂM BẮT ĐẦU
        # tác vụ. Sau khi `stop()` chạy, mọi callback / worker đã submit
        # trước đó nhìn generation CŨ → không phát alert/persist cho phiên
        # đã chết. Trước Phase 1, stop() chỉ set `_running=False` rồi join
        # thread — IO/clip worker pool đã submit từ trước vẫn chạy tiếp
        # và có thể phát alert cho phiên hết hạn (đã gặp thật khi admin
        # restart trong khi xe đang qua).
        self._run_generation: int = 0
        self._stopped: bool = False
        # Exponential-backoff state for camera reconnect — reset khi read OK.
        self._reconnect_failures: int = 0
        # R2: consecutive read errors và reconnect/backoff threshold lưu ở
        # instance level để _handle_read_error() truy cập được (test friendly).
        # Trước đây là local var trong _run_loop, không test được tách rời.
        self._consecutive_errors: int = 0
        self._RECONNECT_AFTER: int = 5
        self._RECONNECT_BACKOFF_SEC: float = 2.0
        self._capture = None
        self._capture_consumed_seq = 0
        self._capture_seq_base = 0
        self._debug_overlay_enabled = True
        for detector in (self._person_detector, self._plate_detector, self._helmet_detector):
            if detector is not None:
                detector.camera_id = self.camera_id
        # Track có TTL/prune — Phase 1: map crossing/sealed/approach có giới hạn
        # và không hồi sinh lượt cũ gây duplicate. Đếm entry + cuối cùng prune
        # entry quá hạn thay vì chờ dict phình ra vô hạn.
        self._crossing_sealed_prune_at: float = 0.0

    def start(self):
        """Bắt đầu thread nền. Phase 1: tăng `_run_generation` để đánh dấu
        phiên mới — toàn bộ worker / alert được enqueue trước đó sẽ không
        ảnh hưởng tới phiên hiện tại."""
        if self._running:
            print("[Pipeline] Already running")
            return

        print("[Pipeline] Starting...")
        self._stopped = False
        self._run_generation += 1
        self._running = True
        # Bước 7: start recorder SAU thread chính — push_frame ngay frame đầu tiên
        # (trước mọi early-return trong _run_loop). Xem comment trong _run_loop.
        if self._recorder is not None:
            self._recorder.start()
        print("[Pipeline] Started")

        # R1 (Task 1): Preview thread tách khỏi AI. Main loop push frame vào queue,
        # preview thread encode JPEG không block. Nếu queue đầy → drop oldest frame.
        # Đây là điểm mấu chốt: main loop KHÔNG encode, KHÔNG chờ encode.
        import queue as _q_module
        self._preview_frame_queue: _q_module.Queue = _q_module.Queue(maxsize=2)
        self._preview_stop = threading.Event()
        self._preview_thread = threading.Thread(
            target=self._preview_loop, daemon=True, name=f"preview-{self.gate_id}")
        self._preview_thread.start()
        print(f"[Pipeline] Preview thread started (queue maxsize=2)")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        ocr_pool = getattr(self, '_ocr_pool', None)
        if getattr(self, '_plate_detector', None) is not None and ocr_pool is not None:
            from app.cv.ocr import warm_up_plate_reader
            ocr_pool.submit(warm_up_plate_reader)

    def stop(self):
        """Dừng thread nền. Phase 1: set `_stopped=True` + tăng generation
        để MỌI worker callback đang chờ trong pool biết là phiên đã chết
        và không phát alert/insert DB cho phiên cũ."""
        if not self._running:
            return

        print("[Pipeline] Stopping...")
        self._stopped = True
        self._running = False
        self._run_generation += 1  # invalidate mọi callback cũ
        self._stop_capture()
        if self._thread:
            self._thread.join(timeout=3.0)
        # F01 (Task 1): guard None cho _detect_pool — minimal profile không
        # có detect pool nên .shutdown(wait=False) trên None sẽ raise.
        if getattr(self, '_detect_pool', None) is not None:
            self._detect_pool.shutdown(wait=False)
        if getattr(self, '_io_pool', None) is not None:
            self._io_pool.shutdown(wait=False)
        if getattr(self, "_clip_pool", None) is not None:
            self._clip_pool.shutdown(wait=False, cancel_futures=True)
        # B2: shutdown OCR worker pool
        if getattr(self, '_ocr_pool', None) is not None:
            self._ocr_pool.shutdown(wait=False)
        if getattr(self, '_crossing_pool', None) is not None:
            self._crossing_pool.shutdown(wait=False, cancel_futures=True)
        if getattr(self, '_recognition_cards', None) is not None:
            self._recognition_cards.close()
        # Bước 7: stop recorder SAU detect_pool + io_pool — join thread writer,
        # finalize segment cuối (release VideoWriter) trước khi process tắt.
        if getattr(self, '_recorder', None) is not None:
            self._recorder.stop()
        # R1: stop preview thread
        if getattr(self, '_preview_stop', None) is not None:
            self._preview_stop.set()
        if getattr(self, '_preview_thread', None) is not None:
            self._preview_thread.join(timeout=2.0)
        print("[Pipeline] Stopped")

    def _is_session_alive(self, captured_generation: int) -> bool:
        """Phase 1: helper — worker callback kiểm tra nhanh phiên còn sống
        không. False = đã stop() hoặc start() lại sau khi tác vụ được enqueue."""
        return (not self._stopped
                and self._running
                and captured_generation == self._run_generation)

    def get_jpeg(self) -> Optional[bytes]:
        """B2: Lấy JPEG pre-encoded bytes mới nhất (hoặc None)."""
        with self._lock:
            return self._latest_jpeg

    # ─── Đợt R helpers ──────────────────────────────────────────────────

    @staticmethod
    def _independent_crop_copy(crop_view: np.ndarray) -> np.ndarray:
        """R2: bản sao C-LIÊN-TỤC — worker giữ không ảnh hưởng frame gốc."""
        return np.ascontiguousarray(crop_view).copy()

    @staticmethod
    def _rescale_bbox(bbox: tuple, scale_x: float, scale_y: float) -> tuple:
        """R5: quy đổi bbox từ ảnh detect (640x480) sang ảnh gốc (1280x720)."""
        x1, y1, x2, y2 = bbox
        return (round(x1 * scale_x), round(y1 * scale_y),
                round(x2 * scale_x), round(y2 * scale_y))

    @staticmethod
    def _crop_for_ocr(frame: np.ndarray, bbox: tuple) -> np.ndarray:
        """R5: lấy crop từ frame gốc, KHÔNG từ frame đã vẽ box."""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        return frame[y1:y2, x1:x2]

    @staticmethod
    def _plate_aspect_ok(bbox: tuple, min_ratio: float = 1.5,
                         max_ratio: float = 6.0) -> bool:
        """R5: bbox có w/h nằm ngoài [1.5, 6.0] → loại."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if h <= 0 or w <= 0:
            return False
        return min_ratio <= (w / h) <= max_ratio

    @staticmethod
    def _is_valid_plate_aspect_ratio(bbox: tuple, min_ratio: float = 1.5,
                                       max_ratio: float = 6.0) -> bool:
        """Wrapper tương thích ngược cho `_plate_aspect_ok`."""
        return VideoPipeline._plate_aspect_ok(bbox, min_ratio=min_ratio,
                                                max_ratio=max_ratio)

    @staticmethod
    def _vertical_overlap(a: tuple, b: tuple) -> bool:
        """True nếu 2 bbox có trục Y chồng lấp (intersect)."""
        ay1, ay2 = a[1], a[3]
        by1, by2 = b[1], b[3]
        return not (ay2 < by1 or by2 < ay1)

    def _smooth_vehicle_type(self, groups, now=None):
        """UT3: vote vehicle_type theo track_id trong window_sec, đa số chiến
        thắng. Khi chưa đủ min_samples → giữ nguyên kết quả frame hiện tại."""
        if now is None:
            now = time.time()
        for g in groups:
            tid = g.get('track_id')
            if tid is None:
                continue
            history = self._track_vehicle_history.setdefault(tid, [])
            current = g.get('vehicle_type')
            history.append((current, now))
            # Bỏ mẫu quá cũ
            cutoff = now - self._vehicle_vote_window_sec
            history[:] = [h for h in history if h[1] >= cutoff]
            if len(history) < self._vehicle_vote_min_samples:
                continue
            # Đa số
            counts: dict = {}
            for vt, _ in history:
                counts[vt] = counts.get(vt, 0) + 1
            winner = max(counts.items(), key=lambda kv: kv[1])[0]
            g['vehicle_type'] = winner

    def _attach_frame_metadata(self, frame, gate_id: str, source_epoch: int,
                                frame_seq: int, ts: float):
        """R1: trả về Frame tuple mang identity (gate_id, source_epoch,
        frame_seq, ts) + np.ndarray."""
        from collections import namedtuple
        Frame = namedtuple('Frame', ['image', 'gate_id', 'source_epoch',
                                      'frame_seq', 'ts'])
        return Frame(image=frame, gate_id=gate_id,
                      source_epoch=source_epoch, frame_seq=frame_seq, ts=ts)

    def _maybe_update_fps(self) -> None:
        """Phase 0: cập nhật capture_fps/ai_fps theo interval 1s.

        Capture FPS = số frame_seq tăng trong 1 giây (mỗi frame mới đọc về
        từ camera). AI FPS = số frame đã QUA detect (counted trong
        `_fps_ai_window` ở nhánh detect) trong 1 giây.

        Đặt cả 2 thành biến "value" — `get_status()` đọc trực tiếp không
        cần tính lại. Counter `_fps_*_window` reset về 0 mỗi lần update.

        Phase 1 (Task 1): đồng thời prune _recognition_results theo TTL.
        Trước đây chỉ có hard cap 500 → trong 1 giờ nhận diện xe máy cũ
        vẫn giữ ~500 entry track_id với timestamp — sau đó drop entry cũ
        nhất. Tuy nhiên bộ nhớ vẫn tăng nếu mỗi lượt đẩy entry mới thay vì
        dọn. Phase 1 thêm prune entry có `time.time() - ts > 30s` (mỗi lượt
        xe ~10-15s, 30s là timeout an toàn cho PlateReviewPanel rerun).
        """
        now = time.monotonic()
        elapsed = now - self._fps_compute_at
        if elapsed < 1.0:
            return
        # Tránh divide-by-zero khi monotonic clock leap (rất hiếm).
        elapsed = max(elapsed, 0.001)
        self._capture_fps_value = round(self._fps_capture_window / elapsed, 2)
        self._ai_fps_value = round(self._fps_ai_window / elapsed, 2)
        self._fps_capture_window = 0
        self._fps_ai_window = 0
        self._fps_compute_at = now
        # Phase 1: prune _recognition_results theo TTL 30s. Cheap O(n) ≤ 500.
        rec = getattr(self, '_recognition_results', None)
        if rec:
            cutoff = time.time() - 30.0
            stale = [tid for tid, (_, ts, _) in rec.items() if ts < cutoff]
            for tid in stale:
                rec.pop(tid, None)

    def _publish_frame_jpeg(self, frame: np.ndarray, frame_seq: int, expected_epoch=None) -> None:
        """R3: encode JPEG đúng 1 lần cho frame này, chia sẻ cho viewer
        qua `get_jpeg()`. Gọi ở cuối mỗi frame loop — kể cả SKIP / NO-PERSON.

        Phase 0: tách bộ đếm `jpeg_new_count` vs `jpeg_repeat_count` — chỉ
        những frame_seq MỚI (khác với frame trước) mới được tính là "hình mới".
        Trước Phase 0 mỗi encode đều đẩy 1 JPEG mới vào `_latest_jpeg`; frontend
        viewer 2-3s/lần refresh luôn thấy "ảnh mới" dù camera không gửi frame
        mới — Phase 0 đếm chính xác để debug.
        """
        t_enc = time.perf_counter()
        try:
            ok, jpeg_buf = cv2.imencode('.jpg', frame,
                                         [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception:
            ok = False
            jpeg_buf = None
        encode_ms = (time.perf_counter() - t_enc) * 1000
        self._metrics_encode.add(encode_ms)
        if expected_epoch is not None and expected_epoch != self._source_epoch:
            return
        if not ok or jpeg_buf is None:
            self._frames_dropped_encode += 1
            with self._lock:
                self._latest_jpeg = None
            return
        jpeg_bytes = jpeg_buf.tobytes()
        if len(self._jpeg_cache) >= self._jpeg_max_size:
            keys = sorted(self._jpeg_cache.keys())[:self._jpeg_max_size // 2]
            for k in keys:
                self._jpeg_cache.pop(k, None)
        # Phase 0: phân biệt JPEG mới (frame_seq khác lần cuối) vs JPEG lặp
        # (cùng frame_seq — xảy ra khi nhiều viewer cùng poll nhanh hoặc khi
        # pipeline re-emit frame cũ do skip). Chỉ tính "hình mới" 1 lần.
        is_new_jpeg = frame_seq != self._jpeg_last_emitted_seq
        if is_new_jpeg:
            self._jpeg_last_emitted_seq = frame_seq
            self._jpeg_new_count += 1
        else:
            self._jpeg_repeat_count += 1
        self._jpeg_cache[frame_seq] = (jpeg_bytes, time.time())
        with self._lock:
            if expected_epoch is not None and expected_epoch != self._source_epoch:
                self._jpeg_cache.pop(frame_seq, None)
                return
            self._latest_jpeg = jpeg_bytes
            self._latest_frame = frame

    def _publish_ai_frame(self, source_frame, dets) -> None:
        """Show the very frame the boxes were computed on.

        Drawing the latest boxes on newer capture frames left them trailing a
        walking person by a body width at ~17 AI fps. While AI frames keep
        coming, capture frames are not shown; see _start_capture.received.
        """
        frames = getattr(self, '_preview_frame_queue', None)
        if frames is None or getattr(self, '_capture', None) is None:
            return
        item = (self._source_epoch, source_frame.copy(), self._frame_seq, dets)
        try:
            frames.put_nowait(item)
        except queue.Full:
            try:
                frames.get_nowait()
            except queue.Empty:
                pass
            try:
                frames.put_nowait(item)
            except queue.Full:
                pass
        self._last_ai_publish = time.monotonic()

    def _preview_loop(self) -> None:
        """R1 (Task 1): Preview encoder thread — tách khỏi main loop.
        Main loop push frame vào queue, preview thread pop và encode JPEG.
        Queue maxsize=2, drop oldest nếu full — không block main loop.
        Stop khi `_preview_stop` event được set."""
        import queue
        while not self._preview_stop.is_set():
            try:
                item = self._preview_frame_queue.get(timeout=.1)
            except queue.Empty:
                continue
            # Legacy test/producer pairs carry no epoch. Runtime always does.
            # AI frames carry their own boxes (4-tuple); capture frames reuse
            # the latest boxes only as a fallback while AI is stalled.
            own_dets = item[3] if len(item) == 4 else None
            epoch, frame, frame_seq = item[:3] if len(item) >= 3 else (self._source_epoch, *item)
            if epoch != self._source_epoch:
                continue
            try:
                overlay = getattr(self, '_preview_overlay', None)
                dets = own_dets
                # A stalled AI must not paint old boxes where a person was
                # half a second ago; past 0.25 s show the frame unboxed.
                if (dets is None and overlay and overlay[0] == self._source_epoch
                        and time.monotonic()-overlay[1] <= .25):
                    dets = overlay[2]
                if getattr(self, '_debug_overlay_enabled', True) and dets:
                    for det, positive, negative in dets:
                        self._draw_detection(frame, det, positive, negative)
                self._draw_roi(frame)
                if DEBUG_CROSSING and getattr(self, '_debug_overlay_enabled', True):
                    self._draw_crossing_line_debug(frame)
                if len(item) >= 3:
                    self._publish_frame_jpeg(frame, frame_seq, expected_epoch=epoch)
                else:
                    self._publish_frame_jpeg(frame, frame_seq)
            except Exception:
                pass

    # ── R3 (Task 1+3): Model hot-reload from candidate ──────────────────────
    def reload_model_from_candidate(self, candidate_id: str) -> dict:
        """R3 (Task 1+3): Hot-reload detector from a training candidate.

        Called when a candidate's `pending_runtime` state should be applied.
        1. Read candidate metadata from the training DB (model_path, engine).
        2. Verify artifact loadability (quick smoke test).
        3. Swap _helmet_detector / _plate_detector / _person_detector under lock.
        4. Save baseline snapshot for rollback.
        5. Update _helmet_health status.

        Returns dict with keys: success (bool), message (str), old_state (dict)."""
        import threading
        result = {"success": False, "message": "", "old_state": None}

        # Read candidate metadata
        try:
            from app.training.dataset_repo import get_candidate
            cand = get_candidate(candidate_id)
        except Exception as exc:
            result["message"] = f"Cannot read candidate {candidate_id!r}: {exc}"
            return result

        if cand is None:
            result["message"] = f"Candidate {candidate_id!r} not found"
            return result

        engine = cand.get("engine", "")
        model_path = cand.get("model_path", "")
        if not model_path:
            result["message"] = f"Candidate {candidate_id!r} has no model_path"
            return result

        if not Path(model_path).exists():
            result["message"] = f"Model path {model_path!r} does not exist"
            return result

        # Determine which detector to replace
        if engine == "helmet":
            attr = "_helmet_detector"
            conf_key = "HELMET_CONF_THRESHOLD"
            mapping_key = "HELMET_MODEL_MAPPING"
        elif engine == "plate_detector":
            attr = "_plate_detector"
            conf_key = "PLATE_CONF_THRESHOLD"
            mapping_key = None
        elif engine == "person":
            attr = "_person_detector"
            conf_key = "PERSON_CONF_THRESHOLD"
            mapping_key = None
        else:
            result["message"] = f"Unknown engine {engine!r} for hot-reload"
            return result

        # Save old state for rollback
        old_detector = getattr(self, attr, None)
        result["old_state"] = {
            "detector": old_detector,
            "path": getattr(self, f"_{attr[1:]}") if hasattr(self, f"_{attr[1:]}") else None,
        }

        # Load new detector under lock
        from app.config import HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD
        threshold_map = {
            "_helmet_detector": HELMET_CONF_THRESHOLD,
            "_plate_detector": PLATE_CONF_THRESHOLD,
            "_person_detector": PERSON_CONF_THRESHOLD,
        }
        threshold = threshold_map.get(attr, 0.25)

        try:
            new_detector = HelmetPlateDetector(model_path, conf_threshold=threshold)
        except Exception as exc:
            result["message"] = f"Failed to load {model_path!r}: {exc}"
            return result

        # Helmet mapping validation
        if engine == "helmet":
            from app.config import HELMET_MODEL_MAPPING
            try:
                from app.cv.helmet_contract import validate_helmet_mapping
                expected = HELMET_MODEL_MAPPING
                names = new_detector.class_names
                if not validate_helmet_mapping(names, expected):
                    result["message"] = (
                        f"Helmet mapping mismatch: expected={expected}, got={list(names)}"
                    )
                    return result
            except ImportError:
                pass  # helmet_contract not available

        # Swap under lock
        with self._lock:
            setattr(self, attr, new_detector)
            if engine == "helmet":
                self._helmet_health = {
                    "status": "ready",
                    "classes": new_detector.class_names,
                    "source": "candidate",
                    "candidate_id": candidate_id,
                    "model_path": model_path,
                }
                # Compute hash
                try:
                    import hashlib
                    with open(model_path, "rb") as f:
                        h = hashlib.sha256(f.read()).hexdigest()
                    self._helmet_health["model_sha256"] = h
                except Exception:
                    pass

        result["success"] = True
        result["message"] = f"Hot-reloaded {engine} from {model_path!r}"
        result["new_model_path"] = model_path
        return result

    def rollback_to_baseline(self, engine: str = "helmet") -> dict:
        """R3 (Task 1+3): Rollback detector to baseline (original HELMET_MODEL_PATH).

        Returns dict with keys: success (bool), message (str)."""
        result = {"success": False, "message": ""}

        # Restore from original model paths
        from app.config import HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH
        from app.config import HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD

        path_map = {
            "helmet": HELMET_MODEL_PATH,
            "plate_detector": PLATE_MODEL_PATH,
            "person": PERSON_MODEL_PATH,
        }
        threshold_map = {
            "helmet": HELMET_CONF_THRESHOLD,
            "plate_detector": PLATE_CONF_THRESHOLD,
            "person": PERSON_CONF_THRESHOLD,
        }
        attr_map = {
            "helmet": "_helmet_detector",
            "plate_detector": "_plate_detector",
            "person": "_person_detector",
        }

        model_path = path_map.get(engine)
        if not model_path:
            result["message"] = f"Unknown engine {engine!r}"
            return result

        if not Path(model_path).exists():
            result["message"] = f"Baseline model path {model_path!r} does not exist"
            return result

        try:
            new_detector = HelmetPlateDetector(model_path, conf_threshold=threshold_map[engine])
        except Exception as exc:
            result["message"] = f"Failed to load baseline {model_path!r}: {exc}"
            return result

        attr = attr_map[engine]
        with self._lock:
            setattr(self, attr, new_detector)
            if engine == "helmet":
                self._helmet_health = {
                    "status": "ready",
                    "classes": new_detector.class_names,
                    "source": "baseline",
                    "model_path": model_path,
                }

        result["success"] = True
        result["message"] = f"Rolled back {engine} to baseline {model_path!r}"
        return result

    def _ocr_submit_with_epoch(self, frame: np.ndarray, plate_det,
                                track_id: int, frame_seq: int,
                                source_epoch: int) -> None:
        """R1+R2: submit OCR với epoch/seq. Đảm bảo mỗi track 1 pending; crop
        là bản sao độc lập; không cancel future đang chạy.

        Phase 0: ghi lại `submitted_at` để `_ocr_consume_pending` tính được
        OCR wait latency (time từ submit → kết quả về). Buffer bounded 60
        mẫu; percentile p50/p95 phục vụ debug OCR chậm.
        """
        if track_id is None:
            return
        if track_id in self._ocr_pending:
            self._ocr_health["duplicate_dropped"] += 1
            return
        # Preview and verified OCR use separate votes, but share a single
        # pending slot for the actual person. A preview never proves ownership.
        alternate = -track_id-1
        if alternate in self._ocr_pending:
            self._ocr_health["duplicate_dropped"] += 1
            return
        # Backlog cross-track
        if (len(self._ocr_pending) >= self._ocr_max_pending
                and track_id not in self._ocr_pending):
            self._ocr_health["stale_dropped"] += 1
            return
        x1, y1, x2, y2 = plate_det.bbox
        h, w = frame.shape[:2]
        pad_x = int((x2 - x1) * PLATE_CROP_PAD_X)
        pad_y = int((y2 - y1) * PLATE_CROP_PAD_Y)
        x1_p = max(0, x1 - pad_x)
        x2_p = min(w, x2 + pad_x)
        y1_p = max(0, y1 - pad_y)
        y2_p = min(h, y2 + pad_y)
        crop_view = frame[y1_p:y2_p, x1_p:x2_p]
        crop_copy = self._independent_crop_copy(crop_view)
        # Crop quá mờ: bỏ qua, chờ frame sau nét hơn — đỡ tốn 1 lượt OCR và
        # đỡ đưa text rác vào plate_voter. PLATE_MIN_BLUR_SCORE<=0 (mặc định)
        # = TẮT hẳn, không tính Laplacian — hàm này chạy ĐỒNG BỘ trên thread
        # chính (không phải OCR pool), tính dù không dùng là phí vô ích mỗi
        # lần có plate detect, từng góp phần làm tăng độ trễ xử lý frame.
        if PLATE_MIN_BLUR_SCORE > 0 and crop_copy.shape[0] >= 20 and crop_copy.shape[1] >= 40:
            blur = compute_blur_score(crop_copy)
            if blur < PLATE_MIN_BLUR_SCORE:
                self._ocr_health["blur_skipped"] += 1
                if DEBUG_PLATE_OCR:
                    print(f"[PlateOCR] track={track_id} SKIP_OCR reason=blur_low blur={blur:.0f} "
                          f"crop={crop_copy.shape[1]}x{crop_copy.shape[0]}")
                return
        submitted_at = time.perf_counter()
        self._ocr_pending[track_id] = self._ocr_pool.submit(
            _ocr_task, crop_copy, track_id, frame_seq, source_epoch,
        )
        self._ocr_submit_meta[track_id] = {
            "frame_seq": frame_seq,
            "source_epoch": source_epoch,
            "ts": time.time(),
            "plate_bbox": plate_det.bbox,
            "plate_class": plate_det.class_name,
            "plate_confidence": plate_det.confidence,
            "submitted_at_perf": submitted_at,
        }
        self._ocr_health["submitted"] += 1

    def _ocr_consume_pending(self, track_id: int):
        """R2: lấy kết quả OCR đã xong cho track_id (consume 1 lần).

        Phase 0: ghi lại OCR wait latency = (now − submitted_at_perf) ms.
        """
        fut = self._ocr_pending.get(track_id)
        if fut is None:
            return None
        if not fut.done():
            return None
        try:
            ocr_result = fut.result()
        except Exception:
            self._ocr_pending.pop(track_id, None)
            meta = getattr(self, "_ocr_submit_meta", None)
            submitted_perf = None
            if meta is not None:
                m = meta.pop(track_id, None)
                if m:
                    submitted_perf = m.get("submitted_at_perf")
            if submitted_perf is not None:
                self._metrics_ocr_wait.add((time.perf_counter() - submitted_perf) * 1000)
            self._ocr_health["errors"] += 1
            return None
        self._ocr_pending.pop(track_id, None)
        meta = getattr(self, "_ocr_submit_meta", None)
        submitted = None
        submitted_perf = None
        if meta is not None:
            submitted = meta.pop(track_id, None)
            if submitted:
                submitted_perf = submitted.get("submitted_at_perf")
                ocr_result['_submitted_at'] = submitted['ts']
                ocr_result['_expected_frame_seq'] = submitted['frame_seq']
        if submitted_perf is not None:
            self._metrics_ocr_wait.add((time.perf_counter() - submitted_perf) * 1000)
        self._ocr_health["completed"] += 1
        return ocr_result

    def _ocr_consume_pending_if_fresh(self, track_id: int, current_epoch: int):
        """R1+R2: như consume_pending + kiểm tra source_epoch. Lệch epoch → bỏ."""
        ocr_result = self._ocr_consume_pending(track_id)
        if ocr_result is None:
            return None
        result_epoch = ocr_result.get("source_epoch", current_epoch)
        if result_epoch != current_epoch:
            self._ocr_health["stale_dropped"] += 1
            return None
        if (ocr_result.get('track_id', track_id) != track_id or
                ocr_result.get('frame_seq') != ocr_result.get('_expected_frame_seq', ocr_result.get('frame_seq')) or
                time.time()-ocr_result.get('_submitted_at', time.time()) > PLATE_VOTE_WINDOW_SEC):
            self._ocr_health['stale_dropped'] += 1
            return None
        if ocr_result.get("error"):
            self._ocr_health["errors"] += 1
        elif not ocr_result.get("full"):
            self._ocr_health["empty"] += 1
        return ocr_result

    def _ocr_init_reader(self) -> None:
        """Đảm bảo EasyOCR Reader đã init từ main thread (1 lần/gate).
        Đa gate dùng chung Reader nhờ lazy init trong app.cv.ocr."""
        from app.cv.ocr import _get_reader
        _get_reader()

    def _submit_ocr_async(self, frame: np.ndarray, plate_det,
                          track_id: int | None, frame_seq: int) -> None:
        """B2 wrapper: submit với source_epoch hiện tại."""
        if track_id is None:
            return
        self._ocr_submit_with_epoch(frame, plate_det, track_id, frame_seq,
                                     self._source_epoch)

    def _collect_plate_vote(self, track_id, plate_det=None):
        """Collect once, even when the plate detector misses the next frame."""
        meta = getattr(self, '_ocr_submit_meta', {}).get(track_id, {})
        result = self._ocr_consume_pending_if_fresh(track_id, self._source_epoch)
        if result is None:
            return None
        box = meta.get('plate_bbox', getattr(plate_det, 'bbox', None))
        if box is None:
            return None
        detection = Detection(meta.get('plate_class', 'plate'),
                              meta.get('plate_confidence', 0), box, track_id)
        voted = self._plate_voter.add_result(detection, result)
        if not hasattr(self, '_recognition_results'):
            self._recognition_results = {}
        self._recognition_results[track_id] = (voted, time.time(), result.get('frame_seq'))
        if len(self._recognition_results) > 500:
            self._recognition_results.pop(next(iter(self._recognition_results)))
        if DEBUG_PLATE_OCR:
            state = 'CONFIRMED' if voted.is_confident else ('PARTIAL' if voted.text else 'EMPTY')
            print(f"[PlateOCR] track={track_id} det={detection.confidence:.2f} "
                  f"OCR={result.get('full', '')!r} norm={voted.text!r} "
                  f"conf={voted.confidence:.2f} support={voted.sample_count} {state}")
        return voted

    def _cached_plate_vote(self, track_id):
        cached = getattr(self, '_recognition_results', {}).get(track_id)
        if cached and time.time()-cached[1] < PLATE_VOTE_WINDOW_SEC:
            return cached[0]
        return None

    def _read_plate_voted(self, frame: np.ndarray, plate_det,
                          track_id: int | None = None, frame_seq: int = 0):
        """Asynchronous OCR only; stable tracks own at most one pending crop."""
        from app.cv.plate_voter import PlateReadResult
        if track_id is None:
            return PlateReadResult(pending=True)
        self._collect_plate_vote(track_id, plate_det)
        cached = self._cached_plate_vote(track_id)
        # Đã confirmed (is_confident) trong cửa sổ PLATE_VOTE_WINDOW_SEC hiện
        # tại: KHÔNG submit OCR lại mỗi frame nữa — tốn tài nguyên vô ích cho
        # 1 biển đã đọc chắc chắn rồi. Cache tự hết hạn sau
        # PLATE_VOTE_WINDOW_SEC (không có update mới), lúc đó tự động OCR lại
        # để xác nhận vẫn còn đúng xe — không cần thêm cooldown config riêng.
        if cached is None or not cached.is_confident:
            self._ocr_submit_with_epoch(frame, plate_det, track_id, frame_seq, self._source_epoch)
        else:
            self._ocr_health["confirmed_skipped"] += 1
            if DEBUG_PLATE_OCR:
                print(f"[PlateOCR] track={track_id} CONFIRMED (skip re-OCR) text={cached.text}")
        return cached or PlateReadResult(pending=True)

    def _apply_camera_change(self):
        """Đợt R1+R3: đổi nguồn camera → tăng source_epoch, clear pending OCR,
        discard JPEG cũ, reset detection state để track mới từ nguồn mới không
        trộn với track cũ. Lỗi đổi giữ nguồn cũ (CameraSwitch.apply đã lo).
        Trả về True nếu apply thành công, False nếu thất bại."""
        if not self._stop_capture():
            return False
        try:
            from app.cv.camera_switch import CameraSwitch
            if not isinstance(self.camera_switch, CameraSwitch):
                # Test/mock: bỏ qua
                return False
            result = self.camera_switch.apply(
                self._webcam,
                lambda source: self._open_webcam(
                    {**GATES.get(self.gate_id, {}), 'source': source}),
                lambda source: set_gate_camera_source(self.gate_id, source),
            )
        except Exception:
            return False
        if result is None:
            self._start_capture()
            return False
        self._webcam, frame = result
        self._active_source = self.camera_switch.source
        # Cập nhật GATES dict để polling/reload cũng thấy source mới
        try:
            GATES[self.gate_id]['source'] = self.camera_switch.source
        except Exception:
            pass
        # R1: source_epoch tăng — mọi OCR result cũ sẽ bị consume-time filter
        self._source_epoch += 1
        if hasattr(self, '_recognition_log'):
            self._recognition_log.reset(self._source_epoch)
            self._recognition_results.clear()
        if hasattr(self, '_recognition_cards'):
            self._recognition_cards.reset(self._source_epoch)
        # R2: clear pending OCR — pipeline mới đã khác view, không dùng kết quả cũ
        self._ocr_pending.clear()
        meta = getattr(self, "_ocr_submit_meta", None)
        if meta is not None:
            meta.clear()
        # R3: discard JPEG cũ — đổi nguồn không phát lại frame cũ
        with self._lock:
            if frame is not None:
                self._latest_frame = frame
            self._latest_jpeg = None
        self._jpeg_cache.clear()
        # Reset các biểu thức chỉ định/danh giờ (evidence from different viewpoints
        # must never share a track/clip):
        self._last_person_dets = []
        self._last_helmet_dets = []
        self._last_plate_dets = []
        self._last_pose_data = []
        if hasattr(self, '_prev_track_bbox'):
            self._prev_track_bbox.clear()
        if hasattr(self, '_track_vehicle_history'):
            self._track_vehicle_history.clear()
        self._last_face_t = 0.0
        self._last_log_time.clear()
        for name in ('_best_plates', '_riding_temporal'):
            store = getattr(self, name, None)
            if store is not None:
                (store.reset if name == '_best_plates' else store.clear)()
        # Phase 2: reset consensus store (track mới không nên thừa hưởng vote cũ)
        consensus = getattr(self, '_plate_consensus', None)
        if consensus is not None:
            consensus.reset()
        self._plate_approach = {}
        self._crossing_sealed = {}
        self._plate_last_crossing = {}
        self._last_sealed_crossing = {}
        # Phase 4 (Task 1): reset late-issue DB id map khi đổi nguồn
        self._crossing_event_to_db_id = {}
        if getattr(self, "_evidence_ledger", None) is not None:
            self._evidence_ledger.reset()
        if getattr(self, "_crossing_detector", None) is not None:
            self._crossing_detector.reset()
        self._fast_track_active = False
        if hasattr(self, '_clip_buffer'):
            self._clip_buffer.clear()
        if hasattr(self, '_frame_timestamps'):
            self._frame_timestamps.clear()
        # Reset PlateVoter + EventManager để vote lại từ đầu (track cũ không
        # còn ý nghĩa với view mới)
        try:
            from app.config import (PLATE_VOTE_WINDOW_SEC, PLATE_VOTE_MIN_AGREE,
                                     PLATE_MIN_CONFIDENCE_SINGLE,
                                     EVENT_STREAK_MIN_FRAMES, EVENT_WINDOW_SEC,
                                     EVENT_GRACE_PERIOD_SEC)
            self._plate_voter = PlateVoter(
                grid_px=60,
                window_sec=PLATE_VOTE_WINDOW_SEC,
                min_agree=PLATE_VOTE_MIN_AGREE,
                min_confidence_single=PLATE_MIN_CONFIDENCE_SINGLE,
            )
            from app.cv.event_manager import EventManager
            self._event_manager = EventManager(
                streak_min_frames=EVENT_STREAK_MIN_FRAMES,
                window_sec=EVENT_WINDOW_SEC,
                grace_period_sec=EVENT_GRACE_PERIOD_SEC,
            )
        except Exception:
            pass
        # Reset ByteTrack của person detector (nếu có)
        try:
            for detector in (self._person_detector, self._plate_detector):
                if detector is not None:
                    detector.reset_tracker()
        except Exception:
            pass
        self._start_capture()
        return True

    def _maybe_reload_source(self) -> None:
        """Reload source từ GATES dict (poll mỗi 5s). Không tăng epoch vì đây
        là cùng view."""
        try:
            new_src = GATES.get(self.gate_id, {}).get('source')
            if new_src is not None and str(new_src) != str(self._active_source):
                if hasattr(self, 'camera_switch') and self.camera_switch is not None:
                    self.camera_switch.request(new_src)
        except Exception:
            pass

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Lấy frame mới nhất đã xử lý.
        Trả về None nếu chưa có frame.
        """
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def set_roi(self, points: list | None) -> None:
        """Cập nhật vùng ROI sống (không restart pipeline). `points=None hoặc []`
        tắt ROI. Lưu DB trước rồi mới gán vào pipeline đang chạy."""
        set_gate_roi(self.gate_id, points or [])
        self._roi_points = points or None
        self._roi_polygon_px = to_pixel_polygon(self._roi_points, VIDEO_WIDTH, VIDEO_HEIGHT)

    def get_alert(self) -> Optional[dict]:
        """Lấy cảnh báo từ queue, trả None nếu không có."""
        try:
            return self._alert_queue.get_nowait()
        except queue.Empty:
            return None

    def _diagnostic(self, stage, status, reason, track_id=None, frame_seq=None, source_epoch=None, **details):
        if not getattr(self, '_recognition_logging_enabled', True):
            return
        if not hasattr(self, '_recognition_log'):
            from app.cv.recognition_log import RecognitionLog
            self._recognition_log = RecognitionLog(self.gate_id, getattr(self, 'camera_id', self.gate_id))
        self._recognition_log.append(track_id, frame_seq if frame_seq is not None else getattr(self, '_frame_seq', 0),
            source_epoch if source_epoch is not None else getattr(self, '_source_epoch', 0), stage, status, reason, details)

    def recognition_snapshot(self, after_seq=0, limit=50):
        if not hasattr(self, '_recognition_log'):
            self._diagnostic('camera', 'pending', 'recognition_starting')
        return {**self._recognition_log.snapshot(after_seq, limit),
                'models': {'helmet': getattr(self, '_helmet_health', {'status': 'unknown'}),
                           'plate': {'status': 'ready'}, 'person': {'status': 'ready'}},
                'ocr': dict(getattr(self, '_ocr_health', {})), 'camera': self.get_status()}

    def recognition_models(self):
        def profile(attribute):
            detector = getattr(self, attribute, None)
            return getattr(detector, 'profile', {}) if detector is not None else {}
        return {'person': profile('_person_detector'), 'plate': profile('_plate_detector'),
                'helmet': {**profile('_helmet_detector'), **getattr(self, '_helmet_health', {})},
                'ocr': {'engine': 'EasyOCR'}, 'tracker': {'engine': 'ByteTrack'}}

    def _observe_group(self, source_frame, group):
        """Recognition remains visible even when no official violation is possible."""
        tid = group.get('track_id')
        # Plate OCR/vote key theo XE (vehicle_track_id), không theo người —
        # xe chở 2 người tạo 2 group/frame CÙNG trỏ 1 plate_dets; key theo
        # người sẽ submit OCR 2 lần cho cùng 1 crop biển và chia vote thành 2
        # bucket độc lập cho cùng 1 xe. Fallback về tid khi ByteTrack chưa
        # confirm track xe (vehicle_track_id=None).
        ocr_key = group.get('vehicle_track_id')
        if ocr_key is None:
            ocr_key = tid
        common = {'vehicle_track_id': group.get('vehicle_track_id'),
                  'posture': group.get('posture_status', 'unknown'),
                  'objects': ['person'] + ([group['vehicle_type']] if group.get('vehicle_type') else [])}
        helmets = group['helmet_dets']
        yes = any(d.class_name == 'With Helmet' for d in helmets)
        no = any(d.class_name == 'Without Helmet' for d in helmets)
        model_error = getattr(self, '_helmet_health', {}).get('status') == 'error'
        helmet = 'model_error' if model_error else 'unknown' if yes == no else 'helmet' if yes else 'no_helmet'
        self._diagnostic('helmet', 'error' if model_error else 'observed' if helmet != 'unknown' else 'review',
            'helmet_model_unavailable' if model_error else 'helmet_conflict' if yes and no else
            'helmet_observed' if yes else 'no_helmet_observed' if no else 'head_not_observed', tid,
            helmet=helmet, **common)
        for reason in group.get('association_reasons', []):
            self._diagnostic('detect', 'review', reason, tid, **common)
        plate = self._observe_best_plate(source_frame, group)
        reason = 'plate_association_ambiguous' if 'plate_association_ambiguous' in group.get('association_reasons', []) else 'vehicle_not_associated' if group.get('_vehicle') is None else 'plate_not_detected'
        state = 'review'
        if group.get('plate_dets'):
            if ocr_key is None:
                reason = 'track_missing'
            elif group.get('_vehicle') is None:
                reason = 'vehicle_not_associated'
        if plate is not None:
            reason, state = ('ocr_error', 'error') if plate.error else ('ocr_pending', 'pending') if plate.pending else \
                ('plate_confirmed', 'observed') if plate.is_confident else ('plate_candidate', 'review') if plate.text else ('ocr_empty', 'review')
        cached = getattr(self, '_recognition_results', {}).get(ocr_key)
        result_frame = cached[2] if cached and plate is cached[0] else None
        self._diagnostic('ocr', state, reason, tid, frame_seq=result_frame, plate_text=plate.text if plate else '',
            plate_samples=plate.sample_count if plate else 0, confidence=plate.confidence if plate else None, **common)
        group['_plate_result'] = plate
        # Unassociated boxes can be previewed, but have no vehicle OCR attempt
        # and can never be used for student/vehicle matching.
        group['_helmet_model_error'] = model_error
        cards = getattr(self, '_recognition_cards', None)
        if cards is not None and '_person' in group:
            cards.observe(source_frame, group, self._frame_seq, self._source_epoch)

    def _observe_best_plate(self, frame, group):
        """Detect/score every crop, but trigger one selected crop near the line."""
        from app.cv.best_plate import make_candidate
        from app.config import PLATE_BEST_MIN_QUALITY, DEBUG_PLATE_BEST_FRAME, PLATE_CONSENSUS_ENABLED
        tid = group.get('vehicle_track_id')
        store = getattr(self, '_best_plates', None)
        if tid is None or store is None or group.get('_vehicle') is None:
            return None
        detector = getattr(self, '_crossing_detector', None)
        hist = getattr(detector, '_tracks', {}).get(tid)
        previous_crossing = getattr(self, '_plate_last_crossing', {})
        if hist and hist.rearmed and previous_crossing.get(tid) == hist.crossed_at and hist.crossed_at is not None:
            store.discard(tid)
            previous_crossing.pop(tid, None)
        store.touch(tid)
        if len(self._plate_approach) > 64:
            self._plate_approach = {k:v for k,v in self._plate_approach.items() if time.monotonic()-v[2] < 60}
        result = store.collect(tid, self._ocr_pool, _ocr_task, self._source_epoch)
        if result is not None:
            self._ocr_health['completed'] += 1
            if result.error:
                self._ocr_health['errors'] += 1
            elif not result.text:
                self._ocr_health['empty'] += 1
        for det in group.get('plate_dets', []):
            original = getattr(self, '_original_source_frame', frame)
            sh, sw = original.shape[:2]
            dh, dw = frame.shape[:2]
            bbox = self._rescale_bbox(det.bbox, sw/dw, sh/dh)
            candidate = make_candidate(original, bbox, det.confidence, self._frame_seq, time.time())
            store.offer(tid, candidate)
        best = store.candidate(tid)
        # Phase 2: ingest OCR result vào consensus store (chạy song song
        # với BestPlateStore fast-path). BestPlateStore dùng crop 1 frame
        # để trigger gần line; consensus vote qua nhiều frame.
        if PLATE_CONSENSUS_ENABLED:
            self._consensus_ingest(tid, result, store.completed_candidate(tid) or best)
        if detector and detector.gate_line and best:
            from app.cv.crossing import vehicle_anchor
            from app.cv.crossing import _signed_side_and_projection
            h, w = frame.shape[:2]
            anchor = vehicle_anchor(group['_vehicle'].bbox)
            x1,y1,x2,y2 = detector.gate_line
            distance, _, projection = _signed_side_and_projection(*anchor, x1*w,y1*h,x2*w,y2*h)
            diagonal = (w*w+h*h)**.5
            distance = abs(distance)/diagonal
            prior = self._plate_approach.get(tid)
            if prior is None or prior[0] != self._frame_seq:
                self._plate_approach[tid] = (self._frame_seq, distance, time.monotonic())
            approaching = prior is not None and self._frame_seq > prior[0] and distance < prior[1]
            near = 0 <= projection <= 1 and approaching and distance <= .20
            imminent = near and distance <= .05
            if (near and best.quality_score >= PLATE_BEST_MIN_QUALITY) or imminent:
                if store.trigger(tid, self._ocr_pool, _ocr_task, self._source_epoch):
                    self._ocr_health['submitted'] += 1
        group['_plate_debug'] = store.debug(tid)
        group['_best_plate_crop'] = best.crop if best else None
        if DEBUG_PLATE_OCR or DEBUG_PLATE_BEST_FRAME:
            self._diagnostic('ocr', 'observed', 'best_plate_selected', tid, best_plate=group['_plate_debug'])
        if not detector or not detector.gate_line:
            self._diagnostic('decision', 'pending', 'gate_line_missing', tid)
        single = store.result(tid)
        self._announce_plate(tid, single)
        return self._consensus_result(tid, single)

    def _observe_plate_only(self, source_frame, plate_dets):
        """N02 (Post-Video Review): rear/ocr_only hoặc camera chỉ thấy biển
        không có người — vẫn phải chạy OCR + consensus cho mỗi plate det,
        không phụ thuộc person/vehicle tracker.

        - Track_id tạm = quantized centroid (rx,ry) — ổn định trong 5–10 frame
          liên tiếp cho cùng 1 biển đứng yên.
        - BestPlateStore + PlateConsensusStore xử lý độc lập với group-by-person.
        - Không gán học sinh, không tạo violation; chỉ hiển thị OCR review."""
        from app.cv.best_plate import make_candidate
        from app.config import PLATE_BEST_MIN_QUALITY, PLATE_CONSENSUS_ENABLED
        store = getattr(self, '_best_plates', None)
        if store is None:
            return
        if self._ocr_pool is None:
            return
        original = getattr(self, '_original_source_frame', source_frame)
        sh, sw = original.shape[:2]
        dh, dw = source_frame.shape[:2]
        for det in plate_dets:
            try:
                bbox = self._rescale_bbox(det.bbox, sw/dw, sh/dh)
            except Exception:
                continue
            x1, y1, x2, y2 = bbox
            tid = det.track_id
            if tid is None:
                continue  # untracked plate remains preview-only; no location identity
            candidate = make_candidate(original, bbox, det.confidence,
                                       self._frame_seq, time.time())
            if candidate is None:
                continue
            store.offer(tid, candidate)
            best = store.candidate(tid)
            if best is None:
                continue
            if best.quality_score >= PLATE_BEST_MIN_QUALITY and store.trigger(tid, self._ocr_pool, _ocr_task, self._source_epoch):
                self._ocr_health['submitted'] += 1
            # Collect kết quả OCR nếu đã về
            result = store.collect(tid, self._ocr_pool, _ocr_task, self._source_epoch)
            if result is not None:
                self._ocr_health['completed'] += 1
                if result.error:
                    self._ocr_health['errors'] += 1
                elif not result.text:
                    self._ocr_health['empty'] += 1
            if PLATE_CONSENSUS_ENABLED:
                self._consensus_ingest(tid, result, store.completed_candidate(tid) or best)
            single = store.result(tid)
            self._announce_plate(tid, single)
            read = self._consensus_result(tid, single)
            self._diagnostic('ocr', 'error' if read and read.error else 'pending' if read and read.pending else 'review',
                'ocr_error' if read and read.error else 'ocr_pending' if read and read.pending else 'plate_candidate' if read and read.text else 'plate_not_read',
                tid, plate_text=read.text if read else '', association='unverified')
            cards = getattr(self, '_recognition_cards', None)
            if cards is not None:
                cards.observe_plate(tid, best, read, store.debug(tid), self._frame_seq, self._source_epoch)

    def _consensus_ingest(self, tid: int, best_plate_result, best_candidate) -> None:
        """Phase 2 (Task 1): nhận kết quả OCR từ BestPlateStore + best crop
        hiện tại → ingest vào PlateConsensusStore để vote đa-frame.

        best_plate_result: PlateReadResult từ BestPlateStore.collect() (có thể None
        nếu OCR future chưa xong).
        best_candidate: PlateCandidate từ BestPlateStore.candidate() (có thể None).

        Hành vi:
          - Nếu có result và best_candidate: tạo CropRecord từ (result, candidate)
            rồi ingest.
          - Nếu không có result nhưng có candidate: KHÔNG ingest (consensus yêu cầu
            OCR xong, không vote crop chưa đọc).
          - Nếu có best_plate_result nhưng candidate đã bị thay thế (frame_id khác
            best.frame_id): vẫn ingest vì kết quả OCR gắn với crop cũ; CropRecord
            tự skip frame_id trùng.
        """
        consensus = getattr(self, '_plate_consensus', None)
        if consensus is None or best_plate_result is None or best_candidate is None:
            return
        from app.cv.plate_consensus import CropRecord
        # best_candidate.frame_id khớp frame_id mà OCR chạy trên đó.
        record = CropRecord(
            frame_id=best_candidate.frame_id,
            timestamp=best_candidate.timestamp,
            normalized=best_plate_result.text or '',
            confidence=best_plate_result.confidence or 0.0,
            quality_score=best_candidate.quality_score or 0.0,
            raw={'error': best_plate_result.error} if best_plate_result.error else {},
            error=best_plate_result.error,
        )
        consensus.ingest_offer(tid, record)

    def _sample_gpu_runtime_snapshot(self) -> dict:
        """Phase 6 (Task 1): trả runtime config + VRAM stats. Throttled
        để không spam `torch.cuda.memory_allocated` mỗi poll."""
        from app.cv.gpu_profiler import get_runtime_config
        cfg = get_runtime_config()
        from app.cv.inference_worker import model_owner
        cfg['owner'] = model_owner().status()
        try:
            import torch
            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                cfg['device_used_mb'] = round((total-free)/1024**2, 1)
                cfg['torch_reserved_mb'] = round(torch.cuda.memory_reserved()/1024**2, 1)
                cfg['budget_mb'] = 3276.8
                cfg['budget_exceeded'] = (total-free) > 3.2*1024**3
        except Exception:
            cfg['device_used_mb'] = None
        profiler = getattr(self, '_gpu_profiler', None)
        if profiler is not None:
            profiler.sample()
            cfg['vram'] = profiler.stats()
        else:
            cfg['vram'] = None
        return cfg

    def dispatch_late_issues(self, eid: str, new_issues: list) -> bool:
        """Phase 4 + F07 (Task 1): merge issues đến trễ vào DB row của
        crossing đã seal. KHÔNG tạo alert mới, KHÔNG tăng event version.

        Idempotent: nếu eid đã bị prune khỏi `_crossing_event_to_db_id` thì
        bỏ qua (event quá cũ, không còn update được). Late issues có thể
        đến từ evidence ledger confirm mũ 100ms sau crossing seal.

        F07 fix (merge thật): KHÔNG ghi đè issues_json bằng danh sách mới
        (trước đây late update chỉ có mũ → mất hết lỗi trước đó). Phải:
          1. Đọc issues_json hiện tại từ DB.
          2. Merge với new_issues theo code (giữ issue đã có, cập nhật
             sample_count từ issue mới nếu cùng code).
          3. Ghi lại.
        Nếu đọc DB fail → trả False (không báo success khi row không tồn
        tại hoặc write fail).
        """
        if not new_issues:
            return False
        # Dùng getattr để chịu test fixture xây dựng pipeline qua __new__
        # mà không gọi __init__ (một số test cũ trong test_vehicle_gate /
        # test_vehicle_crossing_aggregation).
        db_id = getattr(self, '_crossing_event_to_db_id', {}).get(eid)
        if db_id is None:
            return False
        try:
            from app.db import update_violation_issues, get_connection
            # F07: merge với issues hiện tại — KHÔNG ghi đè. Đọc row hiện
            # tại, hợp nhất theo `code`, ghi lại.
            existing: list = []
            try:
                conn = get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT issues_json FROM violation_events WHERE id = ?",
                        (db_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        # Row đã bị xóa / chưa commit — vẫn cho phép ghi
                        # issues mới (giữ backward-compat Phase 4).
                        existing = []
                    else:
                        raw = row["issues_json"]
                        if isinstance(raw, str) and raw:
                            try:
                                parsed = json.loads(raw)
                                if isinstance(parsed, list):
                                    existing = parsed
                            except (ValueError, TypeError):
                                existing = []
                finally:
                    conn.close()
            except Exception:
                # Đọc fail — vẫn thử update với danh sách rỗng + mới (best
                # effort). Caller sẽ thấy False qua return path cuối cùng.
                existing = []

            # Merge theo `code`: issue đã có giữ nguyên status/sample_count
            # (issue cũ đã được xác nhận — KHÔNG hạ cấp). Nếu issue mới
            # cùng code mà status cao hơn (vd 'deferred' → 'confirmed'),
            # nâng cấp và cộng sample_count.
            merged = list(existing)
            existing_codes = {it.get('code'): i for i, it in enumerate(merged)
                              if isinstance(it, dict) and it.get('code')}
            STATUS_RANK = {'pending': 0, 'deferred': 1, 'review': 2,
                           'confirmed': 3, 'conflict': 3}
            for new_it in new_issues:
                if not isinstance(new_it, dict):
                    continue
                code = new_it.get('code')
                if not code:
                    continue
                if code in existing_codes:
                    idx = existing_codes[code]
                    old = merged[idx]
                    # Nâng cấp status nếu cao hơn
                    old_rank = STATUS_RANK.get(str(old.get('status', '')).lower(), 0)
                    new_rank = STATUS_RANK.get(str(new_it.get('status', '')).lower(), 0)
                    if new_rank > old_rank:
                        merged[idx] = {**old, **new_it, 'sample_count':
                                       (old.get('sample_count') or 0) +
                                       (new_it.get('sample_count') or 0)}
                    # Ngược lại: giữ issue cũ nguyên vẹn (KHÔNG overwrite).
                else:
                    merged.append(new_it)
            issues_json = json.dumps(merged, ensure_ascii=False)
            ok = update_violation_issues(db_id, issues_json=issues_json)
            if not ok:
                return False
            if DEBUG_ALERT:
                print(f"[Alert] late-issue merge event={eid} db_id={db_id} "
                      f"codes={[i.get('code') for i in new_issues]} "
                      f"merged_size={len(merged)}")
            return True
        except Exception as exc:
            print(f'[Pipeline] Late-issue merge failed: {type(exc).__name__}')
            return False

    def consensus_decide(self, tid: int):
        """Phase 2: helper lấy kết quả consensus hiện tại cho 1 track.
        Trả tuple (text_or_None, confidence, sample_count)."""
        consensus = getattr(self, '_plate_consensus', None)
        if consensus is None:
            return None, 0.0, 0
        return consensus.decide(tid)

    def _announce_plate(self, tid, single):
        """Tell viewers once per track when its plate is confirmed, with the
        registration lookup. Visual only (no evidence/audio): violations stay
        the only spoken alerts, so a plate is never read aloud on its own.
        Needs >=2 agreeing reads: a single confident read of the same bike
        on another track came out 89F123192 instead of 89F123792."""
        read = self._consensus_result(tid, single)
        if tid is None or not read.is_confident or not read.text:
            return
        from app.cv import gate_pairing
        gate_pairing.record_plate(self.gate_id, read.text, read.confidence or 0.0)
        # One bike can hold a vehicle track and a plate-only track at once,
        # so dedupe on the plate itself for a minute, not on the track.
        announced = getattr(self, '_announced_plates', None)
        if announced is None:
            announced = self._announced_plates = OrderedDict()
        now = time.monotonic()
        key = (self._source_epoch, read.text)
        if now - announced.get(key, -1e9) < 60:
            return
        announced[key] = now
        announced.move_to_end(key)
        while len(announced) > 512:
            announced.popitem(last=False)
        try:
            vehicle = get_vehicle_by_plate(read.text)
        except Exception:
            vehicle = None
        message = {
            'type': 'plate_recognized', 'plate_read': read.text,
            'plate_matched': vehicle['plate_number'] if vehicle else None,
            'registered': vehicle is not None,
            'student_name': vehicle.get('student_name') if vehicle else None,
            'student_class': vehicle.get('student_class') if vehicle else None,
            'camera_id': getattr(self, 'camera_id', None), 'track_id': tid,
            'source_epoch': self._source_epoch,
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        alerts = getattr(self, '_alert_queue', None)
        if alerts is not None:
            try:
                alerts.put_nowait(message)
            except queue.Full:
                pass

    def _consensus_result(self, tid, single):
        from app.cv.plate_voter import PlateReadResult
        text, confidence, count = self.consensus_decide(tid)
        if text and count >= 2:
            return PlateReadResult(text=text, confidence=confidence, sample_count=count, is_confident=True)
        return PlateReadResult(text=getattr(single, 'text', ''), confidence=getattr(single, 'confidence', 0),
            sample_count=getattr(single, 'sample_count', 0), raw_text=getattr(single, 'raw_text', ''),
            pending=getattr(single, 'pending', False), error=getattr(single, 'error', None))

    def _scan_plate_region(self, source_frame, vehicles, people):
        """Recover small plates with one native-resolution region every .5s.

        Called only after full-frame plate inference has completed. This keeps
        a single owner of the existing model; it creates no additional pool or
        model instance. New observations use the current source frame only.
        """
        if os.environ.get('PLATE_REGION_SCAN_ENABLED', 'true').lower() != 'true':
            return []
        candidates = vehicles or people
        now = time.monotonic()
        if not candidates or now-getattr(self, '_plate_region_scan_at', 0) < .5:
            return []
        self._plate_region_scan_at = now
        index = getattr(self, '_plate_region_scan_index', 0)
        self._plate_region_scan_index = index+1
        obj = candidates[index % len(candidates)]
        x1, y1, x2, y2 = obj.bbox
        h, w = source_frame.shape[:2]
        pad_x, pad_y = round((x2-x1)*.1), round((y2-y1)*.1)
        x1, y1 = max(0, x1-pad_x), max(0, y1-pad_y)
        x2, y2 = min(w, x2+pad_x), min(h, y2+pad_y)
        if x2 <= x1 or y2 <= y1 or (x2-x1)*(y2-y1) > .8*w*h:
            return []
        t0 = time.perf_counter()
        found = self._plate_detector.detect(source_frame[y1:y2, x1:x2])
        self._plate_region_scan_ms = (time.perf_counter()-t0)*1000
        self._plate_region_scans = getattr(self, '_plate_region_scans', 0)+1
        return [Detection(d.class_name, d.confidence,
                (d.bbox[0]+x1, d.bbox[1]+y1, d.bbox[2]+x1, d.bbox[3]+y1)) for d in found]

    def get_status(self) -> dict:
        """Trả về trạng thái sức khỏe của pipeline (dùng cho /api/system/health).

        Phase 0 (Task 1): trả thêm `metrics` (capture/ai FPS, latency p50/p95,
        queues, counters, rss/vram). Trước đây chỉ có `avg_process_latency_ms`
        (1 giá trị, dễ bị frame đột biến kéo lên rồi reset). Giờ tách theo giai
        đoạn và percentile.

        KHÔNG trả về frame data, URL, token hay exception details — chỉ số liệu.
        """
        now = time.time()
        camera_open = self._webcam is not None
        try:
            if camera_open and hasattr(self._webcam, 'is_open'):
                camera_open = self._webcam.is_open()
            elif camera_open:
                # WebcamStream doesn't expose is_open — check via the frame timestamp
                camera_open = (now - self._last_frame_time) < 5.0
        except Exception:
            camera_open = False

        # Feature 7: FPS from sliding window of frame timestamps
        fps = 0.0
        if len(self._frame_timestamps) >= 2:
            span = self._frame_timestamps[-1] - self._frame_timestamps[0]
            fps = round((len(self._frame_timestamps) - 1) / span, 1) if span > 0 else 0.0

        # Feature 7: plate read success rate
        plate_success_rate = (
            round(self._plate_successes / self._plate_attempts, 3)
            if self._plate_attempts > 0 else None
        )

        # Phase 0: resource sampler (psutil RSS + torch CUDA) theo interval
        rss_mb, vram_mb, _sample_at = self._resource_sampler.snapshot()

        # Phase 0: metrics snapshot — bounded buffer percentile, KHÔNG log data
        def _pct(buf, p):
            return buf.percentile(p)

        metrics = {
            "capture_fps": self._capture_fps_value,
            "ai_fps": self._ai_fps_value,
            "jpeg_new_count": self._jpeg_new_count,
            "jpeg_repeat_count": self._jpeg_repeat_count,
            "frames_dropped_stale": self._frames_dropped_stale,
            "frames_dropped_encode": self._frames_dropped_encode,
            "latency": {
                "capture_ms": {"p50": _pct(self._metrics_capture, 50),
                                 "p95": _pct(self._metrics_capture, 95)},
                "detect_ms": {"p50": _pct(self._metrics_detect, 50),
                                "p95": _pct(self._metrics_detect, 95)},
                "ocr_wait_ms": {"p50": _pct(self._metrics_ocr_wait, 50),
                                  "p95": _pct(self._metrics_ocr_wait, 95)},
                "encode_ms": {"p50": _pct(self._metrics_encode, 50),
                                "p95": _pct(self._metrics_encode, 95)},
                "persistence_ms": {"p50": _pct(self._metrics_persistence, 50),
                                     "p95": _pct(self._metrics_persistence, 95)},
                "dispatch_ms": {"p50": _pct(self._metrics_dispatch, 50),
                                  "p95": _pct(self._metrics_dispatch, 95)},
            },
            "queues": {
                "ocr_pending": {"size": len(self._ocr_pending),
                                  "capacity": self._ocr_max_pending},
                "alerts": {"size": self._alert_queue.qsize(),
                             "capacity": self._alert_queue.maxsize},
                "clip_buffer": {"size": len(self._clip_buffer),
                                  "capacity": self._clip_buffer.maxlen},
                "jpeg_cache": len(self._jpeg_cache),
            },
            "counters": {
                "ocr_submitted": self._ocr_health.get("submitted", 0),
                "ocr_completed": self._ocr_health.get("completed", 0),
                "ocr_stale_dropped": self._ocr_health.get("stale_dropped", 0)
                                          + self._ocr_health.get("duplicate_dropped", 0),
                "violations_persisted": self._violations_persisted_total,
                "violations_skipped": self._violations_skipped_total,
            },
            # Phase 1: monotonic counter — tăng mỗi start()/stop(). Worker
            # capture generation tại submit time; nếu mismatch → stale.
            "run_generation": self._run_generation,
            "reconnect_failures": self._reconnect_failures,
            # Phase 2: multi-crop plate consensus (top-N khác frame).
            "plate_consensus": {
                "enabled": bool(getattr(self, '_plate_consensus', None) is not None),
                "tracks": len(getattr(self, '_plate_consensus', []) or []),
            },
            "rss_mb": round(rss_mb, 2) if rss_mb is not None else None,
            "vram_mb": round(vram_mb, 2) if vram_mb is not None else None,
        }

        return {
            "running": self._running,
            "thread_alive": self._thread is not None and self._thread.is_alive(),
            "camera_open": camera_open,
            "last_frame_age_sec": round(now - self._last_frame_time, 2),
            "last_detection_age_sec": round(now - self._last_detection_time, 2),
            "frame_count": self._frame_count,
            "uptime_sec": round(now - self._start_time, 1),
            # Feature 7 new fields
            "fps": fps,
            "avg_process_latency_ms": round(self._last_process_latency_ms, 1),
            "plate_read_success_rate": plate_success_rate,
            "io_health": dict(getattr(self, "_io_health", {})),
            "persist_pending": len(getattr(self, "_persist_pending", {})),
            "pedestrian_count": self._pedestrian_count,
            "rider_count": self._rider_count,
            # Phase 0 (Task 1): metrics chi tiết
            "metrics": metrics,
            # Phase 3 (Task 1): expose role/profile cho UI/system page biết
            # camera này thuộc loại nào (front OCR, rear consensus, aux tracker).
            "role": getattr(self, 'role', None),
            "profile": getattr(self, 'profile', None),
            # Phase 3 (Task 1): 4-state posture temporal ledger (RIDING /
            # PUSHING / WALKING / UNKNOWN). Cho UI GuardPage biết model đang
            # phân loại posture nào để highlight.
            "posture_state": getattr(self, '_posture_confirmed', None),
            "posture_confidence": round(getattr(self, '_posture_confidence', 0.0), 3),
            # N05 (Post-Video Review): per-track posture ledger — số track
            # đang được theo dõi, không dùng để quyết định từng xe (chỉ
            # để health check rằng pipeline đang track đúng).
            "posture_track_ledger_count": (
                self._posture_track_ledger.track_count()
                if hasattr(self, '_posture_track_ledger') else 0
            ),
            # Phase 5 (Task 1): GateEventMatcher status — ghép 2 camera cùng
            # cổng vật lý. Auto-match TẮT mặc định (GATE_MATCHER_ENABLED=0)
            # cho đến khi có calibration + cặp lượt có nhãn.
            "gate_matcher": (self._gate_matcher.status() if hasattr(self, '_gate_matcher') else {"enabled": False}),
            # Phase 6 (Task 1): GPU runtime config + VRAM percentile.
            # sample() throttled ở 1Hz; không gọi nvidia-smi.
            "gpu_runtime": (self._sample_gpu_runtime_snapshot()),
        }

    def _open_webcam(self, gate_config: dict):
        return WebcamStream(
            source=gate_config["source"],
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            loop=gate_config.get("loop", True),
        )

    def _stop_capture(self):
        capture = getattr(self, '_capture', None)
        if capture is not None and not capture.stop():
            return False
        self._capture = None
        return True

    def _start_capture(self):
        if self._webcam is None or not hasattr(self, '_preview_frame_queue'):
            return  # compatibility with manually constructed pipeline tests
        self._capture_seq_base = self._frame_seq
        self._capture_consumed_seq = 0
        epoch = self._source_epoch
        generation = self._run_generation
        def received(packet):
            if epoch != self._source_epoch or generation != self._run_generation:
                return
            raw = packet.image
            h, w = raw.shape[:2]
            scale = min(1., VIDEO_WIDTH/w, VIDEO_HEIGHT/h)
            frame = cv2.resize(raw, (round(w*scale), round(h*scale)), interpolation=cv2.INTER_AREA) if scale < 1 else raw.copy()
            self._last_frame_time = time.time()
            self._fps_capture_window += 1
            self._metrics_capture.add(packet.read_ms)
            if time.monotonic() - getattr(self, '_last_ai_publish', 0.) < .3:
                return  # AI frames with their own aligned boxes are flowing
            item = (epoch, frame, self._capture_seq_base+packet.seq)
            try:
                self._preview_frame_queue.put_nowait(item)
            except queue.Full:
                try:
                    self._preview_frame_queue.get_nowait()
                except queue.Empty:
                    pass
                self._preview_frame_queue.put_nowait(item)
        self._capture = LatestFrameCapture(self._webcam, on_frame=received)
        self._capture.start()

    def _handle_read_error(self, error: BaseException) -> bool:
        """Xử lý lỗi đọc frame từ webcam/capture.

        R2: Tách EOFError (file video kết thúc) khỏi lỗi mạng (RTSP offline).
        EOF kết thúc run ngay, KHÔNG reconnect; lỗi khác đếm consecutive_errors
        và reconnect qua backoff khi đạt ngưỡng.

        Trả về True nếu vòng lặp _run_loop nên tiếp tục (đã sleep backoff),
        False nếu phải break (EOF hoặc _running=False).
        """
        # R2: EOFError → kết thúc run. Trước đây nuốt vào 'processing_error'
        # và reconnect cho cả EOF — sai hành vi với video file ngắn.
        if isinstance(error, EOFError):
            print(f"[Pipeline] {self.gate_id}: video file ended — terminating run: {error}")
            self._diagnostic('camera', 'observed', 'source_eof')
            try:
                self._stop_capture()
            except Exception:
                pass
            self._running = False
            return False
        print(f"[Pipeline] Error in loop: {error}")
        self._diagnostic('camera', 'error', 'processing_error')
        self._consecutive_errors += 1
        if self._consecutive_errors >= self._RECONNECT_AFTER:
            print(f"[Pipeline] {self._consecutive_errors} consecutive read failures — reconnecting camera")
            try:
                if not self._stop_capture():
                    raise RuntimeError('capture reader did not stop')
                self._webcam.release()
            except Exception:
                pass
            try:
                # Same URL reconnect is a new tracking/source session.
                self.camera_switch.request(GATES[self.gate_id]['source'], persist=False)
                self._apply_camera_change()
                print("[Pipeline] Webcam reconnected")
            except Exception as reconnect_err:
                print(f"[Pipeline] Reconnect failed: {reconnect_err}")
            self._consecutive_errors = 0
            # Phase 1: exponential backoff thay vì fixed 2s.
            # Reset về 2s khi reconnect THÀNH CÔNG.
            backoff = min(2.0 * (2 ** (self._reconnect_failures)), 30.0)
            self._reconnect_failures += 1
            time.sleep(backoff)
        else:
            time.sleep(0.1)
        return self._running

    def _run_loop(self):
        """Vòng lặp chính của thread nền."""
        gate_config = GATES.get(self.gate_id, {"source": 0, "loop": True, "name": self.gate_id})
        try:
            self._webcam = self._open_webcam(gate_config)
            self._start_capture()
            print("[Pipeline] Webcam opened")
            self._diagnostic('camera', 'observed', 'camera_connected')
        except Exception as e:
            print(f"[Pipeline] ERROR: Cannot open webcam: {e}")
            self._diagnostic('camera', 'error', 'camera_open_failed')
            # Không thoát: camera RTSP khởi động chậm hơn app, hoặc thiết bị
            # vừa được tiến trình trước nhả ra, sẽ được mở lại ở vòng lặp
            # (trước đây pipeline chết hẳn tới khi khởi động lại app).
            self._webcam = None

        # R2: _consecutive_errors/_RECONNECT_AFTER/_RECONNECT_BACKOFF_SEC đã là
        # instance attributes (xem __init__). Local vars đã xóa để tránh shadow.

        while self._running:
            frame = None
            try:
                # Đợt R: API camera changes take priority over frame read.
                # Đặc biệt — nếu _open_webcam ban đầu thất bại (offline) nhưng
                # có pending camera switch sang nguồn khác, vẫn recover được:
                # thử apply switch ngay trước frame read. Nếu switch thành
                # công → frame mới từ candidate. Nếu thất bại → backoff rồi
                # thử lại (không tight-loop spam).
                if (self.camera_switch is not None
                        and getattr(self.camera_switch, 'has_pending', False)):
                    applied = self._apply_camera_change()
                    if applied:
                        self._consecutive_errors = 0
                    else:
                        # Apply fail — chờ rồi retry ở vòng lặp kế tiếp.
                        time.sleep(self._RECONNECT_BACKOFF_SEC)
                        continue
                # Webcam chưa sẵn sàng (initial open thất bại, đợi switch) →
                # backoff rồi quay lại đầu vòng lặp.
                if self._webcam is None:
                    time.sleep(self._RECONNECT_BACKOFF_SEC)
                    if self._running:
                        try:
                            self._webcam = self._open_webcam(GATES.get(self.gate_id, gate_config))
                            self._start_capture()
                            print("[Pipeline] Webcam opened (retry)")
                            self._diagnostic('camera', 'observed', 'camera_connected')
                        except Exception:
                            self._webcam = None
                    continue
                # Đọc frame
                t_read_start = time.perf_counter()
                native_reader = getattr(type(self._webcam), 'read_source_frame', None)
                if getattr(self, '_capture', None) is not None:
                    packet = self._capture.read_latest(after=self._capture_consumed_seq)
                    self._capture_consumed_seq = packet.seq
                    self._frame_seq = self._capture_seq_base+packet.seq-1
                    raw = packet.image
                else:
                    raw = self._webcam.read_source_frame() if callable(native_reader) else self._webcam.read_frame()
                self._original_source_frame = raw
                raw_h, raw_w = raw.shape[:2]
                scale = min(1., VIDEO_WIDTH/raw_w, VIDEO_HEIGHT/raw_h)
                frame = cv2.resize(raw, (round(raw_w*scale), round(raw_h*scale)), interpolation=cv2.INTER_AREA) if scale < 1 else raw.copy()
                source_frame = frame.copy()
                self._frame_seq += 1
                self._consecutive_errors = 0
                self._frame_count += 1
                self._last_frame_time = time.time()
                # Phase 0: capture latency chỉ tính phần cv2 read+resize, không
                # gồm detect (tách ở buffer riêng).
                if getattr(self, '_capture', None) is None:
                    self._metrics_capture.add((time.perf_counter() - t_read_start) * 1000)

                # F02 (Task 1): publish JPEG NGAY SAU khi đọc frame xong, TRƯỚC
                # mọi detect/pose/OCR/DB. Trước đây JPEG publish nằm trong
                # `finally` của try/except → viewer nhận ảnh mới chỉ SAU khi
                # R1 (Task 1): Thay vì encode ngay trong main loop (block),
                # push frame vào preview queue để thread preview encode riêng.
                # Main loop KHÔNG chờ encode. Queue size=2 → drop oldest if full.
                try:
                    if getattr(self, '_capture', None) is None:
                        self._preview_frame_queue.put_nowait((frame.copy(), self._frame_seq))
                except Exception:
                    # Queue full — drop oldest frame (don't block main loop)
                    try:
                        self._preview_frame_queue.get_nowait()
                        self._preview_frame_queue.put_nowait((frame.copy(), self._frame_seq))
                    except Exception:
                        pass

                # Đợt 2, Bước 7: push frame vào continuous recorder NGAY SAU read_frame,
                # TRƯỚC mọi early-return (FRAME_SKIP, no-person, ...). Đây là điểm mấu
                # chốt: continuous recording phải ghi MỌI frame đọc được, kể cả frame bị
                # skip hay không có người — khác hẳn _clip_buffer (chỉ append ở nhánh đã
                # qua detect đầy đủ). 2 cơ chế ghi hình độc lập, không dùng chung buffer.
                if self._recorder is not None:
                    self._recorder.push_frame(frame)

                # Xử lý cách frame
                if self._frame_count % FRAME_SKIP != 0:
                    # Vẽ box từ cache (kết quả detect gần nhất) lên frame hiện tại
                    for det in self._last_helmet_dets:
                        self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)
                    for det in self._last_plate_dets:
                        self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)
                    for det in self._last_person_dets:
                        self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)
                    for keypoints, offset in self._last_pose_data:
                        self._draw_pose_keypoints(frame, keypoints, offset=offset)
                    self._draw_roi(frame)
                    if DEBUG_CROSSING:
                        self._draw_crossing_line_debug(frame)
                    with self._lock:
                        self._latest_frame = frame
                    continue

                # Resize nhỏ CHỈ để detect (giữ tốc độ), sau đó quy đổi bbox kết
                # quả về tọa độ ảnh gốc (frame, VIDEO_WIDTH/HEIGHT) — mọi bước sau
                # (OCR, vẽ box, lưu snapshot) đều dùng ảnh gốc nét hơn, không mất
                # tốc độ detect vì detect vẫn chạy trên ảnh nhỏ như cũ.
                t0 = time.perf_counter()
                frame_h, frame_w = frame.shape[:2]
                detect_scale = min(DETECT_WIDTH/frame_w, DETECT_HEIGHT/frame_h)
                detect_frame = cv2.resize(frame, (max(1, round(frame_w*detect_scale)), max(1, round(frame_h*detect_scale))))
                scale_x = frame_w / detect_frame.shape[1]
                scale_y = frame_h / detect_frame.shape[0]
                self._roi_polygon_px = to_pixel_polygon(self._roi_points, frame_w, frame_h)

                # Chạy person/helmet/plate song song (3 luồng) thay vì tuần tự —
                # cả 3 chỉ cần đúng 1 input là detect_frame, không phụ thuộc lẫn
                # nhau, nên chạy cùng lúc không mất gì ngoài chút CPU thừa ở frame
                # không có người (kết quả helmet/plate lúc đó bị bỏ qua như cũ).
                #
                # F01 (Task 1): dispatch theo capability thực — KHÔNG submit Future
                # cho detector=None (rear/ocr_only: _person_detector=None;
                # minimal: _helmet_detector=None, _plate_detector=None, _person_detector=None).
                # Trước đây: `self._person_detector.detect_tracked(...)` ở rear →
                # AttributeError 'NoneType object has no attribute detect_tracked'.
                # Phase 3 mới: skip-submit + Future() set_result([]) cho detector
                # không load, _detect_pool=None (minimal) thì KHÔNG submit gì cả.
                t_detect_start = time.perf_counter()
                person_future = None
                helmet_future = None
                plate_future = None
                if self._person_detector is not None and self._detect_pool is not None:
                    person_future = self._detect_pool.submit(self._person_detector.detect_tracked, detect_frame)
                else:
                    # Profile ocr_only/minimal: không có person detector.
                    # Khởi tạo Future đã-resolved [] để downstream code vẫn
                    # dùng được .result() mà không phải branch nhiều chỗ.
                    person_future = Future()
                    person_future.set_result([])
                if self._helmet_detector is not None and self._detect_pool is not None:
                    helmet_future = self._detect_pool.submit(self._helmet_detector.detect, detect_frame)
                else:
                    helmet_future = Future()
                    helmet_future.set_result([])
                if self._plate_detector is not None and self._detect_pool is not None:
                    reader = self._plate_detector.detect_tracked if getattr(self, 'profile', 'full') == 'ocr_only' else self._plate_detector.detect
                    plate_future = self._detect_pool.submit(reader, detect_frame)
                else:
                    plate_future = Future()
                    plate_future.set_result([])

                raw_person_dets = self._rescale_dets(person_future.result(), scale_x, scale_y)
                # Phase 0: detect latency = wall-time từ submit 3 future đến khi
                # .result() của cái cuối cùng về — đo TOÀN BỘ song song, không
                # phải tổng tuần tự.
                person_dets = [d for d in raw_person_dets if d.class_name.lower() == 'person']
                vehicle_dets = [d for d in raw_person_dets if d.class_name.lower() in ('motorcycle', 'bicycle')]
                helmet_dets = [d for d in self._rescale_dets(helmet_future.result(), scale_x, scale_y)
                               if d.class_name != 'Without Helmet' or d.confidence >= HELMET_NO_HELMET_MIN_CONF]
                plate_dets = self._rescale_dets(plate_future.result(), scale_x, scale_y)
                self._metrics_detect.add((time.perf_counter() - t_detect_start) * 1000)
                self._fps_ai_window += 1
                if not plate_dets:
                    plate_dets = self._scan_plate_region(source_frame, vehicle_dets, person_dets)
                raw_people = list(person_dets)
                raw_count = len(person_dets)+len(vehicle_dets)+len(helmet_dets)+len(plate_dets)

                # Vùng nhận diện (ROI): loại bỏ mọi detection có tâm ngoài vùng đã
                # cấu hình — lọc CẢ helmet/plate (không chỉ person/vehicle), nếu
                # không chúng vẫn được vẽ lên frame ngoài vùng dù không gán được
                # vào person nào (gây cảm giác "vẫn nhận diện ngoài vùng").
                if self._roi_polygon_px is not None:
                    person_dets = filter_by_roi(person_dets, self._roi_polygon_px)
                    vehicle_dets = filter_by_roi(vehicle_dets, self._roi_polygon_px)
                    helmet_dets = filter_by_roi(helmet_dets, self._roi_polygon_px)
                    plate_dets = filter_by_roi(plate_dets, self._roi_polygon_px)
                for person in raw_people:
                    if not any(person is d for d in person_dets):
                        self._diagnostic('roi', 'review', 'outside_roi', getattr(person, 'track_id', None), objects=['person'])
                self._diagnostic('detect', 'observed', 'objects_detected' if person_dets or vehicle_dets or helmet_dets or plate_dets else 'no_objects',
                    objects={'person': len(person_dets), 'vehicle': len(vehicle_dets), 'helmet': len(helmet_dets),
                             'plate': len(plate_dets), 'excluded_by_roi': raw_count-len(person_dets)-len(vehicle_dets)-len(helmet_dets)-len(plate_dets)})
                if getattr(self, '_helmet_health', {}).get('status') == 'error':
                    self._diagnostic('model', 'error', self._helmet_health['reason'])

                # Publish the completed boxes even when only a vehicle/plate is visible.
                preview_dets = tuple((d, COLOR_PERSON, COLOR_PERSON) for d in person_dets+vehicle_dets)
                preview_dets += tuple((d, COLOR_PLATE, COLOR_PLATE) for d in plate_dets)
                self._preview_overlay = (self._source_epoch, time.monotonic(), preview_dets)
                if not person_dets:
                    self._publish_ai_frame(source_frame, preview_dets)

                # Không có person nào → bỏ qua toàn bộ frame (helmet/plate detect
                # phía trên vẫn chạy xong nhưng kết quả không dùng tới, chấp nhận
                # được vì tổng thời gian không tăng — chạy song song mà).
                if not person_dets:
                    if plate_dets:
                        self._diagnostic('ocr', 'review', 'person_not_associated')
                        # N02 (Post-Video Review): rear/ocr_only profile hoặc
                        # camera chỉ thấy biển không có người vẫn phải OCR +
                        # consensus. Tạo track_id tạm theo bbox centroid
                        # để BestPlateStore + PlateConsensus xử lý độc lập
                        # với group-by-person. Không gánhọc sinh.
                        self._observe_plate_only(source_frame, plate_dets)
                    self._draw_roi(frame)
                    if DEBUG_CROSSING:
                        self._draw_crossing_line_debug(frame)
                    with self._lock:
                        self._latest_frame = frame
                    continue

                # Update detection timestamp (health monitoring)
                self._last_detection_time = time.time()

                # Gom helmet + plate + loại phương tiện vào từng nhóm theo person.
                # matched_helmet_dets: chỉ helmet nằm trong vùng đầu của 1 person
                # cụ thể — dùng để VẼ, loại trừ detection lạc (gương xe, tay lái...)
                groups, matched_helmet_dets = self._group_by_person(person_dets, helmet_dets, plate_dets, vehicle_dets)
                associated_plates = {id(d) for group in groups for d in group.get('plate_dets', [])}
                unassociated_plates = [d for d in plate_dets if id(d) not in associated_plates]
                if unassociated_plates:
                    self._observe_plate_only(source_frame, unassociated_plates)
                self._preview_overlay = (self._source_epoch, time.monotonic(), preview_dets +
                    tuple((d, COLOR_HELMET, COLOR_NO_HELMET) for d in matched_helmet_dets))
                self._publish_ai_frame(source_frame, self._preview_overlay[2])

                # Cập nhật cache để nhánh skip vẽ box mượt — helmet dùng bản đã
                # lọc theo vùng đầu (matched_helmet_dets), không dùng raw helmet_dets
                self._last_person_dets = person_dets
                self._last_helmet_dets = matched_helmet_dets
                self._last_plate_dets = plate_dets

                # Gồm cả vehicle_track_id — _instant_alerted_tracks/_midline_track_state
                # giờ key theo xe (vehicle_track_id) khi có, không chỉ theo người.
                active_tracks = {g.get('track_id') for g in groups} | {g.get('vehicle_track_id') for g in groups}
                # Track nào không còn trong khung thì bỏ khỏi set "đã nhắc" —
                # lượt sau track_id này xuất hiện lại (xe mới) sẽ được nhắc lại.
                self._instant_alerted_tracks &= active_tracks
                if self._midline_track_state:
                    self._midline_track_state = {k: v for k, v in self._midline_track_state.items()
                                                  if k in active_tracks}
                for tid, future in list(self._ocr_pending.items()):
                    owner = -tid-1 if tid is not None and tid < 0 else tid
                    if owner not in active_tracks and future.done():
                        self._ocr_consume_pending(tid)

                # Quan sát tỉ lệ người đi bộ / người đi xe (xem comment ở __init__)
                for group in groups:
                    if group.get('vehicle_type') is None:
                        self._pedestrian_count += 1
                    else:
                        self._rider_count += 1

                # Đếm số người/xe — đánh dấu chở quá số người quy định
                self._count_riders_per_vehicle(groups)

                # Phát hiện tư thế cho mỗi person box — ISOLATED try/except
                groups = self._run_posture_detection(frame, groups)

                # Xe chở 2+ người tạo 2+ group (1 group/person) CÙNG trỏ vào 1
                # _vehicle — chỉ 1 người "đại diện" (track_id nhỏ nhất, ổn định
                # xuyên frame) được tính RIDING_THROUGH_GATE/TOO_MANY_RIDERS/
                # PLATE_NOT_REGISTERED (lỗi thuộc về XE) để tránh ghi 2 dòng
                # DB/bắn 2 alert cho 1 lần xe qua cổng. NO_HELMET vẫn xét riêng
                # từng người — mũ là chuyện của từng người, không phải của xe.
                riders_by_vehicle: dict = {}
                for g in groups:
                    vtid, ptid = g.get('vehicle_track_id'), g.get('track_id')
                    if vtid is None or ptid is None:
                        continue
                    riders_by_vehicle.setdefault(vtid, []).append(ptid)
                primary_track_by_vehicle = {vtid: min(ptids) for vtid, ptids in riders_by_vehicle.items()}
                # Gắn rider/passenger rõ ràng vào từng group cùng xe — rider =
                # người đại diện (primary), passenger = những người CÒN LẠI
                # cùng xe đó. person_count đếm cả rider.
                for g in groups:
                    vtid = g.get('vehicle_track_id')
                    if vtid is None:
                        continue
                    ptids = riders_by_vehicle.get(vtid, [])
                    rider_tid = primary_track_by_vehicle.get(vtid)
                    g['rider_track_id'] = rider_tid
                    g['passenger_track_ids'] = [t for t in ptids if t != rider_tid]
                    g['person_count'] = len(ptids)

                # Xử lý vi phạm cho TỪNG nhóm riêng biệt — bỏ qua nhóm mà xe (hoặc
                # người, nếu không có xe khớp) còn chạm mép khung hình, tức có thể
                # chưa vào/đang ra hết khung → chưa đủ căn cứ kết luận (đặc biệt
                # NO_PLATE/PLATE_OBSCURED: biển số có thể chỉ chưa kịp lọt vào khung).
                for group in groups:
                    self._observe_group(source_frame, group)
                    # Crossing updates once per new vehicle frame. Modules
                    # contribute evidence; only the sealed vehicle event can
                    # request audio after mandatory evidence has been saved.
                    self._update_crossing(group, frame_w, frame_h)
                    if DEBUG_CROSSING:
                        self._draw_crossing_debug(frame, group, frame_w, frame_h)
                self._process_vehicle_crossings(source_frame, groups)

                # Vẽ box helmet — chỉ những helmet đã khớp vùng đầu 1 person
                # (matched_helmet_dets), không vẽ raw helmet_dets để tránh vẽ
                # nhầm lên gương/tay lái xe máy khi detector false-positive.
                for det in matched_helmet_dets:
                    self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)

                # Vẽ box plate (theo nhóm)
                for det in plate_dets:
                    self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)

                # Vẽ box person (cam) — SAU khi OCR đã xong
                for det in person_dets:
                    self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)

                self._draw_roi(frame)
                if DEBUG_CROSSING:
                    self._draw_crossing_line_debug(frame)

                # Feature 7: record frame timing + Feature 4: buffer frame for clip
                self._frame_timestamps.append(time.time())
                # Phase 0: AI FPS = số frame ĐÃ QUA detect/giây. Capture FPS
                # đếm ở đầu loop. Cả 2 đều cập nhật theo interval 1s để tránh
                # chia cho 0 và phản ánh thực tế.
                if getattr(self, '_capture', None) is None:
                    self._fps_capture_window += 1
                self._resource_sampler.update()
                # Resize down before buffering to save RAM (640x360 = ~1/4 of 1280x720)
                small = cv2.resize(frame, (640, 360))
                self._clip_buffer.append(small)
                self._last_process_latency_ms = (time.perf_counter() - t0) * 1000

                # Lưu frame đã vẽ
                with self._lock:
                    self._latest_frame = frame

            except Exception as e:
                if not self._handle_read_error(e):
                    # EOFError hoặc _running đã False → break.
                    break
                # else: tiếp tục vòng lặp (đã sleep backoff trong handler)
                continue
            else:
                # Reset reconnect_failures + backoff khi read THÀNH CÔNG.
                if self._reconnect_failures:
                    self._reconnect_failures = 0
            finally:
                # F02 (Task 1): JPEG đã publish ngay sau read_frame — không
                # publish lại ở finally (AI không được giữ khóa frame qua
                # inference). finally giữ để cập nhật FPS theo interval.
                self._maybe_update_fps()

        # Cleanup
        self._stop_capture()
        if self._webcam:
            self._webcam.release()
            print("[Pipeline] Webcam released")

    @staticmethod
    def _rescale_dets(dets: list, scale_x: float, scale_y: float) -> list:
        """Quy đổi bbox từ tọa độ ảnh detect (nhỏ) về tọa độ ảnh gốc (to hơn)."""
        rescaled = []
        for d in dets:
            x1, y1, x2, y2 = d.bbox
            rescaled.append(Detection(
                class_name=d.class_name,
                confidence=d.confidence,
                bbox=(round(x1 * scale_x), round(y1 * scale_y), round(x2 * scale_x), round(y2 * scale_y)),
                track_id=getattr(d, 'track_id', None),
            ))
        return rescaled

    def _draw_detection(self, frame: np.ndarray, det: Detection,
                       color_if_positive: tuple, color_if_negative: tuple):
        """Vẽ bounding box và nhãn lên frame."""
        x1, y1, x2, y2 = det.bbox

        # Chọn màu dựa trên class name
        if 'helmet' in det.class_name.lower() and 'without' in det.class_name.lower():
            color = color_if_negative
            label = "No Helmet"
        elif 'helmet' in det.class_name.lower():
            color = color_if_positive
            label = "With Helmet"
        elif 'license' in det.class_name.lower() or 'plate' in det.class_name.lower():
            color = color_if_positive
            label = "License Plate"
        else:
            color = color_if_positive
            label = det.class_name

        # Vẽ rectangle
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, THICKNESS)

        # Vẽ nhãn
        conf_text = f"{det.confidence:.0%}"
        text = f"{label} {conf_text}"

        # Background cho text
        (text_w, text_h), _ = cv2.getTextSize(text, FONT, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - text_h - 4), (x1 + text_w, y1), color, -1)

        # Text
        cv2.putText(frame, text, (x1, y1 - 2), FONT, 0.5, (255, 255, 255), 1)

    def _draw_roi(self, frame: np.ndarray):
        """Vẽ viền vùng ROI đang áp dụng (nếu có cấu hình) — không tô nền,
        chỉ để bảo vệ/admin thấy trực quan vùng đang lọc detect."""
        if self._roi_polygon_px is None:
            return
        cv2.polylines(frame, [self._roi_polygon_px], isClosed=True, color=(0, 200, 255), thickness=2)

    def _draw_crossing_line_debug(self, frame: np.ndarray) -> None:
        """DEBUG_CROSSING=1: vẽ vạch mốc + dead-zone 2 bên + nhãn SIDE A/SIDE
        B — để biết chính xác vạch đang nằm ở đâu trên camera thật. ROI và
        vạch mốc là 2 khái niệm RIÊNG (xem docstring crossing.py) — hàm này
        chỉ vẽ vạch, không liên quan gì tới polygon ROI."""
        detector = getattr(self, '_crossing_detector', None)
        if detector is None or not detector.is_configured:
            return
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = detector.gate_line
        p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
        cv2.line(frame, p1, p2, (0, 0, 255), 2, cv2.LINE_AA)
        # Dead-zone: lệch vuông góc với line 1 khoảng = edge_margin * đường chéo.
        dx, dy = (x2 - x1) * w, (y2 - y1) * h
        length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        nx, ny = -dy / length, dx / length
        margin_px = detector.edge_margin * (w * w + h * h) ** 0.5
        for sign, label in ((-1, 'SIDE A'), (1, 'SIDE B')):
            off = (int(nx * margin_px * sign), int(ny * margin_px * sign))
            offset_p1 = (p1[0] + off[0], p1[1] + off[1])
            offset_p2 = (p2[0] + off[0], p2[1] + off[1])
            cv2.line(frame, offset_p1, offset_p2, (0, 160, 255), 1, cv2.LINE_AA)
            label_pt = (offset_p2[0] - 70, offset_p2[1] - 6 if sign < 0 else offset_p2[1] + 16)
            cv2.putText(frame, label, label_pt, FONT, 0.5, (0, 160, 255), 1, cv2.LINE_AA)

    def _draw_crossing_debug(self, frame: np.ndarray, group: dict, frame_w: int, frame_h: int) -> None:
        """DEBUG_CROSSING=1: chấm tại vehicle_anchor + side/khoảng cách/state
        của xe này — để tune vị trí vạch trên camera thật."""
        from app.cv.crossing import vehicle_anchor, _signed_side_and_projection
        vehicle = group.get('_vehicle')
        detector = getattr(self, '_crossing_detector', None)
        if vehicle is None or detector is None or not detector.is_configured:
            return
        tid = group.get('vehicle_track_id') or group.get('track_id')
        if tid is None:
            return
        ax, ay = vehicle_anchor(vehicle.bbox)
        cv2.circle(frame, (int(ax), int(ay)), 5, (0, 0, 255), -1, cv2.LINE_AA)
        x1, y1, x2, y2 = detector.gate_line
        dist, _, _ = _signed_side_and_projection(ax / frame_w, ay / frame_h, x1, y1, x2, y2)
        state_obj = detector._tracks.get(tid)
        if state_obj is None:
            side_label, state = '?', 'NEW'
        else:
            side_label = {-1: 'A', 0: '?', 1: 'B'}.get(state_obj.stable_side, '?')
            state = 'CROSSED' if state_obj.crossing_latched else \
                ('REARMED' if state_obj.has_crossed else 'PRE_CROSS')
        text = f"V{tid} side={side_label} dist={dist:+.3f} {state}"
        cv2.putText(frame, text, (int(ax) + 8, int(ay) - 8), FONT, 0.42, (0, 0, 255), 1, cv2.LINE_AA)

    @staticmethod
    def _vertical_overlap(box_a: tuple, box_b: tuple) -> bool:
        """True nếu 2 bbox có chồng lấp trục Y (không nhất thiết chồng X).

        Dùng để lọc bớt trường hợp gán nhầm người đi bộ đứng/đi ngang qua thành
        "người đang ngồi trên xe" chỉ vì tình cờ gần nhau theo trục X — người
        thật sự ngồi trên xe luôn có box chồng lấp trục Y đáng kể với xe (phần
        chân/thân ở khoảng cùng độ cao với xe), khác với người đi bộ ở xa hơn/gần
        hơn camera (khác "độ sâu" nên khác dải Y dù trùng X do phối cảnh).
        """
        _, ay1, _, ay2 = box_a
        _, by1, _, by2 = box_b
        return max(ay1, by1) <= min(ay2, by2)

    def _group_by_person(self, person_dets, helmet_dets, plate_dets, vehicle_dets):
        """Keep track identity and reject ambiguous spatial associations.

        Trả về (groups, matched_helmet_dets) — matched_helmet_dets chỉ gồm
        helmet detection nào khớp đúng 1 vùng đầu của 1 person (xem vòng lặp
        helmet bên dưới). Helmet không khớp vùng đầu nào (vd: detector nhận
        nhầm gương/tay lái xe máy thành mũ bảo hiểm) bị loại khỏi danh sách
        này — gọi nơi khác dùng list này để VẼ, tránh vẽ box sai vị trí lên
        gương xe thay vì đầu người.
        """
        groups = []
        for person in person_dets:
            x1, y1, x2, y2 = person.bbox
            cx = (x1+x2)/2
            candidates = [(abs((v.bbox[0]+v.bbox[2])/2-cx), v) for v in vehicle_dets
                          if x1 <= v.bbox[2] and x2 >= v.bbox[0]
                          and self._vertical_overlap(person.bbox, v.bbox)]
            candidates.sort(key=lambda pair: pair[0])
            ambiguous = len(candidates)>1 and candidates[1][0]-candidates[0][0] <= .1*(x2-x1)
            vehicle = candidates[0][1] if candidates and not ambiguous else None
            vehicle_type = vehicle.class_name.lower() if vehicle else None
            vtid = getattr(vehicle, 'track_id', None)
            if vtid is not None:
                # A tracked bike once seen as a motorcycle stays one; COCO
                # rarely calls a real bicycle a motorcycle, the reverse is common.
                seen = getattr(self, '_motorcycle_tracks', None)
                if seen is None:
                    seen = self._motorcycle_tracks = OrderedDict()
                if vehicle_type == 'motorcycle':
                    seen[vtid] = True
                    seen.move_to_end(vtid)
                    while len(seen) > 512:
                        seen.popitem(last=False)
                elif vtid in seen:
                    vehicle_type = 'motorcycle'
            groups.append({'_person': person, '_vehicle': vehicle,
                'track_id': getattr(person, 'track_id', None),
                'vehicle_track_id': vtid,
                'vehicle_type': vehicle_type,
                'helmet_dets': [], 'plate_dets': [], 'posture_status': 'unknown',
                'association_reasons': ['vehicle_association_ambiguous'] if ambiguous else []})
        matched_helmet_dets = []
        for helmet in helmet_dets:
            hx1,hy1,hx2,hy2 = helmet.bbox
            cx,cy=(hx1+hx2)/2,(hy1+hy2)/2
            matches = [g for g in groups if g['_person'].bbox[0] <= cx <= g['_person'].bbox[2]
                       and g['_person'].bbox[1]-.15*(g['_person'].bbox[3]-g['_person'].bbox[1]) <= cy <= g['_person'].bbox[1]+.4*(g['_person'].bbox[3]-g['_person'].bbox[1])]
            if len(matches)==1:
                matches[0]['helmet_dets'].append(helmet)
                matched_helmet_dets.append(helmet)
            elif len(matches)>1:
                for g in matches: g['association_reasons'].append('helmet_association_ambiguous')
            # len(matches)==0: helmet không nằm trong vùng đầu của bất kỳ person
            # nào đang có trong khung (vd: gương xe máy) — loại khỏi kết quả,
            # không gán vào group nào và không nằm trong matched_helmet_dets.
        for plate in plate_dets:
            px1,py1,px2,py2 = plate.bbox
            cx,cy=(px1+px2)/2,(py1+py2)/2
            vehicles=[]
            for v in vehicle_dets:
                x1,y1,x2,y2=v.bbox
                pad_x,pad_y=.1*(x2-x1),.1*(y2-y1)
                if x1-pad_x<=cx<=x2+pad_x and y1-pad_y<=cy<=y2+pad_y:
                    vehicles.append(v)
            matches=[g for g in groups if g['_vehicle'] is not None and
                     any(g['_vehicle'] is v for v in vehicles)]
            if len(vehicles)==1:
                for g in matches:g['plate_dets'].append(plate)
            elif len(vehicles)>1:
                for g in matches:g['association_reasons'].append('plate_association_ambiguous')
            if not vehicles:
                # Preview only: lower person region, exactly one candidate.
                nearby = [g for g in groups if g['_person'].bbox[0] <= cx <= g['_person'].bbox[2]
                          and (g['_person'].bbox[1]+g['_person'].bbox[3])/2 <= cy <= g['_person'].bbox[3]]
                if len(nearby) == 1:
                    g = nearby[0]
                    if g.get('_preview_plate') is None and 'plate_association_ambiguous' not in g['association_reasons']:
                        g['_preview_plate'] = plate
                    else:
                        g.pop('_preview_plate', None)
                        g['association_reasons'].append('plate_association_ambiguous')
                elif len(nearby) > 1:
                    for g in nearby:
                        g.pop('_preview_plate', None)
                        g['association_reasons'].append('plate_association_ambiguous')
        return groups, matched_helmet_dets

    def _count_riders_per_vehicle(self, groups: list) -> None:
        """
        Đếm số người khớp cùng 1 xe máy — xe nào vượt quá MAX_RIDERS_PER_MOTORCYCLE
        thì đánh dấu 'too_many_riders'=True cho mọi group thuộc xe đó (sửa tại chỗ).
        Người đi bộ (group['_vehicle'] is None) không tính.
        """
        buckets: dict[tuple, list[dict]] = {}
        for group in groups:
            vehicle = group.get('_vehicle')
            if vehicle is None:
                continue
            buckets.setdefault(vehicle.bbox, []).append(group)

        for riders in buckets.values():
            if len(riders) > MAX_RIDERS_PER_MOTORCYCLE:
                for g in riders:
                    g['too_many_riders'] = True

    @staticmethod
    def _make_crossing_detector(gate_line):
        from app.cv.crossing import CrossingDetector
        # Without a drawn line no vehicle ever crosses, so no violation or
        # alert is ever raised; a fresh demo DB would stay silent.
        return CrossingDetector(
            list(gate_line or _DEFAULT_GATE_LINE),
            edge_margin=CROSSING_EDGE_MARGIN,
            min_frames_per_side=CROSSING_MIN_FRAMES_PER_SIDE,
            rearm_distance=CROSSING_REARM_DISTANCE,
            cooldown_sec=CROSSING_COOLDOWN_SEC,
            allowed_direction=CROSSING_ALLOWED_DIRECTION,
            min_frames_exit_side=CROSSING_MIN_FRAMES_EXIT_SIDE,
            max_transition_sec=CROSSING_MAX_TRANSITION_SEC,
        )

    def set_gate_line(self, line):
        self._crossing_detector = self._make_crossing_detector(line)
        self._midline_track_state.clear()
        self._instant_alerted_tracks.clear()

    def _update_crossing(self, group, frame_w, frame_h):
        from app.cv.crossing import vehicle_anchor
        detector = getattr(self, '_crossing_detector', None)
        vehicle = group.get('_vehicle')
        # Key theo vehicle_track_id (fallback: person track_id nếu ByteTrack
        # chưa confirm track xe) — xe chở 2 người tạo 2 group/frame CÙNG trỏ
        # 1 _vehicle; key theo xe thay vì người để cả 2 group chia sẻ đúng 1
        # lịch sử crossing. detector.update() tự bỏ qua lần gọi thứ 2 trong
        # cùng frame_seq (xem CrossingDetector.update), nên gọi 2 lần/frame
        # cho cùng key vẫn an toàn, không cần cache riêng ở đây.
        tid = group.get('vehicle_track_id') or group.get('track_id')
        if detector is None or tid is None or vehicle is None:
            return False
        ax, ay = vehicle_anchor(vehicle.bbox)
        detector.update(tid, ax/frame_w, ay/frame_h,
                        time.monotonic(), frame_seq=self._frame_seq,
                        frame_size=(frame_w, frame_h))
        hist = detector._tracks.get(tid)
        # Crossing stays valid for this encounter while the issue ledger confirms.
        return bool(hist and hist.has_crossed)

    def _check_instant_gate_alert(self, group, frame_w, frame_h, crossed_gate):
        """Phát cảnh báo loa NGAY khi xe vừa chạm/cán qua vạch mốc (gate_line
        admin cấu hình, hoặc vạch giữa khung hình nếu chưa cấu hình) — không
        chờ evidence ledger/CrossingDetector chính thức gom 3+3 frame ổn định
        rồi mới phát (vẫn cần cho quyết định vi phạm chính xác ở
        _process_violations, không đổi gì ở đó). Đây CHỈ là tín hiệu nhắc nhở
        sớm một chiều — bắn ngay ở FRAME ĐẦU TIÊN phát hiện xe đổi phía so với
        vạch, độ trễ tối thiểu có thể có (1 frame). Mỗi track chỉ bắn 1 lần.
        `crossed_gate` không dùng ở đây nữa (giữ tham số để lời gọi không đổi)
        — xem _check_instant_line_crossing. Key theo vehicle_track_id (không
        phải person track_id) — xe chở 2 người mới chỉ bắn 1 lần cho CẢ xe,
        không phải 1 lần/người.
        """
        tid = group.get('vehicle_track_id') or group.get('track_id')
        if tid is None or tid in self._instant_alerted_tracks:
            return
        main_detector = getattr(self, '_crossing_detector', None)
        line = (main_detector.gate_line if main_detector is not None and main_detector.is_configured
                else _DEFAULT_GATE_LINE)
        if self._check_instant_line_crossing(group, frame_w, frame_h, line, tid):
            self._instant_alerted_tracks.add(tid)
            self._push_instant_gate_alert(tid)

    def _check_instant_line_crossing(self, group, frame_w, frame_h, line, tid) -> bool:
        """True ở ĐÚNG frame xe đổi phía so với `line` ([x1,y1,x2,y2] chuẩn
        hóa [0,1]) — không debounce/streak, chỉ so phía hiện tại với phía ghi
        nhận gần nhất của `tid` (1 giá trị/track, không list lịch sử, không
        dict comprehension mỗi frame) — rẻ hơn cả bản streak trước và phản hồi
        loa nhanh nhất có thể mà vẫn đúng (cần tối thiểu 1 quan sát trước đó để
        biết "đổi phía" nghĩa là gì). Dùng chung vehicle_anchor()/get_line_side()
        với CrossingDetector chính thức — cùng 1 điểm neo (bottom-center bbox),
        cùng quy tắc "trong đoạn P1-P2", chỉ khác là KHÔNG yêu cầu phía trước
        phải ổn định nhiều frame (chấp nhận nhạy hơn vì chỉ là tiếng nhắc)."""
        from app.cv.crossing import vehicle_anchor, get_line_side
        vehicle = group.get('_vehicle')
        if vehicle is None or tid is None:
            return False
        ax, ay = vehicle_anchor(vehicle.bbox)
        cx, cy = ax / frame_w, ay / frame_h
        lx1, ly1, lx2, ly2 = line
        side = get_line_side((cx, cy), (lx1, ly1), (lx2, ly2), deadzone=CROSSING_EDGE_MARGIN)
        if side == 0:
            return False  # dead-zone hoặc ngoài đoạn P1-P2 — chưa quan sát được phía
        last_side = self._midline_track_state.get(tid)
        self._midline_track_state[tid] = side
        return last_side is not None and last_side != side

    def _push_instant_gate_alert(self, track_id):
        """Đẩy cảnh báo 'gate_crossed' vào hàng đợi alert sẵn có — tái dùng
        nguyên cơ chế thread-safe queue.Queue → /guard/ws đã có cho violation,
        không cần thêm transport mới."""
        message = {
            'type': 'gate_crossed',
            'track_id': track_id,
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            self._alert_queue.put_nowait(message)
        except queue.Full:
            try:
                self._alert_queue.get_nowait()
                self._alert_queue.put_nowait(message)
            except queue.Empty:
                pass

    @staticmethod
    def _is_touching_frame_edge(bbox: tuple, frame_w: int, frame_h: int) -> bool:
        """True nếu bbox còn chạm mép khung hình (chưa vào/đang ra hết khung).

        Không có tracker theo dõi vật thể qua nhiều frame, nên đây là tín hiệu
        rẻ tiền nhất để biết "vật thể có khả năng chưa vào hết khung" — tránh
        đánh giá vi phạm (và chụp snapshot) khi biển số/người còn bị cắt cụt ở
        rìa ảnh. Nhược điểm đã biết: xe dừng hẳn sát mép khung sẽ không bao giờ
        được đánh giá — chấp nhận được vì camera cổng trường luôn có luồng xe
        di chuyển qua, không phải điểm dừng cố định.
        """
        x1, y1, x2, y2 = bbox
        margin_x = frame_w * FRAME_EDGE_MARGIN_RATIO
        margin_y = frame_h * FRAME_EDGE_MARGIN_RATIO
        return x1 <= margin_x or x2 >= frame_w - margin_x or y1 <= margin_y or y2 >= frame_h - margin_y

    def _process_vehicle_crossings(self, frame, groups):
        """Live path: gather all riders, seal only at a vehicle crossing."""
        from app.cv.evidence import ErrorSample
        from app.config import ALERT_MAX_PLATE_WAIT_MS
        from copy import deepcopy
        ledger = getattr(self, '_evidence_ledger', None)
        if ledger is None:
            return
        now = time.time()
        buckets = {}
        for group in groups:
            tid = group.get('vehicle_track_id')
            # COCO labels a motorbike "bicycle" in up to half of night/close
            # frames and cannot tell an e-bike from a bicycle; the gate rules
            # (walk through, helmet, rider count) apply to every two-wheeler.
            if (tid is not None and group.get('vehicle_type') in ('motorcycle', 'bicycle')
                    and group.get('_vehicle') is not None):
                buckets.setdefault(tid, []).append(group)
        for key, future in list(getattr(self, '_crossing_jobs', {}).items()):
            if future.done():
                self._crossing_jobs.pop(key)
                try:
                    if not future.result():
                        self._io_health['errors'] += 1
                except Exception:
                    self._io_health['errors'] += 1
        ledger.prune_expired(now, grace_period_sec=60)
        for tid, riders in buckets.items():
            issues = []
            for group in riders:
                ptid = group.get('track_id')
                if ptid is None:
                    continue
                yes = any(d.class_name == 'With Helmet' for d in group['helmet_dets'])
                no = any(d.class_name == 'Without Helmet' for d in group['helmet_dets'])
                riding = group.get('posture_status') == 'riding'
                label = 'positive' if riding and no and not yes else 'negative' if riding and yes and not no else 'unknown'
                person_key = (tid, ptid)
                decision = ledger.update(person_key, 'NO_HELMET', ErrorSample(label, self._frame_seq, now), now)
                if ledger.confirmed_evidence(person_key, 'NO_HELMET', now):
                    details = ledger.evidence_details(person_key, 'NO_HELMET')
                    issues.append({'code':'NO_HELMET', 'status':'confirmed', 'sample_count':details['sample_count'],
                        'evidence_ref':json.dumps({'person_track_id':ptid, 'frame_seqs':details['frame_seqs']})})
                    ledger.release_commit(person_key, 'NO_HELMET')
            riding = any(g.get('posture_status') == 'riding' for g in riders)
            walking = all(g.get('posture_status') == 'walking_with_bike' for g in riders)
            label = 'positive' if riding else 'negative' if walking else 'unknown'
            decision = ledger.update(tid, 'RIDING_THROUGH_GATE', ErrorSample(label, self._frame_seq, now), now)
            if ledger.confirmed_evidence(tid, 'RIDING_THROUGH_GATE', now) and riding:
                details = ledger.evidence_details(tid, 'RIDING_THROUGH_GATE')
                issues.append({'code':'RIDING_THROUGH_GATE', 'status':'confirmed', 'sample_count':details['sample_count'],
                    'evidence_ref':json.dumps({'frame_seqs':details['frame_seqs']})})
                ledger.release_commit(tid, 'RIDING_THROUGH_GATE')
            # Preserve the existing rider-count rule, but contribute it to
            # this same vehicle event instead of emitting an independent alert.
            rider_ids = {g.get('track_id') for g in riders if g.get('track_id') is not None}
            overcrowded = riding and len(rider_ids) > MAX_RIDERS_PER_MOTORCYCLE
            count_label = 'positive' if overcrowded else 'negative' if riding else 'unknown'
            ledger.update(tid, 'TOO_MANY_RIDERS', ErrorSample(count_label, self._frame_seq, now), now)
            if overcrowded and ledger.confirmed_evidence(tid, 'TOO_MANY_RIDERS', now):
                details = ledger.evidence_details(tid, 'TOO_MANY_RIDERS')
                issues.append({'code':'TOO_MANY_RIDERS', 'status':'confirmed',
                    'sample_count':details['sample_count'],
                    'evidence_ref':json.dumps({'person_track_ids':sorted(rider_ids), 'frame_seqs':details['frame_seqs']})})
                ledger.release_commit(tid, 'TOO_MANY_RIDERS')
            hist = getattr(self._crossing_detector, '_tracks', {}).get(tid)
            if not hist or not hist.has_crossed or hist.crossed_at is None:
                continue
            eid = str(uuid.uuid5(uuid.NAMESPACE_URL,
                f'{self.gate_id}:{self.camera_id}:{self._encounter_session_id}:{self._source_epoch}:{tid}:{hist.crossed_at}'))
            # Phase 4 (Task 1): nếu eid đã seal nhưng DB row còn tồn tại,
            # issues mới (mũ đủ mẫu đến muộn, riding confirmed sau seal,
            # v.v.) sẽ được merge qua update_violation_issues() thay vì
            # bị bỏ. KHÔNG tạo row mới, KHÔNG push alert mới (đã đọc 1 lần).
            if eid in self._crossing_sealed:
                self.dispatch_late_issues(eid, issues)
                continue
            if getattr(self, '_last_sealed_crossing', {}).get(tid) == hist.crossed_at or len(self._crossing_jobs) >= 8:
                continue
            self._crossing_sealed[eid] = now
            if not hasattr(self, '_last_sealed_crossing'):
                self._last_sealed_crossing = {}
                self._plate_last_crossing = {}
            self._last_sealed_crossing[tid] = hist.crossed_at
            self._plate_last_crossing[tid] = hist.crossed_at
            # The frozen event owns exactly this crop/future and these samples.
            # A later model result may update cards, never issue a second audio job.
            best = self._best_plates.candidate(tid)
            if best and self._best_plates.trigger(tid, self._ocr_pool, _ocr_task, self._source_epoch):
                self._ocr_health['submitted'] += 1
            plate = self._consensus_result(tid, self._best_plates.result(tid))
            future = self._best_plates.future(tid)
            deadline = time.monotonic() + ALERT_MAX_PLATE_WAIT_MS/1000
            original = getattr(self, '_original_source_frame', frame)
            sh, sw = original.shape[:2]; dh, dw = frame.shape[:2]
            boxes = [g['_person'].bbox for g in riders if g.get('_person')] + [riders[0]['_vehicle'].bbox]
            bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            crop = self._crop_for_ocr(original, self._rescale_bbox(bbox, sw/dw, sh/dh)).copy()
            frozen = {'event_id':eid, 'vehicle_track_id':tid, 'source_epoch':self._source_epoch,
                      'camera_id':self.camera_id, 'frame_seq':self._frame_seq,
                      'observed_at':datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(),
                      'observed_ts':now,
                      'issues':deepcopy(issues), 'plate':deepcopy(plate), 'future':future, 'deadline':deadline,
                      'plate_samples':self._plate_consensus.observations(tid) if hasattr(self, '_plate_consensus') else [],
                      'plate_candidate':deepcopy(best),
                      'plate_frame_id':best.frame_id if best else None,
                      'helmet_status':'no_helmet' if any(i['code']=='NO_HELMET' for i in issues) else 'unknown',
                      'posture_status':'riding' if riding else 'walking_with_bike' if walking else 'unknown'}
            self._crossing_jobs[eid] = self._crossing_pool.submit(self._finish_crossing_event,
                {**frozen, 'run_generation': getattr(self, '_run_generation', 0)},
                original.copy(), crop, [f.copy() for f in self._clip_buffer])
        # Sealed IDs persist for this source; bounding doesn't revive old IDs
        # because expiry exceeds the lifetime of a tracked encounter.
        self._crossing_sealed = {k:v for k,v in self._crossing_sealed.items() if now-v < 3600}

    def _finish_crossing_event(self, frozen, frame, crop, clip_frames):
        from concurrent.futures import TimeoutError
        from app.cv.best_plate import resolve_plate
        from app.cv.crossing_alert import aggregate_crossing_event
        from app.config import PLATE_OCR_MIN_CONFIDENCE, DEBUG_ALERT
        # Phase 1 (Task 1): stop/restart guard. Nếu pipeline đã stop() hoặc
        # start() lại sau khi tác vụ này được submit, phiên cũ chết — bỏ qua,
        # không aggregate, không push alert.
        run_gen = frozen.get('run_generation')
        if run_gen is not None and run_gen != getattr(self, '_run_generation', 0):
            return True
        plate, future = frozen['plate'], frozen['future']
        if future is not None:
            try:
                raw = future.result(timeout=max(0., frozen['deadline']-time.monotonic()))
                # The worker can start late while mandatory evidence from an
                # earlier crossing is being written. Its deadline still belongs
                # to the crossing, not to the time this worker starts.
                valid = (raw.get('source_epoch', frozen['source_epoch']) == frozen['source_epoch']
                         and raw.get('track_id', frozen['vehicle_track_id']) == frozen['vehicle_track_id']
                         and raw.get('frame_seq', frozen.get('plate_frame_id')) == frozen.get('plate_frame_id')
                         and raw.get('completed_monotonic', frozen['deadline']) <= frozen['deadline'])
                if valid:
                    plate = resolve_plate(raw, PLATE_OCR_MIN_CONFIDENCE)
                    if 'plate_samples' in frozen:
                        from app.cv.plate_consensus import PlateConsensusStore, CropRecord
                        from app.cv.plate_voter import PlateReadResult
                        votes = PlateConsensusStore(min_confidence=PLATE_OCR_MIN_CONFIDENCE, min_quality=.3)
                        for record in frozen['plate_samples']:
                            votes.ingest_offer(1, record)
                        candidate = frozen.get('plate_candidate')
                        if candidate:
                            votes.ingest_offer(1, CropRecord(candidate.frame_id, candidate.timestamp,
                                plate.text, plate.confidence, candidate.quality_score, raw=raw, error=plate.error))
                        text, confidence, count = votes.decide(1)
                        plate = PlateReadResult(text=text or '', confidence=confidence, sample_count=count,
                            is_confident=bool(text and count >= 2), raw_text=raw.get('full', ''), error=plate.error)
            except TimeoutError:
                pass
            except Exception as exc:
                from app.cv.plate_voter import PlateReadResult
                plate = PlateReadResult(error=f'ocr_engine_error:{type(exc).__name__}')
        if frozen['source_epoch'] != self._source_epoch:
            return True
        # Single-file gate: the plate the rear camera confirmed at this moment
        # is this vehicle's plate (a front camera cannot see rear plates).
        pairing, front = None, getattr(self, 'role', None) == 'front'
        if front and not getattr(plate, 'is_confident', False):
            from app.cv import gate_pairing
            from app.cv.plate_voter import PlateReadResult
            text, conf, pairing = gate_pairing.pair(frozen.get('observed_ts', time.time()), self.gate_id)
            if text:
                plate = PlateReadResult(text=text, confidence=conf, sample_count=2, is_confident=True)
        event = aggregate_crossing_event(frozen['vehicle_track_id'], frozen['event_id'], frozen['issues'], plate,
                                         plate_expected=not front)
        if pairing == 'paired':
            event['issues'].append({'code': 'PLATE_FROM_REAR_CAMERA', 'status': 'info'})
        elif pairing == 'ambiguous':
            event['issues'].append({'code': 'PLATE_PAIRING_AMBIGUOUS', 'status': 'needs_review'})
        # Matching is permitted ONLY for a complete validated recognition.
        matched = None
        if event['plate_status'] == 'CONFIRMED':
            vehicle = get_vehicle_by_plate(event['plate_read'])
            matched = vehicle['plate_number'] if vehicle else None
            if not matched:
                event['issues'].append({'code':'PLATE_NOT_REGISTERED','status':'confirmed','sample_count':1})
        confirmed = [i for i in event['issues'] if i['status'] == 'confirmed']
        if not confirmed:
            return True
        filename = f'{uuid.uuid4().hex}.jpg'
        if DEBUG_ALERT:
            print(f"[Alert] event={event['crossing_event_id']} vehicle={event['vehicle_track_id']} plate={event['plate_read']} issues={[i['code'] for i in event['issues']]} stage=evidence_pending audio_jobs_planned=1")
        saved = self._persist_violation(frame, os.path.join(SNAPSHOTS_DIR, filename), filename,
            event['plate_read'], matched, frozen['helmet_status'],
            confirmed[0]['code'] if len(confirmed)==1 else 'MULTIPLE', frozen['posture_status'],
            bool(event['plate_read']), getattr(plate, 'confidence', None), self.gate_id, 'pending',
            frozen['event_id'], json.dumps(event['issues'], ensure_ascii=False), frozen['observed_at'],
            frozen['source_epoch'], frozen['camera_id'], track_id=frozen['vehicle_track_id'],
            frame_seq=frozen['frame_seq'], crop_frame=crop, clip_frames=clip_frames,
            crossing_event_id=event['crossing_event_id'], plate_status=event['plate_status'])
        if saved and pairing == 'none':
            # The rear camera often confirms a moment later: attach it then.
            from app.cv import gate_pairing
            eid = frozen['event_id']
            gate_pairing.wait_for_plate(frozen.get('observed_ts', time.time()), self.gate_id,
                lambda text, conf, status: self._attach_late_plate(eid, text, conf, status))
        return saved

    def _attach_late_plate(self, eid, text, confidence, status):
        """Write a plate paired after the event was saved; one UI notice, no
        second spoken alert (the vehicle's alert has already played)."""
        db_id = getattr(self, '_crossing_event_to_db_id', {}).get(eid)
        if db_id is None:
            return False
        from app.db import get_connection, update_violation_plate, update_violation_issues
        conn = get_connection()
        try:
            row = conn.execute("SELECT issues_json FROM violation_events WHERE id = ?", (db_id,)).fetchone()
        finally:
            conn.close()
        try:
            issues = json.loads(row['issues_json'] or '[]') if row else []
        except (TypeError, ValueError):
            issues = []
        if status == 'ambiguous':
            issues.append({'code': 'PLATE_PAIRING_AMBIGUOUS', 'status': 'needs_review'})
            return update_violation_issues(db_id, json.dumps(issues, ensure_ascii=False))
        vehicle = get_vehicle_by_plate(text)
        matched = vehicle['plate_number'] if vehicle else None
        issues = [i for i in issues if i.get('code') != 'PLATE_UNREADABLE']
        issues.append({'code': 'PLATE_FROM_REAR_CAMERA', 'status': 'info'})
        if not matched:
            issues.append({'code': 'PLATE_NOT_REGISTERED', 'status': 'confirmed', 'sample_count': 1})
        if not update_violation_plate(db_id, text, matched, confidence, json.dumps(issues, ensure_ascii=False)):
            return False
        alerts = getattr(self, '_alert_queue', None)
        if alerts is not None:
            try:
                alerts.put_nowait({
                    'type': 'plate_paired', 'event_id': eid, 'violation_id': db_id,
                    'plate_read': text, 'plate_matched': matched, 'registered': vehicle is not None,
                    'student_name': vehicle.get('student_name') if vehicle else None,
                    'student_class': vehicle.get('student_class') if vehicle else None,
                    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            except queue.Full:
                pass
        return True

    def _process_violations(self, frame, helmet_dets, plate_dets,
                            posture_status='unknown', vehicle_type=None,
                            too_many_riders=False, track_id=None, person_bbox=None,
                            crossed_gate=False, frame_seq=None, vehicle_bbox=None,
                            plate_result=None, recognition_updated=False,
                            primary_rider=True):
        # Legacy helper retained for existing integrations. The live loop uses
        # _process_vehicle_crossings; it never invokes this per-person path.
        # primary_rider=False: người này CÙNG xe với 1 group khác đã là "đại
        # diện" của xe đó (xem primary_track_by_vehicle ở _run_loop) — xe 2
        # người (chở theo) trước đây tạo 2 group độc lập, mỗi group tự kết
        # luận RIDING_THROUGH_GATE/TOO_MANY_RIDERS/PLATE_NOT_REGISTERED cho
        # CÙNG 1 xe → ghi 2 dòng DB, bắn 2 alert cho 1 lần xe qua cổng. Các mã
        # lỗi thuộc về XE (không phải NO_HELMET — vẫn xét riêng từng người)
        # chỉ group đại diện mới được đóng góp bằng chứng.
        # Unstable tracks and decision-engine failures never become official alerts.
        if vehicle_type in (None, 'bicycle') or track_id is None:
            self._diagnostic('decision', 'review', 'track_missing' if track_id is None else
                'vehicle_not_associated' if vehicle_type is None else 'bicycle_exempt', track_id)
            return
        ledger = getattr(self, '_evidence_ledger', None)
        if ledger is None:
            self._diagnostic('decision', 'error', 'evidence_engine_unavailable', track_id)
            return
        from app.cv.evidence import ErrorSample
        if not hasattr(self, '_persist_pending'):
            self._persist_pending = {}
        if not hasattr(self, '_io_health'):
            self._io_health = {"errors": 0, "clip_errors": 0}
        if not hasattr(self, '_persist_failures'):
            self._persist_failures = {}
        if not hasattr(self, '_encounter_session_id'):
            self._encounter_session_id = uuid.uuid4().hex
        epoch = int(getattr(self, '_source_epoch', 0))
        camera = getattr(self, 'camera_id', self.gate_id)
        encounter = str(uuid.uuid5(uuid.NAMESPACE_URL,
                        f'{self.gate_id}:{camera}:{self._encounter_session_id}:{epoch}:{track_id}'))
        # Collect failures on the ledger's owning thread; worker callbacks never mutate it.
        for eid, (future, tid, codes, submitted_epoch) in list(self._persist_pending.items()):
            if not future.done():
                continue
            try:
                saved = future.result() is True
            except Exception:
                saved = False
            self._persist_pending.pop(eid, None)
            if submitted_epoch != epoch:
                continue
            if saved:
                self._persist_failures.pop(eid, None)
                for code in codes:
                    self._last_log_time[(eid, code)] = time.time()
            else:
                self._io_health['errors'] += 1
                failures, _ = self._persist_failures.get(eid, (0, 0))
                self._persist_failures[eid] = (failures + 1, time.time())
                for code in codes:
                    ledger.release_commit(tid, code)
        if encounter in self._persist_pending or len(self._persist_pending) >= 32:
            self._diagnostic('io', 'pending', 'evidence_pending', track_id)
            return
        now = time.time()
        failures, last_failure = self._persist_failures.get(encounter, (0, 0))
        if failures >= 3 and now - last_failure < 60:
            self._diagnostic('io', 'error', 'evidence_write_failed', track_id, source_epoch=epoch, frame_seq=frame_seq)
            return
        if failures >= 3:
            self._persist_failures.pop(encounter, None)
        # Keep per-track bookkeeping finite during long shifts.
        ledger.prune_expired(now, grace_period_sec=60)
        self._last_log_time = {key: ts for key, ts in self._last_log_time.items() if now - ts < VIOLATION_COOLDOWN}
        self._persist_failures = {key: value for key, value in self._persist_failures.items() if now - value[1] < 60}
        seq = frame_seq if frame_seq is not None else getattr(self, '_frame_seq', 0)
        self._frame_seq = max(getattr(self, '_frame_seq', 0), seq)
        has_helmet = any('With Helmet' in d.class_name for d in helmet_dets)
        no_helmet = any('Without Helmet' in d.class_name for d in helmet_dets)
        helmet_status = 'unknown' if has_helmet == no_helmet else ('helmet' if has_helmet else 'no_helmet')
        plate_read, plate_matched, confidence = '', None, None
        if plate_dets and not recognition_updated:
            plate_result = self._read_plate_voted(frame, plate_dets[0], track_id=track_id, frame_seq=seq)
        if plate_result:
            plate_read = plate_result.text
            confidence = plate_result.confidence if plate_read else None
            self._plate_attempts += 1
            if plate_read:
                self._plate_successes += 1
        plate_uncertain = not plate_result or not plate_read or not plate_result.is_confident
        if plate_result and (getattr(plate_result, 'pending', False) or getattr(plate_result, 'error', None)):
            plate_uncertain = True
        if plate_read and not plate_uncertain:
            vehicle = get_vehicle_by_plate(plate_read)
            plate_matched = vehicle['plate_number'] if vehicle else None
        candidates = []
        if posture_status != 'riding':
            self._diagnostic('decision', 'review', 'posture_unknown' if posture_status == 'unknown' else 'not_riding', track_id,
                posture=posture_status)
        elif not crossed_gate:
            detector = getattr(self, '_crossing_detector', None)
            self._diagnostic('decision', 'pending', 'crossing_not_confirmed' if detector and detector.gate_line else 'gate_line_missing', track_id)
        if no_helmet and not has_helmet and posture_status == 'riding':
            candidates.append('NO_HELMET')
        # KHÔNG gate theo crossed_gate ở đây nữa — bằng chứng "đang riding"
        # tích lũy LIÊN TỤC suốt lúc xe còn trong khung (giống NO_HELMET),
        # để SẴN SÀNG từ TRƯỚC khi tới vạch. crossed_gate chỉ còn vai trò
        # CHỐT (finalization trigger) ở vòng lặp xác nhận bên dưới — nếu để
        # crossed_gate gate ngay từ đây, ledger chỉ bắt đầu đếm mẫu SAU khi
        # cán vạch, bắt xe phải tiếp tục chạy thêm ~4 mẫu/1.5s NỮA sau vạch
        # mới confirm — đúng độ trễ "chờ thêm frame sau vạch" cần bỏ.
        if primary_rider and posture_status == 'riding':
            candidates.append('RIDING_THROUGH_GATE')
        if primary_rider and too_many_riders and posture_status == 'riding':
            candidates.append('TOO_MANY_RIDERS')
        if primary_rider and plate_read and not plate_uncertain and not plate_matched:
            candidates.append('PLATE_NOT_REGISTERED')
        observations = {
            'NO_HELMET': 'positive' if 'NO_HELMET' in candidates else
                         ('negative' if has_helmet and not no_helmet and posture_status == 'riding' else 'unknown'),
            'RIDING_THROUGH_GATE': 'positive' if 'RIDING_THROUGH_GATE' in candidates else 'unknown',
            'TOO_MANY_RIDERS': 'positive' if 'TOO_MANY_RIDERS' in candidates else 'unknown',
            'PLATE_NOT_REGISTERED': 'positive' if 'PLATE_NOT_REGISTERED' in candidates else
                                    ('negative' if plate_matched else 'unknown'),
        }
        confirmed, issues = [], []
        try:
            for code, observation in observations.items():
                decision = ledger.update(int(track_id), code,
                    ErrorSample(observation, seq, now, code), now=now)
                details = ledger.evidence_details(int(track_id), code)
                if observation != 'unknown' or decision.kind.value == 'conflict':
                    self._diagnostic('decision', 'error' if decision.kind.value == 'conflict' else
                        'confirmed' if decision.kind.value == 'confirm' else 'pending',
                        'evidence_conflict' if decision.kind.value == 'conflict' else
                        'issue_confirmed' if decision.kind.value == 'confirm' else 'collecting_samples', track_id,
                        issue=code, samples=details['sample_count'], required_samples=ledger.min_samples)
                if decision.kind.value == 'confirm':
                    if code == 'RIDING_THROUGH_GATE' and not crossed_gate:
                        # Bằng chứng riding đã đủ nhưng CHƯA cán vạch — đây
                        # chỉ là "không dắt xe" nếu THỰC SỰ đi qua cổng khi
                        # đang riding. Release commit ngay để ledger KHÔNG bị
                        # khoá ở trạng thái "đã confirm" (grace_period_sec) —
                        # giữ nguyên sample window, frame kế tiếp vẫn còn
                        # riding sẽ confirm lại ngay (không cần tích thêm từ
                        # đầu). Khi crossed_gate=True tới, nhánh này không
                        # chạy nữa → confirm thật, chốt NGAY không chờ thêm.
                        ledger.release_commit(int(track_id), code)
                        self._diagnostic('decision', 'pending', 'riding_confirmed_awaiting_crossing', track_id,
                            issue=code, samples=details['sample_count'])
                    elif now - self._last_log_time.get((encounter, code), 0) >= VIOLATION_COOLDOWN:
                        confirmed.append(code)
                        issues.append({'code': code, 'status': 'confirmed', 'reason': None,
                            'sample_count': details['sample_count'],
                            'evidence_ref': json.dumps({'camera_id': camera, 'source_epoch': epoch,
                                                       'frame_seqs': details['frame_seqs']})})
                    else:
                        self._diagnostic('decision', 'pending', 'cooldown', track_id, issue=code)
                elif decision.kind.value == 'conflict':
                    issues.append({'code': code, 'status': 'conflict', 'reason': 'contradictory_observations',
                                   'sample_count': details['sample_count']})
        except Exception as exc:
            self._io_health['errors'] += 1
            print(f'[Pipeline] Evidence unavailable: {type(exc).__name__}')
            return
        if not confirmed:
            return
        if plate_uncertain:
            issues.append({'code': 'PLATE_LOW_CONFIDENCE', 'status': 'deferred',
                'reason': 'ocr_error' if getattr(plate_result, 'error', None) else 'plate_not_confirmed',
                'sample_count': getattr(plate_result, 'sample_count', 0) if plate_result else 0})
        first_ts = min(ledger.evidence_details(int(track_id), c)['first_observed_at'] or now for c in confirmed)
        observed_at = datetime.datetime.fromtimestamp(first_ts, datetime.timezone.utc).isoformat()
        filename = f'{uuid.uuid4().hex}.jpg'
        path = os.path.join(SNAPSHOTS_DIR, filename)
        crop = None
        boxes = [box for box in (person_bbox, vehicle_bbox, *[getattr(d, "bbox", None) for d in helmet_dets + plate_dets]) if box]
        if boxes:
            bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes))
            crop = self._crop_for_ocr(frame, tuple(int(v) for v in bbox)).copy()
            if not crop.size:
                crop = None
        future = self._io_pool.submit(self._persist_violation,
            frame.copy(), path, filename, plate_read, plate_matched, helmet_status,
            confirmed[0] if len(confirmed) == 1 else 'MULTIPLE', posture_status,
            validate_plate_format(plate_read) if plate_read else None, confidence,
            self.gate_id, 'pending',
            encounter, json.dumps(issues, ensure_ascii=False), observed_at, epoch, camera,
            track_id=track_id, frame_seq=self._frame_seq, crop_frame=crop,
            clip_frames=[f.copy() for f in self._clip_buffer],
            # Phase 1: capture generation tại THỜI ĐIỂM ENQUEUE — nếu
            # admin restart hoặc stop() chạy giữa chừng, _persist_violation
            # sẽ thấy generation cũ → không insert row cho phiên đã chết.
            # Dùng getattr để chịu được test fixture xây dựng pipeline
            # thủ công qua __new__ mà không gọi __init__.
            run_generation=getattr(self, '_run_generation', 0))
        self._persist_pending[encounter] = (future, int(track_id), confirmed, epoch)
        self._diagnostic('io', 'pending', 'evidence_pending', track_id)

    def _write_clip(self, frames: list, out_path: str):
        if not frames:
            return False
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), VIOLATION_CLIP_FPS, (w, h))
        try:
            if not writer.isOpened():
                return False
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        return os.path.isfile(out_path) and os.path.getsize(out_path) > 0

    def _save_optional_clip(self, event_id, frames, filename):
        try:
            path = os.path.join(SNAPSHOTS_DIR, filename)
            if not self._write_clip(frames, path):
                raise OSError('clip write failed')
            from app.db import update_violation_media
            update_violation_media(event_id, clip_path=f'data/snapshots/{filename}')
        except Exception as exc:
            self._io_health['clip_errors'] += 1
            print(f'[Pipeline] Clip failed: {type(exc).__name__}')

    def _persist_violation(self, frame, snapshot_path, snapshot_filename,
                           plate_read, plate_matched, helmet_status, violation_type,
                           posture_status, plate_format_valid, plate_confidence=None,
                           gate_id=None, status='pending', encounter_id=None,
                           issues_json=None, observed_at=None, source_epoch=None,
                           camera_id=None, track_id=None, crop_frame=None, clip_frames=None, frame_seq=None,
                           crossing_event_id=None, plate_status=None,
                           run_generation=None):
        """Official alerts require saved mandatory evidence and a committed DB row.

        Phase 0: đo 2 latency:
        - persistence latency: imwrite snapshot + add_violation_event + insert DB
        - dispatch latency: _push_alert (đẩy vào _alert_queue)
        Cả 2 buffer bounded 60 mẫu. Trước đây 2 thao tác này không có telemetry
        → khi alert trễ hoặc mất, debug phải thêm print rải rác.
        Phase 1 (Task 1): `run_generation` được capture tại THỜI ĐIỂM enqueue.
        Nếu `stop()` (hoặc `start()` lần nữa) đã tăng generation, callback này
        là STALE — bỏ qua, không insert row, không push alert, không submit clip.
        Đây là defense-in-depth cùng với source_epoch: source_epoch chống camera
        switch, run_generation chống stop/restart toàn pipeline.
        """
        # Phase 1: stop/restart guard — check generation TRƯỚC cả source_epoch
        # Dùng getattr để chịu test fixture xây dựng pipeline qua __new__
        # mà không gọi __init__ (một số test cũ trong test_vehicle_gate /
        # test_vehicle_crossing_aggregation).
        if run_generation is not None and run_generation != getattr(self, '_run_generation', 0):
            self._violations_skipped_total = getattr(self, '_violations_skipped_total', 0) + 1
            self._diagnostic('io', 'stale', 'persist_stale_generation', track_id, source_epoch=source_epoch, frame_seq=frame_seq)
            return False
        if source_epoch is not None and source_epoch != getattr(self, '_source_epoch', source_epoch):
            return False
        t_persist_start = time.perf_counter()
        success, crop_path = False, None
        try:
            os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
            success = bool(cv2.imwrite(snapshot_path, frame)) and os.path.isfile(snapshot_path) and os.path.getsize(snapshot_path) > 0
            if success and crop_frame is not None:
                crop_name = snapshot_filename.replace('.jpg', '_crop.jpg')
                crop_file = os.path.join(os.path.dirname(snapshot_path), crop_name)
                success = bool(cv2.imwrite(crop_file, crop_frame)) and os.path.isfile(crop_file) and os.path.getsize(crop_file) > 0
                if success:
                    crop_path = f'data/snapshots/{crop_name}'
        except Exception as exc:
            print(f'[Pipeline] Evidence write failed: {type(exc).__name__}')
            success = False
        try:
            new_id = add_violation_event(
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                plate_read=plate_read, plate_matched=plate_matched,
                helmet_status=helmet_status, violation_type=violation_type,
                snapshot_path=f'data/snapshots/{snapshot_filename}' if success else None,
                crop_snapshot_path=crop_path if success else None,
                posture_status=posture_status, plate_format_valid=plate_format_valid,
                clip_path=None, plate_confidence=plate_confidence, gate_id=gate_id,
                status=status, encounter_id=encounter_id, issues_json=issues_json,
                observed_at=observed_at, source_epoch=source_epoch,
                camera_id=camera_id or gate_id, track_id=track_id,
                evidence_state='persisted' if success else 'failed')
            if not success:
                self._diagnostic('io', 'error', 'evidence_write_failed', track_id, source_epoch=source_epoch, frame_seq=frame_seq)
                self._violations_skipped_total = getattr(self, '_violations_skipped_total', 0) + 1
                buf = getattr(self, '_metrics_persistence', None)
                if buf is not None:
                    buf.add((time.perf_counter() - t_persist_start) * 1000)
                return False
            buf = getattr(self, '_metrics_persistence', None)
            if buf is not None:
                buf.add((time.perf_counter() - t_persist_start) * 1000)
            if source_epoch is not None and source_epoch != getattr(self, '_source_epoch', source_epoch):
                return True  # retain history, never speak the previous source
            if not hasattr(self, '_event_versions'):
                self._event_versions = {}
            eid = encounter_id or str(new_id)
            version = self._event_versions.get(eid, 0) + 1
            self._event_versions[eid] = version
            if len(self._event_versions) > 2048:
                self._event_versions.pop(next(iter(self._event_versions)))
            # Phase 4 (Task 1): nhớ eid → DB row id để late issues có thể
            # UPDATE vào cùng event qua update_violation_issues(). Bounded
            # 2048 entries — đủ cho ca 12 giờ (TTL 1h trong prune_expired).
            # Dùng getattr để chịu test fixture xây dựng pipeline qua __new__
            # mà không gọi __init__ (một số test cũ trong test_vehicle_gate /
            # test_vehicle_crossing_aggregation).
            if encounter_id and isinstance(new_id, int):
                eid_to_db = getattr(self, '_crossing_event_to_db_id', None)
                if eid_to_db is None:
                    self._crossing_event_to_db_id = {}
                    eid_to_db = self._crossing_event_to_db_id
                eid_to_db[encounter_id] = new_id
                if len(eid_to_db) > 2048:
                    eid_to_db.pop(next(iter(eid_to_db)))
            t_dispatch_start = time.perf_counter()
            self._push_alert(violation_type, plate_read, plate_matched,
                snapshot_filename=snapshot_filename, plate_format_valid=plate_format_valid,
                event_id=eid, event_version=version, issues=json.loads(issues_json or '[]'),
                gate_id=gate_id, camera_id=camera_id or gate_id,
                source_epoch=source_epoch, track_id=track_id, evidence_state='persisted',
                crossing_event_id=crossing_event_id, vehicle_track_id=track_id,
                alert_finalized=bool(crossing_event_id), plate_status=plate_status)
            disp_buf = getattr(self, '_metrics_dispatch', None)
            if disp_buf is not None:
                disp_buf.add((time.perf_counter() - t_dispatch_start) * 1000)
            self._violations_persisted_total = getattr(self, '_violations_persisted_total', 0) + 1
            self._diagnostic('io', 'observed', 'evidence_saved', track_id, source_epoch=source_epoch, frame_seq=frame_seq)
            # Clips never delay mandatory evidence or official sound.
            if clip_frames and getattr(self, '_clip_pool', None) is not None:
                self._clip_jobs = [job for job in getattr(self, '_clip_jobs', []) if not job.done()]
                if len(self._clip_jobs) < 8:
                    self._clip_jobs.append(self._clip_pool.submit(self._save_optional_clip, new_id, clip_frames,
                                          snapshot_filename.replace('.jpg', '.mp4')))
                else:
                    self._io_health['clip_errors'] += 1
            return True
        except Exception as exc:
            # Debug: log full traceback in DEBUG mode so we can find issues
            # like missing attrs in test fixtures (Phase 1/2 changes tightened
            # this method).
            import traceback as _tb
            print(f'[Pipeline] Event persist failed: {type(exc).__name__}: {exc}')
            if os.environ.get('PIPELINE_DEBUG_TRACE', '0') == '1':
                _tb.print_exc()
            self._diagnostic('io', 'error', 'evidence_write_failed', track_id, source_epoch=source_epoch, frame_seq=frame_seq)
            self._persist_failures_count = getattr(self, '_persist_failures_count', 0) + 1
            return False

    def _try_correlate(self, new_event: dict):
        """Ghép 1 lượt xe từ 2 camera (Bước 3). Chạy trên _io_pool sau khi insert.

        Tách ra khỏi _persist_violation để:
        - Bước 3 là điểm nhạy cảm nhất về correctness (ghép sai = cực tệ) —
          tách hẳn ra để dễ log/trace lỗi mà không ảnh hưởng insert chính.
        - Lỗi correlation KHÔNG được làm hỏng pipeline camera (exception isolation
          đúng theo yêu cầu của Bước 4 về job nền — áp dụng sớm ở đây).
        """
        try:
            candidates = find_correlation_candidates(
                new_event, window_sec=CORRELATION_TIME_WINDOW_SEC,
            )
            if not candidates:
                mark_correlation_unmatched(new_event["id"])
                return

            best, corr_status = find_correlation_candidate(
                new_event, candidates, min_similarity=CORRELATION_MIN_SIMILARITY,
            )
            if best is None:
                # BUG đã gặp: trước đây luôn ghi 'unmatched' bất kể corr_status
                # là gì, làm mất tín hiệu 'needs_review' (có ứng viên nhưng 1
                # trong 2 bên không chắc biển số từ Bước 1, hoặc bên mình không
                # đọc được biển) — giờ truyền đúng corr_status xuống DB.
                mark_correlation_unmatched(new_event["id"], status=corr_status)
                return

            ok = link_violation_events(new_event["id"], best["id"], status=corr_status)
            if ok:
                print(f"[Pipeline] Correlated #{new_event['id']} <-> #{best['id']} ({corr_status})")
            else:
                # Race: 1 trong 2 đã bị ghép trước đó → đánh dấu unmatched
                mark_correlation_unmatched(new_event["id"])
        except Exception as e:
            print(f"[Pipeline] Correlation error for #{new_event.get('id')}: {e}")

    def _push_alert(self, violation_type, plate_read, plate_matched,
                    snapshot_filename=None, plate_format_valid=None, **metadata):
        if not snapshot_filename or metadata.get('evidence_state') != 'persisted':
            return
        message = {
            'type': 'violation', 'violation_type': violation_type,
            'plate_read': plate_read or None, 'plate_matched': plate_matched or None,
            'plate_format_valid': plate_format_valid,
            'snapshot_url': f'/api/media/snapshots/{snapshot_filename}',
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **metadata,
        }
        try:
            self._alert_queue.put_nowait(message)
        except queue.Full:
            try:
                self._alert_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._alert_queue.put_nowait(message)
            except queue.Full:
                pass
            health = getattr(self, '_io_health', None)
            if health is not None:
                health['alerts_dropped'] = health.get('alerts_dropped', 0) + 1

    def _run_posture_detection(self, frame: np.ndarray, groups: list) -> list:
        """
        Chạy pose detection cho mỗi person box trong groups.
        Bổ sung 'posture_status' vào mỗi group dict.
        Hoàn toàn isolated trong try/except để không ảnh hưởng pipeline chính.

        Mọi model chạy trên 1 luồng model-owner duy nhất, nên N người = N lượt
        nối tiếp. Gộp tất cả crop vào 1 lượt batch để chi phí không tăng tuyến
        tính theo số người.
        """
        try:
            from app.cv.pose import PostureDetector, SideViewRiding, RidingTemporalState
            from app.config import DEBUG_RIDING

            detector = PostureDetector()
            if not hasattr(self, '_riding_temporal'):
                self._riding_temporal = RidingTemporalState()
            scorer = SideViewRiding()
            frame_h, frame_w = frame.shape[:2]

            # Cắt crop hợp lệ trước, chỉ submit những group thực sự cần detect
            pending = []
            for group in groups:
                person = group.get('_person')
                if person is None or group.get('_vehicle') is None:
                    group['posture_status'] = 'unknown'
                    continue

                x1, y1, x2, y2 = person.bbox
                x1, x2 = max(0, x1), min(frame_w, x2)
                y1, y2 = max(0, y1), min(frame_h, y2)
                if x2 <= x1 or y2 <= y1:
                    group['posture_status'] = 'unknown'
                    continue

                person_crop = frame[y1:y2, x1:x2]
                if person_crop.size == 0 or person_crop.shape[0] < 30 or person_crop.shape[1] < 30:
                    group['posture_status'] = 'unknown'
                    continue

                pending.append((group, (x1, y1), person_crop))

            batch = detector.detect_pose_batch([crop for _, _, crop in pending]) if pending else []
            pose_data = []
            for (group, offset, _), keypoints in zip(pending, batch):
                vehicle = group.get('_vehicle')
                temporal = self._riding_temporal.observe(group.get('track_id'), group.get('vehicle_track_id'),
                    self._source_epoch, group['_person'].bbox, vehicle.bbox, time.monotonic())
                result = scorer.evaluate(keypoints, bike_bbox=vehicle.bbox, person_bbox=group['_person'].bbox,
                    offset=offset, temporal_score=temporal.temporal_score, motion_score=temporal.motion_score)
                posture = result.state.lower()
                group['posture_status'] = posture
                group['_riding_debug'] = result.debug
                if keypoints:
                    self._draw_pose_keypoints(frame, keypoints, offset=offset)
                    pose_data.append((keypoints, offset))
                    if DEBUG_RIDING:
                        text = f"{result.state} score={result.score:.2f} leg={result.debug['leg_status']}"
                        cv2.putText(frame, text, (offset[0], max(15, offset[1]-10)), cv2.FONT_HERSHEY_SIMPLEX, .45, (0,255,255), 1)
                        self._diagnostic('riding', 'observed', 'side_view_features', group.get('vehicle_track_id'), riding=result.debug)
            self._last_pose_data = pose_data

            # Phase 3 (Task 1): 4-state posture temporal ledger — tích lũy
            # sample nhất quán trong 1.5s trước khi confirm state. Trước đây
            # posture nhảy theo frame (RIDING→WALKING→RIDING khi pose model
            # không chắc chắn); giờ chỉ confirm khi đa số sample trong
            # window đồng ý. Unknown coi như "không có dữ liệu" → KHÔNG
            # phá ledger (giữ state confirm cũ).
            try:
                from collections import Counter
                # Lấy posture phổ biến nhất (mode) từ groups của frame hiện tại
                if groups:
                    frame_states = [
                        (g.get('posture_status') or 'unknown').upper()
                        for g in groups if g.get('_vehicle') is not None
                    ]
                    if frame_states:
                        # Bỏ 'unknown' (không phải evidence) — chỉ vote trên
                        # state có signal
                        vote_pool = [s for s in frame_states if s != 'UNKNOWN']
                        if vote_pool:
                            top_state, top_count = Counter(vote_pool).most_common(1)[0]
                            now_m = time.monotonic()
                            self._posture_window.append((now_m, top_state))
                # prune window
                now_m = time.monotonic()
                while self._posture_window and (now_m - self._posture_window[0][0]) > POSTURE_TEMPORAL_WINDOW_SEC:
                    self._posture_window.popleft()
                # count occurrences
                counts = Counter(s for _, s in self._posture_window)
                if counts:
                    best_state, best_count = counts.most_common(1)[0]
                    total = sum(counts.values())
                    self._posture_confidence = round(best_count / total, 3)
                    if best_count >= POSTURE_TEMPORAL_MIN_SAMPLES:
                        self._posture_confirmed = best_state

                # N05 (Post-Video Review): ingest PER-TRACK. Mỗi group có
                # vehicle_track_id riêng → đẩy posture_status vào
                # `_posture_track_ledger` riêng theo track. Hai xe không
                # chia mẫu (đã test ở test_task01_post_video_posture_per_track).
                ledger_obj = getattr(self, '_posture_track_ledger', None)
                if ledger_obj is not None and groups:
                    ledger_obj.expire_stale(now_m=now_m)
                    for g in groups:
                        if g.get('_vehicle') is None:
                            continue
                        # Key theo vehicle_track_id; nếu chưa có → track_id
                        # phụ (vẫn tách theo group, không gộp 2 xe).
                        key = g.get('vehicle_track_id')
                        if key is None:
                            key = g.get('track_id')
                        if key is None:
                            continue
                        state = (g.get('posture_status') or 'UNKNOWN').upper()
                        ledger_obj.add(int(key), state, now_m=now_m)
            except Exception:
                # ISOLATED — ledger failure không break posture detection
                pass

        except Exception:
            # ISOLATED: posture errors must not break the main pipeline
            for group in groups:
                if 'posture_status' not in group:
                    group['posture_status'] = 'unknown'

        return groups

    def _posture_state(self) -> str:
        """Phase 3 (Task 1): trả về posture state đã confirm qua temporal
        accumulation (RIDING/PUSHING/WALKING/UNKNOWN)."""
        return self._posture_confirmed

    # COCO 17-keypoint skeleton — cặp nối để vẽ đường xương, và nhãn ngắn cho
    # riêng 6 khớp chân (hông/gối/mắt cá) vì đây là 3 khớp quyết định phân loại
    # tư thế (classify_posture) — nhãn phần còn lại (tay/mặt) sẽ rối hình không
    # phục vụ quyết định gì nên chỉ vẽ chấm, không ghi chữ.
    _SKELETON_PAIRS = [
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # vai-khuỷu-cổ tay
        (5, 11), (6, 12), (11, 12),               # thân
        (11, 13), (13, 15), (12, 14), (14, 16),   # hông-gối-mắt cá
    ]
    _KEYPOINT_LABELS = {11: 'Hong T', 12: 'Hong P', 13: 'Goi T', 14: 'Goi P', 15: 'MatCa T', 16: 'MatCa P'}
    _KP_CONF_THRESHOLD = 0.3

    def _draw_pose_keypoints(self, frame: np.ndarray, keypoints: list, offset: tuple):
        """Vẽ khung xương + nhãn khớp hông/gối/mắt cá lên frame (tọa độ crop + offset)."""
        ox, oy = offset
        color_kp = (0, 220, 255)   # vàng-cam — tách biệt với box helmet/plate/person
        color_bone = (0, 160, 200)

        def pt(i):
            if i >= len(keypoints) or keypoints[i].get('confidence', 0) < self._KP_CONF_THRESHOLD:
                return None
            return (int(keypoints[i]['x'] + ox), int(keypoints[i]['y'] + oy))

        for a, b in self._SKELETON_PAIRS:
            pa, pb = pt(a), pt(b)
            if pa and pb:
                cv2.line(frame, pa, pb, color_bone, 1, cv2.LINE_AA)

        for i in range(len(keypoints)):
            p = pt(i)
            if not p:
                continue
            cv2.circle(frame, p, 3, color_kp, -1, cv2.LINE_AA)
            label = self._KEYPOINT_LABELS.get(i)
            if label:
                cv2.putText(frame, label, (p[0] + 4, p[1] - 4), FONT, 0.35, color_kp, 1, cv2.LINE_AA)

    def _draw_riding_debug(self, frame: np.ndarray, group: dict, posture: str,
                           keypoints: list, offset: tuple) -> None:
        """DEBUG_RIDING=1: in state + góc chân + lệch hip/xe lên video để tune
        RIDING_HIP_X_TOLERANCE/RIDING_HIP_Y_TOLERANCE trên camera thật — không
        chạm vào frame gốc dùng cho OCR/evidence (hàm này chỉ được gọi trên
        frame hiển thị, giống _draw_pose_keypoints)."""
        from app.cv.pose import avg_leg_angle, hip_over_bike
        from app.config import POSE_CONF_THRESHOLD

        person = group.get('_person')
        if person is None:
            return
        x1, y1 = person.bbox[0], person.bbox[1]
        lines = [f"P{group.get('track_id')} {posture.upper()}"]
        angle = avg_leg_angle(keypoints, POSE_CONF_THRESHOLD)
        lines.append(f"leg={angle:.0f}" if angle is not None else "leg=?")
        vehicle = group.get('_vehicle')
        if vehicle is not None:
            _, dx, dy = hip_over_bike(keypoints, POSE_CONF_THRESHOLD, vehicle.bbox, offset)
            lines.append(f"hip dx={dx:.2f} dy={dy:.2f}" if dx is not None else "hip=?")
        else:
            lines.append("no bike")
        color = (0, 255, 255)
        for i, text in enumerate(lines):
            cv2.putText(frame, text, (x1, max(12, y1 - 10 - 14 * i)), FONT, 0.42, color, 1, cv2.LINE_AA)


# Pipeline instances keyed by gate_id
_pipelines: dict[str, VideoPipeline] = {}
# ponytail: global lock (không per-gate) — đổi camera là thao tác admin hiếm,
# tốn ~10s (nạp lại model) nên khoá cả tiến trình đổi là chấp nhận được. Nếu
# không khoá: 2 request restart cùng lúc (double-click, 2 tab) sẽ tạo 2
# VideoPipeline song song, cả 2 cùng mở RTSP → camera (thường chỉ cho 1 client
# RTSP) từ chối phiên thứ 2, pipeline bị OFFLINE. Bug này gặp thật khi test.
_pipelines_lock = threading.Lock()


def _create_pipeline_locked(gate_id: str) -> VideoPipeline:
    """Tạo VideoPipeline mới cho gate_id — PHẢI gọi trong _pipelines_lock."""
    gate_config = GATES.get(gate_id)
    if gate_config is None:
        raise ValueError(f"Unknown gate_id: {gate_id}. Available gates: {list(GATES.keys())}")
    # Nguồn camera chọn qua /admin/camera (nếu có) đè lên mặc định từ env var.
    # Mutate GATES tại chỗ vì _run_loop() đọc thẳng từ GATES, không dùng
    # gate_config truyền vào đây (chỉ dùng để lấy "name").
    saved_source = get_gate_camera_source(gate_id)
    if saved_source is not None:
        gate_config["source"] = saved_source
    pipeline = VideoPipeline(gate_id, gate_config)
    _pipelines[gate_id] = pipeline
    return pipeline


def get_existing_pipeline(gate_id: str = "main") -> VideoPipeline | None:
    """Read the running registry without initializing cameras or models."""
    with _pipelines_lock:
        return _pipelines.get(gate_id)


def get_pipeline(gate_id: str = "main") -> VideoPipeline:
    """Lấy (hoặc tạo mới) pipeline instance cho gate_id."""
    with _pipelines_lock:
        if gate_id not in _pipelines:
            _create_pipeline_locked(gate_id)
        return _pipelines[gate_id]


def start_all_pipelines():
    """Start pipeline threads for ALL configured gates."""
    from app.config import GATES
    for gate_id in GATES:
        get_pipeline(gate_id).start()


def stop_all_pipelines():
    """Stop pipeline threads for ALL active gates."""
    global _pipelines
    for gate_id in list(_pipelines.keys()):
        pipeline = _pipelines.pop(gate_id, None)
        if pipeline:
            pipeline.stop()


def start_pipeline(gate_id: str = "main"):
    """Start pipeline thread for the specified gate."""
    get_pipeline(gate_id).start()


def stop_pipeline(gate_id: str = "main"):
    """Stop pipeline thread for the specified gate."""
    pipeline = _pipelines.get(gate_id)
    if pipeline:
        pipeline.stop()


def restart_pipeline(gate_id: str = "main"):
    """Dừng và tạo lại pipeline cho gate (nạp lại model + mở nguồn camera mới).

    stop() đã shutdown() các ThreadPoolExecutor của instance cũ — chúng không
    thể tái dùng, nên phải xoá khỏi _pipelines để bắt buộc tạo instance mới,
    thay vì chỉ start() lại instance cũ (sẽ lỗi RuntimeError khi submit task
    vào pool đã shutdown). Giữ nguyên _pipelines_lock suốt pop+stop+tạo mới để
    không race với get_pipeline() gọi song song (xem comment ở _pipelines_lock).
    """
    with _pipelines_lock:
        old = _pipelines.pop(gate_id, None)
        if old:
            old.stop()
        pipeline = _create_pipeline_locked(gate_id)
    pipeline.start()
