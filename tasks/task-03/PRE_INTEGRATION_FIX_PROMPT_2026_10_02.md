# TASK 3 — Vá trước tích hợp và bàn giao kiểm thử xuyên luồng

Review 02/10/2026: Codex chạy lại hai thư mục `app/tests/task03_helpers` và `app/tests/task03_closure` trong DB/media/assets/config QA riêng bằng venv: **92 passed, 1 warning, 17.81 s**. Không sửa model/camera/data vận hành. Test mới đã cải thiện đáng kể; không triển khai lại phần đúng. Các phép thử bổ sung dưới đây vẫn phát hiện blocker.

## 1. P1 — Chốt hook feedback đúng nghĩa, không áp patch expected_version

`db.record_review_feedback` tính `new_version=current_version+1` và commit, nhưng response `expected_version` vẫn echo input client. Ví dụ client gửi 5, review được cập nhật thành 6, response expected_version vẫn 5. Do đó câu “expected_version là version được cập nhật thành” trong contract sai.

Contract còn chứa ví dụ `result.get('version',0)` và return `result['version']` dù field không có; cần bỏ các ví dụ trái nhau. Không sửa bằng expected_version+1: server có thể chưa validate future version đúng invariant, không lấy input client làm version đã commit.

Chốt enqueue bằng **review_id + feedback_id thực đã lưu** làm định danh event. Worker lấy review.version thực từ adapter/DB để so cursor và lưu nhãn mới nhất. Nếu cần saved_version explicit, bàn giao Task 1/Task 2 patch additive trả `new_version` đã commit theo contract nhất quán; không dùng echo expected_version.

- Task 3 cập nhật hook signature/event/tests/FEEDBACK_HOOK_CONTRACT; Task 1 là writer áp hook ở API sau save thành công và sau kiểm conflict.
- Replay cùng feedback_id không nhân sample; event mới cùng review lấy version mới đúng. 409/save fail không phát event thành công.
- Gọi hook trước lifespan phải False có diagnostics/reconciliation, không tạo singleton tạm hoặc I/O trong request.
- Test qua API thật: input expected=5, DB mới=6; replay; sửa lần hai; stale409. Không chỉ test dict tự dựng.

## 2. P2 — Worker dispatch sai chữ ký

Phép thử thật tạo job `plate_detector` rồi gọi `TrainingWorker._process_once()` trên DB tạm:

```
state=failed
TypeError: _run_detector_job() got an unexpected keyword argument 'dataset_id'
```

Worker gọi mọi runner bằng dataset_id/job_id/target, trong khi placeholder detector/helmet nhận `(job, db_path)`. Thống nhất một runner interface; adapter OCR chuyển từ job sang tham số riêng ở đúng một chỗ. Detector/helmet chưa triển khai phải trả unsupported đúng, không failed do TypeError.

Test `_process_once()` thực với ba target và DB QA: OCR pending_data/evaluated đúng; detector/helmet unsupported đúng cho tới khi có trainer thật. Kiểm waiting resume qua worker, cancel/start/stop và không nhân thread sau lifecycle lặp. Test chỉ kiểm module_exists/_select_runner callable chưa bảo vệ dispatch.

## 3. P3 — Promotion còn bỏ qua chất lượng và provenance

Hash thực đã được kiểm tốt hơn. Tuy nhiên phép thử candidate có file 128 byte không phải model, hash SHA256 đúng, job còn queued, metrics file có 30 mẫu/OCR 0% vẫn promote thành `pending_runtime` khi không có baseline.

- Số byte tối thiểu và hash đúng không chứng minh file loadable; kiểm engine/model metadata/mapping/runtime compatibility thật bằng QA contract.
- Training candidate cần job đã hoàn thành optimization thật, evaluation server liên kết model/dataset/config/hash/holdout. Baseline evaluator không trở thành trained candidate chỉ vì completed.
- Gate theo target: OCR exact toàn biển tối thiểu 50% trên ít nhất 30 biển rõ và các tiêu chí baseline/latency đã chốt. Không baseline thì cần gate tuyệt đối và baseline độc lập phù hợp; không auto pass candidate 0%.
- Detector/mũ dùng chỉ số và số mẫu phù hợp, không dùng ngưỡng 30 OCR cho mọi target. Không tin metrics client hoặc file JSON không có provenance như evaluation độc lập.
- Fail apply giữ baseline; registry pending_runtime vẫn chưa applied. Rollback phải giữ baseline_id rõ và xác nhận runtime khi tích hợp.

Test job queued/failed, artifact không load được dù hash đúng, OCR 0%, metrics model/dataset khác, thiếu baseline, candidate hợp lệ QA. Không đặt tên artifact không có Smoke rồi coi đó là training thật.

## 4. P4 — Tách evaluator khỏi trainer và cập nhật bàn giao

`ocr_trainer.py` hiện đã ghi đúng `IS_EVALUATOR=True`: giữ điều này. Nhưng hệ thống chưa có OCR optimization trainer và detector/helmet còn placeholders. Không ghi “đã hoàn thành training” chỉ vì đổi marker/docstring; cũng không nói chỉ cần thêm nhãn thì model sẽ tự học khi chưa có runner train.

- UI/jobs có operation rõ `evaluate_baseline` và `train`; hỗ trợ operation nào thì hiển thị đúng. Training chưa có phải unavailable/unsupported, không gọi evaluation dưới nhãn training completed.
- Tiếp tục triển khai trainer thật theo FINAL_CLOSURE_PROMPT khi có engine/fixture phù hợp, môi trường tách biệt và GPU được bàn giao. Không tự nâng dependency/đổi model live hoặc chạy GPU chồng Task 1.
- Thiếu nhãn ảnh thật: chuẩn bị collector/editor/asset/dataset, hướng dẫn người dùng duyệt. Không fake accuracy. Smoke optimization/checkpoint riêng chỉ chứng minh plumbing.
- APP_LIFESPAN_PATCH hiện chỉ start/stop collector, chưa có training_worker như report. Cập nhật patch startup/shutdown cả hai và config QA/default enabled rõ; không tự start training trong ca camera vận hành chỉ vì app khởi động.
- Task 2 áp lifecycle sau review và chạy factory QA thật. Task 1 áp hook sau P1. Không sửa chồng shared file.

## 5. Sau bản vá: luồng QA và dữ liệu người dùng

1. Task 1/2 áp shared patches đã kiểm; startup/lifespan init training DB/worker và shutdown sạch trong QA.
2. Browser/API thật: review crop → đúng/sai/sửa chữ → collector lưu asset/label/version → dataset draft → export/import qua root khác → freeze/split → job evaluate/train có operation đúng → trạng thái/metrics/candidate → promotion gate.
3. Khi ảnh/label còn thiếu, người dùng duyệt ít nhất 30 biển rõ khác nhau cho tập đánh giá OCR; dữ liệu training và validation phải riêng, không train lại holdout rồi gọi đó là test độc lập. 50 violation/50 clean dùng nghiệm thu cảnh báo, không thay nhãn OCR.
4. Task 3 bàn giao Task 2 chạy full backend không ignore/deselect, Node/lint/build và browser integration sau snapshot ổn định. Task 1 tiếp tục benchmark video/runtime hai nguồn theo scope riêng.

## Checklist đóng đợt

- [ ] P1 hook không dùng echo expected_version, API integration test đạt.
- [ ] P2 worker thực dispatch mọi target đúng chữ ký/trạng thái.
- [ ] P3 promotion kiểm provenance/quality/model thật, không candidate 0% hoặc job queued.
- [ ] P4 evaluator/trainer/lifespan patch/UI status nhất quán.
- [ ] QA xuyên luồng đã đạt và handoff Task 1/2 cụ thể.

Giữ lịch sử test 92 xanh và thêm test bắt lỗi mới, không giảm assertion/skip. Đính chính các mục acceptance còn PARTIAL, thiếu engine/nhãn/thiết bị ghi rõ. Thực thi liên tục trong scope, không hỏi tiếp tục sau mỗi bước. Không push/deploy, xóa dữ liệu/model/log người dùng hoặc đổi nguồn camera vận hành.
