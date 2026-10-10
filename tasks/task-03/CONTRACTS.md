# Task 3 — Contracts (kết nối với Task 1/2)

## API endpoints mới (Task 3 độc lập — không phụ thuộc Task 1/2)

| Method | Path | Role | Mô tả |
|--------|------|------|-------|
| GET    | /api/training/datasets                 | admin | List datasets (filter engine) |
| POST   | /api/training/datasets                 | admin | Create dataset |
| POST   | /api/training/datasets/{id}/freeze     | admin | Freeze immutable version |
| POST   | /api/training/datasets/{id}/samples    | admin | Add samples (chỉ khi draft) |
| GET    | /api/training/datasets/{id}/samples    | admin | List samples (filter split) |
| POST   | /api/training/datasets/{id}/split      | admin | 70/15/15 group-aware split |
| GET    | /api/training/datasets/{id}/leakage    | admin | Leakage check |
| POST   | /api/training/datasets/{id}/verify     | admin | Verify frozen hash |
| GET    | /api/training/jobs                      | admin | List jobs |
| POST   | /api/training/jobs                      | admin | Create job (queued) |
| GET    | /api/training/jobs/{id}                 | admin | Get job status |
| POST   | /api/training/jobs/{id}/cancel          | admin | Cancel job (idempotent) |
| GET    | /api/training/candidates                | admin | List candidates |
| GET    | /api/training/candidates/active         | admin | Get active candidate for engine |
| POST   | /api/training/candidates/{id}/promote   | admin | Promote (requires metrics ≥ baseline) |
| POST   | /api/training/candidates/rollback       | admin | Retire active candidate |
| POST   | /api/training/export                    | admin | Freeze + export ZIP |
| POST   | /api/training/import/preview            | admin | Preview ZIP diff (no DB write) |
| POST   | /api/training/import/apply              | admin | Apply import (creates new dataset) |

## Adapter (đã qua Task 1/2 owned API)

- `app.training.adapter.list_reviewed_with_feedback()` →
  `app.db.list_recognition_reviews()` + `app.db.get_recognition_review()`.
  KHÔNG sửa file đó. Khi Task 1 mở rộng contract (bbox/provenance/char feedback),
  chỉ cần thêm helper trong adapter.

## Schema (Task 3 định nghĩa, không ghi vào app/schemas.py của Task 1/2)

```python
# app/training/schemas.py
sample = {
  "target_id": str,            # sha256(review_id|frame_seq|crop_sha256)[:24]
  "review_id": str,            # FK cross-domain sang recognition_reviews
  "gate_id": str,
  "encounter_id": str | None,
  "label": {
    "verdict": "correct" | "incorrect" | "unreadable" | "not_plate" | "wrong_association",
    "target_text": str,        # canonical A-Z0-9, 4-12 chars khi verdict ∈ {correct, incorrect}
    "corrected_raw": str | None,
    "top_line": str | None,
    "bottom_line": str | None,
    "quality_score": float | None,
    "reviewer": str | None,
    "reviewed_at": str | None,
  },
  "source": {
    "gate_id": str,
    "camera_id": str | None,
    "run_id": str | None,
    "frame_seq": int | None,
    "source_epoch": int,
    "observed_at": str | None,
    "crop_sha256": str | None,
    "crop_media_id": str | None,
    "image_w": int | None,
    "image_h": int | None,
  },
  "bbox": [x1,y1,x2,y2] | None,  # normalized 0-1
  "classes": dict | None,        # helmet: {is_hi, is_no_hi, is_unknown}
  "split": "train" | "val" | "test" | None,
  "holdout": bool | None,
  "is_augmented": bool | None,
  "augmentation_provenance": {...} | None,
}
```

## Dataset version lifecycle

```
draft  ──[freeze]──>  frozen ──[import_export]──>  (manifest on disk)
   │                       │
   └──[add_samples]─────────┘
```

## Job lifecycle

```
queued
  ├─[gpu_free]──> preparing ──> training ──> evaluating ──> completed
  └─[gpu_busy]──> waiting_resource ──[gpu_free]──> preparing ──> ...
queued|preparing|training|evaluating ──[cancel/error]──> cancelled|failed
```

## Candidate lifecycle

```
candidate ──[promote, metrics ≥ baseline]──> active
active ──[rollback]──> retired
retired ──[promote again]──> (NEW state: another candidate promoted)
```

## Lock contention (parallel safety)

- DB Task 3 (`data/training.db`) riêng với DB runtime (`data/app.db`).
- 1 GPU job tại 1 thời điểm (`dataset_repo.active_job_count()`).
- Cross-task: KHÔNG đụng `data/app.db` khi chạy test; tận dụng adapter.

## Run pipeline runtime tương tác

Task 3 KHÔNG gọi ultralytics/EasyOCR từ pipeline runtime — chỉ qua adapter. Nếu
cần inference cho eval (predict candidate trên holdout), adapter sẽ dùng
ocr_engine/detector_engine wrapper (đã có sẵn).

## Scope auth

- admin: full access.
- security: KHÔNG có quyền training (training là admin-only theo plan).
- teacher/management: KHÔNG truy cập /api/training/*.