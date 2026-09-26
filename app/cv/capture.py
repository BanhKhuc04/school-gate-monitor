"""Webcam capture wrapper using OpenCV."""
import cv2
import numpy as np


class WebcamStream:
    """Bọc cv2.VideoCapture, cung cấp read_frame() và release()."""
    
    def __init__(self, source: int = 0, width: int = 640, height: int = 480):
        """
        Khởi tạo webcam stream.
        
        Args:
            source: Camera index (mặc định 0 = webcam mặc định)
            width: Chiều rộng frame
            height: Chiều cao frame
        """
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được webcam (source={source})")
        
        # Thiết lập độ phân giải
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
