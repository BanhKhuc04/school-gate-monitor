# TASK 4 — NEXT ACTIONS

**Ngày cập nhật**: 2026-10-02

## Immediate Actions (T1 owner)

### Fix 8 test failures từ full regression

T1 preview-thread refactor (queue maxsize=2 + daemon thread) làm các test cũ fail khi chạy full suite. Test pass individually → shared state issue.

**Failed tests cần fix**:

1. `test_camera_offline_no_violations.py::test_frame_without_person_skips_violation_check`
2. `test_dot_R.py::TestR1CaptureDecoupling::test_source_epoch_increments_on_camera_change`
3. `test_dot_R.py::TestR3JpegCache::test_camera_change_discards_old_jpeg`
4. `test_pipeline_loop_output.py::test_real_loop_publishes_every_new_frame_including_skips` (×2)
5. `test_runtime_apply_pending_candidate.py::TestReloadModelFromCandidate::test_reload_helmet_candidate_swaps_detector`
6. `test_runtime_apply_pending_candidate.py::TestReloadModelFromCandidate::test_reload_updates_helmet_health`
7. `test_runtime_apply_pending_candidate.py::TestReloadSnapshotDetection::test_reload_preserves_lock_integrity`
8. `test_camera_pipeline.py::test_source_switch_preserves_pipeline_and_models_but_clears_scene` (ERROR: gate_roi table missing)

**Errors**:
- `test_camera_pipeline.py::test_pipeline_recovers_from_failed_startup_via_source_selection`
- `test_camera_pipeline.py::test_bad_change_leaves_existing_frame_available`

**Cách fix**:
- Update tests để drain `_preview_frame_queue` trước khi assert (`p._preview_stop.set(); p._preview_thread.join(timeout=1)`).
- Hoặc dùng `p._publish_frame_jpeg()` trực tiếp trong test thay vì qua queue.
- Thêm conftest fixture cho `gate_roi` table.
- Sửa `test_runtime_apply_pending_candidate` để isolate state giữa các test (DB cleanup).

## PENDING_HARDWARE Items

### PENDING_VIDEO_FILES
- `C:/Users/khucv/Downloads/tranning/` rỗng — cần upload 15 MP4.
- Sau khi có data, execute `tasks/task-04/video_runtime_measure.py` đến EOF (không 20s).
- Ghi FPS, capture/AI latency p95, RAM/VRAM đầu/giữa/cuối.

### PENDING_DUAL_SOURCE_30MIN
- Cần 2 camera thật (front + rear).
- Capture đồng thời 30 phút.
- 1/2/3 viewer test.
- Đo receive→JPEG p50/p95, OCR queue/drops, latency nội bộ p95 ≤500ms.
- Mục tiêu: preview ≥15 FPS/camera, AI ≥5 FPS/camera.

### PENDING_DETECTOR_HELMET_RUNNER
- T3 runner.py có contract CODE_PARTIAL.
- Cần YOLO weights thật cho plate_detector và helmet.
- Cần label helmet dataset chuẩn.
- Sau khi có weights, update `runners.py` để return `state=completed` thay vì `state=unsupported`.

### PENDING_IMOU_LAN_12HOUR
- Imou camera reconnect test (LAN drop, IP change).
- 12-hour continuous run với monitor RAM/VRAM drift.

## File ownership

| File | Owner |
|------|-------|
| `app/cv/pipeline.py` | T1 |
| `app/main.py` | T4 (lifespan refactor) |
| `app/training/promotion.py` | T3 |
| `app/training/runner.py` | T3 |
| `app/api/training_candidates.py` | T3 |
| `app/api/media.py` | T2 |
| `app/api/auth.py` | T2 |
| `tasks/task-04/*` | T4 |

## Báo cáo từ T1/T2/T3 đã hoàn thành

✅ T1: R1+R6 integrated; R3 apply path added — 29/29 PASS.
✅ T2: E2E browser verified; media restore with assets verified — 8+6 PASS + Chrome DevTools drives.
✅ T3: NaN/loadability gates added; feedback→dataset hook verified; runner contract documented — 154/154 PASS.
✅ T4: Full regression — 1162/1173 PASS (8 fail + 3 err do T1 preview-thread refactor).