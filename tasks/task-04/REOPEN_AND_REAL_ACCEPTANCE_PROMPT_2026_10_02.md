# TASK 4 — Mở lại closure và nghiệm thu runtime/model thật

Ngày: 02/10/2026. Repository: `D:/Work/Project_motorbike`.

Tiếp tục thực thi Task 4 và phối hợp đúng owner Task 1–3. Không mở lại audit toàn repo; giải quyết các điểm đã tái hiện sau đây, rồi nghiệm thu theo mục tiêu đã chốt. Không dừng ở cập nhật báo cáo hoặc hỏi có tiếp tục mỗi checkpoint.

## 1. Đính chính kết luận hiện tại theo bằng chứng mới

Đọc cùng:
- `tasks/task-04/CODEX_TASK1_FINAL_RECHECK_2026_10_02.md`.
- `tasks/task-04/CODEX_TASK23_RECHECK_2026_10_02.md`.

Codex đã kiểm source mới, chạy QA riêng và **chưa sửa application code** trong lượt đối chiếu này. Những mục dưới đây không phải báo cáo giả định còn lỗi từ log cũ:

### A. 58.3 FPS chưa phải benchmark nhận diện thật

`tasks/task-04/video_runtime_measure.py`:
- `_DummyDetector` chỉ sleep 5/8 ms rồi trả list rỗng.
- `_publish_frame_jpeg` bị thay bằng sleep 3 ms + bytes stub, không encode JPEG thật.
- Script tự viết loop read/resize/submit/result, không chạy `VideoPipeline._run_loop()`.
- Chạy tối đa 20 giây/các frame tương ứng mỗi video, không phải toàn timeline tới EOF.
- `_metrics_detect` gộp thời gian từng dummy detector và thời gian chờ nhóm, không phải một tập latency stage có cùng định nghĩa.

JSON báo 0 person/plate/helmet và GPU null phù hợp với harness này. Giữ kết quả như **smoke/harness measurement**, không đánh dấu VIDEO_MEASURED cho luồng YOLO/OCR/camera thật hoặc coi đạt mục tiêu 15 FPS preview/5 FPS AI.

### B. Preview blocker chưa sửa

Source pipeline vẫn publish JPEG rồi `.result()` detector trong cùng loop. Phép thử thật đã tái hiện trong bản đối chiếu Task 1: nguồn tăng 1 → 28 trong một giây detector chưa hoàn tất, pipeline read/frame_seq/JPEG mới đều giữ 1. Các test C1 tự mô phỏng publish rồi chờ không chứng minh hành vi độc lập.

### C. Lifespan test chưa chạy lifespan thật; cleanup exception path bị bỏ

`app/tests/test_main_lifespan.py` gọi start/stop functions riêng và ghi “simulate lifespan”; không thực thi `main.lifespan` để chứng minh integration.

Codex chạy `async with app.main.lifespan(main.app)` thật, chỉ mock các boundary init/start/stop để không mở DB/model/camera vận hành. Ném exception trong thân context:

```
START_CALLS = maintenance:1, pipelines:1, collector:1, training:1
STOP_CALLS_AFTER_EXCEPTION = maintenance:0, pipelines:0, collector:0, training:0
```

Không có worker/camera thật được khởi động trong probe. Kết quả chứng minh cleanup không được gọi ở nhánh context lỗi, không phải quan sát leak của worker thật. Sửa bằng vòng đời có `try/finally` và tracking phần startup thành công, có test exception/partial startup/shutdown failure.

### D. Backup: không tiếp tục dùng lỗi lịch sử để kết luận

`app/tests/test_backup.py` hiện đã dùng R3 `list_backup_sets` trong các test worker/API. Codex vừa chạy toàn file bằng venv, BASE_DIR/DB/media tạm trên D:

**11 passed, 1 warning, 5.12 giây, exit 0**.

QA root: `D:/Work/Project_motorbike/tasks/task-04/codex-task4-backup-recheck-628dmcmn`.

Job aborted/kill cũ không chứng minh 3 test vẫn fail ở mã hiện tại. Đóng mục migration legacy nếu diff và collection xác nhận đã áp, đưa đủ test vào regression chung. Nếu chạy chung vẫn lỗi, lấy traceback mới và sửa isolation/connection/mount/cấu hình đúng nguyên nhân; không chọn bỏ file.

### E. Promotion không thể dựa vào cơ chế runtime chưa có bằng chứng

Test mới assert 256-byte zero file lên `pending_runtime`: nó chứng minh lỗ hổng đang tồn tại, không phải test từ chối model hỏng đã đạt. Chưa tìm thấy `apply_pending.py` trong `app`/`scripts`, ledger vẫn ghi chờ Task 1 bàn giao; không được tuyên bố runtime rollback đã bảo vệ production khi chưa chỉ ra và test đường thực thi đó.

Các điểm missing metric/NaN/unknown runner/provenance thiếu trong bản đối chiếu Task 3 vẫn còn trong source. Không chỉ sửa artifact rồi bỏ các gate khác.

### F. “Full regression 461” là bộ chọn lọc

Các lệnh trong NEXT_ACTIONS chọn file/subdir cụ thể; không phải full `app/tests`. Có thể ghi focused suites đạt nhưng không thay lượt full backend thống nhất sau integration. Hook API có mã và test mới là tiến bộ; chất lượng nhận diện và training thật vẫn chưa hoàn thành.

## 2. Thứ tự thực thi

### R1 — Task 1: preview độc lập AI thực sự

- Tách luồng preview encode/publish khỏi AI chờ kết quả, hoặc cơ chế nonblocking phù hợp; mỗi camera latest frame slot hữu hạn.
- Không tích frame cũ, không chia sẻ YOLO instance đồng thời; giữ model/tracker sở hữu theo camera, scheduling GPU công bằng.
- Giữ camera_id/source_epoch/frame_seq/timestamp; stale results bị bỏ, overlay TTL đúng; crop dùng frame nguồn chưa vẽ tương ứng.
- JPEG thật encode một lần/frame mới, chia sẻ giữa viewer.
- Test dùng producer frame độc lập và **runtime loop thật**: giữ detector Future 2–3 giây, assert nhiều JPEG mới/tuổi frame ngay trong khoảng chặn trước khi release. Thêm OCR chậm, một/hai camera, nhiều viewer, đổi nguồn và shutdown.
- Không thay bằng source-order assertions hoặc loop mô phỏng tương tự production.

### R2 — Task 2/integration owner: lifecycle và test chung

- Startup/shutdown có cleanup `finally`, hữu hạn, idempotent; partial startup/context exception/shutdown một thành phần lỗi không bỏ cleanup thành phần còn lại.
- Test đi qua app factory/router/lifespan thật, chỉ giả lập boundary camera/GPU và dùng DB/media temp; không dựng FastAPI test app khác rồi coi là production lifecycle.
- Kiểm collector tiếp nhận feedback, assets/labels thực và dedup sau HTTP success/replay/conflict; metrics/no-raise không thay test dataset có ảnh đúng.
- Đưa backup R3 cùng `test_backup.py`, `test_maintenance_worker.py`, cleanup đã sửa vào full suite. Tách student photos/media/config/DB; không backup toàn thư mục vận hành trong test.
- Giữ đăng nhập tự điền và tài khoản giáo viên hiện tại; không tự mở rộng auth migration.

### R3 — Task 3 + Task 1: model integrity, promotion và runtime apply

- Metric bắt buộc theo target, kiểu số hữu hạn, count nguyên đúng cỡ tập; reject thiếu/NaN/Infinity/sai miền.
- Require job completed + operation train + runner_type train được hỗ trợ, không nhận unknown/None/evaluate runner.
- Bắt buộc provenance liên kết model SHA256, dataset snapshot/split/hash, target và kết quả evaluation server-side.
- Artifact sai định dạng/không load được phải bị từ chối trước eligible/applied. Load kiểm trong QA có timeout/tài nguyên hữu hạn; không tải vào model đang capture để kiểm thử.
- Đổi test “zero artifact được nhận là bình thường” thành test giữ/reject theo contract đã chốt. Nếu giữ trạng thái chờ kiểm, UI phải ghi chưa kiểm định và tuyệt đối không công nhận mọi gate đã đạt.
- Implement hoặc xác nhận đường apply runtime thật: load/mapping/smoke inference → atomic acknowledgement; failure giữ baseline và rollback có test. Không dùng tên script chưa tồn tại làm bằng chứng.
- Model mũ mapping đúng, hash/path thực; chuẩn class chưa chứng minh accuracy. Ngưỡng precision 0.5/F1 0.5 ở detector không thay precision cảnh báo loa ≥95% mỗi lỗi.

### R4 — Task 2: browser/media/production thật

- Ảnh/crop thật đúng quyền 200, nội dung decode được; giáo viên khác/thiếu lớp bị từ chối.
- Clip thật Range 206, browser play/seek; auth theo chiến lược hiện tại. Test file không tồn tại 403/404 chỉ là negative case.
- Production deep link gọi backend đang phục vụ build, không nhận HTML từ Vite dev fallback. API không tồn tại vẫn JSON 404.
- Backup restore có DB + ảnh/crop/clip fixture, integrity/hash và thời gian thực; DB-only/empty-media không nghiệm thu restore bằng chứng.
- E2E sửa/saved feedback, conflict, export/import ảnh, freeze/split và job operation/state thật. Giữ mock UI suites riêng.

### R5 — Task 3: vòng học từ nhãn thật

- Detector/helmet runner vẫn unsupported, OCR vẫn baseline evaluator: báo CODE_PARTIAL cho training, không ghi CODE_COMPLETE của toàn mục tiêu học.
- Nối UI duyệt crop/đúng/sai/chỉnh biển → asset + label + provenance → dataset draft. Không đoán chữ ở ảnh không đọc được.
- Tách train/validation/test theo encounter/video/session, không leak frame cùng lượt. Người dùng chỉ cần duyệt các mẫu thật chưa xác định.
- Làm runner training cần thiết có optimization/checkpoint thật; test contract trên bộ QA nhỏ. Thiếu corpus đủ để đánh giá thì giữ PENDING_DATA cho chất lượng, không che khả năng trainer chưa có.
- Đánh giá baseline và candidate trên cùng holdout độc lập; người dùng sửa nhãn không làm model đổi ngay. Không dùng enhancement/roster để tự tạo ground truth hay tự gán học sinh.

### R6 — Task 4: benchmark và nghiệm thu đúng nghĩa

- Sau R1 ổn định, chạy tất cả video thực có trong `C:/Users/khucv/Downloads/tranning` tới EOF bằng runtime thật và model QA có mapping/hash đúng. Ghi coverage/timeline/error; source offline throughput tách riêng với realtime FPS.
- Dùng cấu hình hai nguồn front/rear cùng cổng, capture/publish JPEG/OCR/ledger/event/media đúng đường runtime, chạy 30 phút; 1/2/3 viewer.
- Đo capture fresh FPS, preview fresh FPS, AI FPS từng camera, tuổi frame, receive→JPEG p50/p95, OCR queue/drops, RAM/VRAM đầu/giữa/cuối và thiết bị thực của mỗi model. Không lấy sleep dummy hoặc peak snapshot cuối làm số đo toàn ca.
- Mục tiêu đã chốt: preview ≥15 fresh FPS/camera khi source đủ FPS, AI ≥5 FPS/camera, latency nội bộ p95 ≤500 ms. Precision lỗi loa ≥95% từng loại, recall ≥70% clear, OCR exact ≥50% trên ≥30 biển rõ; ≥50 violation/50 clean. Chưa có nhãn thì chưa nghiệm thu accuracy.
- Nhánh gương giữ review-only, auto ghép front/rear OFF tới calibration và tập nhãn đạt.
- Chạy full backend `app/tests` một process mới không ignore/deselect và không chạy chồng job khác; Node/lint/build/browser/production theo snapshot đó. Lưu command, exit, commit+dirty diff manifest, config/model hashes.
- Imou/LAN/reconnect/12 giờ nghiệm thu riêng khi có điều kiện; thiếu thiết bị không chặn R1–R5.

## 3. Bàn giao và persistence

Task 4 cập nhật STATUS_BOARD/ACCEPTANCE_REPORT/NEXT_ACTIONS: focused tests đạt; harness fake measurement; preview REPRODUCED; lifespan exception cleanup REPRODUCED; backup file riêng 11/11 PASS; full/runtime quality/training thật chưa hoàn tất.

Nếu owners Task 1–3 đã bàn giao file, ghi nhận trong ledger rồi integration owner tiếp tục; không để việc treo chỉ vì ownership lịch sử. Nếu owner còn viết, giữ một writer và đưa patch/contract rõ ràng, không sửa chồng.

Tiếp tục phần độc lập và ghi bước tiếp theo sau compaction. Không hạ tiêu chí, không biến bug thành “known gap low priority” để đóng báo cáo, không coi test xác nhận hành vi sai là test sửa lỗi đạt. Chỉ xin thông tin ngoài repository khi thực sự cần. Không đổi camera/model/DB/media vận hành, không push/deploy hay upload cloud.
