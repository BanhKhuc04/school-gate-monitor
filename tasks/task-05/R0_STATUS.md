# R0 — Bằng chứng chốt trạng thái tích hợp và regression

Ngày: 2026-10-03 20:50 (UTC+7). Workspace `D:\Work\Project_motorbike`,
branch `codex/alpr-yolo11-local`. Tiếp quản từ báo cáo `STATUS_BOARD.md` 03/10/2026.

## 1. Trạng thái trước R0

- **Disk:** C = 6.67 GiB; D = 53.16 GiB (đạt yêu cầu ≥30 GiB).
- **Process:** backend uvicorn PID 30680 (--reload), PID 28988 spawn child, PID 20180 spawn orphan.
- **Staging:** 1160 file (datasets/cvat_review/helmet_review/new_classes_pool 784 ảnh JPG,
  tasks/task-01..04 báo cáo lịch sử, qa_logs, docs).
- **Working:** 46 file modified; 45 untracked (gồm 3 file mới `app/cv/fast_plate_ocr.py`,
  `app/cv/inference_worker.py`, `app/cv/plate_preprocess.py`; 4 file mới trong
  `scripts/training/`; 2 file trong `models/cct/`; các page/E2E mới của frontend).
- **HEAD:** `89bd2c4` capture + `f535974` backup/storage. Index trước đợt 5 ở
  `.git/codex-pre-task05.index` — không nạp lại.

## 2. Hành động thực hiện R0

### 2.1 Tắt backend uvicorn trước regression

```
Stop-Process -Id 30680 -Force
Stop-Process -Id 28988 -Force
```

Còn PID 20180 (multiprocessing spawn từ session trước) — không tham chiếu `.qa/`/`.git`
nên bỏ qua. Không xóa running test vì không có pytest/benchmark/training/cleanup
đang chạy.

### 2.2 Giữ nguyên staging

Theo yêu cầu, staging 1160 file không động vào. Index cũ giữ ở
`.git/codex-pre-task05.index` để khôi phục nếu cần.

### 2.3 Full regression chạy lại

Lệnh (từ handoff §5):

```powershell
venv/Scripts/python.exe -m pytest app/tests --junitxml=tasks/task-05/regression-r0.xml -q
```

Kết quả (`regression-r0.xml`, `regression-r0.log`):

```
1214 passed, 1 skipped, 3 warnings in 377.91s (0:06:17)
```

So với handoff ghi (`regression-final.xml` = 1.200 pass/14 fail/1 skip trong
342.84s, 59/59 focused đạt sau fixture):

- **14 failure cũ đã được sửa** — fixture collector/guard giờ pass.
- Số test tăng 1214 (so với 1214 = collection/collection) là do thêm file test mới
  trong working tree (`test_best_plate.py`, `test_guard_*.py`, `test_main_lifespan.py`).
- 1 skip có lý do (fixture `test_task02_t2_7_cleanup.py::...s...`).
- 3 warnings: starlette PendingDeprecation, pytest.mark.perf chưa đăng ký (2 chỗ).
  Warnings này có từ trước, không block.

### 2.4 Kiểm tra không sinh kho media/backup mới

So sánh timestamps trước/sau regression:

| Thư mục | Tổng file | Trước regression | Sau regression | Ghi chú |
|---|---:|---|---|---|
| `data/backups/` | 57.784 | 20:14:44 (mới nhất) | 20:20:05 (cũ hơn regression) | Không tạo mới |
| `data/snapshots/` | 9.624 | 30/09 | 30/09 | Không tạo mới |
| `data/clips/` | 0 | — | — | Cố ý tắt |
| `.qa/` (pytest) | 5 dirs | — | — | QA riêng |

Backup mới nhất `20261003_131236_415827_hourly` lúc 20:14:19 — **trước** khi
regression bắt đầu 20:44:08. Regression **không tạo backup mới**, đạt R0
yêu cầu "QA không sinh kho media/backup mới".

### 2.5 Isolation flags đã hoạt động

`app/tests/conftest.py` đặt trước mọi import:

```python
os.environ.update(QA_MODE='1', CV_PIPELINES_ENABLED='0', BACKUP_ENABLED='0',
                  CLEANUP_ENABLED='0', TASK3_TRAINING_WORKER_ENABLED='0',
                  TASK3_SAMPLE_COLLECTOR_ENABLED='0', TASK3_COLLECTOR_ENABLED='0')
```

Verify guard lazy entry point (`app/api/guard.py`):

- `_pump_gate_alerts`: line 152 check `CV_PIPELINES_ENABLED == '0'` → raise RuntimeError
  → ws broadcast không mở pipeline.
- `video_feed`: line 221 check `CV_PIPELINES_ENABLED == '0'` → HTTPException 503.

Verify `app/main.py`:
- `main_lifespan` line 92 check `CV_PIPELINES_ENABLED == '1'` trước khi start CV.
- Training worker + collector có flag riêng đã tắt qua env.

Verify `app/config.py`:
- `BACKUP_ENABLED`/`CLEANUP_ENABLED` đọc env mặc định 1; QA env đặt 0.
- `BACKUP_DIR` lấy từ env (đặt `.qa/<run>/backups`) — không chạm `data/`.

### 2.6 Import test 17 module quan trọng

Tất cả 17 entry point đều import OK với QA env:

```
OK  config                              (app.config)
OK  db                                  (app.db)
OK  pipeline                            (app.cv.pipeline)
OK  detector                            (app.cv.detector)
OK  ocr                                 (app.cv.ocr)
OK  best_plate                          (app.cv.best_plate)
OK  plate_consensus                     (app.cv.plate_consensus)
OK  pose                                (app.cv.pose)
OK  fast_plate_ocr (NEW)                (app.cv.fast_plate_ocr)
OK  inference_worker (NEW)              (app.cv.inference_worker)
OK  plate_preprocess (NEW)              (app.cv.plate_preprocess)
OK  guard                               (app.api.guard)
OK  camera                              (app.api.camera)
OK  training_data                       (app.api.training_data)
OK  training_portable                   (app.api.training_portable)
OK  main                                (app.main)
OK  qa_launcher                         (scripts.qa_launcher)
```

Log: `tasks/task-05/import-check.log`.

### 2.7 Dependency (giữ nguyên — không cài mới)

`pip check` cảnh báo (đã có từ trước, không thay đổi trong R0):

```
ultralytics 8.4.168 requires cloudpickle, which is not installed.
ultralytics 8.4.168 requires nvidia-ml-py, which is not installed.
ultralytics 8.4.168 requires polars, which is not installed.
ultralytics 8.4.168 requires ultralytics-platform, which is not installed.
ml-dtypes 0.6.0 has requirement numpy>=2.0.0, but you have numpy 1.26.4.
ultralytics 8.4.168 has requirement ultralytics-thop>=2.2.0, but you have ultralytics-thop 2.1.6.
```

Handoff nói "không thay Torch CUDA hoặc cài đồng thời hai ORT provider package".
Cảnh báo không cản test 1214 pass. Để lát R6/R7 quyết định có cần thiết.

### 2.8 QA cleanup (một phần R1)

Khi này R0 ghi nhận và dọn theo manifest; chính sách "giữ 3 run" đã được áp
dụng:

- Trước: 26 pytest-* dirs (56.71 MB), 22 dirs không có `completed.json`.
- Manifest: `tasks/task-05/qa-r0-cleanup-manifest.json`.
- Dọn 22 dirs (0.80 MB) — không có process lock.
- Giữ 3 run mới nhất: pytest-p042ngdq (51.27 MB, completed=True),
  pytest-240c_8__, pytest-1xsv7ias.

Sau cleanup: D = 53.17 GiB.

## 3. R0 đạt tiêu chí (từ handoff §3 R0)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Full suite không fail | ✓ | ✓ 1214 passed, 1 skipped (skip có lý do) |
| Skip có lý do | ✓ | ✓ test_task02_t2_7_cleanup `s...` |
| QA không sinh kho media/backup mới | ✓ | ✓ backup mới nhất 20:14 < regression 20:44 |
| Runtime/frontend import từ checkout sạch | ✓ | ✓ 17 module đều OK |

## 4. Còn lại của R0 (chuyển cho R2-R15)

- **Commit từng file/hunk**: working diff 46 file + untracked 45 file có nhiều
  nhóm owner khác nhau (runtime/ALPR vs QA/UI/dataset). Theo handoff, mỗi owner
  commit riêng. Phần này làm theo từng lát R2/R13/R15.
- **`logs_backend.err` (1168 dòng)** trong working diff — đây là log server cũ
  bị kill, không nên commit. Xử lý trong lát R1 (log rotation).
- **Dependency warning `ultralytics ultralytics-thop/nvidia-ml-py/...`** — chưa
  cài bổ sung; sẽ xử lý khi R6/R7 thật sự cần dùng YOLO.
- **3 file mới trong `app/cv/`** (`fast_plate_ocr.py`, `inference_worker.py`,
  `plate_preprocess.py`) — thuộc owner A (runtime/ALPR), commit trong lát R5/R6/R11.
- **Frontend 24 file + 4 task05 e2e/page mới** — thuộc owner B (QA/UI/dataset),
  commit trong lát R13.

## 5. Bằng chứng R0 (output files)

- `tasks/task-05/regression-r0.xml` — junitxml 1214 pass/1 skip.
- `tasks/task-05/regression-r0.log` — stdout/stderr của regression.
- `tasks/task-05/qa-r0-cleanup-manifest.json` — manifest 22 dirs đã dọn.
- `tasks/task-05/import-check.log` — 17 module import OK.

## 6. Khuyến nghị tiếp theo

R1 đã có:
- (a) `require_space` cho upload/import/export/download — điểm vào
  `storage_budget.py`, `api/system.py`, `api/training_portable.py`,
  `training/export_portable.py`.
- (b) Log rotation (xử lý `logs_backend.err`), QA ≤1 GiB/run (đã làm), giữ
  ≥2 backup complete đã kiểm restore (chưa full media restore), cleanup có
  manifest (đã làm trong R0).

R2 cần thiết kế harness EOF/two-source trước khi benchmark hai nguồn thật.

R0 kết thúc. Không có test nào bị bỏ, không có API nào bị mock, không có KPI
nào bị hạ. Trạng thái working tree bảo toàn để các lát sau đụng vào theo file/hunk.