# R3.4b fix — `SNAPSHOTS_DIR` env-aware (CRITICAL)

## Vấn đề

`app/config.py::SNAPSHOTS_DIR` hard-code `BASE_DIR / "data" / "snapshots"` (production).

QA launcher set env `SNAPSHOTS_DIR=tasks/task-02/qa/snapshots` qua `_qa_env_dict()` nhưng
không có tác dụng vì config không đọc env.

Hệ quả: khi QA backend (port 8002) xử lý `POST /api/system/backup/run` hoặc
`MaintenanceWorker._backup_job()`, `create_backup_set(snapshots_dir=SNAPSHOTS_DIR, ...)`
copy mọi file trong `data/snapshots` (production — 37.548 files × ~80KB ≈ 3GB) vào bộ backup
của QA. Mỗi browser integration test gọi endpoint này → tạo bộ backup ~4GB chứa toàn bộ
media vận hành.

3 lần browser integration test + 1 pytest-full background = 12.6GB + 16.8GB = 29.4GB
phình ra trên disk D: (188GB tổng) → **disk đầy 100% (SizeRemaining=0)**.

Disk full lan sang:
- `sqlite3.OperationalError: database or disk is full` cho mọi pytest sau đó
- Vite dev server không ghi được temp config → `ENOSPC: no space left on device`
  → "vite 5186 fail to start"

## Fix (1 dòng trong `app/config.py`)

```python
# Trước (hard-code):
SNAPSHOTS_DIR = str(BASE_DIR / "data" / "snapshots")

# Sau (env-aware):
SNAPSHOTS_DIR = os.environ.get("SNAPSHOTS_DIR") or str(BASE_DIR / "data" / "snapshots")
```

Theo R3 contract đã có — qa_launcher set env đúng, chỉ thiếu đọc env.

## Verify

```powershell
# Trước fix:
.\venv\Scripts\python.exe -c "import os; os.environ['SNAPSHOTS_DIR']='tasks/task-02/qa/snapshots'; os.environ['APP_DB_PATH']='tasks/task-02/qa/qa.db'; import app.config; print(app.config.SNAPSHOTS_DIR)"
# → D:\Work\Project_motorbike\data\snapshots (SAI)

# Sau fix:
# → D:\Work\Project_motorbike\tasks\task-02\qa\snapshots (ĐÚNG)
```

## Hiệu quả thực đo

| Metric | Trước R3.4b | Sau R3.4b |
|--------|-------------|-----------|
| `media_count` trong QA backup set | 9625 file (~3GB) | 0 |
| `db_size_mb` trong QA backup set | 0.16 MB | 0.16 MB |
| Backup test runtime | 150s (2.5 phút) | 0.94s |
| Disk D: free space | 0 / 188 GB | 39 / 188 GB (sau cleanup) |

## Tác động lên các test khác

- `app/tests/test_task02_t2_8_backup.py` — 14 PASSED (KHÔNG thay đổi, đã đúng)
- `app/tests/test_backup.py` — 7/9 PASSED (1 fail `test_backup_run_admin_ok` trong
  session trước do disk-full mid-run; sau fix 9/9 PASSED in fresh process)
- `app/tests/test_maintenance_worker.py` — 12/12 PASSED (KHÔNG thay đổi)
- `frontend/e2e/test_browser_integration.spec.js::backup/run` — PASSED in 0.94s
  (so với 150s trước fix — 160× faster)