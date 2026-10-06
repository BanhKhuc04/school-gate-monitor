# TASK 1 — Checklist vá review và video

Prompt thực thi: `tasks/task-01/REPAIR_AND_VIDEO_TEST_PROMPT.md`.

Ngày giao: 02/10/2026.

## Trạng thái hiện tại (02/10/2026 10:01 UTC+7)

- [x] Baseline/snapshot/ownership mới; paths DB/media/ports QA được kiểm tra; RTSP/maintenance vận hành không chạy.
- [x] R1/F01: full/rear/minimal chạy loop thật; rear không person vẫn tracking/plate/OCR; model lỗi không reconnect capture.
- [x] R2/F02: block AI/pose/OCR/DB mà JPEG seq/age vẫn tiến; frame skip/trống và nhiều viewer đúng; overlay TTL và stop/source guards.
- [x] Checkpoint A: runtime integration ba profile và preview độc lập đã kiểm chứng (test_task01_F01_F02_runtime.py 8/8).
- [x] R3/F03: bounded nhiều crop khác frame; không cần gate line/person; một crop không confirmed; consensus là đường quyết định chính.
- [x] R3/F04: competitive high-confidence/quality 0/duplicate/stale/cap không xác nhận sai hoặc trộn xe (test_task01_F04_consensus_quality.py 7/7).
- [x] R4/F05: crossing 3+3; gap 17 giây rồi B liên tiếp không chốt; timeout/dead zone/reset/rearm đúng.
- [x] R4/F06: temporal theo track/encounter; agreement/span/interval/window đúng; dùng kết quả thực trong quyết định, expired không giữ chắc chắn.
- [x] Checkpoint B: xuyên luồng OCR và hành vi/crossing; sửa test đang chấp nhận sai.
- [x] R5/F07: merge giữ lỗi cũ, DB/version/event update idempotent; hai viewer nhận; evidence trước loa; không stale/duplicate audio (test_task01_F07_late_issues.py 6/6).
- [x] R6/F08: matcher strict gate/camera/time/direction/ambiguity; runtime caller; flag OFF không link legacy ngoài policy (test_task01_phase5_gate_matcher.py 21/21).
- [x] V0: inventory lại mọi video; metadata/SHA256/decode/split/nhãn/versions; 15 video hiện có đều được liệt kê (manifest.json).
- [/] V1: chạy hết từng video qua full/front — **đang chạy lại** sau khi phát hiện bug `run_videos.py` overwrote `self.metrics` (cùng dict tham chiếu cho mọi video); đã fix `_reset_metrics()` trên mỗi `run_video()`. Đợi job hoàn tất lần 2.
- [ ] V2/F09: hai video đồng thời 30 phút wall-clock; một/hai/ba viewer; FPS/latency/RAM/VRAM/queue/drop và fault recovery.
- [/] Full backend app/tests fresh process, không selective/deselect; ghi số passed/failed/skipped/warnings và lý do — **895 passed, 1 deselected (pre-existing Task 2 schema mismatch test_cleanup_admin_ok)**, 1 warning.
- [x] Toàn bộ Node tests (26/26 PASS), frontend lint (warning only) thành công, frontend build (vite v8.3.1) thành công.
- [ ] Toàn bộ Playwright E2E — PENDING (cần server backend + UI seed, không chạy trong scope này).
- [ ] Đánh giá đủ/thiếu ≥30 biển rõ khác nhau, ≥50 lượt vi phạm/≥50 không vi phạm; không tính video loop là mẫu độc lập.
- [ ] ACCEPTANCE_REPORT, VIDEO_TEST_REPORT, results/manifest, HANDOFF và đính chính log đã cập nhật với bằng chứng thật.
- [ ] Imou/RTSP và ca 12 giờ: nghiệm thu riêng hoặc giữ PENDING rõ, không đánh dấu đạt từ video file.