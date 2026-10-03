# R9 — Status Report

Date: 2026-10-03. Owner B (KART, hand-off R0/R1/R8). Phạm vi R9 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: tạo 3 notebook Kaggle với preflight
manifest/hash/group-disjoint, dừng `pending_data` nếu nhãn thiếu.

## Công cụ / file Owner B tạo

| File | Mục đích |
|---|---|
| `scripts/training/_notebook_builder.py` | Helper viết JSON ipynb thủ công (không cần `nbformat` package) |
| `scripts/training/build_notebooks.py` | CLI tạo 3 notebook từ cell source |
| `scripts/training/validate_notebooks.py` | CLI validate JSON + cấu trúc |
| `notebooks/yolo11_plate.ipynb` | Notebook train YOLO11n detector biển số (9 cells) |
| `notebooks/yolo11_helmet_electric.ipynb` | Notebook train YOLO11 cho helmet + electric-vehicle (9 cells) |
| `notebooks/cct_plate_ocr.ipynb` | Notebook train CCT OCR FastPlateOCR (10 cells) |
| `app/tests/test_r9_notebooks.py` | 16 test: JSON valid, code cell compile, preflight/export cells |
| `app/tests/test_r9_notebook_builder.py` | 7 test cho helper `_notebook_builder` |
| `app/tests/test_r9_preflight.py` | 11 test: preflight logic từ cell (missing manifest, hash mismatch, count=0, …) |

Tổng test R9: 34 test pass.

## Cấu trúc 3 notebook

Mỗi notebook có cấu trúc cell theo handoff R9:

### yolo11_plate.ipynb (9 cells)

1. **markdown** — title + handoff scope
2. **code** — `PIN_IMPORTS`: pin Ultralytics, torch, tắt cache/plots
3. **code** — `WORKDIR_SETUP`: `/kaggle/working`
4. **code** — `PREFLIGHT_CHECK`: def `preflight(audit_dir) -> dict`
5. **code** — `YOLO_LOAD`: gọi preflight, kiểm tra data.yaml
6. **code** — `YOLO_TRAIN`: `YOLO("yolo11n.pt").train(...)` với config rõ ràng
7. **code** — `YOLO_RESUME`: từ `last.pt` qua `resume=True`
8. **code** — `YOLO_EXPORT`: ONNX + manifest + SHA256
9. **code** — `YOLO_SMOKE`: predict 1 ảnh test, assert ≥1 box

### yolo11_helmet_electric.ipynb (9 cells)

1. **markdown** — cảnh báo "2 bài toán riêng, không gộp model"
2. **code** — `PIN_IMPORTS`3. **code** — `WORKDIR_SETUP`
4. **code** — `PREFLIGHT_CHECK`
5. **code** — `HELMET_LOAD`: slug riêng `HELMET_DATASET_SLUG` + `EV_DATASET_SLUG`
6. **code** — `HELMET_TRAIN_HELMET`: train riêng helmet
7. **code** — `HELMET_TRAIN_EV`: train riêng EV
8. **code** — `HELMET_EXPORT`: 2 manifest + 2 hash riêng
9. **code** — `HELMET_SMOKE`: helmet round-trip

### cct_plate_ocr.ipynb (10 cells)

1. **markdown** — title + cảnh báo `--weights-path` ≠ resume đầy đủ
2. **code** — `PIN_IMPORTS`
3. **code** — `CCT_PIN`: in version `fast-plate-ocr`, `onnxruntime`
4. **code** — `WORKDIR_SETUP`
5. **code** — `PREFLIGHT_CHECK`
6. **code** — `CCT_LOAD`: gọi preflight, kiểm tra `{train,val,test}.csv`
7. **code** — `CCT_TRAIN_FULL`: copy CSV → định dạng FastPlateOCR, chạy
   `cct-train` với `--resume-keras` nếu có `last.keras`
8. **code** — `CCT_TRAIN_WEIGHTS_ONLY`: cell cảnh báo `--weights-path` chỉ
   nạp weights + tạo optimizer mới; **KHÔNG dùng làm resume đầy đủ**
9. **code** — `CCT_EXPORT`: ONNX uint8/channels_last + YAML + manifest + SHA256
10. **code** — `CCT_SMOKE`: OCR 10 ảnh test, in exact match

## Tuân thủ handoff R9

| Yêu cầu handoff R9 | Notebook |
|---|---|
| Pin Ultralytics ≥8.4, YOLO11n | ✓ `PIN_IMPORTS` |
| Không ép upgrade Torch local | ✓ `PIN_IMPORTS` chỉ set, không `pip install` |
| Tắt cache/plots | ✓ `cache=False, plots=False` |
| Resume từ `last.pt` (YOLO) | ✓ `YOLO_RESUME` cell |
| `--weights-path` ≠ resume đầy đủ (CCT) | ✓ `CCT_TRAIN_WEIGHTS_ONLY` cell cảnh báo |
| Resume đầy đủ CCT = `last.keras` + `initial_epoch` | ✓ `CCT_TRAIN_FULL` dùng `--resume-keras` |
| Export YOLO ONNX + hash + config | ✓ `YOLO_EXPORT` cell |
| Export CCT ONNX + YAML + hash | ✓ `CCT_EXPORT` cell |
| Manifest đi kèm mọi artifact | ✓ `artifact_*.json` + `.sha256` |
| Preflight manifest/hash/group/split | ✓ `PREFLIGHT_CHECK` cell + reject `pending_data` |
| Dừng `pending_data` nếu thiếu | ✓ `if not pf["ok"]: raise SystemExit(f"pending_data: ...")` |
| Round-trip smoke | ✓ 3 cell SMOKE cuối mỗi notebook |
| Mũ/xe điện KHÔNG gộp model | ✓ `HELMET_TITLE` markdown + 2 slug riêng |

## Verify chạy được

Đã verify:
- `python -B scripts/training/build_notebooks.py` → tạo 3 file
  JSON hợp lệ 10.8-12.7 KB.
- `python -B scripts/training/validate_notebooks.py` → 3/3 OK.
- `pytest app/tests/test_r9_*.py` → 34/34 pass.

Các cell code được verify **compile được** bằng `ast.parse` (không thực thi).
Hàm `preflight` được trích ra và **chạy thực tế** với manifest fixture
trong `test_r9_preflight.py`:
- `preflight_ok_with_valid_manifest` ✓
- `preflight_missing_manifest` ✓ (ok=False, pending_data=True)
- `preflight_zero_count_split` ✓
- `preflight_wrong_holdout_status` ✓
- `preflight_hash_mismatch_raises` ✓ (raise ValueError)

## Đạt / Chưa đạt

### Đạt
- 3 notebook JSON chuẩn nbformat 4.5, mỗi cell có đầy đủ metadata.
- 34 test tự động pass (compile + structure + logic preflight).
- Tuân thủ hầu hết yêu cầu handoff R9.
- Không cần `nbformat` package (Kaggle có sẵn, nhưng local cũng chạy).
- Không stage/commit file; chỉ tạo ở local.

### Chưa đạt (cần R8 + R10 mới có thể chạy thực)
- 3 notebook chưa được chạy thực trên Kaggle (chỉ verify cú pháp + preflight).
- Pre-flight thực tế cần portable dataset (chưa có — R8 chưa xong).
- Không có ảnh mẫu để smoke round-trip cụ thể (cần R8 export trước).

## Đề xuất tiếp theo

1. R8 hoàn tất → export portable dataset → upload lên Kaggle Datasets.
2. Owner B copy 3 notebook lên Kaggle (chỉ local smoke ở đợt này theo
   yêu cầu user "no_kaggle_run").
3. Khi notebook chạy thực, các cell `preflight` sẽ dừng với `pending_data`
   nếu manifest sai → đúng thiết kế.
4. Khi có best.pt YOLO / last.keras CCT → owner sẽ verify ONNX round-trip
   trên CPU, ghi hash, lưu manifest. Tích hợp vào runtime thuộc R7.
5. Helmet notebook: nếu `helmet_detect` vẫn 0 ảnh, cell train sẽ fail
   ở preflight (đúng thiết kế). User cần thu nhãn trước.

## Tóm tắt test R9

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r9_notebooks.py app/tests/test_r9_notebook_builder.py app/tests/test_r9_preflight.py -v
======================== 34 passed, 1 warning in 2.45s ========================
```

## Tóm tắt test R0+R1+R8+R9

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r8_inspect.py app/tests/test_r8_export_smoke.py app/tests/test_r1_storage_guards.py app/tests/test_r9_notebooks.py app/tests/test_r9_notebook_builder.py app/tests/test_r9_preflight.py -v
======================== 52 passed, 1 warning in 5.41s ========================
```

## File Owner B tạo trong R9

```
scripts/training/_notebook_builder.py        # 80 dòng
scripts/training/build_notebooks.py          # ~600 dòng (cell source + builder)
scripts/training/validate_notebooks.py       # 60 dòng
notebooks/yolo11_plate.ipynb                 # 9 cells, 10.8 KB
notebooks/yolo11_helmet_electric.ipynb       # 9 cells, 10.9 KB
notebooks/cct_plate_ocr.ipynb                # 10 cells, 12.7 KB
app/tests/test_r9_notebooks.py               # 16 test
app/tests/test_r9_notebook_builder.py        # 7 test
app/tests/test_r9_preflight.py               # 11 test
tasks/task-05/R9_STATUS.md                   # file này
```