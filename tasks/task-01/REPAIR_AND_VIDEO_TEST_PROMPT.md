# TASK 1 — Vá lỗi review và kiểm chứng toàn bộ video

Ngày giao: 02/10/2026. Repository: `D:/Work/Project_motorbike`.

Bạn tiếp tục TASK 1 đã triển khai, sửa các lỗi review rồi kiểm chứng toàn bộ hệ thống trong môi trường cách ly. Đây là yêu cầu thực thi: đọc → tái hiện → sửa → chạy test → chạy video → báo cáo bằng chứng. Không kết thúc ở lời hẹn sẽ đọc hoặc sẽ dùng agent.

## 1. Đọc đúng hiện trạng, không triển khai lại từ đầu

Đọc:

- `tasks/task-01/plan.md`, đặc biệt mục 8 về tiếp tục thực thi.
- `tasks/task-01/OWNERSHIP.md`, `CONTRACTS.md`, `todo.md`, `EXECUTION_LOG.md`.
- `docs/CODEX_TASK01_REVIEW_2026_10_02.md` — các lỗi F01–F09.
- `tasks/task-02/plan.md` và ownership các task khác nếu có.

Review đã chạy lại bảy file Phase 0–6: 159 passed, 1 warning. Các ca bổ sung vẫn tái hiện lỗi runtime/OCR/crossing/matcher. Không lấy 342 test được chọn hoặc 159 unit test làm bằng chứng hoàn thành pipeline.

Ghi git status, commit/baseline, diff liên quan và dependency/interpreter thực cài. Đối chiếu lại từng F01–F09 vì code có thể đã đổi. Giữ phần đúng, chỉ sửa lỗi còn tái hiện và phần chưa nối runtime.

Không ghi đè thay đổi chưa commit. Không sửa chồng Task 2. File DB/schema/config/main/fixture dùng chung phải theo ownership, bàn giao/tích hợp tuần tự. Không đợi toàn bộ task khác commit mới làm báo cáo riêng: chỉ cần ghi snapshot và dependency tích hợp chính xác.

## 2. QA phải cách ly trước khi chạy

- Backend interpreter bắt buộc `.\venv\Scripts\python.exe`, không dùng global Python.
- Tạo run ID, thư mục DB/media/clip/log/report tạm riêng cho lượt QA. DB dùng schema thật hoặc SQLite Backup API tạo bản sao nếu cần, không dùng DB vận hành.
- Kiểm tra resolved path DB/snapshot/crop/clip/review/upload/backup/recording đều trỏ QA root. Cấu hình hiện tại có đường dẫn bind lúc import; không chỉ đổi APP_DB_PATH rồi giả định mọi media đã cách ly.
- Tạo app bằng factory thật, router/middleware thật với cấu hình QA; capture video được cho phép, RTSP thật và maintenance trên dữ liệu vận hành tắt. Request health/recognition không được tự tạo pipeline khác.
- Chặn startup nếu DB/media trỏ production hoặc source là RTSP thật. Không dựng API giả khác hoàn toàn rồi coi đã kiểm tra bản production.
- Không đổi nguồn/exposure/firmware Imou, không kill backend/task khác, không sửa mật khẩu thiết bị, không xóa DB/media/models/video, không push/deploy.
- Không nâng dependency, train hoặc thử model mới trên môi trường đang chạy. Chỉ một job GPU nặng tại một thời điểm; khi GPU đang được task khác dùng, tiếp tục unit/API/UI độc lập và bố trí phép đo sau.
- Không ghi mật khẩu RTSP/JWT/thông tin học sinh thật vào log/report. Dataset video gốc chỉ đọc; các file tạo ra nằm dưới QA output.

## 3. Sửa theo thứ tự dưới đây

### R1 — Profile front/rear/minimal phải chạy loop thật

Vá F01:

- Init đã bỏ person detector ở rear nhưng live loop vẫn gọi `None.detect_tracked`. Dispatch theo capability thực, có future/result rõ ràng cho nhánh tắt.
- Rear phải có vehicle/plate tracking hoặc nhánh tracking phù hợp để plate OCR không phụ thuộc person. Không sửa bằng cách trả groups rỗng khiến camera không còn nhận diện.
- Minimal phải hiển thị hình dù không có detector/pool; stop/shutdown không gọi `.shutdown()` trên None.
- Tách lỗi inference khỏi lỗi capture; lỗi model không tự reconnect camera tốt. Health/card nêu chức năng thiếu, không báo mọi model ready khi không nạp.

**Test bắt buộc:** dùng capture/detector giả chạy vòng loop thực cho full/ocr_only/minimal; rear không có người vẫn phát hiện plate, tạo track và gửi OCR; model lỗi không gây reconnect; stop từng profile không lỗi. Không thay test bằng assert đường dẫn model tồn tại hoặc hằng số config >0.

### R2 — Preview và JPEG không chờ AI

Vá F02:

- Luồng đọc latest frame và nhịp preview/encode độc lập detect/pose/OCR/DB/clip. AI không giữ khóa frame qua inference.
- Encode một lần mỗi frame hiển thị mới, chia sẻ viewer; gắn camera/epoch/seq/receive monotonic. FPS hiển thị chỉ đếm frame mới.
- Native frame chưa vẽ dùng cho OCR/bằng chứng. Overlay hết hạn sau 500ms; không vẽ box/skeleton cũ trên xe mới.
- Giữ buffer/copy/job hữu hạn; stop/source change vô hiệu hóa kết quả cũ, không tạo worker mồ côi hoặc chồng reader khi chưa dừng được phiên trước.

**Test bắt buộc:** block Future detect/pose và DB write, JPEG seq/timestamp vẫn tiến; block OCR không đứng preview; frame skip/trống vẫn có hình mới; hai viewer không nhân encode; source change bỏ overlay/result cũ; stop trong lúc worker đang chạy không phát alert phiên cũ.

### R3 — OCR multi-crop phải hoạt động trong đường xử lý chính

Vá F03/F04:

- OCR bắt đầu khi crop đủ chất lượng, không đợi person/gate line/crossing/vi phạm. Xe không vi phạm vẫn hiện card và kết quả OCR.
- Thay một attempt vĩnh viễn bằng tối đa 3–5 crop tốt khác frame mỗi lượt, có diversity/quality/TTL/budget. Một job chạy/chờ mỗi track, global cap tám; không fallback đồng bộ.
- Mỗi job mang camera/source epoch/frame/crop/encounter identity; collect đúng một lần, late/stale result bị loại. Retry kỹ thuật hoặc cùng crop không thành phiếu mới.
- Consensus là nguồn xác nhận chính cho lookup/gán xe/học sinh. Không cho `resolve_plate()` một crop confident bypass consensus. Phân biệt OCR thử và biển confirmed trong API/card.
- Ít nhất hai crop khác frame đọc trùng toàn biển và đạt chất lượng; mẫu cạnh tranh đáng tin phải giữ needs_review theo chính sách đã ghi. Không coi hai phiếu thắng một phiếu đối chứng confidence cao là chắc chắn.
- Quality thực là điều kiện hợp lệ, không chỉ field tính rồi bỏ; crop quá nhỏ/mờ/chói/khuất hoặc quality 0 không được tính như bằng chứng tốt. Các ngưỡng có phiên bản, chỉnh trên validation.
- Giữ top crop theo chất lượng/diversity phù hợp, không quảng cáo top-N khi chỉ giữ N mẫu gần nhất. Khi đạt max tracks, update track đang có không được eviction nhầm chính track hoặc track đang chờ OCR.
- Char reader giữ shadow/review-only đến khi được đánh giá tốt hơn baseline. Không đoán hoặc tự sửa ký tự để ép thành biển roster.

**Test bắt buộc:** chạy qua detector/resize/ROI/tracking/crop/worker/consensus/card thật với detector và OCR inference giả. Hai frame hợp lệ mới confirmed; một frame không confirmed; thiếu line/person vẫn OCR; crop thứ hai tốt hơn được xử lý; A(.8), B(.99), A(.8) cần kiểm tra; quality 0 không confirmed; duplicate/out-of-order/old epoch không tăng mẫu; hai xe cùng track number ở hai camera không trộn; crop mũ/biển dùng ảnh chưa vẽ và tọa độ đúng native frame.

### R4 — Crossing đúng khoảng thời gian và temporal theo từng xe

Vá F05/F06:

- Crossing yêu cầu ba frame ổn định phía đầu và ba frame mới phía đích. Giới hạn năm giây phải xử lý cả khoảng mất quan sát giữa hai phía, không chỉ đếm từ frame đầu phía đích.
- Tái hiện đúng A@1000.0/1000.1/1000.2 rồi B@1017.1/1017.2/1017.3: không crossing. Ca A→B ngắn 3+3 vẫn crossing một lần.
- Reset/rearm/track TTL rõ; dead zone không trở thành mẫu ổn định giả. Biên tính theo 2% đường chéo pixel, đúng frame không vuông.
- Temporal theo camera/epoch/encounter/track và từng lỗi, không dùng mode posture toàn camera để xác nhận xe.
- Áp dụng ≥4 mẫu mới trong 1,5 giây, agreement ≥80%, span ≥400ms, interval ≥100ms; unknown không thành phiếu. Bằng chứng hết hạn/track mất không giữ RIDING chắc chắn mãi.
- Dùng kết quả temporal đúng nhóm trong quyết định hành vi; tránh thêm ledger chỉ để expose status nhưng nhánh cảnh báo vẫn dùng một frame.
- Riding/pushing/walking/stationary/unknown phải có mapping nhất quán với contract hiện có; chỉ riding confirmed + crossing mới báo không dắt xe. Stationary/unknown không thành đường tắt.

**Test bắt buộc:** 3+1/3+2 không chốt, 3+3 chốt; gap 17 giây rồi B liên tiếp không chốt; missing track/ON zone/frame lặp/camera switch/quay đầu; hai xe mỗi xe hai mẫu không xác nhận chung; 4 mẫu trong 100ms không đủ span; 4/6 phiếu không đủ 80%; unknown/expired đúng; dắt bộ/ngồi xe đứng yên không báo crossing violation.

### R5 — Late issues merge thật, version và viewer nhận update

Vá F07:

- Merge theo identity issue/người và chính sách trạng thái, giữ NO_HELMET khi bổ sung RIDING_THROUGH_GATE; không thay toàn bộ danh sách bằng subset mới.
- Atomic DB update, kiểm kết quả trả về, retry bounded/idempotent; không báo success khi row không tồn tại hoặc DB write fail.
- Tăng event version khi nội dung đổi và phân phối upsert cho mọi viewer cùng cổng. Không tăng version cho retry nội dung y hệt.
- Giữ snapshot/crop mandatory và DB commit trước tiếng chính thức; media lỗi không URL giả. Lỗi mới cần thêm evidence phải được lưu trước khi đọc.
- Không tạo row/event mới cho update cùng encounter. Không đọc lại lỗi cũ; lỗi mới confirmed được đọc theo TTL/lease/queue contract, OCR vàng vẫn im lặng.
- Tách AI issues khỏi workflow status; không ghi đè trạng thái người dùng xử lý thuộc Task 2.

**Test bắt buộc:** event mũ rồi late riding còn cả hai; retry không duplicate/version tăng giả; DB fail không success; hai viewer đều thấy version mới; reconnect không đọc lịch sử; lỗi mới chưa có media không beep/TTS; dừng/đổi nguồn trong lúc persistence chưa xong không phát âm thanh cũ.

### R6 — Matcher strict, mặc định OFF, có runtime caller

Vá F08:

- Same physical gate, different eligible cameras, source/session valid, corrected time window và hướng/làn đã hiệu chỉnh là hard gates trước scoring.
- Chỉ dùng biển confirmed làm evidence; plate_read thử/fuzzy không tự gán người. Unknown direction không coi là hai hướng hợp lệ giống nhau.
- So toàn bộ ứng viên trước khi quyết định; hai ứng viên exact hợp lệ phải ambiguous. Không exact-return sớm bỏ qua window/ambiguity/gate.
- Bbox hai camera không cùng tọa độ; không dùng overlap trực tiếp nếu chưa có mapping vùng/làn chung. Calibration và đồng hồ lệch phải có hợp đồng.
- Có caller trong runtime và test xuyên luồng, dưới feature flag OFF mặc định. OFF không được tiếp tục nhánh correlator legacy ghép ngoài chính sách.
- Thiếu cặp đồng bộ/calibration: không bật auto-match. Có thể kiểm pipeline/runtime bằng dữ liệu mô phỏng, ghi real matching chưa nghiệm thu.

**Test bắt buộc:** exact nhưng cách 30 giây không match; khác gate/cùng camera/unknown direction không match; hai exact candidates ambiguous; plate fuzzy needs_review; skew/lane mismatch; OFF không link DB; match mô phỏng đúng upsert cùng encounter/version, không nhân cảnh báo.

Sửa test hiện assert matched cho beyond-window và cho phép cả matched/ambiguous. Assertion phải đúng duy nhất trạng thái theo spec. Không thay production bằng hành vi sai để chiều test cũ.

## 4. Kiểm thử video bắt buộc: toàn bộ thư mục tranning

Nguồn chỉ đọc: **`C:\Users\khucv\Downloads\tranning`**.

Kiểm kê tại ngày giao thấy **15 MP4**, gồm 14 clip và `2026-10-01 18-33-23.mp4`. Khi chạy phải inventory lại toàn thư mục, kể cả subfolder nếu có; không hardcode chỉ 14 file hoặc chọn một clip dễ.

### V0 — Manifest và tập đánh giá

- Với từng video: path, file size, SHA256, duration, native dimensions/FPS/codec, decode status, frame count thực/ước lượng và lý do lỗi. Tên file có space phải xử lý bằng argument/path chuẩn.
- Ghi model hash/classes, reader engine, config/version, device/dtype thực của model/input. CUDA available không phải bằng chứng tất cả model chạy CUDA/FP16.
- Ghi video/phiên/lượt nguồn; phát hiện file/cảnh trùng, không đưa cùng encounter hoặc cùng cảnh vào cả tuning và held-out. Thiết lập split theo nhóm video/phiên trước khi chỉnh ngưỡng.
- Chuẩn bị annotation manifest theo đoạn/frame cho đầu đội/không mũ, dắt/đi xe/đứng yên, plate box và toàn biển nhìn rõ. Mẫu mơ hồ là unknown, không đoán nhãn.
- Các video không đồng bộ trước/sau không được coi là cặp xe thật để đo matching hai camera. Chạy đồng thời hai video độc lập chỉ đo tải/isolation.

### V1 — Chạy từng video qua pipeline thật

- Chạy hết từng file từ đầu đến cuối, không chỉ đọc metadata hoặc sample đầu; log end-of-file bình thường, error và số frame thực được xử lý. Có danh sách riêng skipped/undecodable, không báo all videos passed khi còn file chưa chạy.
- File frontend/harness dùng source adapter video nhưng đi qua cùng live loop/tracker/grouping/OCR/consensus/ledger/persistence/card/realtime, DB/media QA. Detector-only benchmark không thay integration video.
- Replay mỗi video lần lượt bằng full/front và ocr_only/rear để kiểm software path (không coi cùng clip chạy hai profile là hai góc camera thật). Minimal có smoke clip riêng chứng minh preview-only.
- Gate line/ROI chỉ cấu hình trong QA theo góc nhìn thật của clip, lưu overlay calibration và config. Nếu clip không có đường cổng xác định thì crossing real-case là NOT_APPLICABLE, nhưng OCR/mũ và negative-case vẫn phải được đo; không vẽ line tùy tiện để tạo lỗi.
- Ghi card/output quan sát và event với timestamp video/receive/confirm, reason khi chưa cảnh báo, sample_count, crop/frame ID; lưu best crops và một số annotated segments để kiểm tra bằng mắt.
- Tìm lỗi cụ thể theo video + timestamp + track + crop. Tái hiện rồi sửa phần mềm và chạy lại clip đó; nếu ảnh gốc người cũng không đọc được thì ghi hạn chế góc/blur/ánh sáng, không hứa model sẽ khôi phục chi tiết mất.
- Dùng ground truth để đo helmet, plate detection, OCR toàn biển và alert riêng, gồm coverage/rejection và false confirmations. Không chỉ đếm log hoặc chọn các ảnh OCR đúng.

### V2 — Hai nguồn đồng thời, 30 phút, viewer và fault injection

- Chọn hai nguồn video từ manifest, mở pipeline front/rear cùng một cổng QA, camera IDs riêng. Chạy tối thiểu **30 phút wall-clock**, ghi rõ loop khi clip ngắn. Tăng epoch/reset track khi loop thành phiên mới; cùng lượt lặp không tính là mẫu độc lập cho precision/recall.
- Chạy realtime pacing theo FPS nguồn để đo tuổi hình, đồng thời có offline evaluation riêng nếu cần; không trộn throughput nhanh hơn realtime thành latency camera thật.
- So một nguồn/hai nguồn, một viewer/hai hoặc ba viewer theo các khoảng đo không chồng. GPU benchmark không chạy cùng training/task khác.
- Đo FPS frame mới capture/display/AI mỗi camera, p50/p95 frame age/latency, OCR queue wait, persistence/dispatch, CPU/RAM/private memory/VRAM đầu/giữa/cuối, max queue/bytes và dropped frames/jobs.
- Chèn block/slow OCR, block detect/pose, DB busy, media write failure, mất một nguồn/reopen, source switch, viewer chậm/reconnect, stop/start. Fault chỉ trên QA sources/data; nguồn kia phải tiếp tục.
- Nhìn ảnh có đồng hồ/timestamp được ghi trong frame để kiểm độ mới preview; synthetic overlay do QA tạo phải ghi rõ chỉ đo nội bộ, không đại diện latency RTSP Imou thật.
- Sau fault recovery, không lẫn crop/biển/track/event giữa camera/epoch; không stale audio, thread/pool/queue tăng không giới hạn hoặc nguồn bị reconnect chỉ vì AI exception.

### Mục tiêu và cách ghi nhận

- Display ≥15 frame mới/s/camera nếu source cung cấp đủ FPS; AI ≥5 frame mới/s/camera. Mục tiêu nâng 10–15 AI FPS phải báo riêng, không gọi 5 là đạt 10–15.
- Receive→JPEG-ready p95 ≤500ms; mũ confirm p95 ≤2s từ quan sát hợp lệ đầu tiên; crossing confirm p95 ≤1s sau đủ điều kiện; bảng update p95 ≤500ms; tiếng bắt đầu ≤1s khi queue rỗng/evidence sẵn.
- Camera trống hoặc segment QA trống đủ 10 phút: 0 vi phạm. Synthetic empty source kiểm rule phần mềm, không thay 10 phút camera thật.
- Precision lỗi đọc loa ≥95% riêng từng loại, recall ≥70% trên ca rõ. Tập test cần ít nhất 50 lượt vi phạm và 50 không vi phạm rõ từ nhiều video/phiên; không đủ phải báo thiếu và tiếp tục phần độc lập.
- OCR toàn biển ≥50% trên ít nhất 30 biển rõ **khác nhau**, có ground truth được rà. Báo số đúng/tổng và số xác nhận sai/từ chối; biển chưa rõ không gán học sinh.
- Gương giữ review-only, auto-match giữ OFF nếu chưa đủ dữ liệu/góc nhìn/calibration. Không dùng video đơn góc hoặc lặp cùng clip làm nghiệm thu thật nhánh đó.
- Không crash/hang/OOM, không memory tăng kéo dài sau warm-up. Việc đo 30 phút trên file không thay RTSP reconnect hoặc ca Imou 12 giờ; các mục thật còn PENDING được ghi chính xác.

## 5. “Test hết” — bộ kiểm thử phần mềm đầy đủ

Sau mỗi lát chạy targeted test để sửa nhanh. Cuối đợt trên snapshot tích hợp ổn định chạy **toàn bộ**, không chỉ 22 file chọn lọc:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Node test chạy tất cả file `frontend/test/*.test.mjs`; trong PowerShell dùng danh sách đường dẫn để chắc wildcard được mở rộng:

```powershell
$taskNodeTests = @(Get-ChildItem -LiteralPath frontend/test -Filter '*.test.mjs' -File | ForEach-Object { $_.FullName })
if ($taskNodeTests.Count -eq 0) { throw 'Không tìm thấy Node tests' }
node --test @taskNodeTests
```

- QA paths/ports/test mode phải cấu hình đúng trước các lệnh trên. Không chạy pytest mặc định nếu fixtures có thể mở RTSP hoặc ghi DB/media thật; sửa isolation trong phạm vi/qua bên tích hợp, rồi chạy đầy đủ.
- Playwright chạy toàn bộ E2E hiện có, có login/card/ảnh/clip/two viewer/reconnect/beep/TTS behavior; mock inference/capture phù hợp, API/router/middleware/schema vẫn thật. Không chỉ tìm chuỗi source.
- Chạy backend full suite fresh process, không chỉ thứ tự thuận lợi. Kiểm thử isolation/module/env/DB; không sửa assertion sang “chấp nhận rows của test khác”. Re-run chỉ khi có thay đổi/failure/isolation concern cần xác minh.
- Timeout/hang là FAIL cần điều tra, không kill rồi gọi PASS. Video performance/soak có deadline phù hợp; timeout test thông thường hữu hạn, ghi elapsed và stack/phase mắc kẹt.
- Không deselect test_guard/origin, không `|| true`, không thêm skip/xfail để báo xanh. Skip vốn có phải liệt kê lý do và ảnh hưởng; hardware-only tests được ghi PENDING, không thay software success paths bằng skip.
- Fail thuộc Task 2 hoặc file đang sửa: ghi bằng chứng và bàn giao, không sửa chồng. Tiếp tục các việc Task 1 độc lập; cuối cùng ghi full suite FAIL/PENDING nếu chưa tích hợp được, không gọi hoàn thành chung.
- Không nâng package hàng loạt để chữa test. Giữ venv/versions đúng, kiểm chứng compatibility với docs chính thức khi sửa API thư viện.

## 6. Báo cáo và điều kiện kết thúc

Output riêng Task 1, không ghi chồng docs của Task 2:

- `tasks/task-01/REPAIR_TODO.md`: checklist sửa F01–F09 và V0–V2.
- Cập nhật `EXECUTION_LOG.md`, giữ lịch sử; đính chính những phase “complete” chưa có runtime caller/benchmark.
- `tasks/task-01/video_qa/manifest.json`: metadata/hash/split/ground truth references của mọi video.
- `tasks/task-01/video_qa/results.json` và `VIDEO_TEST_REPORT.md`: kết quả từng video/profile, các timestamps tái hiện, metrics một/hai nguồn, bảng chất lượng có mẫu số, file chưa chạy/không áp dụng.
- Heavy video/crop/media QA nằm ở output root đã cấu hình, không đẩy vào Git; report chỉ tham chiếu path và hash cần thiết.
- `tasks/task-01/ACCEPTANCE_REPORT.md`: từng F01–F09/R1–R6/test/video/hardware là PASS/FAIL/PENDING, có lệnh/versions/snapshot/result. Ghi phần chưa nghiệm thu thật riêng.
- `tasks/task-01/HANDOFF.md`: thay đổi/hợp đồng/file dùng chung đã tích hợp, cách chạy lại test/harness có argument thực, rollback giữ ngưỡng an toàn; không đề xuất bật legacy 3+1 hoặc giảm mẫu để quay lại.

Harness video dùng script hiện có nếu thực sự đi qua pipeline và cách ly được; nếu thiếu, tạo script nhỏ phù hợp và ghi `--help`/lệnh thực đã chạy. Không viết lệnh script tưởng tượng hoặc chưa được kiểm chứng vào báo cáo.

Làm liên tục, tự chuyển bước sau test, không hỏi lại sau từng đợt. Chỉ cần người dùng khi thật sự thiếu thông tin/thiết bị/quyết định bên ngoài; trong lúc đó tiếp tục phần độc lập. Nếu phiên bị giới hạn buộc ngắt, ghi checkpoint cụ thể để tiếp tục, không tuyên bố xong.

**Chỉ kết luận phần sửa phần mềm đã hoàn thành khi F01–F08 đã được giải quyết, runtime integration đã kiểm chứng, full suite đạt trên snapshot đã ghi nhận và cả 15 video đã có kết quả chạy/đánh giá minh bạch.** Chất lượng thiếu nhãn hoặc nghiệm thu hardware còn PENDING phải giữ nguyên; không gọi Task 1 “hoàn thành đầy đủ/đạt thực tế” trước khi có bằng chứng tương ứng.
