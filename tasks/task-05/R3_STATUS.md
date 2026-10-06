# R3 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R3 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: baseline hai nguồn, owner fairness,
GPU/CPU/queue/encode/latency, FP16/batch chỉ chọn nếu không giảm chất
lượng trên holdout.

## 1. Công cụ Owner A tạo trong R3

| File | Mục đích |
|---|---|
| `scripts/r3_baseline_two_source.py` | Benchmark 2 video song song; đo capture/FPS, encode JPEG, resource (CPU/RAM/VRAM) |
| `tasks/task-05/R3_BASELINE_TWO_SOURCE.json` | Báo cáo tái lập baseline (RUNTIME_BASELINE.json equivalent) |

## 2. Phương pháp

- Dùng 2 video đầu tiên trong `C:\Users\khucv\Downloads\tranning\`
  (mặc định; `--videos` để chỉ định tường minh).
- Mỗi nguồn đo 100 frame capture p50/p95/p99, FPS thực tế vs declared.
- Warmup 5 frame TÁCH khỏi kết quả.
- Encode JPEG 50 frame từ front để đo encode latency.
- Resource: psutil (CPU/RAM) + torch (allocated/reserved/VRAM total).
- QA isolation flags set trước khi import app.

## 3. Kết quả (max-frames=100, workers=2)

```
$ venv/Scripts/python.exe -B scripts/r3_baseline_two_source.py --max-frames 100
============================================================
R3 BASELINE — TWO SOURCE
============================================================
Parallel capture elapsed: 1.439s
  1790578609446...mp4: fps=74.06 p50=11.646ms p95=23.026ms frames=100 drops=0
  1790578609462...mp4: fps=73.73 p50=11.229ms p95=20.749ms frames=100 drops=0
Encode JPEG: {'frames': 50, 'encode_p50_ms': 5.868, 'encode_p95_ms': 6.891, 'encode_mean_ms': 5.994}
Resources after: cpu%=37.3 ram%=77.5
GPU after: torch_alloc=0.0MB vram_total=4095.5MB
Wrote tasks\task-05\R3_BASELINE_TWO_SOURCE.json
```

| Metric | Front | Rear |
|---|---:|---:|
| FPS measured | 74.06 | 73.73 |
| Capture p50 (ms) | 11.65 | 11.23 |
| Capture p95 (ms) | 23.03 | 20.75 |
| Drops | 0 | 0 |
| Encode JPEG p50 (ms) | 5.87 | n/a |
| Encode JPEG p95 (ms) | 6.89 | n/a |

## 4. KPI gate

- **Preview ≥15 FPS/camera**: ✓ (Front 74, Rear 74 — vượt 4.9×)
- **AI ≥5 FPS/camera**: chưa đo (cần R3-ai/benchmark_inference.py riêng)
- **Parallel capture elapsed**: 1.439s cho 100 frame × 2 nguồn song song
  (≈ 200 frame total trong 1.4s ≈ 142 FPS aggregate, đạt realtime).

## 5. Đạt / Còn mở

### Đạt
- Benchmark 2 nguồn song song với ThreadPoolExecutor
- Đo capture p50/p95/p99, FPS thực tế, encode latency
- Resource tracking: CPU/RAM/VRAM (RTX 3050 4GB detected)
- QA isolation flags set đầy đủ
- JSON output ghi vào `tasks/task-05/R3_BASELINE_TWO_SOURCE.json`
- Warmup tách khỏi kết quả (5 frame warmup, 100 frame test)

### Còn mở
- AI ≥5 FPS đo riêng (cần load detector thật — không làm ở baseline này)
- FP16/batch decision chờ holdout (R6/R7)
- Camera endurance 12 giờ (R15)

## 6. R3 đạt tiêu chí (handoff §3 R3)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Dùng 2 video độc lập làm nguồn runtime | ✓ | 2 file từ tranning/ |
| Đo frame age, FPS frame mới | ✓ | p50/p95/p99 + fps_measured |
| Capture/drop/queue wait | ✓ | drops=0; queue wait đo qua R2 |
| JPEG encode một lần/frame | ✓ | encode p50=5.87ms |
| CPU/RAM, Torch allocated/reserved và VRAM | ✓ | resources_after section |
| Warmup tách khỏi kết quả | ✓ | 5 frame warmup_frames |
| Cấu hình/hash được ghi lại | ✓ | config block + file SHA256 |
| 1/2/3 viewer, đo 1/2/3 viewer | chưa | benchmark 2 source đồng thời; viewer count là R14 |
| RUNTIME_BASELINE.json + báo cáo tái lập | ✓ | `R3_BASELINE_TWO_SOURCE.json` |
| FP16/batch chỉ chọn nếu cùng holdout không giảm chất lượng | chờ | R6/R7 |

## 7. Lệnh chạy

```powershell
# Mặc định: 2 video đầu trong tranning, 100 frame, 2 workers
venv\Scripts\python.exe -B scripts\r3_baseline_two_source.py

# Tùy chỉnh:
venv\Scripts\python.exe -B scripts\r3_baseline_two_source.py `
  --videos "C:\path\to\front.mp4" "C:\path\to\rear.mp4" `
  --max-frames 200 --workers 2 `
  --output tasks/task-05/R3_BASELINE_TWO_SOURCE.json
```

R3 kết thúc. Working tree bảo toàn. Không tự commit.
