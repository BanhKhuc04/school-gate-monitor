# RUN_LOCAL_OFFLINE.md — cách chạy bản demo 04/10/2026 không cần Internet

Bản này **chưa được kiểm với WAN ngắt** (gate camera/audio/offline còn
mở theo review e396096). Làm theo thứ tự dưới đây; nếu một bước lỗi,
dừng và xem log trong `logs_demo/`. Bước 7 ghi các giới hạn chưa đạt.

## 1. Chuẩn bị trước

- Windows 10/11, Python 3.11 (venv có sẵn ở `venv/`), Node 20+ (đã có).
- Camera IP RTSP trong LAN (đặt IP cố định), cấu hình trong `app/config.py`
  hoặc qua env `CAMERA_SOURCE`/`CAMERA_SOURCE_SECONDARY` (xem `.env.example`).
- Loa/tai nghe, bật ở chế độ Windows mặc định (không HDMI sang TV).
- Dung lượng D còn ≥ 30 GiB (kiểm tra `Get-Volume D`).

## 2. Khởi động

```powershell
# Từ workspace root
.\release\demo-2026-10-04\START_DEMO.ps1
```

Script sẽ:
1. Build `frontend/dist/` nếu chưa có (~3s, 696 modules).
2. Khởi động `uvicorn app.main:app` ở `127.0.0.1:8000`, không --reload.
3. Đợi `/api/system/health` sẵn sàng (tối đa 30s).
4. Mở Guard + landing local trong trình duyệt mặc định.

Nếu browser chưa mở: truy cập thủ công
- App: <http://127.0.0.1:8000/>
- Landing: `marketing/landing.html` (mở từ file://)
- Operations: `marketing/operations.html` (mở từ file://)

## 3. Kiểm tra trước khi demo

| Hạng mục | Lệnh / cách kiểm | Đạt |
|---|---|---|
| Backend healthy | `curl http://127.0.0.1:8000/api/system/health` (200) | □ |
| Login | đăng nhập với tài khoản demo (`SGM_DEMO_*`) | □ |
| 2 feed mới | Guard page — đợi 5s, badge LIVE xanh | □ |
| Loa sẵn sàng | Badge `🇻🇳 VI-local` xanh; nếu `VI-remote` thì kiểm voice local | □ |
| Bật loa | Nút "🔈 Loa: TẮT" → bấm → "🔊 Loa: BẬT" | □ |
| WAN ngắt | Rút uplink router; LAN giữ; load lại trang | □ |
| Bằng chứng | Mở tab Vi phạm; crop + event_id + timestamp | □ |
| Audio ready | Cảnh báo mẫu: nói nghe được (nếu có giọng local) | □ |

## 4. Tắt

```powershell
.\release\demo-2026-10-04\STOP_DEMO.ps1
```

## 5. Rollback nếu bản mới có vấn đề

```powershell
git stash push -u -m "pre-rollback $(Get-Date -Format yyyyMMdd-HHmmss)"
.\release\demo-2026-10-04\ROLLBACK_DEMO.ps1 -FromTag 81b19f1
.\release\demo-2026-10-04\START_DEMO.ps1
```

Bản cũ `81b19f1` là commit gần nhất trước các sửa đợt 6. DB/evidence mới
giữ nguyên, chỉ đổi mã.

## 6. Khắc phục nhanh

| Triệu chứng | Cách xử |
|---|---|
| `Backend not reachable` | Xem `logs_demo/backend.err.log`; thường do port 8000 bị chiếm — `STOP_DEMO.ps1` rồi `START_DEMO.ps1` lại |
| Loa không phát | Mở DevTools → Console: gõ `speechSynthesis.getVoices()` xem có `vi-VN localService=true` không. Nếu không, dùng clip lưu sẵn hoặc thông báo "đang chờ giọng local" |
| Frame không mới | `/api/system/health.last_frame_age_sec` > 5 → kiểm RTSP LAN. Có thể camera reboot: đợi 30s, ws reconnect tự động |
| Báo cáo lỗi khi build | `cd frontend && npm ci && npm run build` |
| Frontend assets 404 khi WAN ngắt | Build phục vụ local, không CDN: kiểm tra `index.html` không có `fonts.googleapis.com` (đã bỏ ở đợt 6) |

## 7. Phần không nằm trong bản demo này (ghi rõ để người xem biết)

- **Camera thật + ca 12 giờ**: chưa có camera thật hôm nay, dùng 15 clip
  R14 (216 FPS) làm bằng chứng chạy file. KPI 12 giờ vẫn pending.
- **VPS production**: 22/80 reachable, 443 fail, SSH key chưa có — ghi
  `pending_access`. Không ghi đè site EduPortal hiện tại trên VPS.
- **Mũ / xe điện / YOLO11 weights**: chỉ có mã audit + 3 notebook Kaggle;
  bộ mũ = 0 ảnh, chưa train thật. Baseline v8/custom giữ nguyên.
- **Sync production**: chưa đạt gate 23:20, ghi pending_sync.

VPS và sync là phần làm sau demo, không chặn local.