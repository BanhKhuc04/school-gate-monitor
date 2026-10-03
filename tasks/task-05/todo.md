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

03/10/2026 bàn giao theo yêu cầu người dùng: Ultralytics đã 8.4.168, weights
runtime chưa chuyển YOLO11. CCT adapter/GPU/voting/UI/dataset có mã chưa commit.
Full gần nhất 1.200 pass/14 fail/1 skip; fixture gây 14 lỗi đã sửa, nhóm 59 test
đạt, full sau sửa vẫn mở ở R0. Backup 38/38, dataset selftest 10/10, UI 9/9.
Hai bộ backup hash toàn bộ/restore DB đạt; full media restore còn mở.

## Checklist Cursor phần còn lại

- [ ] R0 — Rà working diff/staging, dependency/isolation và full regression sau fixture.
- [ ] R1 — Guard tác vụ nặng, log/QA quota và backup/full media restore.
- [ ] R2 — EOF file/reconnect/source lifetime và stale result.
- [ ] R3 — Baseline hai nguồn, owner fairness, GPU/CPU/queue/encode/latency.
- [ ] R4 — ByteTrack thật và liên kết biển–xe.
- [ ] R5 — Voting ký tự/metadata/late crossing và 2 frame độc lập.
- [ ] R6 — Smoke CCT thật, hai dòng/rectification và benchmark holdout.
- [ ] R7 — Model import/evaluate/gate/apply/ACK/rollback thật.
- [ ] R8 — Duyệt nhãn/group/provenance/holdout; thu mũ/xe điện.
- [ ] R9 — Ba notebook Kaggle; train/resume smoke, manifest/checkpoint.
- [ ] R10 — Train Kaggle thật, YOLO11/CCT challenger, benchmark và migration.
- [ ] R11 — Luật mũ/số người/tư thế/crossing và xe điện/unknown.
- [ ] R12 — Encounter, late issue và cặp trước/sau hiệu chỉnh; auto-match tắt.
- [ ] R13 — AI UI với model/metrics/download/ảnh import API thật.
- [ ] R14 — 15 video EOF, quality report và regression/browser tích hợp.
- [ ] R15 — Hai camera 30 phút/12 giờ, ≥300 lượt có nhãn và KPI.
