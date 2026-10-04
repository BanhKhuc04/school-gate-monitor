"""Webcam capture wrapper using OpenCV."""
import os
import threading
import time
from dataclasses import dataclass

# P0 FIX: phải set TRƯỚC khi cv2 mở bất kỳ VideoCapture(CAP_FFMPEG) nào —
# đây là biến môi trường FFmpeg đọc lúc khởi tạo, set sau (kể cả qua
# cap.set(CAP_PROP_BUFFERSIZE,...) sau khi open) không có tác dụng, đã verify
# thật: cap.set(CAP_PROP_BUFFERSIZE,1) trả về False trên build OpenCV này.
# nobuffer + low_delay ép FFmpeg không đệm sẵn nhiều frame phía sau — nếu
# không, RTSP stream chạy càng lâu thì độ trễ hiển thị càng cộng dồn nặng
# (pipeline detect chậm hơn tốc độ camera gửi về → frame cũ xếp hàng chờ).
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
)

import cv2
import numpy as np
import sys

from app.cv.camera_sources import normalize_source, is_network_source

# DirectShow device open/release is not safe across threads: two gates
# opening OBS Virtual Camera + a webcam at the same instant failed every time
# ("raised unknown C++ exception") and eventually crashed the server.
_DSHOW_LOCK = threading.Lock()
_NO_LOCK = __import__('contextlib').nullcontext()


class WebcamStream:
    """Bọc cv2.VideoCapture, cung cấp read_frame() và release()."""

    def __init__(self, source=0, width: int = 640, height: int = 480, loop: bool = False):
        """
        Khởi tạo webcam stream.

        Args:
            source: Camera index (int, webcam vật lý/ảo) hoặc string
                (đường dẫn video file hoặc rtsp:// URL).
            width: Chiều rộng frame
            height: Chiều cao frame
            loop: Nếu source là video file, tự seek về đầu khi hết file (EOF)
                thay vì raise — chỉ có ý nghĩa với source dạng file.
        """
        source = normalize_source(source)
        self._is_file_or_url = isinstance(source, str)
        network = is_network_source(source)
        self._loop = loop and self._is_file_or_url and not network
        self._network = network
        self._target_size = (width, height)
        self.frame_interval = 0.0

        if network:
            self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000,
            ])
        elif self._is_file_or_url:
            # CAP_DSHOW chỉ áp dụng cho thiết bị capture Windows theo index —
            # dùng nó với video file/RTSP URL sẽ khiến VideoCapture mở thất bại.
            self.cap = cv2.VideoCapture(source)
        else:
            # CAP_DSHOW ép cố định để source (index) luôn trỏ đúng 1 thiết bị —
            # mặc định (CAP_ANY) rơi vào MSMF trên Windows, đánh số thiết bị khác
            # DSHOW nên cùng 1 số index có thể ra 2 camera khác nhau tùy backend.
            backend = cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY
            with _DSHOW_LOCK:
                self.cap = cv2.VideoCapture(source, backend)
        self._device = not self._is_file_or_url
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError('Không mở được camera. Kiểm tra thiết bị, địa chỉ và thông tin đăng nhập.')

        # Thiết lập độ phân giải — CHỈ có tác dụng với webcam vật lý/ảo qua
        # DSHOW. Đã verify thật: với RTSP, cap.set() bị FFmpeg lờ đi hoàn
        # toàn, camera vẫn trả về đúng độ phân giải gốc của nó (vd. Imou trả
        # 2688x1664 dù set 1280x720) — vì vậy read_frame() phải tự cv2.resize
        # xuống target_size cho nguồn network, xem bên dưới.
        with _DSHOW_LOCK if self._device else _NO_LOCK:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self._is_opened = True
        if self._is_file_or_url and not network:
            fps = float(self.cap.get(cv2.CAP_PROP_FPS))
            self.frame_interval = 1.0 / fps if fps > 0 else 1.0 / 25

    def read_source_frame(self) -> np.ndarray:
        """
        Đọc frame mới nhất từ webcam.

        Returns:
            numpy.ndarray: Frame BGR (height, width, 3)
            Raises RuntimeError nếu không đọc được frame.
        """
        if not self._is_opened:
            raise RuntimeError("Webcam đã được release")

        ret, frame = self.cap.read()
        if not ret and self._loop:
            # Hết video file (EOF) — seek về đầu và đọc lại 1 lần cho demo lặp liên tục.
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
        if not ret:
            # R2: phân biệt EOF (file video kết thúc, loop=False) khỏi lỗi
            # mạng/webcam. EOF phải kết thúc run, KHÔNG reconnect — caller
            # (VideoPipeline._run_loop) nhận EOFError và set _running=False.
            if self._is_file_or_url and not self._network:
                raise EOFError("Video file ended")
            raise RuntimeError("Không đọc được frame từ webcam")

        return frame

    def read_frame(self) -> np.ndarray:
        """Compatibility preview; OCR uses read_source_frame() without resize."""
        frame = self.read_source_frame()
        if self._network:
            w, h = self._target_size
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)

        return frame


    def release(self):
        """Giải phóng webcam."""
        if self._is_opened:
            with _DSHOW_LOCK if getattr(self, '_device', False) else _NO_LOCK:
                self.cap.release()
            self._is_opened = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def is_opened(self) -> bool:
        return self._is_opened and self.cap.isOpened()


@dataclass(frozen=True)
class CapturedFrame:
    image: np.ndarray
    seq: int
    captured_at: float
    read_ms: float


class LatestFrameCapture:
    """One reader owns capture I/O. Slow consumers receive only the latest frame.

    The caller retains stream lifetime ownership; stop must join successfully
    before releasing/reusing it. File inputs are paced at their recorded FPS.
    """
    def __init__(self, stream, on_frame=None):
        self.stream, self.on_frame = stream, on_frame
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._latest = None
        self._error = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name='camera-capture')
        self._thread.start()

    def _run(self):
        seq = 0
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                reader = getattr(type(self.stream), 'read_source_frame', None)
                image = self.stream.read_source_frame() if callable(reader) else self.stream.read_frame()
                if self._stop.is_set():
                    break
                seq += 1
                packet = CapturedFrame(image, seq, time.monotonic(), (time.monotonic()-started)*1000)
                with self._condition:
                    self._latest = packet
                    self._condition.notify_all()
                if self.on_frame:
                    self.on_frame(packet)
                remaining = getattr(self.stream, 'frame_interval', 0.0) - (time.monotonic()-started)
                if remaining > 0:
                    self._stop.wait(remaining)
        except Exception as exc:
            with self._condition:
                self._error = exc
                self._condition.notify_all()

    def read_latest(self, after=0, timeout=3.5):
        deadline = time.monotonic()+timeout
        with self._condition:
            while True:
                if self._stop.is_set():
                    raise RuntimeError('capture stopped')
                if self._latest is not None and self._latest.seq > after:
                    return self._latest
                if self._error:
                    # R2: preserve EOFError để caller phân biệt EOF vs network
                    # error. Trước đây wrap thành RuntimeError khiến pipeline
                    # reconnect cho cả file video (vòng lặp vô hạn).
                    err = self._error
                    self._error = None
                    raise err
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('capture frame timeout')
                self._condition.wait(remaining)

    def stop(self, timeout=4):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread:
            self._thread.join(timeout)
        return not self._thread or not self._thread.is_alive()

    @property
    def buffered_frames(self):
        return int(self._latest is not None)
