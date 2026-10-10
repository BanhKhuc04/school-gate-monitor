# Sửa 8 lỗi/thiếu tính năng hệ thống giám sát cổng trường

> Tài liệu này viết để đưa cho Cursor thực thi toàn bộ trong 1 lần, theo đúng thứ tự Ưu tiên 1 → 8 (phần sau phụ thuộc kỹ thuật vào phần trước, không làm tắt/nhảy cóc). Mỗi phần nêu rõ: lỗi hiện tại (kèm file:line), nguyên nhân gốc, và cách sửa cụ thể. Sau khi code xong TỪNG Ưu tiên, tự chạy kiểm tra theo mục Verification tương ứng ở cuối file trước khi sang phần kế — nếu 1 phần không tự test được (cần camera/video thật), ghi rõ trong báo cáo cuối cùng để người dùng tự test tay.

## Context
Test thực tế phát hiện 8 vấn đề. Khảo sát code xác nhận nguyên nhân gốc của phần lớn (#1, #3, #4) đều là **hệ thống không có object tracking** — mỗi frame xử lý độc lập, gán helmet/biển số/loại xe vào người bằng khoảng cách x-center gần nhất trong `_group_by_person()` (app/cv/pipeline.py:538-611), không có ID xuyên suốt nhiều khung hình. Khi 2 người đứng/đi gần nhau (1 dắt xe, 1 đi bộ, hoặc 2 xe chen nhau), khoảng cách x-center có thể khớp nhầm người này với biển số/xe của người kia — đúng như báo cáo.

Quyết định: **làm tracking trước tiên** làm nền tảng, vì #1/#3/#4 đều sửa dễ hơn nhiều khi có ID ổn định.

---

## Ưu tiên 1 — Object tracking xuyên suốt frame (nền tảng cho #1, #3, #4)

**Hiện tại**: app/cv/detector.py:49 gọi `self.model(frame, ...)` — chế độ predict thường, không giữ trạng thái. Không có `.track()` ở đâu trong repo.

**Cách sửa**: Ultralytics YOLO đã hỗ trợ sẵn tracking qua `model.track(frame, persist=True, tracker="bytetrack.yaml")` — không cần thêm thư viện. Chỉ cần bật cho **person detector** (model COCO đang dùng để detect cả `person` lẫn `motorcycle`/`bicycle`, xem pipeline.py:356-357) — track_id của person sẽ theo luôn cả xe (vì cùng 1 lần gọi track() trên cùng model COCO đã trả cả 2 lớp có ID riêng biệt).

1. `app/cv/detector.py`: thêm field `track_id: int | None = None` vào `Detection` dataclass, và method mới `detect_tracked(frame) -> List[Detection]` dùng `self.model.track(frame, persist=True, verbose=False, conf=self.conf_threshold, tracker="bytetrack.yaml")`, đọc `box.id` (có thể `None` vài frame đầu tracker chưa confirm — giữ `track_id=None` lúc đó, groups vẫn hoạt động như cũ bằng nearest-neighbor cho tới khi có ID).
2. `app/cv/pipeline.py:351`: đổi `self._person_detector.detect(detect_frame)` → `self._person_detector.detect_tracked(detect_frame)`.
3. `_group_by_person()` (pipeline.py:538): thêm `'track_id': person.track_id` vào dict trả về mỗi group — vẫn giữ nguyên logic gán helmet/plate/vehicle bằng khoảng cách như cũ (đơn giản, đã đủ chính xác trong 1 frame), track_id chỉ dùng để **nhớ giữa các frame**, không thay thế phép gán trong-frame.
4. Cooldown/dedup (pipeline.py:770-776): hiện `cooldown_key = plate_matched or "UNKNOWN"` — **bug tiềm ẩn nghiêm trọng**: mọi vi phạm không đọc được/không khớp biển số dùng chung 1 khoá `"UNKNOWN"`, nghĩa là sau 1 vi phạm loại này, MỌI vi phạm loại này của người khác trong 60s tiếp theo bị bỏ qua (mất log). Sửa: `cooldown_key = plate_matched or (f"track:{track_id}" if track_id is not None else "UNKNOWN")`.

**Kết quả:** mỗi người có ID ổn định qua nhiều frame → các phần dưới đây (#3 dedup TTS, #plate voting) dùng chung ID này thay vì đoán lại mỗi frame.

---

## Ưu tiên 2 — Đọc biển số xe đi nhanh/chậm không nhận diện được (#2)

**Hiện tại**: `PlateVoter` (app/cv/plate_voter.py) vote theo **vị trí lưới 60px** (`grid_px=60`, pipeline.py:128), cần ≥2 lần đọc khớp nhau trong cửa sổ 2.5s (`PLATE_VOTE_MIN_AGREE=2`, `PLATE_VOTE_WINDOW_SEC=2.5`, app/config.py:149-150) để tin cậy — nếu không đủ 2 mẫu thì rơi về ngưỡng đơn `PLATE_MIN_CONFIDENCE_SINGLE=0.55`. Cộng thêm `FRAME_SKIP=2` (chỉ xử lý 1/2 frame, config.py:105) và EasyOCR tốn 300-800ms/lần — xe đi nhanh có thể lọt qua khung hình chưa kịp tích đủ 2 mẫu, và biển số mờ do chuyển động không đạt 0.55.

**Cách sửa** (tận dụng track_id từ Ưu tiên 1):
1. Đổi khoá vote trong `PlateVoter` từ vị trí lưới sang `track_id` của person/vehicle được gán biển số đó — vote theo **danh tính** thay vì **vị trí**, không bị lệch khi xe di chuyển nhanh qua nhiều ô lưới trong 2.5s.
2. Thêm theo dõi tốc độ di chuyển đơn giản: so `bbox` của cùng track_id giữa 2 frame liên tiếp → nếu delta lớn (xe đi nhanh), tạm thời set `FRAME_SKIP` hiệu lực về 1 (không skip) cho các frame có track_id đó đang active — xử lý mọi frame khi có xe đang di chuyển nhanh trong khung hình, quay lại skip bình thường khi vắng.

---

## Ưu tiên 3 — Nhầm lẫn người đi bộ / người đi xe khi đứng gần nhau (#1, #3 chung nguyên nhân)

Chính là hệ quả của #1 — sau khi có track_id (Ưu tiên 1), thêm 1 bước làm mượt: thay vì tin 100% kết quả gán vehicle_type của **1 frame hiện tại**, giữ 1 dict `_track_vehicle_type: dict[track_id, str]` cập nhật kiểu **vote đa số theo N frame gần nhất** (giống cách plate đã vote) — 1 frame gán nhầm xe của người bên cạnh sẽ bị đa số các frame đúng lấn át, thay vì lập tức đổi is_riding/is_walking chỉ vì 1 frame lỗi.

---

## Ưu tiên 4 — Cảnh báo giọng nói đọc chồng/spam khi đông người (#4)

**Hiện tại**: frontend/src/components/AlertBanner.jsx:102-118 gọi `speakVietnamese()` cho **mọi** WS message không dedup. frontend/src/utils/speak.js:28 gọi `window.speechSynthesis.cancel()` trước mỗi câu mới → **cắt ngang** câu đang đọc thay vì xếp hàng, nên khi nhiều vi phạm dồn dập, câu trước bị cắt nham nhở, người nghe không rõ ai vừa vi phạm gì.

**Cách sửa**:
1. `speak.js`: đổi cơ chế từ cancel-and-replace sang **hàng đợi** (mảng `queue`, phát tuần tự bằng sự kiện `utterance.onend` gọi phát câu tiếp theo) — bỏ dòng `speechSynthesis.cancel()`. Giới hạn hàng đợi tối đa ~3 câu (nếu vượt, bỏ câu cũ nhất — xe đã đi qua rồi đọc trễ vô nghĩa).
2. Dedup theo track_id: dùng `track_id` đính kèm trong payload alert (backend cần thêm `track_id` vào WS payload alert, xem `_push_alert`/websocket broadcast trong pipeline.py) — chỉ đọc **1 lần** cho mỗi người (track_id) trong phiên xuất hiện trước cổng, dù người đó có nhiều vi phạm liên tiếp bị log (đã có ALERT_COOLDOWN=5s nhưng không theo ID nên vẫn có thể đọc lại nếu >5s mà người đó chưa đi khỏi khung hình).
3. Rút gọn câu đọc trong `buildSpeechText()` (AlertBanner.jsx:31-54) — ví dụ bỏ chữ "Cảnh báo:" lặp lại đầu mỗi câu khi đọc liên tiếp nhiều câu trong hàng đợi (chỉ giữ ở câu đầu tiên của 1 đợt).

---

## Ưu tiên 5 — Ảnh chụp vi phạm phải cận cảnh + đủ thông tin (#6)

**Hiện tại**: snapshot lưu là **toàn bộ khung hình** (`frame_snapshot = frame.copy()`, pipeline.py:792; `cv2.imwrite(snapshot_path, frame)`, pipeline.py:840) — không phải ảnh crop riêng người/xe vi phạm, khó nhìn rõ chi tiết khi khung hình đông người.

**Cách sửa**: bên cạnh full-frame hiện có (giữ lại để có ngữ cảnh), lưu thêm **1 ảnh crop cận cảnh** quanh bbox của group vi phạm (person ∪ vehicle ∪ plate, mở rộng biên ~20% mỗi phía để không cắt sát) vào cùng thư mục snapshot, thêm cột `crop_snapshot_path` vào bảng `violation_events` (migration kiểu `ALTER TABLE` như các cột khác trong `init_db()`, xem pattern ở app/db.py:136-149). Frontend (`AdminViolationsPage.jsx`) hiển thị cả 2 ảnh trong modal chi tiết — ảnh crop làm ảnh chính, full-frame làm ảnh phụ/ngữ cảnh.

---

## Ưu tiên 6 — Xác minh tính năng xem video vi phạm (#7)

**Phát hiện quan trọng**: tính năng này **đã tồn tại**, không phải thiếu hoàn toàn — backend gắn `clip_url` cho mỗi vi phạm (app/api/admin.py:276-287), frontend đã render `<video>` khi có `clip_url` (AdminViolationsPage.jsx:206-222).

**Việc cần làm là DEBUG, không phải build mới**:
1. Kiểm tra thực tế: mở 1 vi phạm trong `/admin/violations`, xem có phát video được không.
2. Nếu clip không tồn tại/lỗi: kiểm tra `_write_clip()` (pipeline.py:815-824) có thực sự chạy và ghi file thành công không (log lỗi ghi video, quyền thư mục, `VideoWriter` mở đúng codec chưa) — `VIOLATION_CLIP_SECONDS=4`, `VIOLATION_CLIP_FPS=8` (config.py:145-146), không có cờ bật/tắt nên lẽ ra luôn chạy.
3. Nếu video có nhưng UI không thấy: kiểm tra route `/media/<filename>` có mount đúng `SNAPSHOTS_DIR` không (app/main.py, grep `"/media"`).

---

## Ưu tiên 7 — Sửa ô tìm kiếm biển số (#8)

**Nguyên nhân xác nhận rõ ràng**: `StudentAutocomplete.jsx` không hề có prop `value`/`onChange` trong signature thật (StudentAutocomplete.jsx:11-16) — nó tự quản lý `query` nội bộ và lọc trên prop `vehicles` (mặc định `[]`). Nhưng cả 2 nơi gọi nó — AdminViolationsPage.jsx:546-552 (ô lọc trong Nhật ký vi phạm) và AdminVehiclesPage.jsx:200-207 (ô chọn học sinh khi thêm xe) — đều **không truyền `vehicles`**, và truyền `value`/`onChange` mà component không đọc. Kết quả: gõ gì cũng không ra, vì component luôn lọc trên mảng rỗng.

**Cách sửa** (sửa component 1 chỗ, khớp đúng cách 2 nơi đang gọi):
1. `StudentAutocomplete.jsx`: thêm `useEffect` đồng bộ `query` nội bộ từ prop `value` khi `value` đổi từ bên ngoài (controlled), và gọi `onChange(newQuery)` mỗi lần người dùng gõ (hiện chỉ gọi `onSelect` khi chọn xong, không có `onChange` khi đang gõ).
2. 2 nơi gọi: truyền thêm `vehicles={vehicles}` — cả 2 trang đều đã có sẵn state `vehicles` (danh sách xe đã tải) trong component cha, chỉ thiếu truyền xuống.

---

## Ưu tiên 8 — Nâng cấp form thêm học sinh + link QR đăng ký (#5)

**Hiện tại**: bảng `registered_vehicles` chỉ có `plate_number`, `student_name`, `student_class` (app/db.py:50-57). Form chỉ có 3 field tương ứng (AdminVehiclesPage.jsx:181-224), POST `/api/vehicles` (app/api/admin.py:54-67).

**Cách sửa**:
1. **DB**: migration `ALTER TABLE registered_vehicles ADD COLUMN <col>` cho `photo_path TEXT`, `dob TEXT`, `phone TEXT`, `student_id TEXT` (mã số sinh viên/học sinh) — theo đúng pattern migration đã có trong `init_db()` (app/db.py:136+).
2. **Backend**: mở rộng schema `VehicleIn` (`app/schemas.py`), hàm `add_vehicle`/`update_vehicle` trong `app/db.py`, endpoint upload ảnh mặt học sinh (lưu vào thư mục tương tự `SNAPSHOTS_DIR`, trả về `photo_url`).
3. **Trang admin thêm học sinh**: nâng cấp `AdminVehiclesPage.jsx` — thêm input ảnh (preview trước khi lưu), ngày sinh (date picker), SĐT, mã số sinh viên.
4. **Bảng danh sách mã số hợp lệ**: bảng mới `student_roster(student_id TEXT PRIMARY KEY, student_name TEXT, student_class TEXT)` — admin import trước (CSV/Excel qua 1 trang admin nhỏ, hoặc form nhập tay từng dòng nếu danh sách ngắn) để trang public đối chiếu, chặn đăng ký giả mạo/spam.
5. **Trang public tự đăng ký (`/register`, không cần đăng nhập)**: route mới trong `App.jsx` (ngoài `RequireRole`, giống trang login), 1 link chung — học sinh nhập **mã số sinh viên**, backend kiểm tra tồn tại trong `student_roster` (404/thông báo rõ nếu không khớp) rồi mới cho điền tiếp: biển số + ảnh + SĐT + ngày sinh + lớp (tự điền sẵn lớp/tên từ roster nếu có). Endpoint backend mới `POST /api/register`.
6. **QR code**: dùng thư viện JS nhẹ (`qrcode` npm package, hoặc vẽ SVG QR thuần không cần thư viện nếu muốn ponytail tối đa) sinh QR trỏ tới `<domain>/register`, hiển thị trong trang admin để in/dán ở cổng trường.

---

## Verification (áp dụng chung sau khi code xong từng phần)
1. Ưu tiên 1-3: chạy với video có ≥2 người đi gần nhau (1 dắt bộ, 1 đi xe) — xác nhận log không gán nhầm biển số/loại xe giữa 2 người qua nhiều frame liên tiếp; xác nhận vi phạm "UNKNOWN" của 2 người khác nhau trong <60s đều được log (không mất do chung cooldown key cũ).
2. Ưu tiên 2: test với video xe chạy nhanh qua khung hình — xác nhận tỉ lệ đọc được biển số tăng so với trước (so sánh thủ công 1 đoạn video mẫu).
3. Ưu tiên 4: mô phỏng ≥3 vi phạm liên tiếp trong 3s — xác nhận nghe được đủ câu, không bị cắt ngang giữa chừng.
4. Ưu tiên 5: mở modal vi phạm, xác nhận có cả ảnh crop cận cảnh và full-frame.
5. Ưu tiên 6: mở `/admin/violations`, click 1 vi phạm có `clip_url`, xác nhận video phát được.
6. Ưu tiên 7: gõ vào ô tìm kiếm ở `/admin/violations` và ô chọn học sinh ở `/admin/vehicles`, xác nhận ra kết quả đúng.
7. Ưu tiên 8: quét thử QR bằng điện thoại, xác nhận mở đúng trang `/register` và submit được.
