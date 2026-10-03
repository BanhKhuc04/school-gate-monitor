# Bằng chứng Task 1–4 và đợt 5 (03/10/2026)

| Phần | Mã hiện có | Kiểm thử | Video | Camera thật |
|---|---|---|---|---|
| Task 1 runtime | metrics/profile/consensus/crossing | 59 focused đạt trong audit; 33 capture/preview/runtime đạt sau sửa | Báo cáo cũ giới hạn 20 giây, không đủ EOF | Chưa đạt KPI hai nguồn |
| Task 2 UI/QA | menu cũ, camera/ROI/media/quyền | QA backup/closure 40 đạt, DB/media đã cách ly | Không dùng để chứng minh UI/API | Chưa endurance |
| Task 3 training | dataset/job/candidate/feedback | Schema closure đã kiểm lại | 13 job là baseline, không có job đang train | 3 feedback, chưa đủ holdout |
| Task 4 nghiệm thu | harness/báo cáo | Regression cũ 1192 test có 1 lỗi datasets | 15 video 1280×720 đã có (~8 phút); blocker thiếu video hết hiệu lực | 30 phút/12 giờ giữ mở |

Process lúc bắt đầu: backend uvicorn --reload và Vite đang chạy; không có
pytest/training/benchmark đang dùng artifact dọn. Torch 2.6.0+cu124 CUDA
hoạt động; mức tận dụng GPU chưa có baseline hai nguồn đủ điều kiện.

T1: manifest 6 thư mục test/QA, tổng 53,27 GB (decimal) được dọn;
D sau dọn 68,79 GiB. 176.571 artifact staging bỏ khỏi index; không xóa dữ liệu
vận hành, nhãn, checkpoint. Bản index trước đợt nằm trong .git để phục hồi staging.

Các số liệu accuracy/coverage/mũ/hành vi chưa được đo trên holdout người gán nhãn.
Không đánh dấu mục dữ liệu/camera/Kaggle hoàn tất bằng kết quả unit test.

## Trạng thái khi bàn giao Cursor

- Handoff chính: [CURSOR_HANDOFF.md](CURSOR_HANDOFF.md), R0–R15. Nhiều thay đổi
  runtime/OCR/UI/QA/dataset đang ở working tree; HEAD chưa chứa toàn bộ.
- Commit capture `89bd2c4`; commit backup/storage `f535974`. Không trộn staging
  có sẵn vào commit mới. UI 24 file và dataset 8 file liệt kê trong báo cáo riêng.
- Backup bị lặp mỗi reload đã sửa lịch qua complete marker và cancellation.
  Dọn 23 bộ dang dở có manifest (38,91 GiB), giữ 6 bộ complete. D còn 53,2 GiB,
  C 6,7 GiB tại thời điểm dọn; không xóa nhãn/weights/media vận hành.
- Hai bộ mới nhất: hash 9.626 file/bộ đạt, DB restore integrity ok; full media
  restore còn mở. Backup/maintenance fixture 38/38 đạt.
- Full sau isolation flag: 1.200 pass/14 fail/1 skip (342,84 giây). Sau đó sửa
  fixture bật collector/guard giả và 59/59 đạt; chưa full rerun sau fixture cuối.
  R0 tiếp việc này, không báo full suite xanh.
- UI 9/9 API thật cho auth/dataset/ảnh/bbox; preview/WS stub. Build/lint exit0,
  lint có warnings cũ. `UI_REPORT.md` giữ giới hạn kiểm chứng.
- Dataset audit: 8.259 detect/3.188 OCR hợp lệ cấu trúc, 4 nhóm ảnh trùng detect,
  1 nhóm rò train/val; mũ 0 ảnh. Selftest export 10/10. CSV chưa duyệt, holdout
  chưa có; 3 notebook chưa tạo, chưa train Kaggle. Xem `DATA_REPORT.md`.
- Ultralytics 8.4.168 và CCT package/ONNX có ở local; weights runtime chưa chuyển
  YOLO11. Chưa có baseline hai nguồn/video EOF/camera endurance/accuracy holdout.
