# Prompt giao Cursor: ổn định hai camera Imou trước/sau cùng cổng và hoàn thiện toàn bộ hệ thống

## 1. Mục tiêu, cấu hình đã chốt và cách thực hiện

Bạn tiếp tục phát triển hệ thống giám sát cổng trường trong repository hiện tại. Hoàn thành lượt sửa đang chạy, đọc lại mã và execution log rồi tích hợp kế hoạch này; không triển khai chồng hai phiên sửa cùng phần mã.

**Bối cảnh đã xác nhận:**

- Hai camera Imou **quan sát trước/sau cùng một cổng vật lý**, đều kết nối bằng dây LAN.
- Máy xử lý: i7-12700H, RAM 16 GB, RTX 3050 Laptop 4 GB.
- Vận hành theo ca **8–12 giờ**, khoảng **2–3 thiết bị truy cập đồng thời**.
- Một máy bảo vệ được chọn để phát âm thanh; máy khác mặc định chỉ xem.
- Ưu tiên ít báo sai, không gán nhầm biển/học sinh và không để AI làm giật hình.
- Tiếp tục các yêu cầu A–D, đợt R và E1–E4 còn phù hợp. **Thay giả định “hai camera là hai cổng” bằng mô hình “hai camera hỗ trợ cùng một lượt xe qua một cổng”.**

Mục tiêu là một hệ thống có thể nghiệm thu bằng số liệu, có khả năng phục hồi và bảo toàn bằng chứng. Không tuyên bố “chuẩn doanh nghiệp” chỉ dựa trên số test hoặc FPS của một model.

Giữ FastAPI, React và SQLite trong đợt này. Chưa chuyển sang microservices, PostgreSQL, cloud hoặc thay toàn bộ model khi chưa có phép đo chứng minh cần thiết.

## 2. Các phát hiện cần xác nhận lại trước khi sửa

Repository đang được Cursor chỉnh sửa. Những điểm dưới đây là kết quả kiểm tra tại thời điểm rà soát, phải đối chiếu với mã mới trước khi nhận là lỗi còn tồn tại.

Đã kiểm tra cú pháp **89 tệp Python**, không phát hiện lỗi cú pháp. Đây chưa phải kiểm thử chức năng hoặc nghiệm thu camera thật.

| Nhóm | Phát hiện cần xử lý |
|---|---|
| Mô hình camera | `gate_id` đang được dùng cho từng nguồn hình, trong khi hai nguồn thực tế thuộc cùng một cổng. Dễ tạo sự kiện trùng hoặc ghép sai bằng chứng. |
| Crossing | Kiểm tra cách ly cho thấy ba frame ở phía đầu và **một frame ở phía sau** đã trả crossing. Chưa đáp ứng yêu cầu ba frame ổn định mỗi phía. |
| WebSocket | Có nhánh giữ `threading.Lock` qua `await send_text`; từng kết nối tham gia lấy sự kiện từ queue. Client chậm có thể ảnh hưởng việc phân phối. |
| Truy cập từ máy khác | Frontend còn dùng `localhost:8001`; trên máy người dùng, địa chỉ này trỏ về chính máy đó. Cookie chưa thay thế đầy đủ token trong localStorage và URL video/WebSocket. |
| Media | API tạo URL, thư mục lưu và endpoint phục vụ chưa thống nhất. Có đường dẫn ghép thành `snapshots/snapshots/...`; phạm vi giáo viên còn suy ra từ tên file thay vì quan hệ trong DB. |
| Phân quyền | Giáo viên không có lớp được truyền bộ lọc lớp rỗng xuống DB; truy vấn có thể trở thành không giới hạn lớp. Quyền trong JWT chưa được đối chiếu đầy đủ với thay đổi tài khoản hiện tại. |
| Luồng quản trị | Trang lịch sử gọi API chi tiết xe chưa có; phân trang lịch sử chỉ giữ 20 dòng đầu. Trang vi phạm đổi offset nhưng effect tải dữ liệu chưa phụ thuộc offset. |
| Dữ liệu đầu vào | `limit=-1` được chuyển xuống DB. Đăng ký công khai, upload ảnh và endpoint tạo cảnh báo thử chưa được khóa đầy đủ theo môi trường. |
| Bằng chứng và vận hành | Cần kiểm tra lại tên file theo giây, cooldown dùng `UNKNOWN`, cảnh báo phát trước khi media ghi xong, cleanup bỏ qua lỗi và backup chưa bao phủ đầy đủ media. |
| Kiểm chứng | CI đang cho phép E2E thất bại mà job vẫn thành công. Một số test chỉ kiểm tra thuộc tính hoặc nhận 404, chưa chứng minh luồng thành công hoạt động. |

Các lỗi capture/OCR/JPEG của đợt R phải được kiểm chứng lại bằng test hành vi. Không mặc định chúng còn lỗi, cũng không mặc định đã đạt vì execution log ghi “DAT”.

## 3. Các đợt triển khai

### Đợt 0 — Khóa hiện trạng và chuẩn bị kiểm chứng

- Ghi commit, `git status`, phiên bản dependency thực cài, cấu hình chạy và hash model. Không ghi mật khẩu camera, JWT hoặc dữ liệu học sinh vào báo cáo.
- Lập ma trận yêu cầu với bốn trạng thái: **đã kiểm chứng / lỗi tái hiện được / đang triển khai / chưa đủ dữ liệu**.
- Tách cấu hình test: DB tạm hoặc SQLite backup, media tạm, nguồn video giả, cổng API riêng; mặc định không mở RTSP thật trong test.
- App dùng cho integration test phải đi qua cùng app factory, router, middleware và cấu hình production; không dựng một app thử khác rồi coi là đã kiểm tra production.
- Chạy baseline phù hợp sau khi lượt sửa hiện tại kết thúc. Ghi lỗi trước sửa và lỗi phát sinh riêng.
- Dùng 14 video tại `C:\Users\khucv\Downloads\tranning` cho phép đo có thể tái lập. Video chưa có nhãn hoặc không quay đồng bộ trước/sau không được dùng để tuyên bố độ chính xác ghép hai camera.

### Đợt 1 — Tách cổng vật lý, camera và lượt xe

**Định danh và tương thích**

- Mỗi camera có `camera_id` ổn định; mỗi cổng vật lý có `gate_id`.
- Hai camera hiện tại thuộc một `gate_id`, với vai trò `front` và `rear`. Admin xác nhận vai trò bằng hình xem trước; không đoán từ tên nguồn cũ.
- Track chỉ có ý nghĩa trong bộ khóa `(camera_id, source_epoch, track_id)`.
- Một lượt xe ở cổng có `encounter_id`; một sự kiện có `event_id` UUID và `event_version` tăng khi cập nhật.
- Mỗi bằng chứng giữ camera, phiên nguồn, frame, thời điểm quan sát, phiên bản model và cấu hình quyết định.
- Migration bổ sung bảng/cột và mapping camera–cổng, chạy lặp an toàn. Không viết lại ý nghĩa `gate_id` trong bản ghi lịch sử.
- API cũ giữ hợp đồng chọn nguồn POST **202**, trạng thái `checking/applied/error`; đổi nguồn thất bại giữ nguồn cũ.
- Dữ liệu realtime mới có `schema_version=2`. Trong schema mới, `gate_id` luôn là cổng vật lý; client cũ được phục vụ qua lớp tương thích, không âm thầm đổi nghĩa trường.

**Phân công mặc định theo góc nhìn**

| Camera | Nhiệm vụ chính |
|---|---|
| Trước | Người–xe, mũ, hành vi đi xe/dắt xe, crossing; gương chỉ khi góc nhìn đạt kiểm chứng |
| Sau | Xe, biển số, crop OCR và bằng chứng phía sau |

Chỉ nạp các model cần cho hồ sơ của từng camera. Không mặc định chạy cả ba detector và pose trên mọi người ở cả hai nguồn.

Mỗi loại lỗi có một camera chịu trách nhiệm phát cảnh báo mặc định. Camera còn lại bổ sung bằng chứng; không độc lập phát lại cùng lỗi của cùng lượt xe.

### Đợt 2 — Giữ hình mới và ổn định xử lý hai nguồn

**Capture và hiển thị**

- Mỗi camera có luồng đọc riêng, chỉ giữ một frame mới nhất cho AI. Không tích lũy hàng đợi frame cũ.
- Luồng hiển thị độc lập với detect, OCR, ghi DB và ghi clip.
- Frame mang `camera_id`, `source_epoch`, `frame_seq`, thời gian nhận và timestamp nguồn nếu có. Dùng đồng hồ monotonic để tính độ trễ; lưu thời gian nghiệp vụ theo UTC.
- Giữ ảnh nguồn chưa vẽ để crop OCR/bằng chứng. Ảnh detect và hiển thị là bản thu nhỏ giữ tỷ lệ.
- JPEG được encode một lần cho mỗi frame hiển thị mới và chia sẻ giữa viewer, kể cả khi không thấy người hoặc bỏ lượt AI.
- Overlay hết hạn sau 500 ms nếu chưa có kết quả mới. Mất hình mới quá hai giây phải thể hiện “hình cũ/mất tín hiệu”, không giữ nhãn LIVE.
- Tách số đo FPS capture, FPS hình mới hiển thị và FPS AI. Gửi lặp JPEG không được tính là frame mới.

**RTSP và phục hồi**

- Ghi hồ sơ thực tế mỗi camera: model, firmware, codec, độ phân giải, FPS, bitrate, chu kỳ keyframe và backend decode. Không giả định mọi camera Imou hỗ trợ cùng tùy chọn.
- Giữ RTSP TCP làm baseline. Xác minh timeout mở/đọc thực sự hoạt động trên backend đang cài.
- Reconnect theo backoff 1–2–4–8 giây, tối đa 10 giây, có jitter; không tạo luồng hoặc model mới sau mỗi lần lỗi.
- Mỗi lần nối lại làm mất tính liên tục của track phải tạo phiên nguồn mới và vô hiệu hóa bằng chứng đang chờ của phiên trước.
- Một camera hỏng không làm ngừng camera kia. Hiển thị rõ tính năng nào bị thiếu do mất camera.
- Chỉ thử hardware decode khi backend hỗ trợ và có đo CPU, latency trước/sau; không coi cài CUDA là đã dùng GPU để giải mã video. Đối chiếu [tài liệu OpenCV](https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html).

**AI và OCR**

- Giữ model/tracker state riêng theo camera. Điều phối GPU bằng cơ chế cấp lượt có giới hạn và công bằng; không để các pool tự tạo nhiều inference cạnh tranh không kiểm soát.
- Một model instance chỉ có một bên sở hữu thực thi tại một thời điểm. Tuân thủ nguyên tắc [inference an toàn của Ultralytics](https://docs.ultralytics.com/guides/yolo-thread-safe-inference/).
- OCR dùng worker riêng, tối đa một yêu cầu chạy/chờ mỗi track; hàng đợi chờ toàn hệ thống giới hạn tám yêu cầu. Khi đầy, giữ mẫu tốt hơn hoặc bỏ yêu cầu và tăng bộ đếm; không chặn capture.
- Không fallback sang OCR đồng bộ khi worker bận. Thu kết quả đúng một lần, kiểm tra phiên nguồn và thời điểm trước khi voting.
- Crop gửi worker phải là bản sao độc lập. Không dùng lại frame OCR cũ làm một phiếu mới.
- Pose chỉ chạy cho nhóm người–xe cần phân loại hành vi; không chạy cho toàn bộ người đi bộ.
- Nếu quá tải: giảm tác vụ không thiết yếu và giữ bằng chứng ở trạng thái chưa xác định. Không hạ tiêu chuẩn xác nhận để che việc AI chạy chậm.

### Đợt 3 — Nhận diện đúng và ghép trước/sau thận trọng

**Xác nhận từng lỗi**

Giữ nguyên các ngưỡng E1–E4:

- Tối đa năm quan sát hợp lệ trong 1,5 giây; ít nhất bốn mẫu đồng thuận, tỷ lệ ≥80%, trải dài ≥400 ms, cách nhau ≥100 ms.
- Chỉ tính frame mới. Mẫu mờ, quá nhỏ, bị che hoặc chưa có track ổn định là `unknown`.
- Bằng chứng trái chiều đáng tin cậy chuyển `needs_review`.
- Không đội mũ: phải thấy đầu không đội mũ, thuộc đúng người đang đi xe; mũ cầm tay/treo xe không được tính là đang đội.
- Không dắt xe: phải xác nhận đang đi xe và crossing hợp lệ, với ba frame ổn định mỗi phía trong tối đa năm giây. Đứng yên, dắt bộ hoặc `unknown` không được dùng làm đường tắt.
- Biên chống rung crossing tính trong tọa độ ảnh theo 2% đường chéo; kiểm tra đúng với ảnh không vuông.
- Gương trái theo phía người ngồi lái. Không thấy box gương không đồng nghĩa thiếu gương; nhánh này mặc định chỉ đánh giá cho tới khi đạt kiểm chứng.
- OCR cần ít nhất hai crop khác frame đọc giống toàn biển, đủ chất lượng và không có kết quả cạnh tranh đáng tin cậy.
- OCR lỗi, chưa xong hoặc rỗng không tự trở thành “che biển/không có biển”. Biển chưa rõ hiển thị vàng, không beep hoặc đọc loa.
- Giữ tất cả lỗi đã xác nhận trong `issues[]`; không bỏ lỗi mũ chỉ vì đã có lỗi đi xe qua cổng.

**Ghép bằng chứng hai camera**

- Camera trước tạo lượt xe và có thể cảnh báo lỗi đã xác nhận ngay, không chờ camera sau đọc biển.
- Ghép theo cùng cổng, hướng di chuyển, vùng/làn đã hiệu chỉnh, thời điểm đi qua và sự liên tục của track.
- Biển chính xác đã xác nhận ở cả hai phía là bằng chứng hỗ trợ; biển gần giống chỉ tạo gợi ý xem lại.
- Không ghép chỉ vì hai bản ghi gần thời gian, giống một phần biển hoặc có cùng số track.
- Khi chỉ một camera đọc được biển, chỉ gắn biển đó vào lượt trước nếu phép ghép hai góc đã đạt kiểm chứng và có duy nhất một ứng viên phù hợp. Có nhiều ứng viên hoặc biển mâu thuẫn thì để chưa ghép.
- Mặc định tắt tự động ghép cho cấu hình góc nhìn chưa hiệu chỉnh. Lưu quan sát phía sau để người dùng kiểm tra, không tự gán học sinh.
- Khi ghép được, bổ sung ảnh sau và biển vào cùng event, tăng version; không tạo thêm lượt vi phạm và không đọc lại lỗi cũ.
- Mất camera sau: lỗi mũ/hành vi vẫn hoạt động, biển có thể chưa rõ. Mất camera trước: camera sau tiếp tục hình/OCR; chỉ phát những loại lỗi mà chính góc sau đã được nghiệm thu.

**Dữ liệu và huấn luyện**

- Chuẩn hóa nhãn đầu có/không mũ, biển một/hai dòng, gương nhìn thấy và trạng thái quan sát; hành vi gán theo đoạn video.
- Lưu video nguồn, timestamp, camera, lượt xe và chất lượng quan sát. Không đoán nhãn trên mẫu mơ hồ.
- Chia 70/15/15 theo video hoặc phiên; giữ cả hai góc của cùng lượt xe trong cùng một tập.
- Rà toàn bộ nhãn tự sinh, kiểm tra lần hai ít nhất 20% và toàn bộ mẫu khó.
- Đo riêng detector, ghép đối tượng, OCR toàn biển, ghép hai camera và quyết định cảnh báo.
- Giữ model hiện tại làm baseline. Thử YOLO11/tracker/FP16 trong môi trường riêng và trên GPU mục tiêu; chỉ thay khi tốt hơn về chất lượng và đạt độ trễ.
- Nếu biển hoặc đầu không nhìn rõ ngay cả với người xem, ghi yêu cầu chỉnh góc/ánh sáng/cấu hình nguồn. Không hứa fine-tune sẽ khôi phục chi tiết không có trong ảnh.

### Đợt 4 — Sự kiện, media, WebSocket và âm thanh đáng tin cậy

**Dữ liệu sự kiện**

- Một event chứa `event_id`, cổng, encounter, version, thời gian quan sát/xác nhận, các quan sát từng camera và `issues[]`.
- Mỗi issue có mã, trạng thái AI, lý do, số mẫu và tham chiếu bằng chứng.
- Tách trạng thái AI khỏi trạng thái xử lý `pending/reviewed/resolved/reopened`.
- Ràng buộc duy nhất ở DB ngăn tạo trùng cùng encounter. Không dùng `UNKNOWN` làm cooldown chung cho các xe khác nhau.
- Ảnh, crop và clip dùng UUID; không đặt tên chỉ bằng giây và loại lỗi.
- Chỉ trả URL media đã ghi thành công. Có thể cập nhật bảng trước với `evidence_state=pending`, rồi bổ sung media; thất bại phải hiện trạng thái lỗi.
- Snapshot/crop bắt buộc được xác nhận ghi và liên kết DB trước khi phát âm thanh chính thức; không phải đợi clip hoàn tất.
- Không âm thầm mất lỗi ghi DB/media. Lưu số lỗi, retry giới hạn và hiển thị tình trạng suy giảm; không giả vờ sự kiện đã lưu.

**Phân phối cảnh báo**

- Một bộ phân phối đọc luồng sự kiện đã lưu, gửi cho các subscriber của cổng vật lý.
- Không giữ khóa đồng bộ qua `await`.
- Mỗi client có queue tối đa 64 cập nhật; client chậm bị ngắt và đồng bộ lại, không chặn capture hay client khác.
- Dùng event ID/version để upsert và chống trùng. Reconnect lấy lại trạng thái đã bỏ lỡ; không phát âm thanh lịch sử.
- Ghi thông tin chờ phát cùng transaction sự kiện để khôi phục sau crash; cho phép gửi lại nhưng client không nhân đôi.
- Giao diện song song hiển thị cả trước/sau và một bảng lượt xe chung.

**Âm thanh**

- Câu ngắn theo tên cổng vật lý, không đọc “cổng trước/cổng sau”.
- Giữ tốc độ mặc định 1.15, chỉnh 0.9–1.4; có nghe thử và trạng thái trình duyệt chặn âm thanh.
- Gộp trong 300 ms, tối đa hai lời nhắc; ưu tiên dắt xe → mũ → gương.
- Queue tối đa hai câu chờ, bỏ câu quá năm giây; không chồng tiếng.
- Dedup theo event + mã lỗi; tắt âm thanh, mất quyền phát hoặc đổi phạm vi phải dọn timer/audio.
- Server chỉ cấp quyền phát cho một phiên bảo vệ của cổng: lease 15 giây, heartbeat năm giây. Viewer khác không tự giành quyền; người dùng bật loa bằng thao tác rõ ràng.

### Đợt 5 — Hoàn thiện admin, người dùng và bảo mật

**Đăng nhập và phạm vi truy cập**

- Browser dùng cookie `HttpOnly`, `SameSite=Lax`; `Secure` khi HTTPS. API Bearer được giữ cho script trong giai đoạn chuyển tiếp.
- Bỏ token khỏi localStorage và URL video/WebSocket. Tất cả URL frontend cùng origin; dev qua proxy, bản triển khai phục vụ frontend build cùng hệ thống backend.
- Khi mở ứng dụng, lấy phiên từ `/me`; không tin role lưu trong trình duyệt.
- Kiểm tra tài khoản còn hiệu lực, phiên bản phiên và quyền hiện tại. Đổi mật khẩu, khóa/xóa tài khoản hoặc đổi quyền phải vô hiệu hóa phiên cũ.
- Kiểm tra Origin cho thao tác ghi bằng cookie và WebSocket; không dùng CORS thay cho kiểm tra này.
- Giới hạn đăng nhập, mặc định 10 lần thất bại/15 phút theo tài khoản và nguồn truy cập; không log mật khẩu/token.
- Loại credential RTSP cố định khỏi mã; lưu cấu hình bí mật local ngoài Git, API chỉ trả thông tin đã che.
- Cấu hình vận hành cho 2–3 máy phải có HTTPS nội bộ được tin cậy. Nếu chưa có HTTPS, ghi rõ mới đạt môi trường thử LAN, chưa đạt nghiệm thu bảo mật.

**Quyền nghiệp vụ**

| Vai trò | Quyền mặc định |
|---|---|
| Admin | Cấu hình, tài khoản, roster/xe, sự kiện, bảo trì và báo cáo |
| Bảo vệ | Camera trực tiếp, cảnh báo, xem bằng chứng và xử lý trạng thái được cấp |
| Quản lý | Xem tổng hợp, sự kiện và quyền xử lý hiện có; không sửa cấu hình/tài khoản |
| Giáo viên | Chỉ dữ liệu, ảnh và clip thuộc phạm vi lớp được cấp |
| Khách | Không xem camera, roster, sự kiện hoặc media; đăng ký công khai tắt mặc định |

Giáo viên thiếu lớp hoặc tài khoản không hợp lệ phải bị từ chối, không được biến thành truy vấn toàn trường. Áp dụng cùng quy tắc cho list, detail, export, ảnh và clip.

**Media**

- Phục vụ media bằng ID và quan hệ media → event/xe/học sinh trong DB, không suy ra chủ sở hữu từ tên file.
- Chuẩn hóa đường dẫn cho Windows, kiểm tra đường dẫn thực nằm trong media root; không dùng `startswith` đơn thuần để chống vượt thư mục.
- Có lớp tương thích cho media lịch sử, không di chuyển/xóa hàng loạt dữ liệu cũ.
- Ảnh đúng quyền phải trả được ảnh thật; clip phải phát và tua được. Kiểm tra Range với phiên bản Starlette thực cài, không suy từ tài liệu phiên bản mới.
- Tắt static media công khai ở cấu hình dùng dữ liệu thật.

**Sửa các luồng web**

- Bổ sung API chi tiết xe và chi tiết vi phạm; không tìm chi tiết bằng cách tải 200 dòng rồi dò ID.
- Phân trang phía server, `limit` 1–200 và `offset≥0`; thứ tự ổn định theo thời gian và ID.
- Bộ lọc, chuyển trang và chọn xe phải tải đúng dữ liệu, bỏ phản hồi cũ khi request mới đến; reset trang trước khi áp dụng bộ lọc.
- Không hiển thị lỗi tải thành “không có dữ liệu”. Có loading, empty, error, retry và trạng thái dữ liệu cũ rõ ràng.
- Mutation khóa nút khi đang gửi; sửa trạng thái dùng version để tránh hai người ghi đè nhau. Trả 409 khi xung đột và cho tải lại.
- Mỗi dòng hiển thị lỗi cụ thể, biển xác nhận/chưa rõ, ảnh trước/sau, trạng thái xử lý và lý do cần kiểm tra. Không biến confidence thành “độ chính xác kết luận”.
- Trang ROI hỗ trợ ROI và đường cắt theo từng camera, quy đổi đúng vùng ảnh có letterbox; cảnh báo cấu hình chưa lưu.
- Bỏ route 410 chặn deep link hợp lệ. Refresh các trang admin/giáo viên phải mở đúng SPA; API không tồn tại vẫn trả lỗi API, không trả HTML.
- Import roster/xe có preview, lỗi từng dòng, xử lý trùng và chống submit lặp; export an toàn khi mở bằng bảng tính.
- Upload ảnh phải decode thật, giới hạn 5 MB và kích thước giải nén, tên UUID, bỏ metadata không cần thiết và dọn upload chưa gắn bản ghi.
- Tắt đăng ký công khai và cảnh báo thử trên môi trường dữ liệu thật. Không mở lại đăng ký chỉ vì biết mã học sinh; cần luồng xác minh riêng.

### Đợt 6 — Dữ liệu, vận hành theo ca và khả năng phục hồi

- Giữ SQLite trên ổ local, giao dịch ghi ngắn, timeout hữu hạn và migration có phiên bản. Kiểm tra WAL, checkpoint, foreign key và index trên bản sao trước khi áp dụng; WAL vẫn chỉ có một writer tại một thời điểm. [Tài liệu SQLite](https://www.sqlite.org/wal.html).
- Query/health không được tự khởi tạo model hoặc camera. Thu metrics nền; cập nhật thống kê dung lượng tối đa mỗi 60 giây, không quét toàn bộ media mỗi lượt poll.
- Bổ sung health theo camera và toàn cổng: tuổi frame, FPS, latency p50/p95, reconnect, lỗi OCR/DB/media, queue, RAM/VRAM và dung lượng đĩa.
- Chạy bản vận hành với một tiến trình backend, không `reload`; tránh khởi tạo trùng model/camera do nhiều worker.
- Có lệnh bắt đầu/kết thúc ca, kiểm tra trước ca, shutdown có thời hạn và supervisor khởi động lại khi crash. Giới hạn ba lần restart trong 15 phút; vượt ngưỡng phải báo lỗi.
- Lỗi một camera được phục hồi riêng. Nếu CUDA lỗi làm mất khả năng xử lý, hiển thị AI suy giảm và phục hồi tiến trình có kiểm soát; không âm thầm chuyển CPU rồi tiếp tục báo đạt.
- Backup bằng SQLite Backup API, kèm manifest và media liên quan, gồm crop/clip/ảnh hồ sơ. Đánh dấu hoàn tất chỉ sau kiểm tra toàn vẹn. [SQLite Backup API](https://www.sqlite.org/backup.html).
- Backup trong ca mỗi giờ và cuối ca; media sao lưu tăng dần theo UUID. Giữ 24 mốc theo giờ và 14 mốc cuối ca nếu dung lượng cho phép; thiếu dung lượng phải báo, không tự xóa chứng cứ còn hạn.
- Phục hồi thử sang thư mục riêng, kiểm tra DB, tài khoản, cấu hình và mở được media. Backup trên cùng ổ không được mô tả là bảo vệ khỏi hỏng ổ.
- Giữ thời hạn chứng cứ hiện có, mặc định 90 ngày. Bản ghi giữ phục vụ kiểm tra không được cleanup tự động. Cleanup xử lý cả crop, ghi lỗi và chỉ cập nhật DB đúng kết quả thực tế.
- Cảnh báo đĩa khi trống dưới 15%; mức nghiêm trọng dưới 5% hoặc 5 GB. Ưu tiên dừng ghi hình liên tục tùy chọn, giữ snapshot/crop; không tự xóa bằng chứng còn hạn.
- Log xoay vòng, không chứa credential hoặc thông tin học sinh không cần thiết. Chuẩn bị hướng dẫn mất mạng, đầy đĩa, model lỗi, đổi camera, bắt đầu/kết thúc ca và khôi phục.

## 4. Kiểm thử và tiêu chí nghiệm thu

Các số dưới đây là **mục tiêu cần đo**, không phải kết quả đã đạt.

| Hạng mục | Tiêu chí |
|---|---|
| Chạy theo ca | Hai nguồn chạy 12 giờ, 2–3 thiết bị truy cập; không crash/hang hoặc cần khởi động thủ công trong điều kiện mạng bình thường |
| Hiển thị | ≥15 frame mới/giây/camera khi nguồn cung cấp đủ FPS |
| AI | ≥5 frame mới/giây/camera với hồ sơ nhận diện đã chọn |
| Độ trễ nội bộ | Từ nhận frame đến chuẩn bị hiển thị p95 ≤500 ms |
| Camera → màn hình | Đo bằng cảnh có đồng hồ, mục tiêu p95 ≤1,5 giây; báo riêng với latency nội bộ |
| Mũ | Xác nhận p95 ≤2 giây từ quan sát hợp lệ đầu tiên |
| Qua cổng | Xác nhận p95 ≤1 giây sau khi đủ điều kiện crossing |
| Bảng và âm thanh | Bảng p95 ≤500 ms sau xác nhận; tiếng nói bắt đầu ≤1 giây khi queue rỗng và bằng chứng bắt buộc đã sẵn sàng |
| Chất lượng | Precision lỗi đọc loa ≥95% theo từng loại; recall ≥70% trên trường hợp rõ |
| OCR | Đúng toàn biển ≥50% trên ít nhất 30 biển rõ |
| Tập đánh giá | ≥50 lượt vi phạm rõ và ≥50 lượt không vi phạm rõ, tách theo video/phiên |
| Gương | Riêng ≥30 lượt thiếu rõ và ≥30 lượt có gương rõ trước khi xét bật loa |
| Ghép trước/sau | Tối thiểu 50 cặp lượt có nhãn; không gán nhầm trong tập nghiệm thu. Báo tỷ lệ ghép được và tỷ lệ từ chối, không coi “không ghép gì” là đạt |
| Trường hợp mơ hồ | Có ít nhất 20 tình huống hai xe sát nhau, ngược chiều hoặc che khuất để kiểm tra từ chối ghép sai |
| Khung hình trống | Camera trống 10 phút tạo 0 vi phạm |
| Phục hồi camera | Khi nguồn phát trở lại bình thường, mục tiêu nhận hình mới trong 15 giây; camera còn lại tiếp tục hoạt động |
| Tài nguyên | Không OOM hoặc tăng bộ nhớ kéo dài; báo RAM/VRAM đầu–giữa–cuối ca, queue và frame bỏ |
| API/UI | Với dữ liệu thử 100.000 sự kiện và ba thiết bị, API list/detail thông thường p95 ≤500 ms; trang sử dụng được trong hai giây trên LAN |
| Backup | Khôi phục bản gần nhất, kiểm tra DB và mở media thành công; mục tiêu mất dữ liệu tối đa một giờ và phục hồi ≤30 phút trên bộ dữ liệu nghiệm thu |

**Các nhóm test bắt buộc:**

1. **Capture/OCR:** chặn AI hoặc OCR nhưng hình vẫn tiến; queue không tăng vô hạn; frame skip/trống vẫn cập nhật; kết quả phiên cũ bị loại; hai camera có cùng track ID không trộn dữ liệu.
2. **Nhận diện:** một frame sai, frame lặp, mẫu quá hạn, mất track; mũ treo, đầu khuất, dắt bộ, đứng yên, hai chiều qua cổng; crossing chưa đủ ba frame phía sau không được xác nhận.
3. **Ghép hai góc:** xe đơn, hai xe cạnh nhau, xe nối đuôi, đổi thứ tự, một phía mất hình, timestamp lệch, OCR mâu thuẫn và một phía không đọc biển.
4. **Sự kiện:** nhiều xe cùng giây, nhiều lỗi cùng lượt, DB bận, ổ đĩa đầy, media ghi lỗi, crash giữa ghi bằng chứng và phát sự kiện; không có URL bằng chứng giả.
5. **Realtime/loa:** hai viewer cùng nhận, client chậm, reconnect, reload, hết phiên, mất lease phát loa, tắt âm thanh và event cập nhật muộn.
6. **Phân quyền:** khách, từng vai trò, giáo viên đúng/khác/thiếu lớp, tài khoản bị khóa/đổi quyền, token hết hạn, truy cập trực tiếp media và URL đoán được.
7. **Admin:** lọc/phân trang, detail cũ ngoài 200 dòng gần nhất, chỉnh trạng thái đồng thời, import trùng, upload giả ảnh, ảnh/clip đúng quyền, refresh deep link production.
8. **Vận hành:** backup trong lúc ghi dữ liệu, restore cả media, cleanup lỗi, start/stop lặp, mất một camera và đầy đĩa giả lập.

CI phải có backend test, lint/build frontend, E2E với nguồn/API thử và kiểm tra production qua app factory thật. **Bỏ `|| true` và `continue-on-error` khỏi các kiểm thử bắt buộc.** Test thành công media phải nhận 200 với nội dung đúng; test clip kiểm tra phát/tua; không dùng 404 làm bằng chứng luồng hoạt động.

## 5. Thứ tự bàn giao và nguyên tắc báo cáo

Thực hiện theo thứ tự: **hiện trạng → định danh camera/cổng và nền tảng R → sự kiện/media/phân quyền → nhận diện và ghép hai góc → luồng admin/loa/vận hành → nghiệm thu**.

Chuẩn hóa nhãn và chuẩn bị dữ liệu có thể tiến hành trong lúc các phần độc lập được sửa. Thiếu mẫu có nhãn không được chặn việc sửa API, web, backup hoặc test cách ly.

Khi bắt đầu thực thi, Cursor:

- Lưu kế hoạch này vào `docs/CURSOR_SYSTEM_STABILITY_PLAN_2026_09_30.md`.
- Cập nhật `docs/CURSOR_EXECUTION_LOG.md`, giữ lịch sử và đính chính những mục “DAT” chưa có bằng chứng.
- Tổng hợp kết quả cuối vào `docs/SYSTEM_ACCEPTANCE_REPORT_2026_09_30.md`.

Mỗi đợt phải ghi: vấn đề tái hiện, thay đổi, lệnh kiểm thử, kết quả, số đo trước/sau, phần chưa đạt và cách quay lại cấu hình trước. Phân biệt rõ **đã viết mã**, **test hành vi đạt**, **đã đo trên video** và **đã nghiệm thu trên hai camera thật**.

Không ghi đè thay đổi chưa commit; không sửa hai phiên đồng thời cùng phần mã; không nâng dependency trên môi trường đang chạy; không thay nguồn camera vận hành để benchmark; không xóa DB/media thật, đổi mật khẩu thiết bị, push hoặc triển khai VPS.

Tiếp tục các phần độc lập mà không hỏi lại sau từng đợt. Khi cần góc nhìn, nhãn chuẩn, thông tin model camera hoặc điều kiện thiết bị chưa có, ghi chính xác phần bị thiếu và giữ tính năng tương ứng ở trạng thái chưa nghiệm thu. Không hạ tiêu chí để hoàn thành báo cáo.
