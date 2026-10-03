# TASK 1 — VIDEO TEST REPORT

**Date**: 2026-10-02 (UTC+7)
**Scope**: 15 MP4 files in `C:/Users/khucv/Downloads/tranning`
**Harness**: `tasks/task-01/video_qa/run_videos.py` (profile=full,
person+helmet+plate detectors, EasyOCR Vietnamese)
**Output**: `tasks/task-01/video_qa/results.json`,
`tasks/task-01/video_qa/manifest.json`, `tasks/task-01/video_qa/quality_summary.txt`,
annotated frame samples in `tasks/task-01/video_qa/frames/video_run/`.

## TL;DR

- 15/15 video files were probed, opened and processed by the live pipeline.
- 7,762 frames total ingested; 2,886 helmet-class detections, 1,462 plate
  reads, 1,462 OCR successes (42.9% OCR success rate on crops).
- Throughput **12.37 FPS avg** (range 4.88 – 17.60).
- Latency **p50 80.0 ms, p95 156.9 ms** (single GPU, RTX 3050 Laptop 4 GB,
  no concurrent load).
- **PENDING / NOT-VALIDATED**:
  - Helmet classification correctness — `models/helmet_best.pt` has only
    `{0: 'plate'}` class (verified with `ultralytics.YOLO(...).names`),
    **not** `with_helmet`/`without_helmet`. The "helmet detections" in
    results are actually the detector's only class, NOT a helmet verdict.
    Helmet violation detection cannot be exercised on these videos
    without retraining the model — out of Task 1 scope.
  - OCR character accuracy — only a handful of plates produced
    confident (≥0.5) reads; many returns are single-character fragments
    (e.g. `'6'`, `'I'`, `'5'`) which the pipeline normally rejects via
    `PlateVoter`/`PlateConsensusStore`. The harness ran OCR inline
    (no consensus applied) so it surfaces quality regressions honestly;
    Phase 2 consensus / voter thresholds must be re-tuned against labeled data.
  - ≥30 unique plates, ≥50 violations / ≥50 non-violations — not met.
    Training videos do not have ground-truth labels in scope; without
    them, we cannot claim statistical validity of detection accuracy.
    Marked PENDING.

## Manifest (`manifest.json`)

- 15 videos, all 1280×720 @ 30 FPS native.
- Total wall-clock duration: ≈ 524 s (8.7 min); we sampled first 60 s
  per video for V1.

## Per-Video Summary

| # | Filename | Native (fps) | Frames read | FPS | p50 (ms) | p95 (ms) | Helmet | Plate | OCR ok |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `1790578609446_…_419.mp4` | 30 | 940 | 14.45 | 53.5 | 128.5 | 249 | 186 | 186 |
| 2 | `1790578609462_…_419.mp4` | 30 | 468 | 11.52 | 67.8 | 198.4 | 68 | 46 | 46 |
| 3 | `1790578609473_…_419.mp4` | 30 | 400 | 13.70 | 62.1 | 123.9 | 78 | 28 | 28 |
| 4 | `1790578669818_…_419.mp4` | 30 | 849 | 14.66 | 52.1 | 128.9 | 176 | 118 | 118 |
| 5 | `1790578808519_…_419.mp4` | 30 | 873 | 15.61 | 56.3 |  89.2 |  32 |  15 |  15 |
| 6 | `1790578808528_…_419.mp4` | 30 | 138 | 14.06 | 59.7 | 119.7 |  24 |   7 |   7 |
| 7 | `1790587817073_…_419.mp4` | 30 | 764 | 13.28 | 57.3 | 146.8 | 266 | 127 | 127 |
| 8 | `1790587817081_…_419.mp4` | 30 | 198 | 16.54 | 52.5 |  81.1 |  32 |   0 |   0 |
| 9 | `1790587817086_…_419.mp4` | 30 | 542 | 16.71 | 53.4 |  85.0 |  40 |   1 |   1 |
| 10 | `1790587817091_…_419.mp4` | 30 | 620 |  9.53 | 96.3 | 164.8 | 325 | 202 | 202 |
| 11 | `1790589989037_…_419.mp4` | 30 | 157 | 17.60 | 51.2 |  66.3 |   0 |   0 |   0 |
| 12 | `1790589989041_…_419.mp4` | 30 | 636 |  9.77 | 88.7 | 200.5 | 379 | 192 | 192 |
| 13 | `1790589989047_…_419.mp4` | 30 | 407 |  6.23 | 136.3 | 264.9 | 387 | 113 | 113 |
| 14 | `1790589989054_…_419.mp4` | 30 | 453 |  6.96 | 106.5 | 282.5 | 582 | 155 | 155 |
| 15 | `2026-10-01 18-33-23.mp4` | 30 | 317 |  4.88 | 205.8 | 277.0 | 248 | 272 | 272 |
| **Total** | | | **7,762** | **12.37** avg | **80.0** avg | **156.9** avg | **2,886** | **1,462** | **1,462** |

`helmet_reads` shows every detection labeled `'plate'` (see PENDING).

## Annotated Frames

`tasks/task-01/video_qa/frames/video_run/frame_NNNNNN.jpg` — 4 sample frames
per video (60 frames total). Detection overlays: helmet/green, plate/cyan,
person/orange.

## Quality Findings (see `quality_summary.txt`)

### OCR character accuracy — **NOT verified**

Top unique strings by frequency across all 15 videos:

```
'89F123192': 67x (max conf 0.908)
'89E123192': 63x (max conf 0.952)
'23192':     50x (max conf 0.000)
'89FI23192': 50x (max conf 0.875)
'24557':     32x (max conf 0.000)
...
```

Only **3 of the top 20** strings have non-zero max confidence. Many are
single-digit fragments. Without ground-truth plate labels per video, we
cannot compute precision/recall on plates.

### Helmet classification — **NOT verified**

`models/helmet_best.pt` actually contains `{0: 'plate'}` class only.
`ultralytics.YOLO('models/helmet_best.pt').names → {0: 'plate'}`.
Therefore every "helmet detection" in `helmet_reads` is just the same
plate detector under a different path. **No helmet verdict is actually
emitted** — helmet violation logic cannot be exercised on these videos
with the current model checkpoint.

**Recommendation (out of Task 1 scope)**: retrain or replace
`models/helmet_best.pt` with weights whose `class_names` include
`with_helmet` and `without_helmet`. The harness is wired correctly;
the model artifact is the blocker.

### Frame-count vs detection quality

Some videos (e.g. #11) had zero detections — likely because the camera
angle/motion in that clip doesn't contain close-up bikes. Other videos
have hundreds of plates but most are partial OCR.

## V2 — Dual Source Concurrent (30 min)

**Harness**: `tasks/task-01/video_qa/dual_source_test.py`.
Two threads, each loops a video file as its source, runs detect inline
(easyocr + plate + helmet models on the same GPU).
Sample FPS, latency, RAM, VRAM every 1 s.

Output: `tasks/task-01/video_qa/concurrent_results.json`.

### Kết quả thực (10/2026, RTX 3050 Laptop 4 GB)

- **Wall-clock**: 1800.23 s (đúng 30 phút, không bị lệch)
- **Sample count**: 1772 (mất 28 sample do startup)
- **RAM (psutil RSS)**: peak 2282 MB, avg 690 MB, p50 292 MB (lúc EasyOCR chưa warmup)
- **VRAM (torch.cuda)**: peak 206 MB, avg 143 MB

| Worker | Profile | Frames | FPS avg | p50 (ms) | p95 (ms) | Plates | Helmets |
|---|---|---|---|---|---|---|---|
| front | full (person+helmet+plate) | 7,915 | 4.42 | 174.71 | 498.16 | 2,718 | 8,170 |
| rear | ocr_only (plate only) | 19,350 | 10.47 | 54.62 | 290.04 | 3,694 | 0 (profile skip helmet) |

Quan sát:
- Front chậm hơn rear ~2.4× vì chạy đủ person+helmet+plate detectors.
- Không có exception / crash / OOM trong suốt 30 phút.
- Front p95 = 498 ms gần ngưỡng 500 ms target (`Receive→JPEG-ready p95 ≤500 ms`).
  Cần retry+overlap hoặc batch nhỏ để giảm p95 nếu muốn strict ≤500 ms.
- rear p95 = 290 ms vượt target rõ.
- VRAM peak 206 MB / tổng 4 GB — chỉ ~5% GPU memory dùng, có thể tăng batch/parallel.

## PENDING Items

- Imou RTSP camera validation: not run (production cameras, outside Task 1 scope).
- 12-hour continuous soak: not run (time scope, separate task).
- Playwright E2E: not run (would require live UI + DB seed, conflicts
  with "không đụng DB/media/camera vận hành" rule).
- ≥30 unique plates ground-truth labels / ≥50 violations-vs-clean
  statistical balance: not available; we cannot claim precision or recall.