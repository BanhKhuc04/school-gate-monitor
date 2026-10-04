"""
Pipeline xử lý video trong thread nền.

Luồng: đọc frame → detect helmet → detect plate → OCR → tra DB → ghi log vi phạm → vẽ box → lưu frame.
Có thêm queue cho cảnh báo vi phạm (Bước 4) và ghi log vi phạm vào DB (Bước 6).
"""
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import queue
import datetime
import os
import cv2
import numpy as np
from typing import Optional

from app.config import (
    GATES, HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
    FRAME_SKIP, VIDEO_WIDTH, VIDEO_HEIGHT, DETECT_WIDTH, DETECT_HEIGHT,
    ALERT_COOLDOWN, VIOLATION_COOLDOWN, SNAPSHOTS_DIR, MAX_RIDERS_PER_MOTORCYCLE,
    VIOLATION_CLIP_SECONDS, VIOLATION_CLIP_FPS,
    PLATE_VOTE_WINDOW_SEC, PLATE_VOTE_MIN_AGREE, PLATE_MIN_CONFIDENCE_SINGLE,
    CORRELATION_TIME_WINDOW_SEC, CORRELATION_MIN_SIMILARITY,
    CONTINUOUS_RECORDING_ENABLED, CONTINUOUS_RECORDING_SEGMENT_MINUTES,
    CONTINUOUS_RECORDING_FPS, CONTINUOUS_RECORDING_WIDTH, CONTINUOUS_RECORDING_HEIGHT,
    CONTINUOUS_RECORDING_DIR, FRAME_EDGE_MARGIN_RATIO,
    DETECT_IMGSZ, VIDEO_FILE_REALTIME, TRACK_MIN_FRAMES, DEVICE,
)
from app.cv.capture import WebcamStream
from app.cv.detector import HelmetPlateDetector, Detection, helmet_state
from app.cv.ocr import read_plate_detailed, validate_plate_format, warm_up as warm_up_ocr
from app.cv.plate_voter import PlateVoter
from app.cv.tracker import IouTracker
from app.cv.event_correlator import find_correlation_candidate
from app.cv.roi import to_pixel_polygon, filter_by_roi
from app.db import (
    get_vehicle_by_plate, add_violation_event, find_correlation_candidates,
    link_violation_events, mark_correlation_unmatched, get_connection,
    get_gate_roi, set_gate_roi, get_gate_camera_source,
)


# Màu vẽ bounding box
COLOR_HELMET = (0, 255, 0)      # Xanh lá - có mũ
COLOR_NO_HELMET = (0, 0, 255)   # Đỏ - không mũ
COLOR_PLATE = (255, 255, 0)     # Cyan - biển số
COLOR_PERSON = (255, 128, 0)    # Cam - người (COCO)
COLOR_OK = (60, 170, 60)        # Xanh lá - xe đã đăng ký, không lỗi
COLOR_VIOLATION = (40, 40, 220) # Đỏ - có vi phạm
COLOR_REVIEW = (200, 80, 160)   # Tím - biển số cần người kiểm tra
COLOR_PENDING = (0, 160, 230)   # Cam - đang gom bằng chứng
COLOR_PEDESTRIAN = (140, 140, 140)

# Nhãn KHÔNG DẤU vẽ lên video (cv2.putText không hiển thị được tiếng Việt có dấu)
VIOLATION_SHORT_LABELS = {
    'NO_HELMET': 'KHONG MU',
    'PLATE_NOT_REGISTERED': 'BIEN LA',
    'NO_PLATE': 'KHONG BIEN',
    'PLATE_OBSCURED': 'BIEN MO',
    'PLATE_LOW_CONFIDENCE': 'CAN KIEM TRA',
    'RIDING_THROUGH_GATE': 'CHAY XE QUA CONG',
    'TOO_MANY_RIDERS': 'CHO QUA NGUOI',
}
_PLATE_MISSING_TYPES = {'NO_PLATE', 'PLATE_OBSCURED'}
THICKNESS = 2
FONT = cv2.FONT_HERSHEY_SIMPLEX


class VideoPipeline:
    """
    Thread nền xử lý webcam + YOLO detection + vẽ box cho MỘT gate.

    Frame đã xử lý được lưu vào biến dùng chung, có Lock bảo vệ.
    Có queue cho cảnh báo vi phạm qua WebSocket.
    """

    def __init__(self, gate_id: str, gate_config: dict):
        self.gate_id = gate_id
        self.gate_name = gate_config.get("name", gate_id)

        # Lock bảo vệ frame
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        
        # Queue cho cảnh báo vi phạm
        # ponytail: queue là single-consumer — giả định chỉ 1 bảo vệ xem cùng lúc.
        # Nếu cần nhiều người xem đồng thời sau này, đổi sang broadcast
        # (ví dụ: gửi alert tới mọi WS connection thay vì 1 queue).
        self._alert_queue: queue.Queue = queue.Queue()
        
        # Trạng thái
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Khởi tạo webcam
        self._webcam: Optional[WebcamStream] = None
        self._camera_error: Optional[str] = None
        
        # Khởi tạo detectors
        print("[Pipeline] Loading helmet model...")
        # Model mũ bảo hiểm PHẢI có lớp có mũ / không mũ. Bản trong repo từng bị
        # ghi đè nhầm bằng 1 model biển số (lớp duy nhất 'plate') → hệ thống không
        # bao giờ phát hiện được lỗi không đội mũ mà không báo gì. Giờ kiểm tra
        # ngay lúc khởi động: thiếu file / sai model → báo lỗi rõ ràng, hiện cảnh
        # báo trên trang Sức khỏe, các phần khác (biển số, người, xe) vẫn chạy.
        self._helmet_detector = None
        self._helmet_model_classes: list[str] = []
        if os.path.exists(HELMET_MODEL_PATH):
            try:
                self._helmet_detector = HelmetPlateDetector(
                    HELMET_MODEL_PATH, conf_threshold=HELMET_CONF_THRESHOLD, imgsz=DETECT_IMGSZ
                )
                self._helmet_model_classes = [str(n) for n in self._helmet_detector.class_names.values()]
                print("[Pipeline] Helmet model loaded:", self._helmet_detector.class_names)
            except Exception as e:
                print(f"[Pipeline] Không nạp được model mũ bảo hiểm: {e}")
        self._helmet_model_ok = any(helmet_state(n) for n in self._helmet_model_classes)
        if not self._helmet_model_ok:
            reason = (f"KHÔNG phải model mũ bảo hiểm (các lớp: {self._helmet_model_classes})"
                      if self._helmet_model_classes else "không tồn tại hoặc không đọc được")
            print("=" * 78)
            print(f"[Pipeline] LỖI: {HELMET_MODEL_PATH} {reason}.")
            print("[Pipeline] → Tắt phát hiện mũ bảo hiểm. Sửa: chạy  python scripts/prepare_demo.py")
            print("=" * 78)

        print("[Pipeline] Loading plate model...")
        self._plate_detector = HelmetPlateDetector(
            PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD, imgsz=DETECT_IMGSZ
        )
        print("[Pipeline] Plate model loaded:", self._plate_detector.class_names)

        print("[Pipeline] Loading person model (COCO)...")
        self._person_detector = HelmetPlateDetector(
            PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD, imgsz=DETECT_IMGSZ,
            fallback_path="yolov8n.pt" if PERSON_MODEL_PATH != "yolov8n.pt" else None,
        )
        print("[Pipeline] Person model loaded:", self._person_detector.class_names)

        # Chạy 3 model (person/helmet/plate) song song trên frame — đo thật:
        # 304ms -> 172ms/frame (1.77x), vì PyTorch nhả GIL lúc tính toán nặng nên
        # 3 luồng CPU chạy được cùng lúc. Tạo 1 lần, dùng lại mỗi frame.
        self._detect_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix=f"detect-{gate_id}")

        # Pool riêng cho việc lưu snapshot (cv2.imwrite) + ghi log vi phạm vào DB —
        # 2 việc này là I/O (đĩa + sqlite), không cần chờ xong mới đọc frame tiếp
        # theo. Tách khỏi _detect_pool để không tranh chỗ với việc detect model.
        self._io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"io-{gate_id}")

        # Frame counter cho FRAME_SKIP
        self._frame_count = 0

        # Cache kết quả detect để vẽ box mượt giữa các lần detect thật
        self._last_person_dets: list = []
        self._last_helmet_dets: list = []
        self._last_plate_dets: list = []
        
        # Cooldown cho cảnh báo WebSocket
        self._last_alert_time: float = 0.0

        # Cooldown cho ghi log vi phạm vào DB: {(biển số/track, violation_type): last_time}
        self._last_log_time: dict = {}

        # Theo dõi từng người qua nhiều khung hình — mỗi người/xe được gom bằng
        # chứng riêng và ghi vi phạm đúng 1 lần (xem app/cv/tracker.py).
        self._tracker = IouTracker()
        self._track_state: dict[int, dict] = {}
        # Nhãn (biển số, lỗi) vẽ lên video — cache để vẽ lại ở frame bị skip
        self._overlay_labels: list[tuple[tuple, str, tuple]] = []

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
        self._roi_points = get_gate_roi(gate_id)
        self._roi_polygon_px = to_pixel_polygon(self._roi_points, VIDEO_WIDTH, VIDEO_HEIGHT)

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

    def start(self):
        """Bắt đầu thread nền."""
        if self._running:
            print("[Pipeline] Already running")
            return

        print("[Pipeline] Starting...")
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        # Nạp sẵn OCR ở nền — lần đọc biển số đầu tiên không bị khựng vài giây
        threading.Thread(target=warm_up_ocr, daemon=True, name="ocr-warmup").start()
        # Bước 7: start recorder SAU thread chính — push_frame ngay frame đầu tiên
        # (trước mọi early-return trong _run_loop). Xem comment trong _run_loop.
        if self._recorder is not None:
            self._recorder.start()
        print("[Pipeline] Started")

    def stop(self):
        """Dừng thread nền."""
        if not self._running:
            return

        print("[Pipeline] Stopping...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        self._detect_pool.shutdown(wait=False)
        self._io_pool.shutdown(wait=False)
        # Bước 7: stop recorder SAU detect_pool + io_pool — join thread writer,
        # finalize segment cuối (release VideoWriter) trước khi process tắt.
        if self._recorder is not None:
            self._recorder.stop()
        print("[Pipeline] Stopped")
    
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

    def get_status(self) -> dict:
        """Trả về trạng thái sức khỏe của pipeline (dùng cho /api/system/health)."""
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
            "pedestrian_count": self._pedestrian_count,
            "rider_count": self._rider_count,
            "device": DEVICE,
            "helmet_model_ok": self._helmet_model_ok,
            "helmet_model_classes": self._helmet_model_classes,
            "person_model": self._person_detector.model_path,
            "frame_skip": FRAME_SKIP,
            "detect_size": f"{DETECT_WIDTH}x{DETECT_HEIGHT}",
            "camera_error": self._camera_error,
        }
    
    def _open_webcam(self, gate_config: dict):
        return WebcamStream(
            source=gate_config["source"],
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            loop=gate_config.get("loop", True),
            realtime=VIDEO_FILE_REALTIME,
        )

    def _show_message_frame(self, lines: list[str]):
        """Hiện thông báo lỗi ngay trên khung video (thay vì màn hình đen không
        rõ lý do) — bảo vệ/admin nhìn là biết camera đang gặp vấn đề gì."""
        frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
        y = VIDEO_HEIGHT // 2 - 20 * len(lines)
        for text in lines:
            cv2.putText(frame, text[:90], (40, y), FONT, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
            y += 40
        with self._lock:
            self._latest_frame = frame

    def _run_loop(self):
        """Vòng lặp chính của thread nền."""
        gate_config = GATES.get(self.gate_id, {"source": 0, "loop": True, "name": self.gate_id})
        # Mở camera — lỗi thì thử lại mỗi 3s (camera đang bị app khác chiếm, cắm
        # lại USB, RTSP chưa lên...) thay vì dừng hẳn pipeline đến khi restart app.
        while self._running and self._webcam is None:
            try:
                self._webcam = self._open_webcam(gate_config)
                self._camera_error = None
                print("[Pipeline] Webcam opened")
            except Exception as e:
                self._camera_error = str(e)
                print(f"[Pipeline] ERROR: Cannot open webcam: {e} — thử lại sau 3s")
                self._show_message_frame([
                    f"KHONG MO DUOC CAMERA ({self.gate_id})",
                    f"Nguon: {gate_config.get('source')}",
                    "Dang thu lai moi 3 giay... Doi nguon tai /admin/camera",
                ])
                for _ in range(30):
                    if not self._running:
                        return
                    time.sleep(0.1)

        _consecutive_errors = 0
        _RECONNECT_AFTER = 5
        _RECONNECT_BACKOFF_SEC = 2.0

        while self._running:
            try:
                # Đọc frame
                frame = self._webcam.read_frame()
                _consecutive_errors = 0
                self._frame_count += 1
                self._last_frame_time = time.time()

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
                    for bbox, text, color in self._overlay_labels:
                        self._draw_label(frame, bbox, text, color)
                    self._draw_roi(frame)
                    with self._lock:
                        self._latest_frame = frame
                    continue
                
                # Resize nhỏ CHỈ để detect (giữ tốc độ), sau đó quy đổi bbox kết
                # quả về tọa độ ảnh gốc (frame, VIDEO_WIDTH/HEIGHT) — mọi bước sau
                # (OCR, vẽ box, lưu snapshot) đều dùng ảnh gốc nét hơn, không mất
                # tốc độ detect vì detect vẫn chạy trên ảnh nhỏ như cũ.
                t0 = time.perf_counter()
                frame_h, frame_w = frame.shape[:2]
                if frame_w <= DETECT_WIDTH and frame_h <= DETECT_HEIGHT:
                    # Khung đã nhỏ hơn/bằng cỡ detect (GPU detect nguyên ảnh, hoặc
                    # webcam độ phân giải thấp) — không resize/phóng to vô ích
                    detect_frame = frame
                    scale_x = scale_y = 1.0
                else:
                    detect_frame = cv2.resize(frame, (DETECT_WIDTH, DETECT_HEIGHT))
                    scale_x = frame_w / DETECT_WIDTH
                    scale_y = frame_h / DETECT_HEIGHT

                # Chạy person/helmet/plate song song (3 luồng) thay vì tuần tự —
                # cả 3 chỉ cần đúng 1 input là detect_frame, không phụ thuộc lẫn
                # nhau, nên chạy cùng lúc không mất gì ngoài chút CPU thừa ở frame
                # không có người (kết quả helmet/plate lúc đó bị bỏ qua như cũ).
                person_future = self._detect_pool.submit(self._person_detector.detect, detect_frame)
                # Model mũ sai (xem __init__) → không chạy, tránh vẽ box biển số thành "mũ"
                helmet_future = (self._detect_pool.submit(self._helmet_detector.detect, detect_frame)
                                 if self._helmet_model_ok else None)
                plate_future = self._detect_pool.submit(self._plate_detector.detect, detect_frame)

                raw_person_dets = self._rescale_dets(person_future.result(), scale_x, scale_y)
                person_dets = [d for d in raw_person_dets if d.class_name.lower() == 'person']
                vehicle_dets = [d for d in raw_person_dets if d.class_name.lower() in ('motorcycle', 'bicycle')]
                helmet_dets = (self._rescale_dets(helmet_future.result(), scale_x, scale_y)
                               if helmet_future is not None else [])
                plate_dets = self._rescale_dets(plate_future.result(), scale_x, scale_y)

                # Vùng nhận diện (ROI): loại bỏ mọi detection có tâm ngoài vùng đã
                # cấu hình — lọc CẢ helmet/plate (không chỉ person/vehicle), nếu
                # không chúng vẫn được vẽ lên frame ngoài vùng dù không gán được
                # vào person nào (gây cảm giác "vẫn nhận diện ngoài vùng").
                if self._roi_polygon_px is not None:
                    person_dets = filter_by_roi(person_dets, self._roi_polygon_px)
                    vehicle_dets = filter_by_roi(vehicle_dets, self._roi_polygon_px)
                    helmet_dets = filter_by_roi(helmet_dets, self._roi_polygon_px)
                    plate_dets = filter_by_roi(plate_dets, self._roi_polygon_px)

                # Gán ID theo dõi cho từng người (cùng thứ tự person_dets) — gọi cả khi
                # không có ai để tracker biết các track cũ đã rời khung hình.
                now = time.time()
                track_ids = self._tracker.update([d.bbox for d in person_dets], now)

                # Không có person nào → bỏ qua toàn bộ frame (helmet/plate detect
                # phía trên vẫn chạy xong nhưng kết quả không dùng tới, chấp nhận
                # được vì tổng thời gian không tăng — chạy song song mà).
                if not person_dets:
                    self._overlay_labels = []
                    self._last_person_dets = []
                    self._last_helmet_dets = []
                    self._last_plate_dets = []
                    self._last_pose_data = []
                    self._prune_track_state(now)
                    self._draw_roi(frame)
                    with self._lock:
                        self._latest_frame = frame
                    continue

                # Update detection timestamp (health monitoring)
                self._last_detection_time = time.time()

                # Cập nhật cache để nhánh skip vẽ box mượt
                self._last_person_dets = person_dets
                self._last_helmet_dets = helmet_dets
                self._last_plate_dets = plate_dets

                # Gom helmet + plate + loại phương tiện vào từng nhóm theo person
                groups = self._group_by_person(person_dets, helmet_dets, plate_dets, vehicle_dets)
                for group, track_id in zip(groups, track_ids):
                    group['track_id'] = track_id

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

                # Xử lý vi phạm cho TỪNG nhóm riêng biệt — bỏ qua nhóm mà xe (hoặc
                # người, nếu không có xe khớp) còn chạm mép khung hình, tức có thể
                # chưa vào/đang ra hết khung → chưa đủ căn cứ kết luận (đặc biệt
                # NO_PLATE/PLATE_OBSCURED: biển số có thể chỉ chưa kịp lọt vào khung).
                overlay_labels = []
                for group in groups:
                    edge_ref = group.get('_vehicle') or group.get('_person')
                    if edge_ref is not None and self._is_touching_frame_edge(edge_ref.bbox, frame_w, frame_h):
                        continue

                    track_id = group.get('track_id')
                    state = self._track_state.setdefault(track_id, self._new_track_state())
                    state['frames'] += 1
                    state['last_seen'] = now

                    summary = self._process_violations(
                        frame,
                        group['helmet_dets'],
                        group['plate_dets'],
                        posture_status=group.get('posture_status', 'unknown'),
                        vehicle_type=group.get('vehicle_type'),
                        too_many_riders=group.get('too_many_riders', False),
                        track_id=track_id,
                    )
                    overlay_labels.extend(self._labels_for_group(group, summary))
                self._overlay_labels = overlay_labels
                self._prune_track_state(now)

                # Vẽ box helmet (theo nhóm)
                for det in helmet_dets:
                    self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)

                # Vẽ box plate (theo nhóm)
                for det in plate_dets:
                    self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)

                # Vẽ box person (cam) — SAU khi OCR đã xong
                for det in person_dets:
                    self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)

                # Nhãn biển số + lỗi của từng người/xe (vẽ sau cùng để nằm trên box)
                for bbox, text, color in overlay_labels:
                    self._draw_label(frame, bbox, text, color)

                self._draw_roi(frame)

                # Feature 7: record frame timing + Feature 4: buffer frame for clip
                self._frame_timestamps.append(time.time())
                # Resize down before buffering to save RAM (640x360 = ~1/4 of 1280x720)
                small = cv2.resize(frame, (640, 360))
                self._clip_buffer.append(small)
                self._last_process_latency_ms = (time.perf_counter() - t0) * 1000

                # Lưu frame đã vẽ
                with self._lock:
                    self._latest_frame = frame
                    
            except Exception as e:
                print(f"[Pipeline] Error in loop: {e}")
                _consecutive_errors += 1
                if _consecutive_errors >= _RECONNECT_AFTER:
                    print(f"[Pipeline] {_consecutive_errors} consecutive read failures — reconnecting camera")
                    try:
                        self._webcam.release()
                    except Exception:
                        pass
                    try:
                        self._webcam = self._open_webcam(gate_config)
                        self._camera_error = None
                        print("[Pipeline] Webcam reconnected")
                    except Exception as reconnect_err:
                        self._camera_error = str(reconnect_err)
                        print(f"[Pipeline] Reconnect failed: {reconnect_err}")
                        self._show_message_frame([
                            f"MAT KET NOI CAMERA ({self.gate_id})",
                            "Dang thu ket noi lai...",
                        ])
                    _consecutive_errors = 0
                    time.sleep(_RECONNECT_BACKOFF_SEC)
                else:
                    time.sleep(0.1)

        # Cleanup
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

    def _group_by_person(self, person_dets: list, helmet_dets: list,
                         plate_dets: list, vehicle_dets: list = ()) -> list[dict]:
        """
        Gom helmet + plate + loại phương tiện vào từng nhóm theo person box.

        Logic:
        - helmet/no-helmet → gán vào person mà tâm điểm helmet nằm trong box person.
        - plate → gán vào person có x-center gần nhất, trong phạm vi chiều rộng box person.
        - vehicle (motorcycle/bicycle, COCO) → x-center gần nhất trong phạm vi chiều rộng
          person, VÀ phải chồng lấp trục Y với person (xem `_vertical_overlap`) — thêm
          điều kiện Y để giảm gán nhầm người đi bộ đứng gần xe máy thành người đang lái
          (chỉ so X trước đây dễ khớp nhầm khi người đi bộ tình cờ thẳng hàng X với 1
          xe máy khác ở "độ sâu" khác trong khung hình). Dùng để loại trừ người đi bộ
          và người đi xe đạp thường khỏi việc bắt buộc đội mũ (chỉ xe máy và xe đạp
          điện mới bắt buộc theo luật — COCO không phân biệt được xe đạp điện với xe
          đạp thường, nên hiện tại coi mọi 'bicycle' là được miễn, giới hạn đã biết).

        Trả về list nhóm, mỗi nhóm: {helmet_dets: [...], plate_dets: [...], vehicle_type: str|None}.
        """
        groups = []

        for person in person_dets:
            px1, py1, px2, py2 = person.bbox
            pcx = (px1 + px2) / 2   # person center x
            pcy = (py1 + py2) / 2   # person center y
            p_width = px2 - px1

            group_helmets = []
            group_plates = []

            # Gán helmet: tâm helmet nằm trong box person
            for h in helmet_dets:
                hx1, hy1, hx2, hy2 = h.bbox
                hcx = (hx1 + hx2) / 2
                hcy = (hy1 + hy2) / 2
                if px1 <= hcx <= px2 and py1 <= hcy <= py2:
                    group_helmets.append(h)

            # Gán plate: x-center gần nhất, trong phạm vi chiều rộng person
            best_dist = float('inf')
            best_plate = None
            for p in plate_dets:
                bx1, by1, bx2, by2 = p.bbox
                bpcx = (bx1 + bx2) / 2
                dist = abs(bpcx - pcx)
                if dist < best_dist and dist <= p_width:
                    best_dist = dist
                    best_plate = p
            if best_plate is not None:
                group_plates.append(best_plate)

            # Gán phương tiện: x-center gần nhất, trong phạm vi chiều rộng person
            best_v_dist = float('inf')
            vehicle_type = None
            matched_vehicle = None
            for v in vehicle_dets:
                vx1, vy1, vx2, vy2 = v.bbox
                vcx = (vx1 + vx2) / 2
                dist = abs(vcx - pcx)
                if (dist < best_v_dist and dist <= p_width
                        and self._vertical_overlap(person.bbox, v.bbox)):
                    best_v_dist = dist
                    vehicle_type = v.class_name.lower()
                    matched_vehicle = v

            # Dự phòng: COCO bỏ sót xe máy (xe bị người/xe khác che, góc khuất)
            # nhưng có BIỂN SỐ nằm ngay phần dưới người này → chắc chắn đang đi
            # xe máy (người đi bộ không mang biển số). Trước đây người này bị coi
            # là người đi bộ → mất hết vi phạm của xe đó. Điều kiện thận trọng:
            # tâm biển nằm trong bề ngang người, từ giữa thân xuống tới dưới chân
            # thêm 30% chiều cao người (biển sau xe nằm thấp hơn chỗ ngồi).
            if vehicle_type is None and group_plates:
                bx1, by1, bx2, by2 = group_plates[0].bbox
                bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
                p_height = py2 - py1
                if px1 <= bcx <= px2 and pcy <= bcy <= py2 + 0.3 * p_height:
                    vehicle_type = 'motorcycle'

            groups.append({
                '_person': person,
                '_vehicle': matched_vehicle,
                'helmet_dets': group_helmets,
                'plate_dets': group_plates,
                'vehicle_type': vehicle_type,
            })

        return groups

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

    def _read_plate_voted(self, frame: np.ndarray, plate_det: Detection, key=None):
        """Đọc biển số qua PlateVoter (đa khung hình + confidence). Trả về
        PlateReadResult — xem app/cv/plate_voter.py. key = khóa gom phiếu (ID
        theo dõi của xe), None = gom theo vị trí như cũ."""
        return self._plate_voter.read(frame, plate_det, read_plate_detailed, key=key)

    @staticmethod
    def _new_track_state() -> dict:
        """Bằng chứng gom qua nhiều khung hình cho 1 người/xe (1 track)."""
        return {
            'frames': 0, 'last_seen': 0.0, 'logged': False,
            'helmet_with': 0, 'helmet_without': 0,
            'posture': {'riding': 0, 'standing': 0},
            'too_many_riders': 0, 'plate_seen': 0,
            'best_plate': None,  # (text, confidence, is_confident)
        }

    def _prune_track_state(self, now: float, max_idle_sec: float = 30.0) -> None:
        """Xoá bằng chứng của người/xe đã rời khung hình lâu (không phình RAM)."""
        stale = [tid for tid, st in self._track_state.items() if now - st['last_seen'] > max_idle_sec]
        for tid in stale:
            del self._track_state[tid]

    def _process_violations(self, frame: np.ndarray, helmet_dets: list, plate_dets: list,
                         posture_status: str = 'unknown', vehicle_type: str | None = None,
                         too_many_riders: bool = False, track_id: int | None = None) -> dict | None:
        """
        Xử lý toàn bộ logic vi phạm cho MỘT nhóm (1 person):
        0. Chặn theo loại phương tiện — không có xe hoặc đi xe đạp thì không bắt mũ/biển số
        1. OCR đọc biển số
        2. Tra whitelist trong DB
        3. Xác định violation_type theo thứ tự ưu tiên trong PLAN.md
        4. Chống ghi trùng (1 lần/người-xe theo track_id + cooldown theo biển số)
        5. Lưu snapshot + ghi log vào DB
        6. Đẩy cảnh báo WebSocket

        track_id (từ app/cv/tracker.py): có thì mũ/tư thế/biển số được GOM QUA
        NHIỀU KHUNG HÌNH của cùng người đó và chỉ kết luận sau TRACK_MIN_FRAMES lần
        thấy — không kết luận vội từ 1 khung hình nhiễu. None = xét riêng từng
        khung hình như trước (dùng trong test).

        Trả về tóm tắt để vẽ nhãn lên video: {'plate', 'registered', 'review',
        'violations', 'logged', 'pending'}, hoặc None nếu là người đi bộ/xe đạp.
        """
        # Không phát hiện xe máy/xe đạp nào gần người này → người đi bộ, không bắt lỗi
        # mũ bảo hiểm/biển số. Trước đây thiếu bước này nên người đi bộ qua cổng bị báo
        # PLATE_UNREADABLE sai (mọi group đều bị coi như phải có biển số đọc được).
        if vehicle_type is None:
            return None

        # Xe đạp thường không bắt buộc đội mũ bảo hiểm theo luật, chỉ xe máy và xe đạp
        # điện mới bắt buộc. COCO không phân biệt được xe đạp điện với xe đạp thường,
        # nên hiện tại coi mọi 'bicycle' là được miễn — đây là giới hạn đã biết, sẽ cần
        # dataset/model riêng để phân biệt xe đạp điện khi có.
        if vehicle_type == 'bicycle':
            return None

        state = self._track_state.get(track_id) if track_id is not None else None

        # Phân loại helmet detections của khung hình này
        frame_with_helmet = any(helmet_state(d.class_name) == 'with' for d in helmet_dets)
        frame_without_helmet = any(helmet_state(d.class_name) == 'without' for d in helmet_dets)

        # Đọc biển số từ plate detections (chỉ 1 plate gán vào nhóm này) — vote qua
        # nhiều khung hình + confidence (xem _read_plate_voted / app/cv/plate_voter.py)
        frame_plate_text = ""
        frame_plate_conf = None
        frame_plate_confident = False
        already_confident = (state is not None and state['best_plate'] is not None
                             and state['best_plate'][2])
        if plate_dets and not already_confident:
            # (Đã đọc được biển chắc chắn cho người/xe này rồi thì không OCR lại
            # mỗi khung hình nữa — OCR tốn ~0.4s/lần trên CPU, để dành cho xe khác)
            best_plate = plate_dets[0]  # Đã được gán ở _group_by_person
            vote_key = ('track', track_id) if state is not None else None
            plate_result = self._read_plate_voted(frame, best_plate, key=vote_key)
            frame_plate_text = plate_result.text
            frame_plate_conf = plate_result.confidence if frame_plate_text else None
            frame_plate_confident = bool(frame_plate_text) and plate_result.is_confident
            # Feature 7: track plate read attempts/successes
            self._plate_attempts += 1
            if frame_plate_text:
                self._plate_successes += 1

        if state is None:
            # Xét riêng khung hình này (hành vi cũ)
            has_with_helmet, has_without_helmet = frame_with_helmet, frame_without_helmet
            plate_seen = bool(plate_dets)
            plate_read, plate_confidence, plate_confident = frame_plate_text, frame_plate_conf, frame_plate_confident
        else:
            # Gom bằng chứng qua nhiều khung hình của cùng 1 người/xe
            state['helmet_with'] += frame_with_helmet
            state['helmet_without'] += frame_without_helmet
            if posture_status in state['posture']:
                state['posture'][posture_status] += 1
            state['too_many_riders'] += bool(too_many_riders)
            state['plate_seen'] += bool(plate_dets)
            if frame_plate_text:
                best = state['best_plate']
                better = (best is None
                          or (frame_plate_confident and not best[2])
                          or (frame_plate_confident == best[2] and (frame_plate_conf or 0) > best[1]))
                if better:
                    state['best_plate'] = (frame_plate_text, frame_plate_conf or 0.0, frame_plate_confident)

            has_with_helmet = state['helmet_with'] > 0 and state['helmet_with'] >= state['helmet_without']
            has_without_helmet = state['helmet_without'] > state['helmet_with']
            riding, standing = state['posture']['riding'], state['posture']['standing']
            if riding > standing:
                posture_status = 'riding'
            elif standing > riding:
                posture_status = 'standing'
            elif riding == 0:
                posture_status = 'unknown'
            # hòa (>0) → giữ tư thế của khung hình hiện tại
            too_many_riders = state['too_many_riders'] * 2 >= state['frames'] > 0 and state['too_many_riders'] > 0
            plate_seen = state['plate_seen'] > 0
            if state['best_plate'] is not None:
                plate_read, plate_confidence, plate_confident = state['best_plate']
            else:
                plate_read, plate_confidence, plate_confident = "", None, False

        needs_review = bool(plate_read) and not plate_confident

        # Tra whitelist — KHÔNG tra khi needs_review=True: 1 lần đọc mơ hồ/lệch
        # nhau giữa các frame không đủ tin cậy để gán vào 1 học sinh cụ thể. Đây
        # là chỗ áp dụng "không tự đoán" — thà để needs_review cho người kiểm tra
        # còn hơn tự khớp nhầm biển số.
        plate_matched = None
        if plate_read and not needs_review:
            vehicle = get_vehicle_by_plate(plate_read)
            if vehicle:
                plate_matched = vehicle['plate_number']

        # Cờ tham khảo: biển đọc được có khớp định dạng VN phổ biến không.
        # Không dùng để loại bỏ plate_read — chỉ để bảo vệ lưu ý khi xem lại.
        plate_format_valid = validate_plate_format(plate_read) if plate_read else None

        # Xác định helmet_status
        if has_with_helmet:
            helmet_status = "helmet"
        elif has_without_helmet:
            helmet_status = "no_helmet"
        else:
            helmet_status = "unknown"

        # Xác định violation_type theo thứ tự ưu tiên trong PLAN.md
        violation_types = []

        # 1. Không có plate_det → xe không có biển số trong khung hình
        if not plate_seen:
            violation_types.append("NO_PLATE")
        # 2. Có box biển số nhưng OCR đọc rỗng → bị che/mờ/hỏng
        elif not plate_read:
            violation_types.append("PLATE_OBSCURED")
        # 3. Đọc được nhưng không đủ tin cậy (đa khung hình không đồng nhất /
        # confidence thấp) → cần người kiểm tra, KHÔNG khẳng định là biển lạ
        elif needs_review:
            violation_types.append("PLATE_LOW_CONFIDENCE")

        # 4. Đọc được, đủ tin cậy, nhưng không tìm thấy trong whitelist
        if plate_read and not needs_review and not plate_matched:
            violation_types.append("PLATE_NOT_REGISTERED")

        # 5. Không có mũ bảo hiểm (có Without Helmet mà không có With Helmet).
        # Dắt bộ xe (posture == 'standing') không bắt buộc đội mũ theo luật —
        # chỉ bắt lỗi khi đang ngồi lái (riding) hoặc không xác định được tư thế
        # (unknown, giữ hành vi cũ để không bỏ sót khi pose detection thất bại).
        if has_without_helmet and not has_with_helmet and posture_status != 'standing':
            violation_types.append("NO_HELMET")

        # 6. Tư thế đang ngồi xe (riding) + có helmet → vi phạm đặc biệt
        if posture_status == 'riding' and has_with_helmet and not has_without_helmet:
            violation_types.append("RIDING_THROUGH_GATE")

        # 7. Tư thế đang ngồi xe (riding) + không helmet → cũng là riding
        if posture_status == 'riding' and not has_with_helmet:
            if "NO_HELMET" in violation_types:
                violation_types.remove("NO_HELMET")
            if "RIDING_THROUGH_GATE" not in violation_types:
                violation_types.append("RIDING_THROUGH_GATE")

        # 8. Chở quá số người quy định (đếm sẵn ở _count_riders_per_vehicle)
        if too_many_riders:
            violation_types.append("TOO_MANY_RIDERS")

        summary = {
            'plate': plate_read,
            'registered': bool(plate_matched),
            'review': needs_review,
            'violations': list(violation_types),
            'logged': False,
            'pending': False,
        }

        # Nếu không có vi phạm nào → không làm gì
        if not violation_types:
            return summary

        if state is not None:
            # Người/xe này đã được ghi vi phạm trong lượt đi qua hiện tại → không
            # ghi/cảnh báo lặp lại mỗi khung hình
            if state['logged']:
                summary['logged'] = True
                return summary
            # Chưa đủ số lần thấy để kết luận → chờ thêm bằng chứng (biển số có thể
            # chưa kịp lọt vào khung/chưa đọc rõ, mũ/tư thế có thể nhiễu 1 khung)
            if state['frames'] < TRACK_MIN_FRAMES:
                summary['pending'] = True
                return summary

        # Gộp violation_type nếu nhiều điều kiện cùng đúng — danh sách lỗi cụ thể
        # vẫn được lưu riêng (violation_details) để giao diện hiện RÕ từng lỗi
        if len(violation_types) > 1:
            violation_type = "MULTIPLE"
        else:
            violation_type = violation_types[0]
        violation_details = ",".join(violation_types)

        # Chống ghi trùng cùng 1 xe qua nhiều track (mất dấu rồi bắt lại, 2 người
        # trên cùng 1 xe...): cooldown theo (biển số, loại lỗi). Xe không đọc được
        # biển số dùng ID theo dõi làm khóa — trước đây mọi xe không biển dùng
        # chung khóa "UNKNOWN" nên xe thứ 2, 3... trong cùng 60s bị BỎ SÓT.
        identity = plate_matched or plate_read or (f"track:{track_id}" if track_id is not None else "UNKNOWN")
        cooldown_key = (identity, violation_type)
        current_time = time.time()
        last_log = self._last_log_time.get(cooldown_key, 0)
        if current_time - last_log < VIOLATION_COOLDOWN:
            if state is not None:
                state['logged'] = True
            summary['logged'] = True
            return summary

        # Chuẩn bị đường dẫn snapshot (rẻ, làm ngay ở main thread)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        snapshot_filename = f"{timestamp_str}_{self.gate_id}_{violation_type}.jpg"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

        # Lưu snapshot (cv2.imwrite) + ghi log DB — đẩy ra _io_pool (thread nền)
        # vì đây là I/O tốn vài chục ms, không cần chặn vòng lặp đọc frame tiếp
        # theo để chờ ghi đĩa/DB xong. Copy frame TRƯỚC khi đẩy đi: _run_loop sẽ
        # vẽ box đè lên chính frame này ngay sau khi hàm này return — snapshot
        # phải là ảnh gốc chưa vẽ box, không copy sẽ lưu nhầm ảnh có box.
        frame_snapshot = frame.copy()
        initial_status = 'needs_review' if needs_review else 'pending'
        self._io_pool.submit(
            self._persist_violation,
            frame_snapshot, snapshot_path, snapshot_filename,
            plate_read, plate_matched, helmet_status, violation_type,
            posture_status, plate_format_valid,
            plate_confidence, self.gate_id, initial_status,
            violation_details,
        )

        # Cập nhật cooldown ngay (không chờ IO xong) — tránh spam ghi khi nhiều
        # group/frame liên tiếp rơi vào lúc thread nền đang xử lý phía sau.
        self._last_log_time[cooldown_key] = current_time
        if state is not None:
            state['logged'] = True
        summary['logged'] = True

        # Đẩy cảnh báo WebSocket ngay — coi snapshot là sẽ ghi thành công
        # (best-effort: đã tạo thư mục trước, imwrite hiếm khi lỗi) để không
        # phải chờ IO thread ghi xong mới cảnh báo bảo vệ. Mỗi vi phạm MỚI đều
        # cảnh báo (force) — đã chống lặp ở trên nên không sợ spam.
        self._push_alert(
            violation_type, plate_read, plate_matched,
            snapshot_filename=snapshot_filename,
            plate_format_valid=plate_format_valid,
            violation_details=violation_types,
            force=True,
        )
        return summary

    @staticmethod
    def _format_plate(text: str) -> str:
        """'59K165072' → '59K1-650.72' cho dễ đọc trên video."""
        if validate_plate_format(text) and len(text) >= 8:
            head, tail = text[:4], text[4:]
            if len(tail) == 5:
                return f"{head}-{tail[:3]}.{tail[3:]}"
            return f"{head}-{tail}"
        return text

    def _labels_for_group(self, group: dict, summary: dict | None) -> list[tuple[tuple, str, tuple]]:
        """Nhãn vẽ lên video cho 1 người: ID + đi bộ/đi xe + lỗi; biển số (xanh =
        đã đăng ký, đỏ = biển lạ, tím = cần kiểm tra)."""
        labels = []
        person = group.get('_person')
        track_id = group.get('track_id')
        tid = f"#{track_id} " if track_id is not None else ""
        if person is not None:
            if summary is None:
                kind = "DI BO" if group.get('vehicle_type') is None else "XE DAP"
                labels.append((person.bbox, f"{tid}{kind}", COLOR_PEDESTRIAN))
            elif summary['violations']:
                text = ", ".join(VIOLATION_SHORT_LABELS.get(v, v) for v in summary['violations'])
                color = COLOR_VIOLATION
                if summary['pending'] and not summary['logged']:
                    text = f"dang xet: {text}"
                    color = COLOR_PENDING
                labels.append((person.bbox, f"{tid}{text}", color))
            else:
                labels.append((person.bbox, f"{tid}XE MAY - OK", COLOR_OK))

        plate_dets = group.get('plate_dets') or []
        if summary is not None and plate_dets and summary['plate']:
            if summary['registered']:
                color, suffix = COLOR_OK, " DA DANG KY"
            elif summary['review']:
                color, suffix = COLOR_REVIEW, " ?"
            else:
                color, suffix = COLOR_VIOLATION, " CHUA DANG KY"
            labels.append((plate_dets[0].bbox, self._format_plate(summary['plate']) + suffix, color))
        return labels

    @staticmethod
    def _draw_label(frame: np.ndarray, bbox: tuple, text: str, color: tuple):
        """Vẽ nhãn chữ trắng trên nền màu, ngay trên box (hoặc dưới nếu sát mép trên)."""
        x1, y1 = int(bbox[0]), int(bbox[1])
        scale, thickness = 0.6, 2
        (tw, th), baseline = cv2.getTextSize(text, FONT, scale, thickness)
        top = y1 - th - baseline - 6
        if top < 0:
            top = int(bbox[3]) + 2
        x1 = max(0, min(x1, frame.shape[1] - tw - 6))
        cv2.rectangle(frame, (x1, top), (x1 + tw + 6, top + th + baseline + 6), color, -1)
        cv2.putText(frame, text, (x1 + 3, top + th + 3), FONT, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    def _write_clip(self, frames: list, out_path: str):
        """Write video clip from buffered frames. Runs on _io_pool (Feature 4)."""
        if not frames:
            return
        h, w = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, VIOLATION_CLIP_FPS, (w, h))
        for f in frames:
            writer.write(f)
        writer.release()

    def _persist_violation(self, frame: np.ndarray, snapshot_path: str, snapshot_filename: str,
                            plate_read: str, plate_matched: str | None, helmet_status: str,
                            violation_type: str, posture_status: str,
                            plate_format_valid: bool | None,
                            plate_confidence: float | None = None,
                            gate_id: str | None = None,
                            status: str = 'pending',
                            violation_details: str | None = None):
        """Lưu snapshot + ghi log vi phạm vào DB. Chạy trên _io_pool (thread nền).

        Sau khi insert xong, submit try_correlate (cũng qua _io_pool — không
        thêm thread mới) để ghép với event từ camera kia. Chuỗi: insert →
        correlation → return. Correlation chạy nền độc lập với detect loop,
        lỗi của correlation không ảnh hưởng pipeline chính.
        """
        success = cv2.imwrite(snapshot_path, frame)

        # Feature 4: write video clip (reuse _io_pool, same thread as snapshot)
        clip_path = None
        clip_filename = snapshot_filename.replace('.jpg', '.mp4')
        clip_full_path = os.path.join(SNAPSHOTS_DIR, clip_filename)
        self._write_clip(list(self._clip_buffer), clip_full_path)
        if os.path.exists(clip_full_path):
            clip_path = f"data/snapshots/{clip_filename}"

        try:
            new_id = add_violation_event(
                timestamp=datetime.datetime.now().isoformat(),
                plate_read=plate_read,
                plate_matched=plate_matched,
                helmet_status=helmet_status,
                violation_type=violation_type,
                snapshot_path=f"data/snapshots/{snapshot_filename}" if success else None,
                posture_status=posture_status,
                plate_format_valid=plate_format_valid,
                clip_path=clip_path,
                plate_confidence=plate_confidence,
                gate_id=gate_id,
                status=status,
                violation_details=violation_details,
            )
            print(f"[Pipeline] Violation logged: {violation_details or violation_type}, "
                  f"plate={plate_read or 'N/A'}, gate={gate_id}, id={new_id}")

            # Bước 3: ghép với camera kia. Submit ngay trong _io_pool để không
            # block detect loop — correlation chỉ là query+update nhẹ.
            # Nếu chỉ có 1 gate (gate_id None), find_correlation_candidates trả [].
            if gate_id:
                new_event = {
                    "id": new_id,
                    "gate_id": gate_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "plate_read": plate_read,
                    "plate_matched": plate_matched,
                    "status": status,
                }
                self._io_pool.submit(self._try_correlate, new_event)
        except Exception as e:
            print(f"[Pipeline] Error logging violation: {e}")

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

    def _push_alert(self, violation_type: str, plate_read: str, plate_matched: str,
                     snapshot_filename: str | None = None, plate_format_valid: bool | None = None,
                     violation_details: list[str] | None = None, force: bool = False):
        """Đẩy cảnh báo vi phạm vào WebSocket queue (có alert cooldown, trừ khi
        force=True — dùng cho vi phạm mới được ghi, đã chống lặp ở nơi gọi)."""
        current_time = time.time()
        if force or current_time - self._last_alert_time >= ALERT_COOLDOWN:
            alert = {
                "type": "violation",
                "violation_type": violation_type,
                "violation_details": violation_details or [violation_type],
                "gate_id": getattr(self, "gate_id", None),
                "gate_name": getattr(self, "gate_name", None),
                "plate_read": plate_read or None,
                "plate_matched": plate_matched or None,
                "plate_format_valid": plate_format_valid,
                "snapshot_url": f"/media/{snapshot_filename}" if snapshot_filename else None,
                "timestamp": datetime.datetime.now().isoformat(),
            }
            self._alert_queue.put(alert)
            self._last_alert_time = current_time
            print(f"[Pipeline] Alert pushed: {alert}")

    def _run_posture_detection(self, frame: np.ndarray, groups: list) -> list:
        """
        Chạy pose detection cho mỗi person box trong groups.
        Bổ sung 'posture_status' vào mỗi group dict.
        Hoàn toàn isolated trong try/except để không ảnh hưởng pipeline chính.

        Chạy SONG SONG qua _detect_pool (đã rảnh vào lúc này — 3 future của
        person/helmet/plate đã .result() xong ở _run_loop) thay vì tuần tự từng
        người: N person trong khung hình trước đây = N lần inference YOLO-pose
        nối tiếp nhau, cộng dồn latency tuyến tính theo số người. pose.py dùng
        model instance riêng theo thread (thread-local) nên gọi đồng thời an
        toàn, không tranh chấp state giữa các thread như dùng chung 1 instance.
        """
        try:
            from app.cv.pose import PostureDetector, classify_posture

            detector = PostureDetector()
            frame_h, frame_w = frame.shape[:2]

            # Cắt crop hợp lệ trước, chỉ submit những group thực sự cần detect
            pending = []
            for group in groups:
                person = group.get('_person')
                if person is None:
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

                future = self._detect_pool.submit(detector.detect_pose, person_crop)
                pending.append((group, (x1, y1), future))

            pose_data = []
            for group, offset, future in pending:
                keypoints = future.result()
                posture = classify_posture(keypoints) if keypoints else 'unknown'
                group['posture_status'] = posture
                if keypoints:
                    self._draw_pose_keypoints(frame, keypoints, offset=offset)
                    pose_data.append((keypoints, offset))
            self._last_pose_data = pose_data

        except Exception:
            # ISOLATED: posture errors must not break the main pipeline
            for group in groups:
                if 'posture_status' not in group:
                    group['posture_status'] = 'unknown'

        return groups

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
        # DB lưu dạng chuỗi — "0"/"1" phải đổi về int, nếu không WebcamStream
        # coi là đường dẫn file và không mở được webcam.
        gate_config["source"] = int(saved_source) if saved_source.strip().isdigit() else saved_source
    pipeline = VideoPipeline(gate_id, gate_config)
    _pipelines[gate_id] = pipeline
    return pipeline


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
