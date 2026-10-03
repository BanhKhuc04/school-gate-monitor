# Giao Cursor hoàn tất đợt 5 — ALPR, hai camera, YOLO11

Cập nhật: 03/10/2026, theo yêu cầu bàn giao phần còn lại. Workspace:
`D:\Work\Project_motorbike`, branch `codex/alpr-yolo11-local`.
Đọc file này trước các prompt/checklist lịch sử. Giữ lịch sử Task 1–4;
dùng các task R bên dưới để triển khai tiếp, không làm lại phần đã kiểm chứng.

## 1. Trạng thái bàn giao

| Phần | Đã có | Còn phải làm |
|---|---|---|
| Capture/preview | Capture độc lập, latest frame, queue hữu hạn, JPEG dùng chung, kiểm epoch; test chặn AI 3 giây và encoder theo frame mới đạt | EOF video riêng với mất mạng; reconnect/source race và đo FPS trên hai nguồn thật |
| GPU | Worker owner, chia lượt theo camera, YOLO dùng chung weights, pose singleton, bulk tensor copy, timing chờ đủ detector | Benchmark hai nguồn; kiểm mọi đường gọi model đi qua owner, CPU/VRAM tổng, fairness và độ trễ khi quá tải |
| Tracking/voting | Camera sau dùng track ID; BestPlateStore cho live tối đa 5 crop/2 giây, giữ metadata crop đã OCR; single frame chuyển review | ByteTrack thật với xe di chuyển/đi sát; liên kết biển–xe; voting ký tự/confidence xuyên pipeline, camera/epoch/encounter |
| OCR | Adapter CCT CPU, RGB/config/hash/confidence ký tự; EasyOCR baseline; tối đa 2 biến thể trong đường EasyOCR | Smoke model ONNX thật, hai dòng và rectification cho CCT; benchmark holdout; giữ đầy đủ metadata đến DB/API |
| Dependency/YOLO11 | Venv có Ultralytics 8.4.168, FastPlateOCR 1.1.0, ORT CPU 1.30.0; Torch 2.6.0+cu124 giữ nguyên | Runtime weights vẫn là v8/custom hiện có; chưa train hoặc chuyển mặc định sang YOLO11 |
| Dung lượng | Dọn bản test trùng và 23 backup dang dở có manifest; sửa lịch backup qua reload và hủy copy khi shutdown; D khoảng 53,2 GiB trống | Guard mọi tác vụ nặng, quota/rotation/restore media, giữ đủ backup kiểm chứng |
| UI | 4 menu, quyền/redirect, AI nâng cao, bbox theo mẫu, debug theo camera; 9/9 browser test, build/lint exit0 | Import model, metrics và download ZIP thật; regression các E2E cũ và preview/camera thật |
| Dataset | Audit 8.259 detect + 3.188 OCR; script curation/export và 10/10 selftest | Duyệt nhãn/provenance/group splits; mũ/xe điện chưa đủ dữ liệu; 3 notebook và training chưa làm |
| Luật/encounter | Module luật/crossing/late issues/matcher và test hiện có | Nghiệm thu video có nhãn, encounter hai camera, xe điện/unknown; auto-match vẫn tắt |

**Git:** commit `89bd2c4` chứa capture/preview; `f535974` chứa sửa backup và
storage preflight. Nhiều phần GPU/voting/CCT/UI/QA/dataset còn nằm trong working
tree; HEAD chưa đại diện toàn bộ mã được bàn giao. Staging có thay đổi của người
dùng từ trước. Không `reset --hard`, không `clean -fd`, không `git add .`.
Index trước cleanup được giữ ở `.git/codex-pre-task05.index`; không nạp lại nguyên
index đó vì sẽ đưa artifact vào staging lần nữa. Chốt commit riêng theo file/hunk
đã rà, bảo toàn thay đổi khác.

**Bằng chứng test:**

- Regression đầu: 1.198 pass / 15 fail / 1 skip, sau đó 105 test liên quan đạt.
- Lượt full sau thêm flag cách ly: **1.200 pass / 14 fail / 1 skip**, 342,84 giây,
  tại `regression-final.xml`. 14 lỗi đến từ test collector/guard cần chủ động bật
  worker giả; đã sửa fixture và chạy lại **59/59 đạt** (`focused-isolation.xml`).
- Chưa chạy lại full suite sau các fixture cuối. R0 phải làm trước nghiệm thu.
- Backup/maintenance/restore fixture: **38/38 đạt**. Capture/runtime: 33 test đạt;
  owner/pose/metrics: 45 test đạt; voting/crossing: 59 test đạt;
  OCR adapter/preprocess: 30 test đạt. Các nhóm có thể trùng test; không cộng tổng.
- UI browser dùng auth/dataset/ảnh/bbox API thật; preview/WS có stub, không chứng
  minh FPS/camera. Chi tiết `UI_REPORT.md`, `DATA_REPORT.md`, `STATUS_BOARD.md`.
- Hai backup hoàn chỉnh đã kiểm toàn bộ SHA256 (9.626 file/bộ), restore DB và
  `integrity_check=ok`; full media restore còn mở (`backup-preserved.json`).

**Dữ liệu:** detect có 4 nhóm ảnh trùng, 1 nhóm lọt train/val, bbox giữa bản trùng
khác nhau. OCR có 3.173 chuỗi đề xuất từ bbox nhãn, mọi `human_verified=0`.
Chưa có holdout độc lập. Bộ mũ có 0 ảnh; chưa có nhãn xe điện được kiểm chứng.
15 clip có tại `C:\Users\khucv\Downloads\tranning` (~8 phút, 1280×720).
Blocker cũ “không có video” đã hết hiệu lực; thiếu ground truth vẫn là blocker
đo chất lượng. 13 job OCR lịch sử là baseline, không chứng minh đã training.

## 2. Cách chia việc để chạy nhanh

- **Cursor A — runtime/ALPR:** R2–R7, R11–R12. Owner duy nhất của
  `app/cv/pipeline.py`, detector, OCR, consensus, model promotion và API model.
- **Cursor B — QA/UI/dataset:** R0–R1, R8–R10, R13–R15. Không sửa pipeline
  cùng A. B làm UI import/download sau khi A chốt schema/API; làm notebook khi
  schema dataset đã chốt. Thu/gán nhãn do người duyệt xác nhận, công cụ chỉ hỗ trợ.
- Tối đa hai luồng sửa code. Chỉ một full regression hoặc benchmark GPU đang
  chạy; kiểm process trước khi chạy, không dùng `pytest -n auto` trên máy này.
- Mỗi lát 1–2 giờ, tối đa 3–5 file nguồn, focused test rồi commit riêng.
  Task lớn tách tại các điểm (a)/(b); thời gian train/endurance không tính là lát code.
- Mỗi lát ghi: commit, file, lệnh test/exit code, artifact/dung lượng, số đo và
  giới hạn. Nếu thiếu nhãn/camera, đặt `pending_data`/`pending_camera` và làm các
  việc độc lập tiếp. Không hạ KPI hoặc thay API thật bằng mock để đánh dấu đạt.

## 3. Backlog phần còn lại theo thứ tự

### R0 — Chốt trạng thái tích hợp và regression (P0, B, làm đầu tiên)

- Rà `git diff HEAD` và staging theo danh sách báo cáo, đối chiếu mã chưa commit
  với dependency và fixture. Không bỏ mất `plate_preprocess.py`, adapter/owner
  mới hoặc các component UI đang được import.
- Kiểm QA không mở RTSP, tải YOLO/EasyOCR hoặc chạm DB/media vận hành qua các
  entry point lazy như guard/dev/camera. Worker contract test bật worker có
  fixture/queue riêng; giữ mặc định QA tắt worker. Sửa thiếu isolation nếu còn.
- Chạy lại full pytest trên cây mã ổn định; báo lỗi mới/lỗi cũ riêng, không bỏ test.
  Xác nhận dependency từ venv/requirements, `pip check`; không thay Torch CUDA
  hoặc cài đồng thời hai ORT provider package. Chốt commit kiểm chứng theo lát.
- **Đạt khi:** full suite không fail; skip có lý do; QA không sinh kho media/
  backup mới; runtime/frontend import được từ checkout sạch có các file cần thiết.
- Điểm vào: `app/tests/conftest.py`, `app/main.py`, `scripts/qa_launcher.py`,
  fixtures collector/guard, `requirements.txt`; chia nhỏ trước khi sửa.

### R1 — Hoàn tất bảo vệ ổ đĩa/backup/QA (P0, B, sau R0)

- (a) Áp `require_space` cho upload/import/export/download/benchmark nặng và
  backup API, tính output thực kể cả staging/ZIP/unzip. HTTP trả lỗi có thể hiểu
  được; giới hạn upload, số file và kích thước giải nén; không nhận đường dẫn
  output tùy ý vượt thư mục quản lý. Cảnh báo <15 GiB, chặn <10 GiB hoặc thiếu
  chỗ cho output. Đặt temp/cache trên D; C hiện chỉ khoảng 6,7 GiB.
- (b) Log rotation, QA ≤1 GiB/run và giữ 3 run, dọn staging lỗi sau khi job kết
  thúc. Backup theo quota nhưng giữ ≥2 bộ hoàn chỉnh đã kiểm restore; kiểm lịch
  qua 3 lần restart và cancellation giữa media copy. Ngăn bản incomplete tích
  tụ; cleanup phải có manifest/containment, không xóa job đang chạy.
- **Đạt khi:** test low-space không tạo output/corrupt backup; D ≥30 GiB;
  restore DB+media được kiểm và policy không xóa 2 bộ cần giữ. Recording tắt.
- Điểm vào: `storage_budget.py`, `api/system.py`, `api/training_portable.py`,
  `training/export_portable.py`, `background.py`, backup tests; mỗi lát chọn ≤5.

### R2 — EOF, reconnect và source lifetime (P0, A, sau R0)

- Tách EOF file khỏi lỗi mạng; video hết thì kết thúc lần chạy, không reconnect
  rồi phát lại clip như camera. Giữ pacing theo FPS nguồn.
- Kiểm stop/join reader trước release; đổi nguồn đang OCR/encode, reconnect và
  source thất bại không đưa frame/JPEG/alert/results epoch cũ ra ngoài. Reset
  tracker riêng theo camera/phiên nguồn; không reset predictor chung làm hỏng
  camera còn lại. Không bỏ kiểm first frame trước xác nhận nguồn mới.
- **Đạt khi:** clip ngắn đến EOF đúng một lần; race tests không có frame/biển cũ;
  AI bị chặn 3 giây capture vẫn tiến, queue luôn hữu hạn.
- File: `cv/capture.py`, `cv/pipeline.py`, capture/switch tests.

### R3 — Baseline hai nguồn và GPU thật (P0, A, sau R2)

- Dùng hai video độc lập làm nguồn runtime trước khi có camera; chạy cùng các
  profile front/rear sẽ triển khai. Harness cách ly DB/media/collector/backup.
- Đo frame age và FPS frame mới; capture/drop/queue wait, detect gồm mọi model,
  OCR, encode, event latency p50/p95, CPU/RAM, Torch allocated/reserved và VRAM
  thiết bị. Phân biệt phần memory model với phần dùng bởi desktop/app khác.
- Kiểm owner fairness và queue đầy, predict/pose/OCR/init/hot reload đi qua owner;
  không dùng utilization GPU cao làm tiêu chí duy nhất. Đo 1/2/3 viewer, JPEG
  encode một lần/frame. Warmup tách khỏi kết quả, cấu hình/hash được ghi lại.
- **Đạt khi:** có `RUNTIME_BASELINE.json` + báo cáo tái lập; FP16/batch chỉ chọn
  nếu cùng holdout không giảm chất lượng. Chưa đạt 15 preview/5 AI FPS/camera
  phải chỉ ra bottleneck và giữ mục mở. Không chạy benchmark cạnh full regression.
- File: owner/metrics/profiler, harness mới hoặc script benchmark hiện có;
  `benchmark_pipeline.py` hiện đo một nguồn không đủ cho nghiệm thu này.

### R4 — ByteTrack thật và biển gắn đúng xe (P0, A, sau R2)

- (a) Kiểm API BYTETracker của Ultralytics 8.4.168 bằng model/results thật;
  test track moving qua ô ảnh, xe sát nhau, mất track/đổi nguồn. Giữ tracker
  theo camera/epoch dù weights/predictor dùng chung.
- (b) Liên kết biển với vehicle track theo hình học và thời gian; không gắn theo
  người/ô vị trí khi xe mơ hồ. Plate-only quan sát có ID vẫn xem được; mơ hồ
  giữ review, không tự gán học sinh. Tracking tồn tại không chứng minh nhận dạng.
- **Đạt khi:** có video fixture cho ID ổn định và không trộn hai xe/camera;
  track reuse sau epoch mới không nhận biển của phiên trước.
- File: `cv/detector.py`, `cv/pipeline.py`, vehicle gate/group tests.

### R5 — Voting đầy đủ và metadata xuyên luồng (P0, A, sau R4)

- Giữ tối đa 5 crop khác frame trong cửa sổ 2 giây. Retry/2 biến thể cùng crop
  chỉ là một observation, không thêm phiếu. Hai frame độc lập mới có thể chốt.
- Chuyển raw/normalized/char_confidences/engine/model+config hash/frame/camera/
  track/epoch đến consensus, evidence và API. Hiện `_consensus_ingest` chưa
  chuyển toàn bộ raw/character metadata; chỉ thêm output adapter là chưa đủ.
- Voting ký tự giữ chiều dài/vị trí, xử lý padding theo config; mẫu mâu thuẫn
  mạnh, thiếu chữ hoặc lỗi OCR chuyển review. Validator không thêm ký tự hay
  dùng whitelist để sửa chuỗi yếu. Chốt crossing và future trễ phải dùng crop
  gốc đã đóng băng, không dùng candidate mới; không tạo sự kiện thứ hai.
- **Đạt khi:** integration test toàn đường 2 phiếu đồng thuận/1 phiếu/conflict/
  late result/epoch mismatch; biết nguồn từng phiếu, không trộn encounter.
- File: `best_plate.py`, `plate_consensus.py`, `pipeline.py`, perception contract;
  tách schema/API/DB sang lát sau nếu cần migration.

### R6 — CCT thật, rectification và benchmark OCR (P0, A, sau R5; holdout từ R8)

- (a) Smoke local `models/cct/cct_s_v2_global.onnx` + YAML bằng package 1.1.0
  thật; kiểm dạng return/confidence/padding và finite values, RGB uint8,
  input shape/config/hash. Unit test recognizer giả hiện có chưa thay smoke này.
- CCT xử lý biển hai dòng đúng trên–dưới và crop rectification đã có; tối đa hai
  biến thể, không tăng nét để đoán chữ mất. Không luôn cắt đôi giữa ảnh nếu
  hàng ký tự lệch; crop/config không hỗ trợ phải review. Bảo toàn char confidence.
- (b) EasyOCR và CCT trên cùng crop, cùng holdout có nhãn; báo exact string, CER,
  review/coverage, normal/blur/perspective/night/two-line và latency. CCT CPU
  trước; ORT CUDA thử môi trường riêng với CUDA/cuDNN đúng, đo tổng hệ thống.
- **Đạt khi:** adapter chạy artifact thật, nguồn/metadata rõ, lỗi không tự chốt;
  có báo cáo so sánh tái lập. Giữ EasyOCR mặc định tới khi challenger đạt gate.
- File: `fast_plate_ocr.py`, `ocr.py`, `plate_preprocess.py`, benchmark/tests.

### R7 — Import, đánh giá, áp dụng và rollback model thật (P0, A, sau R5/R6)

- (a) Chốt contract artifact: weights/ONNX, config, mapping, hashes, package
  versions, dataset/holdout hash và metrics. API import admin kiểm kích thước,
  path/hash/mapping/load; metrics tải về chỉ là khai báo, phải đánh giá local
  trên holdout cố định trước eligible. Bổ sung metrics list cho UI. Không load
  pickle/checkpoint từ nguồn tùy ý trong process vận hành; artifact không hợp
  lệ bị cách ly, chưa thể làm active.
- (b) `selected → pending_runtime → applied` chỉ sau runtime xác nhận đúng
  model hash, engine, camera và epoch tại ranh giới an toàn giữa lượt xử lý.
  CCT cần contract ONNX+YAML; promotion cũ chỉ nhận EasyOCR/CustomOCR và torch
  checkpoint nên chưa dùng được cho CCT. Kiểm đường apply thực và ACK mọi
  camera cần dùng; rollback cũng cần load/ACK baseline, không chỉ sửa registry.
- Load thất bại, hash sai, thiếu VRAM hoặc worker bận giữ model đang chạy;
  không đổi metadata trước weights. Gán camera_id cho detector mới, reset
  state liên quan mà không nhận future cũ. Kiểm GPU transient khi đổi model.
- **Gate:** ngưỡng cũ OCR50%/30mẫu hoặc detector/F1 0,5 không đủ nghiệm thu
  vận hành. Tách eligible benchmark khỏi eligible production; production cần
  KPI toàn chuỗi và holdout trong mục4. Baseline eval không mang trạng thái trained.
- **Đạt khi:** import/evaluate/apply/rollback end-to-end với weights thật;
  registry/UI khớp hash runtime; các fail case không mất baseline/lịch sử.
- File theo lát: `training/promotion.py`, `dataset_repo.py`, candidate API,
  `pipeline.py`, adapter/registry và tests. UI nối ở R13.

### R8 — Duyệt dữ liệu và holdout độc lập (P0 dữ liệu, B, làm song song R2–R7)

- Dùng `DATA_REPORT.md`, audit JSON/CSV đã có; không ghi đè CSV đang duyệt.
  Người duyệt chọn một bản/bbox đúng trong 4 nhóm trùng; kiểm ảnh gần trùng và
  leakage theo video/session/encounter, bổ sung provenance được xác nhận.
- Chốt `group_id`, split và `human_verified=1` bằng nhãn người. Public data thiếu
  provenance không được giả làm holdout camera. Chuỗi OCR đề xuất từ annotation
  chưa là nhãn hoàn chỉnh; người duyệt nhập đúng `plate_text`/unreadable.
- Thu mũ/no-helmet/occluded/unknown, xe điện và xe máy thường theo góc cổng;
  phân biệt xe điện từ ảnh phải có quy tắc nhãn rõ. Thu ca khó và negative,
  nhóm ít nhất 300 lượt có ground truth cho nghiệm thu học sinh/ALPR.
- **Đạt khi:** manifest/hash/group-disjoint train/val/test; không pseudo-label
  làm GT; báo số mẫu/hạng mục thiếu. Export chọn ảnh+nhãn, dataset riêng tư,
  không DB/hồ sơ học sinh. Thiếu dữ liệu giữ `pending_data`.
- File: 3 script Kaggle hiện có, curation CSV/manifest và hướng dẫn gán nhãn.

### R9 — Ba notebook Kaggle và checkpoint/resume (P1, B, sau schema R8)

- Tạo ba notebook **chưa có**: `notebooks/yolo11_plate.ipynb`,
  `notebooks/yolo11_helmet_electric.ipynb`, `notebooks/cct_plate_ocr.ipynb`.
  Notebook mũ/xe điện có section/job độc lập; không ép model gộp nhiều lớp.
- Preflight manifest/hash/mapping/group/split; thiếu mũ/xe điện trả pending_data,
  không tạo metrics train giả. YOLO11n/Ultralytics8.4.168; pin package Kaggle sau
  kiểm CUDA environment, không thay Torch local. Export relative paths.
- Lưu best/last, epoch/optimizer/config/dataset hash, metrics và artifact SHA256;
  resume YOLO từ last.pt. CCT `--weights-path` không phải resume optimizer đầy
  đủ; dùng compiled last.keras + initial_epoch, kiểm optimizer step. Chi tiết
  API/package đã đọc tại DATA_REPORT, xác minh trước khi viết cell.
- Giới hạn output/cache/plots/checkpoints; không train local khi hai camera chạy.
  ONNX CCT + YAML phải được test round-trip trên ảnh mẫu và config thật.
- **Đạt khi:** cell compile/schema/selftest, smoke train/resume với dữ liệu nhỏ;
  run thật chỉ đánh dấu sau có log/checkpoint/metrics. Thiếu tài khoản/dữ liệu
  vẫn hoàn thiện notebook và ghi rõ thao tác ngoài máy còn lại.

### R10 — Train YOLO11/CCT và chọn challenger (P1, B; cần dữ liệu + Kaggle)

- Train biển trước từ detector dataset đã duyệt; CCT sau nhãn chuỗi; mũ/xe điện
  sau dữ liệu đủ. Không dùng COCO weights làm detector biển/mũ/xe điện riêng.
- So v8 với YOLO11n trên cùng holdout, rồi đo hai nguồn/VRAM local qua R3.
  Person/vehicle COCO và pose có model/config riêng; migration từng model.
  Thêm path model biển/xe điện có cấu hình và kiểm mapping, giữ v8 rollback.
- Chỉ thử YOLO11s nếu n thiếu chất lượng và s còn đạt tốc độ/VRAM. Candidate
  đạt benchmark vẫn cần gate production R7/R15 trước apply mặc định.
- **Đạt khi:** artifact train thật, config/hash/mapping/metrics đầy đủ, local
  evaluate và rollback bằng weights thật. Nếu không có run thật giữ mở.

### R11 — Luật quan sát được và xe điện (P1, A, sau R4/R5, weights từ R10)

- Kiểm mũ theo vùng đầu, số người theo một xe, posture/crossing theo gate line;
  thiếu chân/mũ khuất/đi bộ/dắt xe/mất track phải unknown/review phù hợp.
- Xe điện dùng model/mapping đã train và duyệt; COCO bicycle/motorcycle không
  đủ kết luận loại động cơ. Chưa có bằng chứng thì ghi unknown, không ép lớp.
- Không thay đổi prediction/evidence lịch sử khi đổi luật/model. Đối chiếu các
  test luật hiện có rồi bổ sung tình huống có nhãn từ video, không viết lại tất cả.
- **Đạt khi:** số đo precision/recall ở mục4 trên tình huống quan sát được;
  unknown được tính/báo, không loại khỏi báo cáo để tăng điểm.

### R12 — Encounter và ghép trước/sau an toàn (P1, A, sau R5/R11)

- Một lượt xe có encounter_id ổn định; late plate/helmet/issues cập nhật cùng
  encounter/event và version, không nhân bản sự kiện/audio intent.
- Dùng cặp lượt trước/sau có nhãn để hiệu chỉnh gate/camera role, thời gian,
  hướng đi và lane mapping. Không so raw pixel giữa hai camera như cùng lane.
- Ghép nhiều ứng viên/thiếu timestamp/bằng chứng mâu thuẫn giữ review; không
  tự gán học sinh. Auto-match tắt tới khi bộ cặp hiệu chỉnh đạt.
- **Đạt khi:** test sát nhau/quay lại cổng/mất track/lỗi đến muộn; cặp video có
  nhãn chứng minh matcher. Hai clip độc lập chỉ chứng minh runtime đa nguồn.

### R13 — Hoàn thiện AI nâng cao trên API thật (P1, B, sau contract R7)

- Giữ menu/redirect/bbox/debug hiện có. Nối import weights và kết quả đánh giá
  từ R7; hiển thị pending/applied/failed/rollback theo ACK/hash runtime.
- Export ZIP có tải HTTP thật, quyền admin, đường dẫn quản lý và dọn theo quota.
  Ảnh bbox cần hỗ trợ asset portable/imported và basename hợp lệ trong allowed
  roots; giữ hash/version/frozen guards, chặn path traversal.
- E2E API thật cho import/metrics/apply/rollback/export/download, role403,
  media lỗi/409, deep link và 320px. Chỉ stub camera trong bài điều hướng;
  bài preview/hiệu năng phải nối camera/video runtime thật.
- **Đạt khi:** thao tác admin đi hết luồng, không nút giả, UI trạng thái khớp
  backend/runtime; build/lint và browser suite đạt. Không thiết kế lại menu lần nữa.

### R14 — 15 video EOF và regression tích hợp (P0 nghiệm thu, B, sau R2–R7)

- Chạy đủ 15 clip đến EOF, tốc độ thời gian thực; log nguồn/hash/FPS/frame count,
  EOF reason, source transitions, detection/OCR/review, latency và disk output.
  Chạy front/rear profiles và two-source test riêng; không tự coi hai clip là cặp.
- Clip thiếu GT chỉ đo hành vi/tốc độ, không accuracy. Chọn encounter được người
  gán nhãn từ R8 để đo toàn chuỗi và ca khó; gồm bỏ sót/review.
- Một full regression sau mỗi đợt tích hợp, Node behavior tests liên quan,
  lint/build, browser với API/media/quyền thật. E2E lịch sử lệch menu/schema cần
  sửa kỳ vọng đúng contract, không xóa test/đổi quyền để xanh.
- **Đạt khi:** report tái lập có baseline/challenger/rollback, không GPU benchmark
  song song pytest, artifact ≤1GiB/run; chưa có clip EOF report thì giữ mở.

### R15 — Camera thật và ca 12 giờ (P0 nghiệm thu, B + người vận hành)

- Hai camera online: chạy 30 phút với 1/2/3 viewer, reconnect/đổi nguồn, kiểm
  frame age, latency và drift RAM/VRAM/disk; rồi ca 12 giờ có log đầu–giữa–cuối.
- Đối chiếu ≥300 lượt có nhãn. Báo số mẫu từng điều kiện, false student match,
  dropped/unreadable/review, luật và tình trạng auto-match. Lưu cấu hình/hash và
  cách rollback; giữ mục pending_camera/pending_data nếu chưa đủ bằng chứng.
- **Đạt khi:** các KPI mục4 đạt bằng dữ liệu/camera thực; full backup restore
  được kiểm; không gọi unit/browser mock là nghiệm thu vận hành.

## 4. KPI giữ nguyên

| Chỉ số | Ngưỡng nghiệm thu |
|---|---|
| ALPR toàn chuỗi trong các biển tự chốt | Exact accuracy ≥95% |
| Coverage trên lượt có biển rõ do người gán nhãn | ≥90%; tính cả bỏ sót/review |
| Hai camera, FPS frame mới | Preview ≥15/camera; AI ≥5/camera |
| Biển từ lúc vào vùng đọc | p95 ≤2 giây |
| Mũ | Precision ≥98%; recall ≥95% |
| Số người/hành vi quan sát được | Precision ≥95%; recall ≥90% |
| Gán học sinh | 0 lỗi quan sát trong holdout ≥300 lượt; công bố số mẫu |
| GPU | Ngân sách khoảng 3,2 GiB tổng; theo dõi Torch và ORT |
| Dung lượng | D ≥30 GiB; warn <15/block <10 hoặc thiếu output |
| QA | ≤1 GiB/run; giữ 3 run, ≥2 backup hoàn chỉnh kiểm restore |

Báo normal/blur/perspective/night/two-line riêng. Không thay KPI toàn chuỗi bằng
mAP detector/CER OCR hoặc chỉ đo trên crop đẹp. Mẫu nhỏ chỉ là smoke/benchmark.

## 5. Lệnh kiểm chứng đã biết

Chạy từ workspace root, Python luôn dùng venv của dự án:

```powershell
venv/Scripts/python.exe -m pytest app/tests --junitxml=tasks/task-05/regression-next.xml -q
venv/Scripts/python.exe -m pytest app/tests/test_latest_capture.py app/tests/test_inference_worker.py app/tests/test_best_plate.py app/tests/test_fast_plate_adapter.py app/tests/test_vehicle_crossing_aggregation.py -q
venv/Scripts/python.exe -B scripts/kaggle_selftest.py
venv/Scripts/python.exe -m pip check
```

Từ thư mục `frontend`:

```powershell
npm run lint
npm run build
npx playwright test --config playwright.task05.config.js
```

CLI curation/export đúng đã ghi ở DATA_REPORT. Không chạy audit cùng output CSV
đang được duyệt. Chưa có harness two-source/EOF đủ nghiệm thu, cần làm R2/R3/R14.

## 6. Phần hoãn và nguồn kỹ thuật

- Hoãn gương, VPS, local training thường trực, nhiều OCR chạy đồng thời trong
  production, lưu mọi crop variant, BoT-SORT/ReID, TensorRT, corner model riêng,
  YOLO11s/model gộp nếu chưa có lợi ích đo được. PaddleOCR chỉ benchmark riêng
  nếu CCT chưa đạt; không làm theo prompt Paddle/3–5 crop cũ trong tasks/todo.
- User đã chọn YOLO11; không tự đổi sang thế hệ mới khác. [YOLO11 official](https://docs.ultralytics.com/models/yolo11/)
  có các model detect/pose riêng; [COCO classes](https://docs.ultralytics.com/datasets/detect/coco/)
  cần đối chiếu mapping, không coi pretrained COCO đã có biển/xe điện riêng.
- CCT theo [FastPlateOCR inference](https://github.com/ankandrew/fast-plate-ocr/blob/master/docs/inference/running_inference.md)
  và package 1.1.0 đã cài. ORT GPU phải theo
  [CUDA/cuDNN compatibility](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html),
  không cài bản GPU mới nhất tùy tiện. Training/resume nguồn cụ thể ở DATA_REPORT.

## 7. Prompt giao Cursor dùng ngay

Bạn tiếp quản School Gate Monitor tại D:\Work\Project_motorbike, branch
codex/alpr-yolo11-local. Hãy hoàn tất phần còn lại theo
tasks/task-05/CURSOR_HANDOFF.md, bắt đầu R0 rồi các task độc lập đúng dependency.
Đọc UI_REPORT, DATA_REPORT, STATUS_BOARD và working diff trước khi sửa. Giữ
mọi thay đổi chưa commit và checklist lịch sử. Phần mới đã có trong working tree
phải được kiểm/chốt tiếp; không dựng lại kiến trúc/menu hoặc báo đã nâng weights
YOLO11 chỉ vì package đã nâng. Tối đa hai luồng: runtime/ALPR và QA/UI/dataset;
mỗi file chung một owner; chỉ một full regression hoặc GPU benchmark cùng lúc.
Chia mỗi lát 1–2 giờ/3–5 file nguồn, focused test, ghi bằng chứng và commit riêng.
Không hạ KPI, không lấy dự đoán làm nhãn, không lấy mock làm nghiệm thu camera,
không tự bật auto-match, không train local khi camera vận hành. Khi thiếu dữ liệu
hay camera, giữ đúng mục pending và làm phần độc lập tiếp. Dùng Kaggle cho train
nặng, artifact/hash/config/metrics/rollback thật; registry chỉ applied khi runtime
ACK. Cập nhật tasks/task-05/todo.md và chỉ mục tasks/todo.md sau từng lát; kết thúc
mỗi đợt bằng báo cáo mã/test/video/camera, tốc độ/chất lượng/dung lượng và việc
còn mở. Bắt đầu bằng xác minh isolation và chạy lại full suite sau 59 test fixture
đã sửa, rồi chốt harness EOF/two-source, voting/CCT, model import/apply và dữ liệu.
