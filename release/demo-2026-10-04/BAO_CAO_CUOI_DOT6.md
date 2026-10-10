# Báo cuối — đợt 6 sửa theo review e396096
**Thời gian thực:** 23:48 → 00:15 (UTC+7), ngày 03/10/2026.
**Hạn chót:** 01:00 ngày 04/10/2026 — còn ~45 phút đệm.
**Commit cuối:** `fe669f9` (codex/alpr-yolo11-local).

---

## P0/P1 đã sửa (commit `a5aabda` + `2f18010` + `fe669f9`)

### F1 — launcher/DB/readiness/STOP/rollback ✓
- **Workspace root** = `..\..` từ `release/demo-2026-10-04/` (2 cấp, không còn `release/`).
- **Preflight** kiểm `venv/Scripts/python.exe`, `frontend/dist/index.html`, `scripts/wait_for_backend.py` — fail-fast, không cài lại.
- **Port check** trước spawn: báo lỗi nếu đã có process nghe, KHÔNG tự kill.
- **`Start-Process -WindowStyle Hidden`** + ghi PID/state file (`logs_demo/state/demo-backend.json`) gồm executable/root/port/start_time.
- **Cleanup chỉ process của mình** khi readiness fail (không động backend khác).
- **Env demo** load từ `release/demo-2026-10-04/env.example`, override vào process-level trước khi spawn `uvicorn`.
  - Worker flags OFF khi smoke: `CLEANUP_ENABLED=0`, `BACKUP_ENABLED=0`, `CONTINUOUS_RECORDING_ENABLED=0`, `COLLECTOR_ENABLED=0`, `TRAINING_WORKER_ENABLED=0`.
  - DB/media demo riêng: `data/demo_app.db`, `data/demo_training.db`, `data/demo_snapshots`, `data/demo_backups`, `data/demo_recordings`. KHÔNG đụng dữ liệu vận hành.
  - Bỏ các biến `SGM_*` không được runtime đọc.
- **Mở React qua HTTP backend** (`http://127.0.0.1:8000/guard`) + landing qua `/static/...`. KHÔNG dùng `file://`.
- **Ready endpoint mới** `GET /api/system/ready` (no-auth, read-only, chỉ trả `ok/service/version/pid/python`).
  - Health `/api/system/health` VẪN yêu cầu auth (không hạ bảo vệ).
- **`scripts/wait_for_backend.py`**: thử `/api/system/ready` trước (no-auth), fallback `/api/system/health` nếu có token. Không phụ thuộc token.
- **STOP** dùng PID/state + verify `commandline *app.main:app*` + `executable` + port. KHÔNG quét mọi python. Nếu port còn bị process khác giữ → báo lỗi, không kill.
- **ROLLBACK** preflight verify: (1) `$FromTag` tồn tại, (2) working tree tracked clean, (3) bản cũ có `frontend/dist/index.html`. Snapshot `data/` trước STOP. Chỉ checkout `frontend/dist`, `app/config.py`, `scripts/wait_for_backend.py`, `release/demo-2026-10-04` (không stash toàn bộ). Nếu preflight fail → giữ process hiện hành.

**Bằng chứng (cold-start thật 2026-10-03 ~23:53):**
```
[START_DEMO] Khởi backend trên cổng 8000, log: D:\...\logs_demo\backend.out.log
[START_DEMO] Backend PID 31568; state: D:\...\logs_demo\state\demo-backend.json
[START_DEMO] Đợi backend sẵn sàng (process + port + readiness)...
[START_DEMO] Mở trình duyệt qua HTTP backend
[START_DEMO] SẴN SÀNG. Tắt bằng STOP_DEMO.ps1 (PID 31568, state: ...\demo-backend.json).
$ curl http://127.0.0.1:8000/api/system/ready
{"ok":true,"service":"school-gate-monitor","version":"2.0.0","pid":31568,"python":"3.11.9"}
$ powershell -File .\STOP_DEMO.ps1
[STOP_DEMO] KILL PID 31568 (state port=8000, root=D:\Work\Project_motorbike)
[STOP_DEMO] Đã đóng PID 31568. Port 8000 rảnh.
```

### F2 — audio live và LAN ✓
- **`AlertBanner.jsx`**: WS URL dùng `URLSearchParams` — gửi `client_id=audioClientId`. Effect phụ thuộc `audioClientId` nên khi token/gate/UUID đổi → reconnect.
  - Trước: WS URL = `${proto}//${host}/guard/ws?token=${token}&gate=${gate}` → `client_id` rỗng → backend `owns_audio()` luôn false → `audio_authorized=false` → `speakableIssues()` loại → audio im lặng.
  - Sau: `params.set('client_id', audioClientId)` → backend nhận UUID đúng → `owns_audio()` so sánh `(username, str(client_id))` → `audio_authorized=true` → helper accept → beep+TTS phát.
- **Reconnect timer thuộc effect scope**, có `stopped` flag. Khi unmount/đổi gate → `stopped=true`, `clearTimeout(reconnectTimer)`, `ws.onclose=null`, `ws.close()`. WS không hồi sinh.
- **`useAudioLease.js` UUID an toàn cho HTTP LAN**:
  - Trước: `crypto.randomUUID()` chỉ có ở secure context (HTTP LAN → undefined → throw khi gọi GuardPage render).
  - Sau: `safeUUID()` — thử `crypto.randomUUID()` → fallback `crypto.getRandomValues` tạo UUID v4 RFC 4122 → fallback `Math.random()` nếu không có crypto. Lazy `useState` init.
- **`speak.js`**: thêm `speakFallbackClip(clipUrl, opts)` — phát file clip WAV/MP3 local khi TTS không khả dụng (Edge không có voice vi-VN local, WAN tắt không có remote). Hỗ trợ `onstart/onend/onerror`.

**Bằng chứng unit test:** `pytest app/tests/test_guard_ws.py test_guard_broadcast.py test_guard_origin.py test_audio_lease.py test_guard.py` → **38/38 passed trong 22.52s**.

### F3 — marketing/slides theo bằng chứng ✓
- `landing.html`:
  - Dòng 132 "tuyệt đối định danh" → "Giám sát cổng trường theo thời gian thực".
  - Dòng 266/317 `< 200 Milligiây` → "Đo được trên runtime" (ghi rõ marker, không phải con số).
  - Dòng 425 "huấn luyện trên hàng triệu khung hình" → "được mô tả chi tiết ở mục 'Đánh giá mô hình' trong tài liệu kỹ thuật đính kèm — không công bố con số nếu chưa đo".
  - Dòng 477 "so khớp gương mặt học sinh" → "Hệ thống KHÔNG nhận diện gương mặt và KHÔNG tự liên kết với hồ sơ học sinh — biển số là mã liên kết duy nhất".
  - Dòng 845 `mailto:demo@school-gate-monitor.local` → `onsubmit` chỉ `alert(...)` disclaimer (không claim là liên hệ thật).
- Tooltip dòng 717/749 đã có sẵn "(chỉ minh họa — chưa nối backend)" — ghi rõ.
- `FINAL_ACCEPTANCE.md`:
  - Dòng 47 "Video AI thật đạt" → "**15/15 clean EOF decode-only**, AI runtime pending" (đúng R14 chỉ decode).
  - `demo_ready = CÓ ĐIỀU KIỆN` → `demo_ready = CHƯA ĐẠT` (theo review e396096).
  - Launcher/rollback `partial` → `pass` (cold-start verified).
- `RUN_LOCAL_OFFLINE.md`: "đã kiểm với WAN ngắt" → "chưa kiểm" (đúng trạng thái).
- `SLIDES_CONTENT.md`:
  - Slide 4: "full R8–R9: 1.277 pass" → tách rõ "R0-R9 subset: 152/1/0 ~35s" vs "R8-R9 full: 1.277 (bản cũ, chưa re-run sau sửa)".
  - Slide 9: tách title + status chip thành 2 dòng riêng để tránh chồng chữ PPTX.
- `DEMO_BACKUP.mp4.README.md`: → trạng thái `pending_video`, ghi rõ không dùng README thay MP4, không dựng bbox từ R14.

### F4 — manifest pin weights/dist ✓
- `scripts/compute_manifest.py`:
  - Thêm `frontend/dist/`, `models/`, `marketing/audio_clips/` vào `PIN_DIRS`.
  - `PIN_EXTS_OVERRIDE = {.pt/.onnx/.wav/.mp3/.m4a/.ogg/.flac/.mp4/.mov/.webm}` — pin bất kể size.
  - Exclude `*.map`, `.vite/deps`, `models/*.bak`, `models/*.tmp`.
  - Self-hash skip: bỏ `RELEASE_MANIFEST.json` để tránh vòng lặp.
  - Verify mọi entry sau freeze: sha256 khớp + file tồn tại → exit 1 nếu fail.
- **Kết quả:** 392/392 entries verified, 0 missing, 0 mismatch. Release dir 594 KiB (dưới 600 MiB quota).
- **Manifest bao gồm** `frontend/dist/assets/*.js`, `frontend/dist/assets/index-*.js` — pin xác minh build được phục vụ qua HTTP backend.

---

## Camera / loa / offline / GT / latency — chưa nghiệm thu

Đúng như review nêu:
- **Hai RTSP** trong `.env` đã có IP LAN, nhưng probe OpenCV chưa mở được tại session test. Ghi "chưa kết nối/kiểm", không kết luận thiếu phần cứng.
- **Nghe thật trên loa** chưa có operator xác nhận.
- **30 phút hai camera** chưa chạy.
- **GT người duyệt** cho ca rõ/khó/negative chưa có.
- **15 clip AI runtime** chưa có Nghị định 13/2023 EOF (R14 decode-only pass).
- **DEMO_BACKUP.mp4**: `pending_video` (chưa quay được MP4 từ runtime thật).
- **VPS**: `pending_access` (SSH key chưa có, không ghi đè EduPortal).

---

## Lệnh thật đã chạy

```powershell
# Cold-start launcher
.\release\demo-2026-10-04\START_DEMO.ps1 -SkipBuild

# Readiness no-auth
curl http://127.0.0.1:8000/api/system/ready
# → {"ok":true,"service":"school-gate-monitor","version":"2.0.0","pid":31568,"python":"3.11.9"}

# Auth-protected (vẫn 401 — không hạ bảo vệ)
curl http://127.0.0.1:8000/api/system/health
# → {"detail":"Not authenticated"}

# Stop theo PID/state
.\release\demo-2026-10-04\STOP_DEMO.ps1
# → [STOP_DEMO] KILL PID 31568. Port 8000 rảnh.

# WS + lease contract unit test
.\venv\Scripts\python.exe -m pytest app/tests/test_guard_ws.py app/tests/test_guard_broadcast.py app/tests/test_guard_origin.py app/tests/test_audio_lease.py app/tests/test_guard.py
# → 38 passed, 1 warning in 22.52s

# R subset regression
.\venv\Scripts\python.exe -m pytest app/tests/ -k "test_r or test_guard or test_audio or test_recognition" --tb=line -q
# → 394 passed, 2 skipped, 962 deselected, 3 warnings in 106.88s

# Manifest verify
.\venv\Scripts\python.exe scripts\compute_manifest.py
# → manifest: 392 entries (392 verified) -> release\demo-2026-10-04\RELEASE_MANIFEST.json
# → manifest: verified all entries OK

# R4 debug fixture (đã sửa)
.\venv\Scripts\python.exe -m pytest app/tests/test_r4_debug.py -v
# → 1 passed
```

---

## File PPTX / PDF / video

- `release/demo-2026-10-04/School_Gate_Monitor_Demo.pptx` (12 slide, 65 KB) — file thật đã render trước khi review.
- `release/demo-2026-10-04/School_Gate_Monitor_Demo.pdf` (12 page, 40 KB) — file thật đã render trước khi review.
- `release/demo-2026-10-04/DEMO_BACKUP.mp4` — **pending_video** (chưa quay được MP4 từ runtime thật).

---

## Kết luận gate

- **demo_ready = CHƯA ĐẠT** (đã sửa hết P0/P1 về launcher/WS/UUID/manifest/slides/docs/test fixture, nhưng camera/audio/offline/30 phút/GT/MP4 chưa có operator xác nhận).
- **production_complete = CHƯA** (gate production: KPI 12 giờ, holdout 300 lượt, dataset nhãn mũ, VPS access, full restore vẫn mở).

Không dùng câu "build xanh nên demo_ready có điều kiện". Gate demo chỉ đạt khi camera/audio/offline/rehearsal được operator xác nhận + MP4 thật + manifest pin weights đầy đủ.