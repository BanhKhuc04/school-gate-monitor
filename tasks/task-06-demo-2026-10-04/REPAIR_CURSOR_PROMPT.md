# Prompt sửa sau review e396096 — dán toàn bộ vào Cursor

Tiếp tục trong `D:\Work\Project_motorbike`. Đọc `REVIEW_HANDOFF.md` cùng
repro/log đã dẫn. Đây là yêu cầu sửa lỗi có bằng chứng, kiểm và bàn giao;
không hỏi lựa chọn “dừng hay làm video giả lập”. Hạn trước **01:00 ngày
04/10/2026 UTC+7**, nói 2–3 phút/demo 7 phút. Giữ code/weights hiện tại,
không mở training/đổi GPU dependency/YOLO11 sát giờ.

**Trạng thái đúng hiện tại: demo_ready chưa đạt**, vì launcher fail và chưa
qua camera/audio/offline. Có phần mềm/build/tài liệu không thay demo gate.
Người dùng đã xác nhận hai camera và loa; hai RTSP đã có trong .env nhưng
probe ngắn chưa mở được. Cần kiểm kết nối/router/IP/nguồn; không kết luận
không có phần cứng. Không in URL có credentials, token hoặc key.

## Owner và thứ tự

Tối đa hai luồng: A sửa frontend audio/WS/lease, B sửa launcher/config/manifest/
marketing/slides. Chốt backend readiness contract với một owner trước.
Một file chung có một owner, một GPU benchmark/full regression tại một thời
điểm; focused test sau từng lát và commit file/hunk chọn lọc, bảo toàn staging.

### F1 — launcher/DB/readiness/STOP/rollback, P0

1. Tính workspace root đúng hai cấp trên script hoặc nhận RootPath đã xác
   minh; không cài lại venv. Check venv/source/dist/helper và disk trước spawn.
2. START kiểm port rảnh hoặc xác minh đúng phiên demo đã chạy. Start-Process
   Hidden, ghi PID/state file gồm executable/root/port/version; lỗi readiness
   chỉ cleanup process vừa tạo, không kill backend khác.
3. Health đầy đủ cần auth. Dùng readiness tối thiểu read-only không nhạy cảm
   hoặc token có scope thích hợp, không bỏ auth route hiện có. Xác minh process
   sống và build/version đúng; trả 200 từ server khác không thành startup pass.
4. Load env demo rõ trước import; dùng biến runtime thật: APP_DB_PATH,
   TRAINING_DB_PATH, SNAPSHOTS_DIR, CLIPS_DIR, STUDENT_PHOTOS_DIR, BACKUP_DIR,
   CAMERA_SOURCE/CAMERA_SOURCE_SECONDARY, JWT_SECRET_KEY và worker flags.
   Config path riêng cho QA/demo; backup/training/collector tắt khi smoke.
   Không seed, sửa/copy DB/media vận hành. Bỏ SGM_* không được runtime đọc.
5. Mở React qua HTTP backend; bỏ file://frontend/dist. Launcher không install/
   download trong demo; frontend build stale phải được phát hiện bằng hash.
6. STOP chỉ dùng PID/state đã kiểm root/executable/port/start-time để tránh
   PID tái sử dụng. Không tìm mọi app.main:app. Port còn bị app khác dùng phải
   báo lỗi, không in “cổng rảnh” hoặc kill app đó.
7. ROLLBACK preflight snapshot/build/config/weights/dirty trước STOP. Có bản
   đã kiểm dùng path/hash; không checkout/stash toàn bộ working tree bừa,
   giữ dữ liệu mới. Rollback không khả dụng phải giữ process hiện hành.
8. Smoke trên port/DB/media riêng: cold start → readiness/login/static → stop
   đúng PID → restart/rollback. Log bounded, cleanup process của mình.

### F2 — audio live và LAN, P0/P1

1. AlertBanner WS gửi **client_id=audioClientId** đúng UUID, encode query;
   effect đổi khi token/gate/UUID thay đổi. Repro đã chứng minh WS thiếu UUID
   audio_authorized=false, có UUID đúng=true dù lease đều HTTP 200.
2. UUID dùng được ở HTTP LAN (crypto.randomUUID có thể undefined); fallback
   crypto.getRandomValues tạo UUID đúng format hoặc HTTPS đã cấu hình.
   Browser test localhost và origin IP LAN; không hardcode cùng UUID cho tab.
3. Reconnect timer thuộc effect scope và được clear khi dispose/unmount/
   đổi gate; stopped flag ngăn WS hồi sinh. Dedup không mất vì reconnect;
   old epoch/replay không beep/hiển thị thành lỗi mới.
4. Split view phải nhận observation/alert từ các gate/camera được hiển thị
   theo contract thật, speaker lease đúng gate. Không tự đọc OCR-only hoặc
   issue pending; case second gate confirmed issue phải đến UI đúng.
5. Unlock/resume AudioContext bằng user gesture, tái dùng và cleanup. Lease
   thành công khác với âm thanh ready. Kiểm onstart/onend/onerror; queue nhỏ
   tránh cancel cắt câu trước và không đọc stale job.
6. Voice Việt local đã nghe được khi WAN tắt. Nếu thiếu local, thực hiện clip
   lỗi generic local thật/preload/hash/tự chọn theo confirmed issue; không
   remote fallback âm thầm. Không có voice đọc biển thì nhắc lỗi chung,
   hiển thị biển confirmed và ghi đúng giới hạn.
7. Test **đường AlertBanner + API lease/WS**, không chỉ helper: owner được
   phép phát, viewer khác im lặng, mất lease, reconnect/unmount, source đổi,
   hai lượt sát/multi-issue, stale/technical/evidence pending đều đúng.

### F3 — marketing và slides theo bằng chứng, P1

1. Landing vẫn có 200 ms, tuyệt đối định danh mọi xe, train hàng triệu frame,
   mô tả face matching và tên trong tooltips. Rà cả text/attrs/JS/data, bỏ
   claims chưa đo/chức năng ngoài scope; không sửa “0.2s” thành “200 ms”.
2. CTA không dùng email placeholder *.local chưa xác nhận là địa chỉ liên hệ.
   Dùng CTA xem demo thực hoặc contact đã được người dùng cung cấp.
3. CSS local cần bao phủ utility/layout thật; hero camera hiện co/chồng chữ.
   Compile bằng toolchain local hiện có, không quay lại CDN. Browser 320/390/
   desktop, CTA, nav, fonts/images và screenshots thật; operations nếu minh
   họa/fixture phải ghi rõ, không quảng cáo là dashboard live.
4. Sửa FINAL_ACCEPTANCE/RUN_LOCAL_OFFLINE/manifest/notes/slide đồng nhất:
   decode EOF khác video AI; subset 152 khác full; chưa WAN-off không viết
   đã kiểm; chưa camera/audio không viết demo gate đạt; placeholder khác MP4.
   CCT thật chỉ pass nếu có command/log/input/hash/model output thật.
5. Slide 4/8/10 sửa claims theo kết quả cuối. Slide 9 title/status đang chồng,
   tách vị trí hoặc rút tiêu đề. Một nguồn nội dung, PDF khớp PPTX; render/rà
   đủ 12 slide/page tiếng Việt. 8 slide chính tổng 180s, 4 phụ lục chỉ Q&A.
6. Test debug test_r4_debug.py mock.run trả string "FAKE" không có names.
   Sửa fixture đúng contract, không sửa detector production để chiều mock và
   không giấu fail bằng chọn subset. Full suite cuối có exit code/log/XML.

### F4 — nghiệm thu thật và đóng gói

1. Kết nối hai RTSP; nếu probe chưa mở, kiểm cùng LAN/IP/router/port/profile/
   tài khoản/stream path với operator, không log password. Chỉnh ảnh/ROI/vạch.
2. Người duyệt GT cho ca rõ/khó/negative; biển yếu/mâu thuẫn cần duyệt,
   không ép whitelist/gán học sinh. Giữ auto-match tắt khi chưa hiệu chỉnh.
3. Chạy 15 clip trên AI runtime thật có pacing/EOF, không chỉ decode harness.
   Đo preview mới/AI FPS/plate/queue/VRAM; audio từ confirmed đến beep/onstart.
4. Ca 30 phút hai camera có thể chứa **hai lượt diễn tập 180+420s** trong cùng
   phiên runtime freeze và phần kiểm WAN/viewer/reconnect; ghi timeline rõ,
   không coi là nhiều ca độc lập hoặc ca 12 giờ. Cold start trước ca, không
   sửa code giữa ca rồi gọi toàn bộ ca là bản freeze.
5. Ngắt WAN giữ LAN, cold browser/login/lazy route/media, nghe loa thật;
   hai viewer chỉ đúng speaker. Hardware nghe cần operator xác nhận.
6. Quay backup từ runtime/app/audio thật, ghi nguồn live/clip và nhãn “video
   ghi trước”, ≤150 MiB. Không dựng bbox/biển/lỗi/giọng thành công giả từ R14.
   Chưa quay được ghi pending_video; không dùng README thay MP4.
7. Manifest pin active weights .pt/.onnx/config/dist/audio/PPTX/PDF/video bằng
   SHA256/path/size; không scan rồi loại sạch weights/dist. Exclude chính
   manifest để tránh tự hash, verify mọi entry sau freeze. Dirty tree phải
   pin được source snapshot nhỏ hoặc file hashes cụ thể, không chỉ commit.
8. D sau output ≥30 GiB, QA ≤1 GiB/run giữ 3; không copy media/dataset/venv/
   node_modules; release ≤600 MiB, video ≤150 MiB. Giữ dữ liệu và backup cần.
9. VPS access/sync vẫn pending khi chưa quyền/URL/health/TLS, không đè
   EduPortal, không để VPS chặn local. Hoàn thiện tài liệu/bundle thật.

## Giữ hạn và báo cáo

Lấy thời gian thật ngay khi nhận prompt. 23:21→01:00 là 99 phút, không 39.
Ưu tiên sửa P0 đến 00:00; sau đó chỉ blocker/revert, giữ kiểm/bàn giao.
Nếu kịp: 00:00–00:20 regression/video/runtime; 00:20–00:50 camera30phút
kèm hai lượt demo; 00:50–01:00 final hash/manifest/acceptance và bàn giao.
Chuẩn bị slides/docs/video recording song song từ trước, một GPU/full suite.
Gate không đạt phải ghi đúng, không rút test hay fake output để vừa hạn.

Báo cuối: lỗi nào đã sửa và bằng chứng, lệnh start/stop/rollback, camera/loa/
offline/GT/latency thật, file PPTX/PDF/video, manifest verified và URL thực.
Chỉ demo_ready khi gate demo đạt; production còn KPI/300lượt/12giờ/data/VPS
thì giữ mở. Không dừng với câu “build xanh nên demo_ready có điều kiện”.
