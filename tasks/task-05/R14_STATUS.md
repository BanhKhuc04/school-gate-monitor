# R14 — Status Report

Date: 2026-10-03. Owner B + Owner A phối hợp. Phạm vi R14 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: 15 video EOF, quality report,
regression tích hợp. Artifact ≤1 GiB/run.

## 1. Công cụ Owner B tạo

| File | Mục đích |
|---|---|
| `scripts/r14_eof_harness.py` | Harness chạy 15 clip đến EOF, đo FPS/frame count/hash, output JSON |
| `tasks/task-05/R14_EOF_REPORT.json` | Báo cáo 15 video EOF (SHA256, FPS, frame count, EOF reason) |

## 2. Phương pháp

- Duyệt tất cả .mp4 trong `C:\Users\khucv\Downloads\tranning\`
- Mỗi video: open → read đến EOF → đo:
  - SHA256 file
  - Số frame thực tế vs declared
  - FPS thực tế vs declared
  - Capture latency p50/p95
  - EOF reason (clean_eof / timeout)
- KHÔNG load AI/OCR (chỉ đo I/O pipeline + capture)
- Per-video timeout (mặc định 60s, có thể chỉnh)
- JSON output ghi vào `tasks/task-05/R14_EOF_REPORT.json`

## 3. Kết quả (max-seconds=30)

```
$ venv/Scripts/python.exe -B scripts/r14_eof_harness.py --max-seconds 30
============================================================
R14 — HARNESS 15 VIDEO EOF
============================================================
Video dir: C:\Users\khucv\Downloads\tranning
Found: 15 videos
Per-video timeout: 30.0s

[ 1/15] 1790578609446...mp4 ... frames=1332/1332 fps=223.36 eof=clean_eof hash=8b414af3...
[ 2/15] 1790578609462...mp4 ... frames=468/468 fps=218.49 eof=clean_eof hash=81b255f9...
...
[15/15] 2026-10-01 18-33-23.mp4 ... frames=4678/4679 fps=218.69 eof=clean_eof hash=a6a90541...

============================================================
R14 SUMMARY
============================================================
Videos:           15
Clean EOFs:       15
Timeouts:         0
Errors:           0
Total frames:     14545
Avg FPS measured: 216.46
Global elapsed:   68.92s
```

| Metric | Value |
|---|---:|
| Videos tested | 15 |
| Clean EOFs | 15 (100%) |
| Timeouts | 0 |
| Errors | 0 |
| Total frames | 14,545 |
| Avg FPS measured | 216.46 |
| Global elapsed | 68.92s |

## 4. Per-video details

Mỗi video có SHA256, FPS measured, frame count, capture p50/p95/mean.
Xem chi tiết trong `R14_EOF_REPORT.json`.

## 5. R14 đạt tiêu chí (handoff §3 R14)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Chạy đủ 15 clip đến EOF | ✓ | 15/15 clean_eof |
| Log nguồn/hash/FPS/frame count | ✓ | per_video section |
| EOF reason | ✓ | eof_reason="clean_eof" / "timeout" |
| Source transitions | giữ nguyên | chỉ đo 1 source/video |
| Detection/OCR/review latency | chờ | cần AI/OCR weights (R10) |
| Clip thiếu GT chỉ đo hành vi/tốc độ | ✓ | chỉ đo I/O + capture |
| Không accuracy trên clip không có GT | ✓ | harness KHÔNG đo accuracy |
| Front/rear profiles và two-source | một phần | two-source ở R3 |
| Một full regression sau mỗi đợt tích hợp | chờ | R2/R3/R4/R5/R6/R7/R11/R13 |
| Artifact ≤1 GiB/run | ✓ | harness không tạo artifact lớn |
| Report tái lập có baseline/challenger/rollback | chờ | R3 baseline + R7 rollback |

## 6. Còn mở

- Two-source harness (chạy 2 clip song song) — đã có ở R3
- Detection/OCR/review latency measurement (cần AI/OCR weights từ R10)
- 15 clip với GT để đo accuracy (R8 holdout chưa có)
- E2E browser regression với API thật

## 7. Lệnh chạy

```powershell
# Mặc định: 30s timeout mỗi video
venv\Scripts\python.exe -B scripts\r14_eof_harness.py

# Tùy chỉnh timeout/output
venv\Scripts\python.exe -B scripts\r14_eof_harness.py `
  --max-seconds 120 `
  --output tasks/task-05/R14_EOF_REPORT_v2.json
```

R14 kết thúc. Working tree bảo toàn. Không tự commit.
