# Review độc lập bản bàn giao e396096 — 03/10/2026

**Kết luận: cần sửa trước nghiệm thu; `demo_ready = CHƯA ĐẠT`.**
Có commit/build/tài liệu/slide, nhưng chưa qua gate camera, loa và WAN-off;
launcher hiện không khởi động được. “Có điều kiện” không tương đương demo
gate đã đạt. `production_complete = CHƯA` là kết luận phù hợp.

Rà trực tiếp workspace, mã, manifest, chạy lại test/build/lint, tái hiện
lease/WS bằng API thật với nguồn event tổng hợp, render PPTX/PDF và mở landing
bằng Edge. Không dùng ca tổng hợp này làm bằng chứng AI hoặc loa nghe thật.
Artifacts review ở `qa_logs/task06_review/`, khoảng 6 MiB lúc rà, không copy
media/dataset/backup vận hành. Launcher lỗi trước khi spawn backend.

## P0 — launcher không chạy và health-check sai hợp đồng

`release/demo-2026-10-04/START_DEMO.ps1:17` lấy parent một cấp từ thư mục script.
Kết quả là `D:\Work\Project_motorbike\release`, không phải workspace root.
Venv/frontend/helper đều không tồn tại ở root được tính này.

Đã chạy `START_DEMO.ps1 -SkipBuild`: exit 1, **“Không tìm thấy venv. Chạy setup
trước.”** Không sửa venv hoặc cài lại package để chữa lỗi đường dẫn này.
STOP/ROLLBACK dùng cùng cách tính root sai.

Ngay cả khi sửa root, helper `scripts/wait_for_backend.py:25` gọi
`/api/system/health` nhưng START không cấp token. Route ở
`app/api/system.py:222` yêu cầu role/auth. Repro API trả **401** khi thiếu token.
Không hạ bảo vệ health đầy đủ; readiness nên dùng endpoint tối thiểu không
nhạy cảm hoặc cơ chế token thích hợp. START cần kiểm đúng phiên backend,
chặn port trùng và cleanup đúng PID của mình khi startup thất bại.

START còn mở React qua `file://...frontend/dist/index.html`; module/assets/API
same-origin cần được phục vụ HTTP local. Mở app qua backend, không mở dist
bằng file. `Start-Process` backend cần `-WindowStyle Hidden` và PID file.

## P0 — lease có nhưng WebSocket không gửi UUID nên tất cả loa bị từ chối

`frontend/src/components/AlertBanner.jsx:75` chỉ có query token/gate, thiếu
`client_id=audioClientId`. Backend WS dùng query này làm speaker identity;
giá trị mặc định rỗng không khớp owner đã xin lease.

Repro `qa_logs/task06_review/contract-repro.json`:

| Ca | Kết quả |
|---|---|
| Xin lease với UUID | HTTP 200 |
| WS thiếu client_id, có cùng user token | audio_authorized = false |
| WS có đúng client_id, cùng token/lease | audio_authorized = true |

`speakableIssues()` loại payload audio_authorized=false, vì vậy helper đúng
vẫn im lặng trong đường live. Cần URLSearchParams/UUID đúng và effect phụ
thuộc audioClientId; browser/API integration test phải bắt lỗi nối này.

## P0 — STOP/ROLLBACK có thể tắt backend ngoài bản demo

`STOP_DEMO.ps1:11` tìm **mọi** python command line chứa `app.main:app`, không
giới hạn PID, workspace hoặc port. Tham số Port chỉ kiểm sau khi đã kill.
Không chạy STOP/ROLLBACK hiện tại để “thử”: có thể tắt backend vận hành/QA khác.

ROLLBACK gọi STOP trước khi kiểm dirty tree, rồi có thể exit 2 vì workspace
hiện đang dirty. Tức là rollback bị từ chối nhưng backend đã bị tắt. Nó cũng
chưa pin/khôi phục config và weights, nên chưa đạt rollback bản đã kiểm.
Đổi sang PID/state file có xác minh executable/workspace/port; preflight
rollback trước khi dừng, không checkout hoặc stash toàn bộ thay đổi người dùng.

## P1 — cấu hình demo không áp dụng, DB/worker chưa cách ly

`env.example` dùng SGM_CAM_FRONT_URL/SGM_CAM_REAR_URL/SGM_JWT_SECRET và các
biến audio giả định. Search toàn app không thấy runtime đọc các biến này.
Tên thật gồm CAMERA_SOURCE, CAMERA_SOURCE_SECONDARY, JWT_SECRET_KEY,
APP_DB_PATH, TRAINING_DB_PATH, SNAPSHOTS_DIR, BACKUP_DIR và các worker flags.

START không đặt DB/media demo hay tắt backup/training/collector; default
config dùng `data/app.db`, maintenance/training có thể bật. Claim “DB demo
riêng” chưa được launcher bảo đảm. Copy env vào thư mục release cũng khác
với vị trí .env mà app/config.py nạp. Phải map/load rõ trước import app.

## P1 — HTTP LAN có thể làm GuardPage lỗi ngay khi render

`useAudioLease.js:5` gọi thẳng crypto.randomUUID(). Trên browser Edge kiểm:

| Origin kiểm | Secure context | typeof crypto.randomUUID |
|---|---|---|
| http://127.0.0.1 | true | function |
| http://IP-LAN | false | undefined |

Hook mới được gọi vô điều kiện trong GuardPage; trên origin LAN như trên sẽ
throw khi tạo clientId. Dùng UUID fallback từ crypto.getRandomValues hoặc
HTTPS local phù hợp; test cả LAN, không chỉ localhost.
[MDN randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)
xác nhận yêu cầu secure context.

## P1 — audio offline/reconnect/split view chưa đủ

- speak.js ưu tiên local rồi **vẫn chọn voice remote** khi không có local;
  chưa có nhánh clip local, không có file audio trong marketing lúc rà.
  Comment/env/slide mô tả fallback không tạo ra fallback thật.
- Không có onstart/onend/onerror/readiness từ tiếng phát thực; badge có thể
  báo VI-remote dù không có giọng Việt. Mỗi speak gọi cancel có thể cắt câu
  trước của lượt xe khác. Cần queue dựa callbacks và bài nghe hai lượt sát.
- AlertBanner tạo AudioContext mới mỗi beep, chưa resume/unlock theo gesture.
  Chỉ xin lease thành công không chứng minh loa đã sẵn sàng.
- Reconnect timer nằm trong connect(), cleanup không clear được. Nếu WS đã
  đóng và đang chờ retry lúc unmount/đổi gate, timer cũ có thể mở WS trở lại.
- Split view hiển thị nhiều gate nhưng chỉ một AlertBanner subscribe activeGate.
  Event gate khác không vào banner/log/audio. Kiểm contract camera/gate thật;
  không phát OCR-only, chỉ phát issue confirmed được quyền.

Phải nghe thật sau ngắt WAN/cold browser, không lấy localService=true hoặc
unit test làm acceptance audio. Tín hiệu local/remote theo
[MDN localService](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService).

## P1 — D8 vẫn còn claims sai và giao diện quảng bá lỗi

Trong landing.html vẫn có:

- Dòng 132: “Không một phương tiện nào ... không được định danh chính xác.”
- Dòng 266/317: dưới **200 ms/Milligiây**, tương đương claim 0,2s chưa đo.
- Dòng 425: “huấn luyện trên hàng triệu khung hình thực tế tại cổng trường”.
- Dòng 477: “So khớp gương mặt học sinh qua ảnh thẻ ...” dù heading đã đổi.
- Tooltips dòng 715/749 vẫn có tên/lớp mẫu; đổi text nhìn thấy chưa sạch mọi attrs.
- Form dòng 845 chuyển mailto sang demo@school-gate-monitor.local chưa được
  xác nhận là liên hệ thật, không đủ bằng chứng CTA đặt lịch hoạt động.

Edge mở file local: không external HTTP request và không pageerror ở landing,
nhưng screenshot `qa_logs/task06_review/landing-desktop.png` cho thấy minh họa
camera co lại/chồng chữ. CSS offline có sẵn không có nghĩa mọi utility class
và layout đã được bảo toàn. Cần build đủ CSS và kiểm 320/390/desktop.

## P1 — nghiệm thu/slide đánh dấu vượt bằng chứng

- FINAL_ACCEPTANCE dòng 47 tick **“Video AI thật ... đạt”** bằng R14 decode-only.
  Đổi sang capture/decode EOF pass; AI runtime vẫn pending.
- RUN_LOCAL_OFFLINE dòng 3 ghi “đã được kiểm với WAN ngắt”, trái với matrix
  pending. Slide 8 ghi **“demo gate đạt”**, trong khi launcher fail, camera/
  audio/offline/rehearsal chưa đạt.
- Slide 4 gọi 152 test R là **full suite**; đó là subset. Full cũ 1.277 pass
  trước bản sửa không thay regression đúng code hiện tại.
- Slide 3 mô tả clip fallback đã có; clip chưa tồn tại. Slide 10/acceptance
  gọi CCT ONNX smoke pass, nhưng bằng chứng R6 được dẫn là hash/mock test;
  chưa tìm thấy run thật được dẫn để xác nhận claim đó.
- Video backup **chưa có MP4**, chỉ có README placeholder. Package chưa đủ
  deliverable theo contract; không đánh dấu cả package đạt.

Người dùng đã xác nhận có hai camera và loa. .env hiện có hai RTSP. Probe
ngắn OpenCV chưa mở được cả hai nguồn (0 frame); chỉ chứng minh chưa đọc
được tại lúc thử, không chứng minh thiếu phần cứng. Ghi “chưa kết nối/kiểm”
và kiểm lại nguồn/router/IP/RTSP, không nói người dùng không có camera.

## P1 — manifest không pin bản build và weights đang chạy

412 file được kiểm hash: **0 mismatch, 0 missing**. Nhưng **0 entry frontend/dist**,
**0 entry .pt/.onnx**. Script bỏ media/model/big files và không scan dist.
Do đó chưa pin weights thực, build được phục vụ hoặc audio fallback.
Pin path/hash của active weights/config/dist; không cần copy venv/kho model.
Manifest phải phản ánh đúng working tree còn dirty, không coi commit 13 file
là toàn bộ runtime đã freeze/reproduce.

## P2 — test debug và slide layout

Chạy mọi `test_r[0-9]*.py`: **152 pass, 1 skip, 1 fail**, 34,84s.
Lỗi ở `test_r4_debug.py:12`: mock owner.run trả string "FAKE", detector cần
object có names. Đây là lỗi fixture debug, chưa chứng minh detector production
lỗi. Sửa mock đúng contract hoặc xử lý script debug theo quy tắc repo và
chạy lại full suite; không im lặng loại khỏi report.

PPTX/PDF đều có 12 slide/page, 16:9; render đủ PPTX và PDF. Slide 9 PPTX có
title chồng status chip; PDF được dựng riêng bằng ReportLab, không phải xuất
từ chính PPTX đã render, nên kích thước/font/nội dung không hoàn toàn đồng
nhất. Dùng một nguồn nội dung đã kiểm và rà sau sửa. File notes có tồn tại,
nhưng hai lượt 180+420s chưa được tổng duyệt.

## Phần xác minh đạt

| Hạng mục | Kết quả review |
|---|---|
| Commit e396096 | Đúng 13 file, +4162/-2937 |
| Node helper audio | 8/8, exit 0; phạm vi helper |
| Frontend lint | exit 0, warnings; không gọi sạch warning |
| Frontend build | exit 0, 696 modules, 3,38s; output QA riêng |
| Release size | 601.909 bytes, khoảng 587,8 KiB; quota đạt |
| Manifest file hashes hiện có | 412 entry, 0 mismatch/0 missing |
| PPTX/PDF | File thật, 12 slide/page, đã render để review |
| Landing initial load local | Không external HTTP request/pageerror; layout còn lỗi |
| D/C lúc rà | D khoảng 53,17 GiB, C khoảng 6,97 GiB |
| VPS deployed | Chưa; giữ pending_access/pending_sync, không đè site khác |

## Việc tiếp theo

Dán [REPAIR_CURSOR_PROMPT.md](REPAIR_CURSOR_PROMPT.md) cho Cursor. Sửa P0 trước,
smoke có isolation, rồi camera/loa/WAN-off thật và tổng duyệt. Video backup
chỉ quay/chạy lại runtime thật, có nhãn nguồn; không dựng nhận diện giả từ
clip decode để bù acceptance. Giữ deadline trước 01:00, gate chưa đủ giữ mở.

Lưu ý lịch: 23:21 đến 01:00 là **99 phút**, không phải 39; 39 phút chỉ tới
00:00. Không dùng nhầm mốc freeze làm hạn bàn giao.
