# Bàn giao từ Codex cho TASK 4 — School Gate Monitor

Mốc bàn giao: 02/10/2026. Mọi phát hiện là snapshot tại lúc kiểm tra; phải đối chiếu mã mới trước khi nhận lỗi còn tồn tại.

## 1. Vai trò và mục tiêu người dùng

Người dùng giao Task 4 thay Codex quán xuyến Task 1/2/3: đọc tiến độ, kiểm chứng báo cáo, giao sửa lỗi, phối hợp tích hợp và chốt chất lượng cuối. Mục tiêu là phần mềm sử dụng được, hình mượt, nhận diện đúng, cảnh báo ngắn/nhanh và vòng sửa nhãn giúp cải thiện model có kiểm chứng.

Người dùng không muốn phải liên tục nhắn “làm đi/tiếp tục”. Tiếp tục mọi phần đã được giao mà không hỏi lại sau từng đợt. Hỏi chỉ khi thật sự thiếu thông tin/thiết bị/quyết định ngoài repository; vẫn làm phần độc lập. Không báo DONE vì số test xanh trong khi hành vi chưa đạt.

Lượt Codex gần đây chủ yếu review + chạy QA cách ly + viết prompt/docs. **Không** sửa application code/model/camera trong các lượt review này. Application changes trong working tree thuộc các phiên Cursor Task 1–3; không coi chúng là patch đã được Codex nghiệm thu toàn hệ thống.

## 2. Workspace và giới hạn

- Repository: `D:\Work\Project_motorbike`, Windows PowerShell.
- HEAD lúc đọc: `83a0309a332e54bc36497c5ba2da4bb8f1ecdd94`; branch `dot-4-all-12`.
- Working tree có rất nhiều thay đổi tracked/untracked/staged của các task; **không stash/reset/clean, commit tất cả, push hoặc overwrite** để tạo baseline sạch.
- Interpreter cố định: `D:\Work\Project_motorbike\venv\Scripts\python.exe`. Global Python từng thiếu cv2/easyocr/ultralytics và gây failure không đại diện venv.
- Máy mục tiêu: i7-12700H, RAM 16 GB, RTX 3050 Laptop 4 GB.
- Hai Imou bằng LAN, **trước/sau cùng một cổng vật lý**, ca 8–12 giờ, 2–3 viewer. Không đồng nhất camera_id với physical gate_id.
- IP camera người dùng sửa gần nhất: `192.168.1.9`; không khẳng định hiện online. Không đưa RTSP password/token vào log/prompt/dashboard. Không đổi exposure/firmware/password/nguồn vận hành để QA.
- Một máy bảo vệ phát loa; viewer khác mặc định chỉ xem. Rate tiếng nói hiện đã đổi theo yêu cầu nhanh: 1.45, clamp 1.0–1.6. Queue ≤2, TTL 5 giây, gộp/dedup và quyền phát phải đúng. Không quay lại rate 1.15 chỉ vì plan cũ nếu contract mới đã chốt.
- **Đăng nhập tạm giữ nguyên:** bấm tài khoản tự điền username/password, có giáo viên phía dưới; API login thật. Chưa chuyển chiến lược auth/localStorage/JWT/cookie. Quyền teacher/media/route vẫn phải đúng. Đọc `tasks/task-02/DEFERRED_AUTH.md`.
- Không deploy VPS/cloud, upload dữ liệu lên Kaggle/Colab, tự thay model live, xóa DB/media/log/model/video người dùng hoặc tự đổi mật khẩu thiết bị.
- QA dùng DB/media/backup/recording/config riêng, nguồn video/AI giả theo phạm vi test. Không mở RTSP thật mặc định trong test.

## 3. Dữ liệu và quy tắc nhận diện đã chốt

Nguồn user cung cấp:
- `C:\Users\khucv\Downloads\tranning` — từng inventory 15 MP4, trước đó gọi 14; đọc inventory hiện tại, không cố định số lượng.
- `C:\Users\khucv\Videos\2026-10-01 18-33-23.mp4`.
- `C:\Users\khucv\Downloads\yolo_plate_ocr_dataset.zip` — đã được nhắc, bàn giao không khẳng định cấu trúc/nhãn đã hợp lệ.

Camera front: người/xe, mũ, tư thế đi xe/dắt bộ, crossing. Góc trước bên phải người lái không mặc nhiên thấy gương trái. Camera rear: plate/crop/OCR/bằng chứng sau. Gương review-only nếu chưa đủ góc nhìn/nhãn. Ghép trước/sau default OFF khi chưa calibration và tập cặp lượt có nhãn; không gán biển/học sinh chỉ vì gần thời gian.

Track khóa camera + source_epoch + track; event/encounter là lượt xe cổng vật lý. Mẫu frame phải mới, không đếm cache/lặp. Mỗi lỗi có evidence riêng: tối đa 5 quan sát hợp lệ/1,5 giây, ≥4 đồng thuận, ≥80%, span ≥400 ms, interval ≥100 ms. Unknown không phải phiếu có/không vi phạm.

Crossing: 3 frame ổn định mỗi phía trong tối đa 5 giây, biên 2% đường chéo frame; không có đường cắt hoặc posture unknown/standing/pushing thì không tự kết luận riding-through-gate.

OCR: ít nhất 2 crop từ frame khác nhau trùng toàn biển, đủ chất lượng và không có contender đáng tin cậy. OCR rỗng/lỗi/chưa rõ là needs_review vàng, không beep/TTS, không tự gán học sinh. Lỗi mũ đã confirmed vẫn cảnh báo khi OCR vàng.

Bằng chứng snapshot/crop và DB thành công trước âm thanh chính thức; bảng có thể pending, không trả URL giả. Nhiều lỗi cùng event/upsert/version, không đánh mất lỗi đến muộn. Không gọi confidence detector/OCR là độ chính xác quyết định.

Model từng có sự cố: `models/helmet_best.pt` mapping `{0: 'plate'}`. Backup `models/backups/helmet_best_20260930_090903.pt` có With Helmet/Without Helmet. Mapping đúng không chứng minh chất lượng; xác minh model path/hash QA/live đang dùng trước nhận định. Không overwrite weights. YOLO11/BoT-SORT chỉ chuyển sau đối chứng trên GPU mục tiêu; số CPU benchmark không chứng minh RTX3050.

## 4. Ownership và phối hợp

| Task | Quyền sửa chính |
|---|---|
| 1 | `app/cv/*`, guard realtime/camera runtime, GuardPage/RecognitionLogPanel/PlateReviewPanel, alert/audio/lease, video benchmark; writer của API feedback hook `app/api/recognition_reviews.py` |
| 2 | Admin/users/register/media, web nghiệp vụ/login autofill, CSV/upload, backup/cleanup/CI/production; integration owner shared sau bàn giao |
| 3 | `app/training/*`, training APIs/UI/editor/scripts/tests/docs; collector, dataset, trainer/evaluator, queue, promotion |
| 4 | Điều phối/review/triage/test/report cuối. Không mặc định chiếm tất cả file shared; sửa targeted khi được owner bàn giao hoặc owner đã xong và đã ghi nhận nhận quyền |

File shared: `app/db.py`, schemas/config/main/auth, router/App/Sidebar, fixture chung/proxy/dependency. Một writer/file tại một thời điểm; đọc diff mới ngay trước áp patch. Bên không giữ file viết patch/contract + test trong integration rồi tiếp tục phần độc lập. Task 2 giữ tích hợp hiện tại; Task 4 quản dependency, chứng cứ và nhận bàn giao cuối.

Phương án feedback **đã chốt A**: hook tại API lưu feedback, không polling trong pipeline. Task 3 làm enqueue/collector/worker; Task 1 thêm hook sau save thành công; Task 2 tích hợp lifecycle. Hook nhẹ bounded/nonblocking, không copy ảnh/train trong request. Try/except không khiến tác vụ sync thành async.

Không tự tạo ba task thay thế khi chúng đã chạy. Nếu môi trường có tools đọc/nhắn đúng task thì dùng identity thật, không suy từ title mơ hồ. User giao Task 4 điều phối trong scope này; không gửi Slack/email hoặc tác vụ ngoài dự án. Các phiên Cursor hiện **không thấy** trong danh sách chat Codex mà Codex đọc được; không giả vờ đã nhắn/nhìn tiến trình nếu chỉ đọc file.

## 5. Trạng thái Task 1 tại bàn giao

Đã có code/test cho rear plate-only, ledger tư thế per-track, model mapping guard, crossing 3+3, JPEG cache, late issues. Codex trực tiếp kiểm crossing:
- 3A→3B liên tiếp: chỉ frame B thứ ba crossing.
- 3A→gap17s→3B: không crossing.

Các điểm chưa xác nhận đạt sau prompt mới:
- `_run_loop()` vẫn publish rồi chờ Future trong cùng loop tại lần đọc gần nhất; chưa chứng minh preview thật độc lập AI. Test từng gọi “blocking detect does not block JPEG” chỉ kiểm source order. Phải xem code mới và test chạy block 2–3 giây vẫn có **nhiều** frame/JPEG mới.
- `video_qa/dual_source_test.py` là Worker detect/OCR riêng; `run_videos.py` dùng pipeline `__new__` + gọi manual, chưa runtime đầy đủ. Chưa whole timeline mọi video; báo cáo 60 giây đầu vẫn đánh dấu done.
- Số cũ front 4.42 FPS/rear 10.47 FPS, p95 ~498/290 ms, RAM 2282 MB, torch VRAM allocated 206 MB: không acceptance preview FPS/camera→screen, không mức GPU utilization. Không dùng lại làm chứng cứ sau code đổi.
- Báo cáo full 959 passed/3 fail/1 skip/1 deselect là **lịch sử**, không full snapshot hiện tại. Backup/cleanup fail cũ đã được sửa/test mới; không giữ chúng làm blocker nếu hiện trạng đạt.

Prompt đang giao mới nhất:
`tasks/task-01/FINAL_CLOSURE_PROMPT_2026_10_02.md`.
Đọc `POST_VIDEO_REPAIR_TODO`, EXECUTION_LOG, ACCEPTANCE_REPORT, HANDOFF và log raw có liên quan.

## 6. Trạng thái Task 2 tại bàn giao

Task 2 đã sửa R3 backup API/worker/list đồng bộ bộ DB+media+manifest+marker, cleanup/schema, teacher/media, CSV/upload, proxy fixture.

Chứng cứ:
- `tasks/task-01/backup_run_final.txt`: 37 passed cho backupR3 + backup + maintenance, 421.28 s. Đây là log mới thay failure disk-full trước đó.
- Codex fresh QA cleanup_admin + teacher + media: 25 passed, 9.19 s.
- Codex Node frontend logic: 26/26 pass trong review trước; không gọi là build/browser cuối.
- User báo browser 38/39 sau sửa same-origin interception. Fixture giả login/API/media/WebSocket: **UI mock**, không backend/browser integration thực. Test nhãn crop Việt còn lỗi cần Task 1 phối hợp.

Còn cần: full backend mới không ignore/deselect, Node/lint/build mới, browser API thật đủ 4 role/class/media/Range, production SPA/API404/build route, lifecycle/training flow; LAN và RPO/RTO media vận hành nghiệm thu riêng.

Tooling từng treo; disk C đầy do tmp backup nhiều GB. Không mặc định shell vẫn chết hoặc mọi failure mới do môi trường. Fixtures backup phải dùng media nhỏ QA, không copy vận hành 20 GB lặp. Không xóa rộng temp/data của người dùng.

Prompt mới nhất:
`tasks/task-02/FINAL_CLOSURE_PROMPT_2026_10_02.md`.

## 7. Trạng thái Task 3 tại bàn giao: 92 test xanh, còn blocker cụ thể

Latest Codex fresh QA run:
`app/tests/task03_helpers` + `app/tests/task03_closure`: **92 passed, 1 warning, 17.81 s**. Tests có thật; không full hệ thống. Đã cải thiện ZIP Unix guard, import asset, SHA256 thực, queue resume/result status, collector cursor/singleton/pagination. Kiểm lại nếu mã đổi.

**Ba blocker mới nhất có bằng chứng:**

1. **Feedback contract sai nghĩa version.** `record_review_feedback` tính new_version=current+1 nhưng response expected_version echo input. Client expected=5, review mới=6, response vẫn expected=5. Contract mới nói dùng expected_version làm saved version là sai; còn chứa ví dụ version không tồn tại. Không áp nguyên patch. Khuyến nghị enqueue review_id + feedback_id thực, worker đọc committed review.version; nếu cần saved_version explicit, return field additive từ new_version đã commit qua shared owner. Không expected+1 mù vì validation future-version hiện cần kiểm lại.
2. **Worker dispatch lỗi.** Phép thử tạo plate_detector job và chạy `TrainingWorker._process_once()` trong DB QA trả failed: `TypeError: _run_detector_job() got an unexpected keyword argument 'dataset_id'`. OCR runner nhận keyword riêng; detector/helmet placeholder nhận job dict. Chuẩn hóa interface/test process_once thực; unsupported phải unsupported, không TypeError. Tests worker_module_exists/callable chưa bảo vệ dispatch.
3. **Promotion chưa đủ quality/provenance/loadability.** Phép thử artifact 128 byte không phải model, SHA256 đúng, job queued, metrics 30 samples/OCR0% vẫn `pending_runtime` khi không có baseline. Hash/số byte không chứng minh trained/loadable model. Chặn job chưa train/evaluate, artifact không load được, metrics không liên kết model/dataset/config/hash, thiếu baseline/absolute-quality. Đây là registry QA, chưa đổi camera; không nói model live đã bị thay.

**Thiếu chức năng cần nói đúng:** `ocr_trainer.py` hiện `IS_EVALUATOR=True`, EasyOCR pretrained inference holdout; **chưa OCR optimization training**, `model_path=None`. Detector/helmet runner placeholders unsupported. User muốn học từ nhãn sửa, chưa đạt chỉ bằng evaluator marker. Cần triển khai trainer thật/operation phân biệt; không nói chỉ cần 30 nhãn thì tự học ngay.

`APP_LIFESPAN_PATCH.md` lần đọc gần nhất chỉ có collector start/stop, chưa training_worker dù report nói có. `main.py`/API hook chưa thấy lifecycle/hook mới đã áp khi grep gần nhất. Phải kiểm code hiện tại trước ghi pending.

Prompt Task 3 ưu tiên mới nhất:
`tasks/task-03/PRE_INTEGRATION_FIX_PROMPT_2026_10_02.md`.
Đọc thêm `POST_CLOSURE_REVIEW_AND_FIX_PROMPT`, FINAL_CLOSURE_PROMPT và actual code/test. Không coi report C01–C08 ALL FIXED là phủ hết requirement.

## 8. Các lỗi review cũ để tránh làm lại

Review trước thấy export ZIP thiếu ảnh, import crop_path=None, ZIP Unix regular bị chặn, lazy singleton mất queue, reconcile kẹt64, waiting không resume, pending_data→completed, hash chỉ kiểm nonempty. Task 3 đã sửa một phần và thêm test; **không nhận các lỗi này vẫn tồn tại nếu chưa kiểm lại**. Latest blocker ở mục7 mới là ưu tiên.

Review trước Task2 thấy cleanup xóa hold/outside root, schema mismatch, flat backup/worker drift, importCSV/upload/SPAAPI404/CI sai. Nhiều phần đã sửa. Dùng test hiện tại, không lặp lỗi lịch sử như mới. Đặc biệt không deselect cleanup_admin vì Codex mới đã PASS.

## 9. Tiêu chí nghiệm thu giữ nguyên

Software:
- Full backend fresh process không ignore/deselect, Node/lint/build, UI mock và browser API integration thật; shared patches đã áp, state/UI đúng.
- Preview tiến khi AI/OCR/DB/clip bị block; frame mới/epoch/track đúng; ảnh/clip/quyền/crop/event/audio thực đúng.
- Feedback→asset/label draft→export/import qua root khác→freeze/split→worker evaluate/train→artifact/evaluation→promotion/rollback contract xuyên luồng.
- Training chỉ DONE khi optimization/checkpoint loadable/log/hash đã có; simulation và evaluator là operation khác.

Hiệu năng/dữ liệu/thiết bị (không suy từ unit):
- Preview ≥15 frame mới/s/camera khi nguồn đủ FPS; AI ≥5 FPS/camera; nhận-frame→JPEG p95≤500 ms. Camera→screen p95 mục tiêu≤1.5 s đo bằng đồng hồ cảnh.
- Helmet xác nhận p95≤2 s từ quan sát hợp lệ đầu; crossing p95≤1 s sau đủ điều kiện; bảng≤500 ms sau confirm; voice start≤1 s khi queue rỗng và bằng chứng ready.
- Precision lỗi đọc loa≥95% từng loại, recall≥70% trường hợp rõ; OCR whole plate≥50% trên ≥30 biển rõ. Tập ≥50 violation/≥50 clean; gương riêng≥30 thiếu rõ/≥30 có rõ để xét mở loa.
- Front/rear matching ≥50 cặp có nhãn + ≥20 ca mơ hồ; báo coverage/reject, không “không ghép gì” là đạt; default OFF tới calibration.
- Camera trống10 phút 0 violation; hai nguồn30 phút QA trước ca Imou12 giờ; 2–3 viewer; reconnect nguồn phục hồi mục tiêu15 s; không OOM/hang/leak.
- API100k event/3client list/detail p95≤500ms; backup restore cảmedia, RPO≤1h/RTO≤30phút trên dữ liệu nghiệm thu.

Chưa đủ nhãn/thiết bị/lịch thì PENDING_DATA/HARDWARE, không hạ ngưỡng hoặc fake. Software hoàn thiện không mặc nhiên hardware accepted.

## 10. Thứ tự tiếp quản ngay

1. Đọc file `plan.md` Task4 và các prompt mới nhất, snapshot git/status và task logs. Lập bảng active/reported/resolved/verified/pending theo chứng cứ, không cố định %.
2. Giao Task3 sửa ba blocker mục7, operation evaluator/train và lifecycle patch. Task1/2 đợi contract đúng, vẫn làm preview/browser riêng.
3. Task1 chứng minh preview độc lập runtime, model/rear/temporal đúng; Task2 tiếp UI/API/media/CI và chuẩn bị app factory QA.
4. Nối feedback hook/lifecycle sau owners bàn giao; test API/browser xuyên luồng.
5. Full regression chung một snapshot ổn định, rồi benchmark runtime/video toàn timeline; chuẩn bị nhãn và nghiệm thu camera thật.
6. Báo cáo riêng code complete/test pass/video measured/hardware accepted, cho user biết đúng một nhóm việc tiếp theo cần họ làm nếu thiếu labels/device.

## 11. Tài liệu nên đọc theo thứ tự

1. `tasks/task-04/plan.md`, `todo.md`, file bàn giao này.
2. `docs/CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md`.
3. Task1/2 `FINAL_CLOSURE_PROMPT_2026_10_02.md`; Task3 `PRE_INTEGRATION_FIX_PROMPT_2026_10_02.md` rồi FINAL_CLOSURE_PROMPT.
4. OWNERSHIP/CONTRACTS/todo/latest log/acceptance của từng task, có timestamp; đọc source/tests liên quan.
5. Khi cần lịch sử: `docs/CODEX_TASK01_POST_VIDEO_REVIEW_2026_10_02.md`, `docs/CODEX_TASK02_REVIEW_2026_10_02.md`, prompt repair cũ và log raw. Không đọc toàn bộ temp/media tree.

Nếu khó tìm thread Cursor thật, đọc file repo và chuẩn bị dispatch rõ để user gửi; không giả tools có thể điều khiển Cursor. Không dừng chỉ vì không nhắn được: review/test/docs/integration sau bàn giao vẫn thực hiện được.
