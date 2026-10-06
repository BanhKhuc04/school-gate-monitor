# R4 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R4 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: ByteTrack thật, liên kết biển–xe
theo hình học và thời gian, tracker theo camera/epoch dù weights/predictor
dùng chung.

## 1. Công cụ / test Owner A tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r4_bytetrack_wiring.py` | 8 test cho ByteTrack wiring (track_id ổn định, camera_id riêng, reset, class mapping) |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r4_bytetrack_wiring.py -v
======================== 8 passed, 1 warning in 4.84s ========================
```

8/8 test pass:
- `test_track_id_stable_across_frames_with_same_position` — 5 frame cùng vị trí → cùng track_id
- `test_different_camera_ids_get_independent_trackers` — front/rear có tracker riêng
- `test_reset_tracker_calls_underlying_reset` — reset_tracker gọi underlying BYTETracker.reset()
- `test_reset_tracker_safe_when_tracker_is_none` — lazy init an toàn
- `test_detect_returns_track_id_none` — detect() (không tracked) trả track_id=None
- `test_detect_tracked_invokes_tracker_update` — detect_tracked() gọi BYTETracker.update
- `test_tracked_detection_uses_class_names_mapping` — class_names mapping đúng
- `test_empty_boxes_does_not_crash_tracker` — empty boxes không crash

## 3. Đã có sẵn trong codebase

- `app/cv/detector.py::HelmetPlateDetector` đã wire sẵn BYTETracker:
  - `detect_tracked(frame)` qua `model_owner().run(camera_id, self._infer, frame, True)`
  - `_infer()` lazy init `BYTETracker` với config (track_high_thresh=.5, track_low_thresh=.1, ...)
  - `reset_tracker()` reset state theo camera_id

## 4. R4 đạt tiêu chí (handoff §3 R4)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Tracker cho ID ổn định xuyên frame | ✓ | test_track_id_stable_across_frames |
| Tracker theo camera/epoch riêng | ✓ | test_different_camera_ids_get_independent_trackers |
| Reset tracker per source | ✓ | test_reset_tracker_calls_underlying_reset |
| Class mapping đúng | ✓ | test_tracked_detection_uses_class_names_mapping |
| Test track moving, xe sát nhau, mất track/đổi nguồn | giữ nguyên | slice R3/R14 — cần video thật có nhiều object |
| Liên kết biển với vehicle track theo hình học/thời gian | Owner A chưa | plate-vehicle association thuộc R5/R11 |

## 5. Còn mở

- Test track moving qua ô ảnh, xe sát nhau — cần video fixture có multi-object
- Liên kết biển–vehicle theo hình học/thời gian (R5/R11)
- ByteTrack thật với model YOLO11 weights (R10/R7)

R4 kết thúc. Working tree bảo toàn. Không tự commit.
