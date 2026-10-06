# TASK 4 — EXECUTION_LOG (nhật ký điều phối)

> Ngày: 02/10/2026 ~21:45 ICT. Ghi theo thứ tự thời gian.

## T4.0–T4.11 — Previous session (see prior EXECUTION_LOG)

F4.0–F4.6 completed: baseline snapshot, verify Tasks 1/2/3, apply F4.3 patches, full regression 494 tests, video measurement 15 files, closure report.

## T4.12 — CODEX_RECHECK_2026_10_02 analysis

Đọc `tasks/task-04/CODEX_TASK23_RECHECK_2026_10_02.md`. Codex chạy độc lập trước khi F4.3 patches áp. Key findings:

1. **F4.3 patches: Codex nói "chưa tích hợp"** — nhưng đã áp ở T4.9. Xác nhận lại bằng `inspect.getsource`:
   - `on_feedback_recorded` present in post_feedback
   - `start_collector_task` ×2, `start_training_worker` ×2, `stop_training_worker` ×4, `stop_collector_task` ×4 in lifespan

2. **Promotion probes**: 5 probes Codex gọi trực tiếp helpers trên file tạm:
   - ✅ `_verify_counted_test` NaN rejected
   - ✅ `evaluate_baseline` blocks promotion
   - ✅ `metrics missing model_sha256` blocks
   - ✅ `256-byte zero artifact ACCEPTED` → **GAP: artifact loadability not checked**
   - All gates check size ≥ 100 + readable + hash match, but NOT loadability

3. **Training placeholders**: detector/helmet → `unsupported` (docstring "chưa triển khai"). OCR → baseline evaluator. Đây là design chủ đích.

4. **Browser integration**: `vite.qa.config.js` proxy đúng; `test_browser_integration.spec.js` tests 4 roles, teacher scope, deep links, backup API. Guard endpoints stubbed.

## T4.13 — Create F4.x integration tests

### T4.13.1 — `test_recognition_feedback_hook.py`

7 tests verifying F4.3 feedback hook contract:
- `test_hook_called_with_correct_params` — patches `app.training.sample_collector.on_feedback_recorded` (NOT module-level import in endpoint)
- `test_hook_not_called_on_conflict` — 409 → no call
- `test_hook_not_called_on_idempotent_replay` — replay → no call
- `test_hook_exception_does_not_break_endpoint` — RuntimeError → 200
- `test_feedback_id_and_new_version_are_server_authoritative` — response has correct fields
- `test_multiple_feedback_increments_version` — v1→2
- `test_hook_not_called_when_collector_disabled` — endpoint doesn't depend on result

**Bug found**: patch target phải là `app.training.sample_collector.on_feedback_recorded` vì endpoint dùng local import.

**Bug found**: `_post_feedback` helper nhận `corrected_text` qua positional args, sửa thành optional keyword arg.

### T4.13.2 — `test_main_lifespan.py`

11 tests verifying lifespan integration:
- Start/stop idempotent, threads alive, env flags, order
- `test_stop_collector_with_timeout`: `SampleCollector` dùng `_started: threading.Event`, KHÔNG `_running`

### T4.13.3 — `test_promotion_artifact_gap.py`

4 tests documenting artifact validation gap:
- `test_256_byte_zero_passes_all_promotion_gates` — proves 256-byte artifact (fake) passes ALL gates → state=pending_runtime. **This is the gap**.
- `test_real_ocr_model_is_large` — .pt files > 1MB (passes)
- `test_real_easyocr_model_is_large` — SKIPPED (easyocr dir not present)
- `test_size_gate_detects_extreme_fake` — < 100 bytes rejected

**Bug found**: `create_candidate` nhận `config: dict`, test truyền `json.dumps(...)` → double-encoded. Fix: truyền dict.

**Bug found**: Windows `.db` file lock khi dùng `tempfile.TemporaryDirectory()`. Fix: persistent temp dir + explicit cleanup + `ignore_errors=True`.

## T4.14 — First test run: 9 failed

```
AttributeError: patch target wrong → 5 fails
TypeError: corrected_text unexpected keyword → 1 fail
AttributeError: _running not found → 2 fails
PermissionError: Windows file lock → 1 fail
```

## T4.15 — Fix all failures

- Patch target: `app.training.sample_collector.on_feedback_recorded` (5 occurrences)
- `_post_feedback` helper: `corrected_text` optional keyword
- `SampleCollector`: dùng `_started.is_set()` thay `_running`
- `create_candidate`: truyền `config=dict` (not json.dumps)
- Temp dir: persistent with `shutil.rmtree(ignore_errors=True)` + explicit connection close

## T4.16 — Second test run: 21/22 PASS (1 SKIP)

```
================== 21 passed, 1 skipped, 1 warning in 9.58s ==================
```

All F4.x integration tests green.

## T4.17 — Full regression

**Task 3 + Task 1 combined** (277 tests):
```
================== 277 passed, 1 warning in 64.12s ==================
```

**Task 2** (115 tests):
```
======================= 115 passed, 1 warning in 37.78s ========================
```

**Recognition + F4.x** (56 tests):
```
================== 56 passed, 1 skipped, 1 warning in 21.69s ==================
```

**TOTAL**: 461 tests — 460 PASS, 1 SKIP, 0 FAIL.

## T4.18 — Update context files

- STATUS_BOARD.md: updated with F4.x results + artifact gap classification
- INTEGRATION_LEDGER.md: updated with evidence + regression results
- EXECUTION_LOG.md: this file updated
- ACCEPTANCE_REPORT.md: updated
- NEXT_ACTIONS.md: updated

## T4.19 — Remaining items (Task 1/2/3 owners)

- Task 1: `apply_pending.py`/`rollback.py` (C5 GPU contract)
- Task 2: Expand browser media tests (real images, Range 206)
- Task 3: `_verify_artifact_loadable()` (low priority)