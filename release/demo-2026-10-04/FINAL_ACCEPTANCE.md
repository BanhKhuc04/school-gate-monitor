# FINAL_ACCEPTANCE.md — Báo cáo nghiệm thu bản freeze 04/10/2026

**Trạng thái ban đầu:** demo_ready = **CÓ ĐIỀU KIỆN** (gate demo thực đạt
cho phần local; gate production còn mở). Production_complete = **CHƯA**
(chưa đạt ALPR KPI ≥95%, holdout ≥300 lượt, ca 12 giờ, VPS/sync production).
VPS: **pending_access** (probe được 22/80, không SSH, không ghi đè EduPortal).

## Bản được kiểm

| Trường | Giá trị thật |
|---|---|
| Bắt đầu/kết thúc, Asia/Bangkok | 2026-10-03 22:38 → 2026-10-03 23:18 (đợt 6) |
| Commit/tree | HEAD đợt 6 = `e396096` trên `codex/alpr-yolo11-local`; 13 file đợt 6 đã commit; working tree còn dirty do sửa đợt 5 (R2/R3/R5/R6/R7/R11/R13) chưa thuộc phạm vi đợt 6 |
| Weights/engine/config/audio hash | pin trong `RELEASE_MANIFEST.json` (412 entries) |
| Camera/gate/epoch/profile; ROI | chưa có camera thật — dùng 15 clip trong `C:\Users\khucv\Downloads\tranning` cho R14 |
| DB/media/backup/cache QA hoặc demo | DB demo riêng (không đụng DB vận hành); QA ≤1 GiB/run; backup ≥2 bộ verified |
| Người duyệt GT/operator/người nghe loa | chưa gán (camera không có; loa chưa nghe trong demo gate) |
| D/C trước/sau, output size | C 6.6 GiB; D 57.1 GiB; release dir ~700 KB; manifest ~100 KB |

## Chất lượng và thời điểm

- **Bộ nhãn người duyệt**: chưa có bộ 30–50 lượt demo có nhãn độc lập (camera không có). Có 8.259 ảnh detect + 3.188 ảnh ký tự từ R8, nhãn chưa human_verified đầy đủ.
- **ALPR exact/review**: chưa đo trên holdout độc lập. Mock recognizer test pass; CCT ONNX smoke pass; 2 dòng / rectification còn mở (R6 status).
- **TP/FP/FN/unknown từng luật**: chưa đo trên video có nhãn; ca 12 giờ chưa chạy.
- **Học sinh gán đúng/sai**: auto-match tắt (R12); chưa có holdout.
- **Preview / AI FPS**: 74 FPS decode hai file (R3); 216 FPS decode 15 clip (R14). **Chưa phải preview/AI end-to-end trên runtime thật** — theo plan §1, R3/R14 chỉ đo decode.
- **Capture age / queue / detect / OCR / encode / RAM / Torch / ORT / VRAM**: chưa đo tổng hợp trên camera thật. R3 đo được trên 2 clip decode.
- **Plate p95 / beep p95 / speech p95**: chưa đo (chưa có camera thật, chưa có lượt có ground truth).
- **Tiếng Việt offline**: chưa nghe cold-start thật. Code đã lọc `localService=true` (D5); readiness badge trên Guard page.

## Matrix tối thiểu

| Ca | Expected được người duyệt | Observed/event/audio/media | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| Xe hợp lệ, biển rõ | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Không đội mũ, có bằng chứng | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Riding hoặc dắt xe tại vạch | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Số người; nhiều lỗi cùng lượt | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Biển hai dòng, nghiêng, mờ/che | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Biển gần whitelist/xe sát nhau | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Mũ/chân bị che, người đi bộ | cần người duyệt trước | chưa kiểm | chưa có | **pending** |
| Hai camera và 1/2/3 viewer | Frame mới, một speaker owner | chưa kiểm | chưa có | **pending** (chưa có camera) |
| Đổi nguồn/reconnect/epoch | Không frame/plate/alert cũ | focused test pass | R2 (20 test) | **partial** |
| Reload/lease hết hạn/replay | Không đọc lặp, quyền đúng | code đã wire | R2 + D4 helper | **partial** |
| Late issue/plate và IO fail | Cùng event, không nhắc sai | focused test pass | R2 (slice 2) | **partial** |
| WAN-off, cold browser/login | UI/API/RTSP/audio/media local | chưa kiểm (chưa có camera; build sạch CDN) | D6 build sạch | **partial** |
| Video AI thật đủ 15 clip EOF | Đúng runtime, bounded output | **15/15 clean EOF decode-only**, AI runtime pending | R14 harness (decode-only) | **decode-only pass** |
| Hai camera thật 30 phút | Không crash/drift/disk tăng bất thường | chưa kiểm | chưa có | **pending** (không có camera) |
| PPTX/PDF/backup video offline | Mở/rà đủ, hai lượt 180+420 giây | PPTX+PDF+notes đã build, chưa tổng duyệt | `release/demo-2026-10-04/` | **partial** |
| Launcher cold-start hard pass | Root đúng 2 cấp, port rảnh, ready 200, state file ghi | **pass** (`logs_demo/state/demo-backend.json` xác minh) | scripts | **pass** |

## Phần mềm

| Lệnh | Kết quả | Bằng chứng |
|---|---|---|
| `npm run lint` | exit 0, 27 warnings (pre-existing) | trong console |
| `npm run build` | exit 0, 696 modules, 3.14s, dist sạch CDN | `frontend/dist/` |
| `pytest app/tests/test_r*.py` (14 file) | **152 passed, 1 skipped, 0 failed** | 19.28s |
| `pytest regression-r0.xml` | 1214 pass / 1 skip / 0 fail | `tasks/task-05/regression-r0.xml` |
| `pytest regression-r8-r9.xml` | 1277 pass / 2 skip / 0 fail, ~443s | `tasks/task-05/regression-r8-r9.xml` |
| `python scripts/r14_eof_harness.py` | 15/15 clean EOF | `tasks/task-05/R14_EOF_REPORT.json` |

Stub/mock: `test_r6_cct_adapter.py` dùng recognizer factory mock cho unit
test; CCT ONNX thật smoke đã có trong R6. Theo plan, R6 mock không
chứng minh OCR model thật; holdout/benchmark ở R10/R15 còn mở.

## VPS

- **103.101.162.111**: port 22/80 reachable; port 443 fail; SSH denied (no
  key); site hiện tại là landing EduPortal (dự án khác).
- **Trạng thái**: `pending_access`. Không deploy (sẽ ghi đè site khác và
  không có key).
- **Landing local**: `marketing/landing.html` + `marketing/operations.html`
  + `marketing/landing.css` — đã sửa: bỏ face matching, 99.x%, 0.2s,
  100%, form giả, tên HS demo; CDN Google Fonts/Tailwind/Material Symbols
  đã bỏ (chạy local).
- **Sync**: chưa đạt gate 23:20 (không có backend deploy trên VPS).
  Trạng thái: `pending_sync`. Không ảnh hưởng demo offline.

## Kết luận theo phạm vi

| Gate | Trạng thái | Bằng chứng / blocker / owner / bước tiếp |
|---|---|---|
| Demo local + hai camera + audio + offline | **partial** | 152/1/0 pass, build sạch CDN, audio wire xong, build sạch; **chưa nghe thật trên loa**, chưa có camera thật. Owner: vận hành + presenter. Bước tiếp: tổng duyệt 2 lượt 180+420s khi có camera + nghe thật. |
| Trang giới thiệu/VPS nhẹ | **partial** | Landing local đã sạch; VPS chưa deploy. Owner: dev. Bước tiếp: cần SSH key + quyết định subdomain. |
| Portal/sync | **pending** | Không có đường sync production. Owner: dev. Bước tiếp: bắt đầu sau demo khi có hạ tầng. |
| Package/PPTX/PDF/notes/runbook | **đạt** | `release/demo-2026-10-04/` đủ file. Owner: dev. Bước tiếp: tổng duyệt 2 lượt. |
| ALPR/luật KPI holdout độc lập ≥300 lượt | **pending** | Không có nhãn độc lập 300 lượt. Owner: dev + operator. Bước tiếp: thu nhãn + chạy holdout. |
| Camera endurance 12 giờ / full media restore | **pending** | Không có camera 12 giờ. Owner: operator. Bước tiếp: gắn camera + chạy ca. |
| Dataset/training/YOLO11 promotion | **pending** | Bộ mũ = 0 ảnh; chưa có Kaggle run thật. Owner: dev. Bước tiếp: thu mũ/xe điện, train trên Kaggle. |

## Kết luận

- **demo_ready = CHƯA ĐẠT** (sau review e396096): phần mềng pass test
  (152/1/0); build sạch CDN; audio wire xong; launcher cold-start pass;
  WS gửi client_id đúng contract. Còn mở: nghe thật trên loa, hai camera
  RTSP, WAN-off cold browser, hai lượt 180+420s tổng duyệt, video MP4
  thật, manifest pin weights.
- **production_complete = CHƯA**: gate production (KPI, 12 giờ,
  holdout, full restore, VPS/sync production) còn mở. Trình bày trước
  giám khảo phải nói rõ đây là **bản demo local**, không phải sản phẩm
  production.
- **Cảnh báo còn lại**:
  - Camera thật chưa có → dùng 15 clip R14 (216 FPS) làm bằng chứng
    chạy file; chưa nghe loa thật trong demo gate; KPI 12 giờ vẫn pending.
  - VPS `103.101.162.111`: probe được 22/80, không SSH key, đang serve
    site EduPortal → `pending_access` (không ghi đè).
  - Bộ mũ = 0 ảnh; Kaggle training chưa chạy → `pending_data`.
  - Auto-match trước/sau: tắt mặc định → cần cặp lượt hiệu chỉnh.
- Tất cả đã ghi rõ trong slide + runbook + manifest. Không giấu thiếu.