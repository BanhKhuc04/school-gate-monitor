# TASK 3 — Ownership (đăng ký phạm vi file)

> Đăng ký: 02/10/2026 12:38 ICT (UTC+7).
> Branch: `dot-4-all-12`, HEAD `83a0309`.
> Làm việc ngay trong working tree hiện tại (Task 1/2 đã đăng ký cùng chiến lược).
> Working tree có nhiều thay đổi chưa commit của các task khác — Task 3 **không tự
> stash/reset/clean** và sẽ bảo vệ phần đó.

## Phạm vi Task 3 — file riêng (tạo mới)

### Backend (mới, độc lập — không sửa file task khác giữ)
- `app/training/__init__.py`
- `app/training/provenance.py` — record/hash/dedup/sample_id
- `app/training/dataset_repo.py` — repo dataset version + samples + splits
- `app/training/label_validator.py` — schema/class/mapping/decode/provenance
- `app/training/splits.py` — 70/15/15 group-aware + leakage checker
- `app/training/augmentation.py` — train-only transforms (no fake targets)
- `app/training/export_portable.py` — ZIP ảnh + crop + labels + manifest
- `app/training/import_portable.py` — staging root, validator, preview, idempotent
- `app/training/dataset_freeze.py` — immutable version, tạo job-scoped snapshot
- `app/training/ocr_engine.py` — wrapper EasyOCR + adapter selection
- `app/training/detector_engine.py` — wrapper ultralytics + class mapping validation
- `app/training/helmet_engine.py` — wrapper helmet model + class mapping validation
- `app/training/jobs.py` — queued/running/completed/failed/cancelled + cancel
- `app/training/evaluator.py` — exact_ocr/CER/detector/helmet + regression
- `app/training/promotion.py` — candidate vs baseline + rollback + lifecycle adapter
- `app/training/sample_collector.py` — provenance hook (chưa gắn runtime — PENDING hook)

### API training/dataset riêng (mới, router độc lập)
- `app/api/training.py` — list jobs/datasets/candidates
- `app/api/dataset.py` — list/freeze/split + scope
- `app/api/export.py` — POST /export, GET status
- `app/api/import_portable.py` — POST upload ZIP + preview
- `app/api/feedback.py` — wrapper mở rộng review (bbox editor, multi-frame)

### Frontend (mới, trang riêng Task 3)
- `frontend/src/pages/TrainingDataPage.jsx` — trang duyệt biển/mũ + bbox editor
- `frontend/src/pages/DatasetManagerPage.jsx` — dataset versions + freeze
- `frontend/src/pages/TrainingJobsPage.jsx` — jobs + progress + cancel
- `frontend/src/pages/CandidateComparePage.jsx` — baseline/candidate + promote/rollback
- `frontend/src/components/training/*` — adapter API + bbox editor + scope
- `frontend/src/api/trainingClient.js` — adapter gọi API training/dataset

### Tests / scripts / docs (Task 3 tự quản)
- `app/tests/test_task03_*` — test riêng (Slice A→E)
- `frontend/e2e/test_task03_training.spec.js` — browser E2E
- `scripts/training/export_ocr_dataset.py`, `import_ocr_dataset.py`,
  `export_detector_dataset.py`, `import_detector_dataset.py`,
  `validate_dataset.py`, `freeze_dataset.py`, `train_ocr.py`,
  `train_plate_detector.py`, `train_helmet.py`, `evaluate_candidate.py`,
  `promote_candidate.py`, `rollback_candidate.py`.
- Tài liệu: `tasks/task-03/OWNERSHIP.md` (file này), `tasks/task-03/CONTRACTS.md`,
  `tasks/task-03/EXECUTION_LOG.md`, `tasks/task-03/ACCEPTANCE_REPORT.md`,
  `tasks/task-03/integration/*.md` (patch bàn giao).

## File dùng chung — Task 1/2 đang giữ

- `app/db.py`, `app/schemas.py`, `app/config.py`, `app/main.py`, `app/auth.py`,
  `app/cv/*`, `app/api/guard.py`, `app/api/admin.py`, `app/api/users.py`,
  `app/api/auth.py`, `app/api/recognition_reviews.py` (review hiện có),
  `app/api/media.py`, `app/api/system.py`, `app/api/roi.py`, `app/api/camera.py`,
  `app/api/register.py`, `app/background.py`, fixture chung `app/tests/conftest.py`,
  `frontend/src/pages/GuardPage.jsx`, `frontend/src/components/PlateReviewPanel.jsx`,
  `frontend/src/components/RecognitionLogPanel.jsx`, `frontend/src/components/AlertBanner.jsx`,
  `frontend/src/components/Sidebar.jsx`, `frontend/src/App.jsx`,
  `frontend/src/auth/AuthContext.jsx`, `frontend/src/auth/RequireRole.jsx`,
  `frontend/src/api/client.js`.
- **Nguyên tắc**: KHÔNG đồng thời ghi các file này. Mọi cần thiết phải ghi patch
  vào `tasks/task-03/integration/<topic>.md` để Task 1/2 tiếp nhận.

## File KHÔNG thuộc phạm vi Task 3

- Mọi file runtime camera/CV (Task 1 giữ).
- Mọi file auth/user/register/vehicles/violations admin pages (Task 2 giữ).
- Mọi file training runtime hiện có (`scripts/train_plate.py`, `scripts/train_helmet.py`,
  `scripts/train_plate_char.py`, `scripts/train_plate_kaggle.ipynb`,
  `scripts/train_plate_colab.ipynb`, `models/*`, `datasets/*` cũ) — Task 3 **chỉ
  THAM CHIẾU** schema/format qua adapter, KHÔNG tự ý ghi đè weights/datasets.

## Quy tắc làm việc

- Một file tại một thời điểm chỉ có một task ghi. Khi cần sửa file dùng chung, ghi
  nhu cầu vào `tasks/task-03/integration/` và **không sửa trực tiếp**.
- Khi cần, chạy `git diff -- <file>` để chứng minh ranh giới trước/sau.
- Không commit toàn bộ thay đổi của working tree. Chỉ commit file thuộc scope Task 3
  sau khi self-review.
- Không push, deploy, ghi đè DB/media/video/log người dùng.
- Không train GPU cùng lúc với Task 1. Một job GPU một thời điểm.
- Không tự ý đổi auth, camera, loa, prediction/evidence lịch sử.
- KHÔNG sửa panel GuardPage/Sidebar/App.jsx của runtime — sửa task khác giữ. Patch
  bàn giao qua integration/.
- Feedback đi vào dataset/trainer thật; lưu feedback CHƯA có nghĩa đã học.