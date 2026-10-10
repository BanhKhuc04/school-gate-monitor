# Prompt thực thi TASK 3 song song — feedback, nhãn và training

Bạn phụ trách **TASK 3 của School Gate Monitor** tại `D:\Work\Project_motorbike`, chạy song song với Task 1 và Task 2. Bắt đầu thực thi ngay và tiếp tục các phần khả thi đến khi hoàn thành, không dừng ở đọc mã/đề xuất.

## 1. Mục tiêu đã chốt

Tạo vòng người dùng chạy camera/video → nhìn crop và dự đoán → tích Đúng hoặc sửa chữ/box/nhãn → lưu nhãn → export/import hoặc tạo dataset trực tiếp → train candidate → so sánh baseline → áp dụng/rollback sau khi đạt.

Ưu tiên **biển số/OCR trước, nhãn mũ kế tiếp**; gương/hành vi triển khai contract và dữ liệu tương ứng khi góc/clip đủ rõ. Đừng triển khai đồng loạt mọi trainer khi vòng plate chưa hoạt động.

Không có cơ chế “bấm Đúng là model tự đổi weights”. Feedback được lưu ngay nhưng training diễn ra theo đợt. Không đoán biển khi mất chi tiết hoặc dùng roster/biển gần giống làm target. Không tự gán học sinh từ feedback và không sửa chứng cứ lịch sử.

Đọc đầy đủ:

1. `D:\Work\Project_motorbike\tasks\task-03\plan.md`.
2. `D:\Work\Project_motorbike\tasks\task-03\todo.md`.
3. Ownership, contracts và execution log hiện tại của Task 1/2.
4. `tasks/task-01/POST_VIDEO_REPAIR_PROMPT.md`, `tasks/task-02/REPAIR_PROMPT.md` và các patch đang chờ tích hợp.
5. Mã review/feedback/export/training hiện có; đối chiếu phiên bản mới trước khi sửa.

`plan.md` là đặc tả đầy đủ. Prompt này chốt cách thực hiện song song và nghiệm thu.

## 2. Ownership và phần bắt đầu ngay

Ghi `tasks/task-03/OWNERSHIP.md` trước khi sửa; kiểm tra file mới chưa bị task khác tạo. Lưu status/diff/commit, không log credentials.

**Task 3 có thể làm ngay trong file riêng**, tên cuối cùng theo pattern repository và tránh trùng:

- Module dataset/training/evaluation/model-candidate mới, ví dụ `app/training/*`; không xây microservice.
- API training/dataset riêng, ví dụ `app/api/training.py`, schemas riêng.
- Trang và component riêng, ví dụ `frontend/src/pages/TrainingDataPage.jsx`, `frontend/src/components/training/*`, client adapter riêng.
- Tools/CLI riêng export/import/validate/split/train/evaluate, trong vị trí có hướng dẫn; tận dụng helper cũ qua adapter, không copy logic thành hai nguồn chân lý.
- Tests `app/tests/test_task03_*`, frontend tests/E2E tên Task 3 riêng, QA outputs và docs trong `tasks/task-03/`.

**Không tự ghi vào file Task 1/2 đang giữ:**

- `app/cv/*`, GuardPage, PlateReviewPanel, RecognitionLogPanel, AlertBanner, các utility loa.
- `app/api/admin.py`, `register.py`, `media.py`, `users.py`, auth modules, `background.py`, `system.py`.
- DB/schema/config/main/router/App/sidebar/shared fixtures/proxy/dependency lockfiles là điểm tích hợp; phải bàn giao hoặc nhận ownership trước khi ghi.
- `app/api/recognition_reviews.py`, script export hiện có có thể đang được sửa: đọc hiện trạng, dùng adapter và đề xuất patch nhỏ, không mặc định lấy quyền ghi vì cần dùng.

Nếu cần shared patch:

1. Tạo `tasks/task-03/integration/<topic>.md` hoặc patch cụ thể với contract, file/hunk, test và owner hiện tại.
2. Ghi PENDING_INTEGRATION, tiếp tục module/UI/CLI/test độc lập.
3. Sau khi bàn giao, tích hợp tuần tự, chạy lại test production factory thật. Không coi patch chưa apply là hoàn thành.

Không stash/reset/clean; không di chuyển/sao chép tùy tiện working tree bẩn để né xung đột. Không commit toàn bộ thay đổi, push/deploy hoặc sửa auth strategy. Giữ các nút tự điền đăng nhập và giáo viên.

## 3. QA và tài nguyên khi chạy song song

- DB/media/dataset/output/tmp/ports/process của Task 3 riêng, path thực kiểm chứng. Không dùng DB/media vận hành trong test hoặc seed.
- Unit/API/UI/export/import chạy ngay trên QA. Video thật nguồn `C:\Users\khucv\Downloads\tranning` chỉ đọc, không ghi đè; thu crop vào dataset QA riêng.
- Không khởi tạo thêm Imou/model inference khi đọc API list/health/dataset. Không thay nguồn/exposure/firmware/config camera đang vận hành.
- Không train GPU cùng benchmark/training của Task 1. Một training GPU job tại một thời điểm; cần trạng thái `waiting_resource` hoặc queued khi tài nguyên chưa được bàn giao, tiếp tục labels/dataset/UI/tests.
- Chuẩn bị contract điều phối GPU cho các task; lock riêng Task 3 không đủ bảo đảm Task 1 đã nhường GPU. Mặc định train ngoài ca/QA khi nguồn GPU không tranh chấp; không tự dừng process task khác.
- RTX3050 4GB: batch/imgsz/workers được xác minh bằng smoke; không dùng batch16 chỉ để “full tài nguyên”, không nâng dependency trên venv đang chạy. Môi trường training riêng nếu cần khác dependency; ghi phiên bản tương thích runtime.
- Không upload dữ liệu camera/học sinh lên Kaggle/Colab/cloud nếu người dùng chưa yêu cầu. Export local vẫn đầy đủ và portable để họ tự dùng khi cần.

## 4. Slice A — Vòng duyệt biển chạy được trước

Tận dụng `recognition_reviews`/history/corrected_text hiện có, bổ sung phần thiếu theo adapter/contracts.

Trang “Dữ liệu huấn luyện” phải có:

- Crop gốc, ảnh ngữ cảnh và vài frame của cùng lượt; zoom nhìn rõ, OCR máy và target người duyệt tách riêng.
- Đúng / Sai–nhập biển / Không đọc được / Không phải biển / Ghép nhầm xe.
- Đúng lưu chuỗi được xác nhận làm target; Sai phải có chuỗi đúng hợp lệ. Cho giữ chuỗi trình bày và canonical, dòng trên/dưới khi cần.
- Chỉnh nhãn đã duyệt, lịch sử và version; retry không nhân đôi. Version phải khớp chính xác, future version bị từ chối; key ràng buộc sample/reviewer/payload không replay sang review khác.
- Loading/empty/error/retry, pagination/filter đúng và bỏ response cũ. Thành công cập nhật version mới, không gửi lại version cũ.
- Role/scope phía server đúng; không để teacher/khách đọc mọi crop chỉ vì API có get_current_user. Không đổi hệ thống auth để xử lý quyền dataset.
- UI tự đề xuất chỉ là pending, không auto-accept confidence cao. Duyệt không beep/TTS hoặc gán roster.

**Test đạt trước khi chuyển slice:** user sửa một biển → reload đúng → sửa lần nữa → history/version đúng; wrong association/unknown không thành positive OCR; hai người sửa409, retry/idempotency và read scope đúng. Test browser trên QA, không chỉ helper/source grep.

## 5. Slice B — Box/mũ và thu mẫu có provenance

- Thêm editor bbox trên ảnh gốc: thêm/sửa/xóa box, đổi class, undo/save; đúng tỷ lệ letterbox/zoom/crop. Sửa text và sửa box là hai target khác nhau.
- Mũ khoanh cùng vùng đầu cho cả With Helmet/Without Helmet, đầu khuất unknown; mũ cầm tay không counted worn. Class mapping version rõ; checkpoint backup đúng lớp cần được Task1 kiểm chứng, không tự train từ checkpoint plate mang tên helmet.
- Hook Task1 thu sample qua patch bàn giao: native frame chưa overlay, crop/frame hash, source video/camera/gate/run/epoch/track/encounter/time/frame_seq, bbox/transform, model/config hash.
- Dedup exact/near và quota/retention training riêng; lấy cả lỗi/mẫu đúng/negative đa dạng. Không một xe lặp chiếm dataset, không lưu vô hạn hay xóa chứng cứ vận hành.
- Gương/hành vi dùng state/quan hệ/clip labels như plan; không tạo box cho vật thể vắng mặt hoặc gán dắt xe từ một ảnh mơ hồ.

**Test:** editor resize/zoom thêm đối tượng bị miss; hai camera trùng track không trộn; source switch, sample trùng và sửa nhãn lại giữ provenance. Không cần chờ hook runtime để hoàn thành editor/import/validator với ảnh QA.

## 6. Slice C — Export/import đầy đủ và dùng được

Có nút tạo dataset trực tiếp từ nhãn đã duyệt; người dùng không bắt buộc xuất/nhập lại để train local.

Luồng ngoài ứng dụng:

`Export ZIP gồm ảnh + crop + nhãn + manifest → sửa nhãn bên ngoài → Import → Preview diff/errors/conflicts → Xác nhận`.

- Không chỉ export JSON với crop_media_id/đường dẫn máy gốc. Check ảnh/crop thực, hash và labels đầy đủ; thiếu file được báo, không đánh package ready.
- Detector: định dạng Ultralytics class/bbox; OCR: crop+text/line targets theo recognizer; char detector nếu dùng cần nhãn bbox ký tự thực. Không biến chữ toàn biển thành box ký tự đoán.
- Validator schema/version/class mapping/coordinates/decode/text/provenance. Unreadable/not_plate/wrong_association không trộn nhầm vào target positive.
- ZIP/path handling trong staging root: traversal/absolute path/symlink/file count/decompressed size có giới hạn. Import không ghi đè DB/media/models.
- Dedup/idempotency/conflict rõ; export cũ không overwrite label mới; preview số thật tạo/sửa/trùng/lỗi, giữ lịch sử.
- Round-trip export→import DB sạch so đủ ảnh/label/source/hash; gói import sửa chỉ áp dụng thay đổi được xác nhận, không mất dữ liệu ngoài batch.

**Test:** portable package, sửa một target/box bên ngoài rồi import đúng; nhãn lỗi từng sample, malicious ZIP, version conflict, hai import/restart và replay không nhân đôi.

## 7. Slice D — Dataset version và trainer thực

- Freeze dataset version trước job; sửa nhãn trong lúc job chạy tạo version khác.
- Chia70/15/15 theo video/phiên/lượt, các góc/crop/augmentation cùng xe cùng split. Policy cùng biển và near-duplicates được kiểm soát; holdout không bị đưa vào train sau khi dùng đánh giá mà vẫn giữ tên test độc lập.
- Audit label tự sinh và mẫu khó, thống kê class/quality/source, checker leakage. Chỉ augmentation train, giữ label hợp lệ; không gen chữ biển từ crop mất nét làm ground truth.
- Trainer riêng plate box, OCR chữ, mũ; chọn OCR engine/trainer tương thích bằng dữ liệu và docs/version, giữ EasyOCR baseline. Không chạy YOLO plate training rồi gọi là OCR training.
- Job queued/waiting_resource/preparing/training/evaluating/completed/failed/cancelled có progress/metrics/output; restart/cancel không nhân job. Một GPU job, output candidate riêng, base mapping/hash kiểm tra.
- Job smoke nhỏ phải chạy trainer thật và tạo candidate load được khi có tài nguyên. Fake trainer phục vụ tests không phải bằng chứng training thật.
- Dữ liệu chưa đủ: chuẩn bị validator/trainer/job/smoke và báo thiếu số mẫu/nhãn; không tự gán target mơ hồ hoặc train dài để thay chứng minh dữ liệu.

**Đạt:** crop/text người duyệt thực sự đi vào training input OCR; labels box đi vào detector; run/dataset/model/config/seed/version có provenance; job lỗi/OOM/cancel xử lý đúng, không overwrite active weights.

## 8. Slice E — So sánh candidate và rollout có rollback

- Baseline/candidate cùng holdout/input/runtime profile. OCR đo exact toàn biển, CER, coverage/review/abstain và sai/gán nhầm; detector/mũ đo precision/recall và case khó. Không lấy raw_nonempty_reads hoặc confidence làm accuracy.
- Regression dữ liệu cũ cùng dữ liệu mới; không promotion nếu candidate chỉ nhớ crop/biển vừa sửa rồi kém tình huống khác.
- Runtime FPS/latency/RAM/VRAM hai camera do adapter/bàn giao Task1; không duplicate inference benchmark khi Task1 đang chiếm GPU.
- UI model/dataset versions, so trước/sau, crop minh chứng, nút Áp dụng/Quay lại; admin chỉ chọn candidate đạt và runtime contract đúng. Không thay model nóng đang chạy bằng cách overwrite file .pt; lifecycle activation bàn giao Task1.
- Import model candidate khác import labels; artifact cần engine/class/checksum/config đúng, không thực thi file tùy ý từ gói labels.
- Giữ ngưỡng đã giao trong plan; thiếu>=30 biển rõ hoặc>=50 lượt vi phạm/50 clean thì chất lượng PENDING_DATA. Gương/matching vẫn review/OFF nếu chưa nghiệm thu.

**Đạt:** candidate so sánh được, không đạt giữ baseline, promotion/rollback QA hoạt động và không sửa prediction/evidence lịch sử.

## 9. Kiểm thử, tài liệu và tự tiếp tục

- Cập nhật todo/contracts/ownership/EXECUTION_LOG/ACCEPTANCE_REPORT riêng Task3. Log commands/env/versions/hash/counts/errors và shared patch status.
- Focused test mỗi slice; checkpoint A/B/C/D/E tự kiểm chứng, không hỏi người dùng duyệt lại từng bước.
- Sau tích hợp: full backend fresh process, Node/lint/build/Playwright qua production factory QA thật; không ignore/deselect/relax assertions để báo xanh.
- Test API/bbox/labels/export/import/split/jobs/eval đều có hành vi thực. Browser end-to-end: user nhập biển đúng → tạo dataset → export/sửa/import → job → so candidate → rollback. Không coi bản mock hoàn thành khi route/UI chưa tích hợp.
- Sử dụng interpreter project cho baseline; training riêng nếu cần phải ghi lệnh/path/version thực. Không chạy pytest đồng thời với task khác cùng basetemp/DB/media root; full integration regression có checkpoint phối hợp, focused test riêng vẫn tiếp tục.
- Không push/deploy/xóa dữ liệu vận hành hoặc thay camera. Không gửi message sang task khác nếu chưa được người dùng cho phép; bàn giao qua integration artifacts/ownership hiện có.

**Bắt đầu bằng Slice A và phần độc lập ngay.** Không kết thúc bằng “tôi sẽ đọc”, “muốn tiếp tục không” hoặc hỏi chọn bước điều tra. Khi cần góc nhìn/nhãn người thật/owner bàn giao/tài nguyên GPU, ghi blocker đúng và tiếp tục phần độc lập. Phân biệt code written/test passed/trained/evaluated/promoted; còn pending thì báo PARTIAL. Không tuyên bố model tự thông minh lên nếu mới lưu feedback mà chưa train/eval.
