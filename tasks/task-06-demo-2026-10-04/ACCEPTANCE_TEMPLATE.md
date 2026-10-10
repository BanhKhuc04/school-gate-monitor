# Mẫu nghiệm thu — sao chép vào FINAL_ACCEPTANCE.md của bản bàn giao

**Trạng thái ban đầu: pending.** Đây là mẫu ghi bằng chứng, không phải báo
cáo đã đạt. Cursor điền bằng kết quả thật của bản freeze và người kiểm loa.

## Bản được kiểm

| Trường | Giá trị thật |
|---|---|
| Bắt đầu/kết thúc, Asia/Bangkok | Chưa kiểm |
| Commit/tree/dirty state; build hash | Chưa kiểm |
| Weights/engine/config/audio hash | Chưa kiểm |
| Camera/gate/epoch/profile; ROI | Chưa kiểm, không ghi RTSP credentials |
| DB/media/backup/cache QA hoặc demo | Chưa kiểm, tách dữ liệu vận hành |
| Người duyệt GT/operator/người nghe loa | Chưa xác nhận |
| D/C trước/sau, output size | Chưa đo |

## Chất lượng và thời điểm

- Bộ nhãn người duyệt: số lượt, nguồn/session, cách chia và ca khó; hash.
- Exact plate đúng/sai/không chốt trên toàn bộ lượt; coverage và số review.
- TP/FP/FN/unknown riêng từng luật; không bỏ negative hoặc ca che khuất.
- Học sinh gán đúng/sai/không gán; số lượt có đủ bằng chứng liên kết.
- Preview tính frame nguồn mới, AI tính inference hoàn tất từng camera.
- Capture age/queue wait/detect/OCR/encode và CPU/RAM/Torch/ORT/VRAM.
- Plate latency từ vào vùng đọc; beep/speech từ issue confirmed; p50/p95/n.
  Đo end-to-end với cùng đồng hồ hoặc đã hiệu chỉnh chênh lệch server/browser;
  không trừ timestamp hai máy chưa đồng bộ rồi báo độ trễ.
- Ghi tiếng thực nghe và callbacks, không dùng `speech_requested` làm audio pass.

## Matrix tối thiểu

| Ca | Expected được người duyệt | Observed/event/audio/media | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| Xe hợp lệ, biển rõ | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Không đội mũ, có bằng chứng | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Riding hoặc dắt xe tại vạch | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Số người; nhiều lỗi cùng lượt | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Biển hai dòng, nghiêng, mờ/che | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Biển gần whitelist/xe sát nhau | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Mũ/chân bị che, người đi bộ | Điền trước khi test | Chưa kiểm | Chưa có | pending |
| Hai camera và 1/2/3 viewer | Frame mới, một speaker owner | Chưa kiểm | Chưa có | pending |
| Đổi nguồn/reconnect/epoch | Không frame/plate/alert cũ | Chưa kiểm | Chưa có | pending |
| Reload/lease hết hạn/replay | Không đọc lặp, quyền đúng | Chưa kiểm | Chưa có | pending |
| Late issue/plate và IO fail | Cùng event, không nhắc sai | Chưa kiểm | Chưa có | pending |
| WAN-off, cold browser/login | UI/API/RTSP/audio/media local | Chưa kiểm | Chưa có | pending |
| Video AI thật đủ 15 clip EOF | Đúng runtime, bounded output | Chưa kiểm | Chưa có | pending |
| Hai camera thật 30 phút | Không crash/drift/disk tăng bất thường | Chưa kiểm | Chưa có | pending |
| PPTX/PDF/backup video offline | Mở/rà đủ, hai lượt 180+420 giây | Chưa kiểm | Chưa có | pending |
| Launcher/rollback | Đúng freeze, không mất dữ liệu mới | Chưa kiểm | Chưa có | pending |

## Phần mềm và VPS

Ghi lệnh, flags/env QA đã che secret, thời gian, exit code và path log cho
focused/full regression, Node/lint/build và browser/API thật. Nêu rõ stub/
mock; không dùng test mock để kết luận inference hoặc âm thanh thực.

VPS: access/deploy/health/version/TLS/auth/rollback/sync có trạng thái riêng;
ghi URL thật đã mở từ ngoài máy và thời điểm. Không đủ quyền: pending_access.
Landing deployed không tự đồng nghĩa portal/sync production đã đạt.
Snapshot phải có thời điểm dữ liệu; WAN-off không coi remote URL truy cập được.

## Kết luận theo phạm vi

| Gate | Trạng thái | Bằng chứng/blocker/owner/bước tiếp |
|---|---|---|
| Demo local + hai camera + audio + offline | pending | Chưa kiểm |
| Trang giới thiệu/VPS nhẹ | pending | Chưa kiểm |
| Portal/sync | pending | Chưa kiểm |
| Package/PPTX/PDF/notes/runbook | pending | Chưa tạo bản release cuối |
| ALPR/luật KPI holdout độc lập ≥300 lượt | pending | Không thay bằng ca demo nhỏ |
| Camera endurance 12 giờ/full media restore | pending | Không thay bằng ca 30 phút |
| Dataset/training/YOLO11 promotion | pending | Notebook không phải training đã chạy |

Chọn `demo_ready` chỉ khi gate demo thực đạt; `production_complete` chỉ khi
toàn bộ gate production đạt. Công bố lỗi quan sát được, số mẫu và coverage;
không hứa hoàn toàn không sai. Bàn giao pending cụ thể để người dùng quyết
định cách trình bày và vận hành dựa trên bằng chứng.
