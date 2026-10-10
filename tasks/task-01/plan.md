# TASK 1 — Khôi phục realtime và nâng cấp nhận diện hai camera

Ngày bàn giao: 02/10/2026. Đây là prompt thực thi dành cho Cursor.

## 1. Nhiệm vụ và kết quả cần bàn giao

Bạn phụ trách **TASK 1: lõi camera, nhận diện, sự kiện và giao diện giám sát trực tiếp** của School Gate Monitor tại `D:/Work/Project_motorbike`.

Hãy triển khai theo thứ tự trong tài liệu này. Đọc lại code trước khi sửa vì repository có nhiều thay đổi chưa commit và có thể đang được các task khác cập nhật. Chỉ sửa lỗi còn tồn tại, giữ phần đã hoạt động đúng. Không refactor toàn bộ dự án, không tạo hệ thống microservices hoặc đổi toàn bộ model.

Máy mục tiêu: i7-12700H, RAM 16 GB, RTX 3050 Laptop 4 GB. Hai Imou 5MP nối LAN quan sát trước/sau **cùng một cổng vật lý**. Camera trước ở góc lệch bên phải người lái: người–xe, mũ, hành vi; gương chỉ đánh giá khi góc nhìn phù hợp. Camera sau: xe, biển và OCR. Không tự suy ra quan sát được gương trái chỉ vì camera nhìn từ bên phải.

Kết quả cần đạt: hình mới và mượt; camera sau đọc biển khi không thấy người; nhận diện nhiều frame; cảnh báo ngắn có căn cứ; không trộn hai camera; giải thích được tại sao chưa nhận diện/chưa cảnh báo. Không đánh dấu hoàn thành chỉ vì test helper đạt hoặc có model/endpoint chưa được nối vào runtime.

## 2. Quy tắc bắt buộc khi nhiều task chạy song song

### 2.1. Quyền sở hữu mã

Task 1 đăng ký phạm vi trước khi sửa trong `tasks/task-01/OWNERSHIP.md`, ghi trạng thái và danh sách file cụ thể. Đọc danh sách sở hữu của các task khác nếu có; không coi tài liệu này đã tự khóa file đối với các phiên không đọc nó.

**Task 1 sở hữu:**

- Luồng live trong `app/cv/pipeline.py`, `capture.py`, `detector.py`, `best_plate.py`, `ocr.py`, `plate_voter.py`, `pose.py`, `crossing.py`, `crossing_alert.py`, `evidence.py`, `recognition_cards.py`, `recognition_log.py`, `recorder.py` và module CV mới thực sự cần thiết.
- Các thành phần CV runtime trong `app/cv/char_plate_reader.py`, `plate_char_tools.py`; giữ giao diện adapter cho công cụ training.
- Luồng video/recognition/realtime trong `app/api/guard.py`; chỉ phần metrics liên quan của `app/api/system.py`.
- `frontend/src/pages/GuardPage.jsx`, `components/RecognitionLogPanel.jsx`, `components/PlateReviewPanel.jsx`, `components/AlertBanner.jsx`, `utils/alertAudio.js`, `alertFilter.js`, `speak.js`, `useAudioLease.js` nếu cần.
- Test và script benchmark riêng của Task 1; tài liệu dưới `tasks/task-01/`.

**File dùng chung — Task 1 là bên tích hợp trong đợt này:**

- `app/db.py`, `app/schemas.py`, `app/config.py`, `app/main.py`, `app/api/camera.py`, `app/api/roi.py`.
- Các task khác cần sửa những file này phải bàn giao yêu cầu/patch riêng; không đồng thời ghi vào cùng file. Task 1 nhận và tích hợp thay đổi tương thích khi có bàn giao, không tự quyết nghiệp vụ thuộc task khác.
- `app/tests/conftest.py` và các fixture dùng chung: phối hợp với chủ sở hữu hiện có; ưu tiên fixture riêng trong test Task 1. Không làm yếu assertion để chấp nhận dữ liệu nhiễm từ test khác.

**Ngoài phạm vi Task 1:** trang admin tổng quát, auth/cookie/CSRF tổng thể, tài khoản/roster, backup tổng thể, CI/deploy và huấn luyện lớn. Những phần này có thể chạy ở task riêng. Task 1 công bố hợp đồng, dùng API/client hiện có, ghi dependency còn thiếu; không sửa chồng `auth.py`, `AuthContext`, `frontend/src/api/client.js`, requirements hoặc workflow. Chưa nghiệm thu LAN/bảo mật khi task tương ứng chưa tích hợp.

### 2.2. Checkout, dữ liệu và tài nguyên

- Ưu tiên checkout/worktree riêng từ cùng baseline có kiểm soát. Working tree hiện có thay đổi chưa commit: không tạo worktree từ HEAD rồi mặc định đã chứa thay đổi mới. Ghi nhận chính xác baseline và patch/file cần mang sang; không tự stash, reset, clean hay commit toàn bộ thay đổi của người khác.
- Nếu dùng chung checkout, chỉ một task được ghi vào mỗi file. Trước mỗi đợt sửa, kiểm tra diff hiện tại; không hoàn nguyên thay đổi chưa rõ chủ sở hữu. Khi xung đột, ghi trong tài liệu Task 1 và tiếp tục phần độc lập.
- Mỗi task dùng DB/media/output/port test riêng. Migration chạy trên SQLite backup hoặc DB tạm trước. Không cho nhiều test cùng ghi DB thật.
- Chỉ một lượt benchmark GPU hoặc training nặng được chạy tại một thời điểm trên RTX 3050. Benchmark khi training khác đang chạy là kết quả bị nhiễu, không dùng nghiệm thu. Không tự kill tiến trình task khác hoặc backend đang phục vụ người dùng.
- Camera thật có một chủ sở hữu phiên vận hành. Dùng video/nguồn giả cho QA; phối hợp lịch khi đo Imou thật. Không tự đổi nguồn, exposure hoặc firmware camera vận hành để benchmark.
- Không cho hai phiên backend cùng capture camera thật hoặc cùng chạy maintenance trên DB/media thật.
- Mỗi task ghi nhật ký riêng. Task 1 không cập nhật chồng `docs/CURSOR_EXECUTION_LOG.md` hoặc acceptance report chung khi task khác đang ghi; bàn giao bản tổng hợp để tích hợp một lần.

## 3. Hợp đồng phải công bố trước khi sửa

Tạo `tasks/task-01/CONTRACTS.md`, dựa trên schema hiện có, nêu input/output và trường bổ sung:

- `gate_id`: cổng vật lý; `camera_id`: nguồn hình ổn định; `role`: front/rear/aux.
- Frame: camera, source epoch, frame sequence, thời gian nhận monotonic; thời gian nghiệp vụ UTC. Timestamp nguồn chỉ dùng khi có và đã kiểm tra.
- Track chỉ duy nhất trong `(camera_id, source_epoch, track_id)`; encounter nội bộ camera có run/session ID. Không so ID track giữa hai camera.
- Quan sát biển: frame/crop ID, chất lượng, engine/model hash, chuỗi thử, trạng thái checking/confirmed/needs_review/error. Không lấy confidence làm độ chính xác kết luận.
- Hành vi: `RIDING`, `PUSHING`, `WALKING`, `UNKNOWN`, kèm lý do, khoảng thời gian và mẫu được chấp nhận.
- Event: UUID, encounter, gate, camera observations, version tăng, `issues[]`, trạng thái bằng chứng; trạng thái AI tách trạng thái xử lý nghiệp vụ.
- Giữ hợp đồng đổi nguồn POST 202 và GET checking/applied/error. Nguồn lỗi phải giữ camera cũ. Không đưa credential vào response/log.
- Bổ sung trường tương thích; không âm thầm đổi nghĩa gate_id lịch sử. Migration có phiên bản, chạy lặp an toàn, không sửa dữ liệu vi phạm cũ.

Không giữ khóa đồng bộ qua await. Model có một chủ sở hữu thực thi; không dùng chung YOLO `.track(persist=True)` giữa camera. Một model detector stateless dùng chung chỉ được thực thi tuần tự có kiểm soát, tracker state vẫn riêng từng camera.

## 4. Hiện trạng cần tái xác nhận

Audit 02/10/2026 tìm thấy các điểm sau. Đối chiếu lại code mới, ghi đã sửa/còn lỗi/chưa đủ chứng cứ:

1. `_run_loop()` vẫn đọc capture và đợi detect/pose cùng vòng; JPEG chỉ cập nhật sau các công đoạn này.
2. Registry/startup theo GATES, chưa tạo hai pipeline từ bảng cameras cùng gate; cả hai góc chưa có profile model riêng.
3. Không có person thì bỏ nhánh OCR dù có xe/biển.
4. `_observe_best_plate()` đợi gần đường cắt; BestPlateStore giữ một crop, có thể xác nhận từ một frame; PlateVoter tồn tại nhưng không phải consensus của live path.
5. Bộ đọc ký tự đã train có adapter/weights nhưng chưa có caller production; review chưa có producer và PlateReviewPanel chưa render trong GuardPage.
6. Crossing hiện nhận 3+1; `max_crossing_sec` không được áp dụng. Phép thử 3 frame đầu rồi 1 frame sau, kể cả cách 17 giây, đã nhận crossing.
7. Sự kiện đóng issues một lần, có thể mất lỗi đủ bằng chứng đến muộn.
8. Pose thread-local có thể nạp nhiều bản theo worker; một số map track/crossing không dọn theo track mất.
9. Health có thể gọi get_pipeline để nạp model; FPS và tuổi frame chưa phản ánh đủ capture/AI/display.
10. Stop join timeout rồi shutdown(wait=False), cần kiểm chứng worker cũ không tiếp tục persist/alert. Recorder cần kiểm tra kích thước frame với VideoWriter.

Không bỏ qua lỗi environment/test isolation. Interpreter chuẩn là `venv/Scripts/python.exe`; không cài lại dependency chỉ vì gọi nhầm Python.

## 5. Thứ tự thực hiện

Chia mỗi phase thành lát nhỏ khoảng 2–5 file, có test hành vi và checkpoint. Thực hiện liên tục, không hỏi lại sau mỗi lát. Mỗi thay đổi phải đi vào startup/API/UI thật nếu thuộc scope, không kết thúc ở helper độc lập.

### Phase 0 — Số đo đúng, health chỉ đọc

Đây là thay đổi đầu tiên; chưa đổi ngưỡng/model để tạo baseline đẹp.

- Ghi baseline commit/diff, phiên bản dependency, hash/mapping weights, nguồn và cấu hình đã che credential. Không ghi dữ liệu học sinh vào báo cáo.
- Sửa `_pipeline_status()` và nhánh recorder health dùng pipeline đang tồn tại; không tạo model/camera. Không quét toàn media mỗi poll; số đo dung lượng có cache và interval tối thiểu 60 giây.
- Instrument capture/decode, detect từng model, tracking, pose, OCR queue wait/inference, encode, persistence và dispatch. Báo p50/p95, không gọi số đo cuối cùng là average.
- Tách capture FPS, AI FPS, JPEG frame mới, frame bị bỏ. Gửi JPEG lặp không tính là hình mới. Phân biệt latency nội bộ với camera→màn hình.
- Metrics dùng buffer hữu hạn, không lưu frame hoặc exception chứa URL/token. Sampling tài nguyên nền khoảng một giây; không gọi nvidia-smi/scan đĩa mỗi frame.
- Ghi RAM working set/private memory, VRAM và các queue đang chờ; số OCR/crop/event. Device thực/model instance/input tensor cần xác minh, không suy từ CUDA available.

**Kiểm chứng:** health không tạo pipeline; các nhánh frame skip/không người vẫn đếm hình mới đúng; metrics có giới hạn bộ nhớ. Chạy một và hai nguồn video cách ly cùng cấu hình, ghi baseline.

### Phase 1 — Hình mới, bộ nhớ hữu hạn, stop/reconnect đúng

- Reader riêng mỗi camera, latest-frame một slot, AI lấy frame mới nhất và bỏ stale. Không tích hàng đợi frame đầy đủ.
- Hiển thị và JPEG độc lập detect/pose/OCR/DB. JPEG encode một lần cho frame hiển thị mới và dùng chung viewer.
- Giữ native frame chưa vẽ cho crop; preview/detect giữ tỷ lệ. Xác định ownership của NumPy arrays: task đang dùng frame không bị sửa tại chỗ; chỉ copy payload cần thiết.
- Overlay gắn frame/epoch/timestamp; hết hạn 500 ms thì bỏ. Không kéo box/skeleton cũ theo xe mới.
- Hình không mới quá hai giây phải hiện hình cũ/mất tín hiệu; một camera lỗi không dừng camera còn lại.
- Reconnect timeout/backoff có giới hạn, không tạo thêm model/thread sau mỗi lỗi. Khi mất liên tục track, tăng epoch và loại kết quả cũ. Không reconnect camera vì exception AI thuần túy.
- Track mất có TTL/prune; map crossing/sealed/approach có giới hạn và không hồi sinh lượt cũ gây duplicate.
- Giới hạn OCR toàn process tối đa tám yêu cầu chạy/chờ, một yêu cầu mỗi track; không fallback OCR đồng bộ. Reset không tạo backlog Future mồ côi.
- Event/media/clip có admission cap và ngân sách bytes; giảm copy toàn ring clip mỗi event bằng ownership/references an toàn. Không giữ NumPy view nhỏ vô tình giữ cả frame lớn quá hạn.
- Stop tăng generation/invalidate, chặn persist/alert đã hết phiên; shutdown có thời hạn và trạng thái lỗi nếu worker không thoát. Restart không khởi tạo capture mới khi capture cũ vẫn giữ nguồn.
- Recorder resize đúng kích thước writer, kiểm tra mở/ghi/đọc lại clip; clip ring có timestamp để phản ánh thời lượng thật.

**Kiểm chứng:** block detect/pose/OCR mà hình vẫn tiến; queue không tăng vô hạn; đổi nguồn không nhận kết quả cũ; stop không phát alert mới; mất một nguồn không ảnh hưởng nguồn kia; nhiều viewer không nhân encode. Đo RAM sau warm-up và cuối 30 phút.

### Phase 2 — Camera sau đọc biển đúng qua nhiều ảnh

- Tạo nhánh quan sát theo vehicle/plate track, không đòi person. Xe không vi phạm và xe thiếu người vẫn có OCR/card.
- Plate detector toàn cảnh dùng ảnh nhỏ; scan vùng xe khi cần phải map sang native frame đúng cùng seq/epoch. Giới hạn vùng/tần suất để không chạy plate detector full-resolution mọi frame.
- OCR bắt đầu khi crop đủ chất lượng, không đợi gate line/crossing. Không có đường cắt vẫn quan sát/OCR; cảnh báo crossing chưa được phép.
- Thay hợp đồng one-best-one-attempt bằng top 3–5 crop **khác frame**, có quality/diversity và cap bytes/TTL. Quality gồm kích thước ký tự/box, confidence, blur/sharpness, exposure, clipping; góc nhìn không quan sát được là unknown.
- Khởi chạy từ crop tốt; cho mẫu tốt hơn bổ sung có giới hạn, không đọc lại mọi frame. Cùng frame/cache/retry kỹ thuật không tính là phiếu mới.
- Xác nhận toàn biển sau ít nhất hai crop khác frame đồng thuận, đủ chất lượng và không có kết quả cạnh tranh đáng tin. Chuỗi yếu/mâu thuẫn/thiếu ký tự → needs_review, không lookup/gán học sinh.
- Regex chỉ kiểm tra định dạng; không biến chữ/số để tạo một biển chưa được quan sát. Test các cặp O/0, I/1, B/8, thiếu chữ series và biển hai dòng.
- Rectification: tìm góc/quadrilateral có đánh giá độ tin cậy, warp/deskew khi hợp lệ; fallback crop gốc nếu không chắc. Không lấy bốn góc bbox axis-aligned rồi tuyên bố đã sửa phối cảnh. So sánh trên biển nghiêng thật; không hứa khôi phục chi tiết đã mất do nhòe.
- Benchmark EasyOCR và bộ đọc 36 ký tự hiện có trên cùng crop/tập giữ lại. Pin hash weights, class mapping, device. Bộ đọc mới chạy shadow/review-only trước; không thay engine mặc định bằng một flag chưa được test end-to-end.
- Không chép weights ký tự vào `models/plate_best.pt`. Không nâng dependency trên environment vận hành. PaddleOCR/LPRNet chỉ thêm vào môi trường benchmark nếu có lý do đo được và weights phù hợp biển Việt Nam.
- Nối producer review từ crop thực, hợp đồng feedback và render PlateReviewPanel trong GuardPage bằng lát riêng. Bảo vệ role/scope; expected_version phải bằng version hiện tại; idempotency gồm review, người thực hiện và payload hash. Không chấp nhận key cũ trên review khác.
- Khi verdict incorrect phải có chuỗi sửa hoặc được phân loại unreadable/wrong_association phù hợp. Feedback không tự retrain nóng; chỉ tạo dataset đã rà, split theo encounter/video/session và kiểm tra hash/crop tồn tại.

**Kiểm chứng:** camera sau không thấy người vẫn đọc được; thiếu gate line không chặn OCR; hai xe sát nhau không trộn biển; OCR lỗi/chậm/mâu thuẫn/frame lặp đều an toàn; review thật xuất hiện và người dùng sửa được. Dùng video `C:/Users/khucv/Videos/2026-10-01 18-33-23.mp4` để tái hiện, nhưng không dùng một biển lặp lại để tuyên bố chất lượng toàn hệ thống.

### Phase 3 — Nối camera trước và phân loại hành vi/mũ

- Startup/registry đọc camera mapping thực, mỗi camera có ID và profile. Front chạy người–xe/mũ/pose khi cần; rear ưu tiên xe/biển/OCR. Không load cả bộ model trên mọi góc khi không dùng.
- Giữ tracker state riêng; thêm scheduler GPU nhỏ có admission/fairness nếu baseline cho thấy tranh GPU. Không coi nhiều worker tương đương nhiều năng lực GPU.
- Xác minh helmet mapping và ảnh thử có/không mũ. Cho override weights nhưng không ghi đè bản cũ. Sai mapping hiển thị nhánh mũ lỗi, camera/plate tiếp tục.
- Ghép mũ với đầu đúng người; mũ cầm tay/treo xe, đầu khuất là unknown. Thêm đánh giá khả năng quan sát, không suy không mũ chỉ vì không thấy box mũ.
- Giữ person↔vehicle association qua thời gian; đổi xe/mất track reset đúng bằng chứng. Với nhiều ứng viên mơ hồ, từ chối ghép.
- Pose chạy trên nhóm có xe và cần quyết định, theo tần suất giới hạn. Đầu ra bốn trạng thái rõ; không dùng bent_leg một frame làm đường tắt RIDING.
- Features gồm hip/shoulder/leg, vùng yên suy ra có độ tin cậy, vị trí tương đối và chuyển động theo thời gian. Cặp đứng yên không đủ để khẳng định đang di chuyển qua cổng.
- Chọn temporal window theo FPS thực và validation: có thể bắt đầu 0,8–1,5 giây, bảo đảm số mẫu tối thiểu và mẫu khác frame. Không ép 20 mẫu nếu khiến cảnh báo chậm, không hạ tiêu chuẩn để che FPS thấp.
- Giữ ledger từng lỗi: mặc định ≥4 mẫu đồng thuận trong 1,5 giây, ≥80%, trải dài ≥400 ms, cách ≥100 ms; unknown không thành phiếu và mâu thuẫn cần kiểm tra.
- Gương: góc trước lệch phải không đảm bảo thấy gương trái theo người lái. Mặc định review-only; không có model/nhãn/góc phù hợp thì ghi thiếu, không báo thiếu từ absence detector.

**Kiểm chứng:** mũ đội/treo/cầm tay, đầu khuất, hai người một xe; riding/pushing/walking/stationary ở đúng góc; chân co một frame không tạo vi phạm; model và track không lẫn camera.

### Phase 4 — Chốt lượt đúng, evidence và cảnh báo nhanh

- Sửa crossing yêu cầu ba frame ổn định phía đầu và ba frame mới ổn định phía đích, tối đa năm giây cho lần chuyển phía. Quy định rõ reset khi quá hạn/mất track; biên chống rung 2% đường chéo pixel, đúng frame không vuông.
- Một lượt qua tạo một event; quay đầu tạo lượt mới chỉ sau rearm hợp lệ, không nhân lỗi cùng lượt. Test 3+1/3+2 không xác nhận, 3+3 xác nhận; khoảng cách 17 giây không xác nhận từ lịch sử cũ.
- Đường cắt dùng finalize, không chặn thu nhận diện. Tách collecting/finalizing/finalized và timeout cụ thể. Không seal issues rỗng rồi bỏ lỗi mũ đủ mẫu đến muộn.
- Sau finalize, bằng chứng hợp lệ phía sau có thể bổ sung vào cùng event/version; không sửa các frame nguồn cũ hay tạo event duplicate. Lỗi mũ/hành vi không chờ camera sau/OCR xong mới được cảnh báo khi đã đủ điều kiện riêng.
- Snapshot/crop mandatory và DB commit trước âm thanh; URL chỉ dành cho file ghi thành công. Clip optional cập nhật sau. Lỗi DB/đĩa/media phải hiện health/card; retry bounded và idempotent, không ghi trùng.
- Bảng là thẻ ảnh người/đầu/biển, trạng thái và số mẫu thực. OCR chưa rõ màu vàng, không biến confidence thành độ chính xác; lỗi mũ đỏ vẫn hiện khi biển vàng. Đang chọn ảnh không hiện thành đã xác nhận.
- TTS câu ngắn theo tên cổng vật lý; gộp khoảng 300 ms, tối đa hai lời nhắc; ưu tiên dắt xe → mũ → gương đã được nghiệm thu. Mặc định rate 1,45, chỉnh 1,0–1,6; kiểm tra giọng Việt thực. Tốc độ đọc không thay thế việc giảm độ trễ event.
- Queue tối đa hai câu chờ, TTL năm giây; không chồng tiếng. Một beep/event và dedup từng mã lỗi. Lỗi mới bổ sung đọc tối đa một lần nếu còn trong TTL và thực sự cần nhắc; update biển không đọc lại lỗi cũ. Lịch sử/reconnect không đọc.
- OCR chưa rõ/engine error chỉ báo trạng thái nhận diện, mặc định không beep/TTS. Nếu có yêu cầu riêng đọc "chưa đọc được biển", phải là tùy chọn chẩn đoán rõ ràng, không mặc định thành vi phạm.
- Một phiên bảo vệ có lease loa; viewer khác vẫn nhận cùng bảng. Tắt loa/mất lease/đổi phạm vi/unmount dọn timer và tiếng. Hiển thị rõ loa tắt, trình duyệt chặn hoặc chưa có lỗi confirmed; không làm yếu ngưỡng để tạo tiếng.

**Kiểm chứng:** lỗi đủ mẫu đến muộn không bị mất; nhiều lỗi/xe/gate; ghi ảnh lỗi/DB bận/đĩa đầy không phát âm thanh chính thức; hai viewer nhận đầy đủ; quan sát lệnh beep/speak thật bằng browser test, không chỉ tìm chuỗi source.

### Phase 5 — Phối hợp trước/sau và hoàn thiện màn giám sát

- Định nghĩa GateEvent/shared encounter trong hợp đồng. Hai camera quan sát cùng cổng; không đổi gate_id lịch sử.
- Matcher xét thời gian đã hiệu chỉnh, hướng, vùng/làn, lớp xe, biển chắc chắn; appearance chỉ dùng nếu có đối chứng và không cần face recognition.
- Không ghép chỉ theo thời gian, track ID hoặc biển gần giống. Nhiều ứng viên/mâu thuẫn → chưa ghép. Camera sau có thể lưu quan sát để người dùng đối chiếu.
- Auto-match mặc định tắt tới khi có calibration và cặp lượt có nhãn. Không lấy helper cũ tìm gate khác bằng fuzzy plate làm matcher mới.
- Hiệu chỉnh IN/OUT theo trajectory/line order từng camera; không coi enter/exit trong toán học luôn đúng hướng vật lý.
- UI hiển thị cả front/rear của cùng gate, một bảng lượt xe, bằng chứng từng camera và trạng thái chức năng bị thiếu khi mất nguồn. Endpoint nhận camera khi cần; không reuse gate như camera ID trong schema mới.
- Đồng bộ realtime upsert bằng event ID/version, queue riêng cho client, reconnect resync trạng thái không phát lịch sử. Trong split view đăng ký đầy đủ phạm vi đang xem.
- Nối API/recognition cards/review và kiểm tra URL media với hợp đồng auth của task phụ trách đăng nhập. Không viết auth riêng hoặc thêm token vào URL mới. Nếu cùng-origin/cookie chưa sẵn, dùng adapter rõ ràng và ghi chưa nghiệm thu LAN.

**Kiểm chứng:** cùng track số ở hai camera không lẫn; xe nối đuôi/đổi thứ tự/ngược chiều/timestamp lệch được từ chối khi mơ hồ; ghép chắc tăng version mà không nhân vi phạm/loa. Test matcher chưa đủ dữ liệu phải báo chưa nghiệm thu, tiếp tục UI và runtime độc lập.

### Phase 6 — Tối ưu GPU và nghiệm thu

- Chỉ tối ưu khi đo được bottleneck; FP16 đã có trong config, cần xác minh thực dùng và đối chứng chất lượng.
- So sánh scheduler, tần suất pose, ROI/input hợp lý trước. Sau đó mới thử ONNX/TensorRT/hardware decode trong môi trường riêng. Không đổi ByteTrack/YOLO11 chỉ vì model mới hơn.
- Đo một/hai nguồn, một/ba viewer, 30 phút cách ly; sau đó đo Imou thật và ca 12 giờ theo lịch tài nguyên đã phối hợp. Training/background benchmark khác phải tách lịch.
- Nếu bản thân frame nguồn nhòe, lưu crop nguồn và báo cần chỉnh góc/ánh sáng/exposure/FPS/codec theo camera thực. FPS AI thấp có thể bỏ lỡ crop rõ; nó không phải trực tiếp là thời gian phơi sáng camera. Không chỉnh thiết bị tự động trong task này.

## 6. Kiểm thử và tiêu chí nghiệm thu

Chạy test với DB/media/source riêng và interpreter dự án. Đọc package scripts trước khi chạy frontend. Không deselect các nhóm nặng để tuyên bố full suite; thay live pipeline bằng fixture phù hợp cho unit/API và giữ integration riêng.

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
```

Trong `frontend`, chạy `node --test test/*.test.mjs`, lint/build và browser tests liên quan theo script thực tế. Báo đầy đủ command, interpreter, count, warning/fail/skip và lý do. Test pipeline phải đi qua flow thật detector → resize → ROI → association → OCR/ledger → event; app test dùng factory/routes production, tránh chỉ test helper.

### Mục tiêu hiệu năng

- Hiển thị ≥15 **frame mới**/giây/camera khi nguồn đủ FPS; nội bộ nhận frame→JPEG-ready p95 ≤500 ms.
- Mức kiểm tra ban đầu AI ≥5 frame mới/giây/camera; mục tiêu nâng cấp 10–15 FPS/camera. Đạt 5 chưa được báo đã đạt mục tiêu 10–15.
- Decode 25–30 FPS chỉ là mục tiêu nếu camera/codec/cấu hình thực cung cấp; đo camera→màn hình bằng cảnh đồng hồ, mục tiêu p95 ≤1,5 giây.
- Xác nhận mũ p95 ≤2 giây từ quan sát hợp lệ đầu; crossing p95 ≤1 giây sau đủ điều kiện; bảng p95 ≤500 ms sau xác nhận; tiếng nói ≤1 giây khi queue rỗng và mandatory evidence đã lưu.
- Không backlog hoặc RAM tăng kéo dài sau warm-up; báo đầu/giữa/cuối, peak/private memory/VRAM và số frame/job bị bỏ, không chỉ RAM toàn máy.

### Mục tiêu chất lượng và độ bền

- Precision lỗi phát loa ≥95% riêng từng loại, recall ≥70% trên trường hợp rõ; tối thiểu 50 lượt vi phạm rõ và 50 không vi phạm rõ, tách theo video/phiên.
- OCR đúng toàn biển ≥50% trên ít nhất 30 biển rõ khác nhau; báo accuracy, tỷ lệ xác nhận, sai được xác nhận và tỷ lệ từ chối. Không đo chỉ trên một biển lặp.
- Gương cần tối thiểu 30 thiếu rõ và 30 đủ rõ ở góc phù hợp trước khi bật cảnh báo. Thiếu dữ liệu giữ review-only.
- Auto-match cần tối thiểu 50 cặp có nhãn, không ghép nhầm trong tập nghiệm thu; thêm ít nhất 20 tình huống khó. Báo match coverage và rejection, không coi không ghép gì là đạt.
- Camera trống 10 phút tạo 0 vi phạm; mất một camera không dừng camera kia; khi nguồn khôi phục mục tiêu nhận frame mới ≤15 giây.
- Hai camera chạy 12 giờ, 2–3 viewer, không crash/hang/khởi động thủ công trong điều kiện mạng bình thường. 30 phút là smoke benchmark, chưa thay nghiệm thu 12 giờ.

Các tiêu chí trên là mục tiêu cần đo. Thiếu dữ liệu hoặc thiết bị thì ghi rõ chưa nghiệm thu, tiếp tục việc không phụ thuộc; không hạ tiêu chí hoặc dùng số test thay chất lượng.

## 7. Tài liệu và cách kết thúc Task 1

Giữ toàn bộ output riêng:

- `tasks/task-01/OWNERSHIP.md`: phạm vi file, xung đột, bàn giao dùng chung.
- `tasks/task-01/CONTRACTS.md`: hợp đồng camera/frame/event/API/model và tương thích.
- `tasks/task-01/todo.md`: checklist có trạng thái thực.
- `tasks/task-01/EXECUTION_LOG.md`: baseline, thay đổi từng lát, command/result, số đo trước/sau, rollback.
- `tasks/task-01/ACCEPTANCE_REPORT.md`: đã viết mã / test hành vi / đo video / nghiệm thu Imou thật.
- `tasks/task-01/HANDOFF.md`: file đã sửa, interface cần task khác dùng, dependency/thiếu dữ liệu, config để bật/tắt thử nghiệm.

Không xóa/ghi đè DB/media/models/video/log người dùng, không push/deploy, không sửa mật khẩu camera, không cài/nâng package vào tiến trình vận hành. Không tạo ảnh AI rồi coi là dữ liệu nghiệm thu thật; dataset mới phải có provenance và nhãn được rà.

Sau mỗi lát, kiểm chứng liên quan; sau mỗi phase, chạy regression phù hợp. Cuối task chạy bộ chung trên trạng thái tích hợp đã ghi nhận. Phân biệt fail có sẵn, fail của Task 1 và fail do task khác đang sửa; không sửa ngầm scope người khác để làm test xanh.

Tiếp tục các phase độc lập mà không hỏi lại sau từng đợt. Chỉ yêu cầu thông tin khi thực sự cần thiết bị/góc nhìn/nhãn/mật khẩu hoặc giải quyết quyền sở hữu đang xung đột; trong khi đó tiếp tục phần không bị chặn. Báo cáo kết thúc phải mô tả chức năng người dùng thực sự sử dụng được, phần chưa đạt và bước nghiệm thu còn lại.

## 8. Yêu cầu tiếp tục thực thi — bổ sung theo người dùng

Người dùng yêu cầu **Task 1 thực thi liên tục đến khi hoàn thành phần việc có thể triển khai và kiểm chứng**, không kết thúc chỉ sau đọc mã, phân tích, gọi explore agent hoặc hoàn thành một phase.

- Đọc baseline, OWNERSHIP, checklist và log hiện có để tiếp tục từ công việc đang dở; không chạy lại toàn bộ bước khám phá nếu đã có kết quả còn hợp lệ.
- Sau đọc mã phải chuyển sang sửa và kiểm chứng lát đầu tiên. Thông báo "tôi sẽ đọc/đánh giá/triển khai" là cập nhật tiến độ, không phải kết quả bàn giao.
- Sau mỗi lát/phase, cập nhật checklist và tự chọn việc tiếp theo có dependency đã đủ. Không hỏi "có tiếp tục không", "muốn làm phase tiếp theo không" hoặc chờ người dùng nhắn "làm đi" lần nữa.
- Nếu dùng agent hỗ trợ theo cơ chế đã được phép của phiên thực thi, nhận kết quả rồi tích hợp/kiểm chứng; không dừng công việc chính ở lời thông báo sẽ gọi agent.
- Khi test lỗi, tái hiện và sửa trong phạm vi sở hữu, chạy lại kiểm thử phù hợp; không bỏ test, nới assertion hoặc báo xong vì chỉ một subset đạt.
- Khi chờ file dùng chung, camera, dữ liệu có nhãn hoặc quyền bên ngoài, ghi dependency cụ thể và tiếp tục mọi phần độc lập. Không đánh dấu xong các mục còn phụ thuộc chỉ vì không thể đo lúc này.
- Không sửa chồng Task 2, không tự mở RTSP thật, kill tiến trình, chạy training nặng hoặc thay DB/media vận hành để chứng minh tiến độ.
- Chỉ bàn giao kết quả cuối khi phần triển khai và kiểm thử khả thi đã hoàn tất, hoặc đã hết việc độc lập do blocker bên ngoài thực sự. Phân biệt rõ code/test đã hoàn thành với nghiệm thu video/camera thật còn PENDING.
- Nếu giới hạn công cụ, phiên hoặc tài nguyên bắt buộc ngắt lượt, ghi checkpoint cụ thể: file đã sửa, test đã chạy, lỗi đang dở, việc tiếp theo và lệnh tiếp tục. Không tuyên bố hoàn thành và không hứa tự chạy nền khi phiên đã kết thúc.

Điều khoản này không hạ ngưỡng nghiệm thu và không cấp thêm quyền tác động dữ liệu/thiết bị thật. Yêu cầu tiếp tục áp dụng cho mọi phase trong phạm vi Task 1.
