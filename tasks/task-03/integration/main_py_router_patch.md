# PATCH: Tích hợp Task 3 routers vào app/main.py

> Trạng thái: PENDING_INTEGRATION (Task 1/2 đang giữ `app/main.py`).
> Khi Task 1/2 bàn giao hoặc cho phép, áp dụng hunk sau đây.

## File: app/main.py

### Thêm import (sau dòng `from app.api.recognition_reviews import router as recognition_reviews_router`):

```python
from app.api.training_data import router as training_data_router  # T3.0-T3.4
from app.api.training_jobs import router as training_jobs_router  # T3.5
from app.api.training_candidates import router as training_candidates_router  # T3.6
from app.api.training_portable import router as training_portable_router  # T3.3
```

### Thêm include_router (sau `app.include_router(recognition_reviews_router)`):

```python
    app.include_router(training_data_router)
    app.include_router(training_jobs_router)
    app.include_router(training_candidates_router)
    app.include_router(training_portable_router)
```

### Thêm vào conftest.py (app/tests/conftest.py):

Sau khối `from app.api.recognition_reviews import router as recognition_reviews_router  # FR6`, thêm:

```python
    from app.api.training_data import router as training_data_router
    from app.api.training_jobs import router as training_jobs_router
    from app.api.training_candidates import router as training_candidates_router
    from app.api.training_portable import router as training_portable_router
```

Và sau `app.include_router(recognition_reviews_router)  # FR6`, thêm:

```python
    app.include_router(training_data_router)
    app.include_router(training_jobs_router)
    app.include_router(training_candidates_router)
    app.include_router(training_portable_router)
```

## Tests đi kèm

- `app/tests/test_task03_api.py` — gọi từng endpoint với admin/security/teacher.
- `app/tests/test_task03_auth.py` — kiểm tra role enforcement.

## Kiểm tra sau khi áp dụng

1. `pytest app/tests/test_task03_api.py -v` — pass.
2. `pytest app/tests/test_recognition_reviews.py -v` — pass (không regress).
3. `pytest app/tests/test_smoke.py -v` — pass.
4. `python -c "from app.main import app; print([r.path for r in app.routes][:5])"` — không lỗi.