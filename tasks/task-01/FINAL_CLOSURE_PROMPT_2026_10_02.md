# TASK 1 — Hoàn thiện runtime hai camera và bàn giao để đóng regression

Bạn tiếp tục TASK 1 trong repository hiện tại. Đây là yêu cầu thực thi, sửa và kiểm chứng đến khi phần khả thi hoàn tất; không chỉ đọc rồi đề nghị người dùng cho tiếp tục.

## 0. Hiện trạng và nguyên tắc

Đọc `plan.md`, `POST_VIDEO_REPAIR_PROMPT.md`, checklist/log/report Task 1 và `docs/CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md`. Đối chiếu mã mới trước khi sửa. Giữ toàn bộ thay đổi chưa commit; không stash/reset/clean, push, deploy hoặc tự thay camera/DB/media/model vận hành.

Hai camera Imou trước/sau cùng cổng vật lý; máy i7-12700H, RAM 16 GB, RTX 3050 Laptop 4 GB. Camera trước xử lý người/xe, mũ, đi xe/dắt bộ, crossing. Camera sau ưu tiên biển và OCR. Góc trước bên phải người lái không mặc nhiên thấy gương trái; gương vẫn review-only nếu chưa đủ góc nhìn/nhãn.

Các phép thử mới đã xác nhận crossing 3+3 và khoảng mất track 17 giây đúng. Cleanup admin đã PASS trong review. Backup/maintenance có log mới 37 passed. Không tiếp tục coi lỗi cleanup/backup lịch sử là blocker đang tồn tại nếu test hiện tại đạt.

Chỉ sửa file Task 1 sở hữu. Task 2 là integration owner cho các file shared sau bàn giao; Task 3 sở hữu collector/training. Đăng ký file shared và đọc lại diff ngay trước khi áp patch; một file chỉ có một writer. Không cần xin lại người dùng cho công việc đã giao. Khi chờ file/tài nguyên, tiếp tục phần độc lập.

## 1. C1 — Preview thật sự độc lập AI

Vấn đề cần đối chiếu: `_run_loop()` publish JPEG rồi vẫn chờ `person_future.result()` cùng vòng lặp. Đưa publish lên trước inference chưa bảo đảm frame kế tiếp tiến khi AI chậm. Test `test_blocking_detect_does_not_block_jpeg_publish` hiện kiểm source, không chạy loop.

Thực hiện từng lát nhỏ, test trước/sau:

- Capture riêng mỗi camera, giữ frame mới nhất với metadata thời điểm nhận, camera, epoch và sequence nguồn. Không tăng frame_seq giả khi đọc lại cùng frame capture.
- Publisher/display chạy độc lập AI/OCR/DB/clip; encode một lần mỗi frame hiển thị mới và dùng chung bytes cho viewer.
- AI lấy snapshot mới nhất, bỏ frame cũ; không dùng hàng đợi không giới hạn. Giữ ảnh nguồn nguyên bản riêng cho OCR/bằng chứng, bản thu nhỏ giữ tỷ lệ cho detect/display.
- Overlay gắn với camera/epoch/frame/thời điểm và hết hạn 500 ms. Kết quả phiên cũ bị bỏ. Mất hình mới quá hai giây phải thể hiện hình cũ/mất tín hiệu.
- Stop/switch/reconnect dừng worker có thời hạn, không nhân model/thread, không để callback cũ ghi trạng thái nguồn mới. Giữ POST đổi camera 202 và thất bại giữ nguồn cũ.

**Nghiệm thu C1:** chạy runtime với nguồn giả phát frame thay đổi. Chặn inference 2–3 giây; trong thời gian chặn phải quan sát nhiều frame mới/JPEG mới, không chỉ một lần publish trước khi block. Chặn OCR/DB/clip riêng có kết quả tương tự. Hai viewer dùng một encode; frame skip/no-person vẫn cập nhật; stop/switch loại kết quả cũ. Không dùng grep source thay kiểm thử hành vi.

## 2. C2 — Kiểm chứng đúng nhận diện và model thực dùng

- Giữ các sửa rear plate-only, OCR async một request chạy/chờ mỗi track và ledger tư thế per-track. Test xuyên detector→tọa độ→ROI→association→OCR/ledger, không chỉ helper.
- Khóa theo camera + epoch + track; không lẫn hai camera có cùng track ID. Native crop chưa vẽ; OCR ít nhất hai frame khác nhau đọc trùng toàn biển và không mâu thuẫn đáng tin cậy.
- Thiếu người ở camera sau không được chặn crop/OCR/card. Ghép chưa chắc chắn phải thể hiện lý do, không gán biển/học sinh.
- Xác minh model path/hash/mapping đang dùng trong QA. `helmet_best.pt` từng chứa plate; backup đúng mapping chỉ được dùng QA sau kiểm ảnh có/không mũ. Không ghi đè weights hoặc tự đổi cấu hình vận hành. Model sai mapping phải hiển thị không khả dụng.
- Giữ cửa sổ bằng chứng nhiều frame, crossing 3+3 tối đa năm giây, trạng thái unknown; không tăng tốc bằng cách giảm số mẫu hoặc suy luận vi phạm từ OCR rỗng.
- Snapshot/crop và DB thành công trước âm thanh chính thức. OCR-only im lặng; nhiều lỗi cùng encounter không mất lỗi; loa ngắn, chống lặp, giữ cấu hình tốc độ hiện đã chốt nếu kiểm chứng hoạt động.
- Chuẩn hóa ảnh trên card bằng nhãn Việt rõ: “Ảnh người”, “Ảnh đầu / mũ”, “Ảnh biển số”. Phối hợp Task 2 sửa test theo contract này, không sửa test cho qua trong khi giao diện vẫn sai.

**Nghiệm thu C2:** các ca mũ treo/cầm tay/đầu khuất/hai xe sát nhau, OCR mâu thuẫn/chậm/lỗi, đi bộ dắt xe/đứng yên/đi xe qua hai hướng, frame lặp/quá hạn/mất track, nhiều lỗi/mất media và reconnect đều có test hành vi.

## 3. C3 — Bàn giao hook feedback cho Task 3: đã chốt phương án A

Không polling feedback trong pipeline. Nơi lưu feedback là `app/api/recognition_reviews.py::post_feedback`.

- Task 3 viết collector/worker và hợp đồng enqueue trong `tasks/task-03/integration/FEEDBACK_HOOK_CONTRACT.md`.
- **Task 1 là writer duy nhất của `recognition_reviews.py`** để thêm hook nhỏ sau khi `db.record_review_feedback` thành công, đã loại conflict. Không thêm hook vào `pipeline.py` để bắt save review.
- Hook chỉ enqueue metadata nhẹ, bounded/nonblocking. Không đọc/copy ảnh, scan DB, freeze dataset hoặc train trong HTTP handler. `try/except` không tự biến tác vụ đồng bộ thành bất đồng bộ.
- Gửi định danh review và version/feedback thực đã lưu; không tin version đề nghị từ client như version mới. Retry/replay không tạo sample trùng. Conflict 409 hoặc save thất bại không enqueue thành công giả.
- Collector thiếu/chưa bật hoặc queue đầy không phá feedback thành công; có log/metric lỗi gọn và cơ chế reconciliation của Task 3 từ feedback đã lưu. Không để lỗi bị mất âm thầm.
- Khi chưa có collector contract, chuẩn bị patch/test rồi tiếp tục C1/C2/C4; không hỏi người dùng chọn A/B/C nữa.

**Nghiệm thu C3:** review thành công được thu; replay không nhân đôi; 409 không thu; collector chậm/lỗi/queue đầy không chặn feedback; sau phục hồi reconciliation thu đủ nhãn mới đúng version. Bàn giao Task 3 mẫu kết quả API thực.

## 4. C4 — Benchmark runtime thật với toàn bộ video tranning

Harness cũ `dual_source_test.py` dùng Worker detect/OCR riêng; `run_videos.py` tạo pipeline bằng `__new__` và xử lý thủ công. Giữ chúng nếu có giá trị component benchmark nhưng không gọi kết quả đó acceptance runtime.

- Viết/chỉnh harness dùng luồng runtime production thật, nguồn file QA, DB/media/config QA, có async OCR/ledger/event/media/JPEG/viewer.
- Inventory mọi video hiện có tại `C:\Users\khucv\Downloads\tranning`: tên, hash, metadata, phiên nguồn, coverage. Không mặc định chỉ 14/15 file nếu thư mục đổi.
- Replay đến EOF/toàn timeline. Nếu chỉ chạy một đoạn, ghi timestamp/phần trăm chưa chạy và trạng thái PARTIAL, không đánh dấu toàn bộ video PASS.
- Sau C1/C2, chạy hai nguồn đồng thời 30 phút với các đoạn 1/2/3 viewer. Dùng model mũ đúng mapping và hồ sơ front/rear thực tế; không giả hai camera là hai gate.
- Báo riêng capture FPS, preview frame mới FPS, AI FPS, frame bỏ, tuổi frame, latency nhận-frame→JPEG p50/p95, queue, lỗi, CPU/RAM và VRAM/GPU thực. Không coi `torch.cuda.memory_allocated` là GPU utilization. Không gọi thời gian detect/OCR là camera→screen.
- Giữ phép so sánh cùng video/config/model hash; xử lý bottleneck đã đo. Mục tiêu preview ≥15 FPS/camera khi nguồn đủ FPS, AI ≥5 FPS/camera, nhận-frame→JPEG p95 ≤500 ms.
- Chưa có ground truth thì chỉ báo cơ chế/hiệu năng, không tính OCR accuracy từ chuỗi nonempty hoặc confidence.

## 5. C5 — GPU/runtime contract cho Task 3

Task 1 cung cấp profile/model/runtime loader contract và cơ chế tài nguyên có thể chia sẻ với worker Task 3. Không để training tự bắt đầu khi benchmark đang chiếm GPU. Giữ model instance/tracker riêng camera, một bên sở hữu inference tại một thời điểm.

Candidate chưa đủ artifact/hash/mapping/evaluation không được load. Khi tích hợp apply/rollback QA, Task 1 phải trả trạng thái applied/failed thật; model lỗi giữ baseline. Registry active của Task 3 không tự đồng nghĩa camera đã load model.

Không mở tự ghép trước/sau khi chưa có calibration và tập cặp lượt có nhãn; matcher default OFF không phải lý do chặn preview/OCR độc lập.

## 6. C6 — Test, bàn giao và điều kiện đóng

Chạy focused sau mỗi lát. Chạy regression Task 1, Node/audio và UI có liên quan. Bàn giao Task 2 để full backend toàn hệ thống sau các patch đã tích hợp; không chạy ba full suite cùng lúc.

Dùng interpreter `D:\Work\Project_motorbike\venv\Scripts\python.exe`; DB/media/backup/recording và pytest basetemp riêng mới mỗi run. Không dùng lại/xóa basetemp của task khác. Không nạp model/camera thật trong unit/API integration khi không cần; test không được pollute module/env.

Cập nhật `CLOSURE_TODO.md`, EXECUTION_LOG, ACCEPTANCE_REPORT và HANDOFF, giữ lịch sử. Mỗi mục có run ID, lệnh, log exit code, snapshot mã/hash/config, bằng chứng trước/sau và rollback. Đính chính P6/P8 đã đánh dấu xong nhưng chưa full-timeline/runtime/browser.

Checklist kết thúc:
- [ ] C1 preview độc lập có test block AI nhiều frame.
- [ ] C2 rear OCR/mũ/ledger/ảnh card và âm thanh đạt hành vi.
- [ ] C3 hook đúng API đã tích hợp và collector không chặn feedback.
- [ ] C4 toàn timeline video và benchmark runtime 30 phút có số liệu thật.
- [ ] C5 GPU/apply/rollback contract đã bàn giao và kiểm QA.
- [ ] C6 test riêng đạt, shared patch tích hợp, Task 2 có bàn giao cho regression chung.

Không tuyên bố đạt độ chính xác khi thiếu nhãn hoặc đạt ca Imou 12 giờ khi chưa đo. Phân biệt CODE_COMPLETE, TEST_PASS, VIDEO_MEASURED, HARDWARE_ACCEPTED. Ngoại lệ dữ liệu/thiết bị giữ PENDING rõ; hoàn thành mọi việc không phụ thuộc chúng. Chỉ báo kết quả cuối hoặc blocker cần thông tin ngoài repository, không kết thúc bằng “bạn muốn tiếp tục không?”.
