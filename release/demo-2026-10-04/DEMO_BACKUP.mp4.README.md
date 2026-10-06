# DEMO_BACKUP.mp4 — pending_video (chưa có MP4 thật)

**Trạng thái hiện tại: pending_video.** File placeholder này KHÔNG được
dùng thay cho video runtime thật và KHÔNG được gọi là bằng chứng AI.

Theo review e396096 và F4-6:
- Quay từ runtime/app/audio thật, ghi rõ nguồn live/clip + nhãn "video
  ghi trước". ≤150 MiB.
- KHÔNG dựng bbox/biển/lỗi/giọng thành công giả từ R14 decode harness.
- Chưa quay được → ghi `pending_video`; không dùng README thay MP4.

Khi quay được, encode ví dụ:
    ffmpeg -framerate 30 -i frame_%05d.jpg -i audio.wav \
        -c:v libx264 -pix_fmt yuv420p -c:a aac DEMO_BACKUP.mp4
