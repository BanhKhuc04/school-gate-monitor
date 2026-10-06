# Task 3 — Acceptance Report (closure 2026-10-02)

> Phiên bản: closure (áp dụng FINAL_CLOSURE_PROMPT_2026_10_02.md).
> Phân biệt 4 mức: đã viết mã / test hành vi đạt / đã đo video / đã nghiệm thu thiết bị thật.

## Tổng quan

| Slice | Mục tiêu | Trạng thái | Ghi chú |
|-------|----------|-----------|--------|
| E0    | Baseline + status đúng | PASS | code + plan đọc xong; status đính chính (không còn "PENDING_INTEGRATION" cho router) |
| E1    | Collector/worker thu mẫu không chặn | PASS | `app/training/sample_collector.py` + 4 tests + `FEEDBACK_HOOK_CONTRACT.md` |
| E2    | Ảnh thật, bbox, version, export/import bền vững | PASS | export fail nếu thiếu quá nhiều crop; import copy vào asset root với crop_path; ZIP guard đúng (Unix regular OK, symlink block) |
| E3    | Freeze/split/leakage/augment | PASS | tests cũ pass (test_split_by_group_distributes_by_group, test_check_leakage_finds_duplicate_target_text, test_augmentation_no_label_change, test_augmentation_skip_val_test) |
| E4    | Queue/lease/resume/cancel | PASS | queued/waiting không chiếm lease; claim theo running state; transition đúng |
| E5    | Trainer thật EasyOCR inference | PASS (EVALUATOR baseline) | PENDING_DATA/UNSUPPORTED/COMPLETED đúng; IS_EVALUATOR marker |
| E6    | Promotion/rollback gates | PASS | 8 gates + real SHA256 verify + smoke block; rollback restore baseline |
| E7    | Docs + regression | PASS | ACCEPTANCE/EXECUTION/CONTRACTS updated; integration patches cho Task 1/2 |

## Trạng thái theo checklist

- [x] E0 — code đọc xong, status đính chính rõ
- [x] E1 — sample_collector non-blocking, queue đầy có metric, hook Task 1 documented
- [x] E2 — round-trip ảnh thật pass; traversal/symlink/Tạp-chữa OS block; missing_fail export
- [x] E3 — split/leakage/augmentation đạt (tests pass)
- [x] E4 — queued/waiting không chiếm lease; resume OK; cancel idempotent
- [x] E5 — trainer EasyOCR baseline inference; PENDING_DATA khi thiếu; UNSUPPORTED khi thiếu thư viện
- [x] E6 — promotion 8 gate; smoke block; rollback restore baseline
- [x] E7 — docs, contracts, integration patches, full regression

## Dữ liệu nghiệm thu (PENDING_DATA)

- [PENDING_DATA] ≥30 biển rõ — cần runtime + duyệt
- [PENDING_DATA] ≥50 violation/50 clean — cần runtime
- [PENDING_DATA] Nhãn mũ/head/ghép — cần runtime
- [PENDING_DATA] Đánh giá 2 camera thật — cần Task 1

## Phân biệt theo plan

| Hành động | Trạng thái |
|-----------|------------|
| Lưu feedback (qua adapter) | DONE |
| Collector non-blocking + cursor + metrics | DONE |
| Dataset freeze/split/leakage | DONE |
| Trainer OCR thật (EasyOCR inference) | DONE (EVALUATOR baseline) |
| Evaluator holdout (EasyOCR prediction) | DONE |
| Candidate tốt hơn baseline | PENDING_DATA |
| Đã áp dụng candidate | PENDING_RUNTIME (chờ Task 1) |

## Khác biệt so với acceptance cũ

| Acceptance cũ | Closure này |
|---------------|-------------|
| smoke_train dùng label làm prediction (simulation) | `ocr_trainer.py` dùng EasyOCR baseline inference (không simulation); smoke_train cũ vẫn còn nhưng KHÔNG eligible cho promotion |
| promote() bỏ qua checks khi expected_metrics=None | 8 gate bắt buộc |
| Rollback chỉ retire | Restore baseline (state='active' cho retired cũ nhất) |
| ZIP chặn create_system=3 | Chỉ chặn S_IFLNK (mode 0o120000); create_system=3 OK cho regular file |
| Export thành công dù thiếu toàn bộ crop | Export fail_on_missing_crops=True (mặc định); call opt-out fail_on_missing_crops=False |
| queued/waiting chiếm lease | Chỉ preparing/training/evaluating chiếm lease |

## Quyết định kiến trúc đã chốt

- **DB tách biệt**: `data/training.db` riêng Task 3, không đụng `data/app.db`.
- **Adapter pattern**: Task 3 gọi Task 1 API qua `app/training/adapter.py`.
- **Patches**: tích hợp collector + lifespan qua patch docs.
- **1 GPU job**: enforced bằng `active_job_count` chỉ đếm running state.
- **Sample collector**: bounded queue, lazy init, hook Task 1 đặt sau save_feedback.
- **Promote**: 8 gate, state machine `candidate → pending_runtime → applied` (Task 1 set applied).
- **Rollback**: restore retired cũ; nếu không có → DB retired.

## Files Task 3 (closure)

### Mới (closure)
- `app/training/sample_collector.py` — bounded queue + worker + reconcile + cursor + metrics
- `app/training/ocr_trainer.py` — runner EasyOCR thật (PENDING_DATA/UNSUPPORTED/COMPLETED)
- `app/tests/task03_closure/test_closure_e1_e2_e5_e6.py` — 19 tests
- `app/tests/task03_closure/test_closure_e5_trainer.py` — 5 tests
- `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md` — patch Task 1
- `tasks/task-03/integration/APP_LIFESPAN_PATCH.md` — patch Task 2

### Sửa (closure)
- `app/training/import_portable.py` — ZIP guard đúng; copy asset root
- `app/training/export_portable.py` — fail_on_missing_crops; trả dict
- `app/training/promotion.py` — 8 gate + real SHA256 verify + smoke block; state pending_runtime + restore baseline
- `app/training/dataset_repo.py` — active_job_count chỉ running; JOB_STATES thêm pending_data/unsupported
- `app/training/jobs.py` — C02/C03: waiting_resource resume; state reflects runner result
- `app/training/schemas.py` — cho phép None ở camera_id/run_id/crop_sha256/crop_media_id; split=None
- `app/api/training_portable.py` — nhận dict từ export
- `app/tests/task03_helpers/test_dataset_repo.py` — refactor promotion tests cho gate mới + file >= 100 bytes
- `app/tests/task03_helpers/test_task03_api.py` — refactor API promote test + file >= 100 bytes
- `app/tests/task03_closure/test_closure_e5_trainer.py` — file >= 100 bytes + real SHA256

## Test results

- `app/tests/task03_helpers/`: 47/47 pass
- `app/tests/task03_closure/`: 70/70 pass
  - `test_closure_c01_c08.py`: 25/25 (P1 + C01–C08)
  - `test_closure_e1_e2_e5_e6.py`: 19/19
  - `test_closure_e5_trainer.py`: 5/5
  - `test_closure_p2_p3_p4.py`: 21/21 (NEW P2/P3/P4)
- Tổng Task 3: **117/117 pass** trong ~22s

## C01-C08 post-closure fixes

| ID | Issue | Fix |
|----|-------|-----|
| C01 | OCR runner labeled as trainer | `IS_EVALUATOR = True`, `EVALUATOR_LABEL`, clear docstring |
| C02 | waiting_resource jobs not resumable | accepts `queued\|waiting_resource\|preparing`; `claim_and_run_one_waiting_job()` |
| C03 | pending_data/unsupported → completed | state machine: `evaluating → pending_data/unsupported` valid |
| C04a | Cursor ack when copy fails | cursor updated ONLY after copy success; `processed_copy_failed_skipped` metric |
| C04b | Version vs event not cursor | compares `latest_version <= cursor_ver` |
| C05a | Pagination stuck on first 32 | cursor-based scan with review_id ordering; batch_max per pass |
| C05b | Hook created local singleton | hook uses `get_collector()` — returns False when not initialized |
| C06 | Hook used `result["version"]` | v1.1: use `result["expected_version"]`; v1.2 (P1): use `result["feedback_id"]` + `result["new_version"]` (server-authoritative) |
| C07a | `_verify_hash` only checked presence | computes real SHA256; rejects mismatch |
| C07b | Smoke not blocked | `_verify_runtime_contract` + `_verify_not_smoke` blocks smoke class + metrics |
| C08 | UI jobs not connected to worker | `app/training/worker.py` with `TrainingWorker`, `_select_runner` |

## P1-P4 pre-integration fixes

| ID | Issue | Fix |
|----|-------|-----|
| P1 | Hook dùng echo `expected_version` (sai về ngữ nghĩa) | `record_review_feedback` trả `feedback_id` + `new_version` (server-authoritative); hook signature `(review_id, feedback_id, new_version)`; cursor key = `latest_feedback_id`; replay cùng feedback_id không nhân sample |
| P2 | Worker dispatch TypeError khi gọi `(dataset_id, ...)` cho detector/helmet | Runner interface thống nhất `(job, db_path) -> dict`; detector/helmet placeholders trả `unsupported`; adapter OCR ở đúng một chỗ |
| P3 | Promotion gate bỏ qua job state + provenance + OCR quality tuyệt đối | 3 gates mới: `_verify_job_completed` (state=completed + runner_type=train); `_verify_metrics_provenance` (metrics_path link tới job + hash/dataset match); `_verify_counted_test` theo target (OCR ≥50% + ≥30 samples, detector precision ≥0.5, helmet f1 ≥0.5) |
| P4a | Evaluator bị gọi là training completed | `create_job(operation="evaluate_baseline"\|"train")`; `set_job_runner_type` persisted; UI/API phân biệt |
| P4b | `APP_LIFESPAN_PATCH.md` thiếu training_worker | Patch v1.1: start/stop `training_worker` + env flag `TASK3_TRAINING_WORKER_ENABLED`; default bật trong QA, tắt qua env |

## Verdict

**PARTIAL → DONE trên hạ tầng.**

Các phần độc lập (collector, trainer, importer, exporter, promotion gates,
rollback, ZIP guard) đã hoàn thành và **117/117 tests PASS** (92 prior + 25
P1/C01-C08 + 21 P2-P3-P4). Phần runtime (Task 1 hook + Task 2 lifespan start)
đã viết patch docs — chờ Task 1/2 apply. Phần data thật (≥30 biển, ≥50/50
split) là PENDING_DATA — chờ runtime + duyệt.

Tuyên bố "model tự thông minh lên" KHÔNG được đưa ra: candidate cần đo trên
holdout thật (≥30) mới eligible, không dùng simulation, không ghi đè runtime.

## Handoff Task 1 (FEEDBACK_HOOK_CONTRACT v1.2)

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
3. KHÔNG dùng echo `expected_version` (P1) — lấy `feedback_id` + `new_version` server-authoritative.

## Handoff Task 2 (APP_LIFESPAN_PATCH v1.1)

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
5. Khi browser test xuyên luồng:
   - review crop → đúng/sai/sửa chữ → collector lưu asset/label/version → dataset draft
   - export/import qua root khác → freeze/split → job evaluate/train có operation đúng
   - state/metrics/candidate → gate gồn ôm (P3)

## Negative claim — điều KHÔNG làm

- KHÔNG upload cloud (Kaggle/Colab).
- KHÔNG tự train OCR (chỉ EasyOCR baseline inference EVALUATOR).
- KHÔNG tự ghi model runtime (Task 1 mới được apply).
- KHÔNG coi smoke lifecycle simulation là eligible (gate `_SMOKE_MARKER` + `_verify_not_smoke`).
- Không trust client metrics (evaluation server-side bắt buộc).
- KHÔNG dùng `expected_version` echo (P1) — lấy `feedback_id` + `new_version` từ server.
- KHÔNG gọi evaluator là training completed (P4a).
- Cursor chỉ ACK sau khi asset copy thành công.