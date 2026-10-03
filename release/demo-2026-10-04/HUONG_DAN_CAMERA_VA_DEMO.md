# Hướng dẫn đặt camera và chạy demo (cập nhật 04/10/2026, 03:30)

Tài liệu này suy ra từ cách code thật sự ra quyết định, không phải lý thuyết chung.
Mỗi quy tắc đặt camera đều có lý do nằm trong code hoặc trong số đo đêm 04/10.

## 1. Vai trò hai camera

| | Camera 1 — Cổng Chính (`main`) | Camera 2 — Cổng Phụ (`secondary`) |
|---|---|---|
| Nguồn | `CAMERA_SOURCE` trong `.env` | `CAMERA_SOURCE_SECONDARY` trong `.env` |
| Vai trò code | `front`, profile `full` | `rear`, profile `ocr_only` |
| Model chạy | người + xe (YOLO11n), mũ, tư thế (YOLO11n-pose), biển số | chỉ biển số + đọc ký tự |
| Bắt lỗi | Không đội mũ, Đi xe qua cổng (không dắt), Chở quá số người | Đọc biển, tra xe đã đăng ký |
| Thông báo | Cảnh báo đỏ + loa khi xe **cắt qua vạch cổng** và lỗi đã đủ bằng chứng | Thông báo xanh/cam khi biển được **2 lần đọc khớp nhau**, không đọc loa |

Xe máy Việt Nam chỉ có biển phía sau, nên camera 1 không cần thấy biển; nếu không
đọc được biển thì camera 1 chỉ ghi "cần xem lại", không báo lỗi và không đọc loa.

## 2. Đặt camera 1 (mũ + dắt xe)

Bộ chấm tư thế (`SideViewRiding`) đo vị trí hông so với yên xe và thân người so
với xe, được thiết kế cho **góc nhìn ngang/chéo**. Nhìn thẳng từ phía trước, người
dắt xe đứng che lên xe nên dễ bị chấm nhầm "đang chạy" (đã thấy ở video cổng trường).

- Đặt lệch sang **một bên lối đi**, trục camera hợp với hướng xe chạy khoảng **45–70°**.
- Cao **2,2–2,8 m**, chúc xuống **15–30°**: thấy rõ đầu (mũ) và **cả hai chân, bánh xe**.
- Toàn bộ người + xe phải nằm trong khung khi qua vạch; mép khung không cắt mất chân.
- Ngược sáng: bật WDR/BLC. Ban đêm: bật hồng ngoại hoặc đèn sân.

## 3. Đặt camera 2 (biển số)

Bộ đọc ký tự cần biển đủ lớn; crop dưới ~60 px chiều rộng thường ra "không đọc được"
(đã thấy crop 46×42 px bị mờ). Camera Imou gửi ảnh 2688×1664, crop biển lấy từ ảnh gốc.

- Đặt **sau lưng xe** (nhìn đuôi xe khi xe đi vào), cao **1,2–1,8 m** (biển cao ~0,8–1 m).
- Lệch ngang và chúc xuống mỗi chiều **≤ 30°**; biển càng thẳng càng tốt — biển nghiêng
  10° đã làm tỉ lệ đọc giảm mạnh (đo trên 35 biển thật).
- Biển cần rộng **≥ 100–120 px** trên ảnh gốc: ống kính 2,8 mm → xe đi trong khoảng ~2 m;
  ống 4–6 mm → tới ~4,5 m.
- Tốc độ màn trập ≥ 1/250 s để biển không nhòe khi xe chạy.

## 4. Vạch cổng — bắt buộc kiểm tra trước demo

Mọi cảnh báo vi phạm chỉ chốt khi **điểm giữa đáy khung xe cắt qua vạch**.
Chưa vẽ vạch thì app dùng vạch ngang mặc định ở 65% chiều cao khung hình.

- Đăng nhập `admin` → **Cài đặt → ROI / Vạch cổng** (`/settings/roi`) → tab **Vạch mốc** →
  chọn cổng → click 2 điểm trên khung hình → lưu. Vạch hiện màu cam trên ảnh camera.
- Vẽ vạch **vuông góc với hướng xe chạy**, ở chỗ xe chắc chắn đi qua và còn thấy trọn người + xe.
  Camera đặt chéo/ngang: vạch thường gần thẳng đứng. Camera nhìn xe tiến lại: vạch ngang.
- Ở sân demo (video đêm 01/10), xe chủ yếu chạy ở dải 70–100% chiều cao khung hình:
  vạch ngang ở **82%** cho 6 lần cắt vạch / 3 cảnh báo đúng, vạch ở 50% thì không có lần nào.

## 5. Các bước demo

1. `.\release\demo-2026-10-04\START_DEMO.ps1` (mở `http://127.0.0.1:8000/guard`).
2. Đăng nhập (DB demo `data/demo_app.db` đã có tài khoản seed):
   `admin / admin123`, `security / security123`, `management / management123`.
3. Đăng ký xe thật của bạn: **Quản lý xe** (`/admin/vehicles`) → thêm biển (xe điện ghi `29MĐ1-123.45` đều được).
4. Vẽ vạch cổng cho cả hai camera (mục 4).
5. Trang Giám sát → bấm **Loa: TẮT** để chuyển sang **BẬT** (cần một cú click của người dùng).
   Nhìn badge giọng đọc cạnh nút loa: **VI-local** = nói được khi ngắt mạng; **VI-remote** =
   cần Internet. Muốn demo ngắt WAN: Windows → Settings → Time & language → Speech →
   thêm giọng **Tiếng Việt (Microsoft An)**, rồi mở lại Edge/Chrome.
6. Diễn:
   - Đi xe qua vạch, không mũ → cảnh báo đỏ "Không đội mũ + Xe chạy qua cổng", loa đọc
     "Không đội mũ, vui lòng dắt xe."
   - Dắt xe qua vạch → **không** cảnh báo.
   - Biển đã đăng ký → thông báo xanh "Đã nhận diện xe …" kèm tên/lớp; biển lạ → thông báo cam.

## 6. Giới hạn nên nói thật

- Tư thế ở góc thẳng trước không đáng tin; hệ thống trả "không rõ" thay vì đoán, và
  "không rõ" không bao giờ thành lỗi.
- Biển nghiêng/nhỏ/mờ → "cần xem lại", không tự kết luận.
- Model biển số (phát hiện) vẫn là YOLOv8 đã train riêng, chính xác hơn bản YOLO11 2 epoch;
  chỉ thay khi bản train Kaggle vượt mAP50-95 0,762 trên cùng tập val.
