"""Webcam capture wrapper using OpenCV."""
import os
import time

import cv2
import numpy as np


class WebcamStream:
    """Bọc cv2.VideoCapture, cung cấp read_frame() và release()."""

    def __init__(self, source=0, width: int = 640, height: int = 480, loop: bool = False,
                 realtime: bool = False):
        """
        Khởi tạo webcam stream.

        Args:
            source: Camera index (int, webcam vật lý/ảo) hoặc string
                (đường dẫn video file hoặc rtsp:// URL).
            width: Chiều rộng frame
            height: Chiều cao frame
            loop: Nếu source là video file, tự seek về đầu khi hết file (EOF)
                thay vì raise — chỉ có ý nghĩa với source dạng file.
            realtime: Chỉ áp dụng video FILE trên đĩa — phát đúng tốc độ thật như
                camera (xử lý chậm thì bỏ bớt frame, nhanh thì chờ). Tắt thì đọc
                file nhanh nhất có thể (video bị tua nhanh/chậm theo tốc độ máy).
        """
        self._is_file_or_url = isinstance(source, str)
        self._loop = loop and self._is_file_or_url

        if self._is_file_or_url:
            # CAP_DSHOW chỉ áp dụng cho thiết bị capture Windows theo index —
            # dùng nó với video file/RTSP URL sẽ khiến VideoCapture mở thất bại.
            self.cap = cv2.VideoCapture(source)
        else:
            # CAP_DSHOW ép cố định để source (index) luôn trỏ đúng 1 thiết bị —
            # mặc định (CAP_ANY) rơi vào MSMF trên Windows, đánh số thiết bị khác
            # DSHOW nên cùng 1 số index có thể ra 2 camera khác nhau tùy backend.
            # CAP_DSHOW chỉ có trên Windows — máy khác dùng backend mặc định.
            if os.name == "nt":
                self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            if self._is_file_or_url and not source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")) \
                    and not os.path.exists(source):
                raise RuntimeError(f"Không tìm thấy file video: {source}")
            raise RuntimeError(f"Không mở được nguồn camera (source={source}) — kiểm tra camera đã cắm, "
                               f"không bị app khác (Zoom/Teams/OBS) chiếm, hoặc đổi nguồn ở /admin/camera")

        # Thiết lập độ phân giải (không ảnh hưởng video file đã có sẵn kích thước)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self._realtime = realtime and self._is_file_or_url and os.path.isfile(source)
        fps = self.cap.get(cv2.CAP_PROP_FPS) if self._realtime else 0
        self._fps = fps if fps and 1 <= fps <= 240 else 25.0
        self._clock_start = None
        self._frames_read = 0

        self._is_opened = True

    def _restart_file(self):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._clock_start = time.monotonic()
        self._frames_read = 0

    def _pace(self):
        """Giữ video file chạy đúng tốc độ thật: bỏ qua frame đã trễ, chờ frame chưa tới giờ."""
        now = time.monotonic()
        if self._clock_start is None:
            self._clock_start = now
        due = int((now - self._clock_start) * self._fps)
        while self._frames_read < due:
            if not self.cap.grab():  # grab() không giải mã màu — bỏ qua frame rẻ hơn read()
                if self._loop:
                    self._restart_file()
                return
            self._frames_read += 1
        wait = self._clock_start + self._frames_read / self._fps - time.monotonic()
        if wait > 0:
            time.sleep(wait)

    def read_frame(self) -> np.ndarray:
        """
        Đọc frame mới nhất từ webcam.

        Returns:
            numpy.ndarray: Frame BGR (height, width, 3)
            Raises RuntimeError nếu không đọc được frame.
        """
        if not self._is_opened:
            raise RuntimeError("Webcam đã được release")

        if self._realtime:
            self._pace()

        ret, frame = self.cap.read()
        if not ret and self._loop:
            # Hết video file (EOF) — seek về đầu và đọc lại 1 lần cho demo lặp liên tục.
            self._restart_file()
            ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("Không đọc được frame từ webcam")

        self._frames_read += 1
        return frame

    def release(self):
        """Giải phóng webcam."""
        if self._is_opened:
            self.cap.release()
            self._is_opened = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def is_opened(self) -> bool:
        return self._is_opened and self.cap.isOpened()
