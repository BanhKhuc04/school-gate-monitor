# Báo cáo rà soát dung lượng ổ D — 2026-10-03

> **Báo cáo chỉ mang tính tham khảo.** Tôi (Cursor Assistant) **không tự ý xóa** bất kỳ file nào. Bạn tự quyết định và tự xóa bằng tay.

## 1. Tình trạng ổ D

| Mục | Giá trị |
|---|---|
| Dung lượng đã dùng | 167.91 GB (180,290,854,912 bytes) |
| Dung lượng còn trống | **7.87 GB** ⚠️ (gần đầy) |
| Tổng ổ D | ~175.78 GB |

## 2. Top folder nặng — phát hiện quan trọng

| Thứ hạng | Folder | Dung lượng | Có phải test? | Ghi chú |
|---|---|---|---|---|
| 1 | `data/backups/*_hourly/media/` (gộp 6 folder) | **~24,049 MB** | ❌ | **Nhân bản ảnh từ snapshots** — vấn đề lớn nhất |
| 2 | `data/snapshots/` | **4,004.94 MB** | ❌ | Ảnh + video clip do app tạo |
| 3 | `.git/objects` | 375.14 MB | ❌ | Lịch sử Git |
| 4 | `.git/index` | 29.72 MB | ❌ | Git index |
| 5 | `app/tests/__pycache__` | 2.78 MB | ⚠️ Có thể xóa | Cache Python |
| 6 | `data/app.db` | 1.32 MB | ❌ | DB đang chạy |
| 7 | `app/tests/task03_closure` | 0.44 MB | ⚠️ Có thể xóa | Test |
| 8 | `data/training` | 0.76 MB | ❌ | Dataset |
| 9 | `app/tests/task03_helpers` | 0.17 MB | ⚠️ Có thể xóa | Test |
| 10 | `data/samples` | 0.27 MB | ❌ | Mẫu |
| 11 | `data/qa_e2e.db` | 0.16 MB | ⚠️ Có thể xóa | DB test |
| 12 | `.pytest_cache/v` | 0.11 MB | ✅ Có thể xóa | Cache pytest |
| 13 | `data/student_photos` | 0.08 MB | ❌ | Ảnh học sinh |
| 14 | `data/training.db` | 0.06 MB | ❌ | DB train |
| 15 | Các file `app/tests/test_*.py` | ~1.0 MB (gộp) | ⚠️ **Không nên xóa** | Test thật — CI cần |

**Tổng `app/tests/` chỉ ~4 MB.** Xóa test chỉ giải phóng tối đa 4 MB — **không giải quyết vấn đề ổ D gần đầy**.

## 3. Phân tích chi tiết `data/backups` (19.48 GB)

### 3.1 File `.db` lẻ (backup DB) — ~17 MB

| File | Size | Time |
|---|---|---|
| `app_20261003_043209.db` | 1.32 MB | 11:32:09 |
| `app_20261003_034740.db` | 1.32 MB | 10:47:40 |
| `app_20261003_033851.db` | 1.32 MB | 10:38:51 |
| `app_20261003_033740.db` | 1.32 MB | 10:37:40 |
| `app_20261003_033716.db` | 1.31 MB | 10:37:16 |
| `app_20260930_132116.db` | 1.14 MB | 10/2 (10:28:03 copy) |
| `app_20260930_130142.db` | 1.14 MB | 10/2 |
| `app_20260930_124814.db` | 1.14 MB | 10/2 |
| `app_20260930_124726.db` | 1.14 MB | 10/2 |
| `app_20260930_043954.db` | 1.14 MB | 9/30 |
| `app_20260930_043952.db` | 1.14 MB | 9/30 |
| `app_20260930_043247.db` | 1.14 MB | 9/30 |
| `app_20260930_042028.db` | 1.14 MB | 9/30 |
| `app_20260930_041442.db` | 1.14 MB | 9/30 |

**Cảnh báo:** Có file `app_20260930_132116.db` đến `app_20260930_041442.db` đều hiển thị LastWriteTime = 10:28:03 — tức là **đã bị sao chép/tập hợp lại vào 10:28:03 hôm nay**. Cần xem lại cơ chế backup (có thể có script copy mỗi ngày).

### 3.2 Folder `*_hourly` (6 folder × 4 GB) — ~24 GB

| Folder | SizeMB | Time |
|---|---|---|
| `20261003_094813_049015_hourly` | 4,008.27 | 4:50:41 PM hôm nay |
| `20261003_092637_870089_hourly` | 4,008.27 | 4:29:12 PM hôm nay |
| `20261002_045133_957108_hourly` | 4,007.11 | 10:27:20 AM hôm nay |
| `20261002_044939_344795_hourly` | 3,430.71 | 10:26:51 AM hôm nay |
| `20261002_034116_352128_hourly` | 4,008.25 | 10:25:59 AM hôm nay |
| `20261003_..._hourly` cũ hơn | (xem chi tiết) | (xem chi tiết) |

**Cấu trúc bên trong mỗi folder hourly:**

```
20261003_094813_049015_hourly/
├── manifest.json                          (1.93 MB)
├── app_20261003_094813_049015.db          (1.32 MB) ← DB
└── media/                                 (~4,005 MB) ← TOÀN BỘ snapshots copy vào
    ├── 20260929_214600_NO_PLATE.mp4       (1.59 MB)
    ├── 20260930_200940_NO_PLATE.jpg       (1.38 MB)
    ├── 20260930_023341_PLATE_OBSCURED.mp4 (1.31 MB)
    └── ... (~hàng nghìn file)
```

**Vấn đề nghiêm trọng:** Mỗi folder hourly chứa bản sao **toàn bộ** `data/snapshots/`. Nếu chạy hourly 24 lần/ngày thì 1 ngày tốn 96 GB. Hiện tại 6 folder đã = 24 GB.

### 3.3 Folder `schema` — 1.38 MB

Không đáng kể, có thể xóa sau khi xác nhận không cần cho migration.

## 4. Phân tích `data/snapshots` (4 GB)

| Loại status | Số file |
|---|---|
| `MULTIPLE.jpg` | 2,080 |
| `PLATE_UNREADABLE.jpg` | 651 |
| Tổng (chỉ đếm 2 status trên) | 2,731 |

Lưu ý: Có file `.mp4` (video clip) cũng nằm trong này — chiếm phần lớn 4 GB.

**Cảnh báo:** `data/snapshots/` đang là **nguồn ảnh trực tiếp** mà app đang dùng (qua `crop_snapshot_path` trong DB). Xóa file ở đây = mất hiển thị ảnh trong Nhật ký vi phạm.

## 5. Phân tích `app/tests` (~4 MB)

| Mục | Số file | Size |
|---|---|---|
| `app/tests/__pycache__/` | (nhiều) | 2.78 MB |
| `app/tests/task03_closure/` | nhiều | 0.44 MB |
| `app/tests/task03_helpers/` | nhiều | 0.17 MB |
| `app/tests/test_*.py` (gộp) | ~80 file | ~1.0 MB |
| Các file test còn lại | nhiều | ~0.1 MB |

**Khuyến nghị:**
- ✅ **Có thể xóa an toàn**: `app/tests/__pycache__/`, `.pytest_cache/`, `data/qa_e2e.db` — tổng **~3 MB**, tự sinh lại khi chạy pytest.
- ⚠️ **Không nên xóa**: các file `test_*.py` — chúng là test thật. Sau khi sửa code mà không chạy test, sẽ không biết có regression.

## 6. Đề xuất thứ tự xóa (nếu bạn muốn tự xóa)

### Tier 1 — An toàn tuyệt đối (regenerate được, ~3 MB)

```powershell
Remove-Item -Recurse -Force .\app\tests\__pycache__
Remove-Item -Recurse -Force .\.pytest_cache
Remove-Item -Force .\data\qa_e2e.db
```

### Tier 2 — Chỉ xóa hourly backup cũ (1–3 cái, ~12 GB)

```powershell
# Giữ lại 2 cái mới nhất, xóa cũ hơn
Get-ChildItem .\data\backups\*_hourly -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 2 |
    Remove-Item -Recurse -Force
```

**Rủi ro:** Mất khả năng restore từ 1 thời điểm cũ hơn. Nếu DB hỏng hôm nay, bạn vẫn còn 2 backup gần nhất.

### Tier 3 — Cân nhắc kỹ (1–10 GB)

- `data/backups/app_2026*.db` (file DB cũ hơn 7 ngày) — giữ lại 3-5 file mới nhất.
- `data/snapshots/*.mp4` cũ hơn 7 ngày — chỉ xóa nếu đã review xong.
- `data/backups/*_hourly/media/*.mp4` — file video là phần nặng nhất trong hourly.

## 7. Vấn đề gốc cần sửa (KHÔNG phải xóa)

| Vấn đề | File | Đề xuất |
|---|---|---|
| Backup hourly **copy toàn bộ snapshots** thay vì incremental | `app/maintenance_worker.py` (cần xác minh) | Sửa backup chỉ copy file **mới từ lần backup trước**, không copy lại toàn bộ |
| Không có chính sách rotation | `app/maintenance_worker.py` | Thêm giữ N backup mới nhất, tự xóa cũ |
| File `.db` backup cũ hiển thị LastWriteTime giống nhau (10:28:03) | Có script copy mỗi ngày (?) | Kiểm tra có script scheduled copy file .db cũ về đây không |

## 8. Việc đã làm

- ✅ Quét ổ D
- ✅ Liệt kê folder lớn
- ✅ Phân tích cấu trúc `data/backups` và `data/snapshots`
- ✅ Phân loại an toàn/không an toàn

## 9. Việc KHÔNG làm

- ❌ Không xóa bất kỳ file nào
- ❌ Không tự sửa `maintenance_worker.py`
- ❌ Không chạm vào `data/app.db` (DB đang chạy)
- ❌ Không chạm vào `app/tests/test_*.py` (CI cần)

---

Bạn có thể dùng file này làm checklist. Khi nào bạn quyết, hãy nói "xóa tier 1" hoặc "xóa tier 2" và tôi sẽ hướng dẫn lệnh PowerShell chính xác (nhưng vẫn để bạn chạy tay).
