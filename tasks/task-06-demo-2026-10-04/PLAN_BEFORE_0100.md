# Kế hoạch chốt demo và bàn giao trước 01:00 — 04/10/2026

Múi giờ: Asia/Bangkok (UTC+7). Hạn người dùng chốt: **trước 01:00 ngày 04/10**.
Thuyết trình 2–3 phút, demo 7 phút. Có laptop RTX 3050/4 GB, hai camera và loa.
VPS: `103.101.162.111`; SSH, hệ điều hành, tài nguyên và domain chưa được xác minh.
Demo phải chạy khi laptop/camera cùng router nhưng **WAN/Internet bị ngắt**.

**Đầu vào cho Cursor:** dán toàn bộ [NEXT_CURSOR_PROMPT.md](NEXT_CURSOR_PROMPT.md).
Checklist thực thi: [todo.md](todo.md). Slide và lời nói:
[SLIDES_CONTENT.md](SLIDES_CONTENT.md); demo: [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).
Mẫu ghi nghiệm thu: [ACCEPTANCE_TEMPLATE.md](ACCEPTANCE_TEMPLATE.md).
Đây là bộ kế hoạch và nội dung; PPTX/PDF/build/deploy chỉ đánh dấu hoàn thành
sau khi Cursor tạo artifact và kiểm theo checklist.

Đây là kế hoạch tiếp theo của `tasks/task-05/CURSOR_HANDOFF.md`, không thay
checklist lịch sử. Nếu Cursor đang làm prompt trước, chốt lát đang chạy rồi
đối chiếu trạng thái thật; không giả định R0–R15 đã xong. Plan này đổi thứ tự
ưu tiên và mở thêm VPS/trang quảng bá/slide theo yêu cầu mới.

## 1. Kết quả phải bàn giao

1. Bản local đã khóa commit/config/weights: hai camera, nhận diện biển, mũ,
   số người và tư thế/crossing; bằng chứng thiếu chuyển cần duyệt, cảnh báo có
   căn cứ và tiếng Việt nghe được ngay trên loa. Xe điện chỉ kết luận nếu có
   weights/mapping/bằng chứng đạt; chưa đủ thì unknown, không đoán từ COCO.
2. Luồng hoạt động không cần Internet: RTSP LAN, API/SQLite/JPEG, login/quyền,
   assets/model/audio local. VPS không nằm trên đường xử lý/cảnh báo tại cổng.
3. VPS có trang giới thiệu và, khi deploy/API/sync vượt kiểm tra, dashboard
   từ xa với thời điểm đồng bộ rõ. Đồng bộ lỗi không làm chậm local, không phát
   lại cảnh báo. Thiếu SSH/domain hoặc sync chưa đạt phải ghi đúng mục chưa xong.
4. Landing page đúng tính năng thực, responsive, liên kết hoạt động; không số
   liệu/quyền riêng tư tuyệt đối, nhận diện khuôn mặt hoặc form gửi giả.
5. PowerPoint12slide gồm8slide chính/180giây và4phụ lục, PDF dự phòng, speaker
   notes đầy đủ; video demo dự phòng, runbook7phút, tài liệu chạy/rollback và
   manifest artifact. Số đo trên slide lấy từ bản đã đóng băng.
6. Báo cáo nghiệm thu mã/test/video/camera/loa/offline/VPS riêng, lỗi quan sát
   được và giới hạn. Không dùng từ “hoàn tất production” nếu gate còn thiếu.

**Không có phép đo hữu hạn nào đảm bảo nhận diện tuyệt đối không sai.** Gate
demo yêu cầu không quan sát gán sai/cảnh báo sai trong bộ rehearsal được người
gán nhãn. KPI toàn chuỗi≥95%, coverage≥90%, holdout≥300lượt và ca12giờ của
đợt5 giữ nguyên; mẫu demo nhỏ hoặc ca30phút không thay thế các gate đó.
Trường hợp mơ hồ phải cần duyệt để không thông báo lỗi hay học sinh sai.

## 2. Điểm cần sửa đã xác minh trong mã ngày03/10

- `GuardPage.jsx` gọi `AlertBanner.jsx` cũ; component này đọc mọi payload bằng
  `buildSpeechText`, chưa nối `createAlertAudio`/`speakableIssues`, chưa kiểm
  `audio_authorized` và chưa xin audio lease. Helper có test đạt không chứng
  minh đường UI live đã dùng helper. Đây là P0 của buổi demo.
- `speak.js` chọn vi-VN nhưng không lọc `localService`. Giọng remote có thể mất
  khi không Internet; `frontend/index.html` còn fonts.googleapis.com.
- Landing hiện có “đối soát khuôn mặt”, “0.2giây”, “99.x%”, “100% tương thích”
  và form chỉ alert giả. README cũng có tiến độ/seed/deploy cũ. Phải sửa trước
  khi trình bày, không đem claim cũ lên slide.
- Full R0 mới có **1.214 pass/1 skip/0 fail** trong `regression-r0.xml`.
  Report mới hơn `regression-r8-r9.xml` có **1.277 pass/2 skip/0 fail**, khoảng
  443 giây. Thay đổi sau report này cần full tích hợp cuối.
  UI 9/9 mới kiểm điều hướng/API/ảnh/bbox;
  camera/audio chưa được nghiệm thu. R0 phải lấy trạng thái mới nhất.
- R3 chỉ đo decode hai file khoảng 74 FPS; R14 đọc 15 file đến EOF khoảng
  216 FPS, không nạp AI. Không dùng số đó chứng minh preview/AI runtime đạt.
- Test R6 dùng recognizer mock; hash/test adapter không chứng minh ONNX thật
  hoặc biển hai dòng nhận đúng. Smoke model thật và holdout vẫn cần kiểm.
- Package Ultralytics 8.4.168/CCT và ba notebook Kaggle đã có; weights vận hành
  chưa chuyển YOLO11. Bộ mũ trống, holdout độc lập chưa có. Notebook khác với
  training đã chạy. `pip check` còn dependency conflict, không nâng hàng loạt.
- D khoảng 53,2 GiB, C khoảng 6,1 GiB lúc rà 22:30; C từng báo thấp hơn nhiều.
  Đo lại trước mọi output. Backup reload đã sửa nhưng quota/restore media đầy
  đủ còn mở. Không copy kho media khi làm bản release/test.

## 3. Phân công và nguyên tắc chạy

- **Cursor A:** runtime/camera/ROI/crop/OCR/voting/luật/latency và backend event.
  Owner `pipeline.py`, detector, consensus, OCR, config và event API.
- **Cursor B:** audio UI/lease/offline assets, QA, VPS/sync riêng, landing,
  slide/runbook/release. Owner frontend/marketing/deploy/docs; backend event
  contract cần A chốt trước, không sửa đè `guard.py`/`pipeline.py`.
- Tối đa hai luồng sửa mã; một full regression hoặc benchmark GPU tại một thời
  điểm. Thu ground truth/đi thử/kiểm loa cần người vận hành xác nhận, không để
  agent tự gán nhãn từ output model. Laptop cắm nguồn, không sleep trong demo.
- Lát 20–40 phút tối nay, 3–5 file nguồn/lát; focused test → log → commit riêng.
  Chốt schema trước khi làm UI/sync. Mã chung có một owner và checkpoint rõ.
- Không xóa/ghi đè staging cũ, không `git add .`, không copy full DB/media.
  Mọi đổi model/config có baseline/rollback thực và source/hash được ghi.

## 4. Lịch thực hiện và mốc dừng

Lịch được điều chỉnh từ trạng thái khoảng 22:30 ngày 03/10, không coi các giờ
trước đó là công việc đã hoàn thành. Thời gian từng task ở mục 5 là ước lượng
cho lát đầy đủ; tối nay chỉ sửa khoảng trống sau khi đối chiếu phần đã có.
Không thể cộng toàn bộ task mới từ đầu rồi hứa đạt cùng hạn. Nếu bắt đầu muộn,
giảm phần thử nghiệm model/tính năng mới và giữ thời gian nghiệm thu/bàn giao;
gate chưa đạt giữ mở, không đổi nhãn để vừa giờ.

| Giờ UTC+7 | Cursor A | Cursor B | Checkpoint |
|---|---|---|---|
|Ngay nhận–22:45|Đối chiếu state/disk/process/camera/weights; nhận owner|Loa/voice offline, SSH read-only, xác định asset phụ thuộc WAN|D0, biết blocker thật và phần đã có|
|22:45–23:05|Hiệu chỉnh camera/ROI; sửa P0 voting/luật/epoch theo GT|Nối audio live/lease/dedup/clip local và bỏ asset WAN|**23:05 chốt model/reader**, giữ baseline nếu chưa đủ GT|
|23:05–23:25|Focused/full tích hợp và 15 clip AI runtime theo thứ tự|Kiểm browser/audio/2 viewer, landing và deploy nhẹ nếu đã sẵn|Một GPU benchmark/full suite; không lấy decode làm AI|
|23:25–23:55|Hai camera thật 30 phút, WAN-off/cold refresh/reconnect/loa|VPS/landing smoke, slide/PDF/video/runbook, ghi số đo thật|Không sai gán/sai audio quan sát được; quota/drift ổn|
|23:55–00:00|Chốt blocker/rollback và config/weights|Chốt UI/audio/asset và trạng thái VPS|**00:00 khóa code/config/weights**|
|00:00–00:30|Cold start bản freeze, hai lượt demo 7 phút|Trình chiếu 3 phút + nghe loa + kiểm fallback mỗi lượt|Không đổi kiến trúc/dependency/model|
|00:30–00:50|Rollback smoke/report cuối/stop process test|Đóng release/hash/PPTX/PDF/runbook và bàn giao|Package mở/chạy được, không lẫn dữ liệu vận hành|
|00:50–01:00|Đệm xử lý blocker bằng revert nhỏ|Giao file/URL/lệnh chạy và pending có bằng chứng|Bàn giao trước 01:00|

VPS access fail quá20phút: B hoàn tất bundle/deploy guide/landing local, ghi
pending_access, chuyển sang audio/slide. Không để SSH chặn local. Không ghi đã
deploy nếu chưa truy cập URL và health từ ngoài máy. Domain chưa có thì landing
static có thể trình bày bằng IP khi online; không đưa login/hồ sơ nhạy cảm qua
HTTP công khai. TLS/access của portal phải đạt trước khi dùng từ xa.

Sau 23:05: không đổi reader nếu chưa có bằng chứng tốt hơn. Sau 00:00: chỉ sửa
blocker bằng thay đổi nhỏ đã test/revert; giữ rehearsal và bàn giao. Train
YOLO11/Kaggle không nằm trên đường găng nếu chưa có dataset/artifact đạt.

## 5. Task theo lát có điều kiện hoàn thành

### D0 — Chốt trạng thái, dung lượng và build (A/B,20phút)

- Đọc task05/diff/staging/check process; không tin checkbox hoặc README cũ.
  Full pytest sau fixture cuối, build/lint và Node audio tests theo phần sửa;
  không chạy benchmark GPU song song. Venv/Torch hiện tại giữ nguyên.
- QA DB/media/backup/training riêng. Tắt maintenance/training/download tự động
  ở QA; kiểm mọi lazy entry point không tải model/mở RTSP vô ý.
- Preflight dự kiến output trên volume đích, D sau tác vụ≥30GiB; không ghi
  cache lớn lên C. QA≤1GiB/run/giữ3run, release≤600MiB, video dự phòng≤150MiB,
  PPTX/PDF+render≤100MiB, VPS media demo≤200MiB và log rotation.
- C dưới 5 GiB báo cảnh báo; dưới 3 GiB dừng tác vụ tạo cache/temp lớn, đặt
  output/cache tạm sang D sau khi kiểm quota. Không dọn AppData/Windows mù.
- **Đạt:** nguồn/role/config/model hash/disk rõ, test result có exit code;
  blocker được ghi, không thêm một bản media backup mỗi reload.

### D1 — Camera LAN và vùng đọc (A,30–45phút, sauD0)

- Xác nhận hai RTSP trực tiếp bằng IP LAN/user đã cấu hình; không cloud URL.
  Cố định/reserve IP, tắt client isolation cho mạng demo, chỉ cho app/firewall
  quyền LAN cần thiết. Không tắt toàn bộ firewall. Kiểm camera reboot khôngWAN.
- Chọn góc/vùng xe đi chậm có biển rõ; chỉnh focus/exposure/ánh sáng theo ảnh
  thật, tránh bóng/nhòe. ROI/vạch cổng tương ứng nguồn, crop từ native frame.
  Không tăng sharpen hoặc scale ảnh để suy ra ký tự đã mất.
- File EOF khác mất mạng, reconnect/đổi nguồn không phát frame/plate/alert cũ;
  reset tracker camera/epoch riêng, capture/preview vẫn tiến khi AI chậm.
- **Đạt:** mỗi camera có frame mới; checkpoint reboot/reconnect/LAN pass,
  source metadata che mật khẩu; không gọi video quay sẵn là camera live.

### D2 — Biển số đúng trước khi tự chốt (A,45phút, sauD1)

- Nhờ người duyệt30–50lượt từ các nguồn demo, gồm rõ, hai dòng, mờ/che,
  nghiêng, sát nhau, whitelist gần giống và không đăng ký. Nhãn lưu trước
  so model, chia theo encounter, không dùng dự đoán làm GT hoặc chỉ chọn ca đẹp.
- Smoke CCT ONNX/YAML thật, RGB/shape/return/char confidence và hai dòng;
  EasyOCR/CCT so cùng crop/GT, exact string/false accept/coverage/latency.
  Kết quả global model chưa đủ tốt thì giữ baseline. Không chạy cả hai engine
  đồng thời trong vận hành để “cứu” từng frame.
- ≤5crop khác frame/2giây; ≥2frame độc lập đồng thuận, không có đối chứng mạnh.
  Retry/variant không thêm phiếu; raw/conf/hash/camera/track/epoch đi xuyên
  consensus. Biển thiếu/mâu thuẫn cần duyệt; validator/whitelist không sửa chữ.
- **Đạt:** demo holdout không quan sát gán sai; báo mọi mẫu bỏ sót/review và
  số mẫu thật. Không đủ chất lượng thì khóa tự gán học sinh, giữ đề xuất/review
  cùng luật đã xác nhận; không hạ ngưỡng hoặc nhập sẵn đáp án để fake ALPR.

### D3 — Luật và một sự kiện/lượt (A,30phút, sauD1/D2)

- Mũ quan sát đúng vùng đầu; người cùng xe; riding/dắt xe đúng vạch. Chân/mũ
  khuất là unknown. Một encounter nhiều issue, late result cập nhật cùng event.
- Front cảnh báo lỗi đã đủ bằng chứng mà không đợi rear/cloud; thời gian chờ
  plate tối đa config hiện có≤200ms tại crossing. Plate đến muộn bổ sung im lặng.
  Thiếu OCR khác lỗi kỹ thuật; unreadable chỉ nhắc kiểm tra, không kỷ luật tự động.
- Auto-match trước/sau tắt nếu chưa có cặp lượt hiệu chỉnh; xe điện chưa đạt
  mapping/weights thì unknown. Không gán nhầm biển từ xe bên cạnh.
- **Đạt:** đúng loại lỗi trên positive/negative/occluded cases có GT, không
  duplicate event/audio, không báo riding cho người đi bộ/dắt xe.

### D4 — Nối audio vào UI thực (B,45phút, contract event từA)

- Thay nhánh legacy trong AlertBanner bằng helper đã test; kiểm finalized,
  confirmed issues, evidence persisted, audio_authorized, TTL và dedup encounter.
  Sử dụng client_id/lease của API thật; heartbeat/release/camera change đúng.
  Split view nhận cả hai camera nhưng chỉ một loa được quyền phát mỗi lượt.
- Một beep ngắn, một câu lỗi ngắn; mũ+riding đọc “Không đội mũ, vui lòng dắt xe”.
  Không phát technical diagnostic, pending/unconfirmed hay replay; không đọc
  student/biển chưa CONFIRMED, không dùng plate_matched để sửa biển OCR yếu.
- Bật loa bằng thao tác người dùng; tái sử dụng AudioContext, resume/cleanup
  khi đổi trang; speech callbacks onstart/onend/onerror để biết âm thanh thực.
  Queue nhỏ/TTL không đọc lỗi cũ; không gọi cancel mỗi sự kiện làm cắt mọi câu.
- **Đạt:**2viewer chỉ1loa, reconnect không đọc lại, nhiều issue cùng lượt đọc
  đủ một lần,20lần rehearsal nghe đúng lỗi và UI báo rõ nếu loa chưa sẵn sàng.
- File: AlertBanner, GuardPage, alertAudio, speak, testaudio; backend lease doA
  sở hữu, B không sửa đè. Gate transport chứ không chỉ helper unit test.

### D5 — Tiếng Việt offline và đo thời điểm nghe (B,20–30phút, sauD4)

- Kiểm `getVoices()`/voiceschanged, chọn vi-VN **localService=true** và nghe
  khi WAN tắt. localService là tín hiệu cấu hình, không thay nghe cold-start thật.
- Không có giọng Việt offline: chuẩn bị trước clip local câu lỗi (mũ, dắt xe,
  số người, đăng ký, biển chưa rõ) và câu kết hợp thường gặp. Có thể tạo/thu
  generic voice khi còn mạng rồi lưu local; không gửi dữ liệu học sinh/biển thật
  cho cloud TTS. Manifest/hash/preload audio, không gọi TTS cloud khi vận hành.
- Đường audio fallback là tự động từ confirmed issues, không nút phát để giả
  làm nhận diện. Nếu không có voice đọc biển offline, đọc lỗi chung và hiển thị
  biển đã xác nhận trên màn hình; ghi đúng phạm vi audio, không nói đã đọc biển.
- **Mục tiêu cần đo:** banner/beep p95≤700ms từ confirmed issue; speech onstart
  p95≤1,2s; plate p95≤2s từ vùng đọc. Ghi thời điểm input/confirm/persist/WS/
  beep/onstart và sample count, không chỉ log “speech_requested”.
- **Đạt:**không lặp/nhầm/đọc muộn stale event; câu nghe được trên loa thật lúc
  WAN tắt. Nếu chưa đạt latency, sửa bottleneck/queue thay vì tăng rate khó nghe.
- Giọng local/remote theo [MDN localService](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService);
  [AudioContext.resume](https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/resume)
  và [getVoices](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices)
  cần kiểm trong browser dùng demo.

### D6 — Build chạy offline và điều khiển một chạm (B,20phút)

- Production build local, một backend process, không --reload; phục vụ React,
  CSS/icons/fonts/audio cùng origin. Bỏ dependency CDN/font online hoặc dùng
  system font. Không service-worker caching vội nếu local static đã đủ.
- Launcher có start/stop/restart/status/rollback và đường dẫn venv rõ; không
  cài/download khi demo. Health phải read-only, không khởi tạo model lần nữa.
  Token/secret local, login cold-start LAN, reboot ngày giờ đúng; không log token.
- **Đạt:**mở browser/profile mới với WAN tắt, login/2preview/quyền/media/
  banner/audio/evidence vẫn hoạt động; không dùng cache cũ để che dependencyWAN.

### D7 — Nghiệm thu runtime và lỗi mong đợi (A/B,40phút)

- Video đủ15clip tới EOF thời gian thực trên runtime thật; hai clip độc lập
  chỉ đo hai nguồn, không chứng minh ghép. Reporter bounded không xuất overlay
  full mỗi frame. Camera thật30phút,1/2/3viewer, theo dõi drift/queue/drop/disk.
- Nguồn file cần pacing theo FPS, nạp detector/OCR runtime thật; không decode
  hết file trước khi AI xử lý hoặc dùng flag QA tắt CV rồi gọi nghiệm thu AI.
- Matrix người duyệt: compliant; mũ; riding; số người; nhiều lỗi; biển lạ đã
  chốt; biển yếu/che; đi bộ/dắt xe; hai xe sát; reconnect; đổi nguồn; mấtWAN;
  reload; expired lease; late issue; IO fail. Mỗi ca lưu expected/observed,
  trạng thái review, text/audio heard, timestamp/encounter/hash và pass/fail.
- Preview mục tiêu≥15FPS/camera, AI≥5FPS/camera, tổngGPU≈3,2GiB. Báo số đo
  dù không đạt, không fake FPS bằng đếm viewer gửi lại JPEG cũ.
- **Đạt:**không gán sai/cảnh báo sai/đọc lặp trong rehearsal có nhãn; không
  crash, disk ổn định. Camera12giờ chỉ ghi hoàn tất sau đủ12giờ và log; quá
  hạn trước01:00 thì giữ pending endurance, không gộp30phút thành12giờ.

### D8 — Trang giới thiệu đúng và dùng được offline (B,30phút)

- Tái dùng branding/navy và landing hiện có, không redesign toàn frontend.
  Bỏ face matching/99.x%/0.2s/100% claims chưa đo; thông tin hiệu năng phải có
  run/hash/date/sample count hoặc ghi “mục tiêu”. Form không có backend đổi
  thành link liên hệ thật do người dùng cung cấp/CTA xem demo, không alert đã gửi.
- Mô tả chính xác hai camera, localGPU/offlineLAN, lỗi có bằng chứng/cần duyệt,
  admin/quyền/nhật ký; xe điện/YOLO11/sync theo trạng thái thực. Public chỉ ảnh
  minh họa hoặc fixture đã ghi nguồn, không tên/mặt/hồ sơ trẻ và credentials.
- Assets local,320px/desktop,CTA/link/QR/font có fallback; bản offline xuất riêng
  dùng cùng nguồn bundle. Landing local chạy khiWAN tắt; bản VPS chỉ khionline.
- **Đạt:**nội dung khớp release, không claims sai/form giả, browser không lỗi,
  tương tác hoạt động; README tiến độ/run được cập nhật từ báo cáo cuối.

### D9 — VPS và đồng bộ không ảnh hưởng local (B, tối đa60phút)

- SSH read-only xác minh hostOS/resource/free disk/service/ports/site hiện có
  qua cấu hình sẵn; không reimage, đổi mật khẩu, chép đè dịch vụ khác hoặc đưa
  secret vào repo/chat. Host chưa đủ quyền thì pending_access đúng nghĩa.
- Deploy release static mới vào thư mục riêng, health/version/rollback; chỉ
  light API/SQLite nếu cần, requirements riêng không Torch/YOLO/OCR trên VPS.
  TLS/domain/login/quyền phải kiểm trước public portal. Không dùng VPS1GB giả
  định từ README để chọn cấu hình; lấy resource thật trước install.
- Nếu sync đã có thì hoàn thiện; chưa có thì lát riêng: edge outbox bounded,
  timeout/backoff; upsert idempotent `(site/edge,encounter,event_version)`, token
  scoped ingest, không client tự bịa quyền/học sinh. VPS dashboard read-only
  ghi source/last_synced/offline; sync không sửa GT/evidence hoặc phát audio.
  Raw video/model không upload; media chọn lọc có quota/auth, không publicDB.
- Test gửi lặp/cũ/out-of-order/mấtWAN/restoreWAN, chỉ1event mới nhất; laptop
  inference/audio không chờ HTTP. Failed sync giữ local và queue hữu hạn.
- Nếu sync chưa vượt tests trước23:20: deploy landing + report snapshot có nhãn
  thời điểm, không gọi dashboard realtime/đã đồng bộ; ghi sync pending riêng.
  Bàn giao deploy bundle/runbook/rollback vẫn phải đủ, không bỏ VPS khỏi checklist.
- **Đạt khi đánh dấu deployed:**URL/health/build hash từ ngoài máy, restart,
  rollback, permissions và trạng thái thực đã kiểm. Chưa đạt không ghi complete.
- Nếu proxy WS thật, cấu hình theo [Nginx WebSocket](https://nginx.org/en/docs/http/websocket.html).

### D10 — Slide3phút + demo7phút + video dự phòng (B)

- Dùng `SLIDES_CONTENT.md`:12slide16:9,8slide chính≤180giây,4appendix chỉQ&A;
  speaker notes tiếng Việt. Xuất PPTX chỉnh sửa được +PDF, mở/rà mọi slide,
  font Việt, ảnh không méo/che chữ, sources và trạng thái verified/target rõ.
- Bộ3phút chỉ nêu bài toán, workflow, nhận diện/bằng chứng, offline/audio,
  giao diện, kiến trúcVPS, kết quả/giới hạn và chuyển demo. Không thuyết trình
  10phút rồi cộng demo. `DEMO_RUNBOOK.md` phân phút đủ420giây và role thao tác.
- Video dự phòng quay bản chạy thật có tiếng, privacy/demo fixture,≤150MiB;
  label “video ghi trước”. Slide không chèn số % từ confidence model làm accuracy.
- **Đạt:**diễn tập presentation+demo2lượt≤10phút; mọi file mở offline, link/QR
  không sai; bản PPTX hiện tại trướcfreeze phải được cập nhật sau báo cáo cuối.

### D11 — Khóa release và bàn giao (A/B,00:00–00:50)

- Release manifest chứa commit + trạng thái dirty nếu còn, env template không
  secret, model/config/audio/slide/demo hash, dependency/version, lệnh start,
  IP mapping LAN che password, gateROI và profile, chức năng/flag đang bật.
- Backup SQLite online và config hiện hành; không copy media vì user đã có
  backups. Kiểm restore/rollback thực trong thư mục test nhỏ, giữ≥2bộ verified;
  full media restore chưa làm ghi pending riêng. Bản rollback không tự nâng
  package/downloadmodel. Không xóa dữ liệu mới khi quay lại mã/cấu hình cũ.
- `FINAL_ACCEPTANCE.md` ghi matrix/lệnh/exitcode/GT/n/metrics/âm thanh nghe/
  WANoffcoldstart/VPSURL cùng các mục pending. Các bản demo accounts/fixtures
  dùng namespace/DB riêng, không sửa thông tin học sinh để diễn kết quả.
- Dùng `ACCEPTANCE_TEMPLATE.md` để báo đúng phạm vi; đo latency với cùng
  đồng hồ hoặc đã hiệu chỉnh server/browser, không trừ hai timestamp lệch giờ.
- Chốt launcher+runbook ngắn, port/process đúng, backup plan nếu một camera
  offline, tiếng Việt lỗi, quyền admin/security và lời trả lờiQ&A có giới hạn.
- **Đạt:**bản freeze cold-start/rollback pass, release≤600MiB, D≥30GiB,
  bàn giao trước01:00. Không đóng dự án production nếu acceptance dài hạn còn mở.

## 6. Gate quyết định, không đổi sau khi test thất bại

| Gate | Điều kiện | Nếu chưa đạt |
|---|---|---|
|23:05 model|Challenger có GT tốt hơn/không giảmcoverage, latency/VRAM ổn|Giữ baseline đã kiểm, không đổi sangYOLO11/CCT vì tên mới|
|23:20 logic/audio|GT không sai gán/báo lỗi; audio hợp quyền/chỉconfirmed|Sửa blocker hoặc rollback; chức năng mơ hồ chuyểnreview|
|00:00 freeze|2camera+loa+offlineLAN+evidence+build/test đạt|Không thêmfeature, ưu tiên bản đã kiểm vàfallback thật|
|00:30 rehearsal|2lượt10phút, coldstart/WANoff/loa nghe rõ|Sửa launcher/loa nhỏ, chuẩn bịvideo có nhãn, báo blocker|
|00:50 handoff|Package/slide/PDF/runbook/hash/acceptance/URLstatus đủ|Không tuyên bố mục chưa làm đã hoàn tất|

“Không báo sai” không được đạt bằng tắt tất cả cảnh báo hoặc review mọi lượt;
coverage/recall/unknown và mẫu bị bỏ qua phải báo cùng số lỗi. Video fallback
không thay bằng chứng camera thật; mock API không thay test nhận diện.

## 7. File bàn giao phải có khi Cursor kết thúc

```text
release/demo-2026-10-04/
  RELEASE_MANIFEST.json
  START_DEMO.ps1 / STOP_DEMO.ps1 / ROLLBACK_DEMO.ps1
  env.example
  FINAL_ACCEPTANCE.md
  RUN_LOCAL_OFFLINE.md
  DEPLOY_VPS.md
  VPS_STATUS.md
  marketing/ (HTML/CSS/assets local)
  School_Gate_Monitor_Demo.pptx
  School_Gate_Monitor_Demo.pdf
  SPEAKER_NOTES.md
  DEMO_RUNBOOK.md
  DEMO_BACKUP.mp4
```

Không gói venv/node_modules/.git/operationalDB/media/backups/dataset đầy đủ;
weights đã có trên laptop được pin đường dẫn+hash, model cần copy chỉ một bản
trong quota. Code deploy VPS dùng requirements nhẹ; full local install guide
không tự train/download lúcdemo. Dữ liệu nhập riêng có version/restore rules.

Khi đủ các gate demo, dùng trạng thái **demo_ready** với acceptance. Chỉ dùng
**production_complete** nếu R0–R15/KPI300lượt/12giờ và các mục VPS/sync/restore
thật cũng đạt. Bàn giao phần còn mở có owner/evidence, không giấu trongTODO.
