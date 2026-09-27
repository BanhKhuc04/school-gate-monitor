"""
Pipeline xử lý video trong thread nền.

Luồng: đọc frame → detect helmet → detect plate → OCR → tra DB → ghi log vi phạm → vẽ box → lưu frame.
Có thêm queue cho cảnh báo vi phạm (Bước 4) và ghi log vi phạm vào DB (Bước 6).
"""
import threading
import time
import queue
import datetime
import os
import cv2
import numpy as np
from typing import Optional

from app.config import (
    CAMERA_INDEX, HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
    FRAME_SKIP, VIDEO_WIDTH, VIDEO_HEIGHT, 
    ALERT_COOLDOWN, VIOLATION_COOLDOWN, SNAPSHOTS_DIR
)
from app.cv.capture import WebcamStream
from app.cv.detector import HelmetPlateDetector, Detection
from app.cv.ocr import read_plate
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
    Thread nền xử lý webcam + YOLO detection + vẽ box.
    
    Frame đã xử lý được lưu vào biến dùng chung, có Lock bảo vệ.
    Có queue cho cảnh báo vi phạm qua WebSocket.
    """
    
    def __init__(self):
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

        # Timestamps for health monitoring
        self._start_time: float = time.time()
        self._last_frame_time: float = self._start_time
        self._last_detection_time: float = self._start_time
    
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

        return {
            "running": self._running,
            "thread_alive": self._thread is not None and self._thread.is_alive(),
            "camera_open": camera_open,
            "last_frame_age_sec": round(now - self._last_frame_time, 2),
            "last_detection_age_sec": round(now - self._last_detection_time, 2),
            "frame_count": self._frame_count,
            "uptime_sec": round(now - self._start_time, 1),
        }
    
    def _run_loop(self):
        """Vòng lặp chính của thread nền."""
        try:
            self._webcam = WebcamStream(
                source=CAMERA_INDEX,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT
            )
            print("[Pipeline] Webcam opened")
        except Exception as e:
            print(f"[Pipeline] ERROR: Cannot open webcam: {e}")
            self._running = False
            return
        
        while self._running:
            try:
                # Đọc frame
                frame = self._webcam.read_frame()
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
                
                # Detect person (COCO → lọc class 'person')
                raw_person_dets = self._person_detector.detect(frame)
                person_dets = [d for d in raw_person_dets if d.class_name.lower() == 'person']

                # Không có person nào → bỏ qua toàn bộ frame
                if not person_dets:
                    with self._lock:
                        self._latest_frame = frame
                    continue

                # Update detection timestamp (health monitoring)
                self._last_detection_time = time.time()

                # Detect helmet & plate
                helmet_dets = self._helmet_detector.detect(frame)
                plate_dets = self._plate_detector.detect(frame)

                # Cập nhật cache để nhánh skip vẽ box mượt
                self._last_person_dets = person_dets
                self._last_helmet_dets = helmet_dets
                self._last_plate_dets = plate_dets

                # Gom helmet + plate vào từng nhóm theo person
                groups = self._group_by_person(person_dets, helmet_dets, plate_dets)

                # Xử lý vi phạm cho TỪNG nhóm riêng biệt
                for group in groups:
                    self._process_violations(frame, group['helmet_dets'], group['plate_dets'])

                # Vẽ box helmet (theo nhóm)
                for det in helmet_dets:
                    self._draw_detection(frame, det, COLOR_HELMET, COLOR_NO_HELMET)

                # Vẽ box plate (theo nhóm)
                for det in plate_dets:
                    self._draw_detection(frame, det, COLOR_PLATE, COLOR_PLATE)

                # Vẽ box person (cam) — SAU khi OCR đã xong
                for det in person_dets:
                    self._draw_detection(frame, det, COLOR_PERSON, COLOR_PERSON)
                
                # Lưu frame đã vẽ
                with self._lock:
                    self._latest_frame = frame
                    
            except Exception as e:
                print(f"[Pipeline] Error in loop: {e}")
                time.sleep(0.1)
        
        # Cleanup
        if self._webcam:
            self._webcam.release()
            print("[Pipeline] Webcam released")
    
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
                         plate_dets: list) -> list[dict]:
        """
        Gom helmet + plate detections vào từng nhóm theo person box.

        Logic:
        - helmet/no-helmet → gán vào person mà tâm điểm helmet nằm trong box person.
        - plate → gán vào person có x-center gần nhất, trong phạm vi chiều rộng box person.

        Trả về list nhóm, mỗi nhóm: {helmet_dets: [...], plate_dets: [...]}.
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

            groups.append({
                'helmet_dets': group_helmets,
                'plate_dets': group_plates,
            })

        return groups

    def _process_violations(self, frame: np.ndarray, helmet_dets: list, plate_dets: list):
        """
        Xử lý toàn bộ logic vi phạm cho MỘT nhóm (1 person):
        1. OCR đọc biển số
        2. Tra whitelist trong DB
        3. Xác định violation_type theo thứ tự ưu tiên trong PLAN.md
        4. Kiểm tra cooldown ghi log
        5. Lưu snapshot + ghi log vào DB
        6. Đẩy cảnh báo WebSocket
        """
        # Phân loại helmet detections
        has_with_helmet = any('With Helmet' in d.class_name for d in helmet_dets)
        has_without_helmet = any('Without Helmet' in d.class_name for d in helmet_dets)

        # Đọc biển số từ plate detections (chỉ 1 plate gán vào nhóm này)
        plate_read = ""
        if plate_dets:
            best_plate = plate_dets[0]  # Đã được gán ở _group_by_person
            x1, y1, x2, y2 = best_plate.bbox
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0 and crop.shape[0] > 20 and crop.shape[1] > 40:
                plate_read = read_plate(crop)

        # Tra whitelist
        plate_matched = None
        if plate_read:
            vehicle = get_vehicle_by_plate(plate_read)
            if vehicle:
                plate_matched = vehicle['plate_number']

        # Xác định helmet_status
        if has_with_helmet:
            helmet_status = "helmet"
        elif has_without_helmet:
            helmet_status = "no_helmet"
        else:
            helmet_status = "unknown"

        # Xác định violation_type theo thứ tự ưu tiên trong PLAN.md
        violation_types = []
        
        # 1. Không có plate_det hoặc OCR trả về rỗng
        if not plate_dets or not plate_read:
            violation_types.append("PLATE_UNREADABLE")
        
        # 2. Có đọc được biển số nhưng không tìm thấy trong whitelist
        if plate_read and not plate_matched:
            violation_types.append("PLATE_NOT_REGISTERED")
        
        # 3. Không có mũ bảo hiểm (có Without Helmet mà không có With Helmet)
        if has_without_helmet and not has_with_helmet:
            violation_types.append("NO_HELMET")
        
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
            # Trong cooldown → chỉ đẩy cảnh báo WebSocket (không ghi log)
            self._push_alert(violation_type, plate_read, plate_matched)
            return
        
        # Lưu snapshot
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_filename = f"{timestamp_str}_{violation_type}.jpg"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
        
        # Đảm bảo thư mục tồn tại
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        
        # Lưu frame gốc (chưa vẽ box) vào snapshots
        success = cv2.imwrite(snapshot_path, frame)
        if not success:
            snapshot_path = None
        
        # Ghi log vào DB
        try:
            add_violation_event(
                timestamp=datetime.datetime.now().isoformat(),
                plate_read=plate_read,
                plate_matched=plate_matched,
                helmet_status=helmet_status,
                violation_type=violation_type,
                snapshot_path=f"data/snapshots/{snapshot_filename}" if snapshot_path else None
            )
            print(f"[Pipeline] Violation logged: {violation_type}, plate={plate_read or 'N/A'}")
        except Exception as e:
            print(f"[Pipeline] Error logging violation: {e}")
        
        # Cập nhật cooldown
        self._last_log_time[cooldown_key] = current_time
        
        # Đẩy cảnh báo WebSocket
        self._push_alert(violation_type, plate_read, plate_matched)
    
    def _push_alert(self, violation_type: str, plate_read: str, plate_matched: str):
        """Đẩy cảnh báo vào WebSocket queue (nếu chưa trong alert cooldown)."""
        current_time = time.time()
        if current_time - self._last_alert_time >= ALERT_COOLDOWN:
            alert = {
                "type": "violation",
                "violation_type": violation_type,
                "plate_read": plate_read or None,
                "plate_matched": plate_matched or None,
                "timestamp": datetime.datetime.now().isoformat()
            }
            self._alert_queue.put(alert)
            self._last_alert_time = current_time
            print(f"[Pipeline] Alert pushed: {alert}")


# Singleton instance
_pipeline: Optional[VideoPipeline] = None


def get_pipeline() -> VideoPipeline:
    """Lấy singleton pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = VideoPipeline()
    return _pipeline


def start_pipeline():
    """Start pipeline thread."""
    get_pipeline().start()


def stop_pipeline():
    """Stop pipeline thread."""
    if _pipeline:
        _pipeline.stop()
