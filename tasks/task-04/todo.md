# TASK 4 — Checklist tiếp quản và nghiệm thu

Trạng thái khởi tạo: **chưa thực thi Task4**. Codex chỉ tạo bộ bàn giao/prompt; không gửi tới Task1/2/3 và không tạo chat mới.

## Tiếp quản
- [ ] F4.0 Đọc HANDOFF/plan/prompts mới, ghi git/status/config snapshot.
- [ ] Lập STATUS_BOARD theo reported/verified/reproduced/pending, dedup lỗi cũ.
- [ ] Xác định kênh/identity Task1/2/3 thật hoặc quản qua docs/dispatch; không đoán đã gửi.
- [ ] Ghi ownership/fileclaim/dependency trong INTEGRATION_LEDGER; không sharedwriter trùng.

## Blocker và bàn giao
- [ ] F4.1 Task3 feedback contract không dùng expected_version echo làm savedversion.
- [ ] Task3 worker process_once thực ba target không TypeError; waiting/cancel/status đúng.
- [ ] Task3 promotion rejects queued/invalidartifact/quality0/provenance sai; baseline/runtime ack rõ.
- [ ] Task3 evaluator/trainer/operation/UI status đúng; runner train thật chưa có phải báo rõ.
- [ ] F4.2 Task1 preview runtime blockAI nhiều frame/JPEG vẫn tiến.
- [ ] Task1 rear/model/temporal/media/audio/card đúng hành vi.
- [ ] Task2 UI mock đủ, API/browser/media/quyền/productionQA thật.
- [ ] Checkpoint: owner tests/log/patch cập nhật, Task4 kiểm độc lập blocker, nhậnsharedpatch đúng.

## Tích hợp và regression
- [ ] F4.3 Feedback→collector→asset/label→datasetUI đạt qua API thật.
- [ ] Correction/version/exportimport/freeze/split đạt roundtrip ảnh thật.
- [ ] UIjob→worker→operation/status/metrics/candidate gate đạt; lifecycle sạch.
- [ ] F4.4 Fullbackend freshprocess QA không ignore/deselect, skip quantrọng đã xử lý.
- [ ] Node/lint/build/browserUI mock/APIintegration/productionroutes cuối đạt.
- [ ] Logs đầy đủ runID/exit/snapshot/modelhash/config; aborted/superseded không tínhPASS.

## Video, dữ liệu và thiết bị
- [ ] F4.5 Runtimewhole timeline tranning inventory/EOF/coverage thực.
- [ ] Hai nguồn30phút 1/2/3viewer và budgetFPS/p95/resource đúng nghĩa.
- [ ] Người dùng có UI/crop để label; datasettrain/val/test độc lập, đủ/chưa đủ ghi thật.
- [ ] Trainer optimization/checkpoint thực và baselinecandidateholdout được đo khi có tài nguyên.
- [ ] CameraImou/LAN/12h/reconnect/RPO/RTO nghiệm thu hoặc PENDINGHARDWARE cụ thể.

## Đóng và resume
- [ ] F4.6 Báo cáo tổng software/quality/hardware tách riêng, không fakeDONE.
- [ ] EXECUTION_LOG/ACCEPTANCE_REPORT/STATUS_BOARD cập nhật và NEXT_ACTIONS đủ resume.
- [ ] Không còn softwareblocker bị che bằng “testxanh”, “fixturetaskkhác”, “chờlabels”.

Mỗi mục đánh x phải có log/test/ảnh/sốđo thích hợp; marking checklist không thay chứng cứ.
