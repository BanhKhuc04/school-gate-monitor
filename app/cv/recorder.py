"""
ContinuousRecorder — ghi hình liên tục độc lập với luồng AI detect.

Đợt 2, Bước 7 — xem docs/plans/CURSOR_PLAN_DOT2_NANG_CAP.md.

Nguyên tắc:
- Nhận MỌI frame đọc từ camera (kể cả frame bị FRAME_SKIP bỏ qua hay không có person).
- KHÔNG được làm chậm vòng lặp đọc camera chính. Chạy trên 1 thread + queue riêng
  (maxsize nhỏ), drop-frame khi đầy — thà mất vài frame ghi hình còn hơn làm nghẽn
  AI pipeline (bài học từ comment _detect_pool: PyTorch nhả GIL nhưng encode MP4
  qua cv2.VideoWriter thì KHÔNG nhả GIL → nếu ghi trực tiếp trên main loop sẽ block).
- Rotate file mỗi `segment_minutes` để file không phình quá lớn (khó mở, khó replay).
- Mặc định TẮT (`CONTINUOUS_RECORDING_ENABLED=False`) cho tới khi có benchmark.
"""
import os
import threading
import time
import queue
from datetime import datetime, timezone

import cv2
import numpy as np


class ContinuousRecorder:
    """
    Ghi hình liên tục cho 1 camera. 1 instance / gate.

    Threading model:
        push_frame() → self._queue (maxsize nhỏ, drop-frame khi đầy)
                       ↓
        self._writer_loop (daemon thread): lấy frame từ queue, encode vào MP4 writer.
        rotate writer mỗi `segment_minutes`.

    Lưu ý: `push_frame()` KHÔNG BAO GIỜ block caller — `put_nowait` + drop nếu đầy.
    Đây là yêu cầu cứng: thread đọc camera phải chạy đều, không phụ thuộc recorder.
    """

    def __init__(
        self,
        gate_id: str,
        segment_minutes: int,
        fps: int,
        width: int,
        height: int,
        output_dir: str,
    ):
        self.gate_id = gate_id
        self.segment_seconds = max(60, segment_minutes * 60)  # tối thiểu 1 phút
        self.fps = max(1, fps)
        self.width = width
        self.height = height
        self.output_dir = output_dir

        # Queue NHỎ (maxsize=4) — chỉ giữ vài frame đệm. Drop ngay khi đầy
        # để không bao giờ block push_frame().
        self._queue: queue.Queue = queue.Queue(maxsize=4)
        self._writer_thread: threading.Thread | None = None
        self._running = False

        # State cho việc rotate segment
        self._current_writer: cv2.VideoWriter | None = None
        self._current_segment_path: str | None = None
        self._segment_start_ts: float = 0.0
        # Stats (cho health page, Bước 5)
        self._frames_written = 0
        self._frames_dropped = 0

    # ─── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Khởi động thread writer. Idempotent."""
        if self._running:
            return
        os.makedirs(self.output_dir, exist_ok=True)
        self._running = True
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name=f"Recorder-{self.gate_id}",
        )
        self._writer_thread.start()

    def stop(self) -> None:
        """
        Dừng thread writer. Đợi thread join (queue drain) để file segment hiện
        tại được finalize qua _finalize_segment() — tránh file MP4 hỏng/dở dang
        khi process tắt đột ngột (Ctrl+C, lifespan shutdown).
        """
        if not self._running:
            return
        self._running = False
        # Đợi thread join — _writer_loop sẽ finalize segment rồi return
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        self._writer_thread = None

    # ─── API cho pipeline ───────────────────────────────────────────────────────

    def push_frame(self, frame: np.ndarray) -> None:
        """
        Đẩy 1 frame vào queue. KHÔNG block — drop ngay nếu queue đầy.

        Tại sao drop thay vì block: thread detect phải đọc frame đều đặn (~30fps).
        Nếu encoder MP4 chậm (CPU nặng) → queue đầy → block push_frame → block
        detect → FPS giảm → ảnh hưởng AI pipeline. Drop frame ghi hình là hy sinh
        chấp nhận được để giữ AI ổn định.
        """
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            self._frames_dropped += 1

    def get_stats(self) -> dict:
        """Trả về stats cho health page — không đụng critical state."""
        return {
            "running": self._running,
            "frames_written": self._frames_written,
            "frames_dropped": self._frames_dropped,
            "current_segment": self._current_segment_path,
            "queue_size": self._queue.qsize(),
        }

    # ─── Writer loop (private) ──────────────────────────────────────────────────

    def _writer_loop(self) -> None:
        """
        Lấy frame từ queue, ghi vào VideoWriter hiện tại. Rotate khi:
          - segment_seconds đã trôi qua
          - writer không mở được (lỗi encode) → retry
        """
        while self._running or not self._queue.empty():
            try:
                frame = self._queue.get(timeout=0.5)
            except queue.Empty:
                # Queue rỗng + không còn chạy → thoát
                if not self._running:
                    break
                continue

            now = time.monotonic()
            # Mở segment mới nếu chưa có hoặc đã quá thời gian
            if (
                self._current_writer is None
                or (now - self._segment_start_ts) >= self.segment_seconds
            ):
                self._finalize_segment()
                self._open_new_segment()

            if self._current_writer is not None:
                try:
                    self._current_writer.write(frame)
                    self._frames_written += 1
                except Exception as e:
                    print(f"[Recorder/{self.gate_id}] write error: {e}")
                    self._finalize_segment()

        # Finalize segment cuối trước khi thoát
        self._finalize_segment()

    def _open_new_segment(self) -> None:
        """Tạo file MP4 mới + mở VideoWriter."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{self.gate_id}_{ts}.mp4"
        path = os.path.join(self.output_dir, filename)
        # mp4v = MPEG-4 part 2, có sẵn trong opencv-python, không cần ffmpeg.
        # Trade-off: file lớn hơn H.264 nhưng encode nhanh hơn — đúng ưu tiên
        # cho continuous recording (CPU encode là bottleneck chính).
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, float(self.fps), (self.width, self.height))
        if not writer.isOpened():
            print(f"[Recorder/{self.gate_id}] ERROR: cannot open writer for {path}")
            self._current_writer = None
            return
        self._current_writer = writer
        self._current_segment_path = path
        self._segment_start_ts = time.monotonic()
        print(f"[Recorder/{self.gate_id}] new segment: {path}")

    def _finalize_segment(self) -> None:
        """Release writer hiện tại (ghi footer MP4). Idempotent."""
        if self._current_writer is not None:
            try:
                self._current_writer.release()
            except Exception:
                pass
            self._current_writer = None
            self._current_segment_path = None


# ─── Module-level helpers ──────────────────────────────────────────────────────

def cleanup_old_recordings(output_dir: str, retention_days: int) -> int:
    """
    Xóa file ghi hình liên tục cũ hơn `retention_days` ngày. Trả về số file đã xóa.
    Dùng cho MaintenanceWorker (Bước 7 sẽ gọi từ một job riêng — KHÔNG gộp vào
    _cleanup_job cũ để tách policy retention).
    """
    import glob as _glob
    from datetime import timedelta
    if not os.path.exists(output_dir):
        return 0
    cutoff = time.time() - retention_days * 86400
    deleted = 0
    for path in _glob.glob(os.path.join(output_dir, "*.mp4")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
                deleted += 1
        except OSError:
            pass
    return deleted
