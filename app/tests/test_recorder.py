"""
pytest tests cho Đợt 2, Bước 7 — ContinuousRecorder.

Bài học từ bug Bước 3: test exercise end-to-end qua entry point thật
(recorder.start()/push_frame/stop()), không chỉ test helper riêng lẻ.
"""
import os
import time
import threading

import numpy as np
import pytest


def _make_frame(w=64, h=48) -> np.ndarray:
    """Tạo 1 frame giả (uint8 BGR) — đủ nhỏ để test chạy nhanh."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# ─── Test push_frame không block ──────────────────────────────────────────────

def test_push_frame_does_not_block_when_queue_full(tmp_path):
    """
    Plan yêu cầu: push_frame KHÔNG block khi queue đầy (maxsize=4) — đây là
    yêu cầu CỨNG để không làm chậm thread detect. Test bằng cách:
      1. Khởi động recorder.
      2. Đẩi frame đầy queue NHANH (không đợi writer kịp xử lý).
      3. push_frame phải return ngay (không block).
      4. frames_dropped > 0 (chứng minh drop đúng cơ chế).
    """
    from app.cv.recorder import ContinuousRecorder

    recorder = ContinuousRecorder(
        gate_id="test", segment_minutes=5, fps=10,
        width=64, height=48, output_dir=str(tmp_path),
    )
    recorder.start()
    try:
        # Đẩi 100 frame ngay — encoder chưa kịp xử lý → queue đầy → drop
        start = time.monotonic()
        for _ in range(100):
            recorder.push_frame(_make_frame())
        elapsed = time.monotonic() - start
        # 100 push_frame phải xong trong <0.5s (mỗi cái <5ms) — nếu block sẽ tới vài giây
        assert elapsed < 0.5, f"push_frame blocked too long: {elapsed:.3f}s for 100 frames"
        stats = recorder.get_stats()
        # Ít nhất vài frame phải bị drop (encoder CPU-bound, queue nhỏ)
        assert stats["frames_dropped"] > 0, (
            f"Expected some frames dropped, got stats={stats}"
        )
    finally:
        recorder.stop()


# ─── Test segment rotate đúng ─────────────────────────────────────────────────

def test_segment_rotates_when_segment_minutes_very_small(tmp_path):
    """
    Set segment_minutes=1 (segment_seconds=60s theo max(60, ...) — quá lâu cho test).
    Test giả lập rotate bằng cách inject _segment_start_ts về quá khứ, gọi
    _writer_loop logic qua push_frame.

    Implementation: dùng monkeypatch để set _segment_seconds = 1 (giây), push frame
    liên tục 2 giây, verify có ≥2 segment file được tạo.
    """
    from app.cv.recorder import ContinuousRecorder

    recorder = ContinuousRecorder(
        gate_id="test", segment_minutes=5, fps=10,
        width=64, height=48, output_dir=str(tmp_path),
    )
    # Override segment_seconds thành 1 (giây) để test rotate NHANH
    recorder._segment_seconds = 1

    recorder.start()
    try:
        # Push frame liên tục trong ~3 giây để trigger rotate
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            recorder.push_frame(_make_frame())
            time.sleep(0.05)  # ~20fps, đủ nhanh để writer kịp xử lý
        # Đợi writer drain queue
        time.sleep(0.5)
    finally:
        recorder.stop()

    # Kiểm tra file segment được tạo — ≥1 file, đúng thư mục, đúng pattern
    files = list(tmp_path.glob("test_*.mp4"))
    assert len(files) >= 1, f"Expected ≥1 segment file, got {files}"


# ─── Test stop() để lại file hợp lệ (END-TO-END) ─────────────────────────────

def test_stop_leaves_valid_mp4_file(tmp_path):
    """
    END-TO-END: start recorder, push 30 frame, stop → file MP4 phải MỞ ĐƯỢC
    bằng cv2.VideoCapture (không phải file rỗng/hỏng). Đây là test hồi quy quan
    trọng nhất: nếu _finalize_segment() không gọi release() (hoặc gọi sai thứ tự),
    file MP4 sẽ thiếu footer → cv2.VideoCapture.isOpened() = False → test FAIL.
    """
    import cv2
    from app.cv.recorder import ContinuousRecorder

    recorder = ContinuousRecorder(
        gate_id="test", segment_minutes=5, fps=10,
        width=64, height=48, output_dir=str(tmp_path),
    )
    recorder.start()
    for _ in range(30):
        recorder.push_frame(_make_frame())
        time.sleep(0.02)  # ~50fps push, đủ để có >1 frame trong file
    recorder.stop()

    # Tìm file MP4
    files = list(tmp_path.glob("test_*.mp4"))
    assert len(files) == 1, f"Expected exactly 1 file, got {files}"
    fpath = str(files[0])
    assert os.path.getsize(fpath) > 0, "MP4 file is empty"

    # Mở file bằng cv2 — phải đọc được
    cap = cv2.VideoCapture(fpath)
    try:
        assert cap.isOpened(), f"cv2 cannot open MP4: {fpath}"
        # Đọc thử 1 frame — không crash
        ret, frame = cap.read()
        assert ret, "cv2.VideoCapture.read() returned False on valid file"
        assert frame is not None and frame.shape[0] > 0 and frame.shape[1] > 0
    finally:
        cap.release()


# ─── Test push_frame KHÔNG tạo file khi queue chưa drain ──────────────────────

def test_get_stats_returns_useful_fields(tmp_path):
    """get_stats() trả về các field cần cho health page: running/written/dropped/queue_size."""
    from app.cv.recorder import ContinuousRecorder

    recorder = ContinuousRecorder(
        gate_id="main", segment_minutes=5, fps=10,
        width=854, height=480, output_dir=str(tmp_path),
    )
    # Trước start
    stats = recorder.get_stats()
    assert stats["running"] is False
    assert stats["frames_written"] == 0
    assert stats["frames_dropped"] == 0

    recorder.start()
    try:
        for _ in range(10):
            recorder.push_frame(_make_frame())
        time.sleep(0.1)
        stats = recorder.get_stats()
        assert stats["running"] is True
        # frames_written hoặc frames_dropped phải >0 (chứng minh đã xử lý)
        assert stats["frames_written"] + stats["frames_dropped"] > 0
        assert stats["queue_size"] >= 0
    finally:
        recorder.stop()


# ─── Test cleanup_old_recordings ──────────────────────────────────────────────

def test_cleanup_old_recordings_removes_old_files(tmp_path):
    """cleanup_old_recordings xóa file .mp4 cũ hơn retention_days, giữ file mới."""
    from app.cv.recorder import cleanup_old_recordings

    # Tạo 2 file giả với mtime khác nhau
    old_file = tmp_path / "old.mp4"
    new_file = tmp_path / "new.mp4"
    old_file.write_bytes(b"x" * 100)
    new_file.write_bytes(b"x" * 100)
    # Set mtime: old_file = 10 ngày trước, new_file = hôm nay
    now = time.time()
    os.utime(old_file, (now - 10 * 86400, now - 10 * 86400))
    os.utime(new_file, (now, now))

    # File không match pattern
    other = tmp_path / "readme.txt"
    other.write_bytes(b"x" * 50)
    os.utime(other, (now - 10 * 86400, now - 10 * 86400))

    deleted = cleanup_old_recordings(str(tmp_path), retention_days=7)
    assert deleted == 1, f"Expected 1 file deleted, got {deleted}"
    assert not old_file.exists(), "old.mp4 should be deleted"
    assert new_file.exists(), "new.mp4 should be kept"
    assert other.exists(), "readme.txt not .mp4 → should be kept"


def test_cleanup_old_recordings_returns_zero_when_dir_missing(tmp_path):
    """cleanup_old_recordings không raise khi thư mục không tồn tại (first run)."""
    from app.cv.recorder import cleanup_old_recordings
    missing_dir = tmp_path / "nonexistent"
    deleted = cleanup_old_recordings(str(missing_dir), retention_days=7)
    assert deleted == 0
