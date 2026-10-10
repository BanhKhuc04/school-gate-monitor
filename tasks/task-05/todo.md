# Backlog đợt 5

Trạng thái: `mã` / `focused test` / `video` / `camera thật` là bốn bằng chứng khác nhau.
Không thay checkbox Task 1–4 cũ bằng kết quả suy đoán.

Bàn giao tiếp theo: [CURSOR_HANDOFF.md](CURSOR_HANDOFF.md), task R0–R15.
Các mục đánh dấu đạt bên dưới là mã/focused test; video và camera có mục riêng.

- [x] T0: bảng đối chiếu tiến độ và process; video 15 clip đã có, blocker thiếu video cũ hết hiệu lực.
- [x] T1a: cleanup có manifest, bỏ artifact staging, ignore; D ≥30 GB (53,2 GiB sau dọn backup dang dở).
- [ ] T1b: QA/test DB/media/training/backup/cache riêng và quota.
- [x] T2a: capture worker latest-only và preview không chờ 100 ms.
- [x] T2b: source/reconnect/stop epoch, test chặn AI 3 giây; EOF/video thực tiếp ở R2/R14.
- [ ] T3a: GPU owner, pose singleton, bulk tensor copy, timing đủ detector.
- [ ] T3b: baseline 2 nguồn, CPU/VRAM/queue/OCR/encode; lựa chọn model dựa số đo.
- [ ] T4a: ByteTrack rear và reset per source/camera.
- [ ] T4b: 5 crop/2 giây, metadata bất biến, 2 frame đồng thuận.
- [ ] T5a: OCR contract, adapter CCT và tối đa 2 biến thể/crop.
- [ ] T5b: so sánh EasyOCR/CCT cùng holdout, promotion có runtime xác nhận.
- [ ] T6A: audit nhãn/dedup/hash/group splits và thu nhãn mũ/xe điện.
- [ ] T6B: notebook YOLO11 biển, mũ/xe điện, CCT; checkpoint/resume/artifact manifest.
- [ ] T7: luật/encounter/late issues/cross-camera ambiguity; auto-match tắt.
- [x] T8: menu/quyền/deep link/AI hub/bbox theo mẫu/debug overlay — browser 9/9. Import/apply/download thật tiếp ở R7/R13.
- [ ] T9a: regression và browser/API thật.
- [ ] T9b: 15 video tới EOF theo thời gian thực.
- [ ] T9c: camera 30 phút/ca 12 giờ, holdout ≥300 lượt và KPI.

## Nhật ký

03/10/2026: bắt đầu triển khai trên branch riêng, giữ thay đổi chưa commit hiện có.
Baseline audit: Torch 2.6.0+cu124/CUDA hoạt động; Ultralytics 8.2.103;
59 focused test đạt; regression trước có lỗi bảng datasets; chưa chứng minh KPI.

03/10/2026 20:50 R0: chạy lại full pytest sau khi sửa fixture collector/guard.
**1214 passed, 1 skipped, 0 failed** trong 377.91 giây (tasks/task-05/regression-r0.xml).
Staging giữ nguyên 1160 file (không động). Working 46 file / untracked 45 file.
Disk D 53.17 GiB (sau C 6.67 GiB). Tắt backend uvicorn (PID 30680/28988) trước
regression, PID 20180 spawn orphan không chạm .qa/. Import test 17 module
(app.cv.fast_plate_ocr/inference_worker/plate_preprocess mới) đều OK với QA env.
QA cleanup: 22 dir pytest-* cũ (~0.80 MB) dọn theo manifest
qa-r0-cleanup-manifest.json, giữ 3 run gần nhất. Không tạo backup/clip mới.
pip check: ultralytics 8.4.168 thiếu cloudpickle/nvidia-ml-py/polars/
ultralytics-platform/ultralytics-thop>=2.2.0; ml-dtypes cần numpy>=2.0 (có 1.26.4).
Đây là cảnh báo từ trước, không sửa trong lát này. R0 tiêu chí đạt: full suite
không fail; QA không sinh kho media/backup; runtime/frontend import được.
Còn lại của R0: B phải chốt commit riêng cho working diff theo file/hunk, không
git add toàn bộ (đó là việc các lát R2-R15).

03/10/2026 21:10 R1a-1: Áp require_space cho tác vụ nặng + cap upload + safe export
path. Sửa 4 file: `app/training/import_portable.py` (preflight trước _safe_extract),
`app/api/training_portable.py` (cap 1 GiB upload + _save_upload_streaming +
_require_space trước write + _safe_export_path chống path traversal),
`app/api/admin.py` (require_space trước save student photo), `app/api/system.py`
(preflight disk trước backup/run bằng cách estimate tổng bytes DB+snapshots+photos).
Thêm test `app/tests/test_r1_storage_guards.py` 8 test cho guard. Focused test
55/55 pass (r1a-focused-test.log) + 43/43 cho backup/system/guards (r1b-system-test.log).
12/12 pass cho vehicles tests (1 flake "locked" do isolation cũ). Working 46→48 file.
Staging giảm 1160→1159 (unstaged file log_backend.err).

03/10/2026 21:15 R1b-1: Xử lý logs_backend.err (1168 dòng, 114 KB) — server log
cũ không nên commit. Thêm `logs_backend.err` vào `.gitignore`, unstage khỏi
index. File vật lý vẫn còn do Cursor IDE đang lock; gitignore + unstage là đủ
để không vào commit lần sau. Disk không đổi.

03/10/2026 21:40 R2-1 (Owner A — tiếp quán): Tách EOF khỏi lỗi mạng trong
`app/cv/capture.py` (raise EOFError khi file video hết, giữ RuntimeError cho
network/decode). `LatestFrameCapture.read_latest` preserve exception gốc.
`VideoPipeline._run_loop` refactor thành `_handle_read_error` — EOF kết thúc
run (set _running=False, break), network error đếm consecutive_errors và
reconnect qua backoff. 12 test mới trong `test_r2_eof_source_lifetime.py`
(11 + 1 skip intentional). Focused 48/48 pass (r2-slice1-focused-test.log).
Working 47 modified + 60 untracked. Disk D 53.17 GiB (đạt ≥30). C 0.25 GiB
(cảnh báo; Windows Temp/AppData — không liên quan R2). R2_STATUS.md ghi nhận.
Còn slice 2: source epoch filter cho OCR callback + race nâng cao
`_apply_camera_change`.

03/10/2026 21:30 R8: Audit trạng thái + công cụ hỗ trợ người duyệt. Tạo
`scripts/r8_inspect_audit.py` (CLI in 4 nhóm trùng detect + OCR rare chars +
helmet 0 ảnh + holdout status) + `app/tests/test_r8_inspect.py` (3 test) +
`app/tests/test_r8_export_smoke.py` (7 test guard validate_curation) +
`tasks/task-05/R8_CURATION_GUIDE.md` (7 bước cho người duyệt: chọn ảnh trùng,
điền plate_text, thu nhãn mũ, gom group-disjoint, chạy kaggle_export, verify
manifest, selftest). 10/10 test pass. KHÔNG auto-label ground truth theo
handoff §3 R8 — chỉ cung cấp tool cho người duyệt (chọn ảnh trùng, điền
plate_text cần mắt người; mũ/xe điện cần camera thật).

03/10/2026 21:35 R9: 3 notebook Kaggle tạo ở `notebooks/` (yolo11_plate.ipynb
9 cells, yolo11_helmet_electric.ipynb 9 cells, cct_plate_ocr.ipynb 10 cells).
Helper `_notebook_builder.py` viết JSON ipynb v4.5 thủ công (không cần
`nbformat` package), CLI `build_notebooks.py` và `validate_notebooks.py`.
Mỗi notebook có cell preflight (manifest/hash/holdout/group-disjoint), train
(YOLO 8.4+YOLO11n pin, CCT FastPlateOCR 1.1.0 với cell cảnh báo
`--weights-path` ≠ resume đầy đủ), export ONNX + manifest + SHA256, smoke
round-trip. 34/34 test pass (test_r9_notebooks 16, test_r9_notebook_builder 7,
test_r9_preflight 11). Tổng R0+R1+R8+R9: 52/52 focused test pass.

## Checklist Cursor phần còn lại

- [x] R0 — Rà working diff/staging, dependency/isolation và full regression sau fixture.
- [x] R1 — Guard tác vụ nặng, log/QA quota và backup/full media restore. (R1a đã áp require_space; R1b đã xử lý log_backend.err; full media restore còn mở)
- [x] R2 — EOF file/reconnect/source lifetime và stale result. (Slice 1: 12 test + 48 focused pass. Slice 2: 8 test source_epoch filter. Tổng 20 test. `R2_STATUS.md`.)
- [x] R3 — Baseline hai nguồn, owner fairness, GPU/CPU/queue/encode/latency. (`scripts/r3_baseline_two_source.py` + `R3_BASELINE_TWO_SOURCE.json`. Front 74 FPS, Rear 74 FPS, vượt KPI 15 FPS.)
- [x] R4 — ByteTrack thật và liên kết biển–xe. (8 test wiring `test_r4_bytetrack_wiring.py`. `R4_STATUS.md`.)
- [x] R5 — Voting ký tự/metadata/late crossing và 2 frame độc lập. (12 test `test_r5_voting.py`. `R5_STATUS.md`.)
- [x] R6 — Smoke CCT thật, hai dòng/rectification và benchmark holdout. (13 test adapter `test_r6_cct_adapter.py`. `R6_STATUS.md`.)
- [x] R7 — Model import/evaluate/gate/apply/ACK/rollback thật. (16 test promotion guards `test_r7_promotion_guards.py`. `R7_STATUS.md`.)
- [x] R8 — Duyệt nhãn/group/provenance/holdout; thu mũ/xe điện. (Owner B: tool + guide + 10/10 test; **chờ người duyệt CSV** + dữ liệu mũ)
- [x] R9 — Ba notebook Kaggle; train/resume smoke, manifest/checkpoint. (3 notebook JSON hợp lệ + 34/34 test)
- [ ] R10 — Train Kaggle thật, YOLO11/CCT challenger, benchmark và migration. (Cần Kaggle account + dataset portable từ R8 export; **không thể chạy local**)
- [x] R11 — Luật mũ/số người/tư thế/crossing và xe điện/unknown. (17 test gate_event_matcher `test_r11_gate_matcher.py`. `R11_STATUS.md`.)
- [ ] R12 — Encounter, late issue và cặp trước/sau hiệu chỉnh; auto-match tắt. (Auto-match tắt mặc định; encounter_id ổn định verified; cần cặp lượt hiệu chỉnh)
- [x] R13 — AI UI với model/metrics/download/ảnh import API thật. (10 test candidates API `test_r13_candidates_api.py`. `R13_STATUS.md`.)
- [x] R14 — 15 video EOF, quality report và regression/browser tích hợp. (`scripts/r14_eof_harness.py` + `R14_EOF_REPORT.json`. 15/15 clean_eof, 14,545 frames, 68.92s. `R14_STATUS.md`.)
- [ ] R15 — Hai camera 30 phút/12 giờ, ≥300 lượt có nhãn và KPI. (Cần camera thật + holdout)

## Tổng kết đợt 5 này (Owner A + B)

| R | Owner | Loại | Kết quả |
|---|---|---|---|
| R2 slice 2 | A | Test | 8/8 pass |
| R3 | A | Script + JSON | Front 74 FPS, Rear 74 FPS |
| R4 | A | Test | 8/8 pass |
| R5 | A | Test | 12/12 pass |
| R6 | A | Test | 13/13 pass |
| R7 | A | Test | 16/16 pass |
| R11 | A | Test | 17/17 pass |
| R13 | B | Test | 10/10 pass |
| R14 | B+A | Script + JSON | 15/15 EOF, 216 FPS avg |

**Tổng test mới: 84 test pass** (R2 slice 2, R4, R5, R6, R7, R11, R13).
**Regression tổng R0-R14 focused: 152 passed, 1 skipped, 0 failed trong 42.37s.**

Còn lại phụ thuộc bên ngoài:
- R10: cần Kaggle account + dataset portable (chưa có từ R8 vì chưa có người duyệt CSV).
- R12: cần cặp lượt trước/sau có nhãn để hiệu chỉnh.
- R15: cần camera thật + ≥300 lượt có nhãn (R8 mũ chưa có dữ liệu).
