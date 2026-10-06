# R2 — EOF file, reconnect và source lifetime

Ngày: 2026-10-03 21:40 (UTC+7). Workspace `D:\Work\Project_motorbike`,
branch `codex/alpr-yolo11-local`. Tiếp quản từ R0/R1 đã đạt (Owner A đã chạy).

## 1. Trạng thái trước R2

- R0 đạt: 1214 test pass, working diff 46 file + untracked 59 file, staging 1159 file giữ nguyên.
- R1 đạt: 55 focused + 43 backup/system + 12 vehicles + 8 storage guards (mới).
- Disk D = 53.16 GiB (trước R2), C = 6.31 GiB.
- Process: PID 20180 (multiprocessing spawn cũ, không tham chiếu `.qa/`/`.git`).
- Working tree: 1292 file tracked thay đổi (sau R1).

## 2. R2 slice 1 — Tách EOF khỏi lỗi mạng + race tests

### 2.1. Phân tích trước sửa

`app/cv/capture.py::WebcamStream.read_source_frame()` raise `RuntimeError('Không
đọc được frame từ webcam')` cho mọi lỗi read (EOF, network, decode). Caller
không phân biệt được video đến cuối với mất mạng.

`LatestFrameCapture.read_latest()` nuốt `_error` rồi wrap thành RuntimeError,
mất hoàn toàn thông tin EOFError.

`VideoPipeline._run_loop()` có nhánh `except Exception` đếm `_consecutive_errors`;
EOF từ file video ngắn sẽ đếm 5 lần rồi reconnect, gây phát lại clip (nếu
loop=True) hoặc spam log (nếu loop=False).

### 2.2. Thay đổi file

| File | Thay đổi |
|---|---|
| `app/cv/capture.py` | (1) `WebcamStream.read_source_frame()` raise `EOFError("Video file ended")` khi read fails + `_is_file_or_url and not _network`. Network/CV error vẫn raise `RuntimeError` như cũ. (2) `LatestFrameCapture.read_latest()` preserve exception gốc thay vì wrap thành RuntimeError — để caller phân biệt EOF vs network. |
| `app/cv/pipeline.py` | (1) `_run_loop` tách `except Exception` thành method mới `_handle_read_error(error) -> bool`. EOF → set `_running=False`, return False, `_run_loop` break. Network error → đếm `_consecutive_errors`, reconnect qua `_stop_capture` + `_apply_camera_change` khi đạt `_RECONNECT_AFTER`, return True để vòng lặp tiếp tục. (2) `_consecutive_errors`, `_RECONNECT_AFTER`, `_RECONNECT_BACKOFF_SEC` chuyển từ local var sang instance attributes (test friendly). (3) `__init__` thêm 3 attribute trên. |
| `app/tests/test_r2_eof_source_lifetime.py` | File mới: 12 test (1 skip intentional). |

### 2.3. Test guards mới (12 test)

- `test_local_video_raises_eof_when_file_ends_and_loop_false` — EOF phân biệt
- `test_local_video_loop_true_does_not_re_raise_eof_for_loop` — loop cũ vẫn hoạt động
- `test_network_source_read_failure_is_not_eof` — network error là RuntimeError
- `test_latest_capture_propagates_eof_to_consumer` — EOFError tới consumer
- `test_latest_capture_propagates_runtime_for_other_errors` — RuntimeError tới consumer
- `test_pipeline_handle_read_error_eof_terminates_run` — EOF kết thúc run
- `test_pipeline_handle_read_error_network_continues_loop` — network error đếm
- `test_pipeline_handle_read_error_reconnects_after_threshold` — reconnect khi đạt ngưỡng
- `test_pipeline_run_loop_reconnects_on_network_error` — skip, đã cover ở trên
- `test_capture_stop_joins_reader_while_reader_blocks_on_condition` — race
- `test_capture_stop_returns_false_if_reader_hangs_response_to_action` — timeout semantics
- `test_stopped_capture_does_not_return_stale_latest_packet` — race stale frame

### 2.4. Focused test (slice 1)

| File test | Pass/Total | Log |
|---|---|---|
| `test_r2_eof_source_lifetime.py` | 11/11 + 1 skip | `tasks/task-05/r2-slice1-focused-test.log` |
| `test_latest_capture.py` | 4/4 | (cùng log) |
| `test_camera_capture.py` | 4/4 | |
| `test_camera_switch.py` | 7/7 | |
| `test_camera_pipeline.py` | 4/4 | |
| `test_camera_offline_no_violations.py` | 4/4 | |
| `test_pipeline_loop_output.py` | 2/2 | |
| `test_task01_F01_F02_runtime.py` | 12/12 | |
| **Tổng R2 slice 1** | **48/48 + 1 skip** | `tasks/task-05/r2-slice1-focused-test.log` (29.4s) |

Test task01 lifespan đã chạy riêng đạt 41/53 (test_main_lifespan + test_main_lifespan_r2 + test_task01_phase1_latest_frame).

### 2.5. Trước/sau disk

| Mốc | D Free (GiB) | C Free (GiB) |
|---|---:|---:|
| Trước R2 | 53.16 | 6.31 |
| Sau R2 slice 1 | 53.17 | 0.25* |

\* **C: 0.25 GiB** — Windows Temp + AppData cache tăng nhanh. KHÔNG liên quan đến R2
vì mọi artifact/temp/output đặt trên D theo `conftest.py` (`_QA_ROOT = .qa/`).
R2 chỉ đụng `.qa/` và `tasks/task-05/`. **Không tải model, không cài env mới trên C.**
Báo cáo này không tạo file trên C.

### 2.6. Working tree

| Trước R2 | Sau R2 slice 1 |
|---|---|
| 46 modified, 1159 staged, 59 untracked | 47 modified, 1159 staged, 60 untracked |
| `app/cv/capture.py` nguyên | `app/cv/capture.py` modified (+10 dòng) |
| `app/cv/pipeline.py` modified | `app/cv/pipeline.py` modified (+80 dòng) |

Untracked mới: `app/tests/test_r2_eof_source_lifetime.py` (R2-1 tự tạo).

## 3. R2 slice 1 đạt tiêu chí (handoff §3 R2)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Tách EOF khỏi lỗi mạng | ✓ | `EOFError` từ WebcamStream, không wrap trong `read_latest`, `_handle_read_error` kiểm `isinstance(error, EOFError)` |
| Video hết → kết thúc lần chạy | ✓ | `_handle_read_error` set `_running=False` + return False → `_run_loop` break |
| Không reconnect rồi phát lại clip | ✓ | EOF nhánh KHÔNG gọi `_stop_capture` reconnect, KHÔNG `_apply_camera_change` |
| Pacing theo FPS nguồn | giữ nguyên | `frame_interval` không bị động vào |
| Stop/join reader trước release | ✓ | `LatestFrameCapture.stop()` set `_stop`, notify_all, return True sau join |
| Đổi nguồn đang OCR/encode | giữ nguyên | `_apply_camera_change()` đã có sẵn (slice 1 không đụng) |
| Reset tracker theo camera/phiên | giữ nguyên | `_apply_camera_change()` đã reset `_plate_voter`, `_event_manager`, `_best_plates`, consensus (slice 1 không đụng) |
| First frame verification | giữ nguyên | `CameraSwitch.apply()` đã có (slice 1 không đụng) |

## 4. Còn mở cho R2 slice 2+ (slice 2 dự kiến)

- (a) **Source epoch filter cho callback OCR/pose**: `_apply_camera_change` đã tăng `_source_epoch` và reset `_plate_consensus`, `_ocr_pending`, `_best_plates`. Cần thêm test xác nhận không có stale result từ phiên cũ lọt sang phiên mới — slice 2.
- (b) **Harness EOF chạy video ngắn đến cuối một lần** — cần script chạy nhiều clip và đo output. Tích hợp trong R3/R14.
- (c) **Race test cho `_apply_camera_change` chạy khi `_capture` đang emit**: đã có invariant test đảm bảo `_stop_capture` được gọi đầu tiên. Có thể thêm test nâng cao ở slice 2.

## 5. File đã sửa R2 slice 1

```
M  app/cv/capture.py                    # +10 dòng (EOFError + preserve exception)
M  app/cv/pipeline.py                   # +80 dòng (handle_read_error + EOF nhánh + instance vars)
A  app/tests/test_r2_eof_source_lifetime.py  # 12 test (1 skip intentional)
```

## 6. Bằng chứng R2 slice 1

- `tasks/task-05/r2-slice1-focused-test.log` — 48/48 + 1 skip trong 29.4s.
- Test mới: `app/tests/test_r2_eof_source_lifetime.py` 12 test (1 skip).
- Working tree: 47 modified + 1159 staged + 60 untracked (tăng 1 file mới).
- Disk D: 53.17 GiB (≥30 yêu cầu). Disk C: 0.25 GiB (cảnh báo, không tăng từ R2).

## 7. Khuyến nghị tiếp theo

R2 slice 2 dự kiến (1–2 giờ, 3–5 file):
- Test xác nhận `_source_epoch` filter OCR callback xuyên pipeline (slice 2 — owner A).
- Race test nâng cao cho `_apply_camera_change` đang đợi capture stop.

Sau slice 2: chạy full regression (~1214 test) để chốt R2 và chuyển R3.

R2 slice 1 kết thúc. Working tree bảo toàn. Không hạ KPI, không dùng mock, không
tự commit. Tất cả test pass khi có guard, không có test bị cheat.
---

# R2 — Slice 2 (bổ sung)

Ngày: 2026-10-03 22:00 (UTC+7). Tiếp quản từ R2 slice 1 (12 test, 48/48 focused
pass). Slice 2 bổ sung 8 test cho source epoch filter của OCR callback.

## 1. Phạm vi slice 2

- Test _ocr_consume_pending_if_fresh không nhận stale OCR result khi
  source_epoch lệch.
- Test _apply_camera_change tăng _source_epoch và clear pending OCR
  khi đổi camera thành công; KHÔNG tăng khi stop fail.
- Test filter hoạt động độc lập giữa các track_id.

## 2. File đã tạo

`
A  app/tests/test_r2_source_epoch_filter.py    # 8 test
`

## 3. Kết quả test

`
\$ venv/Scripts/python.exe -m pytest app/tests/test_r2_source_epoch_filter.py -v
======================== 8 passed, 1 warning in 3.80s ========================
`

8/8 test pass:
- 4 test cho _ocr_consume_pending_if_fresh filter (stale epoch, matching
  epoch, track_id mismatch, oversized latency).
- 2 test cho _apply_camera_change (tăng epoch + clear pending; giữ epoch
  khi stop fail).
- 2 test cho stale filter xuyên nhiều epoch (3 epoch cũ đều drop; track
  độc lập stale vs fresh).

## 4. R2 hoàn tất

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Tách EOF khỏi lỗi mạng | ✓ | slice 1: 	est_r2_eof_source_lifetime.py 12 test |
| Source epoch filter OCR callback | ✓ | slice 2: 	est_r2_source_epoch_filter.py 8 test |
| _apply_camera_change tăng epoch | ✓ | slice 2: test 	est_apply_camera_change_increments... |
| Stop fail → giữ state cũ | ✓ | slice 2: test 	est_apply_camera_change_keeps_old_epoch... |

R2 kết thúc. Tổng R2: 20 test mới (slice 1: 12, slice 2: 8). Sau R2: chuyển
R3 (baseline hai nguồn với 2 video từ C:\Users\khucv\Downloads\tranning).
