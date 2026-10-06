# TASK 1 — HANDOFF

**Date**: 2026-10-02 (UTC+7)
**Repo**: `D:/Work/Project_motorbike`
**Working tree**: Task 1 changes chưa commit; Task 1 changes hoàn toàn trong
các file thuộc scope, không đụng vào `app/db/migrations/`, schema, model
artifacts, hoặc runtime config vận hành.

## Thay đổi đã áp dụng

### Sửa review F01–F08

| File | Mô tả |
|------|------|
| `app/cv/pipeline.py` | (F01) Capability-aware submit, pre-resolved empty futures khi detector=None. (F01) `stop()` getattr trên pool None. (F02) `_publish_frame_jpeg()` ra khỏi finally, encode cache theo `frame_seq`. (F07) `dispatch_late_issues()` merge by code, accumulate sample, idempotent. |
| `app/cv/plate_consensus.py` | (F04) `decide()` filter quality, contender gate. |
| `app/cv/gate_event_matcher.py` | (F08) Hard gates trước scoring, ambiguity check trước exact short-circuit. |
| `app/cv/crossing.py` | (F05) `min_frames_exit_side=3`, `max_transition_sec=5.0`. |
| `app/config.py` | (F04) `PLATE_CONSENSUS_MIN_QUALITY`, `PLATE_CONSENSUS_CONTENDER_*`. (F05) `CROSSING_MIN_FRAMES_EXIT_SIDE`, `CROSSING_MAX_TRANSITION_SEC`. |
| `app/cv/helmet_contract.py` | (F06) Mapping validator. |
| `app/cv/gpu_profiler.py` | (F09) Profiler plumbing. |

### Tests mới

- `app/tests/test_task01_F01_F02_runtime.py` (8 tests)
- `app/tests/test_task01_F04_consensus_quality.py` (7 tests)
- `app/tests/test_task01_F07_late_issues.py` (6 tests)
- `app/tests/test_task01_phase0_metrics.py` (24 tests)
- `app/tests/test_task01_phase1_latest_frame.py` (20 tests)
- `app/tests/test_task01_phase2_plate_consensus.py` (23 tests)
- `app/tests/test_task01_phase3_posture.py` (32 tests)
- `app/tests/test_task01_phase4_crossing_finalize.py` (20 tests)
- `app/tests/test_task01_phase5_gate_matcher.py` (21 tests)
- `app/tests/test_task01_phase6_gpu_profiler.py` (20 tests)
- `app/tests/test_task01_post_video_helmet_model.py` (7 tests)
- `app/tests/test_task01_post_video_posture_per_track.py` (13 tests)
- `app/tests/test_task01_post_video_rear_ocr.py` (6 tests)

**Tổng Task 1 unit tests: 208 PASS** (verified fresh run 02/10/2026 11:55 ICT, 80.59s).

### Video QA artifacts

- `tasks/task-01/video_qa/build_manifest.py` — V0 inventory (SHA256, dims, fps, codec).
- `tasks/task-01/video_qa/run_videos.py` — V1 harness qua pipeline thật.
- `tasks/task-01/video_qa/dual_source_test.py` — V2 30-min concurrent.
- `tasks/task-01/video_qa/manifest.json` — metadata 15 video.
- `tasks/task-01/video_qa/results.json` — per-video metrics.
- `tasks/task-01/video_qa/concurrent_results.json` — V2 metrics.
- `tasks/task-01/video_qa/quality_summary.txt` — top plates + class counts.

### Docs

- `tasks/task-01/REPAIR_TODO.md` — checklist F01–F08 / V0–V2.
- `tasks/task-01/EXECUTION_LOG.md` — phase-by-phase log.
- `tasks/task-01/CONTRACTS.md` — gate/camera/track/behavior/violation contracts.
- `tasks/task-01/VIDEO_TEST_REPORT.md` — per-video results, PENDING markers.
- `tasks/task-01/ACCEPTANCE_REPORT.md` — F01–F08 status, PASS/FAIL/PENDING.
- `tasks/task-01/HANDOFF.md` — file này.

## Cách chạy lại

```powershell
cd D:\Work\Project_motorbike
$env:PYTHONPATH = "D:\Work\Project_motorbike"

# Backend full test (fresh tmp dir để tránh OSError)
.\venv\Scripts\python.exe -m pytest app/tests --no-header -q `
    --basetemp="D:\Work\Project_motorbike\tasks\task-01\pytest-run" `
    --deselect app/tests/test_system.py::test_cleanup_admin_ok

# Frontend lint + build
npm --prefix frontend run lint
npm --prefix frontend run build

# Node tests
Get-ChildItem -LiteralPath frontend/test -Filter '*.test.mjs' -File `
  | ForEach-Object { $_.FullName } | ForEach-Object { node --test $_ }

# Video V0 (manifest)
.\venv\Scripts\python.exe tasks/task-01/video_qa/build_manifest.py

# Video V1 (per-video harness)
Start-Process -FilePath .\venv\Scripts\python.exe `
  -ArgumentList "tasks/task-01/video_qa/run_videos.py" `
  -WorkingDirectory "D:\Work\Project_motorbike" `
  -RedirectStandardOutput "tasks/task-01/video_qa/run_videos.out" `
  -RedirectStandardError  "tasks/task-01/video_qa/run_videos.err" `
  -PassThru | Select-Object -ExpandProperty Id

# Video V2 (30-min dual source)
Start-Process -FilePath .\venv\Scripts\python.exe `
  -ArgumentList "tasks/task-01/video_qa/dual_source_test.py",
    "C:\Users\khucv\Downloads\tranning\1790589989054_*.mp4",
    "C:\Users\khucv\Downloads\tranning\1790587817091_*.mp4",
    "30" `
  -WorkingDirectory "D:\Work\Project_motorbike" `
  -RedirectStandardOutput "tasks/task-01/video_qa/concurrent.out" `
  -RedirectStandardError  "tasks/task-01/video_qa/concurrent.err" `
  -PassThru | Select-Object -ExpandProperty Id
```

## Tích hợp với Task 2

- `app/cv/pipeline.py`, `app/cv/plate_consensus.py`, `app/cv/crossing.py`,
  `app/cv/gate_event_matcher.py` đã sửa; **không đụng schema**, không
  đổi API endpoints, không đổi DB migration.
- `app/tests/test_system.py::test_cleanup_admin_ok` failure là pre-existing
  Task 2 schema mismatch; đã được `-k` deselect trong full-suite này.
- `app/tests/test_backup.py::test_backup_job_creates_file_and_logs_end_to_end`,
  `test_backup_job_respects_keep_count`, `test_run_loop_runs_backup_periodically`
  là pre-existing test/legacy mismatch thuộc ownership Task 2 (Task 2 đã
  refactor `_backup_job` sang `create_backup_set` R3 nhưng chưa migrate 3
  test cũ sang API mới). Task 1 không sửa chồng — đề nghị Task 2 owner
  migrate sang `list_backup_sets()`.
- Khi Task 2 merge schema, re-run full suite **không deselect** để verify
  toàn bộ.

## Rollback

- Phase 0/1/2/3/4/5/6 là ADDS-ONLY (xem `EXECUTION_LOG.md` từng phần).
- Phase 1: set `_run_generation` về 0; chấp nhận stale persist (legacy).
- F02: `_publish_frame_jpeg` trong finally về như cũ.
- F04: `PLATE_CONSENSUS_MIN_QUALITY=0`, `PLATE_CONSENSUS_CONTENDER_CONFIDENCE=1.0` → bypass.
- F05: `CROSSING_MIN_FRAMES_EXIT_SIDE=1`, `CROSSING_MAX_TRANSITION_SEC=600`.
- F07: `_crossing_event_to_db_id = {}` → dispatch trở no-op.
- F08: matcher đã OFF mặc định; không cần rollback.

## PENDING cần người khác

| Hạng mục | Lý do PENDING | Cần gì |
|------|------|------|
| Imou RTSP validation | production camera, ngoài Task 1 scope | lịch nghiệm thu thực tế |
| 12 giờ continuous soak | time scope | chạy trong task riêng |
| Playwright E2E | UI seed đụng Task 2 | seed tự động / fixture |
| Helmet model đúng vai trò | `helmet_best.pt` chỉ có class `plate` | train lại |
| OCR ≥50% trên ≥30 biển có nhãn | không có ground-truth | gán nhãn cho ≥30 biển |
| Gate matcher khác runtime caller | chưa có cặp lượt có nhãn 2 camera | labeled dual-camera pairs + calibration |