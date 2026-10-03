"""Webcam capture wrapper using OpenCV."""
import os

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
            self.cap = cv2.VideoCapture(source, backend)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError('Không mở được camera. Kiểm tra thiết bị, địa chỉ và thông tin đăng nhập.')

        # Thiết lập độ phân giải — CHỈ có tác dụng với webcam vật lý/ảo qua
        # DSHOW. Đã verify thật: với RTSP, cap.set() bị FFmpeg lờ đi hoàn
        # toàn, camera vẫn trả về đúng độ phân giải gốc của nó (vd. Imou trả
        # 2688x1664 dù set 1280x720) — vì vậy read_frame() phải tự cv2.resize
        # xuống target_size cho nguồn network, xem bên dưới.
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self._is_opened = True

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
            self.cap.release()
            self._is_opened = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def is_opened(self) -> bool:
        return self._is_opened and self.cap.isOpened()
