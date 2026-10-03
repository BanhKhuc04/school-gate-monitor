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
