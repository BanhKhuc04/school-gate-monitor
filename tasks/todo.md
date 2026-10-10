# Công việc camera

## Đợt 6 — chốt demo và bàn giao trước 01:00 ngày 04/10/2026

**Đọc trước:** [Prompt giao Cursor](task-06-demo-2026-10-04/NEXT_CURSOR_PROMPT.md).
Kế hoạch/checklist: [plan](task-06-demo-2026-10-04/PLAN_BEFORE_0100.md),
[todo](task-06-demo-2026-10-04/todo.md). Nội dung 12 slide:
[slides](task-06-demo-2026-10-04/SLIDES_CONTENT.md); demo 7 phút:
[runbook](task-06-demo-2026-10-04/DEMO_RUNBOOK.md).
Đợt này nối tiếp R0–R15, thêm offline LAN/audio/VPS/marketing/slides/release;
giữ toàn bộ lịch sử dưới đây. Kế hoạch không phải xác nhận demo đã đạt.

## Đợt mới đã phê duyệt 03/10/2026

Backlog triển khai: [task-05/todo.md](task-05/todo.md).
**Bàn giao Cursor phần còn lại:** [task-05/CURSOR_HANDOFF.md](task-05/CURSOR_HANDOFF.md),
R0–R15 theo trạng thái mới nhất; đọc trước các prompt/checklist cũ bên dưới.
Hợp đồng/KPI: [task-05/plan.md](task-05/plan.md). Checklist lịch sử bên dưới được giữ nguyên.

- [x] C1 — Capture: chuẩn hóa chuỗi index, phân biệt file/URL, timeout mạng, release khi lỗi. Files: capture.py, camera_sources.py, test_camera_capture.py. Nghiệm thu: "0" mở thiết bị số 0; RTSP không seek EOF; lỗi không rò capture. Kiểm chứng: pytest focused. Không phụ thuộc.
- [x] C2 — Chuyển nguồn: giữ instance/model, xác minh first frame trước lưu, giữ nguồn cũ khi lỗi, chặn yêu cầu trùng, xóa cache nhận diện. Files: camera_switch.py, pipeline.py, test_camera_switch.py. Nghiệm thu: nguồn lỗi không thay DB/capture; chuyển thành công tiếp tục stream; startup offline vẫn nhận đổi nguồn. Phụ thuộc C1; pytest focused.
- [x] C3 — API: xác thực admin, gate 404, payload 422, 202 pending, 409 busy, trạng thái che credentials. Files: api/camera.py, test_camera_api.py. Phụ thuộc C2; TestClient với DB tạm và capture giả.
- [x] C4 — UI: lựa chọn rõ ràng, loading/error theo cổng, khóa thao tác đang chạy, polling trạng thái, preview, nhắc ROI. Files: AdminCameraPage.jsx, test_camera.spec.js. Phụ thuộc C3; Playwright Chromium + build + lint.
- [x] C5 — Rà soát và báo cáo: chạy suite, phân biệt lỗi sẵn có và regression; ghi đánh giá kiến trúc, ưu tiên và giới hạn vào docs/ARCHITECTURE_CAMERA_REVIEW.md. Phụ thuộc C1–C4.

Checkpoint: không thay camera/DB đang vận hành để kiểm thử; không ghi đè các kế hoạch cũ ở root/docs.

## Tiếp nối front/rear — kế hoạch Cursor 01/10/2026

Chi tiết và hợp đồng: `docs/CURSOR_FRONT_REAR_RECOGNITION_PLAN_2026_10_01.md`. Đây là checklist bàn giao, chưa triển khai trong lượt lập kế hoạch.

- [ ] FR0 — Baseline và lý do chưa cảnh báo. Nghiệm thu: môi trường test riêng, mỗi lượt có stage/reason thật; test loa không ghi vi phạm vào DB thật. Kiểm chứng: focused guard/recognition tests + browser nghe thử. Phụ thuộc: không. Files: pipeline.py, guard.py, RecognitionLogPanel.jsx, tests chẩn đoán. Scope: M.
- [ ] FR1 — Khởi tạo/vòng đời theo camera_id. Nghiệm thu: hai nguồn cùng gate, trạng thái/epoch độc lập, switch 202 tương thích; một camera lỗi không dừng camera kia. Kiểm chứng: hai capture giả cùng track ID + camera API tests. Phụ thuộc FR0. Files: pipeline.py, camera.py, camera_switch.py, tests camera runtime. Scope: M.
- [ ] FR2 — Profile front/rear. Nghiệm thu: rear không cần person để có crop/OCR; không nạp pose/mũ rear mặc định. Kiểm chứng: test xuyên luồng và model-instance count. Phụ thuộc FR1. Files: config.py, pipeline.py, detector.py, tests profile. Scope: M.
- [ ] FR3 — Capture/hiển thị độc lập AI. Nghiệm thu: chặn AI/OCR vẫn có frame mới, latest-only và JPEG shared, overlay hết hạn. Kiểm chứng: fake slow inference, viewer và source-switch tests; đo GPU queue. Phụ thuộc FR2. Files: capture.py, pipeline.py, guard.py, tests capture/display. Scope: M.

Checkpoint FR0–FR3: focused + backend suite + frontend lint/build; hai camera, role, trạng thái nguồn và nghe thử đi qua app thật. Không tuyên bố camera thật đạt nếu mới dùng nguồn giả.

- [ ] FR4 — Vùng đọc rear và best crop. Nghiệm thu: native crop đúng tọa độ, rear trigger riêng, best thay trước freeze, OCR 1/1; thông số sensor cần người kiểm tra được ghi rõ. Kiểm chứng: crop/ROI/quality tests và ảnh nguồn đứng yên/di chuyển. Phụ thuộc FR3. Files: best_plate.py, pipeline.py, AdminRoiPage.jsx, tests best crop. Scope: M.
- [ ] FR5 — Reader ký tự review-only. Nghiệm thu: đúng model 36 ký tự, runtime engine thật, không tự gán học sinh từ candidate; strict decoder bảo vệ ký tự thiếu. Kiểm chứng: decoder/model contract + same-crop video comparison. Phụ thuộc FR4. Files: reader adapter, pipeline.py, config.py, tests reader. Scope: M.
- [ ] FR6 — API/DB feedback. Nghiệm thu: provenance immutable, correct/incorrect/unreadable/wrong association, idempotency/version/permissions. Kiểm chứng: DB tạm, replay/409/authorization tests. Phụ thuộc FR5. Files: db.py, schemas.py, router feedback, tests feedback. Scope: M.
- [ ] FR7 — Thẻ ảnh duyệt biển. Nghiệm thu: ảnh gốc+đề xuất, tích đúng/nhập sửa, reload giữ feedback; rear chưa ghép hiện riêng. Kiểm chứng: browser thật, network/error/version conflict. Phụ thuộc FR6. Files: RecognitionLogPanel.jsx, GuardPage.jsx, API client, browser tests. Scope: M.

Checkpoint FR4–FR7: crop nguồn và feedback đi xuyên UI/API/DB; thử reader chỉ review, giữ weights vận hành; chạy suite/lint/build, không dùng format đúng để chứng minh chuỗi đọc đúng.

- [ ] FR8 — Hành vi và gương đúng góc trước-phải. Nghiệm thu: chân thiếu không thành dắt bộ, unknown không báo riding, mũ đúng vùng đầu; gương khuất unknown/review-only. Kiểm chứng: SideViewRiding/helmet/crossing tests + clip có nhãn. Phụ thuộc FR2; dữ liệu thiếu ghi rõ. Files: pose.py, helmet_contract.py, pipeline.py, tests perception. Scope: M.
- [ ] FR9A — Chính sách audio backend. Nghiệm thu: front không chờ rear nhiều giây; rear pending không thành vi phạm giả; một audio intent/lượt, thông báo chưa đọc rõ khác lỗi kỹ thuật. Kiểm chứng: event aggregation/deadline/evidence behavior tests. Phụ thuộc FR0, FR7, FR8. Files: config.py, crossing_alert.py, pipeline.py, tests audio policy. Scope: M.
- [ ] FR9B — Loa browser ngắn/nhanh. Nghiệm thu: một beep/câu, rate 1,45 thử và clamp 1,0–1,6, lease/gesture rõ; tốc độ nghe thực áp dụng. Kiểm chứng: Node behavior tests + browser onstart/error + nghe thực. Phụ thuộc FR9A. Files: alertAudio.js, speak.js, AlertBanner.jsx, browser tests. Scope: M.
- [ ] FR10 — Dataset từ feedback. Nghiệm thu: xuất nhãn/provenance theo session/encounter, feedback string không giả làm bbox ký tự; holdout độc lập; synthetic train-only nếu thử. Kiểm chứng: dataset validation, split leakage tests và người rà. Phụ thuộc FR6. Files: script export, manifest schema, tests dataset, tài liệu label. Scope: M.
- [ ] FR11A — Benchmark video/ghép. Nghiệm thu: phép đo hai nguồn/1–3 viewer cách ly 30 phút; ghép mặc định tắt khi chưa hiệu chỉnh; FPS mới, latency, queue, tài nguyên, rollback. Kiểm chứng: nguồn cách ly + cặp video có nhãn; không dùng hai video độc lập để chứng minh ghép. Phụ thuộc FR3–FR10. Files: script benchmark, report, log; triển khai ghép nếu cần là task riêng sau hợp đồng đã kiểm chứng. Scope: M.
- [ ] FR11B — Nghiệm thu thiết bị thật. Nghiệm thu: ảnh ngày/tối, field accuracy/false acceptance/coverage; hai Imou ca 12 giờ và backup/restore theo kế hoạch trước. Kiểm chứng: thiết bị/nhãn thật, đo đồng hồ và log đầu–giữa–cuối ca. Phụ thuộc FR11A và thiết bị. Files: report, log, cấu hình test riêng. Scope: M về thiết lập/báo cáo; phép đo endurance kéo dài theo ca.

Checkpoint cuối: phân biệt mã/test/video/camera thật; không hạ threshold để hoàn tất; báo các mục chưa đủ thiết bị/nhãn. Giữ các công việc độc lập tiến liên tục.

## Bổ sung 03/10/2026 — sửa crop biển số và chuẩn bị train OCR

Phát hiện qua Nhật ký vi phạm (ảnh đính kèm 03/10/2026): crop biển vào review panel hiện lấy ảnh đầy đủ/biển rỗng/sai bbox — không phải lỗi đơn lẻ mà vấn đề hệ thống. EasyOCR pretrained + CPU đọc rất kém trên crop thực tế. Phần bổ sung này chạy song song FR5–FR11B; nếu sửa xong trước khi FR5/FR10 chạy thì FR5 vẫn dùng reader mới.

**Máy:** RTX 3050 4GB (đã xác nhận `nvidia-smi`) — chưa có torch/paddle trong Python311 global; cần dùng đúng venv backend.

### Giai đoạn A — chẩn đoán (làm trước, không code)

- [ ] A1 — Số liệu thật trong DB. Nghiệm thu: biết đúng tỉ lệ rỗng/rỗng-dòng/đúng-1-dòng/đúng-hết/đọc-sai-ký-tự trên 200 vi phạm gần nhất. Kiểm chứng: SQL GROUP BY trên `plate_read` của `violation_events`, kèm 5 mãnh có `crop_snapshot_path` để xem bằng mắt. Phụ thuộc: không. Files: truy vấn ad-hoc, không sửa app. Scope: S.
- [ ] A2 — Reader đang chạy CPU hay GPU. Nghiệm thu: biết backend hiện dùng `DEVICE=cpu` hay `gpu`; thời gian trung bình 1 lần readtext; crop có thực sự qua `_preprocess_plate_crop` không. Kiểm chứng: in log `[OCR]` lúc startup, đo pympy 30 lần readtext trên 5 crop thật. Phụ thuộc: không. Files: `app/config.py` DEVICE, `app/cv/ocr.py`. Scope: S.
- [ ] A3 — Ảnh crop gốc. Nghiệm thu: 10 crop gần nhất phân loại được (đúng biển / nhầm cảnh / mờ / xa / nghiêng). Kiểm chứu: lấy `crop_snapshot_path` qua `/api/media/snapshots/{id}`, mở bằng mắt. Phụ thuộc: A1. Files: không. Scope: S.

### Giai đoạn B — sửa crop tốt hơn (theo ý tưởng xoay 2 đỉnh đáy)

- [ ] B1 — Crop lưu nhiều biến thể. Nghiệm thu: 1 lần detect biển → lưu 3–5 crop (gốc + xoay theo 2 đỉnh đáy + tăng tương phản + adaptive threshold) vào DB kèm `variant` và `bbox` riêng. OCR chạy trên cả 3–5 thay vì 1. Kiểm chứu: test reprocess 1 track, đếm so với baseline; crop lưu phải xem được qua `/api/media/snapshots/`. Phụ thuộc: A1-A3. Files: `app/cv/best_plate.py`, `app/cv/plate_preprocess.py`, `db.py`, tests. Scope: M.
- [ ] B2 — Xoay biển theo 2 đỉnh đáy (ý tưởng từ ảnh 03/10). Nghiệm thu: contour 4 đỉnh → lấy 2 đỉnh thấp nhất → tính góc quay bằng `tan()` → xoay về chính diện. Hỗ trợ biển nghiêng trái/phải ±20°. Kiểm chứu: unit test trên 5 ảnh nghiêng thật + 1 synthetic xoay ±30°. Phụ thuộc: B1. Files: `app/cv/plate_preprocess.py` mới hoặc module `rectify_v2.py`. Scope: M.
- [ ] B3 — Lọc theo chất lượng KHÔNG bỏ mẫu. Nghiệm thu: mọi crop đều được ghi nhận (kể cả mờ) nhưng chỉ crop `quality_score ≥ PLATE_BEST_MIN_QUALITY` (0.65 hiện tại) mới ghi `plate_read`. Crop mờ được lưu vào review dataset (label "unreadable" sau). Kiểm chứu: kiểm thử DB đếm row crop vs row có plate. Phụ thuộc: B1. Files: `app/cv/best_plate.py`, `db.py`. Scope: S.

### Giai đoạn C — train reader mới (song song B)

- [ ] C1 — Cài PaddleOCR GPU trong venv backend. Nghiệm thu: import paddle OK, `paddle.device.is_compiled_with_cuda() == True`, EasyOCR cũ vẫn chạy (không phá vỡ). Kiểm chứu: `python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"` trong venv. Phụ thuộc: A2. Files: `requirements.txt`. Scope: S.
- [ ] C2 — Adapter PaddleOCR song song EasyOCR (review-only). Nghiệm thu: mỗi crop qua cả EasyOCR + PaddleOCR; kết quả PaddleOCR xuất hiện trong `RecognitionLogPanel` (cột "reader khác") nhưng KHÔNG tự gán học sinh — giống FR5 char-plate. Kiểm chứu: test xuyên pipeline với fake readers; browser thấy cả 2 đề xuất. Phụ thuộc: C1, FR6. Files: `app/cv/ocr.py` adapter, `RecognitionLogPanel.jsx`, tests. Scope: M.
- [ ] C3 — So sánh EasyOCR vs PaddleOCR. Nghiệm thu: ≥100 crop đã được admin duyệt (đúng/sai rõ), đo agreement rate, character-level accuracy, latency CPU vs GPU. Kiểm chứu: script offline đọc `recognition_reviews` + `feedback`, chạy cả 2 reader, sinh báo cáo. Phụ thuộc: FR6, C2. Files: script `scripts/ocr_benchmark.py`, `docs/OCR_BENCHMARK_2026_10_03.md`. Scope: M.
- [ ] C4 — Bật PaddleOCR mặc định (nếu C3 cho kết quả tốt hơn). Nghiệm thu: `PLATE_READER=paddleocr` qua env, runtime ≥20 FPS trên 1 camera, accuracy số cao hơn baseline hiện tại. Giữ EasyOCR làm fallback khi PaddleOCR fail. Kiểm chứu: focused OCR test + benchmark 30 phút 1 camera. Phụ thuộc: C3. Files: `app/config.py`, `app/cv/ocr.py`. Scope: M.

### Checkpoint A-B-C: crop có ≥3 biến thể; reader mới chạy song song; benchmark có số liệu thật trước khi đổi mặc định. Không dùng số tổng hợp để "chứng minh" reader mới tốt hơn.

### Rủi ro cần theo dõi
- RTX 3050 4GB VRAM — mô hình PaddleOCR `v4` mặc định có thể không vừa; phải dùng `mobile` hoặc `server` đúng cấu hình.
- PaddleOCR Python wheel cho Windows + CUDA 13.3 có thể chưa có bản chính thức → có thể cần chạy Python 3.10 venv riêng.
- Backend hiện chạy Python311 global (thiếu easyocr) → venv backend phải có torch+paddle+easyocr cùng lúc.
- Không tự train weights trước khi có ≥500 mẫu có feedback đúng/sai thật từ FR6.

