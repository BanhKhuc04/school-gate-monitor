# INTEGRATION LEDGER — 2026-10-02 (Updated)

## Files Modified This Session

| File | Change | Owner | Reason |
|------|--------|-------|--------|
| `app/main.py` | Refactored `lifespan()` with try/finally, unconditional cleanup | T4 | R2: Fix exception handling |
| `app/tests/test_main_lifespan_r2.py` | New: 10 tests for R2 | T4 | Verify R2 fix |
| `app/cv/pipeline.py` | Preview thread + queue maxsize=2; `_publish_frame_jpeg` async | T1 | R1: preview decoupled from AI |
| `app/cv/pipeline.py` | `reload_model_from_candidate()`, `rollback_to_baseline()` | T1 | R3: hot-reload + rollback |
| `app/tests/test_task01_r1_preview_decoupled.py` | Updated for new architecture | T1 | Verify R1 fix |
| `app/tests/test_runtime_apply_pending_candidate.py` | New: 5 tests for hot-reload | T1 | R3: apply pending |
| `app/tests/test_runtime_rollback.py` | New: 5 tests for rollback | T1 | R3: rollback |
| `app/tests/test_task01_F01_F02_runtime.py` | Updated for new R1 architecture | T1 | Adapt existing tests |
| `app/training/promotion.py` | NaN gate, loadability with torch timeout, provenance snapshot+split_hash | T3 | R3: stricter gates |
| `app/training/runner.py` | New: unified runner contract `(job, db_path) -> dict` | T3 | R5: dispatcher |
| `app/training/worker.py` | Delegate to runner.py via `_select_runner()` | T3 | R5: worker cleanup |
| `app/training/dataset_repo.py` | `set_job_split_hash()` + schema column `split_hash` | T3 | R3: provenance |
| `app/training/provenance.py` | `compute_split_hash()`, `compute_dataset_snapshot()` | T3 | R3: provenance |
| `app/tests/test_promotion_nan_gate.py` | New: 10 tests for NaN/Infinity/string/bool rejection | T3 | R3: NaN gate |
| `app/tests/test_promotion_artifact_loadable.py` | New: 6 tests for torch.load verification | T3 | R3: loadability |
| `app/tests/test_feedback_to_dataset.py` | New: 7 tests for hook→collector | T3 | R5: feedback hook |
| `app/tests/test_closure_p5.py` | New: 11 tests for provenance + runner + R5 loop | T3 | R3+R5 closure |
| `app/tests/test_promotion_artifact_gap.py` | Updated: 256-byte zero file REJECTED | T3 | F4.5 gap closed |
| `app/tests/test_media_restore_with_assets.py` | New: 6 tests for backup with SHA256 round-trip | T2 | R4: media restore |
| `frontend/e2e/test_browser_e2e_real.spec.js` | New: 8 tests + 1 skip for Chrome DevTools MCP drives | T2 | R4: E2E real |
| `tasks/task-02/REOPEN_AUTH_AUDIT.md` | New: audit no scope creep | T2 | R4 audit |
| `tasks/task-02/REOPEN_CLOSURE.md` | New: closure document | T2 | R4 closure |
| `tasks/task-01/POST_VIDEO_REPAIR_TODO.md` | Updated với REOPEN closure | T1 | R1 closure doc |
| `tasks/task-01/ACCEPTANCE_REPORT.md` | Updated với REOPEN closure | T1 | R1 closure doc |
| `tasks/task-02/ACCEPTANCE_REPORT.md` | Updated REOPEN row | T2 | R2 closure doc |
| `tasks/task-02/EXECUTION_LOG.md` | Updated REOPEN section | T2 | R2 execution log |
| `tasks/task-04/STATUS_BOARD.md` | New: T4 status board | T4 | Integration tracking |
| `tasks/task-04/INTEGRATION_LEDGER.md` | New: T4 ledger | T4 | Integration tracking |
| `tasks/task-04/ACCEPTANCE_REPORT.md` | New: T4 acceptance report | T4 | Integration closure |
| `tasks/task-04/NEXT_ACTIONS.md` | New: T4 next actions | T4 | Pending items |

## Key Findings

### R1: Preview Decoupling (F02)
- **T1 fix**: Preview thread riêng (`_preview_frame_queue` maxsize=2 + daemon `_preview_loop()`).
- Main loop push không chờ → AI block 10s vẫn publish mỗi 100-200ms.
- Queue drop oldest nếu full → không block main loop.
- **Regression**: 7 tests cũ fail vì expected synchronous JPEG cache (fix in NEXT_ACTIONS).

### R2: Lifespan Exception Cleanup (F4.3)
- **T4 fix**: All `_stop_X = lambda: None` initialized before try.
- `try/finally` unconditional cleanup.
- Each component isolated try/except — one failure doesn't block others.
- 10/10 tests PASS in `test_main_lifespan_r2.py`.

### R3: Runtime Apply + Validation
- **T1 fix**: `reload_model_from_candidate()` + `rollback_to_baseline()`.
- **T3 fix**: NaN/Infinity gate, loadability with torch timeout 5s, snapshot+split_hash provenance.
- 256-byte zero file REJECTED (F4.5 gap closed).

### R4: Browser/Media Production
- **T2 fix**: Chrome DevTools MCP drives for real E2E.
- Media restore with SHA256 round-trip verified.
- 8/8 E2E spec + 6/6 restore tests PASS.

## Test Results Summary

| Suite | Tests | Passed | Failed |
|-------|-------|--------|--------|
| `test_main_lifespan.py` | 11 | 11 | 0 |
| `test_main_lifespan_r2.py` | 10 | 10 | 0 |
| `test_recognition_feedback_hook.py` | 7 | 7 | 0 |
| `test_promotion_artifact_gap.py` | 4 | 3 | 0 (1 skipped) |
| `test_task01_F01_F02_runtime.py` | 9 | 9 | 0 |
| `test_task01_r1_preview_decoupled.py` | 6 | 6 | 0 |
| `test_runtime_apply_pending_candidate.py` | 5 | 3 | 2 (shared state) |
| `test_runtime_rollback.py` | 5 | 5 | 0 |
| `test_promotion_nan_gate.py` | 10 | 10 | 0 |
| `test_promotion_artifact_loadable.py` | 6 | 6 | 0 |
| `test_feedback_to_dataset.py` | 7 | 7 | 0 |
| `test_closure_p5.py` | 11 | 11 | 0 |
| `test_media_restore_with_assets.py` | 6 | 6 | 0 |
| `test_task02_t2_2_media.py` | 15 | 15 | 0 |
| **Full regression** | **1173** | **1162** | **8 fail + 3 err** |

## Regression Output

```
Số test: 1173
PASSED: 1162
FAILED: 8
ERROR: 3
SKIPPED: 0
Exit code: 1
Elapsed: 850.74s (0:14:10)
```

## Blocker Items

1. **T1 Fix 8 Test Failures**: Tests cũ cần update cho async JPEG queue.
2. **PENDING_VIDEO_FILES**: `C:/Users/khucv/Downloads/tranning/` rỗng.
3. **PENDING_DUAL_SOURCE_30MIN**: Cần 2 camera thật.
4. **PENDING_DETECTOR_HELMET_RUNNER**: Cần YOLO weights + helmet labels.
5. **PENDING_IMOU_LAN_12HOUR**: Cần thiết bị Imou.