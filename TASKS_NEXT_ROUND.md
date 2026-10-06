# Checklist: model biển số + đa camera + deploy VPS

> Đọc [PLAN_NEXT_ROUND.md](PLAN_NEXT_ROUND.md) trước. Mỗi bước test độc lập được trước khi sang bước sau. Làm đến khi hết danh sách hoặc gặp mục [CẦN NGƯỜI KIỂM TRA] thì dừng lại chờ.

- [x] **1** — ~~Chờ candidate~~ ĐÃ XONG: nhận file `best.pt` (plate) + `best (1).pt` (helmet) từ Kaggle.
- [x] **2** — ĐÃ XONG (làm trực tiếp thay vì script riêng): test cả 2 model cũ/mới trên toàn bộ 875 ảnh thật `data/snapshots/*.jpg` (đếm ảnh có ≥1 detection).
  - Biển số: cũ 74/875 → mới **258/875** (tốt hơn 3.5 lần).
  - Mũ bảo hiểm: cũ 679/875 → mới **346/875** (TỆ HƠN — overfit lệch domain do dataset Roboflow khác góc/khoảng cách).
- [x] **3** — ĐÃ XONG: backup `models/plate_best.pt` → `models/plate_best.pt.bak`, thay bằng bản mới. `pytest app/tests/ -q` → 44/44 pass.
- [x] **4** — Bỏ qua (không cần thiết thêm — đã xác nhận qua bước 3 pytest pass, không đổi logic).
- [x] **5** — ĐÃ XONG: model mũ bảo hiểm **KHÔNG thay** — quyết định giữ bản cũ vì bản mới tệ hơn rõ rệt (xem bước 2).
- [x] **6** — ĐÃ XONG (Cursor): `app/config.py` có `GATES: dict[str, dict]`.
- [x] **7** — ĐÃ XONG (Cursor): `_pipelines: dict` + `get_pipeline(gate_id="main")` trong `app/cv/pipeline.py`. 49/49 pytest pass.
- [x] **8** — ĐÃ XONG (Cursor): `?gate=` cho `/guard/video_feed` và `/guard/ws`.
- [x] **9** — ĐÃ XONG (Cursor): `/api/system/health` trả `gates: [...]`.
- [x] **10** — ĐÃ XONG (Cursor): dropdown chọn cổng trong `GuardPage.jsx`, ẩn khi `gates.length <= 1` (`showGateSelector`).
- [ ] **11** — [CẦN NGƯỜI KIỂM TRA] Khi camera thứ 2 lắp xong thật: set `CAMERA_SOURCE_SECONDARY`, xác nhận dropdown hiện ra và chuyển cổng đúng luồng video/alert.
- [ ] **12** — [CẦN NGƯỜI LÀM — không phải Cursor] Tự SSH `root@103.101.162.111`, chạy `bash scripts/deploy_vps.sh`, đổi mật khẩu VPS sau khi xong, xác nhận `http://103.101.162.111/` load được từ trình duyệt ngoài.

## Việc rõ ràng KHÔNG làm đợt này

Class xe đạp điện riêng (chưa có dataset thật), còi/loa vật lý GPIO (chưa có phần cứng), nhận diện khuôn mặt (đã bỏ hẳn, quyết định pháp lý).
