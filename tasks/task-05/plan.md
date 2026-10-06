# Đợt 5 — hai camera, ALPR và YOLO11

Kế hoạch do người dùng phê duyệt ngày 03/10/2026. RTX 3050 4 GB, local,
hai camera trước/sau. Giữ FastAPI/React/SQLite và API cũ. Không dùng kết quả
baseline để khẳng định đã train hoặc dùng video độc lập để khẳng định ghép camera.

## Thứ tự và owner

1. T0: đối chiếu Task 1–4, code/process/test/video/camera thật; bảo toàn lịch sử.
2. T1: manifest dọn artifact, ignore, QA riêng, quota 1 GB/run/3 run; D ≥30 GB.
3. T2: capture độc lập, latest-only, preview theo frame mới, epoch chống ảnh cũ.
4. T3: một owner inference, timing đủ detector, queue/OCR/encode/CPU/VRAM.
5. T4: ByteTrack rear, tối đa 5 crop độc lập/2 giây, ≥2 phiếu mới chốt biển.
6. T5: FastPlateOCR CCT adapter, RGB/config/confidence ký tự; EasyOCR baseline.
7. T6A/B: manifest/hash/holdout theo session, xuất Kaggle riêng từng bài toán.
8. T7: luật mũ/số người/tư thế; encounter idempotent, ghép mơ hồ cần duyệt.
9. T8: 4 menu chính, AI nâng cao admin, bbox theo mẫu, giữ deep link/quyền.
10. T9: focused từng lát, regression/browser/API/video EOF, camera 30 phút/12 giờ.

Runtime/ALPR: Codex chính. UI: agent ui_settings. Tối đa hai luồng sửa code;
chỉ một regression đầy đủ hoặc benchmark GPU một lúc. Mỗi lát 3–5 file nguồn,
kiểm thử rồi commit riêng; không gom staging cũ vào commit mới.

## Hợp đồng và điều kiện nghiệm thu

- Capture → detect → ByteTrack → native crop → rectification → OCR → consensus
  → validator → event. Queue hữu hạn; không dùng biến thể cùng frame làm phiếu mới.
- OCR gồm raw/normalized, character confidence, engine/hash/frame/track/epoch.
- Accepted exact accuracy ≥95%, coverage ≥90% trên lượt có biển rõ do người gán nhãn.
- Preview ≥15 FPS/camera, AI ≥5 FPS/camera, plate p95 ≤2 giây từ vùng đọc.
- Mũ precision ≥98%/recall ≥95%; số người/hành vi ≥95%/≥90% khi quan sát được.
- Holdout ≥300 lượt, không quan sát gán nhầm học sinh; công bố mẫu và lỗi thực tế.
- Tổng GPU khoảng 3,2 GB; FP16/batch/model chỉ chọn sau benchmark/holdout.
- Cảnh báo disk <15 GB; chặn tác vụ nặng <10 GB hoặc thiếu output dự kiến.
- Không xóa dữ liệu vận hành/nhãn/checkpoint; ít nhất 2 backup kiểm restore.
- YOLO11n challenger, giữ v8 rollback; model riêng cho biển/mũ/xe điện.
- Auto-match trước/sau tắt đến khi có cặp lượt hiệu chỉnh đạt; gương/VPS hoãn.

## Giới hạn ngoài code

Huấn luyện Kaggle cần tài khoản và dataset có nhãn. Chất lượng/endurance camera
thật cần hai nguồn đang online và holdout được người xác nhận. Các mục đó giữ mở
cho tới khi có bằng chứng, không đánh dấu hoàn tất bằng unit test.
