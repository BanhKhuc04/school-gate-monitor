# Checklist đợt 6 — bàn giao trước 01:00 ngày 04/10/2026

Đây là checklist triển khai tiếp theo, **chưa đánh dấu nghiệm thu**. Giữ lịch
sử Task 1–5; đối chiếu mã và báo cáo mới trước khi nhận việc.
Plan: [PLAN_BEFORE_0100.md](PLAN_BEFORE_0100.md).
Prompt thực thi: [NEXT_CURSOR_PROMPT.md](NEXT_CURSOR_PROMPT.md).

Mỗi dòng đạt cần ghi path bằng chứng, timestamp UTC+7, commit/tree/config/
weights hash, người kiểm; mock/video/camera/âm thanh/VPS tách riêng.

## Preflight — ngay nhận prompt tới 22:45

- [ ] D0a — A/B: cập nhật state board từ diff/process/R0–R15; sửa kết luận vượt phạm vi test. Full R8–R9 1.277 pass/2 skip không thay regression sau sửa mới.
- [ ] D0b — B: quota và QA isolation, D sau output ≥30 GiB; C/temp/cache kiểm thật; không backup media hoặc tải model khi test.
- [ ] D1a — A: hai RTSP LAN, IP/ROI/vạch, camera/loa sẵn; metadata che credentials. Reconnect/source epoch không phát cũ.
- [ ] D9a — B: SSH read-only VPS 103.101.162.111, OS/resource/domain/TLS/service; ghi access thực, không giả định từ README.

## P0 runtime và audio — tới 23:05

- [ ] D1b — A, sau D1a: camera focus/ánh sáng/exposure/góc đúng; crop native; WAN-off camera reboot vẫn mở được.
- [ ] D2a — A + người duyệt: 30–50 lượt có GT độc lập, cả ca khó/negative; ground truth không lấy prediction.
- [ ] D2b — A: vote ≥2 frame độc lập, tối đa 5 crop/2 giây; raw/char confidence/hash/track/camera/epoch xuyên consensus, mâu thuẫn cần duyệt.
- [ ] D2c — A: CCT ONNX/YAML thật và EasyOCR so cùng crop nếu đủ GT; không coi recognizer mock là smoke model. Chốt baseline/reader trước 23:05.
- [ ] D3a — A: luật mũ/số người/tư thế theo bằng chứng; unknown/review; one encounter/multi-issue/late update không duplicate.
- [ ] D3b — A: không ép whitelist/gán học sinh khi biển yếu; auto-match trước/sau tắt khi chưa hiệu chỉnh; xe điện không đoán từ COCO.
- [ ] D4a — B, contract từ A: nối AlertBanner live với filter/dedup/finalized/evidence/audio_authorized; UUID lease/renew/release, split view cả hai camera.
- [ ] D4b — B: một beep/câu ngắn, queue/TTL bounded; 2 viewer chỉ 1 speaker; reconnect/late plate không đọc lại.
- [ ] D5a — B: giọng Việt local hoặc clip local tự chọn từ issue thật; nghe loa khi WAN tắt; readiness/gesture/onstart/onerror rõ.
- [ ] D6a — B: local production assets/API/auth/media, bỏ CDN/fonts online, một process không reload; cold browser/lazy route chạy offline.

## Checkpoint tích hợp — 23:05–23:25

- [ ] Focused tests theo phần sửa; frontend Node/lint/build đạt, warnings phân loại.
- [ ] Full regression đúng bản tích hợp, exit code/report rõ; chỉ một full suite hoặc GPU benchmark.
- [ ] D7a — A: runtime AI thật trên 15 clip đến EOF theo thời gian thực; không dùng decode-only để đánh dấu AI/preview đạt.
- [ ] D7b — A/B: hai nguồn, browser/API thật, plate/crossing/audio/evidence, source switch/replay/IO fail; không gọi hai clip độc lập là ghép trước/sau.
- [ ] Metrics mới: preview frame mới/AI FPS từng camera, queue/age/OCR/encode/CPU/VRAM, plate/beep/speech latency và n thật.

## Camera, VPS, trình bày — 23:25–23:55

- [ ] D7c — A + operator: 30 phút hai camera thật, WAN-off/cold refresh/loa/1–3 viewer/reconnect, drift tài nguyên và disk; GT expected/observed.
- [ ] D8 — B: landing đúng release, responsive/local assets/CTA hoạt động; bỏ claims không đo, face/form giả; không public PII.
- [ ] D9b — B, sau D9a: deploy nhẹ có URL/health/version/rollback; portal auth/TLS đạt. Không Torch/YOLO trên VPS.
- [ ] D9c — B, sau contract A: sync nếu đã có/đủ giờ kiểm; idempotency/order/auth/WAN recovery. Chưa qua 23:20 giữ pending, snapshot có timestamp.
- [ ] D10a — B: PPTX 12 slide (8 chính/180 giây +4 Q&A), PDF/notes; số đo và trạng thái từ bản freeze, rà đủ slide.
- [ ] D10b — B: video backup có tiếng ≤150 MiB, nguồn thật/nhãn ghi trước; runbook 420 giây và fallback rõ.

## Khóa và bàn giao — 00:00–00:50

- [ ] 00:00: khóa code/config/weights; sau mốc chỉ sửa blocker nhỏ đã kiểm hoặc revert, không mở feature/dependency mới.
- [ ] D6b/D11a — A/B: START/STOP/ROLLBACK, cold start đúng build không download/seed; backup/restore fixture nhỏ, giữ dữ liệu mới.
- [ ] D10c — operator/presenter: 2 lượt tổng duyệt 180+420 giây, có WAN-off/cold browser/loa thật; không sai gán/lỗi/đọc lặp quan sát được.
- [ ] D11b — A/B: package ≤600 MiB, slide/render ≤100 MiB, manifest hashes/env.example không secret; D ≥30 GiB.
- [ ] D11c — A/B: FINAL_ACCEPTANCE/VPS_STATUS/RUN_LOCAL_OFFLINE/DEPLOY_VPS, pending có owner; URLs/slide/file mở được từ bản bàn giao.
- [ ] 00:50: giao lệnh chạy + package + PPTX/PDF + runbook + URL thực; giữ 10 phút đệm, hoàn tất trước 01:00.

## Gate giữ mở nếu chưa đủ dữ liệu hoặc thời gian

- [ ] ALPR ≥95%, coverage ≥90%; báo riêng điều kiện khó trên holdout độc lập.
- [ ] Mũ precision ≥98%/recall ≥95%; hành vi/số người ≥95%/≥90%.
- [ ] Không gán nhầm học sinh trong holdout ≥300 lượt; công bố n/lỗi.
- [ ] Ca hai camera 12 giờ và full media restore thực.
- [ ] Dataset mũ/xe điện đủ nhãn; Kaggle training thật và YOLO11 weights đạt benchmark/promotion/rollback.
- [ ] VPS/sync production/TLS/quyền/endurance đạt toàn bộ phạm vi đã yêu cầu.

Không lấy ca demo nhỏ thay KPI dài hạn. `demo_ready` cần các gate demo thực;
`production_complete` cần cả gate dài hạn. Phần chưa đạt phải ghi rõ, tiếp tục
làm các phần độc lập, không đóng toàn bộ dự án bằng suy đoán.
