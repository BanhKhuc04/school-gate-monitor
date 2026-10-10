# TASK 4 — ACCEPTANCE REPORT

**Ngày**: 2026-10-02

## Tổng kết nghiệm thu

| Mục | Status | Bằng chứng |
|-----|--------|------------|
| R1 Preview độc lập AI | ✅ CODE_COMPLETE | T1 report + 6 tests |
| R2 Lifespan exception cleanup | ✅ CODE_COMPLETE | 10/10 tests |
| R3 Apply runtime + rollback | ✅ CODE_COMPLETE | T1: 5+5 tests |
| R3 Validation gates | ✅ CODE_COMPLETE | T3: 10 NaN + 6 loadable + provenance |
| R4 Media Range 206 | ✅ CODE_COMPLETE | 2/2 tests |
| R4 Production deep link | ✅ CODE_COMPLETE | 8/8 tests |
| R4 Backup restore assets | ✅ CODE_COMPLETE | T2: 6/6 tests |
| R4 E2E browser thật | ✅ CODE_COMPLETE | T2: 8/8 Chrome DevTools |
| R5 Feedback → dataset hook | ✅ CODE_COMPLETE | T3: 7/7 tests |
| R5 Training runner | ⚠️ CODE_PARTIAL | T3 runner.py — `state=unsupported` cho detector/helmet |
| R6 Backend full regression | ⚠️ CODE_PARTIAL | 1162/1173 PASS (8 fail + 3 err do T1 preview-thread refactor) |
| R6 Video full timeline EOF | ⏳ PENDING_HARDWARE | `C:/Users/khucv/Downloads/tranning/` rỗng — không có MP4 |
| R6 Dual-source 30-min | ⏳ PENDING_HARDWARE | Cần 2 camera + 30 phút |
| R6 Imou/LAN/12-hour | ⏳ PENDING_HARDWARE | Cần thiết bị Imou |

## Chi tiết CODE_COMPLETE

### R1 — Preview độc lập AI (F02)
- Pipeline tách encode JPEG ra `_preview_loop` daemon thread, queue maxsize=2.
- Main loop push frame không chờ → AI block 10s vẫn publish mỗi 100-200ms.
- `tasks/task-01/POST_VIDEO_REPAIR_TODO.md` updated với REOPEN closure.

### R2 — Lifespan exception cleanup (F4.3)
- `try/finally` bao toàn bộ lifespan.
- 4 `_stop_X = lambda: None` khởi tạo trước try.
- Cleanup unconditional trong finally, stop order: pipelines → training → collector → maintenance.

### R3 — Apply runtime + rollback
- `reload_model_from_candidate(candidate_id)` — hot-swap detector.
- `rollback_to_baseline(engine)` — restore baseline model.
- Validation gates: artifact existence, SHA256, NaN/Infinity, loadability, provenance, runtime class mapping.

### R4 — Browser/media thật
- Media endpoint trả 206 cho Range request đúng RFC 7233.
- Chrome DevTools MCP drives login admin/teacher thật, promote UI, deep link SPA fallback.
- Backup restore với SHA256 round-trip cho snapshot+crop+clip.

## Chi tiết CODE_PARTIAL

### R5 — Training loop (detector/helmet)
- Runner contract: `app/training/runner.py` định nghĩa unified `(job, db_path) -> dict`.
- OCR runner: CODE_COMPLETE (EasyOCR thật).
- Detector runner: returns `state='unsupported'` thay vì raise.
- Helmet runner: returns `state='unsupported'` thay vì raise.
- **Lý do**: thiếu YOLO weights thật + GPU fixture + label helmet dataset.

## Chi tiết PENDING_HARDWARE

| Item | Cần | Đã có | Gap |
|------|-----|-------|-----|
| Video full timeline EOF | 15 MP4 từ `tranning/` | 0 | Cần upload MP4 |
| Dual-source 30-min | 2 camera + 30 phút | 0 | Cần camera |
| 1/2/3 viewer | 1-3 browser session | 0 | Cần test instance |
| Imou reconnect | Camera Imou | 0 | Cần thiết bị |
| LAN test | LAN network | 0 | Cần thiết bị |
| 12-hour test | 12 giờ chạy | 0 | Cần thời gian |

## Regression Results (Sau T4 Fixes)

### Initial (trước fix)
```
1173 collected
1162 PASSED, 8 FAILED, 3 ERRORS
Exit code: 1
Elapsed: 850.74s (0:14:10)
```

### After T4 fixes (verified 34/34 pass)
```powershell
.\venv\Scripts\python.exe -m pytest `
  app/tests/test_camera_offline_no_violations.py `
  app/tests/test_pipeline_loop_output.py `
  app/tests/test_dot_R.py `
  app/tests/test_runtime_apply_pending_candidate.py `
  app/tests/test_camera_pipeline.py `
  --tb=short -q --basetemp=C:/pytest_iso8
```

**Result: 34 passed, 1 warning in 11.19s** ✅

### Full suite final run
**BLOCKED**: D: drive hết disk space (0-414MB còn lại sau pycache cleanup). EasyOCR load VGG weights ~100MB/test → peak ~3GB cho full suite. Cần:
- Dọn user files lớn khỏi D: HOẶC
- Chạy batch nhỏ HOẶC
- Tạm skip `test_ocr_init.py` (heavy model loading)

## File output trong scope TASK 4

| File | Mô tả |
|------|-------|
| `STATUS_BOARD.md` | Tóm tắt tiến độ + R1-R6 status |
| `INTEGRATION_LEDGER.md` | File đã sửa + tests |
| `ACCEPTANCE_REPORT.md` | Báo cáo nghiệm thu |
| `NEXT_ACTIONS.md` | Hành động tiếp theo + PENDING_HARDWARE |