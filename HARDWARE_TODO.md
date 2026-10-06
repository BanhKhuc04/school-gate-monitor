# Hardware TODO — chưa làm vì chưa có phần cứng thật

## Còi/loa vật lý qua GPIO
Hiện tại cảnh báo âm thanh chỉ chạy trong trình duyệt của bảo vệ
(`frontend/src/components/AlertBanner.jsx`): beep phân biệt theo loại vi phạm
+ TTS tiếng Việt qua Web Speech API. Không có còi/loa/relay vật lý nào được
lái — vì chưa có phần cứng để test.

Khi có phần cứng thật (Raspberry Pi + relay/buzzer, hoặc loa ngoài qua GPIO):
- Thêm 1 lệnh gọi phần cứng ngay tại nơi alert được đẩy vào queue
  (`app/cv/pipeline.py` — `_push_alert` / `_push_face_match_alert`), hoặc một
  consumer riêng đọc từ `_alert_queue` song song với WebSocket.
- Không cần đổi kiến trúc hiện tại (queue single-consumer) — nếu cần nhiều
  consumer (WS + GPIO), đổi `queue.Queue` thành broadcast đơn giản (list các
  queue con) lúc đó, không làm trước khi có nhu cầu thật.

## RTSP / đa camera
`CAMERA_SOURCE` (app/config.py) đã source-agnostic (index/file path/rtsp://
URL) nhưng mới validate bằng video file local, chưa test với RTSP server hay
camera IP thật. Đa camera (nhiều `VideoPipeline` chạy song song) là bước sau,
chưa xây UI/luồng xử lý cho việc đó vì không có camera thứ 2 để test.
