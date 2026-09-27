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
    CAMERA_SOURCE, CAMERA_LOOP, HELMET_MODEL_PATH, PLATE_MODEL_PATH, PERSON_MODEL_PATH,
    HELMET_CONF_THRESHOLD, PLATE_CONF_THRESHOLD, PERSON_CONF_THRESHOLD,
    FRAME_SKIP, VIDEO_WIDTH, VIDEO_HEIGHT,
    ALERT_COOLDOWN, VIOLATION_COOLDOWN, SNAPSHOTS_DIR
)
from app.cv.capture import WebcamStream
from app.cv.detector import HelmetPlateDetector, Detection
from app.cv.ocr import read_plate, validate_plate_format
from app.db import get_vehicle_by_plate, add_violation_event

# Face match cooldown (seconds) — separate from violation cooldown
FACE_MATCH_COOLDOWN = 30.0
# How much of the top of the person box to crop for face detection (0.0–1.0)
_FACE_CROP_TOP_RATIO = 0.40


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

        # Cooldown for face match alerts
        self._last_face_match_time: float = 0.0
    
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
    
    def _open_webcam(self):
        return WebcamStream(
            source=CAMERA_SOURCE,
            width=VIDEO_WIDTH,
            height=VIDEO_HEIGHT,
            loop=CAMERA_LOOP,
        )

    def _run_loop(self):
        """Vòng lặp chính của thread nền."""
        try:
            self._webcam = self._open_webcam()
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

                # Phát hiện tư thế cho mỗi person box — ISOLATED try/except
                groups = self._run_posture_detection(frame, groups)

                # Xử lý vi phạm cho TỪNG nhóm riêng biệt
                for group in groups:
                    self._process_violations(
                        frame,
                        group['helmet_dets'],
                        group['plate_dets'],
                        posture_status=group.get('posture_status', 'unknown'),
                    )

                # Face recognition — isolated try/except, does not affect helmet/plate pipeline
                self._run_face_match(frame)

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
                _consecutive_errors += 1
                if _consecutive_errors >= _RECONNECT_AFTER:
                    print(f"[Pipeline] {_consecutive_errors} consecutive read failures — reconnecting camera")
                    try:
                        self._webcam.release()
                    except Exception:
                        pass
                    try:
                        self._webcam = self._open_webcam()
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
                '_person': person,
                'helmet_dets': group_helmets,
                'plate_dets': group_plates,
            })

        return groups

    def _process_violations(self, frame: np.ndarray, helmet_dets: list, plate_dets: list,
                         posture_status: str = 'unknown'):
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
        
        # 1. Không có plate_det hoặc OCR trả về rỗng
        if not plate_dets or not plate_read:
            violation_types.append("PLATE_UNREADABLE")
        
        # 2. Có đọc được biển số nhưng không tìm thấy trong whitelist
        if plate_read and not plate_matched:
            violation_types.append("PLATE_NOT_REGISTERED")
        
        # 3. Không có mũ bảo hiểm (có Without Helmet mà không có With Helmet)
        if has_without_helmet and not has_with_helmet:
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
                snapshot_path=f"data/snapshots/{snapshot_filename}" if snapshot_path else None,
                posture_status=posture_status,
                plate_format_valid=plate_format_valid,
            )
            print(f"[Pipeline] Violation logged: {violation_type}, plate={plate_read or 'N/A'}")
        except Exception as e:
            print(f"[Pipeline] Error logging violation: {e}")

        # Cập nhật cooldown
        self._last_log_time[cooldown_key] = current_time

        # Đẩy cảnh báo WebSocket
        self._push_alert(
            violation_type, plate_read, plate_matched,
            snapshot_filename=snapshot_filename if snapshot_path else None,
            plate_format_valid=plate_format_valid,
        )

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

    def _push_face_match_alert(self, matched_label: str, similarity: float, snapshot_path: str | None):
        """Đẩy face match alert vào WebSocket queue (có cooldown riêng)."""
        current_time = time.time()
        if current_time - self._last_face_match_time < FACE_MATCH_COOLDOWN:
            return  # still in cooldown

        snapshot_filename = os.path.basename(snapshot_path) if snapshot_path else None
        alert = {
            "type": "face_match",
            "matched_label": matched_label,
            "similarity": round(similarity, 4),
            "snapshot_url": f"/media/{snapshot_filename}" if snapshot_filename else None,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self._alert_queue.put(alert)
        self._last_face_match_time = current_time
        print(f"[Pipeline] Face match: {matched_label} ({similarity:.3f})")

    def _run_face_match(self, frame: np.ndarray):
        """
        Thu nhien dien khuon mat tu frame hien tai.
        - Crop top 40% cua moi person box
        - Goi detect_and_embed -> match_embedding
        - Neu match -> _push_face_match_alert
        ISOLATED try/except: khong anh huong main helmet/plate pipeline.
        """
        try:
            from app.cv.face import detect_and_embed, match_embedding
            from app.db import get_face_embeddings, add_face_match_event
            person_dets = self._last_person_dets
            if not person_dets:
                return
            registered = get_face_embeddings()
            if not registered:
                return
            import struct
            known_labels = []
            known_vehicle_ids = []
            known_vecs = []
            for rec in registered:
                emb_bytes = rec.get("embedding")
                if not emb_bytes:
                    continue
                vec = np.array(struct.unpack(f"{len(emb_bytes)//4}f", emb_bytes), dtype=np.float32)
                known_vecs.append(vec)
                known_labels.append(rec["label_name"])
                known_vehicle_ids.append(rec.get("vehicle_id"))
            if not known_vecs:
                return
            frame_h, frame_w = frame.shape[:2]
            for person in person_dets:
                x1, y1, x2, y2 = person.bbox
                x1, x2 = max(0, x1), min(frame_w, x2)
                y1, y2 = max(0, y1), min(frame_h, y2)
                top_y2 = int(y1 + (y2 - y1) * _FACE_CROP_TOP_RATIO)
                if top_y2 <= y1:
                    continue
                face_crop = frame[y1:top_y2, x1:x2]
                if face_crop.size == 0 or face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
                    continue
                face_resized = cv2.resize(face_crop, (112, 112))
                emb_bytes = detect_and_embed(face_resized)
                if emb_bytes is None:
                    continue
                vec = np.array(struct.unpack(f"{len(emb_bytes)//4}f", emb_bytes), dtype=np.float32)
                matched, best_sim, best_idx = match_embedding(vec, known_vecs)
                if matched:
                    matched_label = known_labels[best_idx]

                    # Lưu full frame làm bằng chứng (giống pattern violation snapshot)
                    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
                    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    snapshot_filename = f"{ts_str}_face_{matched_label}.jpg"
                    snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
                    if not cv2.imwrite(snapshot_path, frame):
                        snapshot_filename = None

                    # Ghi audit trail vào DB — trước đây hàm này chưa từng được gọi
                    try:
                        add_face_match_event(
                            matched_label=matched_label,
                            similarity=float(best_sim),
                            vehicle_id=known_vehicle_ids[best_idx],
                            snapshot_path=f"data/snapshots/{snapshot_filename}" if snapshot_filename else None,
                        )
                    except Exception as e:
                        print(f"[Pipeline] Error logging face match event: {e}")

                    self._push_face_match_alert(
                        matched_label=matched_label,
                        similarity=best_sim,
                        snapshot_path=snapshot_path if snapshot_filename else None,
                    )
                    break
        except Exception:
            pass

    def _run_posture_detection(self, frame: np.ndarray, groups: list) -> list:
        """
        Chạy pose detection cho mỗi person box trong groups.
        Bổ sung 'posture_status' vào mỗi group dict.
        Hoàn toàn isolated trong try/except để không ảnh hưởng pipeline chính.
        """
        try:
            from app.cv.pose import PostureDetector, classify_posture

            detector = PostureDetector()
            frame_h, frame_w = frame.shape[:2]

            for group in groups:
                # Get person bbox from group (stored in the group from _group_by_person)
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

                keypoints = detector.detect_pose(person_crop)
                posture = classify_posture(keypoints) if keypoints else 'unknown'
                group['posture_status'] = posture

        except Exception:
            # ISOLATED: posture errors must not break the main pipeline
            for group in groups:
                if 'posture_status' not in group:
                    group['posture_status'] = 'unknown'

        return groups


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
