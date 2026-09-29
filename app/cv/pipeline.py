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
)
from app.cv.capture import WebcamStream
from app.cv.detector import HelmetPlateDetector, Detection
from app.cv.ocr import read_plate, validate_plate_format
from app.db import get_vehicle_by_plate, add_violation_event


# Màu vẽ bounding box
COLOR_HELMET = (0, 255, 0)      # Xanh lá - có mũ
COLOR_NO_HELMET = (0, 0, 255)   # Đỏ - không mũ
COLOR_PLATE = (255, 255, 0)     # Cyan - biển số
COLOR_PERSON = (255, 128, 0)    # Cam - người (COCO)
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
        
        # Khởi tạo detectors
        print("[Pipeline] Loading helmet model...")
        self._helmet_detector = HelmetPlateDetector(
            HELMET_MODEL_PATH, conf_threshold=HELMET_CONF_THRESHOLD
        )
        print("[Pipeline] Helmet model loaded:", self._helmet_detector.class_names)
        
        print("[Pipeline] Loading plate model...")
        self._plate_detector = HelmetPlateDetector(
            PLATE_MODEL_PATH, conf_threshold=PLATE_CONF_THRESHOLD
        )
        print("[Pipeline] Plate model loaded:", self._plate_detector.class_names)

        print("[Pipeline] Loading person model (COCO)...")
        self._person_detector = HelmetPlateDetector(
            PERSON_MODEL_PATH, conf_threshold=PERSON_CONF_THRESHOLD
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

        # Cooldown cho ghi log vi phạm vào DB: {(plate_type, violation_type): last_time}
        self._last_log_time: dict = {}

        # Cache OCR gần nhất theo vị trí biển số trên khung hình — EasyOCR chạy
        # CPU tốn 300-800ms/lần; nếu chạy lại mỗi frame detect cho CÙNG 1 xe đang
        # đứng/đi qua cổng ở gần đúng vị trí cũ thì lãng phí toàn bộ thời gian đó
        # và làm nghẽn cả vòng lặp đọc frame. Key: ô lưới thô quanh tâm bbox biển
        # số, TTL ngắn vì xe di chuyển qua khung hình khá nhanh.
        self._plate_ocr_cache: dict = {}

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

        # Feature 4: ring buffer for violation video clips
        self._clip_buffer: deque = deque(maxlen=VIOLATION_CLIP_SECONDS * VIOLATION_CLIP_FPS)

    def start(self):
        """Bắt đầu thread nền."""
        if self._running:
            print("[Pipeline] Already running")
            return
        
        print("[Pipeline] Starting...")
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
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
        print("[Pipeline] Stopped")
    
    def get_frame(self) -> Optional[np.ndarray]:
        """
        Lấy frame mới nhất đã xử lý.
        Trả về None nếu chưa có frame.
        """
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None
    
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
        }
    
    def _open_webcam(self, gate_config: dict):
        return WebcamStream(
            source=gate_config["source"],
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            loop=gate_config.get("loop", True),
        )

    def _run_loop(self):
        """Vòng lặp chính của thread nền."""
        gate_config = GATES.get(self.gate_id, {"source": 0, "loop": True, "name": self.gate_id})
        try:
            self._webcam = self._open_webcam(gate_config)
            print("[Pipeline] Webcam opened")
        except Exception as e:
            print(f"[Pipeline] ERROR: Cannot open webcam: {e}")
            self._running = False
            return

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
                
                # Xử lý cách frame
                if self._frame_count % FRAME_SKIP != 0:
                    # Vẽ box từ cache (kết quả detect gần nhất) lên frame hiện tại
                    for det in self._last_helmet_dets:
                        self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)
                    for det in self._last_plate_dets:
                        self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)
                    for det in self._last_person_dets:
                        self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)
                    with self._lock:
                        self._latest_frame = frame
                    continue
                
                # Resize nhỏ CHỈ để detect (giữ tốc độ), sau đó quy đổi bbox kết
                # quả về tọa độ ảnh gốc (frame, VIDEO_WIDTH/HEIGHT) — mọi bước sau
                # (OCR, vẽ box, lưu snapshot) đều dùng ảnh gốc nét hơn, không mất
                # tốc độ detect vì detect vẫn chạy trên ảnh nhỏ như cũ.
                t0 = time.perf_counter()
                frame_h, frame_w = frame.shape[:2]
                detect_frame = cv2.resize(frame, (DETECT_WIDTH, DETECT_HEIGHT))
                scale_x = frame_w / DETECT_WIDTH
                scale_y = frame_h / DETECT_HEIGHT

                # Chạy person/helmet/plate song song (3 luồng) thay vì tuần tự —
                # cả 3 chỉ cần đúng 1 input là detect_frame, không phụ thuộc lẫn
                # nhau, nên chạy cùng lúc không mất gì ngoài chút CPU thừa ở frame
                # không có người (kết quả helmet/plate lúc đó bị bỏ qua như cũ).
                person_future = self._detect_pool.submit(self._person_detector.detect, detect_frame)
                helmet_future = self._detect_pool.submit(self._helmet_detector.detect, detect_frame)
                plate_future = self._detect_pool.submit(self._plate_detector.detect, detect_frame)

                raw_person_dets = self._rescale_dets(person_future.result(), scale_x, scale_y)
                person_dets = [d for d in raw_person_dets if d.class_name.lower() == 'person']
                vehicle_dets = [d for d in raw_person_dets if d.class_name.lower() in ('motorcycle', 'bicycle')]
                helmet_dets = self._rescale_dets(helmet_future.result(), scale_x, scale_y)
                plate_dets = self._rescale_dets(plate_future.result(), scale_x, scale_y)

                # Không có person nào → bỏ qua toàn bộ frame (helmet/plate detect
                # phía trên vẫn chạy xong nhưng kết quả không dùng tới, chấp nhận
                # được vì tổng thời gian không tăng — chạy song song mà).
                if not person_dets:
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

                # Đếm số người/xe — đánh dấu chở quá số người quy định
                self._count_riders_per_vehicle(groups)

                # Phát hiện tư thế cho mỗi person box — ISOLATED try/except
                groups = self._run_posture_detection(frame, groups)

                # Xử lý vi phạm cho TỪNG nhóm riêng biệt
                for group in groups:
                    self._process_violations(
                        frame,
                        group['helmet_dets'],
                        group['plate_dets'],
                        posture_status=group.get('posture_status', 'unknown'),
                        vehicle_type=group.get('vehicle_type'),
                        too_many_riders=group.get('too_many_riders', False),
                    )

                # Vẽ box helmet (theo nhóm)
                for det in helmet_dets:
                    self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)

                # Vẽ box plate (theo nhóm)
                for det in plate_dets:
                    self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)

                # Vẽ box person (cam) — SAU khi OCR đã xong
                for det in person_dets:
                    self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)

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
                        print("[Pipeline] Webcam reconnected")
                    except Exception as reconnect_err:
                        print(f"[Pipeline] Reconnect failed: {reconnect_err}")
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

    def _group_by_person(self, person_dets: list, helmet_dets: list,
                         plate_dets: list, vehicle_dets: list = ()) -> list[dict]:
        """
        Gom helmet + plate + loại phương tiện vào từng nhóm theo person box.

        Logic:
        - helmet/no-helmet → gán vào person mà tâm điểm helmet nằm trong box person.
        - plate → gán vào person có x-center gần nhất, trong phạm vi chiều rộng box person.
        - vehicle (motorcycle/bicycle, COCO) → cùng cách gán như plate; dùng để loại trừ
          người đi bộ và người đi xe đạp thường khỏi việc bắt buộc đội mũ (chỉ xe máy và
          xe đạp điện mới bắt buộc theo luật — COCO không phân biệt được xe đạp điện với
          xe đạp thường, nên hiện tại coi mọi 'bicycle' là được miễn, đây là giới hạn đã biết).

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
                if dist < best_v_dist and dist <= p_width:
                    best_v_dist = dist
                    vehicle_type = v.class_name.lower()
                    matched_vehicle = v

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

    _OCR_CACHE_GRID = 60      # px — ô lưới thô để coi 2 lần detect là "cùng 1 biển"
    _OCR_CACHE_TTL = 1.5      # giây — thời gian tái dùng kết quả OCR cũ
    _OCR_CACHE_MAX_SIZE = 200  # ngưỡng dọn cache để không phình vô hạn qua nhiều giờ chạy

    def _read_plate_cached(self, frame: np.ndarray, plate_det: Detection) -> str:
        """
        Đọc biển số có cache theo vị trí. EasyOCR (CPU) tốn 300-800ms/lần — nếu
        chạy lại mỗi frame detect cho cùng 1 xe đứng/đi qua cổng ở gần đúng vị trí
        cũ thì lãng phí toàn bộ thời gian đó. Cache theo ô lưới thô quanh tâm bbox,
        TTL ngắn vì xe di chuyển qua khung hình khá nhanh — không dùng để né OCR
        vĩnh viễn, chỉ tránh lặp lại trong vài frame liên tiếp gần nhau.
        """
        x1, y1, x2, y2 = plate_det.bbox
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        key = (cx // self._OCR_CACHE_GRID, cy // self._OCR_CACHE_GRID)

        now = time.time()
        cached = self._plate_ocr_cache.get(key)
        if cached is not None and (now - cached[1]) < self._OCR_CACHE_TTL:
            return cached[0]

        crop = frame[y1:y2, x1:x2]
        plate_read = ""
        if crop.size > 0 and crop.shape[0] > 20 and crop.shape[1] > 40:
            plate_read = read_plate(crop)

        self._plate_ocr_cache[key] = (plate_read, now)
        if len(self._plate_ocr_cache) > self._OCR_CACHE_MAX_SIZE:
            self._plate_ocr_cache = {
                k: v for k, v in self._plate_ocr_cache.items() if now - v[1] < self._OCR_CACHE_TTL
            }
        return plate_read

    def _process_violations(self, frame: np.ndarray, helmet_dets: list, plate_dets: list,
                         posture_status: str = 'unknown', vehicle_type: str | None = None,
                         too_many_riders: bool = False):
        """
        Xử lý toàn bộ logic vi phạm cho MỘT nhóm (1 person):
        0. Chặn theo loại phương tiện — không có xe hoặc đi xe đạp thì không bắt mũ/biển số
        1. OCR đọc biển số
        2. Tra whitelist trong DB
        3. Xác định violation_type theo thứ tự ưu tiên trong PLAN.md
        4. Kiểm tra cooldown ghi log
        5. Lưu snapshot + ghi log vào DB
        6. Đẩy cảnh báo WebSocket
        """
        # Không phát hiện xe máy/xe đạp nào gần người này → người đi bộ, không bắt lỗi
        # mũ bảo hiểm/biển số. Trước đây thiếu bước này nên người đi bộ qua cổng bị báo
        # PLATE_UNREADABLE sai (mọi group đều bị coi như phải có biển số đọc được).
        if vehicle_type is None:
            return

        # Xe đạp thường không bắt buộc đội mũ bảo hiểm theo luật, chỉ xe máy và xe đạp
        # điện mới bắt buộc. COCO không phân biệt được xe đạp điện với xe đạp thường,
        # nên hiện tại coi mọi 'bicycle' là được miễn — đây là giới hạn đã biết, sẽ cần
        # dataset/model riêng để phân biệt xe đạp điện khi có.
        if vehicle_type == 'bicycle':
            return

        # Phân loại helmet detections
        has_with_helmet = any('With Helmet' in d.class_name for d in helmet_dets)
        has_without_helmet = any('Without Helmet' in d.class_name for d in helmet_dets)

        # Đọc biển số từ plate detections (chỉ 1 plate gán vào nhóm này) — có cache
        # theo vị trí để tránh chạy lại EasyOCR cho cùng 1 xe (xem _read_plate_cached)
        plate_read = ""
        if plate_dets:
            best_plate = plate_dets[0]  # Đã được gán ở _group_by_person
            plate_read = self._read_plate_cached(frame, best_plate)
            # Feature 7: track plate read attempts/successes
            self._plate_attempts += 1
            if plate_read:
                self._plate_successes += 1

        # Tra whitelist
        plate_matched = None
        if plate_read:
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
        if not plate_dets:
            violation_types.append("NO_PLATE")
        # 2. Có box biển số nhưng OCR đọc rỗng → bị che/mờ/hỏng
        elif not plate_read:
            violation_types.append("PLATE_OBSCURED")
        
        # 2. Có đọc được biển số nhưng không tìm thấy trong whitelist
        if plate_read and not plate_matched:
            violation_types.append("PLATE_NOT_REGISTERED")
        
        # 3. Không có mũ bảo hiểm (có Without Helmet mà không có With Helmet).
        # Dắt bộ xe (posture == 'standing') không bắt buộc đội mũ theo luật —
        # chỉ bắt lỗi khi đang ngồi lái (riding) hoặc không xác định được tư thế
        # (unknown, giữ hành vi cũ để không bỏ sót khi pose detection thất bại).
        if has_without_helmet and not has_with_helmet and posture_status != 'standing':
            violation_types.append("NO_HELMET")

        # 4. Tư thế đang ngồi xe (riding) + có helmet → vi phạm đặc biệt
        if posture_status == 'riding' and has_with_helmet and not has_without_helmet:
            violation_types.append("RIDING_THROUGH_GATE")

        # 5. Tư thế đang ngồi xe (riding) + không helmet → cũng là riding
        if posture_status == 'riding' and not has_with_helmet:
            if "NO_HELMET" in violation_types:
                violation_types.remove("NO_HELMET")
            if "RIDING_THROUGH_GATE" not in violation_types:
                violation_types.append("RIDING_THROUGH_GATE")

        # 6. Chở quá số người quy định (đếm sẵn ở _count_riders_per_vehicle)
        if too_many_riders:
            violation_types.append("TOO_MANY_RIDERS")

        # Nếu không có vi phạm nào → không làm gì
        if not violation_types:
            return
        
        # Gộp violation_type nếu nhiều điều kiện cùng đúng
        if len(violation_types) > 1:
            violation_type = "MULTIPLE"
        else:
            violation_type = violation_types[0]
        
        # Key cho cooldown log: plate_matched hoặc "UNKNOWN"
        cooldown_key = plate_matched or "UNKNOWN"
        
        # Kiểm tra cooldown ghi log
        current_time = time.time()
        last_log = self._last_log_time.get(cooldown_key, 0)
        if current_time - last_log < VIOLATION_COOLDOWN:
            # Trong cooldown → chỉ đẩy cảnh báo WebSocket (không ghi log, không snapshot mới)
            self._push_alert(violation_type, plate_read, plate_matched, plate_format_valid=plate_format_valid)
            return

        # Chuẩn bị đường dẫn snapshot (rẻ, làm ngay ở main thread)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_filename = f"{timestamp_str}_{violation_type}.jpg"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

        # Lưu snapshot (cv2.imwrite) + ghi log DB — đẩy ra _io_pool (thread nền)
        # vì đây là I/O tốn vài chục ms, không cần chặn vòng lặp đọc frame tiếp
        # theo để chờ ghi đĩa/DB xong. Copy frame TRƯỚC khi đẩy đi: _run_loop sẽ
        # vẽ box đè lên chính frame này ngay sau khi hàm này return — snapshot
        # phải là ảnh gốc chưa vẽ box, không copy sẽ lưu nhầm ảnh có box.
        frame_snapshot = frame.copy()
        self._io_pool.submit(
            self._persist_violation,
            frame_snapshot, snapshot_path, snapshot_filename,
            plate_read, plate_matched, helmet_status, violation_type,
            posture_status, plate_format_valid,
        )

        # Cập nhật cooldown ngay (không chờ IO xong) — tránh spam ghi khi nhiều
        # group/frame liên tiếp rơi vào lúc thread nền đang xử lý phía sau.
        self._last_log_time[cooldown_key] = current_time

        # Đẩy cảnh báo WebSocket ngay — coi snapshot là sẽ ghi thành công
        # (best-effort: đã tạo thư mục trước, imwrite hiếm khi lỗi) để không
        # phải chờ IO thread ghi xong mới cảnh báo bảo vệ.
        self._push_alert(
            violation_type, plate_read, plate_matched,
            snapshot_filename=snapshot_filename,
            plate_format_valid=plate_format_valid,
        )

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
                            plate_format_valid: bool | None):
        """Lưu snapshot + ghi log vi phạm vào DB. Chạy trên _io_pool (thread nền)."""
        success = cv2.imwrite(snapshot_path, frame)

        # Feature 4: write video clip (reuse _io_pool, same thread as snapshot)
        clip_path = None
        clip_filename = snapshot_filename.replace('.jpg', '.mp4')
        clip_full_path = os.path.join(SNAPSHOTS_DIR, clip_filename)
        self._write_clip(list(self._clip_buffer), clip_full_path)
        if os.path.exists(clip_full_path):
            clip_path = f"data/snapshots/{clip_filename}"

        try:
            add_violation_event(
                timestamp=datetime.datetime.now().isoformat(),
                plate_read=plate_read,
                plate_matched=plate_matched,
                helmet_status=helmet_status,
                violation_type=violation_type,
                snapshot_path=f"data/snapshots/{snapshot_filename}" if success else None,
                posture_status=posture_status,
                plate_format_valid=plate_format_valid,
                clip_path=clip_path,
            )
            print(f"[Pipeline] Violation logged: {violation_type}, plate={plate_read or 'N/A'}")
        except Exception as e:
            print(f"[Pipeline] Error logging violation: {e}")

    def _push_alert(self, violation_type: str, plate_read: str, plate_matched: str,
                     snapshot_filename: str | None = None, plate_format_valid: bool | None = None):
        """Đẩy cảnh báo vi phạm vào WebSocket queue (có alert cooldown)."""
        current_time = time.time()
        if current_time - self._last_alert_time >= ALERT_COOLDOWN:
            alert = {
                "type": "violation",
                "violation_type": violation_type,
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

            for group, offset, future in pending:
                keypoints = future.result()
                posture = classify_posture(keypoints) if keypoints else 'unknown'
                group['posture_status'] = posture
                if keypoints:
                    self._draw_pose_keypoints(frame, keypoints, offset=offset)

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


def get_pipeline(gate_id: str = "main") -> VideoPipeline:
    """Lấy (hoặc tạo mới) pipeline instance cho gate_id."""
    global _pipelines
    if gate_id not in _pipelines:
        gate_config = GATES.get(gate_id)
        if gate_config is None:
            raise ValueError(f"Unknown gate_id: {gate_id}. Available gates: {list(GATES.keys())}")
        _pipelines[gate_id] = VideoPipeline(gate_id, gate_config)
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
