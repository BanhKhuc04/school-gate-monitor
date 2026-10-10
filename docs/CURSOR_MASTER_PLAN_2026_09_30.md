# Kế hoạch giao Cursor rà soát và phát triển hệ thống giám sát cổng trường

> Bàn giao ngày 30/09/2026. Người thực hiện các đợt phát triển: **Cursor**.
> Hai tài liệu kế hoạch và nhật ký đã được tạo. Phần “Kế hoạch đã duyệt” bên dưới giữ nguyên nội dung được người dùng chốt; câu nói hai tệp chưa được tạo mô tả thời điểm lập kế hoạch trước đó.
> Nhật ký: [CURSOR_EXECUTION_LOG.md](CURSOR_EXECUTION_LOG.md). Việc có tài liệu bàn giao không có nghĩa các đợt phát triển đã chạy hoặc đạt nghiệm thu.

## Cập nhật mới nhất — nhãn chuẩn và cảnh báo chính xác, nhanh

Người dùng đã duyệt [kế hoạch nhận diện và cảnh báo E1–E4](CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md). Kiểm tra và hoàn thiện phần nền OCR/capture của A–B trước, rồi thực hiện E1 quyết định nhiều frame → E2 event/bảng/loa → E3 nhãn/model → E4 đo và nghiệm thu. C/D của kế hoạch hai camera tiếp tục theo phụ thuộc, không phải lý do trì hoãn sửa luật sai.

Quy tắc mới chốt: gương trái theo người lái; ngồi đi xe **và** crossing mới báo không dắt xe; biển chưa rõ chỉ bảng vàng, không beep/TTS; ít nhất hai crop khác frame mới tin OCR. Bằng chứng riêng từng lỗi: tối đa 5 mẫu hợp lệ/1,5 giây, ít nhất 4 đồng thuận/80%, cách mẫu ≥100 ms và trải dài ≥400 ms, mâu thuẫn rõ chuyển cần kiểm tra. Tiêu chí mới cho lỗi đọc loa là precision ≥95% theo từng loại. Khi mâu thuẫn về các nội dung này, ưu tiên kế hoạch E; các yêu cầu bảo mật và dữ liệu ở kế hoạch tổng vẫn giữ nguyên.

## Nền tảng đã giao — OCR và độ mượt hai camera

Người dùng đã duyệt [kế hoạch hai camera A–D](CURSOR_DUAL_CAMERA_PERFORMANCE_PLAN_2026_09_30.md) cho laptop i7-12700H, RAM 16 GB, RTX 3050 4 GB: A sửa OCR/đo baseline → B tách capture, inference, OCR và hiển thị → C cải thiện biển số/ghép đối tượng → D thử YOLO11/BoT-SORT có đối chứng. Kết hợp với thứ tự cập nhật mới nhất E1–E4 ở trên.

Giữ yêu cầu bảo mật, dữ liệu, hợp đồng camera và tiêu chí ít báo sai của kế hoạch tổng bên dưới. Giữ lịch sử đợt 1–7 đã được ghi trong nhật ký; không triển khai lại các mục đã đúng. Nhãn `DAT` và microbenchmark cũ không thay cho phép đo hai camera hoặc kiểm chứng độ chính xác mới. Cập nhật kết quả A–D trong cùng [nhật ký](CURSOR_EXECUTION_LOG.md).

## Lệnh giao việc cho Cursor

```text
Đọc toàn bộ docs/CURSOR_MASTER_PLAN_2026_09_30.md và docs/CURSOR_EXECUTION_LOG.md.
Đọc docs/CURSOR_DUAL_CAMERA_PERFORMANCE_PLAN_2026_09_30.md và
docs/CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md.
Kiểm tra phần nền A/B hiện có, sửa phần thiếu rồi thực hiện E1 → E2 → E3 → E4.
Tiếp tục C/D theo phụ thuộc, giữ kết quả cũ và chỉ dùng môi trường QA cách ly.
Đây là yêu cầu thực thi: đọc mã, tái hiện lỗi, sửa phần còn thiếu, chạy kiểm thử,
ghi bằng chứng vào nhật ký rồi tự chuyển sang đợt tiếp theo; không chỉ trả lại kế hoạch.
Giữ nguyên mọi thay đổi chưa commit của người dùng và phần camera đã đạt kiểm thử.
Chỉ chạy QA trên DB/media/cấu hình/nguồn camera riêng đã xác minh cách ly.
Khi thiếu thiết bị, bí mật cấu hình hoặc nhãn đáng tin cậy, ghi chính xác phần chưa
xác nhận và tiếp tục phần độc lập. Không hạ tiêu chí nghiệm thu để đánh dấu hoàn tất.
Không tự triển khai VPS, đổi mật khẩu thiết bị, xóa dữ liệu vận hành hoặc push remote.
Sau mỗi đợt cập nhật docs/CURSOR_EXECUTION_LOG.md với lệnh, kết quả, bằng chứng,
lỗi còn lại và bước tiếp theo. Tiếp tục cho đến khi hoàn tất phần có thể làm trong repo.
```

## Kế hoạch đã duyệt

### Mục tiêu và cách bàn giao

Mốc đầu tiên là **demo đáng tin cậy trên máy tại trường**: camera hoạt động ổn định, cảnh báo đến đúng cổng, ít báo sai và bằng chứng có thể xem lại. Cursor thực hiện liên tục theo thứ tự dưới đây, kiểm chứng xong từng đợt rồi tự chuyển sang đợt kế tiếp.

Cursor lưu nguyên kế hoạch này vào `docs/CURSOR_MASTER_PLAN_2026_09_30.md` và ghi kết quả từng đợt vào `docs/CURSOR_EXECUTION_LOG.md`. Trong chế độ lập kế hoạch hiện tại, hai tệp đó **chưa được tạo**. Bản kế hoạch này là nội dung để giao cho Cursor.

Working tree hiện có nhiều thay đổi chưa commit. Trước khi sửa, Cursor phải ghi nhận `git status`, đọc mã và test hiện tại, chạy baseline, rồi chỉ sửa phần còn thiếu hoặc còn lỗi. Các kế hoạch cũ và README là tài liệu lịch sử khi mâu thuẫn với mã. Phần chọn camera vừa hoàn thành đã có 242 test backend và 4 test Chromium đạt; không triển khai lại phần đó nếu kiểm tra hiện trạng vẫn đạt.

### Các đợt Cursor thực hiện

1. **Khóa hiện trạng và tạo môi trường kiểm chứng riêng.** Xác nhận các tính năng thực có, phiên bản dependency, route và migration. Dùng bản sao SQLite tạo bằng cơ chế backup của SQLite, thư mục media tạm và cấu hình test riêng; không dùng DB hoặc camera đang vận hành để chạy QA. Lập bảng “đã có / lỗi xác nhận / cần đo thêm” cho API, CV, frontend, dữ liệu và tác vụ nền. Chạy pytest, build, lint và E2E hiện có; ghi rõ lỗi baseline trước khi thay đổi.

2. **Chặn vi phạm và bằng chứng sai.** Tái hiện hiện tượng log tiếp tục tăng sau khi dừng video test bằng nguồn giả lập, camera trống và các video mẫu. Lần theo source đang chạy, track ID, cooldown và EventManager; sửa nguyên nhân đã tái hiện thay vì tăng ngưỡng đoán mò. Tên ảnh, crop và clip phải là định danh duy nhất cho từng sự kiện, kể cả nhiều xe cùng giây. Chỉ trả đường dẫn media khi tệp ghi thành công; lỗi ghi DB/media phải hiện trong health/log và không phát cảnh báo kèm bằng chứng không tồn tại. Kiểm chứng camera trống 10 phút tạo **0 vi phạm**, một xe không tạo nhiều bản ghi trong cooldown 60 giây, hai xe gần nhau không dùng chung cooldown.

3. **Lập tập đánh giá và sửa nhận diện.** Dùng 14 video hiện có tại `C:\Users\khucv\Downloads\tranning\`, ghi phiên bản và hash của model đang dùng. Cursor trích mẫu ở các góc, thời điểm và điều kiện khác nhau, gán nhãn các trường hợp nhìn rõ; mẫu mơ hồ ghi “không xác định”, không ép thành đúng/sai. Tách video dùng để chỉnh và video giữ lại để đánh giá. Đo riêng phát hiện xe, mũ, box biển, OCR chính xác cả biển và cảnh báo cuối cùng. Sau đó sửa crop/ghép đối tượng/OCR hoặc fine-tune model theo lỗi có bằng chứng. Kết quả OCR yếu hoặc mâu thuẫn phải chuyển `needs_review`, không tự gán cho học sinh. Không coi số lượng log là độ chính xác.

4. **Sửa quy tắc “chạy xe qua cổng”.** Bỏ nhánh tự động kết luận chỉ vì xe máy có mặt trong ROI. Thêm đường cắt cổng cấu hình riêng cho mỗi gate: hai điểm tọa độ chuẩn hóa `[0,1]`, lưu DB và chỉnh trong trang ROI. Chỉ ghi `RIDING_THROUGH_GATE` khi cùng track xe có ít nhất ba frame ổn định ở mỗi phía đường, đi qua trong tối đa năm giây; dùng biên chống rung tương đương 2% đường chéo frame. Một lượt qua đường chỉ tạo một sự kiện. Không có đường cắt hoặc track đủ tin cậy thì không tự động kết luận lỗi này; vẫn xử lý các lỗi độc lập khác. Test xe đứng yên, đi sát đường, đi qua hai hướng, mất track, đổi camera và hai xe đi gần nhau.

5. **Làm cảnh báo đúng cho nhiều cổng và nhiều người xem.** Thay queue một người đọc và việc gửi cho mọi WebSocket bằng bộ phân phối theo gate. Mỗi client nhận sự kiện của gate đã chọn; chế độ xem song song đăng ký tất cả gate. Mỗi sự kiện có ID, `gate_id` và thời điểm; nhiều client đều nhận được cùng sự kiện, client chậm không chặn capture hoặc client khác. Không giữ `threading.Lock` qua `await`. Giữ cơ chế cảnh báo âm thanh nhưng kiểm tra chống đọc lặp theo lượt xe và reset khi đổi gate. Test hai gate, hai client cùng gate, ngắt kết nối, client chậm và reconnect.

6. **Bảo vệ dữ liệu và sửa luồng web.** Bỏ JWT và mật khẩu RTSP cố định khỏi mã; tạo secret riêng trong cấu hình local bị Git bỏ qua, yêu cầu secret từ môi trường khi chạy production và ghi rõ việc đăng nhập lại sau khi đổi khóa. Frontend dùng cùng origin qua Vite proxy khi dev và backend/reverse proxy khi triển khai; chuyển phiên trình duyệt sang cookie `HttpOnly`, `SameSite=Lax`, dùng `Secure` với HTTPS. API tiếp tục nhận Bearer cho script hiện có trong giai đoạn chuyển tiếp. Kiểm tra Origin cho thao tác ghi và WebSocket. Thay static mount `/media` bằng endpoint kiểm tra vai trò và phạm vi lớp của giáo viên; sửa đường dẫn ảnh học sinh. Endpoint tạo cảnh báo thử chỉ bật trong môi trường test/dev. Sửa route SPA trả 410 để mở trực tiếp hoặc refresh `/admin/violations` được. Đăng ký công khai mặc định tắt cho dữ liệu thật cho tới khi có cơ chế xác minh học sinh; bản demo dùng roster giả, kiểm tra ảnh bằng decode thực, tên tệp UUID, giới hạn dung lượng/tần suất và dọn upload bỏ dở. Test khách, admin, bảo vệ, giáo viên khác lớp, token hết hạn và deep link production.

7. **Hoàn thiện luồng sử dụng và vận hành.** Kiểm tra thực tế đăng nhập, camera, ROI, cảnh báo, danh sách/chi tiết vi phạm, crop/clip, xử lý trạng thái, xe, roster, đăng ký thử và dashboard. Sửa lỗi tái hiện được; hiển thị mất tín hiệu thật thay nhãn LIVE cố định. Đồng bộ README với React 19, nhiều camera và API hiện tại. Kiểm tra backup SQLite có thể khôi phục cùng media, cleanup không xóa chứng cứ còn hạn giữ. Gom script QA vào vị trí có hướng dẫn sau khi xác định mục đích từng script; không xóa dữ liệu, model, log hoặc tệp người dùng chỉ vì nằm ở root. Thêm CI cho pytest, frontend build/lint, E2E có API giả và kiểm tra route production. Tách `pipeline.py`/`db.py` thành module nghiệp vụ từng phần sau khi hành vi đã có test bảo vệ.

### Giao diện, dữ liệu và tiêu chí đạt

- Giữ hợp đồng chọn camera hiện tại: POST trả **202**, GET trả `checking`/`applied`/`error`. Cursor chỉ sửa nếu kiểm thử phát hiện lỗi. Nguồn lỗi phải giữ camera cũ; không đưa thông tin đăng nhập camera vào API hoặc log ứng dụng.
- Bổ sung cấu hình đường cắt theo gate vào DB và API ROI, có migration lặp lại an toàn. DB cũ không có đường cắt vẫn mở được; lỗi `RIDING_THROUGH_GATE` tự động chỉ bật sau khi gate được cấu hình đường cắt. Dữ liệu vi phạm cũ không bị viết lại.
- Media và API cho giáo viên phải cùng dùng quy tắc phạm vi lớp ở phía server. Ảnh trong trang và clip phát được bằng phiên cookie, không cần token trong URL.
- Tập kiểm chứng cần tối thiểu **50 lượt vi phạm rõ ràng và 50 lượt không vi phạm rõ ràng**, lấy từ nhiều video; nếu dữ liệu hiện có không đủ thì Cursor ghi thiếu hụt và tiếp tục các đợt không phụ thuộc dữ liệu. Điều kiện đạt demo: precision cảnh báo tổng ≥90%, recall trên trường hợp rõ ràng ≥70%, OCR đúng toàn biển ≥50% trên tối thiểu 30 biển nhìn rõ; báo cáo riêng từng loại lỗi. Với cảnh báo mơ hồ, ưu tiên `needs_review`.
- Luồng hai camera phải chuyển đúng video/alert theo cổng; không nhân đôi sự kiện khi hai người xem cùng mở trang. Sau khi xác nhận vi phạm, 95% cảnh báo đến giao diện trong tối đa năm giây trên máy edge dùng để demo. Báo cáo FPS, độ trễ và RAM khi chạy hai nguồn trước khi đề xuất tối ưu thêm.

Sau mỗi đợt, Cursor chạy test liên quan rồi chạy lại bộ kiểm thử chung, cập nhật bảng kết quả và lỗi còn lại trong execution log. Khi thiếu camera thật, mật khẩu mới hoặc mẫu có nhãn đủ tin cậy, Cursor ghi rõ phần nào chưa thể xác nhận trên thiết bị thực và vẫn tiếp tục các đợt độc lập. Không tự triển khai VPS, đổi mật khẩu thiết bị vật lý, xóa DB/media vận hành hoặc đẩy mã lên remote trong kế hoạch demo này.

### Giả định đã chốt

Ưu tiên **ít báo sai** hơn số lượng cảnh báo. “Chạy xe qua cổng” đòi hỏi chuyển động đi qua đường cắt đã cấu hình, không chỉ xuất hiện trong ảnh. Cursor làm liên tục, không dừng sau từng đợt để hỏi tiếp; chỉ cần người dùng khi việc thực sự đòi hỏi thông tin hoặc thiết bị ngoài repository. Mã và test tại thời điểm Cursor bắt đầu là nguồn xác minh cuối cùng; các báo cáo QA cũ cung cấp ca tái hiện, không được xem là lỗi vẫn còn nếu mã hiện tại đã sửa.

## Phụ lục thực thi cho Cursor

Phụ lục này tổ chức việc thực hiện, không thay đổi phạm vi và ngưỡng của kế hoạch đã duyệt.

### Bắt đầu và tiếp tục phiên làm việc

1. Đọc quy tắc repository nếu có, kế hoạch này và nhật ký. Ghi ngày giờ, branch, HEAD, `git status --short` và danh sách file dự định sửa. HEAD một mình không đại diện cho working tree đang có thay đổi.
2. Đọc mã/test trước khi sửa. Ghi nhận các thay đổi sẵn có; không reset, clean, stash hoặc gom commit toàn bộ working tree. Không ghi đè `tasks/plan.md`, `tasks/todo.md` của đợt camera trước.
3. Xác minh đường dẫn DB, media, backup, cleanup và nguồn camera của tiến trình test đều tách khỏi vận hành trước khi khởi động app hoặc chạy script QA. SQLite có thể dùng WAL: dùng API backup của SQLite thay vì chỉ copy tệp `.db` đang mở.
4. Chạy baseline trên môi trường cách ly, ghi lệnh/cwd/exit code/số test/lỗi/warning vào nhật ký. Kiểm tra fixture/lifespan có tự mở camera hoặc chạy worker trước khi chạy test tích hợp. Không chạy hàng loạt các script root chưa đọc.
5. Thực hiện đợt chưa hoàn tất đầu tiên. Mỗi lỗi có ca tái hiện, nguyên nhân, test hồi quy và kết quả sau sửa. Nếu hành vi đã đúng thì ghi “đã có, đã kiểm chứng” và không triển khai lại.
6. Sau mỗi đợt chạy kiểm thử liên quan và bộ chung; cập nhật trạng thái trước khi chuyển tiếp. Khi trở lại phiên mới, tiếp tục từ nhật ký, không bắt đầu lại từ kế hoạch cũ.
7. Thiếu đầu vào ngoài repo chỉ chặn nhiệm vụ phụ thuộc đầu vào đó. Ghi phần thiếu, bằng chứng đã có và việc độc lập tiếp theo; không đánh dấu tiêu chí thiết bị thật đạt bằng test mock.

### Bản đồ đọc mã ban đầu

| Miền | Điểm vào cần đọc | Điều cần xác minh |
|---|---|---|
| Khởi động/cấu hình | `app/main.py`, `app/config.py`, `requirements.txt` | Lifespan, worker, route production, nguồn secret, dependency thực cài |
| Camera | `app/api/camera.py`, `app/cv/camera_sources.py`, `app/cv/camera_switch.py`, `app/cv/capture.py`, `app/tests/test_camera_*.py` | Hợp đồng 202, giữ nguồn cũ khi lỗi, reset trạng thái khi đổi nguồn, che credentials |
| CV/sự kiện | `app/cv/pipeline.py`, `app/cv/event_manager.py`, `app/cv/plate_voter.py`, `app/cv/ocr.py`, `app/cv/event_correlator.py` | Luồng source/frame/track/cooldown, ghi bằng chứng, gán học sinh, luật qua cổng |
| ROI/dữ liệu | `app/api/roi.py`, `app/cv/roi.py`, `app/db.py`, `app/schemas.py` | Tọa độ theo frame thật, migration, gate, đường cắt tùy chọn |
| Cảnh báo | `app/api/guard.py`, `frontend/src/components/AlertBanner.jsx`, `frontend/src/utils/speak.js` | Phân phối theo gate, nhiều người đọc, backpressure, dedup, reconnect |
| Phiên/media/đăng ký | `app/auth.py`, `app/api/auth.py`, `app/api/admin.py`, `app/api/register.py`, `frontend/src/api/client.js` | Phân quyền server, cookie/Bearer, Origin, ảnh học sinh, upload, roster demo |
| UI/vận hành | `frontend/src/App.jsx`, `frontend/src/pages/`, `app/background.py`, `app/tests/`, `frontend/e2e/`, `frontend/playwright.config.js` | Luồng người dùng, tín hiệu thật, backup/restore, test độc lập, CI |

Các phát hiện cũ để tìm ca tái hiện: [đánh giá kiến trúc và camera](ARCHITECTURE_CAMERA_REVIEW.md), [QA ngày 30/09](QA_REPORT_2026_09_30.md), [snapshot codebase](CODEBASE_SNAPSHOT_REPORT.md), [kế hoạch 8 vấn đề cũ](PLAN_FIX_8_ISSUES.md). Chỉ kế hoạch đã duyệt phía trên quy định thứ tự và tiêu chí cho lần bàn giao này. Không sao chép secret, mật khẩu, token hay dữ liệu định danh học sinh thật vào tài liệu, fixture, artifact CI.

### Danh sách việc có thể nghiệm thu riêng

| ID | Công việc | Bằng chứng đầu ra bắt buộc |
|---|---|---|
| D1.1 | Kiểm kê API/CV/UI/DB/background và môi trường | Bảng đã có/lỗi xác nhận/cần đo thêm; phiên bản runtime/dependency; danh sách route/migration |
| D1.2 | Dựng QA cách ly, ghi baseline | Đường dẫn cấu hình DB/media riêng; SQLite backup hợp lệ; kết quả pytest/build/lint/E2E và lỗi trước sửa |
| D2.1 | Điều tra sự kiện tăng sau dừng nguồn, cooldown | Ca tái hiện + trace đã che nguồn; test dừng/EOF/offline/reset; camera trống 10 phút, cùng xe và hai xe |
| D2.2 | Bảo đảm nhất quán event/DB/media | ID riêng; test sự kiện cùng giây, ghi file/DB lỗi, clip/crop đúng nguồn và sự kiện; health/log thấy lỗi |
| D3.1 | Tạo tập mẫu và tập giữ lại theo video | Manifest video/model/hash, nhãn rõ/không xác định, split không trùng video, số lượng đủ/thiếu |
| D3.2 | Đo và sửa nhận diện theo lỗi | Báo cáo xe/mũ/box biển/OCR/cảnh báo; so sánh trước/sau trên tập giữ lại; `needs_review` cho OCR yếu/mâu thuẫn |
| D4.1 | DB/API/UI đường cắt từng gate | Migration chạy lại an toàn; DB cũ mở được; validate hai điểm [0,1] khác nhau; không sửa vi phạm lịch sử |
| D4.2 | Luật crossing trên track | Test 3 frame mỗi phía, tối đa 5 giây, biên 2% đường chéo; đứng yên/rung/hai hướng/mất track/đổi camera/hai xe |
| D5.1 | Phân phối sự kiện nhiều gate/client | Test mỗi client đúng gate, hai client nhận cùng event ID, split view, disconnect, slow client, reconnect |
| D5.2 | Âm thanh và vòng đời subscription | Test chống đọc lặp theo lượt xe, reset đổi gate, không rò timer/subscription; không khóa threading qua await |
| D6.1 | Secret, origin và phiên cookie | Config local bị ignore, production thiếu secret báo lỗi rõ; login/logout/expiry, cookie flags, Bearer compatibility, Origin HTTP/WS |
| D6.2 | Media, đăng ký và deep link | Ma trận role/lớp cho cả API và media; phát ảnh/clip qua cookie; upload decode/UUID/limit/cleanup; dev-only test alert; SPA refresh |
| D7.1 | Luồng người dùng và vận hành | Checklist thực tế, backup + restore media, retention, README/API hiện hành, phân loại script QA |
| D7.2 | CI, tách module và đo demo | CI pytest/build/lint/mock E2E/production routes; test bảo vệ trước refactor; FPS/RAM/latency hai nguồn và giới hạn chưa đo |

Thứ tự chính: D1 → D2 → D3 → D4 → D5 → D6 → D7. Nếu D3 thiếu dữ liệu/nhãn, lưu tiến độ và tiếp tục D4–D7; khi tập kiểm chứng đủ phải đánh giá lại phiên bản cuối sau D4–D7. Refactor ở D7 không được làm mất khả năng đối chiếu hành vi trước/sau.

### Quy ước đo và báo cáo

- Lưu phiên bản mã, trạng thái thay đổi liên quan, SHA-256 model/video, cấu hình, gate và nguồn giả lập đã che thông tin đăng nhập trong mỗi lần đo. Dùng đồng hồ đơn điệu cho khoảng thời gian; timestamp có múi giờ cho nhật ký.
- Đếm theo **lượt xe/sự kiện**, không coi các frame liên tiếp của một lượt là mẫu độc lập. Chốt quy tắc ghép prediction với nhãn trước khi chạy tập giữ lại; báo cáo TP, FP, FN và số mẫu không xác định riêng. Precision = TP/(TP+FP), recall = TP/(TP+FN); mẫu số bằng 0 là chưa đủ bằng chứng, không tự ghi 100%.
- OCR đúng toàn biển = số biển khớp đầy đủ / số biển nhìn rõ trong tập đánh giá. Công bố quy tắc chuẩn hóa định dạng; không bỏ các lượt OCR rỗng khỏi mẫu số. Không dùng chính kết quả model làm nhãn chuẩn.
- Tập giữ lại tách theo video; không chỉnh threshold bằng kết quả trên tập giữ lại. Nếu video thiếu góc, biển rõ hoặc lượt âm tính, ghi chính xác số thiếu. Mẫu không xác định không được dùng để làm đẹp precision/recall; báo cáo riêng số lượng và nguyên nhân.
- Độ trễ alert đo từ lúc **xác nhận vi phạm** đến lúc giao diện nhận/hiển thị; báo p50/p95, số event, cấu hình edge, số nguồn/viewer, FPS theo gate và RAM. Mốc đạt là p95 ≤5 giây. Test mock xác minh hợp đồng, không thay phép đo thiết bị demo.
- Mỗi artifact kiểm chứng ghi nguồn dữ liệu tổng hợp/thật. Chỉ công bố demo đạt khi mọi tiêu chí bắt buộc đã có bằng chứng, kể cả tối thiểu 50 lượt dương, 50 lượt âm và 30 biển rõ.

### Các lệnh tham khảo phải xác minh trước khi chạy

Các lệnh dưới đây dựa trên cấu trúc đang có; chúng không tự bảo đảm cách ly. D1 phải đọc fixture, config và E2E trước, rồi ghi lệnh thực tế đã dùng vào nhật ký.

```powershell
# Tại root, sau khi xác minh fixture/config không mở tài nguyên vận hành:
.\venv\Scripts\python.exe -m pytest -q --tb=short

# Tại frontend:
npm.cmd run build
npm.cmd run lint
# Chạy sau khi chuẩn bị API/DB/media và web server test riêng:
npm.cmd run test:e2e
```

Test camera riêng hiện dùng API giả: `frontend/e2e/test_camera.spec.js`. Kiểm tra cấu hình cổng/baseURL của chính test và Playwright trước khi chạy. Không mặc định toàn bộ E2E hoặc các script QA root dùng API giả; có script trỏ API local thật.

### Điều kiện kết thúc bàn giao thực thi

Cursor cập nhật nhật ký với từng việc đã có/đã sửa, test thực chạy, kết quả metric, migration/config cần áp dụng, cách rollback thay đổi của riêng đợt đó và danh sách phần còn thiếu bằng chứng. Nếu thiếu camera thật hoặc dữ liệu chuẩn thì ghi “chưa nghiệm thu demo”, dù toàn bộ test tự động đã đạt. Không tự restart hay thay cấu hình tiến trình vận hành chỉ để có kết quả kiểm chứng.
