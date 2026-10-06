# Rà soát kiến trúc và cải tiến chọn camera — 2026-09-30

Người dùng ưu tiên sửa và cải tiến chọn nguồn camera trong ứng dụng. Đánh giá dựa trên working tree hiện tại (nhiều thay đổi chưa commit), giữ nguyên các sửa đổi ngoài phạm vi.

## Hiện trạng

- React/Vite → FastAPI → SQLite; mỗi cổng có VideoPipeline riêng, MJPEG và WebSocket.
- Pipeline đã có tracking, OCR voting, EventManager, ROI, clip, correlation, recording và maintenance. README mô tả một camera đã lỗi thời.
- Camera API hiện ghi DB rồi thay toàn bộ pipeline; webcam index lưu dạng chuỗi; MJPEG giữ tham chiếu pipeline cũ; UI báo thành công trước khi có hình.

## Quyết định đợt sửa này

1. Chuẩn hóa index/RTSP/HTTP/video file và giới hạn thời gian mở/đọc nguồn mạng bằng OpenCV FFmpeg.
2. Yêu cầu chuyển nguồn trả 202, pipeline xử lý ở ranh giới frame; giữ model và pipeline instance. Chỉ lưu DB và thay capture sau khi đọc được frame đầu tiên. Nguồn lỗi giữ capture cũ.
3. Tách trạng thái yêu cầu chuyển nguồn ra module nhỏ; tuần tự hóa thao tác cùng cổng; UI đọc trạng thái thực tế. Không giữ khóa toàn cục trong I/O camera.
4. Xóa cache tracking/OCR/clip khi đổi nguồn; giữ ROI theo cổng và nhắc kiểm tra lại khi thay góc nhìn.
5. UI có nhãn rõ, trạng thái đang kiểm tra/thành công/lỗi, preview nguồn hiện tại, khóa form khi đang chuyển, hủy response cũ khi đổi cổng. API che thông tin đăng nhập camera.

OpenCV timeout chỉ áp dụng backend FFmpeg/GStreamer, không bảo đảm deadline của driver USB: https://docs.opencv.org/4.10.0/d4/d15/group__videoio__flags__base.html

## Thứ tự

Theo tasks/todo.md: kiểm thử lỗi → capture và điều khiển nguồn → API → UI → kiểm thử tích hợp và báo cáo toàn dự án.

## Hướng phát triển tiếp theo

- Tách dần pipeline lớn thành capture/inference/event persistence; không viết lại toàn bộ.
- Chuẩn hóa cấu hình env/DB, danh sách cổng riêng, secret và API base URL; quản lý gate CRUD sau khi vòng đời camera ổn định.
- Cảnh báo theo cổng và nhiều người xem; giám sát mất hình, latency, reconnect.
- Dữ liệu đánh giá model tại cổng thật; đo precision/recall trước khi thay threshold hoặc fine-tune.
- CI backend + browser test, đồng bộ tài liệu hiện trạng và gom script QA vào scripts/.

## Giới hạn kiểm chứng

Kiểm thử tự động dùng capture giả và video tổng hợp, không đổi camera/DB vận hành. Xác nhận camera IP/USB thật cần phần cứng hoạt động. Không triển khai hoặc commit trong đợt này.

## Phần tiếp nối — front/rear và phản hồi biển số, 01/10/2026

Giữ nguyên lịch sử C1–C5 đã hoàn thành. Kế hoạch chi tiết cho yêu cầu tiếp nối cùng hệ thống nằm tại [CURSOR_FRONT_REAR_RECOGNITION_PLAN_2026_10_01.md](../docs/CURSOR_FRONT_REAR_RECOGNITION_PLAN_2026_10_01.md); công việc mới được thêm vào `tasks/todo.md`.

Bổ sung 03/10/2026 (sửa crop biển số + reader mới) nằm trong cùng `tasks/todo.md` mục "Bổ sung 03/10/2026". Hướng dẫn triển khai chi tiết: `docs/CURSOR_CROP_OCR_RECOVERY_PLAN_2026_10_03.md` (sẽ viết khi bắt đầu Giai đoạn A).

Quyết định chính: cam trước-phải xử lý mũ/hành vi và gương quan sát được; cam sau đọc biển độc lập điều kiện thấy người. Tách capture/display khỏi AI, dùng best crop nguồn với một OCR attempt/lượt, tích hợp reader ký tự ở review-only và lưu phản hồi đúng/sai để tạo dataset có phiên bản. Chẩn đoán và kiểm chứng loa là bước đầu; không giảm chuẩn bằng chứng để phát tiếng.

Rủi ro cần kiểm chứng: ảnh nguồn nhòe/thiếu chi tiết; reader mới có trường hợp thiếu ký tự vẫn confidence cao; runtime hiện khóa theo gate; gương trái có thể khuất từ góc phải; liên kết hai góc chưa hiệu chỉnh. Tự ghép và cảnh báo gương chưa đủ bằng chứng vẫn tắt. Các mốc FPS/chất lượng/12 giờ trong kế hoạch là mục tiêu, chưa đạt trong lượt lập kế hoạch này.
