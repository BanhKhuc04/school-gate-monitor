# Cải thiện nhận diện và độ mượt hai camera trên laptop hiện tại

> Kế hoạch A–D được người dùng duyệt ngày 30/09/2026, ưu tiên thực thi tiếp theo của **Cursor**.
> Kế hoạch tổng: [CURSOR_MASTER_PLAN_2026_09_30.md](CURSOR_MASTER_PLAN_2026_09_30.md).
> Ghi kết quả vào [CURSOR_EXECUTION_LOG.md](CURSOR_EXECUTION_LOG.md); giữ lịch sử các đợt cũ.
> Các mục tiêu hiệu năng bên dưới là tiêu chí cần đo, không phải kết quả đã đạt.

> Cập nhật tiếp theo đã duyệt: [nhãn chuẩn và cảnh báo E1–E4](CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md). Hoàn thiện nền OCR/capture A–B trước khi tích hợp E. Quy tắc mới về gương trái, OCR nhiều crop, xác nhận từng lỗi và im lặng khi biển chưa rõ được chốt ở kế hoạch E; giữ mục tiêu hiệu năng và phạm vi môi trường cách ly của tài liệu này.

## 1. Kết luận và hướng áp dụng

**Có thể áp dụng YOLO11, nhưng cần sửa pipeline hiện tại trước. Đổi model hoặc tracker riêng lẻ chưa giải quyết được lỗi OCR và video giật.**

Notebook public được dẫn có 13 ô, chủ yếu huấn luyện YOLO11n và dự đoán trên ảnh. Bản mình đọc chưa có phần BoT-SORT, xử lý video hoặc OCR biển số như bài giới thiệu. Vì vậy, dùng nó làm tài liệu tham khảo huấn luyện. [Notebook gốc](https://www.kaggle.com/code/uzairahmad1434/yolov11n-bikevhelmetvnohelmet)

Máy mục tiêu đã xác nhận: **i7-12700H, RAM 16 GB, RTX 3050 4 GB**. Môi trường Python hiện nhận CUDA. Ưu tiên là hai camera hiển thị ít trễ, đồng thời giữ tiêu chí ít báo sai đã chốt.

## 2. Những vấn đề đã tìm thấy

| Phát hiện trong mã hiện tại | Ý nghĩa |
|---|---|
| Khởi tạo EasyOCR bằng `allowlist` và `paragraph` | Đã xác nhận không tương thích với EasyOCR 1.7.2 đang cài. Lỗi xảy ra khi khởi tạo OCR; hai tham số này thuộc bước đọc ảnh. |
| Đọc camera, detect, pose và OCR nằm trong cùng vòng xử lý | Khi AI/OCR mất thời gian, việc đọc và cập nhật hình cũng phải chờ. Cần đo mức ảnh hưởng thực tế. |
| Mỗi camera có ba detector, thêm pose theo từng người | Hai camera làm tăng số lượt inference và model trong bộ nhớ. Chưa có benchmark toàn pipeline đủ để kết luận sức tải. |
| Camera mạng bị thu xuống 1280×720; detect tiếp tục thu xuống 640×480 | Có thể mất chi tiết biển nhỏ và làm biến dạng tỷ lệ ảnh trước nhận diện. |
| Bộ lọc biển loại box rộng/cao dưới 1,5 | Đã kiểm chứng box tỷ lệ 1,25 bị loại; có nguy cơ bỏ mất biển hai dòng gần vuông. |
| Mỗi người xem tự encode JPEG | Thêm cửa sổ xem làm tăng công việc encode, kể cả khi khung hình chưa đổi. |

Sửa EasyOCR theo API chính thức, đồng thời thêm test sử dụng chữ ký hàm thật để tránh mock che lỗi. [Tài liệu EasyOCR](https://www.jaided.ai/easyocr/documentation/)

## 3. Thứ tự Cursor thực hiện

### Đợt A — Sửa OCR và đo đúng điểm nghẽn

- Sửa tham số khởi tạo/đọc EasyOCR; khởi tạo reader một lần có kiểm soát. Lỗi OCR phải hiện trong health, không biến thành kết luận biển bị che.
- Đo riêng thời gian capture, detect, tracking, pose, OCR, encode và tuổi khung hình; ghi thiết bị thực dùng của từng model.
- Chạy đối chiếu một camera và hai camera trên cùng bộ video, cùng cấu hình.
- Kiểm tra bộ lọc hình dạng biển và crop bằng mẫu biển một dòng/hai dòng; thay điều kiện loại cứng bằng kiểm chứng hình học và liên kết với xe.
- Giữ ByteTrack và model hiện tại làm baseline.

### Đợt B — Tách hiển thị khỏi AI

- Mỗi camera có luồng đọc riêng, liên tục cập nhật **một khung hình mới nhất**. AI lấy hình mới, không xử lý hàng đợi hình cũ tích tụ.
- Khung hình mang `gate_id`, mã phiên nguồn, số thứ tự và thời điểm. Kết quả của camera/phiên cũ bị bỏ sau khi đổi nguồn.
- Giữ model và trạng thái tracking riêng từng gate trong đợt đầu; điều phối các lượt GPU để tránh nhiều pool cùng tranh tài nguyên. Không dùng chung một YOLO instance giữa các thread.
- OCR chuyển sang worker riêng, hàng đợi giới hạn; tối đa một yêu cầu đang chờ cho mỗi track. Chọn crop rõ, đủ lớn, cập nhật bằng mẫu tốt hơn thay vì đọc lại mọi frame.
- Encode JPEG một lần cho mỗi frame hiển thị của gate và chia sẻ cho các viewer. Không vẽ box cũ kéo dài khi kết quả nhận diện đã hết hạn.
- Giữ hợp đồng đổi camera POST 202 và nguồn lỗi giữ camera cũ.

### Đợt C — Cải thiện biển số và ghép đúng đối tượng

- Giữ ảnh nguồn đủ chi tiết cho crop OCR; ảnh hiển thị và ảnh detect dùng bản thu nhỏ riêng, giữ đúng tỷ lệ.
- Tìm biển trong vùng xe ở độ phân giải thích hợp; quy đổi tọa độ chính xác về ảnh nguồn.
- Ghép người–xe–mũ–biển theo hình học và lịch sử track; tránh ghép biển của xe bên cạnh.
- Đánh giá crop rõ/mờ/nghiêng, sắp xếp ký tự hai dòng và voting qua nhiều mẫu. Kết quả yếu hoặc mâu thuẫn vào `needs_review`.
- Chưa thay EasyOCR bằng engine khác trước khi có kết quả baseline sau sửa lỗi.

### Đợt D — Thử YOLO11 và BoT-SORT có đối chứng

- Thử YOLO11n trong môi trường riêng. Dự án đang dùng Ultralytics 8.2.103 và giới hạn `<8.3`, trong khi YOLO11 được bổ sung từ 8.3.0; cần kiểm tra tương thích trước khi thay dependency. [Bản phát hành chính thức](https://github.com/ultralytics/ultralytics/releases/tag/v8.3.0)
- Fine-tune bằng dữ liệu góc camera trường; tách tập chỉnh và tập đánh giá theo video.
- Giữ các chức năng hiện có: người đi bộ, xe đạp, số người trên xe và qua cổng. Model ba lớp trong bài giới thiệu chưa đủ thay toàn bộ hệ thống.
- So sánh ByteTrack với BoT-SORT, ban đầu tắt ReID. Chỉ chuyển tracker nếu giảm đổi nhầm ID mà vẫn đạt ngân sách độ trễ. BoT-SORT có thêm cơ chế xử lý chuyển động camera và ReID tùy chọn, không mặc nhiên nhanh hơn ByteTrack. [Tài liệu tracking](https://docs.ultralytics.com/modes/track/)
- Chỉ thử FP16 hoặc TensorRT sau khi pipeline ổn định; giữ phương án hiện tại nếu tăng tốc làm giảm chất lượng.

## 4. Kiểm thử và tiêu chí nghiệm thu

- Kiểm thử hai nguồn chạy đồng thời 30 phút; một và hai người xem; mất mạng, reconnect, đổi nguồn, OCR lỗi và OCR chậm.
- Không lẫn track, crop, biển số hay cảnh báo giữa hai gate; OCR chậm không làm đứng luồng hiển thị.
- Mục tiêu ban đầu: **hiển thị ≥15 FPS/camera, xử lý AI ≥5 FPS/camera**, độ trễ nội bộ từ nhận frame đến chuẩn bị hiển thị p95 ≤500 ms. Đây là mục tiêu cần đo, chưa phải kết quả đã đạt.
- Đo thêm độ trễ thực từ camera đến màn hình bằng cảnh có đồng hồ; không dùng FPS hiển thị để suy ra độ mới của hình.
- Giữ tiêu chí demo đã chốt: precision cảnh báo ≥90%, recall ≥70%, OCR đúng toàn biển ≥50% trên ít nhất 30 biển rõ; tối thiểu 50 lượt vi phạm và 50 lượt không vi phạm rõ.
- Báo CPU, RAM, VRAM, FPS từng gate, p95 độ trễ và số khung bị bỏ. Thiếu dữ liệu thì ghi thiếu, không đánh dấu đạt.

## 5. Bàn giao cho Cursor

Khi thực thi, cập nhật kế hoạch chính và nhật ký hiện có với thứ tự **A → B → C → D**; tiếp tục giữ các yêu cầu bảo mật, dữ liệu và vận hành của kế hoạch trước.

Không nâng dependency trực tiếp trên tiến trình đang chạy, thay nguồn camera vận hành để benchmark hoặc ghi đè thay đổi chưa commit. Mọi so sánh dùng môi trường cách ly; chỉ đưa model mới vào cấu hình sử dụng sau khi vượt baseline và đạt tiêu chí.

Tại thời điểm duyệt kế hoạch, các phát hiện được xác nhận bằng kiểm tra chỉ đọc; chưa sửa mã hoặc cấu hình camera trong đợt A–D. Khi thực thi, Cursor phải kiểm tra lại mã hiện có và cập nhật kết quả mới vào nhật ký.

## 6. Chỉ dẫn triển khai và bằng chứng cần bàn giao

### Bắt đầu từ hiện trạng, không làm lại các đợt cũ

1. Đọc tài liệu này, master plan, execution log và test/config hiện có. Ghi `git status`, branch/HEAD và thời điểm bắt đầu. Giữ nguyên lịch sử kết quả và mọi thay đổi chưa commit.
2. Nhật ký cũ có các mục `DAT` nhưng chưa đo hai camera end-to-end. Không dùng nhãn đó, thời gian riêng một model hoặc số lượt `push_frame` của recorder để suy ra FPS hiển thị thật hay độ chính xác.
3. Dùng nguồn giả/video và DB/media cách ly. Trước khi chạy suite, đọc fixture/lifespan, xác minh capture và worker nền không dùng DB/camera vận hành. Không chạy script QA root chưa đọc.
4. Sửa từng phần nhỏ có test hồi quy, chạy test liên quan và bộ chung sau mỗi đợt. Không tự hạ ngưỡng hoặc đổi lỗi thành skipped để ghi `DAT`.

### Ma trận nhiệm vụ

| ID | Việc Cursor thực hiện | Bằng chứng kết thúc |
|---|---|---|
| A1 | Sửa EasyOCR, bảo vệ khởi tạo, phân biệt lỗi OCR với biển không đọc được | Test theo signature EasyOCR thật; khởi tạo đồng thời; lỗi init/read; health phản ánh lỗi; không tự phát lỗi biển bị che do exception |
| A2 | Bổ sung đo từng công đoạn, chạy baseline một/hai nguồn | Báo cáo cùng video/config/model hash; capture/display/AI FPS riêng; p50/p95; device thực; CPU/RAM/VRAM; không tuyên bố benchmark CPU khi chưa ép/kiểm device |
| A3 | Kiểm tra filter hình dạng và crop | Ca biển một/hai dòng gần vuông, nghiêng, box ra ngoài ảnh, text áo/nền; số mẫu bị bỏ trước/sau, không giảm precision bằng cách chấp nhận mọi box |
| B1 | Capture riêng từng gate và latest-frame buffer | Buffer không tăng vô hạn; AI chậm vẫn đọc/publish; frame sequence không xử lý lặp; stop/reconnect/switch không rò thread |
| B2 | Phiên nguồn và điều phối inference | Không áp dụng kết quả gate/phiên cũ; tracker riêng; CUDA schedule không làm gate còn lại chờ vô hạn; đổi nguồn lỗi giữ camera cũ |
| B3 | OCR worker giới hạn và crop chất lượng | Tối đa một pending job/track; khóa job/cache có gate + phiên + track; lỗi/chậm không chặn capture; kết quả đến trễ bị bỏ; shutdown sạch |
| B4 | Cache JPEG theo gate/frame và overlay hết hạn | Hai viewer dùng cùng kết quả encode; số lần encode không nhân theo viewer; frame/box cũ không hiện như dữ liệu mới |
| C1 | Ảnh nguồn, resize giữ tỷ lệ, tìm biển trong vùng xe | Test ánh xạ tọa độ 720p/1080p/ảnh dọc và crop nguồn; ROI dùng kích thước thật; ảnh raw không bị vẽ overlay trước crop |
| C2 | Ghép xe/người/mũ/biển và voting | Hai xe gần nhau/che khuất không dùng chung biển; mẫu yếu/mâu thuẫn chuyển needs_review; đo trên tập giữ lại |
| D1 | Môi trường thử YOLO11 và compatibility | Lock phiên bản thử riêng; model hash; test checkpoint hiện có và candidate; môi trường app đang chạy không bị thay |
| D2 | Dữ liệu, fine-tune và A/B tracker/model | Split theo video; nhãn rõ/không xác định; đo precision/recall/OCR/ID switch/latency; thiếu nhãn thì ghi số thiếu và tiếp tục phần độc lập |
| D3 | Thử tăng tốc có kiểm soát | FP16/TensorRT chỉ sau baseline ổn định; kiểm chất lượng và VRAM; lưu cấu hình có thể quay lại |

### Các ràng buộc tích hợp dễ bị bỏ sót

- Giữ đầu đọc camera thuộc một owner. Thay đổi capture thread phải tích hợp CameraSwitch theo hợp đồng xác minh frame đầu tiên rồi mới áp dụng; không có hai thread đồng thời read/release cùng capture.
- OCR `pending`, `error`, `unreadable` là ba trạng thái khác nhau. Không dùng kết quả OCR chưa đến hoặc lỗi engine để kết luận `PLATE_OBSCURED`. Các loại vi phạm độc lập khác vẫn được xử lý theo bằng chứng riêng.
- Ảnh nguồn/crop giao worker phải có vòng đời độc lập với frame bị sửa/vẽ ở thread khác. Kết quả chỉ gắn vào đúng gate, phiên nguồn và track đã yêu cầu.
- Chỉ đếm frame thật mới khi tính FPS; không dùng việc phát lại JPEG cũ để đạt 15 FPS. AI FPS tính lượt inference hoàn tất trên frame riêng biệt, không tính cache reuse.
- Baseline offline phục vụ so sánh chất lượng phải xử lý video nhất quán; kiểm thử live phải phát video theo thời gian nguồn để đánh giá backlog. Không dùng tốc độ đọc hết file không pacing làm FPS camera.
- Health giữ trường hiện có để tương thích, bổ sung thống kê thực và lỗi theo công đoạn. Trường đang đặt tên trung bình nhưng chỉ chứa lần đo cuối phải được sửa/ngữ nghĩa làm rõ.
- Mỗi lần đo giữ model hash, video hash, cấu hình, warm-up, thời lượng và số viewer. Không lấy clip render thành công làm bằng chứng đạt precision/recall.
- Khi A–D đạt phần tự động nhưng chưa đo thiết bị/nhãn đủ, báo phần hoàn tất và phần còn chờ riêng. Không tự đưa mô hình mới vào cấu hình vận hành hay restart backend để nghiệm thu.

### Lệnh giao việc

```text
Tiếp tục dự án theo docs/CURSOR_DUAL_CAMERA_PERFORMANCE_PLAN_2026_09_30.md.
Đọc thêm master plan và execution log để giữ yêu cầu cũ, nhưng ưu tiên A → B → C → D.
Thực thi sửa mã và kiểm thử, không chỉ viết lại kế hoạch. Bắt đầu A1 và A2 sau khi
kiểm tra working tree và cấu hình QA cách ly. Không triển khai lại phần đã đúng.
Sau mỗi đợt cập nhật docs/CURSOR_EXECUTION_LOG.md với lệnh, kết quả, bằng chứng,
metric thực và phần chưa xác nhận. Tự chuyển sang đợt tiếp theo, thiếu thiết bị/nhãn
chỉ chặn phần phụ thuộc. Giữ nguyên môi trường và camera/DB/media đang vận hành.
Không push remote, không triển khai VPS, không đổi mật khẩu thiết bị, không hạ
tiêu chí để đánh dấu DAT. Báo trung thực nếu 30 phút soak test hoặc số mẫu chưa đủ.
```
