# TASK 3 — Duyệt nhãn, export/import dữ liệu và huấn luyện có đối chứng

Ngày giao: 2026-10-02. Mục tiêu Task 3 được người dùng đổi từ tích hợp tổng sang **vòng cải thiện nhận diện bằng feedback và training**. Đây là kế hoạch bàn giao, chưa triển khai mã hoặc chạy training trong lượt lập kế hoạch.

## 1. Trải nghiệm người dùng cần đạt

Người dùng chạy camera/video nhiều lần, thấy ảnh/crop và kết quả máy, sửa khi sai, lưu nhãn đúng. Có thể tiếp tục duyệt trong ứng dụng hoặc export bộ dữ liệu để sửa nhãn ngoài rồi import lại. Từ dữ liệu đã duyệt, tạo dataset phiên bản, train candidate, so sánh với model đang dùng và chọn model đạt để áp dụng có rollback.

Luồng:

`Chạy thử → thu mẫu → máy gợi ý → người duyệt chữ/box/nhãn → dataset phiên bản → training offline → đánh giá độc lập → candidate → áp dụng sau khi đạt → tiếp tục thu lỗi mới`.

Feedback được lưu ngay, **weights không tự thay ngay khi bấm Đúng/Sai**. Feedback có thể sửa kết quả được duyệt trong bản ghi theo contract, nhưng không tự cập nhật roster, gán học sinh hoặc viết lại bằng chứng lịch sử. Dữ liệu ngày càng nhiều chưa bảo đảm model ngày càng tốt; mỗi bản cần đối chứng.

## 2. Tận dụng mã hiện có và phối hợp ownership

Đã đọc: `app/api/recognition_reviews.py`, feedback helpers trong `app/db.py`, `frontend/src/components/PlateReviewPanel.jsx`, `scripts/export_plate_dataset.py`, các script train plate/char/helmet.

- Đã có verdict correct/incorrect/unreadable/not_plate/wrong_association và corrected_text, feedback history/version/idempotency.
- Export hiện chủ yếu tạo JSON manifest và grouping, chưa phải bộ portable đủ ảnh + nhãn + import/validate + training vòng kín.
- PlateReviewPanel hiện do Task 1 giữ; DB/schema/factory và admin routes có Task 1/2 đang sửa. Không sửa chồng.
- Task 3 ưu tiên module/API/trang/dataset tools mới riêng, adapter tận dụng review hiện có. Mọi thay đổi hook thu mẫu runtime, router/nav, DB/schema hoặc panel do task khác giữ phải có patch/test bàn giao trong `tasks/task-03/integration/`. Chỉ tích hợp tuần tự khi file được bàn giao.
- Không thay auth strategy; giữ đăng nhập tự điền. Admin quản lý export/import/training/model; người duyệt được cấp quyền có thể gán nhãn theo quyền hiện hành. Không mở dữ liệu học sinh/crop cho mọi user đăng nhập.
- Không sửa capture/tracking/preview/loa để né lỗi Task 1; lỗi runtime phải được sửa trước khi dùng số đo runtime để đánh giá model. Task 3 có thể làm UI/dataset/train offline độc lập với phần chưa bàn giao.

## 3. Phân biệt nhãn và model được cải thiện

| Người dùng sửa | Dữ liệu cần lưu | Tác dụng |
|---|---|---|
| OCR đọc sai toàn biển | Crop nguyên gốc + chữ đúng, dòng trên/dưới khi có, trạng thái nhìn rõ và người duyệt | Dataset OCR chữ; không tự huấn luyện YOLO box |
| Box biển/mũ sai hoặc bị bỏ sót | Ảnh ngữ cảnh gốc + thêm/sửa/xóa bbox + class | Dataset detector |
| Đội mũ / không mũ | Bbox cùng quy ước vùng đầu + class có/không mũ; đầu khuất là unknown | Detector/nhánh mũ và kiểm tra ghép đầu-người |
| Ghép biển sai xe | Nhãn quan hệ giữa quan sát/xe, crop và track đúng, lý do | Tập đánh giá ghép/pipeline; không coi chữ đúng là biển đúng xe |
| Đi xe / dắt bộ | Đoạn video + khoảng thời gian + track và riding/pushing/walking/stationary/unknown | Đánh giá/huấn luyện hành vi; một ảnh không đủ làm nhãn chuyển động |
| Có/thiếu/khuất gương | Bbox gương nếu nhìn thấy, bên người lái và trạng thái vùng quan sát | Dataset gương khi góc phù hợp; không tạo box cho vật thể vắng mặt |

YOLO detector cần class + box theo định dạng chuẩn; OCR recognizer cần ảnh/chữ đúng theo engine được chọn. Nếu thử detector từng ký tự hiện có, phải có bbox/class từng ký tự; chuỗi toàn biển không tự biến thành các box ký tự chính xác.

Nguồn chính thức: [Ultralytics detection datasets](https://docs.ultralytics.com/datasets/detect/), [EasyOCR custom recognition models](https://github.com/JaidedAI/EasyOCR/blob/master/custom_model.md), [EasyOCR trainer](https://github.com/JaidedAI/EasyOCR/blob/master/trainer/README.md). Đối chiếu API/version thực cài trước khi triển khai; không nâng dependency môi trường vận hành để thử training.

## 4. T3.0 — Baseline và hợp đồng dữ liệu

- Đọc mã hiện tại sau thay đổi Task 1/2; ghi schema/API contract, model hash/mapping/config, ownership và git status. Không ghi credentials.
- QA dùng DB/media/dataset/output riêng, không migration/cleanup/seed trên dữ liệu thật trong test. Export phải đọc snapshot dữ liệu ổn định, không init_db/migrate DB vận hành ngầm.
- Xác định model/engine thực: plate detector, OCR EasyOCR hoặc char candidate review-only, helmet backup đúng lớp. Không train mũ từ checkpoint chỉ có lớp plate.
- Định nghĩa sample_id/review_id/label_version, ảnh/crop hash, nguồn video/camera/run/epoch/frame/time/encounter, transform từ ảnh gốc tới crop, model/config version và label provenance.

**Đạt:** contract phân biệt proposal và human label; test role/version và dataset QA không chạm dữ liệu/model vận hành.

## 5. T3.1 — Trang duyệt và chỉnh nhãn

Ưu tiên trang riêng “Dữ liệu huấn luyện” thay vì sửa trực tiếp GuardPage đang do Task 1 giữ. Có queue biển/mũ/box/hành vi, ảnh ngữ cảnh và vài crop tốt của cùng lượt xe, phóng to ảnh gốc và xem frame lân cận.

Với biển:

- Đúng: lưu chuỗi máy mà người dùng thực sự xác nhận; không chỉ lưu verdict bỏ trống target.
- Sai: nhập biển đúng, cho sửa hai dòng và dấu trình bày; lưu raw + canonical theo quy ước rõ.
- Không đọc được: loại khỏi OCR supervised positive, giữ làm case đánh giá unknown/reject.
- Không phải biển và Ghép nhầm xe có target khác, không ép thành OCR string.
- Muốn sửa box thì kéo/chỉnh/thêm/xóa box trên ảnh gốc, đổi class, undo và xác nhận; mapping letterbox/crop phải đúng. Không đoán box từ corrected_text.
- Được sửa lại nhãn đã duyệt, giữ lịch sử và người/thời điểm; optimistic version phải bằng version hiện tại, không nhận version tương lai. Idempotency key ràng buộc review/sample + người/payload; retry không nhân đôi hoặc replay sang sample khác.
- Submit thành công cập nhật đúng label/version mới; frontend không dùng version cũ trả về rồi bị409 ở lần sửa tiếp theo. Pagination/filter không reset offset mỗi lượt fetch; hủy phản hồi cũ khi đổi lọc.

Chỉ người có quyền được duyệt/cập nhật; giữ scope dữ liệu. Không auto-accept vì confidence cao. Mẫu khó được ưu tiên nhưng cũng lấy mẫu đúng/ảnh trống đa dạng để tránh chỉ học từ lỗi.

**Đạt:** browser sửa một biển sai → lưu → reload đúng → sửa lần nữa đúng; sửa bbox thêm đối tượng bỏ sót; conflict/retry/permissions đúng; không gán nhầm xe và không phát loa khi chỉ duyệt dataset.

## 6. T3.2 — Thu mẫu và quản lý phiên bản nhãn

- Tận dụng hook thu crop/review của Task 1 qua adapter đã bàn giao; không viết runtime khác. Thu từ camera đang dùng chỉ qua tính năng người dùng bật rõ; QA replay video cách ly.
- Giữ ảnh nguồn chưa overlay, crop lossless/phù hợp OCR, bbox/transform, timestamp và frame identity. Dedup exact hash, gần trùng và nhiều frame cùng lượt; không để một xe lặp hàng nghìn lần áp đảo dataset.
- Một lượt có vài crop tốt/khó kèm chất lượng mờ/chói/khuất/nhỏ/nghiêng; không lưu vô hạn. Có quota/retention dữ liệu training riêng và báo dung lượng, không xóa chứng cứ vận hành còn hạn.
- Nhãn suy từ frame rõ khác phải có provenance cùng track/lượt đã kiểm chứng. Không dùng một biển đọc được của xe gần đó gán cho crop mờ. Mẫu không thể xác định giữ unknown.
- Với nhãn gương/hành vi thiếu góc/đoạn video, ghi thiếu; tiếp tục OCR và mũ trước. Model gợi ý tự động chỉ là pre-label pending cần người duyệt.

**Đạt:** hai camera cùng track ID không trộn sample; source switch/replay không tạo target sai; ảnh/crop và label có thể truy ngược nguồn và không mất vì cleanup nhầm.

## 7. T3.3 — Export/import portable và kiểm tra lỗi nhãn

Có hai lựa chọn thao tác:

1. Duyệt trong app → tạo dataset trực tiếp, không bắt người dùng export/import mỗi vòng.
2. Export gói ZIP → gán/sửa nhãn ngoài (CVAT hoặc công cụ tương thích) → import lại → preview diff → xác nhận áp dụng nhãn.

Gói gồm ảnh thật, crops, labels, manifest/class mapping có version, schema, hashes, source/group IDs và hướng dẫn. Detector export Ultralytics khi phù hợp; OCR export crop + text/line labels phù hợp recognizer. Bộ dữ liệu portable không chỉ có đường dẫn tuyệt đối trên máy gốc.

Import phải:

- Kiểm schema/class mapping/hash/ảnh decode được/bbox giới hạn/chuỗi target, thiếu/trùng ID và provenance.
- Preview số mới/sửa/trùng/xung đột/lỗi; không tự sửa âm thầm label không khớp mapping.
- Replay idempotent; import khác nội dung cùng ID/version phải có conflict/merge có kiểm soát, giữ lịch sử. Không ghi đè nhãn mới hơn bằng export cũ.
- Bảo vệ path traversal/absolute path/symlink, số file/kích thước giải nén; chỉ ghi staging dataset root. Không giải nén đè media/DB/models.
- Export→import DB sạch phải khôi phục đủ ảnh/nhãn/provenance; gói mới hơn vào DB đã có chỉ thay sample được duyệt trong preview.
- Không nhập arbitrary model weights như nhãn; import dataset và import candidate model là hai luồng riêng.

**Đạt:** round-trip đủ dữ liệu, nhãn sai có lỗi từng sample, sửa đúng được áp dụng một lần và không phá nhãn/camera đang vận hành.

## 8. T3.4 — Dataset freeze và chia tập chống leakage

- Đóng băng dataset version trước train; sửa nhãn trong lúc train tạo version tiếp theo, không thay đầu vào job đang chạy.
- Chia70/15/15 theo video/phiên và nhóm liên quan. Hai camera/crop/augmentation/encounter cùng lượt ở cùng split. Với mục tiêu tổng quát hóa OCR, kiểm soát cả cùng biển/lặp xe giữa train và test; ghi policy/grouping rõ, không chỉ tách review_id.
- Test holdout cố định, không đưa lỗi của test vào training rồi tiếp tục gọi đó là test độc lập. Mẫu test được dùng để chỉnh phải chuyển vai trò và cần holdout mới.
- Rà nhãn tự sinh, lần hai>=20% và mọi mẫu khó; thống kê class/quality/source, cảnh báo imbalance và missing labels.
- Tăng cường blur nhẹ, ánh sáng, perspective/noise từ ảnh có nhãn đúng ở train split. Không làm mất chữ hoàn toàn rồi coi crop đó là positive đọc được; không đánh giá trên ảnh synthetic thay video thật. Không gen biển “sắc nét” từ ảnh mờ để dùng như bằng chứng/ground truth.

**Đạt:** validator phát hiện leakage/class mapping lệch và dataset ready chỉ khi samples/labels thực hợp lệ; số thiếu ghi rõ.

## 9. T3.5 — Training jobs offline có giới hạn tài nguyên

- Tách job train plate detector, OCR recognizer, helmet. Sửa chữ biển chỉ cung cấp target OCR; phải chọn/triển khai trainer có thể nhận crop/text và runtime adapter tương thích. Không giả vờ train OCR bằng cách chạy YOLO plate detector.
- Giữ baseline EasyOCR và model đang dùng. Thử OCR tùy chỉnh/char approach trong môi trường riêng dựa trên dữ liệu, không đổi engine chỉ vì có script. Char model cần labels ký tự thật; full strings không tự tạo char annotations chuẩn.
- Job rõ trạng thái queued/preparing/training/evaluating/failed/cancelled/completed, progress/epochs/metrics/output, cancel/resume nếu engine hỗ trợ. Restart không tạo job hoặc candidate trùng.
- Một job GPU training mỗi lần trên RTX3050 4GB; batch/workers/imgsz đo theo khả năng thật. Không hứa batch16 an toàn hoặc “full tài nguyên” cùng inference. Mặc định train ngoài ca/QA hoặc ở máy riêng; thu/duyệt dữ liệu vẫn có thể tiếp tục mà không chạy train ngay.
- Nếu train cùng camera, chỉ cho phép khi đo được ngân sách preview/AI/VRAM và chính sách giảm tải; không làm giật camera hoặc hạ chuẩn xác nhận để giữ job.
- Base checkpoint/model class phải đúng nhiệm vụ, code/version/hyperparams/seed/dataset hash được ghi. Candidate lưu output riêng, không ghi đè models active. Không broad-upgrade dependency hoặc tự upload dữ liệu học sinh/video lên cloud.

**Đạt:** train job smoke trên dataset nhỏ hợp lệ tạo model load được; eval dùng holdout; lỗi/OOM/cancel có trạng thái đúng và không phá camera/model hiện hành. Nếu dữ liệu thiếu, hoàn thành trainer/validator/smoke nhưng training chất lượng vẫn PENDING_DATA.

## 10. T3.6 — Đánh giá trước/sau và candidate promotion

So baseline và candidate trên cùng holdout/video/cấu hình, báo:

- Detector precision/recall/mAP và lỗi box/head association.
- OCR exact toàn biển, CER hoặc lỗi ký tự, tỷ lệ đọc được, tỷ lệ abstain/review, sai biển và ghép nhầm xe. Confidence model không phải độ chính xác.
- Mũ/hành vi: precision/recall theo lượt và loại lỗi, nhóm mờ/xa/chói/đông người riêng.
- Runtime hai camera: AI/preview FPS, latency, RAM/VRAM và thời gian OCR; candidate chính xác hơn nhưng quá chậm chưa đạt.

Giữ mục tiêu đã chốt: lỗi đọc loa precision>=95% từng loại, recall>=70% trường hợp rõ; OCR toàn biển>=50% trên>=30 biển rõ; >=50 lượt vi phạm và>=50 lượt không vi phạm rõ. Không coi repeated frames/loop là mẫu độc lập; dữ liệu nhỏ báo counts/uncertainty và PENDING, không chứng minh “chuẩn doanh nghiệp”.

Candidate không được chỉ học dữ liệu mới mà làm kém tình huống cũ; mix old/new theo dataset policy và có regression. Không bắt buộc mỗi lần train phải promotion; nếu không vượt baseline giữ model cũ, báo nguyên nhân.

UI có “So sánh bản hiện tại/bản mới”, minh chứng crop sai→đúng/sai mới, model/dataset version, “Áp dụng” và “Quay lại”. Chỉ admin áp dụng candidate đã kiểm hash/class/runtime contract và tiêu chí. Đổi model có lifecycle/source generation phù hợp qua patch Task1; không nóng ghi đè checkpoint đang chạy. Model mới không sửa dự đoán/bằng chứng lịch sử.

**Đạt:** promotion/rollback hoạt động trên QA, candidate chưa đạt không được tự bật, bản đang chạy và reason đầy đủ.

## 11. Ảnh mờ và xe đi nhanh: cải thiện khả năng đọc, không bịa chữ

Với xe nhanh, ưu tiên dữ liệu nguồn đủ nét, nhiều frame liên tiếp, chọn crop rõ và voting có kiểm chứng. Dùng phối cảnh/line ordering/preprocessing phù hợp; learned robustness từ mẫu thực đã gán đúng có thể giúp ảnh mờ vừa phải.

Nếu mọi frame đều mất chi tiết, không thể bảo đảm khôi phục đúng biển. Không suy ra theo roster/biển gần giống hoặc ép format thành một số cụ thể để đạt read rate. Khi không đủ bằng chứng, hiển thị chưa đọc rõ và cho người duyệt; ảnh làm sắc nét chỉ là hỗ trợ nhìn, không ground truth mới.

Exposure/ánh sáng/góc camera có ảnh hưởng đến blur; Task1/đợt nghiệm thu thiết bị đề xuất và đo thay đổi khi được phép, Task3 không tự chỉnh Imou đang vận hành. FPS cao không tự bảo đảm shutter nhanh hay crop nét.

## 12. Kiểm thử và bàn giao

Thứ tự: T3.0→T3.1→T3.2→T3.3→T3.4→T3.5→T3.6. Trong lúc Task1/2 giữ shared files, hoàn thành schema contract/mock adapter/UI/module/tools riêng; chờ tích hợp không chặn mọi phần độc lập.

Test bắt buộc: feedback đúng/sai/unknown, sửa lại/history/version tương lai/retry/key khác review; bbox/letterbox/không nhãn/mũ cầm tay; scope; export/import round-trip/malformed ZIP/conflict/dedup; split leakage; freeze dataset; train smoke/OOM/cancel/restart; eval độc lập; promotion/rollback; browser complete loop user sửa biển→dataset→job→candidate→so sánh.

Focused tests mỗi slice; backend full regression + Node/lint/build/browser sau tích hợp, môi trường cách ly. Không bỏ test hoặc nới assertion để báo xanh; không dùng dataset lớn/train dài thay smoke nhanh kiểm đúng hợp đồng.

Bàn giao trong `tasks/task-03/`: ownership/contracts/todo/log, sample/schema/label guide, export/import guide, training/evaluation/model reports, acceptance với PASS/FAIL/PARTIAL/PENDING và lệnh thực/version/hash. Không push/deploy/xóa DB/media/model vận hành. Không hỏi lại sau từng checkpoint; thiếu nhãn/thiết bị ghi đúng phần chưa xác nhận và tiếp tục phần độc lập.

**Không tuyên bố “tự thông minh lên” chỉ vì lưu feedback:** phải chứng minh nhãn đúng, dữ liệu dùng bởi trainer, candidate cải thiện trên holdout và runtime dùng đúng bản đã nghiệm thu.
