# FEEDBACK_HOOK_CONTRACT — sample_collector (Task 3 ↔ Task 1)

> Mục đích: Task 1 thêm 1 dòng hook vào `app/api/recognition_reviews.py` để Task 3 thu mẫu sau khi feedback lưu thành công.
> Ngày: 2026-10-02. Phiên bản: 1.2 (post-P1 fix: feedback_id identity + new_version).

## 1. Tóm tắt

Task 3 cần biết KHI NÀO có feedback mới để chuẩn bị asset/cursor. Task 1 là writer duy nhất của `app/api/recognition_reviews.py`. Thay vì polling DB, Task 1 thêm 1 dòng gọi hook public của Task 3 sau khi `record_review_feedback` thành công.

Hook **chỉ enqueue** (non-blocking, bounded queue), KHÔNG xử lý ảnh, KHÔNG gọi DB thêm, KHÔNG train.

## 2. API hook (Task 3 public) — v1.2

```python
from app.training.sample_collector import on_feedback_recorded

# Trả True nến enqueue được, False nếu queue đầy / collector tắt.
# Mọi lỗi bị nuốt; KHÔNG raise.
on_feedback_recorded(
    review_id: str,
    feedback_id: int,    # P1: server-generated ID từ record_review_feedback
    new_version: int,    # P1: version DB MÀ REVIEW ĐÃ COMMIT (server-authoritative)
    *, source: str = "feedback",
) -> bool
```

Đặc tính:

- **Non-blocking** — `on_feedback_recorded` đặt vào bounded queue với `put_nowait`; queue đầy → trả False, bump metric `dropped_queue_full`.
- **No I/O** — không mở file, không đọc DB. Worker nền sẽ tự xử lý.
- **Lazy-init safe** — singleton collector có thể được start từ app lifespan (Task 2 integration); nếu chưa, hook tự tạo collector ở trạng thái chưa start worker. Không bao giờ raise.
- **Idempotent** — worker reconcile theo `(review_id, latest_feedback_id)` cursor; replay cùng feedback_id KHÔNG nhân sample. Cursor đọc qua adapter `latest_feedback_id`; fallback `version` nếu adapter cũ.

### Tại sao `feedback_id` + `new_version` (P1)

- `feedback_id`: identity để dedupe replay. Cùng feedback_id → cursor đã có → skip.
- `new_version`: version DB commit (server-authoritative). KHÔNG dùng echo `expected_version` — client có thể gửi sai; server mới biết version thực sự đã tăng lên bao nhiêu.

### KHÔNG dùng echo `expected_version`

- Cũ (v1.1): `result.get('expected_version')` echo input → version mới? Sai nếu client gửi stale.
- Mới (v1.2): lấy từ `result['new_version']` server-authoritative. Worker lấy `latest_feedback_id` từ adapter/DB để so cursor.

## 3. Nơi patch Task 1

Trong `app/api/recognition_reviews.py`, sau khi `db.record_review_feedback(...)` thành công:

```python
# Khối try/except để KHÔNG phá endpoint feedback
try:
    from app.training.sample_collector import on_feedback_recorded
    on_feedback_recorded(
        review_id=review_id,
        feedback_id=result["feedback_id"],   # P1: server-generated identity
        new_version=result["new_version"],   # P1: server-authoritative version
        source="recognition_feedback",
    )
except Exception:
    # Không để exception của Task 3 ảnh hưởng endpoint Task 1
    pass
```

### Vị trí chính xác

Mở `app/api/recognition_reviews.py`. Tìm endpoint `post_feedback` (khoảng line 55–90). Tìm dòng:

```python
result = db.record_review_feedback(
    review_id=review_id,
    ...
)
return {"review_id": review_id, "version": result["version"], ...}
```

Chèn khối hook trước `return`, sau khi `result` được gán. Tóm tắt patch (KHÔNG đổi logic nghiệp vụ):

```python
result = db.record_review_feedback(
    review_id=review_id,
    reviewer=payload.reviewer,
    verdict=payload.verdict,
    ...
)
# --- BEGIN TASK3 HOOK (P1) ---
try:
    from app.training.sample_collector import on_feedback_recorded
    on_feedback_recorded(
        review_id=review_id,
        # P1: dùng feedback_id (server-generated, identity để dedupe)
        #     và new_version (server-authoritative version đã commit).
        feedback_id=result["feedback_id"],
        new_version=result["new_version"],
        source="recognition_feedback",
    )
except Exception:
    pass
# --- END TASK3 HOOK ---
return {"review_id": review_id, "version": result["version"], ...}
```

### Bảo vệ

- Đặt trong `try/except` (rộng) — nuốt mọi exception từ Task 3.
- Task 1 KHÔNG thay đổi logic nghiệp vụ, KHÔNG thêm field trong schema/return.
- Hook chỉ enqueue; nếu Task 3 tạm thời không có (import fail) → except pass.

### Khi nào KHÔNG gọi hook

- Khi `result.get("applied") == False` (conflict 409).
- Khi `result.get("idempotent_replay") == True` (replay key cũ) — KHÔNG gọi lại vì sample đã có.
- Lỗi lưu DB (`record_review_feedback` raise) — KHÔNG gọi hook.

Cú pháp đề xuất:

```python
result = db.record_review_feedback(...)
if result.get("applied") and not result.get("idempotent_replay"):
    try:
        from app.training.sample_collector import on_feedback_recorded
        on_feedback_recorded(
            review_id=review_id,
            feedback_id=result["feedback_id"],
            new_version=result["new_version"],
            source="recognition_feedback",
        )
    except Exception:
        pass
```

## 4. Worker Task 3

Worker chạy trong `SampleCollector._run_worker()` — thread nền riêng:

- Mỗi 5 giây (period) kiểm tra queue + chạy reconcile pass.
- Mỗi 30 giây persist metrics ra `data/training/sample_collector.metrics.json`.
- Cursor ở `data/training/sample_collector.cursor.json` — idempotent.
- Reconcile scan batch tối đa 32 review (batch_max); pagination dùng review_id ordering ổn định — KHÔNG dùng [:batch_max] luôn lấy trang đầu.
- Cursor update CHỈ sau khi asset copy thành công; copy fail → không update cursor → sẽ retry ở pass sau.

### Bật/tắt collector

```bash
# Bật (mặc định)
export TASK3_COLLECTOR_ENABLED=1

# Tắt khi cần (vd. test DB không có sample)
export TASK3_COLLECTOR_ENABLED=0
```

### Lifespan integration

`app/main.py` lifespan hiện đã start training routers. Task 2 (integration owner) sẽ thêm (xem `APP_LIFESPAN_PATCH.md`):

```python
try:
    from app.training.sample_collector import start_collector_task
    from app.training.worker import start_training_worker
    start_collector_task()
    start_training_worker(poll_sec=5.0)
except ImportError:
    pass
# ... yield ...
try:
    from app.training.worker import stop_training_worker
    from app.training.sample_collector import stop_collector_task
    stop_training_worker(timeout=5.0)
    stop_collector_task()
except ImportError:
    pass
```

Nếu Task 2 chưa integrate, lazy-init ở `on_feedback_recorded` vẫn tạo collector nhưng worker chưa chạy cho đến khi lifespan start. Điều này an toàn — queue tồn tại 1024 slot.

## 5. Không làm gì (negative contract)

Task 1 KHÔNG ĐƯỢC:

- Đọc file `app/training/*` (Task 3 giữ).
- Tự gọi adapter trong hook.
- Tự train hoặc copy ảnh trong hook.
- Tự ghi vào DB `data/training.db`.
- Đổi schema response của `/api/recognition/reviews/{id}/feedback` (chỉ Task 3 đổi `record_review_feedback`).
- Dùng `expected_version` echo làm version (P1).

Task 3 KHÔNG ĐƯỢC:

- Tự thêm hook vào file Task 1.
- Đợi sync kết quả từ hook (chỉ enqueue).

## 6. Test bảo vệ

`app/tests/task03_closure/test_closure_c01_c08.py::TestP1HookContractFeedbackId`:
- `test_record_review_feedback_returns_feedback_id_and_new_version` — verify response có `feedback_id` (>=1) và `new_version` (= DB version đã commit, KHÔNG echo input).
- `test_idempotent_replay_returns_same_feedback_id` — replay cùng key → cùng feedback_id.
- `test_conflict_returns_no_event` — 409 → `feedback_id=None` → không gọi hook.
- `test_hook_signature_uses_feedback_id_and_new_version` — hook signature đúng.
- `test_feedback_event_dataclass_has_feedback_id` — FeedbackEvent có field mới, không còn `feedback_version`.

`app/tests/task03_closure/test_closure_e1_e2_e5_e6.py::test_collector_*`:
- `test_collector_enqueue_does_not_block_when_full` — queue đầy → trả False, metric bumped.
- `test_collector_enqueue_never_raises` — review_id/feedback_id None → không raise.
- `test_collector_cursor_persisted_and_idempotent` — cursor update với `latest_feedback_id`, replay không nhân.
- `test_collector_on_feedback_recorded_hook_safe` — hook public không raise khi singleton chưa start.

Khi Task 1 apply patch, có thể thêm integration test:

```python
# app/tests/test_recognition_feedback_hook.py
def test_post_feedback_invokes_collector():
    # patch on_feedback_recorded → tăng counter
    # gọi POST /api/recognition/reviews/{id}/feedback
    # assert counter == 1
    # assert feedback_id và new_version từ result được truyền đúng
```

## 7. Rollback

Nếu hook gây lỗi runtime:

1. Task 1 revert commit (hoặc xóa khối BEGIN/END TASK3 HOOK).
2. Collector vẫn hoạt động thông qua reconcile scan DB (mỗi 5 giây) — không mất feedback.
3. Báo Task 3 để update integration patch.

## 8. Số liệu kỳ vọng

- Collector metric `data/training/sample_collector.metrics.json`:
  - `enqueued`: số event đã enqueue
  - `dropped_queue_full`: số event bị queue đầy
  - `processed`: số event đã xử lý
  - `processed_assets_copied`: số crop đã copy thành công
  - `reconcile_runs`: số pass reconcile
  - `last_event_ts`, `last_run_ts`, `heartbeat`: timestamp monitor

Khi queue đầy > 0 → cần xử lý (tăng queue_max, check disk I/O, hoặc test env không có ảnh).

## 9. Migration từ v1.1 → v1.2

- `feedback_version` (int) → `feedback_id` (int) + `new_version` (int).
- Endpoint /api/recognition/reviews/{id}/feedback trả `new_version` (KHÔNG echo `expected_version`).
- Task 1 đổi hook call.
- Test cũ `test_collector_*` cập nhật theo signature mới.