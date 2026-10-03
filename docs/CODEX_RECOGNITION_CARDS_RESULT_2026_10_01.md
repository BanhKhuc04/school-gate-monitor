# Thẻ nhận diện bằng ảnh và chẩn đoán OCR — 2026-10-01

## Phạm vi và model thực tế

Thực hiện yêu cầu thay log chữ bằng thẻ ảnh người, đầu/mũ và biển, xác nhận qua nhiều frame; kiểm tra model thật và điểm nghẽn biển. Không thay dependency, trọng số hoặc ngưỡng xác nhận vi phạm. DB/media của phiên kiểm tra nằm trong thư mục tạm. Giữ OBS Virtual Camera index 1 do người dùng chọn; lượt này không phải nghiệm thu camera Imou.

Đối chiếu trọng số thật và API của tiến trình đang chạy:

| Nhánh | Trọng số/engine | Kiến trúc/device |
|---|---|---|
| Người, xe | yolov8n.pt, COCO | YOLOv8n, cuda:0 |
| Mũ | helmet_best_20260930_090903.pt (backup được cấu hình trong launcher thử) | YOLOv8n, cuda:0; With Helmet / Without Helmet |
| Box biển | plate_best.pt | YOLOv8n custom, cuda:0; một lớp biển |
| OCR | EasyOCR 1.7.2 | Reader của pipeline |
| Theo dõi | ByteTrack | bytetrack.yaml, state riêng pipeline |
| Tư thế (theo mã đang dùng) | yolov8n-pose.pt | Nạp khi xử lý người, cache theo thread; không được khởi tạo từ endpoint thẻ |

YOLOv8n được xác minh từ YAML backbone C2f, depth_multiple=0.33, width_multiple=0.25 và thông tin training khi có. Model mũ mặc định helmet_best.pt vẫn sai lớp plate; không ghi đè file, contract tiếp tục đóng riêng nhánh mũ nếu cấu hình model sai.

YOLO11 + BoT-SORT chưa dùng trong phiên chạy. yolo11n.pt có trên máy, nhưng Ultralytics 8.2.103 hiện không load được C3k2. Không nâng venv đang chạy để thử. Chưa có so sánh GPU cùng tập test trường để kết luận model notebook tốt hơn. Model ba lớp Bike/Helmet/No-Helmet không cung cấp OCR biển hay thay tất cả nhiệm vụ hiện có.

## Những gì đã sửa

- Mỗi track có một thẻ cập nhật, không thêm một dòng mỗi frame. Có crop từ ảnh chưa vẽ: người, đầu/mũ và biển; mỗi ảnh ghi frame và thời gian riêng. Khi chưa có box mũ, ảnh đầu chỉ là vùng đầu ước lượng, không phải kết luận có mũ.
- Số mẫu thực lấy từ EvidenceLedger: ít nhất bốn mẫu mới, cách nhau 100 ms, trải dài ít nhất 400 ms trong cửa sổ 1.5 giây. Mẫu trái chiều chuyển cần kiểm tra, không có track không được xác nhận. Đây là ổn định quan sát theo track, không xác nhận danh tính học sinh.
- Ảnh encode trên worker riêng; tối đa hai tác vụ chạy/chờ mỗi camera, một tác vụ mỗi track. Cập nhật ảnh thường tối đa 2 Hz/track; có thêm tối đa 2 lượt/giây khi vừa thấy biển để tránh lịch encode lệch lịch tìm biển. Không chờ encode trong capture/AI.
- Bộ nhớ tối đa 24 thẻ, TTL 15 giây; 192 JPEG, mỗi ảnh không quá 64 KiB, cạnh dài tối đa 360 px. Không ghi DB/media cho thẻ. Ảnh gần nhất có thể khác frame hiện tại, được ghi frame/thời gian rõ. Thẻ chưa có track chỉ giữ frame hiện tại, có ID riêng theo box trong frame; không dồn thành danh sách người giả hoặc tự ghép hai người chưa có ID. Encode người chưa có track giới hạn 2 Hz toàn camera. URL chỉ được tạo sau encode thành công. Lỗi encode có trạng thái lỗi.
- GET /guard/recognition_cards và /guard/recognition_image/{id}?gate=... chỉ đọc pipeline đã tồn tại, không khởi tạo camera/model. Vai trò admin/security/management; ảnh dùng phiên cookie/Bearer, không token trong URL; giáo viên/khách bị chặn. Đổi source epoch xóa thẻ/ảnh, kết quả encode phiên cũ bị bỏ.
- Giao diện có lọc track, tạm dừng cập nhật, ẩn thẻ hiện tại, lỗi/retry và thông tin model/device thực dùng. Thẻ không gọi beep/TTS. Giữ tab Cảnh báo riêng.
- Nếu detector bỏ sót xe nhưng có đúng một ứng viên biển trong nửa dưới vùng người, cho crop/OCR đọc thử; không đưa ứng viên vào plate_dets đã ghép. Dùng khóa OCR âm -person_track_id-1, tách hẳn vote khỏi khóa xác minh dương. Hai namespace dùng chung một slot pending cho người. Kết quả preview được thu cả khi xe xuất hiện ở frame sau để không chặn OCR xác minh.
- Khi full-frame detector không thấy biển, tìm thêm trong đúng một vùng xe/người trên ảnh nguồn, tối đa mỗi 500 ms; xoay vòng ứng viên. Đợi inference toàn ảnh hoàn tất trước khi gọi lại cùng instance; không tạo model/pool GPU mới. Quy đổi bbox bằng offset crop, lọc ROI như cũ, không dùng box cache làm mẫu mới.
- Có thể tắt scan vùng bằng PLATE_REGION_SCAN_ENABLED=false. API thẻ trả số lượt scan và thời gian scan cuối; chưa có benchmark đủ để nghiệm thu ảnh hưởng toàn pipeline.
- PlateVoter vẫn loại chuỗi sai định dạng khỏi text dùng gán xe và không xác nhận từ một lần đọc. Bổ sung raw_text chỉ cho chẩn đoán: chuỗi thiếu/sai định dạng hiển thị vàng “Đọc được một phần — chưa đủ toàn biển”, không dùng matching.

## Bằng chứng trên nguồn hiện tại

Full-frame plate model không phát hiện biển trên một frame OBS đã giữ để đối chiếu. Cùng model/ngưỡng 0.25 tìm thấy biển khi crop vùng xe; các vùng kiểm tra có confidence detector khoảng 0.80–0.87. Đây là confidence box, không phải độ chính xác OCR. Không suy ra precision/recall từ một frame.

Sau nối scan vùng, pipeline gửi và thu OCR, hiển thị ảnh biển thật. Crop mẫu 74×60 px có biển nghiêng, ký tự nhỏ. Kiểm tra EasyOCR trực tiếp trên crop đọc thiếu dòng trên và sai ký tự; native đọc 63035, upscale thử trả chuỗi khác có ký tự sai. Không áp dụng upscale chỉ từ một mẫu, không hạ ngưỡng. UI thật còn có lượt đọc một phần 89AA. Chưa đạt OCR toàn biển; phản ánh rằng chất lượng OCR hiện yếu là có cơ sở.

Ảnh xem trước: docs/recognition-cards-preview.jpg.
Ảnh nguồn/crop đối chiếu cục bộ: docs/recognition-source-check.jpg, docs/recognition-plate-check.jpg.
Các ảnh này là dữ liệu kiểm tra cục bộ, không được dùng như dữ liệu có nhãn nghiệm thu hoặc tự động đưa vào training.

## Kiểm chứng

- Full backend cuối: 530 passed, một warning python_multipart, 248.86 giây; không loại test guard.
- 11 test mới thẻ/preview: frame lặp, nhiều mẫu, mũ mâu thuẫn, track thiếu, window quá hạn, buffer/queue giới hạn, crop raw, reset epoch, OCR preview không matching, ambiguity, role/API đọc không khởi tạo, ROI offset/throttle, OCR partial không được xác nhận, encode lỗi không URL giả.
- Chromium nhóm camera + pre-E3 + recognition: 13 passed. Sau thay đổi nhỏ cuối về trạng thái partial và thời gian crop, nhóm recognition chạy lại 4 passed.
- Node: 17 passed. Build và lint thành công; còn warning cũ của các trang khác và bundle lớn.
- Việc chạy regression phát hiện mất kết quả OCR khi box biến mất do một guard mới quá rộng. Đã bỏ guard đó; preview vẫn tách khỏi matching và bộ test chung đã đạt lại.
- Micro-measure 100 lần observe trên ảnh tổng hợp: median 0.053 ms, p95 0.164 ms; encode chạy bất đồng bộ. Đây chỉ là chi phí submit/cập nhật metadata trong thử tổng hợp, không chứng minh FPS hai camera hay mức giảm ≤5%.

Lệnh:
    .\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
    node --test test/*.test.mjs                         (cwd frontend)
    npx playwright test e2e/test_camera.spec.js e2e/test_pre_e3.spec.js e2e/test_recognition.spec.js --project=chromium
    npm run build
    npm run lint

## Còn chưa nghiệm thu và bước tiếp theo

- Cần video gốc/crop biển đủ rõ từ hai góc Imou, nhãn toàn biển do người xem xác nhận, đo tỷ lệ bỏ sót box, OCR toàn biển và gán sai. Phân tích riêng ảnh mờ, chói, nghiêng, biển hai dòng và xe sát nhau.
- Điều chỉnh crop/góc nhìn/độ phân giải theo phép đo; chỉ rectification, thay OCR hoặc fine-tune sau baseline có nhãn và đánh giá trên video giữ lại. Nhiều lần đọc giống nhau vẫn có thể lặp cùng một lỗi của model.
- Giữ YOLOv8/ByteTrack làm baseline; YOLO11/BoT-SORT cần môi trường riêng, so sánh GPU mục tiêu cùng dữ liệu và tác vụ. Chưa có bằng chứng để tự chuyển.
- Chưa đo hai nguồn 30 phút, 12 giờ, FPS/latency/RAM/VRAM và precision/recall/OCR theo tiêu chí đã chốt. Scan vùng có thêm inference, cần đo ảnh hưởng; không tuyên bố đã mượt hoặc chính xác chuẩn doanh nghiệp.
- Chưa bật tự ghép hai camera, gương hay crossing khi thiếu cấu hình. Không biến thẻ quan sát thành vi phạm hoặc kết luận danh tính.

## Quay lại

Snapshot các file trước lượt tại C:\Users\khucv\AppData\Local\Temp\recognition_cards_before_mbzds6tl. Chỉ đối chiếu/hoàn trả từng hunk nếu không có sửa mới từ người dùng/Cursor. Không reset hàng loạt working tree. Có thể tắt riêng scan vùng bằng biến môi trường nêu trên. Không đổi nguồn OBS của phiên thử hoặc trọng số vận hành.
