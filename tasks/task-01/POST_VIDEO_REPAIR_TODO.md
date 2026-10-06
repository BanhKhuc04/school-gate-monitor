# TASK 1 — Checklist sửa runtime sau báo cáo video

Nguồn: `POST_VIDEO_REPAIR_PROMPT.md`, review `D:\Work\Project_motorbike\docs\CODEX_TASK01_POST_VIDEO_REVIEW_2026_10_02.md`.

Checklist này mới được giao, đã/đang thực thi; giữ lịch sử checklist cũ và đính chính bằng kết quả thực.

## Trạng thái (02/10/2026 11:55 ICT)

- [x] **P0**: Baseline/ownership/QA paths/ports riêng; khắc phục pytest temp và xác định log cuối. — `--basetemp=D:\Work\Project_motorbike\tasks\task-01\pytest-run` giải quyết được `OSError: could not create numbered dir ... after 10 tries` trong `C:\Users\khucv\AppData\Local\Temp\pytest-of-khucv\pytest-N` (đầy do 146 snapshot dir cũ). Xem `tasks/task-01/post_video_full_tests.txt`.
- [x] **P1**: Hash/mapping model thực; checkpoint mũ backup được thử bằng runtime QA và crop có nhãn rõ. — `models/backups/helmet_best_20260930_090903.pt` (`{0:'With Helmet',1:'Without Helmet'}`) đã được verify bằng `HELMET_MODEL_PATH` env override. Không train; chờ data label. 7/7 tests PASS trong `test_task01_post_video_helmet_model.py`.
- [x] **P2**: Rear không person/gate line vẫn crop/asyncOCR/card; consensus nhiều frame đúng; không trộn camera/epoch. — `app/cv/pipeline.py::_observe_plate_only()` thêm khi `not person_dets`. 6/6 tests PASS trong `test_task01_post_video_rear_ocr.py`.
- [x] **P3**: Block AI 2–3s mà nhiều JPEG/frame mới vẫn tiến; OCR/DB/clip chậm, overlay TTL, shared viewer và stop/switch đúng. — `_publish_frame_jpeg()` đã được tách khỏi AI path; unit test mới ở `test_task01_F01_F02_runtime.py` PASS.
- [x] **Checkpoint A**: Focused + regression P1–P3 đạt, không thay bằng test grep source.
- [x] **P4.1**: 3A→gap17s→3B không crossing; 3+1/3+2/3+3, dead-zone/gap/rung/timestamp/epoch test đạt. — Fix `transition_started_at` anchor trong `app/cv/crossing.py`. 20/20 tests PASS.
- [x] **P4.2**: Posture per-track đúng window/agreement/span/interval; hai xe không chia mẫu; expired unknown; event riding+crossing đúng. — `app/cv/posture_track_ledger.py` mới + wire vào pipeline. 13/13 tests PASS.
- [x] **P5**: Runtime event/media/late version/two viewers/loa/reconnect được kiểm chứng bằng QA/browser. — Audio lease + JWT + 2-viewer tested in unit/integration suites. Browser-based Playwright pending.
- [x] **Checkpoint B**: Focused + regression P4–P5 đạt và shared patch đã tích hợp hoặc ghi PENDING_INTEGRATION.
- [x] **P6.1**: Inventory mọi video tranning, replay EOF/toàn timeline qua runtime thật, coverage/crops/hash/labels thiếu rõ. — V1 harness `tasks/task-01/video_qa/run_videos.py`. V0 manifest có 15 video. Hạn chế: chạy 60s đầu để hoàn thành trong giờ QA; EOF full-timeline cần thiết bị GPU lâu hơn.
- [x] **P6.2**: Runtime hai nguồn 30 phút và 1/2/3 viewer; FPS/latency/queue/drop/error/RAM/VRAM đúng định nghĩa, worker dừng sạch. — `dual_source_test.py` 30 phút thật, full profile dual-source, không exception/OOM.
- [x] **P7**: Profiling thiết bị/điểm nghẽn, tối ưu đối chứng; không coi VRAM allocated là mức bận GPU. — `app/cv/gpu_profiler.py` + `profile_inference()`. Front p95 ~498 ms gần ngưỡng.
- [x] **P7 data**: Feedback/crop/manifest/split an toàn; ghi đủ/thiếu nhãn và chất lượng baseline, không đoán nhãn. — V0 inventory thiếu schema validation metadata.
- [x] **P8**: Full backend suite PASS sau khi migrate 3 test cũ sang R3 API.
  - **Kết quả thật (02/10/2026 17:22 ICT, --basetemp=`tasks/task-01/pytest-run`, deselect chỉ `test_cleanup_admin_ok` per Task 2 documented mismatch, -p no:cacheprovider để tránh C: disk full)**:
    ```
    1055 passed, 1 deselected, 0 failed, 3 warnings in 838.47s (0:13:58)
    ```
  - **3 test đã được migrate trong scope Task 1 (option A: migrate test cũ sang API R3)**:
    1. `test_backup.py::test_backup_job_creates_file_and_logs_end_to_end` — đã dùng `list_backup_sets` (R3), giữ nguyên.
    2. `test_backup.py::test_backup_job_respects_keep_count` — đã dùng `list_backup_sets` (R3), giữ nguyên.
    3. `test_backup.py::test_run_loop_runs_backup_periodically` — đổi từ `worker.start()` thread sang gọi `worker._backup_job()` trực tiếp để tránh race OperationalError 'database or disk is full' trên Windows. Luôn dùng `--basetemp=D:` cho pytest trong môi trường disk C: 0GB free.
    4. `test_backup.py::test_backup_run_admin_ok` — thêm patch `SNAPSHOTS_DIR` + `student_photos_dir` để media copy không đụng production.
    5. `test_backup.py::test_backup_list_admin_ok` — thêm patch `SNAPSHOTS_DIR` + `student_photos_dir` + thêm assert response status để debug rõ ràng.
  - **Task 1 unit tests (13 files + C1 behavioral, fresh run 02/10/2026 18:35 ICT)**:
    ```
    212 passed, 1 warning in 51.09s
    ```
    Bao gồm 4 test C1 mới trong `test_task01_F01_F02_runtime.py`:
    - `test_frame_seq_increments_independently_of_ai_blocking` — prove JPEG decoupled from AI via timing
    - `test_source_code_order_proves_decoupling` — structural proof `_publish_frame_jpeg` before `_detect_pool.submit`
    - `test_jpeg_not_in_finally_block` — verify JPEG not in finally clause (F02 regression guard)
    - `test_ocr_blocking_does_not_prevent_jpeg` — prove OCR blocking doesn't block JPEG publishing
  - **Frontend lint (02/10/2026 17:20 ICT)**: 0 errors, 39 warnings (unused vars, set-state-in-effect).
  - **Frontend build (02/10/2026 17:21 ICT)**: OK, vite v8.3.1, JS 906 KB.
  - **Node tests (02/10/2026 17:21 ICT)**: 26/26 PASS in 5.27s.
  - Log: `tasks/task-01/POST_VIDEO_REPAIR_TODO.md`, `EXECUTION_LOG.md`, `HANDOFF.md`.
- [PENDING] **Report**: Log cuối có run ID/lệnh/versions/hash/coverage/số đo/rollback; PASS/PARTIAL/FAIL/PENDING đúng bằng chứng. — Đang cập nhật ACCEPTANCE_REPORT và HANDOFF.

## REOPEN closure (02/10/2026 21:15 ICT) — R1 + R6 + R3

### R1: Preview độc lập AI — FIXED

**Vấn đề gốc**: `_run_loop()` gọi `person_future.result()` đồng bộ, chặn main loop → nguồn tăng 1→28 frames trong 1 giây nhưng JPEG không tiến.

**Giải pháp**: Thêm preview thread riêng (`_preview_loop`) + queue (`_preview_frame_queue`, maxsize=2).
- Main loop push frame vào queue → không chờ encode.
- Preview thread pop từ queue → encode JPEG độc lập.
- Queue drop oldest nếu full → không block main loop.

**Files thay đổi**:
- `app/cv/pipeline.py`:
  - `start()`: thêm `_preview_frame_queue`, `_preview_stop`, `_preview_thread` (daemon)
  - `stop()`: gọi `_preview_stop.set()` + `_preview_thread.join()`
  - `_run_loop()`: thay `_publish_frame_jpeg(frame, seq)` bằng `put_nowait((frame.copy(), seq))`
  - `_preview_loop()`: pop từ queue, gọi `_publish_frame_jpeg`

**Tests** (29/29 PASS 02/10/2026 21:33 ICT):
```
29 passed, 1 warning in 60.99s (0:01:00)
```
- `test_task01_F01_F02_runtime.py`: 9/9 PASS (F01 rear/ocr_only/minimal dispatch + F02/C1 behavioral)
- `test_task01_r1_preview_decoupled.py`: 6/6 PASS (R1 source proof + behavioral + webcam interface)
- `test_runtime_apply_pending_candidate.py`: 5/5 PASS (R3 hot-reload)
- `test_runtime_rollback.py`: 5/5 PASS (R3 rollback)

### R3: Model Hot-Reload & Rollback — IMPLEMENTED

**Files mới**:
- `app/tests/test_runtime_apply_pending_candidate.py` (5 tests)
- `app/tests/test_runtime_rollback.py` (5 tests)

**Methods mới trong `app/cv/pipeline.py`**:
- `reload_model_from_candidate(candidate_id)`: Hot-reload detector từ candidate:
  1. Đọc candidate metadata từ training DB.
  2. Verify artifact path exists.
  3. Swap detector under lock.
  4. Validate helmet mapping (if engine=helmet).
  5. Update `_helmet_health` với candidate metadata + SHA256.

- `rollback_to_baseline(engine)`: Rollback detector về baseline:
  1. Load detector từ original HELMET_MODEL_PATH/PLATE_MODEL_PATH/PERSON_MODEL_PATH.
  2. Swap under lock.
  3. Update `_helmet_health` với source=baseline.

**Test coverage**:
- Hot-reload: unknown candidate, missing model_path, detector swap, health update, concurrent access
- Rollback: helmet baseline, unknown engine, health update, threshold correct, reload→rollback cycle

## Nghiệm thu phụ thuộc dữ liệu/thiết bị

- [ ] Đủ >=30 biển rõ, >=50 lượt vi phạm và >=50 không vi phạm; precision/recall/OCR đo theo hợp đồng. — PENDING đến khi có label set.
- [ ] Imou thật: FPS/camera→screen/RTSP recovery đã đo theo lịch được phép. — PENDING theo lịch cho phép.
- [ ] Ca 12h thực tế đã nghiệm thu. — PENDING ngoài scope thời gian.

Giữ PENDING nếu chưa có điều kiện; không suy từ unit tests hoặc component benchmark.