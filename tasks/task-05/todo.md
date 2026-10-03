# Backlog đợt 5

Trạng thái: `mã` / `focused test` / `video` / `camera thật` là bốn bằng chứng khác nhau.
Không thay checkbox Task 1–4 cũ bằng kết quả suy đoán.

- [ ] T0: bảng đối chiếu tiến độ và process; video 15 clip đã có, blocker thiếu video cũ hết hiệu lực.
- [ ] T1a: cleanup có manifest, bỏ artifact staging, ignore; D ≥30 GB.
- [ ] T1b: QA/test DB/media/training/backup/cache riêng và quota.
- [ ] T2a: capture worker latest-only và preview không chờ 100 ms.
- [ ] T2b: source/reconnect/stop epoch, test chặn AI 3 giây.
- [ ] T3a: GPU owner, pose singleton, bulk tensor copy, timing đủ detector.
- [ ] T3b: baseline 2 nguồn, CPU/VRAM/queue/OCR/encode; lựa chọn model dựa số đo.
- [ ] T4a: ByteTrack rear và reset per source/camera.
- [ ] T4b: 5 crop/2 giây, metadata bất biến, 2 frame đồng thuận.
- [ ] T5a: OCR contract, adapter CCT và tối đa 2 biến thể/crop.
- [ ] T5b: so sánh EasyOCR/CCT cùng holdout, promotion có runtime xác nhận.
- [ ] T6A: audit nhãn/dedup/hash/group splits và thu nhãn mũ/xe điện.
- [ ] T6B: notebook YOLO11 biển, mũ/xe điện, CCT; checkpoint/resume/artifact manifest.
- [ ] T7: luật/encounter/late issues/cross-camera ambiguity; auto-match tắt.
- [ ] T8: menu/quyền/deep link/AI hub/bbox theo mẫu/debug overlay.
- [ ] T9a: regression và browser/API thật.
- [ ] T9b: 15 video tới EOF theo thời gian thực.
- [ ] T9c: camera 30 phút/ca 12 giờ, holdout ≥300 lượt và KPI.

## Nhật ký

03/10/2026: bắt đầu triển khai trên branch riêng, giữ thay đổi chưa commit hiện có.
Baseline audit: Torch 2.6.0+cu124/CUDA hoạt động; Ultralytics 8.2.103;
59 focused test đạt; regression trước có lỗi bảng datasets; chưa chứng minh KPI.
