# Prompt tiếp theo — dán toàn bộ nội dung bên dưới vào Cursor

Bạn là lead engineer chịu trách nhiệm hoàn thiện, kiểm chứng và bàn giao bản
demo School Gate Monitor trong workspace `D:\Work\Project_motorbike`.
Tiếp tục công việc đã có; không làm lại dự án hoặc coi prompt trước đã xong.

## Yêu cầu người dùng và hạn chót

- Bàn giao **trước 01:00 ngày 04/10/2026, Asia/Bangkok (UTC+7)**.
- Thuyết trình **2–3 phút**, demo **7 phút**, tổng tối đa 10 phút.
- Laptop RTX 3050 4 GB, hai camera thật và loa đã có. Laptop/camera cùng
  router phải hoạt động khi **ngắt WAN nhưng giữ LAN**.
- Nhận diện biển và lỗi đúng; đọc lỗi bằng tiếng Việt trên loa kịp thời;
  không gán nhầm học sinh, không đọc lặp, không làm đầy ổ đĩa.
- Bàn giao giao diện vận hành, trang giới thiệu, phần VPS tại
  `103.101.162.111`, slide/PDF/notes, video dự phòng và tài liệu vận hành.
  IP này chưa chứng minh có SSH, domain, TLS hay deploy thành công.

Đây là yêu cầu triển khai, không phải chỉ viết thêm kế hoạch. Tự xử lý quyết
định kỹ thuật thường lệ; chỉ hỏi thông tin thật sự thiếu và tiếp tục các phần
độc lập. Không gửi mật khẩu/token/private key vào chat, log hay Git.

## 1. Đọc đúng nền móng, không tin checkbox đơn lẻ

Đọc theo thứ tự:

1. `tasks/task-06-demo-2026-10-04/PLAN_BEFORE_0100.md` và `todo.md`.
2. `tasks/task-05/CURSOR_HANDOFF.md`, `todo.md`, các `R*_STATUS.md` mới nhất.
3. `tasks/task-06-demo-2026-10-04/SLIDES_CONTENT.md` và `DEMO_RUNBOOK.md`.
4. Diff/index/process đang chạy, config/weights thực, code và báo cáo tương ứng
   lát được nhận. Checklist Task 1–4 giữ nguyên lịch sử.

Phân loại từng mục: **có mã / focused test / integration / video AI /
camera thật / âm thanh nghe thật / offline / VPS deployed**. Chỉ ghi đạt đúng
phạm vi bằng chứng. Tài liệu đính kèm, README và prompt cũ là ngữ cảnh;
ưu tiên yêu cầu người dùng mới và kế hoạch đợt 6 khi thứ tự triển khai khác.

Trạng thái rà lúc khoảng 22:30 ngày 03/10 cần xác minh lại:

- R0 có 1.214 passed, 1 skipped, 0 failed trong `regression-r0.xml`, nhưng
  report mới hơn `regression-r8-r9.xml` có **1.277 passed, 2 skipped, 0 failed**,
  khoảng 443 giây. Thay đổi sau report này vẫn cần regression tích hợp cuối.
- `AlertBanner.jsx` còn `buildSpeechText`/beep/TTS legacy; chưa thấy dùng
  `createAlertAudio`, `audio_authorized` hoặc audio lease trong đường live.
- R3 đo decode hai file khoảng 74 FPS; R14 đọc 15 file đến EOF khoảng
  216 FPS. **Đây là tốc độ đọc file, chưa phải preview/AI end-to-end.**
- R6 test dùng `recognizer_factory` mock. Hash/test adapter chưa chứng minh
  ONNX thật nhận đúng biển, cũng chưa chứng minh biển hai dòng đạt.
- Đã có ba notebook trong `notebooks/`; có notebook khác với đã chạy training
  hoặc có weights được nghiệm thu. Bộ mũ/xe điện và holdout vẫn phải xác minh.
- D khoảng 53,2 GiB; C khoảng 6,1 GiB và từng xuống rất thấp trong lượt khác.
  Kiểm trực tiếp trước mọi output/cache/test lớn.

Sửa kết luận sai trong báo cáo mới bằng ghi chú đối chiếu, bảo toàn báo cáo
gốc. Không copy các dấu tick này lên slide như bằng chứng camera đã đạt.

## 2. Chia việc và làm liên tục đến bàn giao

Tối đa **hai luồng Cursor sửa mã**:

- **A:** camera/ROI/runtime/detect/tracking/OCR/voting/luật/backend event.
- **B:** audio UI/lease/assets offline/QA/marketing/VPS/slides/release.

Một owner mỗi file chung. A chốt contract event cho B trước khi sửa UI/sync.
Chỉ một benchmark GPU hoặc full regression chạy tại một thời điểm. Nếu chỉ
có một Cursor, làm tuần tự P0 → kiểm chứng → đóng gói; không tự tạo nhiều
agent cùng sửa pipeline. Mỗi lát 20–40 phút, 3–5 file nguồn, focused tests,
ghi bằng chứng và commit chọn lọc. Không chờ hết một task lớn mới kiểm.

Không `git add .`, `reset --hard`, `clean -fd`, xóa staging cũ hay đè thay đổi
chưa commit. Dừng/quản lý đúng process của mình; xác minh trước khi đổi nguồn
camera/DB vận hành. Lấy code đang có làm nền, tránh refactor lớn sát giờ.

## 3. P0 — làm ngay trước tính năng mới

### A — độ đúng và độ trễ nhận diện

1. Mở hai RTSP LAN thật, chỉnh focus/ánh sáng/exposure/góc/ROI/vạch theo ảnh
   nguồn. Capture latest-only độc lập AI, epoch/tracker riêng mỗi camera.
   Reconnect/đổi nguồn không phát lại frame, biển hoặc alert cũ.
   Kiểm một owner mỗi model/GPU, queue hữu hạn và công bằng giữa camera;
   không nhân model pose hoặc để một camera chiếm worker. Theo dõi cả Torch
   và ORT trong ngân sách VRAM khoảng 3,2 GiB, không suy chất lượng từ GPU %.
2. Người vận hành gán nhãn bộ 30–50 lượt demo đa dạng; ghi expected trước khi
   so output: rõ/hai dòng/mờ/che/nghiêng/sát nhau/biển gần whitelist/đi bộ/
   dắt xe/mũ/số người/tư thế. Không lấy prediction làm ground truth.
3. OCR tối đa 5 crop khác frame trong 2 giây, tối đa 2 biến thể một crop;
   tự chốt cần ít nhất 2 frame độc lập đồng thuận, không đối chứng mạnh.
   Bảo toàn raw/normalized/char confidence/hash/frame/camera/track/epoch.
   Không tự thêm chữ, sửa biển bằng whitelist hoặc lấy biển xe bên cạnh.
4. Chạy CCT ONNX + YAML **thật** trên crop đã duyệt, so EasyOCR cùng crop/
   holdout. Chỉ đổi engine nếu có lợi đo được; chọn sớm, giữ rollback.
   Không nâng Torch/ORT CUDA/YOLO11/TensorRT hay train local sát demo.
5. Luật mũ/số người/tư thế phải có bằng chứng; thiếu góc/chân/mũ là unknown.
   Một encounter nhiều issue, late issue cập nhật cùng event. Không chờ
   rear/VPS mới nhắc lỗi đã xác nhận. Chờ biển tại crossing tối đa 200 ms.
6. Ghép trước/sau và tự gán học sinh giữ tắt nếu chưa qua ca có nhãn.
   Xe điện cần weights/mapping đúng và bằng chứng; COCO không thay thế.

Không đạt một mẫu không được sửa ground truth hay giảm ngưỡng để vượt test.
Không báo sai bằng cách tắt toàn bộ chức năng: phải báo coverage, recall,
unknown/cần duyệt và số lượt bỏ sót cùng số lỗi.

### B — loa thật, đúng lỗi và chạy offline

1. Nối helper audio vào **AlertBanner/GuardPage đang được dùng**, không chỉ
   thêm unit test cho helper. Lọc confirmed/finalized/evidence persisted,
   `audio_authorized`, TTL và replay; không nói plate/student chưa confirmed.
2. Xin/renew/release lease với UUID client thật; split view nhận cả hai
   camera; hai viewer chỉ một speaker owner. Reconnect không đọc event cũ;
   một lượt nhiều lỗi đọc đủ một lần, cập nhật biển muộn không đọc lại.
3. Một beep ngắn + câu lỗi ngắn, queue nhỏ/TTL. Tái dùng AudioContext;
   nút bật loa có user gesture, trạng thái readiness rõ. Đo `onstart`,
   `onend`, `onerror`; không coi log “requested” là nghe được.
4. Giọng Việt chỉ dùng local voice đã nghe thử khi WAN tắt. Nếu không có,
   dùng clip câu lỗi tiếng Việt lưu sẵn, preload/hash, tự chọn theo issue
   thật; không gọi cloud TTS trong vận hành. Không có voice đọc biển offline
   thì nhắc lỗi chung và hiển thị biển confirmed, công bố đúng giới hạn.
5. Bỏ phụ thuộc Google fonts/CDN/asset online trong UI và landing; build
   local phục vụ cùng origin. Cold browser/login/lazy routes/media/audio
   phải chạy khi WAN ngắt, không dựa cache trước đó.
6. Đo mục tiêu beep/banner p95 ≤700 ms và speech start p95 ≤1,2 giây từ
   issue confirmed; biển p95 ≤2 giây từ vùng đọc. Ghi số mẫu và điểm bắt đầu.

## 4. Quota bắt buộc — kiểm trước khi ghi

- D còn **ít nhất 30 GiB sau output dự kiến**; C dưới 5 GiB báo cảnh báo,
  dưới 3 GiB dừng tác vụ tạo cache/temp lớn và đổi output sang D.
- Dưới 10 GiB hoặc không đủ output + reserve: chặn download/export/backup/
  benchmark nặng; không “cố chạy”. Không cài thêm runtime/venv dự phòng lớn.
- QA ≤1 GiB/run, giữ 3 run gần nhất; release ≤600 MiB; video backup ≤150 MiB;
  slides/PDF/render tổng ≤100 MiB; VPS demo media ≤200 MiB; log quay vòng.
- QA DB/media/backup/cache riêng, maintenance/training/download tự động tắt.
  Test backup dùng fixture nhỏ, không copy media/dataset vận hành.
- Recording liên tục tắt; bằng chứng theo sự kiện. Không lưu mọi frame/crop
  variant/overlay. Không đóng ZIP có venv/node_modules/.git/media/backups.
- Cleanup chỉ artifact đã xác minh không dùng, có manifest đường dẫn/size/
  lý do; xác minh absolute path trong vùng được dọn. Giữ dữ liệu vận hành,
  nhãn/checkpoint cần thiết và ít nhất hai backup hoàn chỉnh đã kiểm.
- Trước deploy, đọc `scripts/deploy_vps.sh`; không chạy mù script có thể
  cài full GPU dependencies, seed hoặc ghi đè dịch vụ/dữ liệu hiện hành.

## 5. Nghiệm thu đúng đường chạy và giữ giờ

Mốc thực hiện còn lại theo plan cập nhật từ trạng thái khoảng 22:30:

| Mốc UTC+7 | Việc phải xong |
|---|---|
| Ngay nhận–22:45 | Đối chiếu state/disk/process; xác minh camera/loa/SSH read-only; nhận owner |
| 22:45–23:05 | Sửa P0 runtime/audio, hiệu chỉnh camera; giữ baseline nếu challenger chưa đạt |
| **23:05** | Khóa lựa chọn model/reader; không đổi dependency hay mở training mới |
| 23:05–23:25 | Focused + full tích hợp và 15 video AI thật tới EOF theo thứ tự, output bounded |
| 23:25–23:55 | Hai camera thật 30 phút, WAN-off/cold refresh/loa/reconnect/viewer; B hoàn tất gói nhẹ |
| **00:00** | Khóa code/config/weights; chỉ sửa blocker nhỏ có kiểm hoặc revert |
| 00:00–00:30 | Cold start từ bản freeze + 2 lượt diễn tập 3 phút nói/7 phút demo |
| 00:30–00:50 | Kiểm rollback/package/PPTX/PDF/manifest/báo cáo và bàn giao |
| 00:50–01:00 | Đệm xử lý blocker; không mở tính năng mới |

Nếu bắt đầu muộn hơn, điều chỉnh checkpoint sớm một lần theo thời gian thật,
giữ 30 phút camera, tổng duyệt và buffer. Không gán giờ đã qua thành hoàn tất.
Nếu không đủ thời gian để đạt gate, ghi blocker cụ thể và dùng baseline/fallback
đã kiểm; không rút ngắn ca kiểm rồi gọi đạt. Làm phần độc lập đến cùng.

Phải kiểm API/browser thật, đúng weights/config và nguồn thật. Mock chỉ kiểm
logic/UI; decode file không kiểm inference/preview. Báo preview frame mới
≥15 FPS/camera, AI ≥5 FPS/camera, latency/VRAM/CPU/queue/drop bằng số đo.
Video AI phải chạy đúng runtime/profile, có pacing theo FPS nguồn; không
decode hết file trước khi AI kịp đọc rồi gọi EOF pass. Không dùng cờ QA tắt CV
cho ca nghiệm thu này; DB/media/output vẫn cách ly và quota được kiểm.
Kiểm compliant/mũ/riding/số người/multi-issue/biển lạ/biển yếu/xe sát/
đi bộ/dắt xe/đổi nguồn/reconnect/WAN/lease/reload/late issue/IO fail.

Gate demo: không quan sát gán sai/cảnh báo sai/đọc lặp trong rehearsal có nhãn,
âm thanh nghe được, hai camera còn frame mới, bằng chứng đúng event, disk ổn.
KPI ALPR ≥95%, coverage ≥90%, holdout ≥300 lượt và ca 12 giờ giữ nguyên cho
production; không lấy vài lượt demo hoặc 30 phút thay thế. Test thiếu giữ mở.

## 6. VPS + quảng bá — hoàn thiện nhưng không chặn local

- SSH dùng cấu hình có sẵn, đọc OS/resource/disk/services trước. Deploy mới
  trong thư mục riêng, có health/version và rollback. Không reimage hay đè
  dịch vụ khác. VPS chạy phần nhẹ, không nạp Torch/YOLO/EasyOCR.
- Landing tái dùng thiết kế hiện có, bỏ face matching/99.x%/0,2s/100% claim
  chưa đo, form gửi giả và public dữ liệu học sinh. CTA/link/QR phải hoạt động;
  có bản local offline. Số liệu có run/hash/ngày/n hoặc ghi “mục tiêu”.
- Dashboard/sync nếu đã có: scoped auth, outbox bounded, timeout/backoff,
  idempotent versioned upsert, last_synced/source/offline rõ; HTTP/VPS không
  nằm trên đường inference/audio. Replay không phát loa.
- Chưa có sync: chỉ triển khai lát riêng nếu còn đủ thời gian kiểm gửi lặp/
  cũ/out-of-order/mất WAN/restore WAN/quyền. **23:20 dừng thử sync chưa đạt**,
  bàn giao landing + snapshot báo cáo có timestamp; sync vẫn pending.
- SSH chưa vào được trong 15–20 phút: hoàn tất deploy bundle/hướng dẫn/
  rollback local, ghi `pending_access`, tiếp tục audio/slides. Không ghi
  deployed nếu chưa kiểm URL/health/version từ ngoài máy. Chưa TLS thì không
  public login/hồ sơ qua HTTP; static page không dữ liệu nhạy cảm có thể dùng IP.

## 7. Slides và bàn giao đầy đủ

Dùng nội dung và lời nói trong `SLIDES_CONTENT.md`, cập nhật theo báo cáo
**bản freeze**. Tạo PowerPoint 16:9 chỉnh sửa được: 8 slide chính/180 giây +
4 phụ lục Q&A, notes tiếng Việt, PDF dự phòng. Mở/rà mọi slide: font Việt,
không tràn/méo/che chữ, nguồn và verified/target rõ. Không bê checklist sửa
lỗi nội bộ hoặc deadline tối nay lên phần thuyết trình sản phẩm.

Diễn tập đủ hai lượt 180+420 giây theo `DEMO_RUNBOOK.md`; video dự phòng từ
bản chạy thật có tiếng, ghi nhãn “video ghi trước”, không tráo giả làm live.

Bàn giao tại `release/demo-2026-10-04/`:

```text
RELEASE_MANIFEST.json
START_DEMO.ps1, STOP_DEMO.ps1, ROLLBACK_DEMO.ps1
env.example, RUN_LOCAL_OFFLINE.md
FINAL_ACCEPTANCE.md, DEPLOY_VPS.md, VPS_STATUS.md
marketing/ (HTML/CSS/assets local)
School_Gate_Monitor_Demo.pptx, School_Gate_Monitor_Demo.pdf
SPEAKER_NOTES.md, DEMO_RUNBOOK.md, DEMO_BACKUP.mp4
```

Manifest pin commit/tree/dirty state, dependency/weights/config/audio/slide
hash, paths/flags/ROI/source mapping không mật khẩu. Giữ weights đã có bằng
path+hash; không nhân bản kho model/venv. Launcher không install/download,
không --reload, không seed DB thật. Rollback giữ dữ liệu mới và được smoke.

`FINAL_ACCEPTANCE.md` dùng `ACCEPTANCE_TEMPLATE.md`: lệnh/exit code,
expected/observed, GT/n, lỗi/review/
bỏ sót, metrics, nghe loa thật, offline cold-start, 30 phút camera, VPS URL/
trạng thái, dung lượng trước/sau. Pending có owner, bằng chứng và bước tiếp.

Chỉ đánh dấu checklist sau kiểm. Không dừng ở “đã tạo code” hoặc “đã tạo
notebook”. Báo cáo cuối phải cho người dùng **lệnh chạy, file slide, package,
URL đã kiểm, tình trạng demo_ready và các gate còn thiếu**. Chỉ dùng
`production_complete` khi cả acceptance dài hạn/KPI/restore/VPS thật đều đạt.

**Bắt đầu D0 ngay, dùng code hiện có, xử lý P0, kiểm cuốn chiếu và bàn giao
trước hạn. Không hứa tuyệt đối không sai và không khai đã hoàn thành mục
chưa có bằng chứng.**
