# Task 1–2–3: tiến độ và phương án xử lý

Ngày rà soát: 02/10/2026. Nguồn: mã và báo cáo đang có trong working tree tại thời điểm đọc; các task vẫn có thể tiếp tục cập nhật sau mốc này.

## 1. Kết luận

Chưa thể đóng nghiệm thu toàn hệ thống. Task 1 đã bổ sung nhiều logic nhận diện nhưng luồng hiển thị vẫn bị ràng buộc bởi vòng xử lý AI. Task 2 đã sửa nhiều lỗi nghiệp vụ và backup, nhưng browser integration và regression chung chưa có kết quả đầy đủ mới nhất. Task 3 có nền tảng quản lý dữ liệu/job/UI nhưng chưa có vòng huấn luyện thật từ thao tác người dùng; có các lỗi được tái hiện trong xuất/nhập, queue và promotion.

Đây là review, không phải lượt sửa mã ứng dụng. Không thay camera, model vận hành, DB hoặc media thật. Không khởi động thêm tiến trình camera/GPU, không gửi lệnh cho các phiên Cursor. Danh sách chat Codex truy cập được không cung cấp trạng thái chạy của ba phiên Cursor; tiến độ dưới đây dựa trên repository và báo cáo, không khẳng định phiên nào đang chạy/dừng.

## 2. Tiến độ thực

| Task | Đã có | Chưa đủ để nghiệm thu | Kết luận |
|---|---|---|---|
| 1 — Camera/nhận diện/runtime | Nhánh OCR camera sau không có person; ledger tư thế theo track; kiểm tra mapping mũ; crossing được sửa; cache JPEG; nhiều test riêng | Preview độc lập AI chưa đạt bằng chứng; benchmark còn là harness riêng; toàn timeline video chưa chạy; thiếu nhãn chất lượng và camera thật 12 giờ | PARTIAL |
| 2 — Admin/người dùng/vận hành | Cleanup/schema mới; teacher scope/media; bộ backup DB/media; CSV/upload; sửa fixture cùng origin | Full regression mới chưa chốt; E2E 38/39 báo cáo là UI mock; browser với API thật, production và LAN còn thiếu | PARTIAL |
| 3 — Feedback/dataset/training | Module/API/trang dữ liệu, bbox, queue, compare; test helper/API | Không có trainer OCR thật và worker nối từ UI; import ảnh chưa tạo liên kết bền vững; queue/promotion sai; chưa có candidate được đo hơn baseline | PARTIAL — hạ tầng, chưa chứng minh học tốt hơn |

Không dùng phần trăm checklist để diễn đạt mức hoàn thành sản phẩm: một lỗi runtime cốt lõi có thể khiến nhiều mục xanh vẫn không sử dụng được.

## 3. Kiểm chứng mới trong lượt review

Các kiểm tra dùng `venv\Scripts\python.exe`, DB/media/config tạm trong thư mục riêng tại `%TEMP%`. Không chạy lifespan camera thật. Không dùng DB vận hành.

| Kiểm tra | Kết quả |
|---|---|
| `app/tests/task03_helpers` | **43 passed**, 1 warning, 11.59 s |
| Cleanup admin hiện tại + `test_task02_t2_1_teacher.py` + `test_task02_t2_2_media.py` | **25 passed**, 1 warning, 9.19 s |
| `node --test test/*.test.mjs` trong frontend | **26 passed**, không skip |
| Crossing: 3A rồi 3B liên tiếp | Chỉ frame B thứ ba trả crossing |
| Crossing: 3A, khoảng trống 17 giây, 3B | Không crossing |
| Export dataset có sample nhưng không có crop | Vẫn xuất thành công ZIP chỉ có manifest và README |
| Export/import với ảnh PNG thật | Import thêm sample, nhưng `crop_path=None`; ảnh chỉ nằm trong staging preview, chưa liên kết thành asset bền vững của dataset |
| Candidate trỏ đến file không tồn tại, không metrics | `promotion.promote()` vẫn trả `state=active` trong DB tạm |
| Job đã `waiting_resource` gọi chạy tiếp | Bị từ chối vì hàm chỉ nhận trạng thái `queued` |
| Hai job cùng target đều queued | `can_start_gpu_job()` trả False cho cả hai |
| ZIP chứa file Unix bình thường, mode regular-file | Bị từ chối nhầm là symlink |

Các unit test xanh trên không phủ được các lỗi tái hiện bổ sung. Không chạy lại full backend, build/lint hoặc Playwright trong lượt audit này. Không đo FPS/precision/recall mới.

Log `tasks/task-01/backup_run_final.txt` đã có **37 passed** cho ba nhóm backup/maintenance, mới hơn báo cáo 3 fail cũ. Cleanup cũ bị deselect trong báo cáo Task 1 cũng đã PASS ở phép thử mới. Phải cập nhật lại báo cáo, không tiếp tục viện dẫn hai lỗi lịch sử này như blocker hiện tại.

## 4. Phát hiện cần sửa

### A. Task 1: preview vẫn chờ vòng AI — ưu tiên cao nhất cho độ mượt

`app/cv/pipeline.py::_run_loop` gọi `_publish_frame_jpeg()` rồi vẫn chờ `person_future.result()` trong cùng vòng lặp. Khi AI bị chặn, vòng lặp chưa đọc và publish frame kế tiếp. Publish sớm giúp frame hiện tại tới trước AI; chưa tạo được luồng hiển thị độc lập.

`test_task01_F01_F02_runtime.py::test_blocking_detect_does_not_block_jpeg_publish` không chạy loop; vẫn kiểm tra thứ tự chuỗi trong source. Báo cáo nói JPEG tiếp tục tăng khi chặn inference chưa được test đó chứng minh.

Sửa: luồng capture giữ frame mới nhất; publisher/display tiến độc lập; AI tiêu thụ snapshot mới nhất. Định danh camera/epoch/frame thật, kết quả cũ bị bỏ. JPEG encode một lần mỗi frame hiển thị mới. Test chặn AI 2–3 giây nhưng thấy **nhiều frame_seq và JPEG mới** trong thời gian chặn; không chỉ publish một lần trước khi chặn.

### B. Task 1: benchmark không đại diện runtime — ưu tiên cao

`video_qa/dual_source_test.py` vẫn là `Worker` đọc video và detect/OCR riêng. `run_videos.py` tạo pipeline qua `__new__` và gọi xử lý thủ công. Chúng chưa chứng minh toàn luồng `VideoPipeline` thực với pose/ledger/async OCR/event/media/JPEG/viewer hoạt động đồng thời.

Front 4.42 FPS trong số đo cũ thấp hơn mục tiêu AI 5 FPS, nhưng phép đo đó không được dùng như FPS preview hoặc acceptance pipeline thật. VRAM allocated 206 MB không phải mức sử dụng GPU.

Sửa harness dùng runtime thật, DB/media/nguồn video QA riêng; chạy mọi video đến EOF hoặc báo chính xác tỷ lệ coverage/chưa chạy. Chạy 30 phút hai nguồn sau khi sửa preview, có 1/2/3 viewer, dùng hồ sơ front/rear đúng vai trò và model mũ đã kiểm tra. Phân biệt AI FPS, frame mới preview, nhận-frame→JPEG, camera→màn hình.

### C. Task 2: browser QA chưa phải integration thật — ưu tiên cao

`isolatedFixture.js` giả lập login, API, media và WebSocket. Kết quả 38/39 là kiểm tra UI trên dữ liệu giả. Nó chưa xác minh teacher scope, media/Range, DB, auth/route và reconnect của backend thật. Fixture login còn đưa teacher vào URL mặc định admin; mock `/me` trả admin.

Chờ localStorage là cơ chế đồng bộ test, chưa chứng minh hoặc sửa được race condition của ứng dụng. Nếu tái hiện lỗi thật, lấy trace/network rồi sửa đúng nguyên nhân, giữ cách đăng nhập tạm theo yêu cầu người dùng.

Sửa nhãn ảnh Việt qua handoff Task 1; không bỏ test hoặc đổi selector thành không kiểm tra nội dung. Tách rõ UI mock và browser integration sử dụng factory triển khai thật với CV/nguồn giả, DB/media QA. Kiểm tra đủ bốn vai trò, teacher đúng/khác/thiếu lớp, login sai, reload, chi tiết ngoài 200 dòng, ảnh/clip và deep link production.

CI hiện còn gọi uvicorn app thật dưới nhãn “mock/test mode” mà chưa thể hiện một cấu hình QA tắt camera/model. Job production-routes hiện kiểm secret; chưa kiểm route SPA/API/media bản build thực. Đây là việc Task 2 cần hoàn thiện.

### D. Task 3: smoke không phải huấn luyện — ưu tiên cao

`scripts/training/smoke_train.py` mô phỏng training: prediction lấy trực tiếp từ nhãn holdout, candidate dùng `/tmp/smoke.pt`. Kết quả 100% của smoke kiểm lifecycle, không đo OCR model. `ocr_engine.py` hiện chỉ có wrapper EasyOCR đọc ảnh; detector wrapper chỉ predict. API tạo job chỉ ghi queue, chưa có worker/trainer nối thao tác UI vào training thật.

Sửa báo cáo thành “lifecycle simulation PASS”. Triển khai runner thật cho target đã chọn, job worker, artifact/checkpoint/hash/log/metrics. Khi chưa hỗ trợ OCR training, phải trả rõ `unsupported` hoặc chưa khả dụng, không gọi inference/simulation là training. Huấn luyện detector biển không tự làm OCR đọc chữ tốt hơn.

### E. Task 3: promotion thiếu điều kiện — ưu tiên chặn áp dụng model

`promotion.promote()` bỏ kiểm tra nếu không truyền `expected_metrics`; UI đang truyền null. Trọng số không tồn tại và chưa đánh giá vẫn được đánh dấu active. Metrics client cung cấp không thể thay thế kết quả đánh giá server. Hiện đây là active trong registry, chưa phải đổi model runtime; không được hiển thị như đã áp dụng vào camera.

Sửa: chỉ promote artifact thật, hash/mapping/runtime contract đúng, training hoàn thành và có evaluation độc lập đủ điều kiện lưu phía server. Candidate smoke/test không được promote. Tách `eligible/selected/pending_runtime/applied/failed` theo hợp đồng phù hợp; chỉ applied khi Task 1 xác nhận load thành công. Rollback phải chọn lại baseline trước đó và xác nhận runtime khi có tích hợp; hàm hiện chỉ retire active.

### F. Task 3: xuất/nhập ảnh chưa đủ cho vòng sửa nhãn — ưu tiên cao

Export có thể thành công khi toàn bộ crop thiếu. Import có thể ghi sample nhưng không lưu/liên kết ảnh vào kho asset dataset; `crop_path=None`. Ảnh preview không phải nguồn training bền vững. `crop_media_id` cần giải quyết qua ID→media của server, không mặc định là tên file dưới snapshots.

Sửa: xuất manifest với đường dẫn tương đối và hash của ảnh thật. Không gọi gói thiếu ảnh là train-ready. Import kiểm decode/hash/kích thước, copy ảnh vào kho dataset ổn định, liên kết crop_path rồi commit metadata; preview/apply dùng cùng artifact đã xác nhận. Import lại idempotent, giữ lịch sử/version và không ghi đè nhãn mới bằng gói cũ. Dọn staging có giới hạn, không xóa asset đã nhập.

ZIP Unix bình thường đang bị chặn do `create_system == 3` được coi là symlink. Kiểm mode symlink thực thay vì hệ điều hành tạo ZIP. Thay kiểm containment bằng đường dẫn resolve và quan hệ thư mục, không dùng `startswith` đơn thuần. Test Windows/Linux ZIP bình thường và ZIP traversal/symlink/bomb.

### G. Task 3: queue/GPU lease sai — ưu tiên cao trước training

Job waiting không resume được. Hai job queued cùng target chặn nhau vì queued/waiting bị tính là đang giữ tài nguyên. Lock in-process và bộ đếm theo target chưa điều phối được nhiều tiến trình hay GPU đang dùng bởi Task 1/runtime.

Sửa: queued không chiếm GPU, chọn job theo thứ tự công bằng; claim nguyên tử qua cơ chế dùng chung đã thống nhất. Chỉ một job training giữ lease; inference được ưu tiên theo ngân sách đã đo. Resume waiting, heartbeat/recovery sau crash, cancel thực dừng runner/subprocess và giải phóng tài nguyên. Không cần xây dịch vụ riêng nếu một worker local đáp ứng được.

### H. Cập nhật tiến độ thay vì báo lại thiếu tích hợp đã có

`app/main.py` đã include bốn router training; `App.jsx` đã có các trang training/bbox. Báo cáo Task 3 vẫn ghi chờ router/routing. Điều này không chứng minh integration đạt, nhưng phải kiểm hiện trạng rồi cập nhật đúng, không chờ mã đã có.

## 5. Thứ tự giải quyết và ownership

1. **Ngay trong các task đang chạy:** Task 1 xử lý A; Task 3 khóa promotion không đủ điều kiện và sửa F/G; Task 2 hoàn thiện browser QA/CI. Các phần này có thể độc lập về file.
2. **Task 1 và 3 bàn giao contract:** review/media→dataset, frame/track/camera/epoch, engine/hash/mapping, runtime apply/rollback và GPU lease. Một owner giữ từng file shared; bên còn lại đưa patch có test.
3. **Task 3 hoàn tất vòng người dùng:** xem crop thật → sửa chữ/box → lưu version → export/import ảnh → freeze/split → training thật → holdout → candidate. Chưa đủ nhãn thì chuẩn bị collector/editor, không fake số đo.
4. **Task 2 làm integration owner cho QA chung:** áp patch shared đã thống nhất, chạy backend fresh process toàn bộ, Node/lint/build, UI mock và browser với backend QA thật, production build routes. Phân công này là phương án giao việc; lượt audit chưa nhắn sang task.
5. **Task 1 đo runtime video thật:** toàn timeline 15 video tranning, hai nguồn 30 phút, rồi camera Imou/ca 12 giờ khi có lịch. Task 3 đánh giá nhận diện trên nhãn độc lập; Task 2 xác nhận UI/media/backup.

Không chạy ba full-suite cùng lúc, không chạy hai training/benchmark GPU cạnh tranh, không sửa chung file đồng thời. Không stash/reset hoặc xóa thay đổi của task khác. Nếu file shared đang được giữ, tiếp tục phần độc lập và bàn giao patch; không hỏi lại sau mỗi bước.

## 6. Chỉ thị có thể gửi cho từng task

### Gửi Task 1

Đọc toàn bộ báo cáo này, tập trung A/B/H. Giữ các sửa crossing/rear OCR/ledger đúng hiện có. Hoàn thiện preview độc lập AI bằng test runtime chặn AI 2–3 giây vẫn có nhiều frame/JPEG mới; thay test grep source. Chuyển video harness sang runtime thật và coverage toàn timeline tranning. Handoff Task 3 contract review/media, GPU lease và model apply/rollback; handoff Task 2 nhãn ảnh Việt ở RecognitionLogPanel. Không sửa chồng task khác. Đính chính các mục PASS chưa có bằng chứng, bỏ blocker backup/cleanup lịch sử khi test hiện tại đạt. Tiếp tục đến khi phần khả thi đã kiểm chứng, không kết thúc bằng câu hỏi tiếp tục.

### Gửi Task 2

Đọc toàn bộ báo cáo này, tập trung C/H và QA tích hợp. Sửa E2E còn lại theo contract nhãn Việt qua Task 1; tách UI mock và browser integration với app factory thật, DB/media QA, không camera/model thật. Kiểm đủ admin/security/management/teacher, teacher scope, reload, lỗi login, deep link, API404, ảnh/Range và backup restore. Giữ đăng nhập tự điền và tài khoản giáo viên theo yêu cầu. Nhận patch shared Task 3 hiện trạng trước khi sửa; không chờ router/routing đã có. Sau khi các owner bàn giao, chạy full backend không ignore/deselect, Node/lint/build và hai loại E2E. Không gọi 38/39 mock là hoàn tất. Không dùng failure lịch sử làm bằng chứng regression mới. Ghi run ID, commit/diff snapshot, lệnh, log đầy đủ và pending thực tế.

### Gửi Task 3

Đọc toàn bộ báo cáo này, tập trung D/E/F/G/H. 43 test helper/API xanh chưa chứng minh training. Sửa export/import để ảnh thật được lưu bền vững và hash/crop_path đúng; thêm tests còn thiếu. Chặn promotion khi không artifact/hash/evaluation server, smoke luôn không eligible. Sửa queued/waiting resume và GPU lease phối hợp Task 1. Nối UI/job worker vào trainer thật; không dùng label làm prediction, không dùng đường dẫn trọng số giả làm candidate thật. Khôi phục baseline đúng khi rollback; active registry không được hiển thị đã áp dụng runtime. Kiểm router/trang hiện đã gắn thay vì chờ patch cũ. Hoàn thiện sửa chữ/box trên crop thật với version/idempotency/history, freeze train/val/test không leakage. Thiếu nhãn/GPU ghi thiếu chính xác và tiếp tục editor/import/tests; không đánh dấu trainer hoặc chất lượng PASS bằng simulation.

## 7. Điều kiện đóng và nghiệm thu

- Full backend fresh process không ignore/deselect; skip phải có lý do riêng và không bỏ luồng quan trọng. Dùng basetemp QA mới mỗi run, không trỏ vào thư mục một task khác đang dùng.
- Node/lint/build và browser UI mock đều đạt; browser integration API thật chứng minh quyền/media/route/training flow theo phạm vi.
- AI bị chặn vẫn có nhiều frame hiển thị mới; camera sau OCR không phụ thuộc có người; không lẫn camera/epoch/track.
- Export/import giữ được ảnh/nhãn/hash khi chuyển sang máy/thư mục khác và import lặp không nhân đôi/mất nhãn.
- Training thật tạo checkpoint có hash, loss/log và evaluation; candidate smoke hoặc chưa đo không thể promote.
- Mục tiêu hai camera: preview ≥15 FPS/camera khi nguồn đủ FPS; AI ≥5 FPS/camera; p95 nhận-frame→JPEG ≤500 ms. Số đo chưa đạt phải ghi FAIL hoặc PARTIAL.
- Chất lượng: OCR toàn biển ≥50% trên ít nhất 30 biển rõ; precision cảnh báo loa ≥95% từng loại, recall ≥70% trên trường hợp rõ; tối thiểu 50 violation/50 clean. Thiếu nhãn là PENDING_DATA, không dùng confidence hoặc số OCR nonempty thay cho độ chính xác.
- Gương review-only khi chưa đạt góc nhìn/nhãn và nghiệm thu riêng. Không tự ghép trước/sau hoặc gán học sinh khi chưa đủ bằng chứng.
- Hai camera Imou thật/12 giờ, latency camera→screen và LAN nhiều máy là phần nghiệm thu riêng. Không thay đổi camera vận hành hoặc chạy training trên GPU đang phục vụ ca nếu chưa có ngân sách/lịch thống nhất.

Chốt báo cáo bằng bốn mức: **đã viết mã / test hành vi đạt / đã đo video / đã nghiệm thu thiết bị thật**. Không dùng một số tổng test để thay thế bốn mức này.
