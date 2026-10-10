# R8 — Hướng dẫn duyệt nhãn/holdout

Ngày: 2026-10-03. Tạo cùng đợt Owner B triển khai R0/R1/R8. Mục đích: giúp
người duyệt hoàn tất bốn bước R8 (handoff §3 R8) với công cụ có sẵn, không
cần đụng vào code runtime.

## Tổng quan trạng thái

| Bộ dữ liệu | Ảnh | Trạng thái |
|---|---:|---|
| `vn_plate_detect` | 8.259 | 4 nhóm trùng detect, 1 nhóm rò train/val; cần người duyệt |
| `plate_char_ocr` | 3.188 | 3.173 đề xuất OCR; **plate_text** để trống; cần người duyệt |
| `helmet_detect` | 0 | `pending_data` — cần thu nhãn trước |

Audit JSON: `tasks/task-05/dataset_audit.json` (file lớn 10 MB).
Curation CSV mẫu: `tasks/task-05/vn_plate_detect_curation.csv`,
`plate_char_ocr_curation.csv`, `helmet_detect_curation.csv`.

## Bước 1 — Kiểm tra trạng thái (Owner B chạy)

```powershell
venv\Scripts\python.exe -B scripts\r8_inspect_audit.py
```

Output in ra:
- 4 nhóm trùng detect (cần chọn 1 ảnh / nhóm).
- OCR: số ảnh có `proposal_from_labels` (3.173 / 3.188).
- OCR: ký tự hiếm (O:4, Q:2, W:4 bbox).
- Helmet: 0 ảnh.
- Tất cả 3 bộ: `holdout_status: pending_human_group_curation`.

## Bước 2 — Duyệt 4 nhóm trùng `vn_plate_detect`

Nhóm 1: `quandoi99.jpg` vs `quandoi102.jpg` (label_conflict)
Nhóm 2: `quandoi50.jpg` vs `quandoi64.jpg` (label_conflict)
Nhóm 3: `quandoi73.jpg` vs `quandoi75.jpg` (label_conflict)
Nhóm 4: `quandoi90.jpg` (train) vs `quandoi92.jpg` (val) — **rò train/val**

Cho mỗi nhóm:
1. Mở cả 2 ảnh + label.
2. Chọn ảnh có bbox đúng hơn; copy `image_sha256` và `label_sha256` từ audit.
3. Trong `vn_plate_detect_curation.csv`:
   - Hàng ảnh được chọn: điền `human_verified=1`, `group_id`, `split` (đã có từ audit).
   - Hàng ảnh bị loại: `human_verified=0` (giữ nguyên) hoặc xóa hàng.
5. Nhóm 4 (rò train/val): buộc chọn 1 ảnh; ảnh kia `human_verified=0`.

Quy tắc `group_id`:
- Mỗi nhóm trùng phải có cùng `group_id` (vd: `quandoi_dup_1`) để kaggle_export
  phát hiện cross_split và reject.
- Ảnh rò train/val nên đổi `split` sang test (giữ test riêng biệt) hoặc loại.

## Bước 3 — Duyệt OCR `plate_char_ocr`

Với mỗi ảnh OCR có `proposal_from_labels` (3.173 dòng):
1. Mở ảnh crop.
2. Đọc chuỗi đề xuất (`proposal_from_labels`).
3. Nếu đúng → copy sang `plate_text`.
4. Nếu sai → điền đúng theo ảnh (4-10 ký tự A-Z0-9).
5. Nếu không đọc được → để trống + ghi chú riêng; KHÔNG điền giả.

Lưu ý:
- Ký tự O/Q/W chỉ có 2-4 bbox — thiếu dữ liệu cho các chữ hiếm.
- `human_verified=0` → không export được.
- Format check: regex `^[A-Z0-9]{4,10}$` (xem `kaggle_export.py:validate_curation`).

## Bước 4 — Thu nhãn mũ (cần dữ liệu mới)

`helmet_detect` hiện 0 ảnh → `pending_data`. Không thể R10 train YOLO mũ
nếu không có dữ liệu.

Hướng thu nhãn (cần người + camera thật):
1. Quay video cổng trường ≥2 giờ (giờ đến/đi học).
2. Trích frame theo chu kỳ 1 giây.
3. Annotate 4 lớp: `with_helmet`, `no_helmet`, `occluded`, `unknown`.
4. Group theo encounter (xe vào/ra) để giữ group-disjoint train/val/test.
5. Tối thiểu 300 lượt có nhãn cho R15 nghiệm thu.

Sau khi có dataset, chạy lại:
```powershell
venv\Scripts\python.exe -B scripts\kaggle_dataset_audit.py --datasets datasets\helmet_v1 --output tasks\task-05\helmet_audit_v1.json
```

## Bước 5 — Kiểm tra guard trước khi export

Sau khi điền CSV, chạy test guard (đã có):
```powershell
venv\Scripts\python.exe -m pytest app\tests\test_r8_export_smoke.py -v
```

Test sẽ kiểm:
- Không có `human_verified=1` → pending_data.
- Hash đã đổi từ audit → reject.
- Không đủ 3 split → pending_data.
- Group rò → reject.
- OCR plate_text không khớp regex → reject.

## Bước 6 — Export portable dataset

Khi CSV đã duyệt đủ 3 split group-disjoint:

```powershell
# Detect
venv\Scripts\python.exe -B scripts\kaggle_export.py `
  --audit tasks\task-05\dataset_audit.json `
  --dataset vn_plate_detect `
  --curation tasks\task-05\vn_plate_detect_curation.csv `
  --kind detect `
  --output data_exports\plate_detect_v1

# OCR
venv\Scripts\python.exe -B scripts\kaggle_export.py `
  --audit tasks\task-05\dataset_audit.json `
  --dataset plate_char_ocr `
  --curation tasks\task-05\plate_char_ocr_curation.csv `
  --kind ocr `
  --output data_exports\plate_ocr_v1
```

Output:
- `images/{train,val,test}/<sha>.jpg`
- `labels/{train,val,test}/<sha>.txt` (detect) hoặc `{train,val,test}.csv` (OCR)
- `data.yaml` (detect) hoặc `plate_config.yaml` (OCR)
- `manifest.json` + `manifest.sha256` (chứa `holdout_status: human_curated_group_disjoint`)

## Bước 7 — Selftest kaggle_export

```powershell
venv\Scripts\python.exe -B scripts\kaggle_selftest.py
```

10 test đã có. Chạy để đảm bảo selftest không bị hỏng khi sửa audit.

## Quy tắc vàng

- KHÔNG auto-label làm ground truth. Mọi `plate_text` phải do người điền.
- KHÔNG suy `group_id` từ tên file — chỉ từ video/session/encounter thật.
- KHÔNG pseudo-label từ prediction model.
- KHÔNG đổi CSV gốc đang duyệt — copy sang phiên bản mới nếu cần thử.
- Hash không khớp audit → đó là dấu hiệu file đã bị sửa → reject.

## Tiếp theo

Khi đủ:
- `vn_plate_detect_curation.csv`: ≥1 hàng `human_verified=1` cho mỗi split, không
  group rò, không ảnh trùng cross-split.
- `plate_char_ocr_curation.csv`: `plate_text` đầy đủ 4-10 A-Z0-9 cho các ảnh
  verify được.
- `helmet_detect_curation.csv`: có dữ liệu mới (chưa có → R10 pending).

Owner B sẽ tạo 3 notebook Kaggle (R9) dựa trên dataset portable đã export ở
bước 6. Notebook sẽ check preflight manifest/hash trước khi train.

## File Owner B tạo trong đợt này

- `scripts/r8_inspect_audit.py` — CLI xem tóm tắt audit + duplicate groups
- `app/tests/test_r8_inspect.py` — 3 test cho CLI
- `app/tests/test_r8_export_smoke.py` — 7 test cho guard validate_curation
- `tasks/task-05/R8_CURATION_GUIDE.md` — file này