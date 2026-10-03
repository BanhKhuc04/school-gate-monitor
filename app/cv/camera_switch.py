"""One pending source change per gate; capture I/O belongs to the pipeline thread."""
import threading

from app.cv.camera_sources import display_source, normalize_source


class CameraBusy(Exception):
    pass


class CameraSwitch:
    def __init__(self, source):
        self.source = normalize_source(source)
        self._lock = threading.Lock()
        self._pending = None
        self._persist = True
        self._state = 'idle'
        self._error = None

    @property
    def has_pending(self):
        with self._lock:
            return self._pending is not None

    def request(self, source, camera_online=False, persist=True):
        source = normalize_source(source)
        with self._lock:
            if self._pending is not None:
                raise CameraBusy('Cổng này đang chuyển nguồn. Vui lòng đợi hoàn tất.')
            self._error = None
            if source == self.source and camera_online:
                self._state = 'applied'
                return
            self._pending = source
            self._persist = persist
            self._state = 'checking'

    def status(self):
        with self._lock:
            return {
                'current': display_source(self.source),
                'pending': display_source(self._pending),
                'state': self._state,
                'error': self._error,
            }

    def apply(self, old_stream, open_stream, save):
        """Return (capture, first frame) only on success; leave the old capture on failure."""
        with self._lock:
            source, persist = self._pending, self._persist
        if source is None:
            return None
        candidate = None
        try:
            candidate = open_stream(source)
            frame = candidate.read_frame()
            if frame is None or frame.size == 0:
                raise RuntimeError('Empty frame')
            if persist:
                save(str(source))
        except Exception:
            try:
                if candidate is not None:
                    candidate.release()
            except Exception:
                pass  # Failed driver cleanup must not leave the request pending.
            with self._lock:
                self._state = 'error'
                self._error = 'Không thể mở, đọc hoặc lưu nguồn mới. Nguồn cũ được giữ nguyên; kiểm tra kết nối, thông tin đăng nhập và lưu trữ.'
                self._pending = None
            return None
        try:
            if old_stream is not None:
                old_stream.release()
        except Exception:
            pass  # The verified new stream has already been persisted.
        with self._lock:
            self.source = source
            self._pending = None
            self._state = 'applied'
        return candidate, frame
