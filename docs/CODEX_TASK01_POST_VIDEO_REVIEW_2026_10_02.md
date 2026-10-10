# Task 1 — đối chiếu báo cáo sửa lỗi và video QA

Ngày review: 2026-10-02. Review chỉ đọc mã/artifact, kiểm tra metadata model và chạy probe crossing thuần; không chạy inference/training, không thay model/camera hoặc DB/media vận hành.

## Kết luận

**Chưa đóng Task 1 theo tiêu chí đã giao.** Có log test đạt và hai script xử lý video, nhưng F02/F03/F05/F06 còn vấn đề trong runtime; V1/V2 chưa kiểm tra pipeline ứng dụng đầy đủ. Các phần cần camera thật/nhãn thống kê giữ PENDING là đúng, nhưng không dùng các blocker đó để bỏ qua lỗi runtime có thể sửa và kiểm tra cách ly.

## Các bằng chứng đã đối chiếu

- `tasks/task-01/full_tests_run.txt`: 895 passed, 1 deselected, 1 warning, 232.38s. Đây là log có thật, nhưng đã bỏ cleanup API nên không phải toàn bộ suite xanh.
- `tasks/task-01/full_tests_final.txt`: log sửa đổi muộn hơn, 11 failed, 576 passed, 1 deselected, 347 errors. Nhiều error là không tạo được thư mục pytest tạm. Chưa xác định nguyên nhân môi trường cuối cùng; không kết luận đây đều là regression logic, cũng không được dùng lượt xanh trước để mô tả lượt mới nhất đạt.
- `VIDEO_TEST_REPORT.md`, `ACCEPTANCE_REPORT.md`, `HANDOFF.md`, scripts `run_videos.py` / `dual_source_test.py`, JSON V1/V2 đã đọc.
- Metadata `models/helmet_best.pt`: `{0: 'plate'}`.
- Metadata `models/backups/helmet_best_20260930_090903.pt`: `{0: 'With Helmet', 1: 'Without Helmet'}`. Chỉ kiểm tra lớp, chưa chứng minh chất lượng nhận diện.
- Probe crossing bằng implementation hiện tại: 3 frame phía A tại 1000.0/1000.1/1000.2; 3 frame phía B tại 1017.1/1017.2/1017.3; frame cuối vẫn trả crossing True.

## N01 — Model mũ sai vai trò có phương án kiểm tra trước khi training

Model mặc định sai lớp làm runtime tắt nhận diện mũ; harness lại bypass validation và gắn detector plate vào vai trò helmet. 2.886 box không phải bằng chứng đã nhận diện mũ.

Có checkpoint backup đúng hai lớp ngay trong repository. Cần thử checkpoint đó trên ảnh/video có mũ, không mũ, mũ cầm tay và đầu bị khuất bằng cấu hình QA riêng, ghi hash/config và kết quả. Không ghi đè model hiện tại hoặc bật vận hành chỉ vì mapping đúng. Chỉ quyết định fine-tune sau baseline chất lượng này.

## N02 — Camera sau chưa có đường OCR không phụ thuộc người

Trong `app/cv/pipeline.py`, profile `ocr_only` không nạp detector người. `_run_loop()` có nhánh `if not person_dets: ... continue` trước khi tạo group và gọi `_observe_group()`; nhánh OCR đang nằm ở quan sát group. Vì vậy rear có thể phát hiện box nhưng không đi vào OCR/voting theo runtime này.

Cần luồng rear theo vehicle/plate track riêng, không cần person detector hoặc posture. Khi chưa có track/ghép xe đáng tin cậy, vẫn có thể hiện crop/OCR review với lý do, không gán học sinh. Test xuyên vòng xử lý thật của rear: source → detection → crop → async OCR → ít nhất hai frame đồng thuận → recognition card; kết quả phiên cũ phải bị loại.

## N03 — Chuyển JPEG lên đầu vòng AI chưa tách hiển thị

`_publish_frame_jpeg()` đã được chuyển trước inference, nhưng vẫn nằm trong cùng `_run_loop()` với `person_future.result()` và các tác vụ AI. Trong thời gian vòng này chờ AI, không có lần publish khung mới tiếp theo từ vòng đó. Capture ở thread riêng chưa đủ nếu publisher vẫn chờ AI.

Test `test_blocking_detect_does_not_block_jpeg_publish` hiện đọc vị trí chuỗi trong source; không chạy vòng lặp hoặc kiểm tra nhiều frame/JPEG tiến trong khi Future bị chặn. Acceptance nói test chặn Future và seq vẫn tiến vượt quá điều test chứng minh.

Cần publisher/encode lấy latest frame riêng hoặc worker AI độc lập khỏi vòng preview. Test hành vi: source tiếp tục cấp frame, block AI 2–3 giây, nhiều frame_seq/JPEG mới vẫn tiến; block OCR/DB tương tự; stale overlay hết hạn, viewer dùng chung bytes.

## N04 — Crossing vẫn nhận track sau khoảng trống 17 giây

Thời điểm `transition_started_at` được bắt đầu khi gặp frame ở phía đối diện, nên không tính khoảng trống từ lần cuối thấy phía đầu. Probe hiện tại vẫn trả True cho 3A → 17s gap → 3B.

Cần vô hiệu hóa chứng cứ khi gián đoạn/mất liên tục và tính cửa sổ từ chứng cứ phía đầu hợp lệ tới phía đích. Giữ 3+3 frame mới, tối đa 5s theo contract. Test trực tiếp chuỗi trên, dead-zone gap, timestamp/frame lặp và source epoch mới. Không chỉ kiểm tra constructor có tham số 5s.

## N05 — Posture temporal chưa theo track

Khối temporal posture vẫn chọn mode từ các group của một frame rồi append vào `self._posture_window` chung cho pipeline. Đây không phải ledger riêng theo camera/source/track/lượt xe. Test count hoặc thuộc tính không chứng minh hai xe không chia sẻ mẫu.

Cần ledger theo track/lượt xe, frame identity, khoảng cách mẫu/cửa sổ/span/agreement theo contract; hết hạn chuyển unknown. Test hai xe mỗi xe chỉ hai mẫu không đủ bốn mẫu, riding/pushing trái nhau, TTL và mất track. Health tổng theo camera nếu cần phải tách khỏi quyết định từng xe.

## N06 — V1/V2 là benchmark detector/OCR, chưa phải QA pipeline thật

- V1 tạo `VideoPipeline.__new__`, gán nhiều state giả, vô hiệu ledger/event manager và dùng pool stub; vòng video gọi detector + OCR đồng bộ. Không chạy `_run_loop`, quyết định violation/persist/realtime/loa thực.
- V2 tạo Worker riêng, đọc file và gọi detector/OCR inline; không dùng `VideoPipeline`. Không có pose/hành vi/crossing/consensus/event/preview/JPEG/viewer/GPU scheduling thực.
- V1 dừng theo budget wall-clock khoảng65s, nên có thể chỉ xử lý đoạn đầu đối với clip dài/tốc độ thấp; không chứng minh toàn nội dung 15 video đã được kiểm tra. Cần frame coverage/duration thực từng file.
- OCR success được tính khi có bất kỳ text, kể cả fragment/conf0; không phải đúng toàn biển. Nhãn phải đổi thành raw_nonempty_reads hoặc tương đương.
- V2 p95 đang đo detect/OCR sau đọc frame, không phải receive→JPEG-ready hoặc camera→screen. Không so thẳng 498ms với tiêu chí preview500ms.
- Detector error có thể chỉ được log; OCR exception bị `pass`. `worker.error=null` không chứng minh zero stage exceptions.
- Các list plate_reads/helmet_reads trong harness tăng theo frame; kết quả 30 phút không chứng minh bộ nhớ ứng dụng hữu hạn trong ca12h.

Cần harness chạy pipeline triển khai thật, chỉ thay source/DB/media/clock/startup config QA. Đo capture/newJPEG/AI riêng, drop/queue/age/error từng stage, hai viewer, OCR chậm và replay toàn video. Chạy lại dual-source30m sau khi sửa runtime. Giữ các kết quả cũ dưới nhãn component benchmark, không bỏ chúng.

## N07 — Front throughput chưa đạt; số VRAM không đủ quyết định tăng parallel

Component benchmark ghi front4.42FPS, dưới mục tiêu AI5FPS. Chưa có số FPS preview mới15FPS. VRAM206MB là `torch.cuda.memory_allocated()`, không phải tổng GPU/VRAM sử dụng hay mức bận GPU. Không kết luận GPU còn95% công suất hoặc tăng pool chỉ từ số này.

Đo thiết bị từng model/OCR, stage timings, GPU utilization, reserved/allocated và process VRAM khi có công cụ; dùng task profile front/rear đúng chức năng. Tối ưu theo điểm nghẽn đo được, giữ tiêu chí ít báo sai.

## N08 — Browser QA không cần seed dữ liệu vận hành

Lý do seed UI xung đột Task2 không phải blocker tất yếu: dùng DB/media/accounts thử, cổng QA riêng, app factory thật và startup dependency test. Phối hợp ownership trên fixture/factory, không sửa chồng. Nếu còn pending integration thì ghi đúng dependency; đừng coi chưa có camera thật là lý do bỏ test hai viewer/update/loa trong browser.

## Thứ tự tiếp tục

1. Kiểm tra checkpoint mũ backup bằng QA và hoàn thiện rear OCR không phụ thuộc người.
2. Tách publisher khỏi AI, test Future chặn thực; sửa crossing gap và posture per-track.
3. Đổi harness thành QA runtime thật; chạy toàn nội dung video và dual-source30m, đo preview/AI/latency đúng định nghĩa.
4. Khắc phục môi trường pytest temp hiện lỗi, rerun fresh suite không deselect sau Task2 cleanup tích hợp; chạy browser QA cách ly.
5. Chuẩn hóa số đo và acceptance. Tập nhãn đủ/camera Imou/12h vẫn PENDING tới khi có bằng chứng; chưa bật auto-match hai camera hoặc gương khi chưa đạt nhãn/góc nhìn.

Review này không chạy lại 895 test hoặc 30 phút inference. Các kết luận mã nêu trên là đọc luồng hiện tại; probe crossing và metadata model là kiểm tra trực tiếp. Không có thay đổi mã ứng dụng trong lượt review.
