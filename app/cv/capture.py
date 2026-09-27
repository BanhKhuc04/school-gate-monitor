"""Webcam capture wrapper using OpenCV."""
import cv2
import numpy as np


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
            self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được nguồn camera (source={source})")

        # Thiết lập độ phân giải (không ảnh hưởng video file đã có sẵn kích thước)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self._is_opened = True

    def read_frame(self) -> np.ndarray:
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
