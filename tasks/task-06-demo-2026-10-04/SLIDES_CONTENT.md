# Nội dung 12 slide — School Gate Monitor, demo 04/10/2026

**Ràng buộc đã xác nhận:** bàn giao trước01:00 ngày04/10/2026, Asia/Bangkok; nói2–3phút, demo7phút, tổng10phút. Có laptop, hai camera thật và loa; tất cả hoạt động trên cùng router khi mất Internet. VPS dự kiến `103.101.162.111`, SSH/domain chưa xác minh.

**Cách dùng:** slide1–8 là phần chính, tổng180giây; slide9–12 là phụ lục Q&A, không trình bày trong10phút. Nội dung phản ánh mã/bằng chứng lúc lập plan, không xác nhận bản demo đã nghiệm thu. Trước xuất PPTX, chỉ cập nhật trạng thái bằng log/biên bản của đúng bản build. Không điền số accuracy/FPS bằng confidence của một ảnh.

**Trước xuất bản cuối:** dùng kết quả trong `FINAL_ACCEPTANCE.md` của bản
freeze. Thay trạng thái đã thay đổi bằng bằng chứng thật, cập nhật lời nói
tương ứng. Bài trình bày nói về sản phẩm và kết quả; thông tin lỗi đang sửa
chỉ dùng để chuẩn bị, không bê nguyên checklist nội bộ lên sân khấu.
Nếu chưa có phép đo, giữ nhãn “mục tiêu/chưa nghiệm thu”, không để chỗ trống
hoặc số giả trong PPTX. File này là nội dung/notes, chưa phải PPTX/PDF đã xuất.

**Nhãn thống nhất:** `ĐÃ CÓ MÃ` = chức năng hiện hữu; `ĐÃ KIỂM CHỨNG` = đúng phạm vi test ghi kèm; `CẦN NGHIỆM THU` = còn phải chạy trên phần cứng/dữ liệu thật; `ĐỀ XUẤT/MỤC TIÊU` = hướng phát triển, chưa đạt. Mỗi slide nên có nhãn nhỏ ở chân trang và tối đa bốn ý chính. Dùng ảnh của đúng build/ca demo đã duyệt; hình minh họa phải ghi rõ.

## Slide1 — Cổng trường an toàn, bảo vệ xử lý chủ động

Thời lượng chính:15giây. Nhãn: `BẢN DEMO LOCAL · CẦN NGHIỆM THU`.

### Nội dung hiển thị

- School Gate Monitor — trợ lý giám sát cổng trường.
- Hai camera → biển số và tình huống qua cổng → bằng chứng → người duyệt.
- Demo04/10/2026: laptop + camera + loa, hoạt động trong LAN.

### Lời nói

“Hệ thống hỗ trợ bảo vệ quan sát xe qua cổng, đọc biển và xem bằng chứng để xử lý. Hôm nay chúng tôi trình diễn bằng laptop, hai camera và loa trên mạng nội bộ, kể cả khi ngắt Internet.”

### Hình và căn cứ

Ảnh toàn cảnh bố trí demo thực tế, chưa có ảnh thì dùng sơ đồ camera–laptop–loa. Không dùng mock99% hoặc ảnh nhận diện khuôn mặt.

## Slide2 — Một luồng làm việc rõ ràng

Thời lượng chính:20giây. Nhãn: `UI ĐÃ KIỂM CHỨNG · LUẬT CẦN NGHIỆM THU`.

### Nội dung hiển thị

- Giám sát: xem camera, biển đọc và tình trạng bằng chứng.
- Vi phạm: kiểm ảnh và lịch sử; báo cáo nằm cùng luồng.
- Xe đăng ký: đối chiếu biển đã xác nhận.
- Cài đặt: camera, vùng đọc, lưu trữ; AI nâng cao chỉ dành cho admin.

### Lời nói

“Bảo vệ làm việc trên Giám sát; người quản lý kiểm bằng chứng trong Vi phạm. Xe đăng ký và Cài đặt được tách rõ. Mỗi tài khoản chỉ thấy phần phù hợp quyền. Trường hợp ảnh yếu hoặc biển mâu thuẫn cần người duyệt trước khi gắn với hồ sơ.”

### Hình và căn cứ

Screenshot bốn menu của bản mới. `task-05/UI_REPORT.md`: browser9/9 cho auth/quyền/dataset/media/bbox; camera preview/WS trong bộ test có stub.

## Slide3 — Demo chạy tại chỗ khi mất Internet

Thời lượng chính:25giây. Nhãn: `KIẾN TRÚC LOCAL HIỆN CÓ · OFFLINE CẦN KIỂM THẬT`.

### Nội dung hiển thị

- Hai camera RTSP trong LAN → laptop xử lý bằng GPU local.
- Web, đăng nhập, weights và bằng chứng đều phục vụ tại máy.
- Âm thanh dùng giọng Việt local đã kiểm hoặc câu nhắc lưu sẵn.
- Rút cáp WAN của router, giữ kết nối LAN trong phần demo.

### Lời nói

“Internet không nằm trong đường nhận diện của buổi demo. Camera gửi hình qua router tới laptop; giao diện và dữ liệu được mở tại máy. Chúng tôi sẽ rút WAN, giữ LAN rồi kiểm hình mới và âm thanh. Giọng đọc phải chạy tại máy; nếu không có, dùng câu nhắc đã lưu sẵn.”

### Hình và căn cứ

Sơ đồ ba khối `2camera LAN → laptop/GPU/DB/web → loa`; router WAN có công tắc ngắt. `app/config.py`, `app/main.py`, capture/owner hiện có. Không vẽ VPS như dependency đang hoạt động. Font Google trong `frontend/index.html` và chọn giọng trong `utils/speak.js` còn cần xử lý/kiểm offline trước chốt build.

## Slide4 — Phần đã làm và bằng chứng kiểm thử

Thời lượng chính:25giây. Nhãn: `ĐÃ KIỂM CHỨNG TRONG PHẠM VI NÊU`.

### Nội dung hiển thị

- Capture độc lập, frame mới nhất, JPEG chia sẻ: đã có mã và focused test.
- UI: 9/9 browser test; **R0–R9 subset**: 152 pass, 1 skip, 0 fail (~35s).
- Audit/export dataset: 10/10 selftest; không dùng nhãn dự đoán làm ground truth.
- **R8–R9 full**: 1.277 pass, 2 skip, 0 fail (~443s) — bản cũ, chưa re-run sau sửa.
- Hai camera, chất lượng nhận diện, tiếng Việt offline: còn cần nghiệm thu thật.

### Lời nói

“Chúng tôi đã tách capture khỏi AI và rút gọn giao diện. Bộ regression R8–R9 có
1.277 bài đạt, và giao diện có chín bài browser đạt. Đây là kiểm phần mềm;
chất lượng nhận diện và loa phải được đối chiếu riêng trên camera, kể cả khi
không có Internet.”

### Hình và căn cứ

Nguồn: `tasks/task-05/regression-r8-r9.xml`, `UI_REPORT.md`, `DATA_REPORT.md`.
Report đã full rerun nhưng chưa chứng minh các thay đổi sau report. Trước freeze lấy
report cuối và thay số nếu phạm vi đã đổi. R3/R14 decode file không chứng
minh FPS preview/AI; R6 recognizer mock không chứng minh OCR model thật.

## Slide5 — Biển số: ưu tiên đúng và có thể kiểm tra

Thời lượng chính:25giây. Nhãn: `ĐÃ CÓ MÃ · TOÀN CHUỖI CẦN NGHIỆM THU`.

### Nội dung hiển thị

- Detect → track → chọn crop → OCR → đồng thuận nhiều frame.
- Hai mẫu độc lập là điều kiện chốt; một crop biến đổi không thành hai phiếu.
- Biển mờ, thiếu chữ hoặc mâu thuẫn → cần duyệt.
- Giữ ảnh gốc và nguồn quan sát; không ép khớp xe đăng ký.

### Lời nói

“Biển số cần được kiểm qua nhiều frame và giữ ảnh nguồn. Khi thiếu chữ hoặc các lần đọc mâu thuẫn, kết quả phải chuyển cần duyệt. Danh sách xe đăng ký chỉ dùng đối chiếu sau xác nhận, không dùng để sửa một chuỗi yếu. Phần nối metadata toàn chuỗi vẫn là hạng mục nghiệm thu.”

### Hình và căn cứ

Một crop rõ và một crop yếu của ca đã gán nhãn, không tự điền biển chưa biết. `best_plate.py`, `plate_consensus.py`, adapter CCT và handoffR4–R6; metadata/ByteTrack thật/biển hai dòng còn mở.

## Slide6 — Cảnh báo ngắn, đúng tình huống, đúng lúc

Thời lượng chính:25giây. Nhãn: `MÃ BEEP/TTS HIỆN CÓ · LUỒNG AN TOÀN CẦN NỐI VÀ KIỂM`.

### Nội dung hiển thị

- Kiểm mũ, số người, tư thế qua cổng theo bằng chứng quan sát được.
- Một lượt xe: gộp lỗi; loa nhắc ngắn, không đọc biển chưa xác nhận.
- Chỉ một máy giữ quyền phát loa; reconnect không đọc lại cảnh báo cũ.
- Dùng âm thanh tại máy khi WAN ngắt; bất định chuyển người duyệt.

### Lời nói

“Loa cần nhắc ngắn như ‘Vui lòng đội mũ’ hoặc ‘Vui lòng dắt xe’, theo lỗi đã xác nhận. Một lượt không được phát lặp ở nhiều màn hình. Luồng banner cũ hiện chưa nối đầy đủ lọc và quyền loa; bản demo chỉ bật tự động sau khi kiểm việc này cùng âm thanh offline.”

### Hình và căn cứ

Ba nhãn `đã xác nhận → một lần nhắc → bảo vệ kiểm ảnh`. GuardPage import AlertBanner; AlertBanner đang gọi beep/TTS trực tiếp, chưa dùng `createAlertAudio`/`useAudioLease`; backend có `audio_authorized`. Không ghi “tiếng Việt offline đã đạt” chỉ vì có giọngvi-VN trong danh sách.

## Slide7 — Bảy phút để kiểm chứng luồng thực tế

Thời lượng chính:25giây. Nhãn: `KỊCH BẢN DEMO · KẾT QUẢ GHI SAU TỔNG DUYỆT`.

### Nội dung hiển thị

- Đăng nhập, hai camera, rút WAN giữ LAN.
- Xe có biển rõ; tình huống mũ/qua cổng có nhãn đối chiếu.
- Biển yếu → cần duyệt; kiểm ảnh và một lượt sự kiện.
- Nghe loa, xem lịch sử, mở AI nâng cao; có bản ghi dự phòng.

### Lời nói

“Phần tiếp theo kéo dài bảy phút. Chúng tôi sẽ mở hai camera, ngắt Internet và chạy các tình huống đã chuẩn bị. Người xem có thể đối chiếu ảnh, chuỗi biển, cảnh báo và lịch sử. Nếu thiết bị lỗi, chúng tôi chuyển sang bản ghi đã ghi rõ nguồn, không gọi đó là kết quả live.”

### Hình và căn cứ

Timeline gọn của `DEMO_RUNBOOK.md`. Cảnh live phải được tổng duyệt; video/file hoặc payload giả lập phải công bố ngay khi sử dụng.

## Slide8 — Bản bàn giao có thể vận hành và kiểm lại

Thời lượng chính: 20 giây. Nhãn: `BÀN GIAO · TRẠNG THÁI THEO BẢN FREEZE`.

### Nội dung hiển thị

- Bản chạy, cấu hình/model được pin, báo cáo và cách khôi phục baseline.
- Tài liệu vận hành, slide/PDF, video dự phòng và kịch bản demo.
- VPS/trang giới thiệu theo trạng thái đã kiểm; local hoạt động độc lập.
- Tiếp tục nghiệm thu dài hạn và nâng model bằng dữ liệu đã duyệt.

### Lời nói

“Bản bàn giao giữ đúng build, cấu hình và bằng chứng kiểm, có hướng dẫn vận
hành và cách quay lại baseline. Local xử lý tại cổng; VPS phục vụ phần nhẹ
theo trạng thái đã nghiệm thu. Tiếp theo là phần demo bảy phút để đối chiếu
những gì hệ thống thực sự làm được.”

### Hình và căn cứ

Ảnh bản chạy hoặc danh sách ngắn artifact thật. Trạng thái VPS lấy từ
`VPS_STATUS.md`: deployed/pending_access/pending_sync, không gọi toàn bộ đã
xong nếu chỉ deploy landing. Chuyển ngay sang demo; slide 9–12 chỉ khi hỏi.

## Slide9 — Phụ lục: thước đo chất lượng và tốc độ

Thời lượng:Q&A, ngoài180giây. **Hai dòng tách riêng để tránh chồng chữ trong PPTX/PDF:**
Tiêu đề slide: "Thước đo chất lượng và tốc độ (mục tiêu, chưa đo)".
Trạng thái chip ở chân trang: "PHỤ LỤC · CHƯA CÓ SỐ ĐO NGHIỆM THU".

### Nội dung hiển thị

- ALPR toàn chuỗi: đúng≥95% trong các biển tự chốt; coverage≥90% lượt có biển rõ.
- Hai camera: preview mới≥15FPS/camera, AI≥5FPS/camera; biểnp95≤2giây từ vùng đọc.
- Mũ: precision≥98%, recall≥95%; hành vi/số người: precision≥95%, recall≥90%.
- Holdout tối thiểu300lượt cho kiểm gán học sinh; công bố cả lỗi/cần duyệt/bỏ sót.

### Lời nói

“Đây là tiêu chí mục tiêu đã chốt trong plan, chưa phải kết quả đo. Phải có nhãn người duyệt độc lập, tính cả bỏ sót và cần duyệt, và báo riêng mờ, đêm, phối cảnh, hai dòng. Không thấy lỗi trong vài lượt demo không đủ chứng minh đạt các tỷ lệ này.”

### Căn cứ

Plan đợt5 và handoff mục4. Đo độ trễ loa riêng theo event→beep→speech và kiểm nghe thật; không lấy GPU utilization hoặc confidence OCR thay cho accuracy.

## Slide10 — Phụ lục: dữ liệu và phương án YOLO11

Thời lượng:Q&A, ngoài180giây. Nhãn: `AUDIT ĐÃ KIỂM · TRAIN/WEIGHTS MỚI CHƯA ĐẠT`.

### Nội dung hiển thị

- 8.259 ảnh detect,3.188 ảnh ký tự: hợp lệ cấu trúc, chưa có holdout độc lập.
- Detect có4nhóm trùng,1nhóm rò train/val; bộ nhãn mũ0ảnh.
- Ultralytics đã lên8.4.168; weights runtime chưa chuyển YOLO11.
- Duyệt nhóm/nhãn → export Kaggle riêng tư → train từng bài toán → đánh giá/rollback.

### Lời nói

“Nâng package không đồng nghĩa đã nâng model. Đã có audit, công cụ xuất dữ
liệu người duyệt và ba notebook Kaggle. Notebook chưa chứng minh training
đã chạy; dữ liệu mũ và xe điện vẫn cần bổ sung. Chúng tôi đánh giá YOLO11n
trước, giữ baseline để quay lại nếu chất lượng hoặc tốc độ không đạt.”

### Căn cứ

`DATA_REPORT.md`, `CURSOR_HANDOFF.md`. CCT adapter/ONNX/config local hiện có; smoke thật, holdout và promotion còn mở. 3.173 đề xuất chuỗi từ bbox không tự thành ground truth.

## Slide11 — Phụ lục: VPS và giới thiệu sản phẩm

Thời lượng:Q&A, ngoài180giây. Nhãn: `ĐỀ XUẤT · CHƯA XÁC NHẬN DEPLOY`.

### Nội dung hiển thị

- Local giữ camera, inference, âm thanh và vận hành khi mất Internet.
- VPS dự kiến103.101.162.111 phục vụ trang giới thiệu và phần nhẹ qua HTTPS.
- Đồng bộ/remote cần contract và kiểm riêng; SSH/domain chưa xác minh.
- Giới thiệu theo bằng chứng: bỏ face matching,0,2giây,99% và form báo gửi giả.

### Lời nói

“Buổi demo offline không cần VPS. Kiến trúc đề xuất đặt inference tại trường; VPS phục vụ phần nhẹ khi đã kiểm kết nối và bảo mật. Nội dung marketing phải phản ánh đúng sản phẩm. Nhận diện khuôn mặt, tỷ lệ99% hay tốc độ0,2giây trên trang cũ không phải khả năng được kiểm chứng để công bố.”

### Căn cứ

`marketing/landing.html` còn face/0.2/99.x, form chỉalert; `landing/index.html` còn99.2%,30.2FPS/99.1% và submit giả. `scripts/deploy_vps.sh` có script nhưng không chứng minh đã deploy; còn cần tách dependencies/flagCV/TLS/static assets phù hợp VPS. Không mở form cũ và nói “đã gửi đăng ký”.

## Slide12 — Phụ lục: điều kiện thông qua và rollback

Thời lượng:Q&A, ngoài180giây. Nhãn: `CHECKLIST NGHIỆM THU · ĐIỀN THEO KẾT QUẢ THẬT`.

### Nội dung hiển thị

- Sau rútWAN: cold refresh/login, hai feed mới, event/media và loa vẫn hoạt động.
- Hai viewer: một owner phát loa; không đọc lại lịch sử hoặc phát sai biển.
- Báo cáo giữ build/weights hash, nguồn ca, GT, kết quả và giới hạn.
- Lỗi live chuyển bản ghi có nhãn; rollback về build/weights/config đã kiểm.

### Lời nói

“Thông qua demo cần cả hình, nhận diện, bằng chứng và loa hoạt động thật khi không có Internet. Bản ghi dự phòng phải có nguồn rõ. Khi lỗi, chúng tôi giữ baseline và công bố giới hạn; không đổi nhãn, bỏ test hoặc gán tay một kết quả rồi gọi đó là AI.”

### Căn cứ

`DEMO_RUNBOOK.md` dưới đây là checklist chưa thực thi. Kiểm voice.localService=true và nghe tại loa khi WAN tắt; nếu không có giọng Việt local, dùng clip nhắc chung lưu sẵn, không đọc biển bằng cloudTTS hoặc chuỗi bất định.

## Chỉ dẫn xuất deck

- Deck16:9; dùng navy/trắng, chữ≥24pt cho thân,36pt cho tiêu đề; không nhồi các ghi chú kỹ thuật lên slide.
- Ghi speaker notes từ phần “Lời nói”; đặt nguồn/phạm vi chứng minh trong notes hoặc chân trang nhỏ.
- Slide9–12 phải mang dấu “Phụ lục”; tổng diễn giải chính180giây, demo420giây. Bản nói120giây rút lời, vẫn giữ mệnh đề “chưa nghiệm thu”, không mở phụ lục.
- Xuất PPTX và PDF tại máy; kiểm tiếng Việt, font fallback, ảnh/link/video offline và chế độ trình chiếu khiWAN đã ngắt. Đây là nội dung nguồn, chưa phải file deck đã render/kiểm.

Nguồn hiện trạng: `tasks/task-05/{STATUS_BOARD.md,CURSOR_HANDOFF.md,UI_REPORT.md,DATA_REPORT.md}`, `frontend/src/{App.jsx,pages/GuardPage.jsx,components/AlertBanner.jsx,utils/alertAudio.js,utils/alertFilter.js,utils/useAudioLease.js,utils/speak.js}`, `app/api/{guard.py,audio_lease.py}`, `frontend/index.html`, hai trang landing và deploy script. Không dùng README lịch sử thay cho trạng thái đợt5.
