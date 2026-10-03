# Demo 04/10/2026 — hai camera, loa và LAN offline

Hạn bàn giao: **trước 01:00 ngày 04/10/2026, Asia/Bangkok (UTC+7)**.
Thuyết trình tối đa 180 giây, demo 420 giây, tổng tối đa 10 phút.
Có laptop RTX 3050 4 GB, hai camera thật và loa. VPS: `103.101.162.111`;
SSH/domain/TLS/deploy chưa xác minh.

Đây là runbook chuẩn bị và nghiệm thu. Chỉ xác nhận kết quả sau khi chạy đúng
bản freeze. Nội dung slide: [SLIDES_CONTENT.md](SLIDES_CONTENT.md).
Kế hoạch: [PLAN_BEFORE_0100.md](PLAN_BEFORE_0100.md); bằng chứng dùng
[ACCEPTANCE_TEMPLATE.md](ACCEPTANCE_TEMPLATE.md).

## 1. Mốc và phân vai

| Mốc UTC+7 | Công việc | Bằng chứng |
|---|---|---|
| Ngay nhận prompt–22:45 | State/disk/process, hai RTSP/loa, quyền SSH read-only | Owner và blocker thật |
| 22:45–23:05 | Sửa P0 runtime/audio, chỉnh camera và chọn baseline | Focused tests, GT, ca nghe thật |
| 23:05–23:25 | Full tích hợp và 15 clip AI runtime theo thứ tự | Exit code/hash, metrics đúng phạm vi |
| 23:25–23:55 | Hai camera thật 30 phút, WAN-off/cold refresh/loa/viewer | Expected/observed, tài nguyên/disk |
| **00:00** | **Khóa code/config/weights**; slides/video/launcher đã sẵn | Commit/tree/config/weights hash |
| 00:00–00:30 | Cold start và hai lượt tổng duyệt 180+420 giây | Nghe loa, kiểm event/media và timing |
| 00:30–00:50 | Rollback smoke, report, kiểm package/PPTX/PDF | Manifest và pending rõ |
| **00:50** | **Bàn giao**, giữ 10 phút đệm trước 01:00 | File/lệnh chạy/URL đã kiểm |

A giữ runtime/ALPR/backend event; B giữ audio UI/lease/QA/VPS/marketing/slides.
Operator điều khiển app/loa/WAN; presenter nói; người duyệt xác nhận GT độc lập.
Có thể kiêm vai, cần ghi tên. Tối đa hai luồng sửa mã, chỉ một full regression
hoặc GPU benchmark tại một thời điểm. Không sửa code trong tổng duyệt.

Điền trước khi diễn tập: operator/presenter/người duyệt; build/config/weights
hash; URL local; camera/gate ID; case manifest. RTSP credentials chỉ lưu
trong config riêng, không chiếu/log công khai.

## 2. Preflight bắt buộc

| Hạng mục | Cách kiểm | Qua khi |
|---|---|---|
| Điện/loa | Cắm nguồn laptop/router/camera; chọn đúng đầu ra Windows | Khán giả nghe rõ, không nhầm loa HDMI/tai nghe |
| LAN | RTSP dùng IP LAN trực tiếp; IP ổn định, không client isolation | Hai camera mở được không cần cloud/P2P |
| WAN-off | Rút uplink/WAN, giữ nguồn router/LAN/PoE | Laptop và camera còn kết nối, không rút nhầm dây camera |
| Build/assets | App local phục vụ JS/CSS/icons/fonts/audio | Cold browser/lazy routes/login/media mở được khi WAN tắt |
| Runtime | Weights đã có và pin hash; config/ROI đúng nguồn | Không download model, tracker/epoch tách riêng |
| Hình ảnh | Focus/ánh sáng/exposure/góc, ảnh native và vạch cổng | Người duyệt nhìn được biển/mũ/tư thế của ca kỳ vọng |
| Loa | User gesture bật loa; voice Việt local hoặc clip local | Nghe thật khi WAN tắt; readiness và lỗi rõ |
| Speaker lease | Một owner, viewer thứ hai không phát | Đổi trang/reconnect không đọc lại event cũ |
| Disk | Đo C/D và output dự kiến, recording liên tục tắt | D sau output ≥30 GiB; QA ≤1 GiB/run; C thấp chặn cache lớn |
| Trình chiếu | Mở PPTX/PDF/video bằng máy demo | Font Việt/ảnh/âm thanh đúng, mở offline được |
| Launcher | Một backend process không --reload | Không install/seed/download; health read-only; rollback sẵn |

Dùng DB/media demo riêng cho tài khoản/fixtures. Không seed hoặc thay hồ sơ
trong DB vận hành để tạo kết quả đẹp. Không tắt toàn bộ firewall để mở RTSP.

## 3. Những bằng chứng chưa thể đánh đồng

- R0 có 1.214 pass/1 skip; regression R8–R9 có **1.277 pass/2 skip/0 fail**
  trong `tasks/task-05/regression-r8-r9.xml`. Thay đổi sau báo cáo đó cần kiểm
  tích hợp cuối; kết quả phần mềm không thay chất lượng camera/loa.
- UI 9/9 browser test không chứng minh preview/WS hoặc nhận diện thật nếu
  phần đó dùng stub. R3/R14 chỉ đọc/decode file, không đo AI end-to-end.
- R6 recognizer mock không chứng minh CCT ONNX thật. Package YOLO11 và notebook
  có sẵn không đồng nghĩa đã train, áp weights hoặc nhận diện xe điện đúng.
- AlertBanner live phải dùng filter/dedup/finalized/evidence/audio_authorized
  và UUID lease thật. Helper được test riêng không thay việc nối vào trang.
- Giọng vi-VN xuất hiện trong danh sách chưa chứng minh offline. Phải nghe
  cold-start khi WAN tắt; không có voice local thì dùng clip câu lỗi local.
- VPS script/địa chỉ IP không chứng minh deployed. Ghi URL/health/hash/TLS/
  auth/rollback riêng trong VPS_STATUS; không đưa VPS lên đường xử lý local.

Trước demo lấy tình trạng mới từ FINAL_ACCEPTANCE của bản freeze; không đọc
nguyên danh sách lỗi nội bộ này cho khán giả khi các lỗi đã được sửa.

## 4. Audio và phép đo

Một lượt: beep ngắn, một câu nhắc theo các lỗi đã confirmed. Mũ và riding có
thể đọc “Không đội mũ, vui lòng dắt xe”. Technical error/pending không thành
vi phạm; biển/student chưa confirmed không được đọc. Biển đến muộn bổ sung
im lặng, không phát lại lịch sử hoặc đọc hai lần ở hai viewer.

Thiếu voice đọc biển offline: nhắc lỗi chung bằng clip local, hiển thị biển
confirmed trên màn hình và công bố đúng phạm vi. Clip phải tự chọn theo event
thật; bấm phát clip không chứng minh hệ thống đã tự phát cảnh báo.

Ghi t_read_zone, t_confirmed, t_persisted, t_ws_received, t_beep_started,
t_speech_started và callbacks/error. Dùng cùng đồng hồ hoặc hiệu chỉnh lệch
server/browser. Công bố n và p50/p95; một ca không chứng minh cam kết p95.

Mục tiêu: plate p95 ≤2 giây từ vùng đọc; beep/banner p95 ≤700 ms và speech
start p95 ≤1,2 giây từ issue confirmed. Không tăng tốc đọc đến khó nghe để
che việc queue hoặc inference chậm.

## 5. Ca demo có ground truth

Lập manifest: case_id, source/session, build/weights hash, GT_plate,
GT_helmet, GT_riders, GT_crossing, expected_review, observed_event_id,
observed_audio và pass/fail/reason. Người duyệt xác nhận ảnh gốc **trước**
so output; không dùng model prediction làm GT.

| Ca | Nội dung | Kỳ vọng được chốt trước |
|---|---|---|
| A | Biển rõ, xe đăng ký demo | Chuỗi đúng và nguồn crop đúng, không ép whitelist |
| B | Không đội mũ, quan sát đủ bằng chứng | Đúng lỗi, một sự kiện/nhắc; ca đối chứng có mũ không báo |
| C | Tư thế qua vạch hoặc số người | Ca đã diễn tập, đúng luật; khuất thì unknown |
| D | Biển mờ/che/thiếu chữ/hai xe sát | Cần duyệt nếu thiếu bằng chứng, không gán xe bên cạnh |
| E | Đi bộ/dắt xe hoặc xe chưa phân loại | Không tự kết luận riding hay xe điện |
| F | Hai viewer/reconnect/WAN-off | Frame mới, chỉ một speaker, không phát event cũ |

Thực hiện ca thật trong khu vực demo kiểm soát; có thể dùng clip đã ghi nhãn
cho tình huống không tiện tái hiện, cần công bố là nguồn ghi trước.
Các ca A–F không thay holdout ≥300 lượt, KPI chất lượng hoặc ca 12 giờ.

## 6. Kịch bản demo — đúng 420 giây

| Thời gian | Operator | Presenter và điểm kiểm |
|---|---|---|
| 00:00–00:35 | Mở app local/login, bốn menu; bật loa | Nêu build local và quyền theo vai trò |
| 00:35–01:10 | Mở hai feed, vật di chuyển; rút WAN giữ LAN | Chỉ ra frame mới của cả hai camera |
| 01:10–02:15 | Ca A, mở crop và kết quả | Đối chiếu GT; chốt đúng hoặc công bố cần duyệt |
| 02:15–03:05 | Ca B, nghe loa và xem bằng chứng | Kiểm đúng lỗi và một lần nhắc |
| 03:05–03:45 | Ca C hoặc đối chứng E đã tổng duyệt | Kiểm luật; unknown không tự gán lỗi |
| 03:45–04:25 | Ca D, mở Duyệt biển/crop | Giải thích thiếu bằng chứng chuyển người duyệt |
| 04:25–05:05 | Viewer thứ hai/ca F | Chỉ owner phát loa, không đọc event cũ |
| 05:05–05:50 | Vi phạm/lịch sử/ảnh/báo cáo | Đúng event/encounter và ảnh của cùng lượt |
| 05:50–06:25 | AI admin/mẫu/bbox/export workflow | Cho thấy mẫu có ngữ cảnh; không export kho lớn/đổi weights |
| 06:25–07:00 | Landing local và chốt bàn giao | Nêu trạng thái VPS thực, local không cần WAN; kết thúc đúng giờ |

Chỉ một tab phát loa; video backup không phát tiếng cùng speaker live.
Trong WAN-off không âm thầm dùng 4G để bù API/voice/CDN. Nguồn là video phải
ghi nhãn, kể cả UI đang có badge LIVE.

Nếu một bước lỗi: xử lý tối đa 20 giây rồi chuyển fallback, không debug dài
trước khán giả. Giữ bằng chứng lỗi; không sửa đáp án rồi gọi đó là OCR.

## 7. Fallback có công bố nguồn

| Mức | Khi dùng | Cách trình bày |
|---|---|---|
| F1 | Một camera lỗi, runtime vẫn chạy | Một nguồn live + clip local có GT; không nói đã ghép hai camera |
| F2 | Runtime/live không ổn | MP4 quay app/camera/loa của bản đã kiểm, ghi thời điểm/build và “video ghi trước” |
| F3 | Video/audio không sẵn | PDF/screenshots đã duyệt, nêu là minh họa luồng và giới hạn |

Ngắt WAN là **điều kiện demo chính**, không phải lỗi cần fallback. F2/F3 giúp
giữ buổi trình bày, không đóng gate hai camera/loa thật. Chia đoạn backup
theo timeline trên để vẫn kết thúc trong 7 phút.

Chuẩn bị trước freeze: PPTX/PDF, video ≤150 MiB, vài screenshot/crop cần thiết,
audio generic local và manifest hash; không copy cả kho media/dataset.

## 8. VPS và landing

Local giữ camera/inference/audio/DB. VPS dùng phần nhẹ/trang giới thiệu nếu
deploy/auth/TLS đã kiểm. Mất VPS/WAN không làm chậm app local.

Trong demo offline mở bản landing local; nếu muốn nói VPS đã deploy, dùng
bằng chứng health/build/URL đã kiểm trước đó và công bố thời điểm. Landing
deployed khác với portal/sync đã đạt. Chưa truy cập được SSH ghi pending_access.

Landing/slide chỉ có chức năng thật và số đo có nguồn; bỏ claim face matching,
99.x%, 0,2 giây, 100% hoặc form “đã gửi” giả. Không public hồ sơ học sinh.
Không chạy script deploy cũ trước khi rà dependencies/seed/overwrite dịch vụ.

## 9. Chốt bàn giao

Dùng [ACCEPTANCE_TEMPLATE.md](ACCEPTANCE_TEMPLATE.md) để ghi pass/fail/pending
riêng cho test, GT/ALPR/luật, 30 phút camera, loa, offline cold browser,
VPS/landing/sync, slides, package và rollback.

Release có launcher start/stop/rollback, manifest commit/tree/dirty/hash,
config/env không secret, report, runbook và PPTX/PDF/notes/video. Không gói
venv/node_modules/.git/media/DB vận hành; weights pin path+hash, tránh nhân bản.

Rollback đúng build+weights+config đã kiểm, giữ DB/evidence mới. Schema đổi
phải có quy tắc restore đã kiểm; không chép đè DB tùy tiện. Bảo toàn staging,
không git add toàn bộ/reset hard/clean.

Chỉ ghi demo_ready khi gate demo thật đạt. Production_complete cần cả KPI,
holdout ≥300 lượt, ca 12 giờ, restore và VPS/sync đầy đủ. Pending có owner,
bằng chứng và bước tiếp. File này là kịch bản, chưa xác nhận demo đã chạy.
