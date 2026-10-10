# TASK 3 — Review closure và sửa các hành vi chưa được test bảo vệ

Ngày: 02/10/2026. Đây là phần bổ sung cho FINAL_CLOSURE_PROMPT, không thay kế hoạch cũ. Đối chiếu mã mới trước khi sửa; các task khác có thể đang chỉnh tiếp.

## 1. Kết luận review

Codex đã chạy lại `app/tests/task03_helpers` + `app/tests/task03_closure` bằng venv trong QA root riêng: **67 passed, 1 warning, 23.78 s**. Các config DB/media/training/assets được tách khỏi vận hành. Không chạy GPU/model/camera thật.

Các test xanh là có thật, nhưng chưa chứng minh E1/E4/E5/E6 đã đạt requirement. Không đóng E0–E7 toàn bộ. Giữ phần ZIP/import/export và guard đã sửa đúng; bổ sung test hành vi để bắt các lỗi dưới đây.

Run đầu với collector bị tắt cho một test enqueue thất bại vì test không tự thiết lập enabled. Run lại với collector enabled đạt 67/67. Không coi lỗi config thử nghiệm đó là regression production; fixture nên tự set trạng thái collector để độc lập môi trường.

Các phép thử bổ sung dùng DB/media tạm riêng và không thay application code/model vận hành.

## 2. Phát hiện có bằng chứng

### T3-C01 — OCR trainer hiện là evaluator, chưa huấn luyện

`app/training/ocr_trainer.py::run_ocr_training_job` ghi rõ: “Đây KHÔNG phải training thật”, dùng EasyOCR pretrained inference holdout, trả `model_path=None` và không tạo trọng số. `epochs` không điều khiển optimization. Thiếu dữ liệu không phải nguyên nhân duy nhất khiến chưa có trainer: đường huấn luyện chưa được triển khai.

Sửa acceptance E5 thành evaluator baseline hoặc PARTIAL; không ghi “Trainer OCR thật DONE”. Đổi tên/operation rõ để UI không gọi inference là training. Triển khai runner OCR thực tương thích engine hoặc để tính năng training chưa khả dụng rõ ràng cho tới khi có runner. Smoke optimization thật có loss/optimizer/checkpoint loadable khác với lifecycle simulation; không dùng smoke làm bằng chứng accuracy.

### T3-C02 — Waiting job vẫn không resume

`jobs.run_training_job` vẫn chỉ nhận `queued` và từ chối `waiting_resource`. Phép thử chuyển queued→waiting rồi gọi runner trả `SchemaError: job ở state='waiting_resource' — không thể chạy`.

Test `test_waiting_state_can_resume` hiện chỉ kiểm `can_start_gpu_job()` và state trong tập hợp, không thực hiện resume.

Sửa runner/worker nhận waiting và claim nguyên tử; test phải tạo waiting, giải phóng tài nguyên, gọi worker/runner và quan sát job thực chạy. Giữ sửa queued không giữ lease. Bổ sung concurrent process/cross-target claim và cancel dừng runner thật, không chỉ đổi trạng thái DB.

### T3-C03 — Thiếu dữ liệu vẫn bị báo completed

Phép thử runner trả `{'state':'pending_data'}` cho thấy outer result và DB job đều `completed`. `run_training_job` bỏ qua trạng thái runner và luôn chuyển evaluating→completed.

Phân biệt evaluate-only/training và pending_data/unsupported/failed/cancelled/completed. Không hoàn tất training khi chưa có artifact hoặc chưa thực hiện optimization. State/API/UI phải phản ánh đúng result, có quy tắc resume khi dữ liệu đủ. Test runner pending_data/unsupported/cancel/error và completed có artifact hợp lệ.

### T3-C04 — Collector không khớp dữ liệu nguồn, cursor làm mất retry

Adapter hiện trả review dạng flat có `crop_media_id` và `crop_sha256`; collector chỉ đọc `review['source']`. Phép thử review flat trỏ ảnh PNG đang tồn tại cho `_copy_asset_if_needed=False`.

Sau reconcile, dù copy thất bại cursor vẫn tăng `{'flat':1}`; reconcile lần sau `updated=0`. Khi ảnh xuất hiện lại hoặc lỗi I/O hồi phục, version đó bị bỏ qua.

`_handle_event` còn so `latest_version <= ev.feedback_version` rồi coi đã xử lý, thay vì so version đã xử lý trong cursor. Event có version đúng bằng DB mới nhất bị skip; phép thử xác nhận `processed_skipped_existing=1`.

Chuẩn hóa adapter schema thật và media ID→asset qua quan hệ server. Chỉ ack/cập nhật cursor thành công sau asset và metadata/label đã lưu đúng, hoặc ghi trạng thái loại mẫu terminal có lý do. Lỗi retryable phải retry. So event với cursor bền vững, không coi version DB bằng event là processed. Collector hiện chỉ chuẩn bị `.bin`/cursor, chưa đưa nhãn vào draft/UI tự động; phải hoàn thiện hoặc báo PARTIAL rõ.

### T3-C05 — Reconciliation kẹt 64 dòng, hook lazy-init làm mất queue

Phép thử adapter trả 70 review: pass đầu scan/update 64, pass hai vẫn scan 64 nhưng update 0; cursor chỉ có 64 review. `items[:batch_max]` luôn lấy cùng trang đầu, không tiến tới các review sau.

Phép thử khi singleton chưa được khởi tạo: `on_feedback_recorded()` trả True nhưng `get_collector()` vẫn None. Collector vừa tạo là biến local, không được giữ vào singleton/worker; queue nhận event không có nơi xử lý. Constructor còn tạo thư mục/đọc cursor, trái contract hook không I/O.

Reconcile dùng pagination/cursor bền vững tiến hết lịch sử, không full scan hàng nghìn review mỗi event. Hook chỉ dùng collector đã được lifespan tạo; chưa sẵn sàng thì trả False có metric và để reconciliation thu lại. Không lazy-init I/O ở request và không báo enqueue True vào queue sẽ bị bỏ. Worker lỗi persist metrics/cursor phải được ghi và phục hồi có kiểm soát, không chết âm thầm.

### T3-C06 — Hook contract sai version

`record_review_feedback` hiện trả `feedback_id`, `expected_version` và status/applied; không trả `version`. Contract đề nghị `result.get('version',0)` hoặc `result['version']`: có thể enqueue version 0 hoặc lỗi bị `except pass` nuốt.

Task 3 đọc contract thật và bàn giao Task 1/Task 2 patch additive nếu cần saved_version/feedback_id chuẩn. Không coi expected_version gửi từ client là version mới. Save conflict/failed không enqueue; replay có định danh/version nhất quán. Test qua endpoint thật, không chỉ gọi hook với dict tự dựng.

### T3-C07 — Promotion vẫn chưa kiểm chứng hash/chất lượng/training provenance

`_verify_hash` chỉ kiểm chuỗi hash có giá trị, chưa tính SHA256 file và đối chiếu. Gate metrics mới chỉ xác nhận file có metric/count, không chứng minh metric thuộc artifact/dataset/config đó hoặc job đã train xong.

Phép thử candidate có file `not a trained model`, SHA256 sai (`0` lặp 64 ký tự), job còn queued và metrics OCR 0%/30 mẫu vẫn được chuyển `pending_runtime`. Đây là registry QA, chưa load camera; nhưng gate “đủ để áp dụng” đang sai.

Sửa gate fail-closed: artifact/hash thực, khả năng load/mapping/engine contract thực, training/evaluation operation đúng, job hoàn thành hợp lệ, evaluation server liên kết model/dataset/config hash và holdout, tối thiểu chất lượng tuyệt đối theo target. Client không được chọn file metrics hoặc ghi số giả. Không có baseline/evaluation hợp lệ không mặc định eligible. Không chỉ kiểm prefix model_class hoặc tên không chứa Smoke để xác định có training thật.

Giữ cải thiện pending_runtime; applied cần ack Task 1 thật. Rollback cần kiểm artifact/baseline pointer và runtime contract; không coi đổi DB state là đã đổi model camera. Báo cáo đang nói “retired cũ nhất”, mã chọn retired gần nhất trước current active; chốt baseline_id rõ, đặc biệt khi nhiều lần rollback.

### T3-C08 — UI tạo job chưa nối worker training

API create_job hiện ghi queued; chưa có worker gọi trainer thật từ job UI, ngoài CLI simulation. Collector worker không phải training worker. Router/menus có mặt không chứng minh feedback→dataset→train→candidate hoạt động.

Hoàn thiện lifecycle training worker và dispatch operation thực, coordinated GPU lease với Task 1, integration patch Task 2. Browser/API thật phải thấy job do UI tạo được worker xử lý hoặc waiting_reason đúng; không có simulation fallback production.

## 3. Thứ tự thực thi

1. Thêm test đỏ cho C02/C03/C04/C05/C06/C07. Sửa status/report E1/E4/E5/E6 về PARTIAL theo bằng chứng; giữ lịch sử 67 test xanh.
2. Sửa collector schema/cursor/retry/pagination/singleton và contract feedback. Không để Task 1/2 áp patch hiện tại có version sai/lazy queue lỗi.
3. Sửa runner state/resume/lease và promotion/provenance. Chặn candidate không đạt ngay; không auto load model live.
4. Nối API/UI worker; tách baseline evaluation khỏi training và triển khai trainer thực. Khi thiếu nhãn, test plumbing/optimization bằng fixture hợp lệ riêng và ghi quality PENDING_DATA. Không đánh dấu trainer hoàn thành vì evaluator chạy được.
5. Task 1 áp hook API sau save thành công theo contract mới; Task 2 áp lifecycle patch sau kiểm module an toàn. Một shared file chỉ một writer; không tự sửa chồng.
6. Test xuyên luồng bằng production factory QA: POST feedback→worker→draft có ảnh/nhãn→export/import→freeze→job→status/metrics/candidate→gate. Task 2 nhận bàn giao cho browser và full regression.

## 4. Kiểm thử bắt buộc bổ sung

- Review thực flat và media ID thật: copy/decode/hash đúng, label history/provenance vào draft.
- Equal-version event mới, replay, stale409, feedback sửa lần hai; không bỏ event vừa lưu.
- Hơn 64/200 review, queue đầy và restart: mọi review đủ điều kiện được thu; không kẹt trang đầu.
- Asset chưa có→asset xuất hiện; I/O fail→retry thành công. Không cursor-ack thành công giả.
- Hook trước lifespan/disabled/error; không tạo singleton tạm, không I/O trong hook, không enqueue True rồi mất event.
- Waiting→resource free→runner thật được gọi; concurrent claim/cancel/crash recovery.
- Runner pending_data/unsupported/evaluation-only không bị DB/UI báo training completed.
- SHA256 sai, artifact không load được, job queued/failed, metrics của model/dataset khác, OCR 0%/thiếu baseline, smoke marker bị thiếu: promotion đều bị chặn.
- Candidate đúng contract QA pass gates; rollback có baseline đúng và pending/applied ack rõ.
- Trainer optimization thật tạo checkpoint có hash/load được; inference evaluator không được gọi training.

## 5. Báo cáo và điều kiện đóng

Chạy focused rồi toàn Task 3 bằng `venv\Scripts\python.exe` với config/root DB/media/asset QA. Fixture tự set enabled/env và hoàn trả; không sửa dữ liệu/model live. Không ignore/deselect để giữ số test cũ. Test phải gọi hành vi đang bảo vệ, không assert “state thuộc tập queued/waiting” rồi gọi resume PASS.

Cập nhật todo/EXECUTION_LOG/ACCEPTANCE_REPORT/CONTRACTS, thêm lệnh/run ID/log và các phép thử mới. Ghi rõ **collector lưu asset/label đạt**, **training optimization đạt**, **holdout chất lượng đã đo**, **runtime applied đã xác nhận**. Thiếu nhãn/thiết bị là PENDING riêng; không dùng làm lý do chấp nhận bug collector/queue/promotion hoặc runner chưa có.

Tiếp tục phần độc lập, không hỏi lại sau từng đợt. Không chỉnh pipeline để thu feedback; không thay dependency/runtime model trên phiên camera đang chạy. Chỉ đóng software khi các test xuyên luồng mới đạt và shared patches đã tích hợp, không chỉ vì 67 helper tests xanh.
