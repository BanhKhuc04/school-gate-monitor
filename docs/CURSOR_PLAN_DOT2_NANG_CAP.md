# Kế hoạch nâng cấp Smart School Gate — Đợt 2 (độ tin cậy biển số, 2 camera, lưu trữ, backup)

> **GỬI CURSOR: Bước 1 đã code xong + 87 test pass (commit `51d418d`). Đọc
> `DEVELOPMENT_HANDOVER.md` mục "SESSION LOG — 2026-09-29 (đợt 2, Bước 1)" để biết
> chính xác đã làm gì trước khi đọc tiếp plan này. BẮT ĐẦU TỪ BƯỚC 3.**
> Có video thật để test pipeline (không cần camera vật lý) tại
> `C:\Users\khucv\Downloads\tranning\` — 14 file `.mp4`, 1280x720 30fps, quay cổng
> trường thật có xe máy qua lại. Set `CAMERA_SOURCE=<đường dẫn 1 file>.mp4` và
> `CAMERA_LOOP=1` để pipeline đọc lặp lại file này như 1 camera sống — dùng để
> verify Bước 3 (ghép 2 camera: set `CAMERA_SOURCE` + `CAMERA_SOURCE_SECONDARY`
> trỏ tới 2 file khác nhau để giả lập 2 góc camera), và benchmark Bước 7.

## Context

Dự án đã có 1 nền tảng hoạt động đầy đủ (64/64 test pass, commit `9d81244`): pipeline CV (helmet/plate/pose/OCR), quản lý xe-học sinh, lịch sử vi phạm + audit trail, 4 vai trò phân quyền, health/cleanup cơ bản. `DEVELOPMENT_HANDOVER.md` đã audit chính xác trạng thái từng phần.

Người dùng muốn nâng cấp tiếp theo hướng production-ready hơn: biển số đọc chính xác + biết khi nào KHÔNG chắc chắn (không tự đoán), 2 camera trước/sau ghép đúng 1 lượt xe (không tự đoán khi mơ hồ), lưu trữ có kiểm soát dung lượng (kể cả ghi hình liên tục), backup an toàn cho SQLite đang chạy, tất cả **tái dùng tối đa code/pattern đã có**, không thêm dependency khi stdlib/code sẵn có đủ dùng, và triển khai từng lát mỏng — mỗi bước tự chạy test + commit + cập nhật `DEVELOPMENT_HANDOVER.md` trước khi sang bước kế.

Nguyên tắc xuyên suốt: **reuse > extend > refactor > build new**. Phần liên quan tới mất dữ liệu, ghép sai xe (correlation), và backup ưu tiên đúng-đắn hơn số dòng code ngắn gọn — chấp nhận thêm 1 chút code nếu đó là cách an toàn hơn.

---

## Bước 0 (nền tảng, gộp vào Bước 1) — thêm cột còn thiếu cho `violation_events`

Trước khi làm gì, phát hiện quan trọng: **`violation_events` hiện KHÔNG có cột `gate_id`** — không biết bản ghi nào đến từ camera nào. Đây là điều kiện tiên quyết bắt buộc cho Bước 3 (ghép 2 camera), nên thêm ngay trong migration của Bước 1 để không phải sửa `add_violation_event()`/`_persist_violation()` 2 lần.

---

## Bước 1 — Đa khung hình + confidence score cho biển số + trạng thái "cần kiểm tra" ✅ ĐÃ XONG (commit `51d418d`)

**Vấn đề hiện tại** (đã verify qua đọc code): `_process_violations()` gọi `self._read_plate_cached()` → trả về 1 chuỗi text duy nhất từ `read_plate()` (không có confidence). `read_plate_detailed()` đã tồn tại sẵn trong `app/cv/ocr.py` (trả `{'full', 'top_line', 'bottom_line', 'confidence'}`) nhưng **không được gọi ở đâu**. `Detection.confidence` (của box biển số YOLO) cũng bị bỏ qua. Không có khái niệm "không chắc chắn" — mọi kết quả OCR đọc được đều bị coi là đúng tuyệt đối, kể cả khi tra whitelist.

**Thiết kế (module tách riêng để sau này thay implementation dễ dàng, đúng yêu cầu):**

File mới `app/cv/plate_voter.py`:
```python
@dataclass
class PlateReadResult:
    text: str              # biển số đã normalize, "" nếu không đọc được
    confidence: float      # 0.0-1.0, trung bình từ read_plate_detailed()
    sample_count: int      # số lần đọc giống nhau trong cửa sổ voting
    is_confident: bool     # True nếu đủ điều kiện để tin dùng (xem ngưỡng dưới)

class PlateVoter:
    """Vote biển số qua nhiều lần đọc gần nhau về thời gian + vị trí.
    Thay thế logic cache đơn giản cũ (_plate_ocr_cache: 1 giá trị/vị trí) bằng
    rolling window nhiều mẫu/vị trí — vẫn dùng chung 1 khái niệm "ô lưới vị trí"
    (_OCR_CACHE_GRID) đã có, không đổi cách nhóm."""
    def __init__(self, grid_px: int, window_sec: float, min_agree: int, min_confidence: float): ...
    def read(self, frame, plate_det, ocr_fn) -> PlateReadResult:
        """ocr_fn: callable(crop) -> {'full', 'confidence'} — tiêm read_plate_detailed
        vào đây thay vì import cứng, để sau này đổi OCR engine chỉ cần đổi callable."""
```

Logic quyết định `is_confident`: đủ điều kiện tin dùng nếu (a) cùng 1 text xuất hiện ≥ `PLATE_VOTE_MIN_AGREE` lần trong cửa sổ `PLATE_VOTE_WINDOW_SEC`, HOẶC (b) 1 lần đọc có `confidence ≥ PLATE_MIN_CONFIDENCE_SINGLE` (đọc rõ ngay từ đầu, không cần chờ vote). Nếu không đủ điều kiện → `is_confident=False`, **KHÔNG được gọi `get_vehicle_by_plate()`** (đây là chỗ áp dụng "không tự đoán" — tránh gán nhầm 1 học sinh vì đọc sai 1 ký tự).

**File sửa `app/cv/pipeline.py`:**
- `_read_plate_cached()` đổi tên thành `_read_plate_voted()`, dùng `PlateVoter` (khởi tạo 1 instance/pipeline trong `__init__`, thay `self._plate_ocr_cache: dict` bằng `self._plate_voter = PlateVoter(...)`). Trả về `PlateReadResult` thay vì `str`.
- `_process_violations()`: đọc `result = self._read_plate_voted(frame, best_plate)`. Nếu `result.is_confident`: giữ nguyên toàn bộ logic cũ (tra whitelist, `PLATE_NOT_REGISTERED`...). Nếu KHÔNG confident và `result.text` không rỗng: **bỏ qua bước tra whitelist**, set `plate_matched=None`, thêm cờ `needs_review=True`.
- `_persist_violation()`/`add_violation_event()` thêm 2 tham số: `plate_confidence: float`, `gate_id: str` (giá trị `self.gate_id`, có sẵn trên instance). Nếu `needs_review=True` khi gọi `add_violation_event`, truyền `status='needs_review'` thay vì để mặc định `'pending'`.

**Schema (`app/db.py::init_db()`, thêm vào block migration ALTER TABLE — đúng pattern try/except đã có):**
```python
ALTER TABLE violation_events ADD COLUMN plate_confidence REAL
ALTER TABLE violation_events ADD COLUMN gate_id TEXT
```
`add_violation_event()` thêm 2 param `plate_confidence: float = None, gate_id: str = None`, insert vào 2 cột mới — **không đổi cột nào đã có, không rename**. `status` column vốn không có CHECK constraint ở DB (verify qua `init_db()`) — thêm giá trị `'needs_review'` KHÔNG cần migration, chỉ cần code Python cho phép giá trị này khi tạo mới.

**Config mới (`app/config.py`):**
```python
PLATE_VOTE_WINDOW_SEC = 2.5
PLATE_VOTE_MIN_AGREE = 2
PLATE_MIN_CONFIDENCE_SINGLE = 0.55
```

**API/Frontend (tái dùng UI Feature 10 đã có, không tạo màn hình mới):**
- `app/api/admin.py::list_violations` — thêm param `status: str = None` filter (đúng pattern dynamic-WHERE đã có trong `db.py::list_violations`), để lọc riêng "cần kiểm tra".
- `frontend/src/pages/AdminViolationsPage.jsx::STATUS_COLORS` — thêm entry `needs_review` (màu tím/violet để phân biệt trực quan với `pending` màu vàng — không phải "chưa ai xem" mà là "AI không chắc").
- Modal chi tiết: hiện thêm `plate_confidence` (dạng %) khi có giá trị, để người xử lý biết vì sao rơi vào needs_review.

**Test:** `app/tests/test_plate_voter.py` mới (pure unit test, không cần mock model — `PlateVoter` nhận `ocr_fn` giả lập) — case: 1 lần đọc confidence cao → confident ngay; 2 lần đọc giống nhau confidence thấp → confident qua vote; đọc lệch nhau liên tục → không bao giờ confident. Mở rộng `test_vehicle_gate.py`: case `plate_confidence` thấp → `plate_matched` phải là `None` dù DB có xe khớp y hệt text đọc được (chứng minh KHÔNG tự đoán).

**Acceptance criteria:** (1) biển đọc 1 lần rõ nét (confidence cao) vẫn nhanh như cũ, không delay thêm; (2) biển mờ/đọc lệch nhiều lần → `status='needs_review'`, không tự gán vào học sinh nào; (3) toàn bộ 64 test cũ vẫn pass; (4) verify tay: tạo violation qua dev-trigger hoặc mock, xem đúng badge "Cần kiểm tra" + confidence % trong UI.

**Rủi ro regression:** `_read_plate_cached` đổi return type (str → object) — mọi call site khác phải rà lại (hiện chỉ có 1 call site trong `_process_violations`, đã verify). Test cũ `test_vehicle_gate.py` mock `_read_plate_cached` trả string trực tiếp — cần cập nhật mock trả `PlateReadResult` tương ứng, nếu không sẽ fail ngay (đã lường trước, đưa vào phần Test ở trên).

---

## Bước 2 — (đã gộp vào Bước 1) ✅ ĐÃ XONG

`needs_review` dùng chung `status` column + `STATUS_COLORS` + `PATCH /violations/{id}/status` + audit log đã có sẵn từ Feature 10 — không có việc riêng nào ngoài Bước 1.

---

## Bước 3 — Ghép 1 lượt xe từ 2 camera (trước + sau)

**Thiết kế:** không tạo bảng "vehicle_events" mới (không cần abstraction tách biệt khỏi violation) — mở rộng `violation_events` bằng 2 cột tự tham chiếu, ghép SAU khi cả 2 bản ghi đã tồn tại (loose coupling, 2 pipeline gate vẫn chạy độc lập hoàn toàn như hiện tại, không cần giao tiếp trực tiếp giữa 2 thread).

**Schema (`init_db()` ALTER TABLE):**
```python
ALTER TABLE violation_events ADD COLUMN linked_violation_id INTEGER
ALTER TABLE violation_events ADD COLUMN correlation_status TEXT
```
`correlation_status`: `NULL` (chưa thử ghép — trường hợp chỉ có 1 gate hoặc gate thứ 2 tắt), `'unmatched'` (đã thử, không tìm thấy ứng viên), `'matched'` (đã ghép, `linked_violation_id` trỏ sang bản ghi ở gate kia), `'needs_review'` (có ứng viên nhưng độ tin cậy chưa đủ để tự ghép — **không tự đoán**).

**File mới `app/cv/event_correlator.py`:**
```python
def find_correlation_candidate(new_event: dict, window_sec: float) -> tuple[Optional[dict], str]:
    """Trả về (candidate_row | None, correlation_status).
    Query violation_events cùng thời gian ±window_sec, gate_id KHÁC new_event['gate_id'],
    linked_violation_id IS NULL (chưa bị ghép với ai khác).
    Chấm điểm mỗi ứng viên: plate giống hệt (sau normalize) = điểm cao nhất;
    similarity qua difflib.SequenceMatcher (stdlib, không thêm dependency) nếu KHÁC
    nhau ít (vd. đọc lệch 1 ký tự) = điểm trung bình; cả 2 events đều status
    'needs_review' (chưa chắc plate) → không bao giờ tự ghép, luôn trả 'needs_review'.
    """
```

**File sửa `app/cv/pipeline.py::_persist_violation`:** sau khi `add_violation_event()` trả về `id` mới, gọi `try_correlate(new_id)` (submit tiếp trong cùng `_io_pool` — không thêm thread mới) — cập nhật `correlation_status`/`linked_violation_id` cho CẢ 2 bản ghi (2 UPDATE, 1 hàm mới `db.py::link_violation_events(id_a, id_b)` dùng `_write_lock` như mọi hàm ghi khác).

**Config mới:** `CORRELATION_TIME_WINDOW_SEC = 15`, `CORRELATION_MIN_SIMILARITY = 0.85` (ngưỡng `difflib.SequenceMatcher.ratio()`).

**API/Frontend:** `GET /api/violations` trả thêm `linked_violation_id`/`correlation_status` (tự động vì `SELECT ve.*`). `ViolationDetailModal` thêm dòng "Ghép với cổng kia: #123 (đã khớp)" / "Chưa rõ — cần kiểm tra" khi có giá trị, click mở luôn violation kia trong modal khác (tái dùng modal đã có, chỉ đổi `violationId` đang xem).

**Test:** `app/tests/test_event_correlator.py` — case: 2 event cùng biển số trong window → matched; biển lệch 1 ký tự, similarity cao → matched; biển khác hẳn → unmatched; 1 trong 2 event có status needs_review (Bước 1) → luôn needs_review, không bao giờ tự ghép nhầm.

**Acceptance criteria:** (1) chỉ 1 camera bật (cấu hình hiện tại) → `correlation_status` luôn NULL, hành vi cũ không đổi gì; (2) 2 event trùng biển số trong 15s → tự ghép đúng; (3) không có case nào tự ghép sai 2 biển số khác nhau hoàn toàn (test âm phải có); (4) toàn bộ test cũ (bao gồm Bước 1) vẫn pass.

**Rủi ro regression:** Đây là điểm nhạy cảm nhất về correctness theo đúng cảnh báo của người dùng — ưu tiên viết test case "không được ghép sai" nhiều hơn test "ghép đúng". Vì chạy trong `_io_pool` (1 worker/gate, 2 gate = 2 pool riêng), 2 event từ 2 gate có thể race nhau khi cùng cố ghép — dùng `_write_lock` chung của `db.py` (đã có sẵn, dùng chung cho mọi hàm ghi) để tránh ghi đè lẫn nhau.

---

## Bước 4 — Tự động dọn dữ liệu cũ (background thread, không thêm dependency)

**Thiết kế:** tái dùng nguyên `get_old_violation_media_paths()`/`clear_violation_snapshot_paths()` đã có (Feature 8) — chỉ đổi cách TRIGGER từ "admin bấm nút" sang "tự động theo lịch", cộng thêm audit log + lock + graceful shutdown theo đúng yêu cầu.

**File mới `app/background.py`:**
```python
class MaintenanceWorker:
    """Thread nền chạy các job bảo trì định kỳ (dọn dẹp, backup — Bước 6 dùng chung).
    Pattern giống hệt VideoPipeline: threading.Thread(daemon=True) + cờ _running +
    join() khi stop() để graceful shutdown, không phải thread mồ côi."""
    def __init__(self):
        self._running = False
        self._thread = None
        self._job_lock = threading.Lock()  # chống chạy đè khi job trước chưa xong

    def start(self): ...  # giống VideoPipeline.start()
    def stop(self): ...   # giống VideoPipeline.stop() — join(timeout=...)
    def _run_loop(self):
        while self._running:
            self._run_job_safely(self._cleanup_job)
            # Bước 6 sẽ thêm self._run_job_safely(self._backup_job) ở đây
            time.sleep(CLEANUP_INTERVAL_HOURS * 3600)

    def _run_job_safely(self, job_fn):
        if not self._job_lock.acquire(blocking=False):
            return  # job trước còn chạy — bỏ qua lần này, không xếp hàng chồng
        try:
            job_fn()
        except Exception as e:
            print(f"[Maintenance] Job {job_fn.__name__} failed: {e}")  # exception isolation
        finally:
            self._job_lock.release()
```

**Audit log cho tác vụ hệ thống:** bảng mới nhỏ `system_maintenance_log` (id, job_name, started_at, finished_at, success, detail_json) — KHÔNG dùng chung `violation_audit_log` vì bảng đó có FK bắt buộc tới `violation_id`, không hợp với job không gắn 1 violation cụ thể. `app/db.py` thêm `log_maintenance_run(job_name, success, detail: dict)`.

**File sửa `app/main.py::lifespan`:** start `MaintenanceWorker` cùng lúc với `start_all_pipelines()`, stop cùng lúc shutdown — tái dùng đúng vị trí/pattern đã có, không thêm cơ chế khởi động riêng.

**API mới:** `GET /api/system/maintenance-log?limit=20` (admin) — xem lịch sử chạy tự động, tái dùng pattern list đơn giản như `get_violation_audit_log`.

**Config:** `CLEANUP_ENABLED=True`, `CLEANUP_INTERVAL_HOURS=24`, `CLEANUP_RETENTION_DAYS=90` (tách khỏi con số hardcode 90 đang nằm rải rác trong API).

**Test:** `test_maintenance_worker.py` — job lock chặn chạy đè (giả lập job chậm bằng `time.sleep` ngắn trong thread test), exception trong job không làm chết `_run_loop` (job thứ 2 vẫn chạy được sau khi job 1 raise), `log_maintenance_run` ghi đúng.

**Acceptance criteria:** cleanup thủ công qua nút bấm (Feature 8 cũ) vẫn hoạt động y hệt song song; tắt `CLEANUP_ENABLED` → không có thread nào chạy job tự động; dry-run vẫn khả dụng qua endpoint preview cũ (không đổi).

**Rủi ro regression:** thấp — không đụng logic cleanup thật, chỉ thêm lớp lịch/lock/log bọc ngoài hàm đã có sẵn và đã có test.

---

## Bước 5 — Thống kê dung lượng đĩa thật (stdlib, không thêm dependency)

**File sửa `app/api/system.py`:** thêm `shutil.disk_usage(SNAPSHOTS_DIR)` (stdlib, 1 dòng) vào `HealthResponse`: `disk_total_mb`, `disk_used_mb`, `disk_free_mb`. Mở rộng `_snapshots_size_mb()` thành trả thêm breakdown theo phần mở rộng file (`.jpg` = ảnh, `.mp4` = clip vi phạm, sau Bước 7 thêm thư mục `data/recordings/` = ghi hình liên tục) — mỗi loại 1 con số riêng thay vì gộp chung `snapshot_size_mb`.

**Frontend `AdminHealthPage.jsx`:** thêm 3 stat-cell mới (tổng/đã dùng/còn trống) dùng đúng pattern `bg-[#f4f6f9] rounded-xl` đã có, và 1 breakdown nhỏ (ảnh/clip vi phạm/ghi liên tục) dạng list thay vì chart mới.

**Test:** mở rộng `test_system.py::test_health_admin_ok` — assert có đủ field mới, `disk_free_mb >= 0`.

**Acceptance criteria:** health page hiện đúng dung lượng đĩa thật của máy chạy dev; field cũ (`db_size_mb`, `snapshot_count`...) không đổi giá trị/tên.

**Rủi ro regression:** rất thấp — chỉ thêm field, không đổi field cũ.

---

## Bước 6 — Backup SQLite an toàn (không copy file thô khi đang ghi)

**Vấn đề:** copy trực tiếp `data/app.db` bằng `shutil.copy` trong lúc pipeline đang ghi (WAL/journal có thể đang mở) có rủi ro backup ra file hỏng/thiếu transaction dở dang.

**Giải pháp đúng:** dùng chính SQLite Online Backup API qua stdlib `sqlite3.Connection.backup()` (có từ Python 3.7, chính là API `.backup()` được SQLite team làm ra riêng cho việc "backup DB đang chạy" — không phải giải pháp tự chế).

**File sửa `app/db.py`:**
```python
def backup_database(dest_path: str) -> None:
    """Backup an toàn app.db đang chạy, dùng SQLite online backup API — không copy
    file thô (rủi ro đọc giữa lúc ghi dở). Chặn bởi _write_lock để không backup
    giữa lúc có transaction ghi đang mở (an toàn kép, dù .backup() tự nó đã an toàn)."""
    with _write_lock:
        source = get_connection()
        try:
            dest = sqlite3.connect(dest_path)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
```

**File mới trong `app/background.py::MaintenanceWorker._backup_job`:** gọi `backup_database()` ra `data/backups/app_{timestamp}.db`, dọn backup cũ hơn N bản (giữ ví dụ 14 bản gần nhất — reuse pattern glob+sort theo mtime như cleanup). Media backup (`data/snapshots/`) **configurable, tắt mặc định** (`BACKUP_MEDIA_ENABLED=False` — dung lượng lớn, không phải ai cũng cần), khi bật dùng `shutil.copytree(dirs_exist_ok=True)` đơn giản, không đồng bộ incremental phức tạp.

**Config:** `BACKUP_ENABLED=True`, `BACKUP_INTERVAL_HOURS=24`, `BACKUP_KEEP_COUNT=14`, `BACKUP_DIR`, `BACKUP_MEDIA_ENABLED=False`.

**API:** `POST /api/system/backup/run` (admin, chạy tay ngay lập tức, không chờ lịch) + `GET /api/system/backup/list` — tái dùng style route như cleanup preview/run đã có.

**Test:** `test_backup.py` — backup ra file, mở file backup bằng connection mới, query `SELECT COUNT(*) FROM violation_events` khớp với DB gốc; backup trong lúc có 1 thread khác đang `add_violation_event()` liên tục (giả lập concurrent write) → backup không exception, dữ liệu đọc lại được toàn vẹn (không cần khớp tuyệt đối số dòng vì có thể chạy giữa lúc ghi, chỉ cần không lỗi/không corrupt).

**Acceptance criteria:** backup file mở được, dữ liệu đọc lại đúng; backup không làm pipeline camera bị đứng khung hình đáng kể (đo `last_frame_age_sec` trước/sau lúc backup chạy).

**Rủi ro regression:** thấp — hàm mới, không đụng code cũ. Rủi ro thật nằm ở vận hành (quên bật `BACKUP_ENABLED` trên máy thật) — ghi rõ trong `DEVELOPMENT_HANDOVER.md` sau khi xong.

---

## Bước 7 — Ghi hình liên tục (continuous recording), chia đoạn, có công tắc bật/tắt

**Đây là hạng mục nặng nhất — làm ĐÚNG như yêu cầu (không lược bỏ), nhưng mặc định TẮT cho tới khi có số đo thật.**

**File mới `app/cv/recorder.py`:**
```python
class ContinuousRecorder:
    """Ghi hình liên tục độc lập với luồng AI detect — nhận MỌI frame đọc từ camera
    (kể cả frame bị FRAME_SKIP bỏ qua hay không có person), không được làm chậm
    vòng lặp đọc camera chính. Chạy trên 1 thread + queue riêng (maxsize nhỏ,
    drop-frame khi đầy — thà mất vài frame ghi hình còn hơn làm nghẽn AI pipeline)."""
    def __init__(self, gate_id: str, segment_minutes: int, fps: int, width: int, height: int):
        self._queue = queue.Queue(maxsize=4)
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._current_writer = None
        self._segment_start = None

    def push_frame(self, frame): 
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass  # drop — không bao giờ block caller

    def _writer_loop(self): ...  # rotate file mỗi segment_minutes, resize trước khi ghi
    def stop(self): ...  # đóng writer hiện tại triệt để trước khi thread thoát (graceful)
```

**File sửa `app/cv/pipeline.py::_run_loop`:** ngay sau `frame = self._webcam.read_frame()` (dòng đầu vòng lặp, TRƯỚC mọi nhánh `continue` của FRAME_SKIP/no-person) — nếu `self._recorder` tồn tại: `self._recorder.push_frame(frame)`. Đây là ĐIỂM MẤU CHỐT: continuous recording phải nằm trước mọi early-return, khác hẳn `_clip_buffer` (chỉ append ở nhánh đã qua detect đầy đủ) — 2 cơ chế độc lập nhau, không dùng chung buffer.

`VideoPipeline.__init__`: tạo `self._recorder = ContinuousRecorder(...) if CONTINUOUS_RECORDING_ENABLED else None`. `stop()`: gọi `self._recorder.stop()` nếu có, đảm bảo segment cuối được finalize (writer.release()) trước khi tiến trình tắt.

**Lưu trữ:** `data/recordings/{gate_id}/{YYYYMMDD_HHMMSS}.mp4`, resize xuống độ phân giải thấp hơn hiển thị (giống cách `_clip_buffer` đã làm — mặc định 854×480 hoặc thấp hơn, **cần benchmark để chọn số cuối**), FPS ghi thấp hơn FPS đọc camera thật (mặc định 10fps — đủ xem lại, giảm đáng kể CPU encode + dung lượng so với ghi full framerate).

**Retention riêng** (KHÔNG dùng chung policy với violation evidence — đây chính là lý do #6 trong yêu cầu gốc muốn "phân tầng theo loại dữ liệu", tự nhiên tách ra vì continuous recording không có bản ghi DB, chỉ có file): job dọn riêng trong `MaintenanceWorker` (Bước 4), glob theo mtime, xóa file cũ hơn `CONTINUOUS_RECORDING_RETENTION_DAYS` (mặc định 7).

**Config:**
```python
CONTINUOUS_RECORDING_ENABLED = False   # mặc định TẮT — bật sau khi có số đo
CONTINUOUS_RECORDING_SEGMENT_MINUTES = 5
CONTINUOUS_RECORDING_FPS = 10
CONTINUOUS_RECORDING_WIDTH = 854
CONTINUOUS_RECORDING_HEIGHT = 480
CONTINUOUS_RECORDING_RETENTION_DAYS = 7
```

**Đo đạc bắt buộc trước khi đổi mặc định sang `True`** (đúng yêu cầu): viết `scripts/benchmark_recording.py` — chạy pipeline với recording OFF rồi ON (cùng nguồn video test, cùng thời lượng), so sánh `get_status()['fps']`/`avg_process_latency_ms` giữa 2 lần chạy + CPU% (đo qua `psutil` **nếu đã có sẵn trong requirements, nếu chưa thì đo qua `time` thô, không thêm dependency mới chỉ để đo**) + dung lượng file/phút. Kết quả in ra bảng, báo lại người dùng trước khi đổi `CONTINUOUS_RECORDING_ENABLED` mặc định hay khuyến nghị bật ở máy thật.

**API/Frontend:** `AdminHealthPage.jsx` thêm toggle hiển thị trạng thái recording mỗi gate (on/off, dung lượng đang chiếm, tuổi segment hiện tại) — chỉ hiển thị, việc bật/tắt thật sự qua config/env (không cần UI runtime-toggle ở bước này, tránh over-engineer khi chưa rõ nhu cầu vận hành thật).

**Test:** `test_recorder.py` — `push_frame` không block khi queue đầy (đo thời gian gọi phải cực nhanh dù queue full), segment rotate đúng sau `segment_minutes` (giả lập bằng cách set `segment_minutes` rất nhỏ trong test), `stop()` để lại file hợp lệ (đọc lại bằng `cv2.VideoCapture` xác nhận mở được, không phải file rỗng/hỏng).

**Acceptance criteria:** (1) `CONTINUOUS_RECORDING_ENABLED=False` (mặc định) → hành vi hệ thống y hệt trước Bước 7, 0 thay đổi quan sát được; (2) bật `True` trong môi trường test → có file `.mp4` xuất hiện đúng thư mục, đúng độ dài segment; (3) có báo cáo benchmark số liệu thật kèm theo trước khi khuyến nghị bật mặc định; (4) tắt app (`Ctrl+C`/lifespan shutdown) không để lại file segment dở/hỏng.

**Rủi ro regression:** cao nhất trong cả 7 bước nếu benchmark cho thấy ảnh hưởng AI pipeline đáng kể — theo đúng yêu cầu người dùng, **dừng lại báo số liệu, không tự ý đổi scope** (ví dụ không tự ý giảm xuống "chỉ ghi khi có người" — đó là đổi từ continuous sang event-based, ngoài phạm vi đã chốt).

---

## Trình tự thực thi & xác nhận sau mỗi bước

Mỗi bước: code → `pytest app/tests/ -v` (phải pass hết, bao gồm test cũ) → verify tay qua browser nếu có phần UI → **commit riêng** (không gộp 2 bước vào 1 commit) → cập nhật `DEVELOPMENT_HANDOVER.md` (mục 5 Feature Status, mục 15 Completed Development thêm dòng, mục 24 Current Handover Summary) → mới sang bước kế tiếp.

Thứ tự: **Bước 1 → Bước 3 → Bước 4 → Bước 5 → Bước 6 → Bước 7**, đúng theo mức độ phụ thuộc (Bước 3 cần `gate_id`/`plate_confidence` từ Bước 1; Bước 4/5/6 độc lập nhau, làm trước Bước 7 vì Bước 7 sẽ tận dụng lại `MaintenanceWorker` của Bước 4 cho việc dọn recording cũ).
