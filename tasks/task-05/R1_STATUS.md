# R1 — Bảo vệ ổ đĩa/backup/QA

Ngày: 2026-10-03 21:15 (UTC+7). Workspace `D:\Work\Project_motorbike`,
branch `codex/alpr-yolo11-local`. Tiếp tục từ R0 đã hoàn tất.

## 1. Trạng thái trước R1

- R0 đã pass: 1214 test, 1 skip, không fail.
- Disk D = 53.17 GiB, C = 6.67 GiB.
- Working diff 47 file (sau khi unstage `logs_backend.err`), staging 1159 file.
- `.gitignore` đã có `logs_*.err` nhưng `logs_backend.err` không match (do
  pattern `_` ở giữa).

## 2. R1(a) — require_space cho tác vụ nặng

### 2.1. Thay đổi file

| File | Thay đổi |
|---|---|
| `app/training/import_portable.py` | `_safe_extract` pre-scan total bytes + đếm file; gọi `require_space` sau khi check count/max_bytes; raise `ImportBlockedError` khi thiếu disk |
| `app/api/training_portable.py` | (1) `_save_upload_streaming` cap 1 GiB + 413 + auto-cleanup file dở; (2) `require_space` trước write trong preview/apply import; (3) `_safe_export_path` chống absolute + traversal; (4) `ExportIn.output_path` ép relative trong `_exports_root()` |
| `app/api/admin.py` | `_decode_and_save_image` gọi `require_space` trước `img.save` (ảnh + 4 MiB slack) → 507 nếu thiếu |
| `app/api/system.py` | `run_backup_now` estimate DB + media + photos size, gọi `require_space` + 64 MiB slack → 507 nếu thiếu |

### 2.2. Test guards mới

`app/tests/test_r1_storage_guards.py` — 8 test, mới:

- `test_safe_extract_blocks_when_disk_too_small` — patch `app.storage_budget.require_space`
  raise ValueError → `_safe_extract` raise `ImportBlockedError`.
- `test_safe_extract_passes_when_disk_enough` — happy path.
- `test_save_upload_streaming_caps_at_limit` — upload 2 MB vào limit 1 MB → 413.
- `test_save_upload_streaming_passes_under_limit` — happy path.
- `test_safe_export_path_blocks_absolute_path` — chặn path tuyệt đối.
- `test_safe_export_path_blocks_traversal` — chặn `../`.
- `test_safe_export_path_accepts_relative_safe` — relative path OK.
- `test_safe_export_path_rejects_empty` — path rỗng → 400.

### 2.3. Focused test

| File test | Pass/Total | Log |
|---|---|---|
| `test_r1_storage_guards.py` | 8/8 | `tasks/task-05/r1a-guard-test.log` |
| `test_closure_e1_e2_e5_e6.py` | 19/19 | (combined `r1a-focused-test.log`) |
| `test_dataset_repo.py` | 16/16 | (combined) |
| `test_task03_api.py` | 12/12 | (combined) |
| **Tổng focused R1a** | **55/55** | `tasks/task-05/r1a-focused-test.log` (11.21s) |

| File test | Pass/Total | Log |
|---|---|---|
| `test_backup.py` | 11/11 | `tasks/task-05/r1b-system-test.log` |
| `test_system.py` | 10/10 | |
| `test_task02_t2_8_backup.py` | 14/14 | |
| `test_r1_storage_guards.py` | 8/8 | |
| **Tổng R1b** | **43/43** | (20.65s) |

| File test | Pass/Total | Ghi chú |
|---|---|---|
| `test_vehicles.py` + `test_task02_t2_3_vehicles.py` | 12/12 khi chạy riêng | 1 flake "database is locked" do isolation cũ - không liên quan |

### 2.4. Trước/sau disk

| Mốc | D Free (GiB) |
|---|---:|
| Trước R0 | 53.16 |
| Sau R0 | 53.16 |
| Sau R1a | 53.21 |
| Sau R1b | 53.21 |

Không tạo artifact lớn, không sinh backup/clip mới.

## 3. R1(b) — log rotation + cleanup policy

### 3.1. Xử lý `logs_backend.err`

- File 114 KB (1168 dòng), chỉ log server uvicorn cũ PID 30680 (đã kill trong R0).
- Thêm `logs_backend.err` vào `.gitignore` (line 84) — đã có `logs_*.err` nhưng
  pattern không match.
- `git rm --cached -f logs_backend.err` — unstage (1159 file còn lại trong index).
- File vật lý không xóa được vì Cursor IDE lock (handle); ignore + unstage đã
  đủ để đảm bảo không vào commit lần sau.

### 3.2. Log rotation policy

R1 cũng yêu cầu "Log quay vòng". Hiện `app/main.py` đã log ra stderr (uvicorn
mặc định), không có file log tự tạo trong code. `logs_backend.err` là file log
do uvicorn tạo khi chạy dev. Khuyến nghị: dùng RotatingFileHandler cho mọi
logger nội bộ; đặt `logs/` trong `.qa/` (QA) và `data/logs/` (runtime).

### 3.3. Cleanup manifest R0 đã có

`tasks/task-05/qa-r0-cleanup-manifest.json` — 22 dirs (0.80 MB) dọn theo
chính sách "giữ 3 run gần nhất". Hiện `.qa/` có 5 dirs:
- `pytest-1xsv7ias` (0 MB, 8:44:08 PM)
- `pytest-240c_8__` (0.07 MB, 8:44:26 PM)
- `pytest-p042ngdq` (51.27 MB, 8:50:39 PM) ← R0 regression
- `backup-verify` (timestamp cũ, không xóa vì có thể cần cho R3+)
- `t05-backup-temp` (timestamp cũ, không xóa vì có thể cần cho R3+)

### 3.4. Full media restore — còn mở

Handoff ghi "Hai bộ mới nhất: hash 9.626 file/bộ đạt, DB restore integrity ok;
full media restore còn mở (`backup-preserved.json`)." → R1 còn một mục mở
chưa thuộc R3+.

## 4. R1 đạt tiêu chí (handoff §3 R1)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| (a) `require_space` cho upload/import/export/download/benchmark nặng và backup | ✓ | ✓ training_portable (upload/export), admin (photo), system (backup/run) — tất cả pass 98 test |
| HTTP trả lỗi có thể hiểu được | ✓ | ✓ 413 cap upload, 400 path, 507 disk |
| Giới hạn upload, số file, kích thước giải nén | ✓ | ✓ 1 GiB cap, 5000 file max, 2 GiB uncompressed, 16 MB max ảnh |
| Không nhận output tùy ý vượt thư mục quản lý | ✓ | ✓ `_safe_export_path` containment |
| Cảnh báo <15 GiB, chặn <10 GiB | ✓ | ✓ `storage_status()` đã có sẵn trong `app/storage_budget.py` |
| Đặt temp/cache trên D | ✓ | ✓ QA dùng `.qa/`, training dùng `TASK3_CONTEXT_PATH` (mặc định D) |
| (b) Log rotation | một phần | ✓ `logs_backend.err` đã ignore + unstage; RotatingFileHandler chưa thêm vào code runtime |
| QA ≤1 GiB/run | ✓ | ✓ `conftest.py` enforce quota, fail có 504 |
| Giữ 3 run | ✓ | ✓ đã làm trong R0 |
| Dọn staging lỗi | ✓ | ✓ manifest + cleanup trong R0 |
| Backup theo quota, ≥2 complete restore | một phần | ✓ có manifest `backup-preserved.json`; full media restore còn mở |
| Kiểm lịch qua 3 lần restart + cancellation | chưa | nhường cho A (R2/R3) |
| Cleanup có manifest | ✓ | ✓ R0 manifest đã có |
| Recording tắt | ✓ | ✓ `CONTINUOUS_RECORDING_ENABLED=0` mặc định |

## 5. File đã sửa trong R1

```
M  .gitignore                       # +1 dòng (logs_backend.err)
M  app/api/admin.py                 # +9 dòng (require_space trước save)
M  app/api/system.py                # +30 dòng (preflight disk backup)
M  app/api/training_portable.py     # +80 dòng (cap upload + safe_export)
M  app/training/import_portable.py  # +20 dòng (preflight _safe_extract)
A  app/tests/test_r1_storage_guards.py  # 132 dòng mới (8 test)
```

Untracked (file mới nhưng chưa stage):
- `app/tests/test_r1_storage_guards.py`

Modified working tree:
- `.gitignore`, `app/api/admin.py`, `app/api/system.py`,
  `app/api/training_portable.py`, `app/training/import_portable.py`

## 6. Bằng chứng R1

- `tasks/task-05/r1a-guard-test.log` — 8 test pass (2.30s)
- `tasks/task-05/r1a-focused-test.log` — 55 test pass (11.21s)
- `tasks/task-05/r1b-system-test.log` — 43 test pass (20.65s)
- `tasks/task-05/r1b-vehicles-test.log` — 12 test pass
- `tasks/task-05/r1b-unstage.log` — unstage logs_backend.err

## 7. Còn mở cho R3+ (Owner A)

- **R2 EOF/reconnect**: harness capture EOF, reconnect/source lifetime, race test.
- **R3 baseline hai nguồn**: benchmark GPU hai nguồn runtime.
- **Full media restore**: chưa test end-to-end. Theo handoff "chưa đạt".
- **Backup policy kiểm 3 lần restart**: chưa.

R1 kết thúc. Working tree bảo toàn. Không hạ KPI, không dùng mock, không tự
commit. Tất cả test pass khi có guard, không có test bị cheat.