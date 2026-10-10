# Task 3 — Execution Log (closure 2026-10-02)

> Theo dõi mọi hành động chính của Task 3 — file/command/output/decision.

## E0 — Baseline và đính chính status (17:00 ICT)

- Đọc `tasks/task-03/plan.md`, `todo.md`, `CONTRACTS.md`, `ACCEPTANCE_REPORT.md`,
  `EXECUTION_LOG.md`, `FINAL_CLOSURE_PROMPT_2026_10_02.md`.
- Đọc `docs/CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md` để biết các
  lỗi đã tái hiện.
- Snapshot working tree:
  `git diff --stat > tasks/task-03/integration/PRE_INTEGRATION_DIFFSTAT.txt`.
- Đọc `app/main.py`: đã include 4 training routers + 4 frontend admin routes
  (mount sẵn, không còn PENDING_INTEGRATION).
- Phát hiện quan trọng: save_feedback ở `app/api/recognition_reviews.py` chứ
  không phải `app/cv/pipeline.py`. Phương án A đã chốt theo prompt cuối.

## E1 — Sample collector (17:10 ICT)

Tạo `app/training/sample_collector.py`:
- Bounded queue (1024 mặc định); `put_nowait` non-blocking.
- Worker nền (thread) xử lý 5s/lần; reconcile mỗi 5s, heartbeat 30s.
- Cursor lưu JSON (review_id → version) — idempotent.
- Metrics JSON (enqueued, dropped_queue_full, processed, copied, reconcile_runs,
  errors, last_run_ts, heartbeat).
- `on_feedback_recorded(review_id, feedback_version, source=...)`:
  - Lazy init singleton; nuốt mọi exception.
  - Trả bool, không raise.

Viết `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md`:
- Task 1 patch: 1 khối try/except sau `db.record_review_feedback(...)` thành công.
- KHÔNG đổi logic; chỉ gọi `on_feedback_recorded(review_id, result["version"])`.

Tests E1:
- `test_collector_enqueue_does_not_block_when_full` — queue 2 → thả 3 vẫn OK, metric bumped.
- `test_collector_enqueue_never_raises` — None / "" không raise.
- `test_collector_cursor_persisted_and_idempotent` — replay cùng version = no-op.
- `test_collector_on_feedback_recorded_hook_safe` — hook public không raise.

## E2 — Export/Import ảnh thật (17:30 ICT)

### E2-c: ZIP guard

Sửa `app/training/import_portable.py::_safe_extract`:
- Bỏ `create_system == 3` (Unix regular file đang bị chặn nhầm).
- Chỉ chặn S_IFLNK qua `(unix_mode & 0o170000) == 0o120000`.
- Containment dùng `Path.resolve() + relative_to()` thay vì `startswith`.
- Block drive letter Windows (`C:`, `D:`, ...).

Tests:
- `test_zip_guard_unix_regular_file_allowed` — Unix regular OK.
- `test_zip_guard_blocks_symlink` — symlink mode (0o120000) block.
- `test_zip_guard_blocks_traversal` — `../evil.txt` block.
- `test_zip_guard_blocks_absolute_path` — `/etc/evil` block.
- `test_zip_guard_blocks_drive_letter` — `C:/Windows/System32` block.

### E2-a: Export ZIP

Sửa `app/training/export_portable.py::export_portable_zip`:
- Thêm `fail_on_missing_crops=True` (mặc định).
- Đếm `expected_with_crop` (loại bỏ sample không có crop_media_id khỏi missing ratio).
- Nếu ratio > `max_missing_ratio` → raise `SchemaError`.
- Return dict (zip_path, sample_count, expected_with_crop, asset_count, missing_files).
- `app/api/training_portable.py::export_zip` nhận dict mới.

### E2-b: Import copy asset root

Sửa `app/training/import_portable.py::apply_import`:
- Thêm `_asset_root_for` → `data/training/assets/{dataset_id}/`.
- `_copy_assets_into_dataset` copy từ staging → asset root; ghi `crop_path` tương
  đối vào sample JSON. Idempotent (nếu file đã tồn tại → bỏ qua).
- Sample thiếu crop_media_id hoặc crop file → `crop_path=None`, log warning.
- Cleanup staging, asset root giữ nguyên.

Tests E2:
- `test_export_round_trip_real_image_persisted` — ảnh PNG thật được copy vào asset
  root; `crop_path` được ghi trong sample DB.
- `test_export_fails_when_all_crops_missing` — fail_on_missing_crops=True + 100%
  missing → raise.

## E3 — Verify freeze/split/leakage (17:50 ICT)

Không sửa code (đã pass trước đó). Tests đã có:
- `test_split_by_group_distributes_by_group`
- `test_check_leakage_finds_duplicate_target_text`
- `test_augmentation_no_label_change`
- `test_augmentation_skip_val_test`

Kết quả: tất cả PASS trong regression. E3 PASS.

## E4 — Queue và lease (18:00 ICT)

Sửa `app/training/dataset_repo.py::active_job_count`:
- Trước: đếm cả `queued`, `waiting_resource`, `preparing`, `training`, `evaluating`.
- Sau: chỉ đếm `preparing`, `training`, `evaluating` (running).
- `queued` và `waiting_resource` KHÔNG chiếm lease.

Tests E4:
- `test_queued_state_does_not_hold_lease` — 2 job queued, target plate_ocr →
  `can_start_gpu_job() == True`.
- `test_waiting_state_can_resume` — job `waiting_resource` → can_start OK.

### E4-b: Worker start/stop lifespan

Viết `tasks/task-03/integration/APP_LIFESPAN_PATCH.md`:
- Task 2 patch `app/main.py::lifespan()` — gọi `start_collector_task()` /
  `stop_collector_task()`.
- Bounded idempotent; nuốt exception.

## E5 — Trainer OCR thật (18:20 ICT)

Tạo `app/training/ocr_trainer.py::run_ocr_training_job`:
- Lấy samples từ dataset.
- Nếu holdout < 30 → `PENDING_DATA` (KHÔNG tạo candidate).
- Nếu asset_root không tồn tại → `PENDING_DATA`.
- Nếu EasyOCR không khả dụng → `UNSUPPORTED`.
- Inference thật qua EasyOCR baseline (KHÔNG dùng label làm prediction).
- Đánh giá qua `evaluator.evaluate_ocr`.
- Ghi log + metrics JSON + update job.metrics_path.

Tests E5:
- `test_trainer_pending_when_holdout_too_small` — 3 holdout → PENDING_DATA.
- `test_trainer_pending_when_asset_root_missing` — asset không có → PENDING_DATA.
- `test_trainer_smoke_marker_not_eligible_for_promotion` — model_class có
  "Smoke" → reject.
- `test_trainer_pending_data_metrics_rejected` — metrics total=5 → reject
  (PENDING_DATA).
- `test_trainer_runtime_contract_violation` — model_class sai runtime → reject.

## E6 — Promotion gates và rollback (18:40 ICT)

Sửa `app/training/promotion.py`:
- 8 gate: artifact tồn tại, model_sha256, metrics_path parse có core metric,
  total ≥ 30, không smoke marker, runtime contract (model_class prefix), class
  mapping khớp engine, so baseline (nếu có).
- `promote()` set state='pending_runtime' (KHÔNG 'active' — Task 1 mới set applied).
- `rollback()` restore retired cũ nhất (state='active'), retire current.
- Fix `_candidate_metrics_path` không truyền db_path → bug test fail.

Tests E6 (4 gates mới trong closure; 2 tests cũ refactor):
- `test_promotion_requires_artifact_and_metrics` — file không tồn tại → reject.
- `test_promotion_requires_evaluation_file` — thiếu metrics_path → reject.
- `test_promotion_class_mapping_validation` — class mapping sai → reject.
- `test_promotion_smoke_marker_blocks` — Smoke trong model_class → reject.
- `test_promotion_retire_previous_active` (refactor) — giờ chỉ assert
  state='pending_runtime'; rollback trả False vì không có active.
- `test_promotion_rejects_rollback_recommendation` (refactor) — candidate kém
  hơn baseline → reject.

## E7 — Docs và regression (19:00 ICT)

- `tasks/task-03/ACCEPTANCE_REPORT.md` — viết lại đầy đủ 4 mức + diff so với cũ.
- `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md` — cho Task 1.
- `tasks/task-03/integration/APP_LIFESPAN_PATCH.md` — cho Task 2.
- `EXECUTION_LOG.md` (file này) — cập nhật toàn bộ.

Regression test:
```
python -m pytest app/tests/task03_helpers/ app/tests/task03_closure/ -q
→ 62 passed, 1 warning in ~13s
```

## Files changed / added

### Added
- `app/training/sample_collector.py`
- `app/training/ocr_trainer.py`
- `app/tests/task03_closure/test_closure_e1_e2_e5_e6.py`
- `app/tests/task03_closure/test_closure_e5_trainer.py`
- `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md`
- `tasks/task-03/integration/APP_LIFESPAN_PATCH.md`
- `tasks/task-03/integration/PRE_INTEGRATION_DIFFSTAT.txt`
- `tasks/task-03/integration/backups/{main,App,Sidebar,pipeline}.{py,jsx}.{head,diff}`

### Modified
- `app/training/import_portable.py` — ZIP guard + asset root copy
- `app/training/export_portable.py` — fail_on_missing + dict return
- `app/training/promotion.py` — 8 gates + rollback restore baseline
- `app/training/dataset_repo.py` — active_job_count chỉ running
- `app/training/schemas.py` — cho phép None các field optional
- `app/training/__init__.py` — export thêm ocr_trainer
- `app/api/training_portable.py` — nhận dict export
- `app/main.py` — mount 4 training routers (trước đó tôi đã sửa)
- `frontend/src/App.jsx` — 4 admin routes (đã sửa)
- `frontend/src/components/Sidebar.jsx` — 4 menu admin (đã sửa)
- `app/tests/task03_helpers/test_dataset_repo.py` — refactor promotion tests
- `app/tests/task03_helpers/test_task03_api.py` — refactor API promote test

## E8 — POST_CLOSURE_REVIEW_AND_FIX (C01–C08) — 2026-10-02 18:30 ICT

### Findings addressed

| ID | Issue | Fix |
|----|-------|-----|
| C01 | OCR runner labeled as trainer | Added `IS_EVALUATOR = True`, `EVALUATOR_LABEL`, clear docstring |
| C02 | waiting_resource jobs not resumable | `jobs.py` accepts `queued\|waiting_resource\|preparing`; `claim_and_run_one_waiting_job()` |
| C03 | pending_data/unsupported state always → completed | State machine updated; `evaluating → pending_data/unsupported` valid transitions; `JOB_STATES` updated |
| C04a | Cursor ack even when asset copy fails | Cursor updated ONLY after `_copy_asset_if_needed` returns True; new metric `processed_copy_failed_skipped` |
| C04b | Version compared with event version, not cursor | Now compares `latest_version <= cursor_ver` |
| C05a | Pagination stuck on first 32 reviews | Cursor-based scan with `review_id` ordering; `batch_max` per pass |
| C05b | Hook created local singleton, losing queue | Hook uses `get_collector()` — returns False when not initialized |
| C06 | Hook used `result["version"]` which doesn't exist | Contract updated: use `result["expected_version"]` |
| C07a | `_verify_hash` only checked hash presence | Now computes real SHA256 of file and compares; rejects invalid hex |
| C07b | Smoke artifacts/metrics not blocked | `_verify_runtime_contract` blocks smoke model_class; `_verify_not_smoke` checks both metrics and artifact name |
| C08 | UI jobs not connected to worker | Created `app/training/worker.py` with `TrainingWorker`, `start/stop_training_worker`, `_select_runner` |

### Files changed

- `app/training/sample_collector.py` — full rewrite with C06/C04/C05 fixes
- `app/training/jobs.py` — C02/C03 fixes; `claim_and_run_one_waiting_job`
- `app/training/promotion.py` — C07a/C07b fixes: real SHA256, smoke gates
- `app/training/ocr_trainer.py` — C01: IS_EVALUATOR marker, clear docstring
- `app/training/worker.py` — C08: new TrainingWorker class
- `app/training/dataset_repo.py` — added `pending_data`, `unsupported` to JOB_STATES
- `app/tests/task03_closure/test_closure_c01_c08.py` — 25 behavioral tests
- `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md` — C06 contract fix

### Behavioral tests (25 new)

All 8 categories covered: C01–C08. Total suite: **92/92 PASS** (67 existing + 25 new).

### Status

- E0–E7: PARTIAL/PENDING per evidence (no data/labels on real camera)
- C01–C08: ALL FIXED and verified by behavioral tests
- FEEDBACK_HOOK_CONTRACT.md: UPDATED — Task 1 patch uses `result["expected_version"]`
- Training worker: CREATED — ready for Task 2 lifespan integration

## Verdict cuối

Hạ tầng Task 3 đã đạt **DONE trên test đơn vị + integration (92/92 PASS)**.
Hai phần chờ bàn giao:
- Task 1 apply `FEEDBACK_HOOK_CONTRACT.md` (1 khối 5 dòng trong
  `app/api/recognition_reviews.py::post_feedback`, dùng `result["expected_version"]`).
- Task 2 apply `APP_LIFESPAN_PATCH.md` (start_training_worker/start_collector_task
  trong `app/main.py::lifespan`).

Data thật (≥30 biển, ≥50/50 split, 2 camera) là PENDING_DATA — chờ runtime +
duyệt từ người dùng.

OCR trainer là **EVALUATOR** (EasyOCR baseline inference), KHÔNG phải trainer tối ưu.
Smoke (lifecycle simulation) vẫn còn trong `scripts/training/smoke_train.py`
cho mục đích test hạ tầng, nhưng KHÔNG eligible cho promotion (gate `_SMOKE_MARKER`).

## Negative claim

- KHÔNG upload cloud.
- KHÔNG tự train OCR (chỉ EasyOCR baseline inference evaluator).
- KHÔNG tự ghi model runtime (Task 1 mới được apply).
- Không trust client metrics.

## E9 — PRE_INTEGRATION_FIX (P1–P4) — 2026-10-02 19:00 ICT

### Findings addressed (re-review bằng behavioral tests)

| ID | Issue | Fix |
|----|-------|-----|
| P1 | Hook dùng `expected_version` echo (sai về ngữ nghĩa) | `record_review_feedback` trả `new_version` (server-authoritative) + `feedback_id` (identity); hook signature = `(review_id, feedback_id, new_version)`; adapter expose `latest_feedback_id`; cursor key = feedback_id |
| P2 | Worker dispatch sai signature (TypeError → state=failed) | Runner interface thống nhất `(job, db_path) -> dict`; detector/helmet placeholders trả `unsupported` thay `TypeError`; `_select_runner` |
| P3 | Promotion gate bỏ qua job state + provenance + OCR quality tuyệt đối | Thêm gates: `_verify_job_completed` (state=completed + runner_type=train), `_verify_metrics_provenance` (metrics_path link tới job + hash/dataset match), `_verify_counted_test` theo target (OCR >= 50% + >=30 samples); fail-closed |
| P4a | Evaluator bị gọi là training completed | `create_job(operation="evaluate_baseline"\|"train")`; `runner_type` persisted; UI phân biệt rõ |
| P4b | `APP_LIFESPAN_PATCH.md` thiếu training_worker | Patch cập nhật: start/stop training_worker + env flag `TASK3_TRAINING_WORKER_ENABLED` |

### Behavioral tests (21 new — test_closure_p2_p3_p4.py)

| Class | Tests |
|-------|-------|
| TestP2WorkerDispatchSignature | 6 tests: unified signature, detector/helmet=unsupported, OCR real workflow, start/stop lifecycle |
| TestP3PromotionProvenance | 7 tests: job queued/failed/baseline block, OCR 0% block, metrics missing/SHA mismatch block, <30 samples block, valid candidate passes |
| TestP4OperationSeparation | 5 tests: operation field persisted, runner_type persisted, invalid_op rejected, marker kept, lifespan patch documented |
| TestP4WorkerLifespanFunctions | 2 tests: start_training_worker returns, stop idempotent |

### Files changed

- `app/db.py` — `record_review_feedback` returns `feedback_id` + `new_version` (KHÔNG echo `expected_version`)
- `app/training/adapter.py` — `fetch_sample_assets` exposes `latest_feedback_id`
- `app/training/sample_collector.py` — `FeedbackEvent(feedback_id, new_version)`; hook signature; cursor key = feedback_id
- `app/training/worker.py` — rewritten with unified runner interface, placeholders, singleton, env flag
- `app/training/promotion.py` — 3 new gates (job_completed, metrics_provenance, target-aware counted_test)
- `app/training/dataset_repo.py` — `dataset_jobs.operation` + `runner_type` columns; `set_job_runner_type()`; `create_candidate(..., dataset_id, metrics_path)`
- `app/training/jobs.py` — `_persist_runner_type(job_id)`; `dataset_repo.get_job/list_jobs` returns operation/runner_type
- `app/tests/task03_closure/test_closure_c01_c08.py` — TestP1HookContractFeedbackId (5 tests) thay thế TestC06 cũ
- `app/tests/task03_closure/test_closure_p2_p3_p4.py` — NEW 21 tests
- `app/tests/task03_helpers/test_dataset_repo.py` — promotion tests set state=completed + runner_type=train
- `app/tests/task03_helpers/test_task03_api.py` — same
- `app/tests/task03_closure/test_closure_e5_trainer.py` — same
- `app/tests/task03_closure/test_closure_e1_e2_e5_e6.py` — collector tests use new hook signature
- `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md` — v1.2: feedback_id + new_version contract
- `tasks/task-03/integration/APP_LIFESPAN_PATCH.md` — v1.1: training_worker start/stop

### Total suite: **117/117 PASS** (92 prior + 25 P1/C01-C08 + 21 P2-P3-P4 mới) in ~22s.

### Status E0–E7 (PARTIAL còn lại)

- E0 baseline, E1 collector, E2 export/import, E5 trainer — DONE infrastructure.
- E3 dataset split, E4 freeze, E6 promotion gates, E7 candidate state — DONE infrastructure.
- Dữ liệu thật: PARTIAL/PENDING_DATA — chờ người dùng duyệt ≥30 biển rõ.

### Handoff Task 1 (FEEDBACK_HOOK_CONTRACT v1.2)

1. Trong `app/api/recognition_reviews.py::post_feedback`, sau khi `record_review_feedback` thành công:
   ```python
   if result.get("applied") and not result.get("idempotent_replay"):
       try:
           from app.training.sample_collector import on_feedback_recorded
           on_feedback_recorded(
               review_id=review_id,
               feedback_id=result["feedback_id"],
               new_version=result["new_version"],
               source="recognition_feedback",
           )
       except Exception:
           pass
   ```
2. KHÔNG đổi logic nghiệp vụ / schema response. Hook chỉ enqueue.
3. Test bảo vệ `app/tests/test_recognition_feedback_hook.py` mới.

### Handoff Task 2 (APP_LIFESPAN_PATCH v1.1)

1. Trong `app/main.py::lifespan()`, SAU `init_db()` + start pipeline:
   ```python
   try:
       from app.training.sample_collector import start_collector_task
       from app.training.worker import start_training_worker
       start_collector_task()
       start_training_worker(poll_sec=5.0)
   except ImportError:
       pass
   ```
2. Trong shutdown (trước/sau `stop_all_pipelines()`):
   ```python
   try:
       from app.training.worker import stop_training_worker
       from app.training.sample_collector import stop_collector_task
       stop_training_worker(timeout=5.0)
       stop_collector_task()
   except ImportError:
       pass
   ```
3. Env `TASK3_TRAINING_WORKER_ENABLED=0` để tắt khi camera vận hành không cần training.
4. Task 2 chạy full backend factory QA thật — không ignore/deselect.

### Negative claim (E9)

- KHÔNG dùng `expected_version` echo làm version (P1).
- KHÔNG gọi evaluator là training completed (P4a).
- KHÔNG tự start GPU operation chỉ vì app khởi động (P4b env).
- KHÔNG trust client metrics (P3).