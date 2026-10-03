# TASK 1 — Ownership (đăng ký phạm vi file)

> Đăng ký: 02/10/2026 00:41 ICT (UTC+7).
> Branch: `dot-4-all-12`, HEAD `83a0309`. Working tree có nhiều thay đổi chưa commit (của các task khác) — Task 1 **không tự stash/reset/clean** và sẽ bảo vệ các thay đổi đó.
> Trạng thái worktree: đã từng thử tạo worktree mới từ HEAD nhưng file mới (untracked) thuộc scope Task 1 chỉ tồn tại trong working tree hiện tại; quyết định làm việc ngay trong working tree gốc và tách bạch thay đổi của Task 1 khỏi thay đổi đang có bằng cách:
>
> 1. Mỗi file thuộc scope Task 1 nếu đã có thay đổi chưa commit → **không sửa chồng** trừ khi đã đối chiếu và xác nhận cùng chủ đích; nếu khác chủ đề thì ghi nhận vào mục Xung đột bên dưới.
> 2. Tạo file mới thuộc scope Task 1 khi cần.
> 3. Test/benchmark/EXECUTION_LOG riêng của Task 1 nằm trong `tasks/task-01/` và `app/tests/test_task01_*` (file mới).
>
> Baseline snapshot của working tree hiện có: `tasks/task-01/baseline_working_tree.txt` (git status --short tại thời điểm đăng ký).

## Phạm vi Task 1 — file chính (cần đọc kỹ trước khi sửa)

### CV runtime (đọc/sửa)
- `app/cv/pipeline.py`
- `app/cv/capture.py`
- `app/cv/detector.py`
- `app/cv/ocr.py`
- `app/cv/pose.py`
- `app/cv/plate_voter.py`
- `app/cv/recorder.py`
- `app/cv/roi.py`
- `app/cv/event_correlator.py`
- `app/cv/smoke_test.py`

### API + main (đọc/sửa phần thuộc scope)
- `app/main.py`
- `app/api/guard.py`
- `app/api/system.py` (chỉ phần metrics/health liên quan)
- `app/api/dev.py`

### Frontend (đọc/sửa)
- `frontend/src/pages/GuardPage.jsx`
- `frontend/src/components/AlertBanner.jsx`
- `frontend/src/utils/speak.js`
- Các file frontend mới thuộc scope (RecognitionLogPanel, PlateReviewPanel, alertAudio, alertFilter, useAudioLease) chỉ có trong working tree untracked; nếu cần sửa sẽ bảo vệ nội dung hiện có.

### File dùng chung — chỉ tích hợp tương thích khi có bàn giao
- `app/db.py`, `app/schemas.py`, `app/config.py`, `app/auth.py`, `app/api/camera.py` (chưa tồn tại trong HEAD, là file mới trong working tree untracked), `app/api/roi.py`, `app/api/admin.py`, `app/api/auth.py`.
- `app/tests/conftest.py` — ưu tiên dùng fixture riêng trong test Task 1; không làm yếu assertion hiện có.

### Test + benchmark riêng của Task 1
- Mới: `app/tests/test_task01_phase0_metrics.py`, `app/tests/test_task01_phase1_latest_frame.py`, v.v.
- Mới: `scripts/bench_task01_*.py`.
- Tài liệu: `tasks/task-01/OWNERSHIP.md` (file này), `tasks/task-01/CONTRACTS.md`, `tasks/task-01/todo.md`, `tasks/task-01/EXECUTION_LOG.md`, `tasks/task-01/ACCEPTANCE_REPORT.md`, `tasks/task-01/HANDOFF.md`.

## Xung đột / thay đổi chưa rõ chủ sở hữu

| File | Trạng thái trong working tree | Ghi chú Task 1 |
|---|---|---|
| `app/cv/pipeline.py` | Đã sửa +1588/-349 so với HEAD | Chưa rõ chủ; nếu cần sửa, đối chiếu kỹ và ghi lại từng thay đổi trong EXECUTION_LOG. |
| `app/cv/detector.py`, `app/cv/pose.py`, `app/cv/ocr.py`, `app/cv/capture.py`, `app/cv/plate_voter.py` | Đã sửa | Tương tự. |
| `app/api/guard.py`, `app/api/system.py`, `app/api/admin.py`, `app/api/auth.py`, `app/api/roi.py` | Đã sửa | Phối hợp với task khác nếu cần. |
| `app/db.py`, `app/schemas.py`, `app/config.py`, `app/main.py` | Đã sửa | Tích hợp tương thích, không tự ý đổi nghiệp vụ thuộc task khác. |
| File mới (untracked): `app/cv/best_plate.py`, `char_plate_reader.py`, `crossing.py`, `crossing_alert.py`, `event_manager.py`, `evidence.py`, `helmet_contract.py`, `plate_char_tools.py`, `recognition_cards.py`, `recognition_log.py`, `camera_sources.py`, `camera_switch.py`; `app/api/camera.py`, `recognition_reviews.py`, `media.py`, `register.py`, `audio_lease.py` | Mới, chưa commit | Thuộc scope Task 1; **chưa commit vì chưa xác minh**. Task 1 sẽ đọc, đánh giá, và đăng ký lại ownership của từng file nếu phù hợp. |
| `app/cv/recorder.py` | Đã sửa trong HEAD (4039a18); đã thêm test | Thuộc scope Task 1. |
| `frontend/src/components/RecognitionLogPanel.jsx`, `PlateReviewPanel.jsx`, `frontend/src/utils/alertAudio.js`, `alertFilter.js`, `useAudioLease.js` | Mới (untracked) | Thuộc scope Task 1. |
| `scripts/benchmark_inference.py`, `scripts/train_plate.py`, `scripts/train_plate_colab.ipynb` | Đã sửa | Không chạm nếu không có yêu cầu benchmark mới. |

## Quy tắc làm việc

- Một file tại một thời điểm chỉ có một task ghi; Task 1 không ghi vào file đang được task khác sửa mà không có patch bàn giao.
- Khi cần thiết, snapshot bằng `git diff -- <file>` để chứng minh ranh giới.
- Không commit toàn bộ thay đổi của working tree; chỉ commit file thuộc scope Task 1 sau khi self-review.
- Không push, không deploy, không ghi đè DB/media/video/log người dùng.
