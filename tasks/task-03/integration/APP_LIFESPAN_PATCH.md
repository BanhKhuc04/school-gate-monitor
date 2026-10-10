# APP_LIFESPAN_PATCH — sample_collector + training_worker start/stop từ app lifespan (Task 3 → Task 2)

> Ngày: 2026-10-02. Phiên bản: 1.1 (cập nhật 2026-10-02 P4: thêm `training_worker`).

## Mục đích

Task 3 cần 2 background worker chạy nền:
- **sample_collector**: thu mẫu từ feedback API.
- **training_worker**: claim queued/waiting_resource jobs và dispatch runner.

Cả hai phải start/stop an toàn cùng app lifespan (do Task 2 — integration owner —
quản lý).

## Patch tối thiểu (KHÔNG đổi logic)

Mở `app/main.py`. Trong `lifespan()` (khoảng line 30–60), SAU khi `init_db()` và
SAU khi start pipeline:

```python
# --- BEGIN TASK3 COLLECTOR ---
try:
    from app.training.sample_collector import start_collector_task
    start_collector_task()
except ImportError:
    print("[App] Task3 collector unavailable")
# --- END TASK3 COLLECTOR ---

# --- BEGIN TASK3 TRAINING WORKER (P4) ---
try:
    from app.training.worker import start_training_worker
    start_training_worker(poll_sec=5.0)
except ImportError:
    print("[App] Task3 training worker unavailable")
# --- END TASK3 TRAINING WORKER ---
```

Trong khối shutdown (trước/SAU `stop_all_pipelines()`):

```python
# --- BEGIN TASK3 TRAINING WORKER STOP (P4) ---
try:
    from app.training.worker import stop_training_worker
    stop_training_worker(timeout=5.0)
except ImportError:
    pass
# --- END TASK3 TRAINING WORKER STOP ---

# --- BEGIN TASK3 COLLECTOR STOP ---
try:
    from app.training.sample_collector import stop_collector_task
    stop_collector_task()
except ImportError:
    pass
# --- END TASK3 COLLECTOR STOP ---
```

## Cờ bật/tắt (config)

- `TASK3_COLLECTOR_ENABLED=0` → sample collector không start.
- `TASK3_TRAINING_WORKER_ENABLED=0` → training worker không start (default bật
  trong QA, default tắt trong production camera nếu cần).

Mặc định: bật cả hai. Không tự start training trong ca camera vận hành chỉ vì
app khởi động — nếu app của bạn chỉ chạy inference, set
`TASK3_TRAINING_WORKER_ENABLED=0`.

## Đặc tính

### sample_collector
- `start_collector_task()` idempotent: nếu worker đã chạy → no-op.
- `stop_collector_task()` đặt sentinel, join tối đa 5s.
- File `data/training/sample_collector.cursor.json` persist sau khi có feedback đầu tiên.

### training_worker (P4)
- `start_training_worker(poll_sec=5.0)` idempotent: gọi 2 lần trả về cùng instance.
- `stop_training_worker(timeout=5.0)` set sentinel, join thread; idempotent.
- Worker loop: thử claim queued job GPU-free → chạy runner; thử resume waiting jobs
  cho 3 target (plate_ocr, plate_detector, helmet).
- KHÔNG tự start GPU operation nếu app context không có GPU.

## Kiểm tra

- Sau lifespan start:
  - `data/training/sample_collector.metrics.json` có `heartbeat` mới sau ≤ 30s.
  - `data/training/sample_collector.cursor.json` được persist sau feedback đầu tiên.
  - `threading.enumerate()` có `task3-sample-collector` và `task3-training-worker`.
- Sau lifespan stop:
  - `threading.enumerate()` không còn 2 thread trên.

## Lưu ý Task 2

- KHÔNG đặt import Task 3 ở top-level app/main.py — Task 3 module có thể chưa
  ready trong môi trường Task 2 trước khi Task 3 hợp nhất. Import lazy trong
  lifespan đã làm đúng điều này.
- Nếu `app/main.py` không có sẵn `lifespan()` → không apply patch.
- Cờ `TASK3_TRAINING_WORKER_ENABLED` đọc trong `app.training.worker.is_enabled()`.
- Patch này là additive — KHÔNG xóa patch collector cũ.