# Kiểm tra tạm camera Imou — 2026-10-01

- Địa chỉ người dùng cập nhật: `192.168.1.9`, channel 1, main stream (subtype 0). Không lưu mật khẩu trong tài liệu hoặc repository.
- `.13:554` timeout; `.9:554` kết nối được. Pipeline mở camera, trang `/guard` hiển thị hình thực.
- Backend: `http://localhost:8001`; frontend: `http://localhost:5174/guard`.
- Đây là phiên kiểm tra riêng: SQLite được sao bằng Backup API, snapshot/crop/clip nằm trong thư mục tạm; cleanup, backup định kỳ và ghi liên tục tắt. Cấu hình camera và DB vận hành không bị thay đổi.
- Thư mục phiên: `C:\Users\khucv\AppData\Local\Temp\school_gate_camera_check_8yhc0fa9`.
- Tiến trình backend và Vite được giữ chạy để người dùng kiểm tra. Backend không dùng reload/multiple workers.

## Lỗi trạng thái đã sửa

`app/api/camera.py` import `get_existing_pipeline`, nhưng pipeline chưa khai báo hàm này. API luôn coi pipeline chưa chạy dù camera hoạt động. Thêm accessor chỉ đọc registry dưới lock, không khởi tạo camera/model. Test dùng registry thật, chứng minh trạng thái online và không tạo instance khi registry trống.

- Test trước sửa: thất bại đúng tại `health.running`.
- Kiểm tra liên quan: 26 passed.
- Toàn bộ backend: `venv\Scripts\python.exe -B -m pytest app/tests -p no:cacheprovider --tb=short -q` — 501 passed, 1 warning, 162.78 giây.
- Kiểm chứng runtime sau restart: login HTTP 200, camera API HTTP 200, running/camera_open true, tuổi frame 0.08 giây tại thời điểm đo.
- Đã nhìn thấy hình camera thật trên trình duyệt. Những số này xác nhận kết nối; không phải nghiệm thu độ trễ toàn tuyến hay chất lượng nhận diện.

## Điểm cần kiểm tra riêng

Log khởi tạo `models/helmet_best.pt` cho thấy mapping `{0: 'plate'}`. Cần đối chiếu đúng file trọng số mũ trước khi nghiệm thu nhận diện; phiên này không tự thay model.

## Dừng phiên kiểm tra

Backend PID launcher nằm trong `backend.pid` của thư mục phiên, tiến trình Python con nghe cổng 8001. Vite nghe cổng 5174. Khi dừng, chỉ dừng đúng các tiến trình của phiên này; không dừng ứng dụng khác. Nguồn `.9` chỉ áp dụng phiên tạm, không cấu hình lại DB hoặc `.env` vận hành.
