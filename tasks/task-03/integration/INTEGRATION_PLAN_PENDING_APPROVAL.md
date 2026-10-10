# Plan: Bật quyền sửa file Task 1/2 cho Task 3 — triển khai end-to-end

> Trạng thái: PENDING_USER_APPROVAL (chờ bạn duyệt).
> Người soạn: Task 3 (assistant).
> Mục tiêu: từ PARTIAL → DONE end-to-end trên runtime.

## 0. Nguyên tắc khi được bật quyền

1. **Snapshot trước** — `git diff --stat > tasks/task-03/integration/PRE_INTEGRATION_DIFFSTAT.txt`
3. **Một file một lúc** — không sửa 2 file Task 1/2 cùng commit.
4. **Mỗi bước test liền** — chạy test riêng bước đó. Không gom 4 commit.
5. **Backup working tree** — copy file Task 1/2 ra `tasks/task-03/integration/backups/` trước khi sửa.
6. **KHÔNG commit toàn bộ** — chỉ commit file Task 3 + file Task 1/2 mà tôi đã sửa, để Task 1/2 cherry-pick.
7. **KHÔNG push/deploy/ghi đè runtime data**.

## 1. File Task 1/2 cần sửa (sau khi bật quyền)

### A. `app/main.py` (Task 1+2 cùng giữ)
**Hiện trạng:** Đã sửa `+1588/-349`, đã include router guard/auth/users/etc nhưng CHƯA có `training_data`/`training_jobs`/`training_candidates`/`training_portable`.

**Hành động:** Thêm 4 dòng include_router ngay sau recognition_reviews (line 126).

```python
from app.api import training_data, training_jobs, training_candidates, training_portable
# ...
app.include_router(training_data.router)
app.include_router(training_jobs.router)
app.include_router(training_candidates.router)
app.include_router(training_portable.router)
```

**Verify:** `curl -H "Authorization: Bearer $ADMIN" http://localhost:8000/api/training/datasets` → 200 (không 404).

**Backup:** `app/main.py` → `tasks/task-03/integration/backups/main.py.before`.

### B. `frontend/src/App.jsx` (Task 2 giữ phần routing)
**Hiện trạng:** Đã sửa, đã có route admin/teacher/management.

**Hành động:** Thêm 4 import + 4 `<Route>` (admin only) cho DatasetManagerPage, TrainingJobsPage, CandidateComparePage, BBoxEditorDemoPage.

**Verify:** Login admin → thấy 4 menu trong Sidebar.

**Backup:** `App.jsx` → `tasks/task-03/integration/backups/App.jsx.before`.

### C. `frontend/src/components/Sidebar.jsx` (Task 2 giữ)
**Hành động:** Thêm 4 menu item cho admin.

**Backup:** `Sidebar.jsx` → `integration/backups/Sidebar.jsx.before`.

### D. `frontend/src/components/PlateReviewPanel.jsx` (Task 1 giữ)
**Hiện trạng:** Panel đã có, đang duyệt chữ biển.

**Hành động:** Thêm BBoxEditor vào panel — khi user chọn "Sửa bbox" thì mở BBoxEditor với bbox hiện tại của review, gọi PATCH `/api/training/datasets/{ds}/samples/{tid}/bbox`.

**Vấn đề cần giải:**
- Mapping letterbox (ảnh ngữ cảnh gốc → crop) — Task 1 phải cung cấp `original_image_w/h` trong review record, hoặc task 3 dùng công thức heuristic.
- Cần `dataset_id` đang active — fetch từ `/api/training/datasets?state=draft` lấy cái mới nhất của admin.

**Backup:** `PlateReviewPanel.jsx` → `integration/backups/PlateReviewPanel.jsx.before`.

### E. `app/cv/pipeline.py` (Task 1 giữ — RỦI RO CAO)
**Hiện trạng:** Đã sửa `+1588/-349`, là hot path của camera runtime.

**Hành động:** Thêm 2 thứ:
1. **Hook sample_collector**: sau khi `recognition_log.save_review(review)` thành công, gọi `maybe_add_to_active_dataset(review)` (Task 3 adapter đã có).
2. **Model swap**: thay chỗ đang load baseline model bằng `get_active_model_path(engine)` — đọc từ Task 3 candidate repo. CHỈ reload khi pipeline restart, KHÔNG swap giữa frame.

**Verify:**
- `pytest app/tests/test_smoke.py` PASS (không phá inference thường).
- `pytest app/tests/test_task03_helpers/` PASS (vẫn 43/43).

**Backup:** `pipeline.py` → `integration/backups/pipeline.py.before`.

### F. `frontend/src/api/client.js` (Task 2 giữ)
**Hành động:** Có thể cần thêm `withCredentials` nếu Task 3 endpoint cần cookie. Có thể KHÔNG cần vì axios client đã có sẵn.

### G. `app/api/recognition_reviews.py` (Task 1 giữ)
**Hành động:** Có thể thêm field trả về `sample_can_originate_bbox` (bool) để PlateReview biết có thể edit bbox hay không. KHÔNG sửa logic review.

## 2. Trình tự commit (10 commit nhỏ)

| # | Commit | Files | Verify |
|---|--------|-------|--------|
| 1 | snapshot diffstat | `integration/PRE_INTEGRATION_DIFFSTAT.txt` | file tồn tại |
| 2 | backup 6 file | `integration/backups/*.py.before` | so sánh MD5 |
| 3 | mount training routers | `app/main.py` | import ok |
| 4 | add training API tests | `app/tests/test_integration_training.py` | 12+ test pass |
| 5 | add frontend routes | `App.jsx` + `Sidebar.jsx` | npm run lint OK |
| 6 | add BBoxEditor in PlateReview | `PlateReviewPanel.jsx` | manual smoke |
| 7 | wire sample_collector hook | `app/cv/pipeline.py` | smoke test pass |
| 8 | wire model swap | `app/cv/pipeline.py` | smoke test pass |
| 9 | add integration test E2E backend | `app/tests/test_integration_e2e.py` | full E2E pass |
| 10 | final verification | `tasks/task-03/EXECUTION_LOG.md` | 43 tests + new tests pass |

## 3. Rủi ro và giảm thiểu

| Rủi ro | Xác suất | Giảm thiểu |
|--------|----------|------------|
| Phá runtime camera | Trung bình | Snapshot `pipeline.py`, smoke test sau mỗi commit, rollback git nếu test fail |
| Task 1/2 merge conflict | Cao (vì họ đang sửa) | Commit nhỏ, có backup, có integration note — Task 1/2 cherry-pick |
| Phá model load | Thấp | Dùng try/except khi đọc candidate, fallback baseline |
| Phá test Task 1/2 | Trung bình | Chạy full test suite sau mỗi commit |
| PlateReviewPanel thay đổi quá nhiều | Thấp | Chỉ thêm 1 nút + BBoxEditor nhỏ, không refactor |

## 4. Câu hỏi cần bạn quyết

1. **Có cho phép tôi sửa `app/cv/pipeline.py` không?** (file Task 1 giữ — hot path)
   - Có → tôi wire hook + model swap
   - Không → tôi chỉ mount router + frontend route, model swap đợi Task 1
2. **Có cho phép tôi sửa `PlateReviewPanel.jsx` không?** (Task 1 giữ)
   - Có → wire BBoxEditor vào panel
   - Không → dùng trang `BBoxEditorDemoPage` riêng, admin click qua menu
3. **Có cho phép tôi chạy training thật (GPU lock với Task 1) không?**
   - Có → tôi wire GPU lock chung
   - Không → smoke_train CLI không cần GPU lock
4. **Có cho phép tôi promote candidate và verify model runtime chạy model mới không?**
   - Có → tôi wire model swap hoàn chỉnh
   - Không → chỉ wire model load helper, không tự động promote

## 5. Thời gian ước tính

- Bước 1-5 (mount router + frontend): 20 phút
- Bước 6 (PlateReview wire): 15 phút
- Bước 7 (sample_collector hook): 20 phút
- Bước 8 (model swap): 15 phút
- Bước 9 (integration test): 20 phút
- Bước 10 (verify + log): 10 phút

**Tổng: ~1.5 giờ** (không tính debug nếu có vấn đề).

## 6. Sau khi xong

- Tất cả Task 3 PENDING → DONE
- Full regression pass (Task 1 + Task 2 + Task 3 tests)
- Browser E2E pass (17 tests)
- Có file `tasks/task-03/ACCEPTANCE_REPORT.md` update PASS cho end-to-end
- Commit có message rõ ràng để Task 1/2 review

## 7. Nếu có điều gì đó phá runtime

Tôi sẽ:
1. `git revert <commit>` ngay
2. Restore file từ `integration/backups/`
3. Báo cáo cho bạn trước khi làm tiếp