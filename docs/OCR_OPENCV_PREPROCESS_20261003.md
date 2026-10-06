# OpenCV plate preprocessing - 2026-10-03

Gray -> bilateral -> Canny -> five largest contours -> convex four-corner
perspective correction. Bright-panel Otsu fallback handles broken rims.
Try up to four crop variants with CLAHE/adaptive threshold; conflicting
reads require review. Variants never add independent votes.

Exact reads: reviewed 8/40 -> 15/40; roll20 1/8 -> 4/8; camera 0/11 -> 1/11.
48 focused tests pass. Full suite blocked by disk space.
Timing, per-image results and before/after image: runs/ocr_opencv_20261003/.
Backend restart required. Independent camera validation remains necessary.
