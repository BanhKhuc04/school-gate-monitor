# TASK 1 — Hợp đồng (CONTRACTS)

Ngày soạn: 02/10/2026. Tài liệu công bố HỢP ĐỒNG giữa Task 1 và các task dùng
chung trước khi sửa. Phạm vi: lõi camera, nhận diện, sự kiện, giao diện giám
sát. Mọi thay đổi dưới đây đã được đối chiếu với mã nguồn tại HEAD `83a0309`.

## 1. Định danh

| Khái niệm | Mô tả |
|---|---|
| `gate_id` | Cổng vật lý (string). Cố định theo cơ sở hạ tầng; KHÔNG thay đổi cho lịch sử vi phạm. |
| `camera_id` | Nguồn hình ổn định gắn vào gate; `camera_id` có thể thay đổi khi admin chọn nguồn mới. |
| `role` | Vai trò camera (`front` / `rear` / `aux`); xác định profile model (person/helmet pose vs vehicle/plate/OCR). |
| `source_epoch` | Số nguyên tăng khi `apply_camera_change()` thành công. Mọi kết quả OCR/detect cũ mang epoch != hiện tại bị loại. |
| `frame_seq` | Số frame mới từ camera kể từ pipeline start, tăng đơn điệu. |

## 2. Frame và track

- Mỗi frame gắn `(gate_id, camera_id, source_epoch, frame_seq, ts_wall)`.
  Thời gian nghiệp vụ UTC; thời gian monotonic dùng cho latency/dedup.
- Track chỉ duy nhất trong `(camera_id, source_epoch, track_id)`. KHÔNG so ID
  track giữa hai camera. Encounter nội bộ camera có UUID/vehicle track_id riêng.
- Track bị belong khi:
  - Đổi camera thành công (`source_epoch` tăng), HOẶC
  - Mất track liên tục quá TTL (`_max_track_ttl_sec`, mặc định 8s — Phase 1),
    HOẶC
  - Stop pipeline (`_running=False`).

## 3. Quan sát biển số

| Trường | Mô tả |
|---|---|
| `plate_text` | Chuỗi đã chuẩn hóa (regex áp dụng; KHÔNG biến đổi để "thành" biển chưa quan sát). |
| `confidence` | Confidence OCR (EasyOCR) hoặc char detector; KHÔNG coi là độ chính xác kết luận. |
| `engine` | `"easyocr"` (mặc định) hoặc `"char_plate"` (review-only khi `CHAR_PLATE_READER_REVIEW_ONLY=1`). |
| `model_hash` | Hash weights model (Phase 1: SHA256 đầu 8 bytes của file). |
| `frame_id` | `frame_seq` của frame phát hiện crop. |
| `crop_id` | UUID plate crop lưu cùng với snapshot evidence. |
| `status` | `checking` (đang gom) / `confirmed` (≥2 mẫu đồng thuận + chất lượng + khớp crop khác frame) / `needs_review` (chuỗi yếu/mâu thuẫn/thiếu ký tự) / `error` (engine lỗi). |
| `attempts` | Số lần đã submit OCR cho track này trong epoch hiện tại. Phase 1 cap 1 mỗi track. |

`PLATE_OCR_MIN_CONFIDENCE` (mặc định 0.70) là ngưỡng cho 1 lần đọc đơn lẻ.
Consensus yêu cầu ≥ `PLATE_VOTE_MIN_AGREE` mẫu giống nhau trong
`PLATE_VOTE_WINDOW_SEC`. Không bao giờ gán học sinh khi `status=needs_review`.

## 4. Quan sát hành vi

`posture_status ∈ {RIDING, PUSHING, WALKING, STATIONARY, UNKNOWN}` kèm lý do,
khoảng thời gian và mẫu chấp nhận.

- `RIDING`: ≥4 mẫu đồng thuận trong 1.5s, ≥80% agreement, span ≥400ms,
  interval ≥100ms.
- `PUSHING`: như RIDING mà vận tốc ≈ 0 hoặc có dấu hiệu chân chống/đẩy.
- `WALKING`: ≥3 mẫu cách nhau ≥200ms, vai–hông–gối gần thẳng đứng.
- `STATIONARY`: pose ổn định ≥2s, không có dấu hiệu dịch chuyển.
- `UNKNOWN`: thiếu khớp xương / quá mờ / chỉ 1 frame.

`MIRROR_LEFT_OBSERVABLE` là cờ từng camera/góc — Phase 1 chỉ review-only khi
admin đã cấu hình. Không bật cảnh báo thiếu gương trái trên camera trước lệch
phải mà chưa có nhãn/góc phù hợp.

## 5. Sự kiện vi phạm

| Trường | Mô tả |
|---|---|
| `event_id` | UUID; định danh 1 lượt xe. |
| `encounter_id` | UUID cùng gate/camera/epoch; nhiều issue gộp vào 1 event. |
| `gate_id`, `camera_id` | Camera quan sát. |
| `source_epoch` | Epoch tại thời điểm quan sát. |
| `issues[]` | List `Issue{code, status, sample_count, evidence_ref, first_observed_at}`. |
| `version` | Tăng mỗi lần thêm issue mới. UI tăng version hiển thị cùng `event_id`. |
| `plate_status` | `CONFIRMED` / `NEEDS_REVIEW` / `UNREADABLE` / `ENGINE_ERROR`. |
| `evidence_state` | `pending` / `persisted` / `failed`. DB có cột tương ứng. |

Trạng thái AI (đang xử lý / đã chốt) tách khỏi trạng thái nghiệp vụ (review /
đã duyệt / chuyển phạt). Issue `resolved` chỉ chuyển khi admin/giáo viên xử lý.

## 6. Hợp đồng đổi nguồn camera (giữ API cũ)

- `POST /api/camera/apply` → 202 Accepted khi hợp lệ; body chứa
  `{status: "checking" | "applied" | "error", source, error?: str}`.
- `GET /api/camera/status` → `{status, source, ...}`. Khi đang chuyển trả
  `checking`; thất bại trả `error` (giữ NGUỒN CŨ — không tự ý chuyển).
- Nguồn lỗi giữ camera cũ; chỉ `applied` mới tăng `source_epoch`.
- Không ghi credential (user/pass RTSP) vào response hoặc log.

## 7. Migrations

- Tất cả cột bổ sung đều nullable + default; KHÔNG drop cột cũ chứa dữ liệu.
- Migration có phiên bản (`migration_versions`); chạy lặp an toàn (idempotent).
- Không tự ý sửa 6 bảng hiện có (`violation_events`, `violation_audit_log`,
  `registered_vehicles`, `gate_roi`, `gate_camera_source`, `student_roster`,
  `users`, `system_maintenance_log`) ngoài bổ sung cột tương thích.

## 8. Concurrency

- KHÔNG giữ khoá đồng bộ qua `await`.
- Mỗi camera có tracker riêng; KHÔNG dùng chung `predictor.trackers`
  giữa hai camera.
- Một model detector stateless dùng chung chỉ chạy tuần tự có kiểm soát
  (đã enforce bằng `ThreadPoolExecutor(max_workers=1)` ở nhánh OCR);
  tracker state (BoT-SORT/ByteTrack) vẫn riêng từng camera.

## 9. Phần dành cho task khác

- `auth.py`, `AuthContext`, `frontend/src/api/client.js`: KHÔNG sửa chồng.
  Khi cần giao tiếp với nhau, dùng hợp đồng cookie / Bearer hiện có.
- Backup/roster tổng thể, huấn luyện lớn, CI/deploy: NGOÀI PHẠM VI Task 1.
- Task 1 công bố hợp đồng ở đây, dùng API/client hiện có; ghi dependency còn
  thiếu; không sửa chồng khi task tương ứng chưa tích hợp.