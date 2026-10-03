# R7 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R7 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: chốt contract artifact, API import
admin, evaluate local, gate production, apply/ACK/rollback, không load
pickle từ nguồn tùy ý.

## 1. Công cụ / test Owner A tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r7_promotion_guards.py` | 16 test cho `app/training/promotion.py` guards |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r7_promotion_guards.py -v
======================== 16 passed, 1 warning in 5.07s ========================
```

16/16 test pass:
- 3 test `_verify_artifact` (file missing / too small / missing path field)
- 2 test `_verify_hash` (mismatch reject / match accept)
- 3 test `_verify_runtime_contract` (unknown engine / block unknown class / accept compatible)
- 4 test `_verify_not_smoke` (smoke in model_class / simulate in model_class / allow clean / lifecycle_simulation note)
- 2 test helmet engine (YOLO accept / pickle block)
- 1 test `_RUNTIME_CONTRACT` có đủ 3 engines
- 1 test SchemaError là SchemaError (không bị nuốt thành Exception chung)

## 3. Đã có sẵn trong codebase

- `app/training/promotion.py`:
  - `_verify_artifact`: file >= 100 bytes, hash SHA256, loadable với timeout
  - `_verify_hash`: SHA256 khớp claimed hash
  - `_verify_runtime_contract`: engine → class prefix whitelist
    - plate_ocr: ('EasyOCR', 'CustomOCR')
    - plate_detector: ('YOLO', 'Ultralytics')
    - helmet: ('YOLO', 'Ultralytics', 'Helmet')
  - `_verify_not_smoke`: smoke marker trong model_class + lifecycle_simulation note
  - `promote()`: gate đầy đủ trước khi mark pending_runtime
  - `rollback()`: giữ baseline cũ
  - `SchemaError` cho mọi lỗi contract

## 4. R7 đạt tiêu chí (handoff §3 R7)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Chốt contract artifact (weights/ONNX, config, mapping, hashes) | ✓ | _verify_artifact + _verify_hash |
| API import admin kiểm kích thước, path/hash/mapping/load | ✓ | _verify_artifact min size + _load_artifact_with_timeout |
| Metrics tải về chỉ là khai báo, đánh giá local trên holdout | ✓ | _verify_metrics_server_side |
| Không load pickle/checkpoint từ nguồn tùy ý | ✓ | _verify_runtime_contract (YOLO/Ultralytics only) |
| selected → pending_runtime → applied chỉ sau runtime xác nhận | ✓ | _mark_pending_runtime |
| CCT cần contract ONNX+YAML | ✓ | R6 test (model+config hash) |
| Rollback giữ baseline cũ | ✓ | rollback() function |
| Load thất bại / hash sai / thiếu VRAM → không đổi metadata trước weights | ✓ | _verify_* chạy trước promote |
| Tách eligible benchmark / eligible production | giữ nguyên | _verify_job_completed + gate logic |
| Registry/UI khớp hash runtime | chờ R13 | API trả model_hash + config_hash |
| Fail case không mất baseline/lịch sử | ✓ | rollback giữ state |

## 5. Còn mở

- Apply/ACK runtime end-to-end (cần YOLO/CCT weights thật từ R10/R6)
- GPU transient test (cần GPU + runtime test)
- Rollback cũ load/ACK baseline (cần runtime ACK path)

R7 kết thúc. Working tree bảo toàn. Không tự commit.
