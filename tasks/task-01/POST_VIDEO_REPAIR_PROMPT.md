# TASK 1 — sửa runtime còn lỗi và kiểm chứng lại bằng pipeline thật

Bạn tiếp tục TASK 1 của School Gate Monitor tại `D:\Work\Project_motorbike`. Đây là yêu cầu **sửa mã, chạy test và hoàn thành các phần khả thi**, không chỉ lập kế hoạch hoặc giải thích báo cáo.

## 1. Đọc, xác minh và phối hợp

Đọc toàn bộ:

- `D:\Work\Project_motorbike\docs\CODEX_TASK01_POST_VIDEO_REVIEW_2026_10_02.md`.
- `D:\Work\Project_motorbike\tasks\task-01\REPAIR_AND_VIDEO_TEST_PROMPT.md`.
- `D:\Work\Project_motorbike\tasks\task-01\OWNERSHIP.md`, `CONTRACTS.md`, `REPAIR_TODO.md`.
- `D:\Work\Project_motorbike\tasks\task-01\EXECUTION_LOG.md`, `VIDEO_TEST_REPORT.md`, `ACCEPTANCE_REPORT.md`, `HANDOFF.md`.
- Hai harness và artifacts trong `D:\Work\Project_motorbike\tasks\task-01\video_qa`.
- `D:\Work\Project_motorbike\tasks\task-02\REPAIR_PROMPT.md` và ownership Task 2 để phối hợp.

Mã đang được nhiều task sửa. Xác minh lại từng lỗi trên mã hiện tại; giữ phần đã sửa và test hành vi đạt. Không triển khai lại chỉ vì review trước ghi lỗi. Lưu commit/status/diff và phiên bản dependency/model/config của lần kiểm chứng. Không ghi secret, mật khẩu camera hoặc dữ liệu học sinh vào log.

Không sửa chồng file dùng chung đang có owner khác ghi. Nhu cầu shared-file phải có patch/test cụ thể trong `tasks/task-01/integration/`, ghi PENDING_INTEGRATION và tiếp tục phần độc lập; tích hợp tuần tự khi file đã bàn giao. Patch chưa áp dụng không phải tính năng hoàn thành. Không stash/reset/clean hoặc commit toàn bộ working tree để chia lỗi giữa các task.

Task 1 giữ CV/runtime/Guard/realtime/loa/QA video. Task 2 giữ admin/cleanup/backup/upload/CSV và sửa production routes. Factory/fixture/config/DB/schema phải phối hợp ownership. Không sửa Task 2 cleanup để tự làm regression xanh nếu chưa nhận bàn giao.

Giữ đăng nhập tự điền bốn vai trò như người dùng yêu cầu; không đổi auth strategy. Giữ auto-match trước/sau OFF và gương review-only khi chưa có góc/nhãn nghiệm thu. Không bật tính năng thiếu bằng chứng để tạo tiếng báo.

## 2. P0 — Khóa baseline và môi trường QA

Tạo launcher QA rõ ràng: DB, snapshots/crop/clip, ảnh hồ sơ, review/upload, backup, recording, log và API/frontend ports riêng. Kiểm tra mọi resolved path thực sự nằm trong QA root, gồm đường dẫn đã bind lúc import. Không chỉ đặt APP_DB_PATH rồi coi media đã cách ly.

Không mở RTSP/camera vận hành hoặc maintenance trên dữ liệu thật; không đổi exposure/firmware/cấu hình camera đang chạy. QA dùng video file và fake capture khi cần fault injection. Không nâng dependency trên môi trường đang vận hành.

Điều tra log mới `full_tests_final.txt` bị lỗi tạo thư mục pytest tạm. Kiểm tra khả năng tạo/ghi file, dung lượng, quyền và va chạm giữa các pytest process. Dùng basetemp riêng có định danh mỗi run khi phù hợp. Không tự kết luận shell hỏng hoặc xóa temp hàng loạt; không kill tiến trình của task khác. Lỗi môi trường phải có traceback và kiểm tra khắc phục cụ thể.

Giữ log xanh cũ và log thất bại mới với run ID/thời gian; báo đúng lượt nào là cuối cùng. Baseline focused trước sửa; full regression sau khi môi trường QA an toàn.

Đính chính REPAIR_TODO/acceptance cũ nếu test chỉ grep source hoặc harness chưa chạy runtime: trạng thái phải là PARTIAL/FAIL/PENDING tương ứng. Tạo `POST_VIDEO_REPAIR_TODO.md` theo P0–P8 dưới đây.

## 3. P1 — Kiểm tra model mũ backup, chưa train ngay

Đã kiểm tra metadata:

- `models/helmet_best.pt`: `{0: 'plate'}` — sai vai trò mũ.
- `models/backups/helmet_best_20260930_090903.pt`: `{0: 'With Helmet', 1: 'Without Helmet'}` — mapping phù hợp, chất lượng chưa đo.

Thực hiện:

1. Ghi hash, class mapping và đường dẫn thực mà runtime resolve. Kiểm tra env override; không mặc định file tên helmet là model mũ đúng.
2. Cấu hình QA riêng dùng checkpoint backup, không ghi đè trọng số hiện tại hoặc thay config tiến trình vận hành. Validator runtime và harness dùng cùng contract; model sai phải hiện lỗi và tắt nhánh mũ, không đếm box plate thành helmet.
3. Trích crop/frame thực từ nhiều video: đầu có mũ/không mũ, mũ cầm tay/treo xe, đầu khuất, hai xe gần nhau. Mẫu mơ hồ ghi unknown. Rà trực quan các dự đoán và lập baseline có nhãn đáng tin cậy trong khả năng hiện có.
4. Xác nhận head association và người đang đi xe trước kết luận mũ; mapping đúng không phải chất lượng đạt. Không cần tắt camera/plate khi model mũ không khả dụng.
5. Chỉ đề xuất/fine-tune sau khi phân loại lỗi do model, crop, ghép hoặc góc nhìn. Nếu nhãn thiếu, ghi thiếu cụ thể và chuẩn bị crop/manifest để người dùng duyệt bằng UI feedback hiện có; không đoán nhãn và không tự đổi model vận hành.

**Đạt:** model role sai không phát vi phạm mũ; checkpoint đúng đi qua runtime QA, crop minh chứng có nhãn rõ. Precision/recall chưa đủ dữ liệu vẫn PENDING, không coi số box là độ chính xác.

## 4. P2 — Rear OCR không phụ thuộc person hoặc crossing

Lỗi cần tái hiện: `ocr_only` bỏ person detector nhưng `_run_loop()` có `if not person_dets: continue` trước nhánh group/OCR. Camera sau có box mà không tiến tới đọc biển.

Thực hiện:

- Tạo đường rear dựa trên vehicle/plate track, không nạp person/pose chỉ để vượt điều kiện person. Model/tracker theo camera và chỉ nạp nhiệm vụ cần thiết.
- Theo dõi/lưu crop biển rõ từ ảnh nguồn chưa vẽ; quy đổi bbox đúng native resolution. Recognition vẫn hiển thị box/crop/OCR chưa chắc ngay cả khi chưa có violation, chưa gate line hoặc chưa ghép lượt trước/sau.
- Dùng key camera_id + source_epoch + track/quan sát riêng; không trộn track cùng số ở hai camera. Khi chưa có liên kết xe đáng tin, OCR chỉ review, không gán học sinh hoặc tự ghép encounter trước.
- OCR async: một request chạy/chờ mỗi track, queue toàn hệ thống hữu hạn, crop copy độc lập; không fallback đồng bộ khi bận. Kết quả thu đúng một lần; giữ metadata của crop thực đã submit, không lấy bbox/frame của best crop mới để gán cho kết quả cũ.
- Consensus là đường quyết định runtime: ít nhất hai crop khác frame cùng toàn biển, chất lượng/confidence đủ và không có ứng viên cạnh tranh đáng tin. Một crop, frame lặp, quality0, fragment hoặc mâu thuẫn không được confirmed. Cho phép thu mẫu tốt hơn, không dừng vĩnh viễn sau một lần OCR.
- Không lấy OCR rỗng làm thiếu/che biển. OCR chưa rõ vàng và im lặng; mũ/hành vi đã xác nhận độc lập vẫn được cảnh báo.

**Test xuyên luồng thật:** rear source → detect/tracking → crop → async OCR → consensus → card/API. Không person và không gate line vẫn thấy tiến trình OCR; một mẫu chưa confirmed, hai mẫu đúng mới confirmed; stale/duplicate/ambiguous không gán biển. Test hai camera cùng track ID và đổi nguồn khi Future đang chạy.

## 5. P3 — Preview thật sự độc lập AI/OCR/DB

Di chuyển `_publish_frame_jpeg` lên đầu vòng AI chưa đáp ứng yêu cầu vì vòng này vẫn chờ `.result()` trước khi publish khung tiếp theo.

Thực hiện giải pháp nhỏ nhất phù hợp code:

- Capture cập nhật latest native frame riêng; AI lấy frame mới nhất, bỏ backlog cũ.
- Publisher/encode hoặc vòng preview có thể tiến khi AI đang chờ, không bị detect/pose/OCR/DB/clip chặn. Tránh tạo thêm model instance hoặc pool không cần thiết.
- Encode một lần mỗi camera/frame hiển thị mới, viewer dùng chung bytes. Overlay cập nhật từ AI gắn camera/epoch/frame/time và hết hạn500ms; không vẽ box cũ kéo dài hoặc trộn nguồn.
- Preview/AI/source FPS đo riêng; không đếm gửi lại JPEG thành frame mới. Frame age dùng monotonic phù hợp. Mất frame mới quá2s hiển thị hình cũ/mất tín hiệu.
- Stop/reconnect/switch có vòng đời worker rõ, join hữu hạn và invalidate nguồn cũ. Một camera lỗi không dừng camera còn lại. Không giữ lock đồng bộ qua await hoặc giữ khóa ảnh suốt inference.

**Test hành vi bắt buộc:** nguồn giả cấp nhiều frame liên tục; dùng Future/Event chặn AI2–3s; trong lúc chưa nhả, ít nhất nhiều frame_seq và JPEG mới vẫn tăng. Chặn OCR/DB/clip tương tự; kiểm tra no-person, FRAME_SKIP, hai viewer shared bytes, overlay TTL và stop/switch không publish phiên cũ. Test grep vị trí mã không được thay thế kiểm tra này.

## 6. P4 — Crossing và posture theo lượt xe

### P4.1 Crossing

Probe cũ cần trở thành regression test:

```text
3 frame A: 1000.0, 1000.1, 1000.2
3 frame B: 1017.1, 1017.2, 1017.3
Expected: không crossing
```

- Hiện transition timer bắt đầu ở frame đầu phía B nên bỏ qua khoảng mất track17s. Sửa tính liên tục/cửa sổ của chứng cứ phía A→B; mất track quá hạn không ghép thành lượt qua cổng.
- Chỉ crossing khi3 frame ổn định mỗi phía, frame mới, trong tối đa5s theo contract. Dead-zone không được làm sống chứng cứ quá hạn. Biên2% đường chéo đúng với ảnh không vuông.
- Test3+1/3+2 không xác nhận,3+3 xác nhận một lần, gap17s, dead-zone gap, rung/quay đầu, frame/timestamp lặp, epoch mới, hai hướng và hai xe.

### P4.2 Posture

- Bỏ quyết định temporal từ mode của toàn group/camera. Mỗi xe/lượt có ledger theo camera/epoch/track, dùng frame identity và đồng hồ phù hợp.
- Áp dụng cửa sổ1.5s, tối đa5 quan sát hợp lệ, ít nhất4 đồng thuận, tỷ lệ>=80%, span>=400ms, cách mẫu>=100ms theo contract. Unknown không là phiếu có/không lỗi; mâu thuẫn đáng tin chuyển review.
- Hết hạn/mất track chuyển unknown, không giữ riding chắc chắn. Health tổng nếu cần không được dùng làm quyết định từng xe.
- Kết quả ledger phải được sử dụng trong quyết định thực: RIDING_THROUGH_GATE chỉ khi riding ổn định + crossing hợp lệ. Standing/pushing/walking/unknown không đi đường tắt; lỗi độc lập vẫn giữ.

**Test:** hai xe mỗi xe2 mẫu không gom thành4, một riding/một pushing, frame lặp, TTL/span/interval/window, source switch và đứng/ngồi yên/dắt qua cổng. Kiểm tra event thực, không chỉ helper trả enum.

## 7. P5 — Realtime/bằng chứng/loa trong QA

- Giữ event/issues version/update hiện có, xác minh late issue không làm mất issue cũ hoặc cộng sample giả khi replay.
- Snapshot/crop và DB thành công trước âm thanh chính thức; clip có thể pending. Lỗi lưu không tạo URL giả/loa chính thức.
- Hai viewer cùng nhận upsert/version, client chậm không chặn pipeline, reconnect không đọc lịch sử. Audio lease và dedup theo contract hiện hành; không chỉnh luật âm thanh chỉ để làm test xanh.
- Giọng ngắn, tốc độ cấu hình hiện có1.45 và giới hạn an toàn đã chọn; không đọc OCR chưa chắc. Kiểm tra người dùng bật loa, browser chặn voice và lý do mute thật.
- Dùng DB/media/accounts QA và API/frontend ports riêng; seed này không đụng Task2 dữ liệu vận hành. Startup phải dùng factory thật sau bàn giao shared patch, CV nguồn giả/file được inject, không app test dựng khác.

**Test browser:** recognition card có ảnh người/đầu/biển và số mẫu thực; OCR vàng không beep/TTS; helmet/crossing đủ điều kiện có bảng và lệnh phát đúng; hai viewer/late update/reconnect/switch/mute. Stub SpeechSynthesis để quan sát dispatch khi cần, nhưng kiểm tra thêm trạng thái voice khả dụng thực; test lệnh không chứng minh đã nghe tiếng Việt trên máy khác.

## 8. P6 — Viết lại QA video bằng runtime triển khai thật

Giữ artifacts V1/V2 cũ, đổi nhãn thành **component detector/OCR benchmark**. Không gọi chúng là full pipeline hoặc dùng latency detect/OCR làm latency preview. `text != empty` chỉ là raw_nonempty_read, không OCR đúng toàn biển.

Harness mới phải dùng lifecycle và runtime `VideoPipeline` thực, chỉ thay dependency bên ngoài cho QA. Không `__new__` rồi gán pool giả/ledgerNone trong bài đo nghiệm thu; không gọi detector trực tiếp thay cho pipeline. Fake detector chỉ dành cho test fault injection, phải tách khỏi benchmark model thật.

### P6.1 — Toàn bộ video trong `C:\Users\khucv\Downloads\tranning`

- Inventory lại mọi video thực có, không hardcode số15 nếu thư mục thay đổi. Lưu SHA256/duration/frame count/codec và model/config hash.
- Replay từng file đến EOF, xử lý toàn timeline và ghi coverage/frame bỏ. Không dừng sau60s wall-clock rồi tuyên bố đã chạy hết clip. Offline mode có thể điều tiết tốc độ; realtime mode bỏ frame cũ hợp lệ phải ghi rõ số AI frames/coverage, không coi mọi frame đã inference.
- QA front/rear đúng profile, role/camera cùng cổng vật lý, nguồn file độc lập và epoch đúng. Ground truth trước/sau chưa đồng bộ thì không dùng để tuyên bố matching đạt.
- Crop minh chứng đặt theo video/camera/epoch/track/frame để không ghi đè giữa video. Giữ liên kết raw/crop/prediction/confirmed/event và lý do reject.
- Lưu số confirmed plate khác với raw nonempty; model mũ đúng vai trò khác box count; review vs confirmed vs persisted alerts riêng.
- Với dữ liệu đủ rõ, chuẩn bị/kiểm chứng nhãn và báo lỗi thực; thiếu thì liệt kê chính xác. Video loop hoặc nhiều frame cùng xe không là mẫu độc lập.

### P6.2 — Hai nguồn đồng thời30 phút qua runtime thật

- Nguồn file real-time paced, loop có boundary epoch hợp lý; đo monotonic wall-clock đủ1800s. Model loading/warmup tách khỏi cửa sổ đo và ghi riêng.
- Hai camera cùng gate, một/hai/ba viewer; OCR chậm/lỗi, mất một nguồn, reconnect/switch bằng nguồn giả được kiểm chứng riêng. Không thay nguồn camera vận hành.
- Thu FPS capture/newJPEG/AI mỗi camera; age/receive→JPEG-ready p50/p95; stage timings detect/tracking/pose/OCR/encode/persist/dispatch; queue/drop/reconnect/errors và event/media consistency.
- Dùng rolling buffers/bounded summaries; không list tăng vô hạn cho mọi OCR/box suốt ca. Ghi exceptions từng stage; không `except: pass` rồi báo0 exception. Stop/join phải chứng minh worker đã dừng, không còn thread chạy khi xuất report.
- Timestamps start/end thật và runtime/config hash; không gán cả start/finish bằng thời điểm lúc xuất JSON. p95 tính từ phân phối hợp lệ, không lấy trung bình p95 từng video làm p95 toàn hệ thống.

**Mục tiêu:** preview frame mới>=15FPS/camera khi source đủ, AI>=5FPS/camera, receive→JPEG-ready p95<=500ms, không crash/OOM/queue tăng vô hạn. Các số component4.42/10.47FPS trước chỉ là baseline, chưa đủ nghiệm thu runtime.

## 9. P7 — Tối ưu bằng điểm nghẽn thật, chuẩn bị dữ liệu nhận diện

- Ghi thiết bị thật từng detector/pose/OCR. Đo CPU/RAM và GPU utilization/process VRAM khi có công cụ; phân biệt allocated/reserved/VRAM toàn tiến trình. `torch.cuda.memory_allocated=206MB` không đồng nghĩa GPU còn95% công suất.
- Profile nhiệm vụ front/rear; tránh plate/pose/OCR dư trên camera trước nếu nhiệm vụ không cần. Điều phối GPU công bằng, state riêng camera, không chia sẻ model qua thread không an toàn.
- Tối ưu resize giữ tỷ lệ/cropnative, lịch pose/OCR, batch/FP16 chỉ sau đo và đối chứng chất lượng. Không tăng pool/batch hoặc hạ tiêu chuẩn xác nhận chỉ để dùng hết tài nguyên.
- Biển thật quá nhỏ/mờ/chói: lưu crop và pixel/quality minh chứng, đề xuất góc/ánh sáng/exposure để người dùng kiểm tra trên camera thật. Không tự chỉnh thiết bị; không dùng ảnh AI/super-resolution làm chữ biển hay ground truth mới.
- Dùng feedback đúng/sai và biển sửa lại hiện có để chuẩn bị dataset có provenance, split theo video/phiên/lượt. Không học online hoặc tự đổi weights ngay sau một lần người dùng tích đúng.
- Chỉ train khi baseline có bằng chứng lỗi model và nhãn đủ. Giữ tập test độc lập; model mới phải vượt baseline và latency trước khi đề xuất đưa vào vận hành.

Mục tiêu chất lượng giữ nguyên: precision lỗi đọc loa>=95% từng loại, recall>=70% trường hợp rõ, OCR toàn biển>=50% trên>=30 biển rõ; tập>=50 lượt vi phạm và>=50 lượt không vi phạm rõ. Thiếu mẫu ghi PENDING_DATA, vẫn tiếp tục sửa/test phần độc lập. Gương và ghép hai góc giữ OFF/review khi chưa đủ điều kiện.

## 10. P8 — Full regression, report và bàn giao

Sau kiểm tra QA isolation, dùng interpreter cố định tại root:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
```

Trong `D:\Work\Project_motorbike\frontend`:

```powershell
node --test test/*.test.mjs
npm run lint
npm run build
npm run test:e2e
```

Không bỏ cleanup/maintenance/guard hoặc các test khó để gọi suite xanh. Nếu còn lỗi thuộc Task2 đang tích hợp, report regression FAIL/PENDING_INTEGRATION với traceback và test owner; không ghi fullPASS. Không làm yếu assertion hoặc dùng grep source thay test hành vi. Unit/integration không load camera/model thật chỉ vì fixture thiếu.

Chạy focused tests sau mỗi thay đổi; regression tại checkpoint P1–P3, P4–P5 và P6–P8. Khi có thêm sửa lỗi, chạy lại các kiểm tra bị ảnh hưởng và regression cuối trong fresh process. Không để benchmark/training tranh GPU với phiên task khác; không chạy hai lần full pytest song song trong cùng QA root.

Cập nhật `POST_VIDEO_REPAIR_TODO.md`, `EXECUTION_LOG.md`, `VIDEO_TEST_REPORT.md`, `ACCEPTANCE_REPORT.md`, `HANDOFF.md` và artifacts mới với run ID. Giữ lịch sử, đính chính mục PASS vượt bằng chứng. Mỗi kết quả phải có lệnh thực, cấu hình, test/coverage, số đo, lỗi/pending và rollback không làm giảm tiêu chuẩn nhận diện.

**Cách thực hiện đã được chốt:** tiếp tục ngay, không hỏi lại “muốn tiếp tục không” sau từng đợt. Checkpoint là kiểm chứng tự động, không phải dừng chờ duyệt. Khi thiếu file bàn giao/thiết bị/nhãn, ghi blocker chính xác và tiếp tục phần độc lập; không kết thúc chỉ bằng lời hứa sẽ đọc hoặc kế hoạch.

**Chỉ đóng phần sửa runtime khi:** các lỗi N01–N08 đã xử lý có bằng chứng hành vi, rear OCR và preview độc lập hoạt động, crossing/posture đúng, video QA runtime hoàn tất, browser/fresh regression đã chạy và status đúng kết quả. Camera Imou/12h/accuracy đủ nhãn nếu chưa đo thì còn PENDING riêng; không tuyên bố nghiệm thu toàn hệ thống. Không đẩy remote, triển khai VPS, thay config camera/DB/media vận hành hoặc bật model mới chưa kiểm chứng.
