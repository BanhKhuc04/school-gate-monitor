# Đối chiếu Task 1 Final Closure — còn blocker preview

Ngày: 02/10/2026. Bổ sung cho Task 4, đọc sau `CODEX_TASK23_RECHECK_2026_10_02.md`.

Codex chỉ đọc mã, chạy nguồn giả/QA cách ly và ghi tài liệu. Chưa sửa application code, chưa gửi yêu cầu tới phiên Cursor khác, chưa đổi camera/model/DB/media vận hành. Không ghi đè bảng trạng thái Task 4 đang giữ.

## 1. Kết luận

Hook và lifecycle tích hợp đã có trong mã hiện tại. Nhưng không xác nhận C1 “preview độc lập AI” đã hoàn tất: phép thử chạy `_run_loop()` thật cho thấy JPEG không tăng khi detector Future chưa hoàn tất. Đây là blocker phần mềm, không phải thiếu camera thật hay nhãn.

## 2. Những phần đã kiểm tra

### Log full backend

`tasks/task-01/full_result.txt` kết thúc:

> 1055 passed, 1 deselected, 3 warnings in 838.47s (0:13:58)

`tasks/task-01/ACCEPTANCE_REPORT.md` ghi test bị loại là `test_system.py::test_cleanup_admin_ok`. Vì vậy bản tóm tắt “full backend, tất cả test” chưa mô tả đúng lượt chạy. Codex không chạy lại full suite trong lượt đối chiếu này.

Codex chạy riêng test cleanup bị loại bằng venv, DB/media/BASE_DIR tạm trên ổ D:

- `test_system.py::test_cleanup_admin_ok`: **1 passed, 1 warning in 0.71s**, exit 0.
- QA root: `D:/Work/Project_motorbike/tasks/task-04/codex-task1-cleanup-z9j406uk`.

Đây là bằng chứng lỗi cleanup lịch sử không tái hiện trong phép thử riêng hiện tại. Chưa chứng minh isolation khi chạy chung; Task 4 cần đưa test trở lại full suite sau tích hợp và không dùng lý do cũ để deselect tiếp.

### Tích hợp Task 3

`app/api/recognition_reviews.py::post_feedback` đã có hook:

- Sau `record_review_feedback`, xử lý conflict trước enqueue.
- Chỉ gọi khi `applied` và không `idempotent_replay`.
- Dùng `feedback_id`, `new_version`, `review_id`, `source`.

`app/main.py::lifespan` đã có start/stop collector và training worker. Các mục “chưa có hook/lifespan” trong bản bàn giao trước trở thành lịch sử tại snapshot này, không giữ là blocker mã chưa viết.

Vẫn cần test HTTP/lifecycle qua app factory thật: feedback → asset/label dataset, replay/conflict/queue đầy, start/stop lặp, shutdown có lỗi. Có mã chưa đồng nghĩa luồng tích hợp đã nghiệm thu. Không khởi động pipeline RTSP thật khi kiểm các luồng này.

### Dung lượng

Tại lúc Codex kiểm tra:

- C: free 34,920,181,760 byte (~32.5 GiB).
- D: free 38,971,580,416 byte (~36.3 GiB).

Thông báo C: 0 GB thuộc thời điểm cũ; không còn đúng ở snapshot kiểm tra này. QA vẫn phải dùng DB/media/basetemp riêng và không copy hàng loạt chứng cứ thật. Codex không dọn/xóa dữ liệu trong lượt này.

## 3. C1 chưa đạt — source và test

`VideoPipeline._run_loop()` vẫn thực hiện cùng một vòng:

1. Đọc frame, tăng `_frame_seq`.
2. Encode/publish JPEG.
3. Submit detector.
4. Chờ `person_future.result()` rồi các Future khác, sau đó mới trở lại bước đọc frame tiếp theo.

Di chuyển publish lên trước `.result()` giúp phát được frame hiện tại sớm hơn; không làm các frame kế tiếp tiếp tục được encode lúc AI còn chạy. Nguồn capture có thể tiếp tục nhận hình, nhưng viewer vẫn nhận JPEG cũ.

Hai test mới mang tên behavioral trong `test_task01_F01_F02_runtime.py` tự viết vòng `read → publish → sleep/result`, không chạy `_run_loop` thật:

- Test detect nhận 3 JPEG sau ba lần chờ 2.5 giây; không assert JPEG mới trong khoảng detector đang bị chặn.
- Test OCR nhận 3 JPEG sau khoảng 6 giây và assert tổng thời gian ≥5 giây; không chứng minh preview tiếp tục tiến trong các khoảng chờ đó.

Hai test structural/source order cũng chỉ chứng minh thứ tự câu lệnh. Các test này có thể xanh dù hành vi mục tiêu vẫn sai; không dùng chúng làm bằng chứng C1 đạt.

## 4. Phép thử runtime độc lập

Codex dựng pipeline qua helper `_bare_pipeline('full')`, thay duy nhất nguồn và detector/pool để không nạp model hay camera thật:

- Nguồn giả có producer thread liên tục cập nhật ảnh khoảng 30 FPS.
- Chạy **`p._run_loop()` thật** trong một thread, `FRAME_SKIP=1`, `camera_switch=None`.
- Submit person detector trả Future chưa hoàn tất; detector khác trả Future đã có kết quả.
- Đợi tới khi detector được submit, lấy snapshot, giữ Future chưa hoàn tất thêm 1 giây rồi lấy snapshot tiếp.

Kết quả thực:

| Chỉ số | Trước chặn | Sau 1 giây |
|---|---:|---:|
| Frame nguồn | 1 | 28 |
| Số lần pipeline đọc nguồn | 1 | 1 |
| `_frame_seq` pipeline | 1 | 1 |
| `_jpeg_new_count` | 1 | 1 |

`PREVIEW_ADVANCED_DURING_BLOCK=False`. Sau phép thử, bỏ chặn Future và dừng/join thread thành công (`LOOP_STOPPED=True`). Không có thread QA cố ý giữ lại. QA root: `C:/Users/khucv/AppData/Local/Temp/codex-task1-loop-probe-tnju0ibn`.

Đây là tái hiện blocker runtime bằng nguồn giả, không phải số đo FPS trên Imou hoặc benchmark toàn ca.

## 5. Việc giao Task 4 và owner Task 1

1. Mở lại C1, không ghi Task 1 đã hoàn tất preview. Owner runtime sửa tách luồng publish preview khỏi AI chờ Future, hoặc cơ chế nonblocking lấy kết quả trong luồng preview; dùng latest-frame slot hữu hạn, không thêm queue frame cũ.
2. Frame/result giữ camera_id, source_epoch, frame_seq/time; overlay có TTL. Không mất track/ledger/crossing, không trộn crop frame cũ/mới hoặc tự giảm chuẩn xác nhận.
3. Viết test gọi loop/runtime thật: chặn AI 2–3 giây trong khi nguồn liên tục phát frame, assert nhiều JPEG/frame_seq mới **trước khi thả detector**, kiểm get_jpeg và tuổi frame. Test tương tự với OCR chậm, hai camera và nhiều viewer. Cleanup mọi thread/pool khi test kết thúc.
4. Không sửa assertion sang “publish trước submit”, không mô phỏng lại một loop khác rồi coi là test production.
5. Sau sửa, cùng Task 4 chạy full backend không ignore/deselect trên snapshot thống nhất, Node/lint/build và browser thật. Xử lý độc lập validation promotion và các thiếu hụt media/production trong `CODEX_TASK23_RECHECK_2026_10_02.md`.
6. Chạy toàn timeline video tranning qua runtime thật và hai nguồn 30 phút trước khi nghiệm thu Imou 12 giờ. Các số video 60 giây/harness cũ không thay phép đo sau bản sửa này.

Task 4 cập nhật STATUS_BOARD/INTEGRATION_LEDGER/NEXT_ACTIONS của mình: hook/lifespan có mã; C1 còn REPRODUCED; cleanup test riêng PASS; full tích hợp cuối PENDING. Giữ một writer mỗi file, không sửa chồng hoặc đổi cấu hình vận hành để làm QA.
