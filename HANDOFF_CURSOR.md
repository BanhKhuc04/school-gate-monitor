# Bàn giao cho Cursor — School Gate Monitor

Dự án: hệ thống camera AI giám sát cổng trường (FastAPI backend + React/Vite
frontend). Repo: `D:\Work\Project_motorbike`. Đọc file này trước khi làm gì
tiếp — nó tóm tắt chính xác trạng thái hiện tại, việc đang dang dở, và 1 bug
thật cần sửa trước khi tiếp tục.

## Việc đang dang dở NGAY LÚC BÀN GIAO — có bug thật, CHƯA commit

Đang restyle từng trang React theo bộ thiết kế mới ("Vanguard Campus
Security", xem phần Design system bên dưới). Vừa làm xong `GuardPage.jsx`
(trang giám sát trực tiếp của bảo vệ) thì phát hiện **WebSocket cảnh báo
không còn đẩy alert tới client** — đây có thể chính là nguyên nhân thật của
cái "flaky test" `test_guard.spec.js` đã coi là vô hại suốt cả phiên làm
việc trước đó (lúc thì pass lúc thì fail 1 trong 2 test alert) — giờ nó fail
**cả 2** đều đặn, nên nhiều khả năng đây luôn là bug thật, không phải flake.

**File đang sửa dở (chưa commit):**
- `app/api/system.py` — mở thêm quyền `security` cho `GET /api/system/health` (để Guard page hiện trạng thái pipeline)
- `app/tests/test_system.py` — cập nhật test tương ứng (đã pass)
- `frontend/src/components/AlertBanner.jsx` — thêm prop `onAlert` callback (để GuardPage nhận lịch sử alert mà không cần mở 2 WebSocket)
- `frontend/src/pages/GuardPage.jsx` — viết lại toàn bộ theo thiết kế mới (status strip real-time từ `/api/system/health`, panel video HUD, panel lịch sử cảnh báo bên phải)

**Cách tái hiện bug** (đã xác nhận bằng Python thuần, KHÔNG liên quan gì tới
frontend/React — loại trừ hoàn toàn nghi ngờ do GuardPage mới viết):

```bash
cd D:\Work\Project_motorbike
./venv/Scripts/python.exe -c "
import asyncio, json, urllib.request

async def main():
    import websockets
    req = urllib.request.Request('http://localhost:8000/api/auth/login', method='POST',
        data=json.dumps({'username':'security','password':'security123'}).encode(),
        headers={'Content-Type':'application/json'})
    token = json.loads(urllib.request.urlopen(req).read())['access_token']

    uri = f'ws://localhost:8000/guard/ws?token={token}'
    async with websockets.connect(uri) as ws:
        print('connected')
        req2 = urllib.request.Request(
            f'http://localhost:8000/api/dev/trigger-test-alert?violation_type=NO_HELMET&plate_read=WSTEST',
            method='POST', headers={'Authorization': f'Bearer {token}'})
        urllib.request.urlopen(req2)
        print('triggered, waiting for message...')
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print('RECEIVED:', msg)
        except asyncio.TimeoutError:
            print('TIMEOUT - no message received')

asyncio.run(main())
"
```

Kết quả hiện tại: `connected` → `triggered, waiting for message...` →
**`TIMEOUT - no message received`**. Backend `POST /api/dev/trigger-test-alert`
vẫn trả về `200 {"ok": true, "alert": {...}}` bình thường (tức là code endpoint
chạy đúng, `pipeline._alert_queue.put(alert)` được gọi) — nhưng WS handler ở
`app/api/guard.py` (`websocket_alerts`, đọc bằng `pipeline.get_alert()` mỗi
200ms) không bao giờ lấy được item đó ra để gửi cho client.

**Hướng nghi vấn chưa kiểm chứng hết** (chưa đủ thời gian đào sâu):
- `get_pipeline()` là singleton module-level (`app/cv/pipeline.py`, biến
  `_pipeline`) — kiểm tra xem WS handler và dev-trigger endpoint có thực sự
  cùng trỏ tới 1 instance hay không (ví dụ nếu pipeline thread crash và có
  logic nào đó tạo lại instance mới thì `_alert_queue` cũ mất theo).
- Kiểm tra `pipeline.get_alert()` (method lấy item từ `_alert_queue`) — xem
  có đang catch exception nuốt mất lỗi, hoặc dùng sai queue instance không.
- `_alert_queue` được comment là "single-consumer" — kiểm tra có chỗ nào
  khác đang consume (rút cạn) queue trước khi WS kịp đọc không (ví dụ nếu
  2 WS client cùng kết nối, mỗi client gọi `get_alert()` riêng nhưng cùng
  queue → chỉ 1 client nhận được, còn lại timeout — CÓ THỂ đây chính là gốc
  rễ: lúc tôi test có nhiều tab trình duyệt/nhiều kết nối WS cũ chưa đóng
  hẳn đang tồn tại song song, "ăn mất" message trước khi client mới kịp đọc).
- Việc backend mới được restart nhiều lần trong phiên (để áp dụng code mới)
  — kiểm tra có tiến trình `uvicorn` cũ nào còn sống song song trên cổng
  8000 không (`netstat -ano | grep :8000`), vì nếu 2 process backend cùng
  chạy thì mỗi process có `_alert_queue` riêng, và trigger có thể rơi vào
  process không phục vụ WS đang kết nối.

**Việc cần làm trước tiên:** xác định gốc rễ (nhiều khả năng nhất là giả
thuyết "nhiều connection cùng consume 1 queue" hoặc "2 process backend chạy
song song" ở trên), sửa đúng gốc, xác nhận bằng đúng script Python ở trên
(không cần qua Playwright), rồi mới quay lại verify `test_guard.spec.js`.

## Việc đã làm xong trong phiên trước (đã commit, xem `git log`)

Thứ tự thời gian, mới nhất trước:
1. `f4c2082` Restyle LoginPage theo design system mới
2. `e6bc027` Thay landing page bằng thiết kế Stitch "Vanguard Campus Security"
3. `d4d8dc4` **Xóa hoàn toàn nhận diện khuôn mặt** (backend + DB + frontend + test) — quyết định sản phẩm vì khẩu trang phá được face recognition
4. `169e0f9` Thêm trang landing/marketing ban đầu
5. `86d1f5b` Dashboard: thêm trend 14 ngày + theo lớp, fix bug JOIN thiếu (Lớp/Học sinh luôn rỗng)
6. `cfba44e`, `eae9bd8`, `b2ac691` — polish UI admin nhỏ (format ngày giờ, tab title, layout width)
7. `70278e2` Giải mã dataset ký tự biển số (user cung cấp) để chuẩn bị train YOLO
8. `8b597c9` **Fix bug thật**: gate helmet/plate theo loại xe — trước đây người đi bộ/xe đạp thường bị báo vi phạm sai
9. `d9ee010`, `50e764e` — **2 fix bug gốc quan trọng nhất**: (a) `getattr(dict,...)` khiến posture luôn `'unknown'`, RIDING_THROUGH_GATE không bao giờ chạy; (b) face-match không lưu snapshot/DB (đã xóa tính năng này sau ở #3, nhưng fix này từng đúng lúc đó). Cũng thêm `CAMERA_SOURCE`/`CAMERA_LOOP` (hỗ trợ webcam index/video file/RTSP), âm thanh phân biệt loại vi phạm + TTS tiếng Việt, regex validate biển số VN (gắn cờ, không drop).

**Artifact đã publish** (link chia sẻ được, để gửi cho trường khác xem):
https://claude.ai/artifact/KCqznZsiqASqLhXWRtCCUv (trang landing, đồng bộ với `marketing/landing.html`)

## Design system — "Vanguard Campus Security"

Nguồn: user dùng Google Stitch tạo ra 1 bộ thiết kế đầy đủ (landing + 7 màn
hình admin), export zip, tôi đã giải nén và decode ra:
- **Token đầy đủ**: `frontend/src/index.css` (`@theme` block — Tailwind v4,
  tự sinh utility class như `bg-primary`, `text-on-surface`, `bg-error-container`...)
- **Font**: Plus Jakarta Sans (UI) + JetBrains Mono (dữ liệu/timestamp/biển số), load qua Google Fonts trong `frontend/index.html`
- **Bảng màu gốc** (nếu cần đối chiếu lại): Navy `#091426` (primary), Cobalt `#0051d5` (secondary/CTA), Emerald `#00a472`/`#6ffbbe` (tertiary, trạng thái hợp lệ), Error đỏ `#ba1a1a`
- **File Stitch export gốc** (ảnh + code.html từng màn hình) nằm ở:
  `C:\Users\khucv\AppData\Local\Temp\stitch_export\stitch_school_gate_monitor_landing_page\`
  (giải nén từ `C:\Users\khucv\Downloads\stitch_school_gate_monitor_landing_page.zip`
  — nếu thư mục temp đã bị dọn, giải nén lại từ file zip trong Downloads)
  - `school_gate_monitor_..._camera_ai/` → landing page (đã áp dụng, xem `marketing/landing.html`)
  - `ng_nh_p_h_th_ng_qu_n_tr_.../` → Login (đã áp dụng, xem `frontend/src/pages/LoginPage.jsx`)
  - `gi_m_s_t_tr_c_ti_p_guard_live_view/` → Guard live view (đang áp dụng dở, xem phần bug ở trên)
  - `nh_t_k_vi_ph_m_violations_log/` → Violations log (CHƯA làm)
  - `ph_ng_ti_n_ng_k_registered_vehicles/` → Vehicles (CHƯA làm)
  - `s_c_kh_e_h_th_ng_l_u_tr_system_health/` → Health (CHƯA làm)
  - `qu_n_l_t_i_kho_n_user_accounts/` → Users (CHƯA làm)
  - `b_o_c_o_th_ng_k_analytics_dashboard/` → Dashboard (CHƯA làm)
  - `ng_k_i_so_t_khu_n_m_t_face_enrollment_logs/` → **BỎ QUA hẳn** — đây là màn hình đăng ký khuôn mặt, tính năng đã bị xóa khỏi sản phẩm (xem commit `d4d8dc4`)
  - `vanguard_campus_security/DESIGN.md` → tài liệu design system đầy đủ (màu, typography, spacing, component style) do Stitch sinh ra

**QUAN TRỌNG khi áp dụng thiết kế Stitch vào từng trang:** các màn hình mock
của Stitch có RẤT NHIỀU chi tiết/tính năng KHÔNG có thật trong backend (ví
dụ: multi-camera switcher, "ca trực/điểm kiểm soát", demo account shortcuts,
nút "Chặn kiểm tra vé", "Trừ điểm thi đua", traffic load real-time, NVR
station...). **Không bịa thêm chức năng giả** — chỉ lấy màu sắc/font/layout,
còn nội dung/tính năng phải khớp đúng với API thật đang có. Xem cách
`LoginPage.jsx` và `GuardPage.jsx` đã làm (bỏ hết phần giả, chỉ giữ phần
thật) làm mẫu tiếp tục cho 5 trang còn lại: Violations, Vehicles, Health,
Users, Dashboard.

## Chạy dự án

```bash
# Backend
cd D:\Work\Project_motorbike
./venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
# (tùy chọn) trỏ camera vào video file thay vì webcam OBS mặc định:
# CAMERA_SOURCE=đường/dẫn/video.mp4 CAMERA_LOOP=1 ./venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# Frontend
cd D:\Work\Project_motorbike\frontend
npm run dev

# Test
cd D:\Work\Project_motorbike
./venv/Scripts/python.exe -m pytest app/tests -q      # unit, không cần server chạy
./venv/Scripts/python.exe -m pytest tests/ -q         # integration, CẦN backend đang chạy ở :8000
cd frontend && npx playwright test --reporter=list    # CẦN cả backend :8000 và frontend :5173 đang chạy
```

Tài khoản test có sẵn: `admin`/`admin123`, `security`/`security123`,
`management`/`management123`.

## Lưu ý khác

- Nhiều file rác ở gốc repo (`fix_pipeline*.py`, `debug_seed.py`,
  `check_pipeline.py`, `PLAN_*.md` cũ) là từ phiên làm việc trước đó, chưa
  dọn, chưa track git — bỏ qua, không phải việc của tôi để lại.
- `yolov8n-pose.pt` ở gốc repo — file model tải về, đã có trong `.gitignore`.
- `datasets/plate_char_ocr/` — dataset ký tự biển số user cung cấp, đã giải
  mã mapping class (xem `datasets/plate_char_ocr/README.md`), sẵn sàng train
  nhưng CHƯA train (`yolo detect train data=datasets/plate_char_ocr/data.yaml ...`).
- License YOLOv8/Ultralytics (AGPL) — user đã được cảnh báo, quyết định "cứ
  train trước, tính license sau khi bán được" — CHƯA xử lý, cần nhắc lại
  trước khi thương mại hoá thật.
