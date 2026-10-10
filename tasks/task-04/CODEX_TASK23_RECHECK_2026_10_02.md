# Codex đối chiếu báo cáo Task 2–3 sau PRE_INTEGRATION_FIX

Ngày: 02/10/2026. Repository: `D:/Work/Project_motorbike`.

Đây là bổ sung bàn giao cho Task 4, không thay STATUS_BOARD/NEXT_ACTIONS mà Task 4 đang giữ. Codex chỉ đọc mã, chạy QA cách ly và viết tài liệu này; chưa áp hook/lifespan hay sửa application code. Không liên hệ hoặc gửi việc cho các phiên Cursor khác.

## 1. Kết quả kiểm tra độc lập

### Task 3

Chạy bằng `venv/Scripts/python.exe` trong process mới, cấu hình DB, media, training DB và BASE_DIR tạm; không mở camera hay nạp model vận hành.

- `app/tests/task03_helpers` + `app/tests/task03_closure`: **117 passed, 1 warning, 18.29 giây**, exit 0.
- Cờ QA: `TASK3_COLLECTOR_ENABLED=1`, `TASK3_TRAINING_WORKER_ENABLED=1`.
- QA root: `C:/Users/khucv/AppData/Local/Temp/codex-task23-review-enabled-n2qt38mq`.
- Lần đầu chủ động tắt training worker (`...ENABLED=0`) có 115 pass/2 fail vì hai test yêu cầu start worker; lần chạy lại bật đúng điều kiện QA đạt 117/117. Không coi hai lỗi cấu hình đó là regression production.

Đối chiếu mã xác nhận:

- `app/db.py::record_review_feedback` bổ sung `feedback_id` và `new_version` từ DB.
- Runner detector/helmet cùng signature với worker và trả `unsupported`; đã tránh lỗi gọi sai tham số.
- Có trường `operation`, `runner_type`, kiểm tra job completed và chất lượng tối thiểu mới.
- Contract hook v1.2 và lifespan v1.1 đã được viết.

**Chưa tích hợp:** `app/api/recognition_reviews.py::post_feedback` chưa gọi `on_feedback_recorded`; `app/main.py` chưa có start/stop collector/training worker. Không đánh dấu luồng feedback → dataset → worker đã chạy trong ứng dụng chỉ vì test helper đạt.

**Chưa có training thật:** `worker.py::_run_detector_job` và `_run_helmet_job` vẫn là placeholders `unsupported`; OCR runner vẫn evaluator baseline. Đây là khả năng phần mềm còn thiếu, tách riêng với thiếu dữ liệu nhãn. Không chỉ ghi PENDING_DATA rồi tuyên bố trainer đã xong.

### Task 2

Mã `app/config.py::SNAPSHOTS_DIR` đã đọc env, sửa đúng nguyên nhân QA copy media thật. Codex chưa chạy lại toàn bộ Task 2/browser trong lượt này; các số 91/29/26/21 và lint/build là **kết quả chủ task báo cáo**.

Browser suite mới dùng login/API thật là tiến bộ. Tuy nhiên, source không chứng minh toàn bộ phạm vi trong phần mô tả báo cáo:

- `test_browser_integration.spec.js` gọi `/admin/violations` trên **BASE_URL 5187**. `vite.qa.config.js` không proxy `/admin`, nên HTML 200 này do Vite dev fallback; chưa kiểm backend phục vụ frontend build khi production refresh/deep link.
- Media test chỉ gọi file không tồn tại, chấp nhận 403 hoặc 404. Chưa chứng minh người đúng quyền nhận ảnh thật 200 và clip Range 206/phát/tua, người khác lớp bị từ chối.
- Bộ integration vẫn stub GuardPage recognition/video/audio và thay WebSocket. Nó không nghiệm thu realtime camera/âm thanh.
- Không có case CSV/import hay upload ảnh hợp lệ chạy xuyên luồng trong spec 21 test vừa đọc. Unit/API test khác có thể bao phủ, nhưng phải ghi đúng nguồn bằng chứng.
- Kiểm claim lớp cho phép `null`; kiểm management read cho phép cả 200 và 403; kiểm public registration cho phép 403 và 503. Cần assertion theo contract cụ thể ở những luồng được dùng làm nghiệm thu, không chỉ nhận một trong hai kết quả.
- Test backup/run hiện chỉ kiểm key `complete` tồn tại; cần assert hoàn tất thật và restore DB cùng media fixture, không chỉ DB-only/empty-media.
- Báo cáo 37 backup test cũ và 29 test mới khác số lượng; Task 4 đối chiếu collection/log để giải thích, không tự kết luận bỏ test hay coi số cũ là kết quả lượt mới.

Không coi server dev bị dừng sau test là production regression nếu log chứng minh nó phục vụ bình thường; cũng không coi thông báo server alive trước đây là trạng thái hiện tại.

## 2. Promotion chưa đóng: probes qua helper thực

Codex gọi trực tiếp các helper trong `app/training/promotion.py`, dùng file tạm và stub DB cho trường hợp metadata; không đụng registry vận hành. Kết quả sau bản P1–P4:

| Probe | Kết quả thực | Cần xử lý |
|---|---|---|
| `_verify_counted_test({'total':30,'f1':0.99}, 'plate_ocr')` | ACCEPTED | Metric bắt buộc theo đúng target; thiếu `exact_match_pct` phải từ chối |
| `_verify_counted_test({'total':30,'exact_match_pct':NaN}, 'plate_ocr')` | ACCEPTED | Reject NaN/Infinity, sai kiểu, ngoài miền; số mẫu phải số nguyên hợp lệ |
| `_verify_job_completed` với state completed, runner_type=None, operation=evaluate_baseline | ACCEPTED | Require operation=train và runner_type train được hỗ trợ; không chỉ reject một chuỗi evaluate_baseline |
| `_verify_metrics_provenance` với file metrics tồn tại nhưng thiếu model_sha256/dataset_id | ACCEPTED | Liên kết provenance bắt buộc, đối chiếu candidate/job/dataset snapshot/hash/target/holdout |
| `_verify_artifact` với file 256 byte toàn zero | ACCEPTED | Helper chỉ kiểm đọc/size, chưa kiểm loadability dù docstring nói có; xác minh load/mapping/inference trong QA trước khi công nhận model dùng được |

Probe root: `C:/Users/khucv/AppData/Local/Temp/codex-promotion-provenance-probe-engjpiof`.

Đây là kết quả **từng helper**, chưa phải phép thử full `promote()` cho mọi tổ hợp và chưa chứng minh model giả được runtime áp dụng. Task 3 cần bổ sung test xuyên toàn hàm promotion/DB cho các tình huống trên để chứng minh không lên `pending_runtime`/eligible sai. Runtime phải tiếp tục giữ model cũ nếu load candidate thất bại.

Ngưỡng detector precision 0.5/helmet F1 0.5 không thay tiêu chí cảnh báo loa precision ≥95% từng loại trên lượt xe rõ. Tách eligibility thử nghiệm/review khỏi quyền bật cảnh báo vận hành; báo recall, cỡ tập test và coverage riêng.

## 3. Việc giao tiếp theo, theo ownership hiện có

1. **Task 3:** vá validation promotion theo bảng trên; test helper và toàn promote, gồm thiếu/sai/NaN, job evaluate/unknown runner, provenance thiếu/mismatch và artifact không load được. Cập nhật báo cáo: evaluator/unsupported/trainer thật tách rõ. Bổ sung đường training thật có optimization + checkpoint + holdout trước khi gọi luồng học từ feedback hoàn tất; nếu thiếu dữ liệu thì runner được chứng minh bằng bộ QA nhỏ, khả năng nhận diện thực giữ PENDING_DATA.
2. **Task 1:** áp hook v1.2 sau DB success, chỉ khi applied và không replay; nhận feedback_id/new_version đúng. Test HTTP qua app thật, conflict/replay/queue đầy và lỗi worker không phá feedback. Sửa case cards còn fail và kiểm preview runtime không đứng khi AI/OCR bị chặn.
3. **Task 2:** áp lifecycle collector/worker có giới hạn shutdown, env vận hành inference-only không tự chạy training. Test start/stop lặp và không nhân worker. Bổ sung production backend deep link, ảnh/crop/clip thật đúng/sai quyền, Range, backup restore có media nhỏ và assertions theo contract; giữ chiến lược đăng nhập tự điền hiện có.
4. **Task 4:** ghi nhận tiến bộ, kiểm độc lập các blocker mới, sửa trạng thái trong bảng của mình; tích hợp một writer mỗi shared file rồi chạy full backend fresh process, Node/lint/build, browser mock + API thật + production. Không tiếp tục dùng danh sách 9 fail lịch sử làm nguyên nhân hiện tại khi chưa chạy lại.
5. Sau software ổn định: runtime thật toàn timeline video tranning, hai nguồn 30 phút và bộ nhãn holdout. Camera thật 12 giờ/LAN/độ chính xác phải có số đo riêng trước nghiệm thu.

Không hạ tiêu chí, không đổi model/camera/DB/media vận hành, không sửa chồng các file Task 4 hoặc task khác đang giữ. Task 4 có thể điều phối phần độc lập ngay; không cần người dùng chọn lại A/B/C hoặc hỏi tiếp tục mỗi checkpoint.
