# R8 — Status Report

Date: 2026-10-03. Owner B (KART, hand-off R0/R1). Phạm vi R8 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: duyệt nhãn, holdout độc lập,
thu nhãn mũ/xe điện, đảm bảo `human_curated_group_disjoint` trên mọi dataset.

## Trạng thái trước R8 (đã có sẵn)

Từ đợt trước:
- `scripts/kaggle_dataset_audit.py` — sinh audit JSON + CSV template.
- `scripts/kaggle_export.py` — guard chỉ export khi `human_verified=1`,
  group-disjoint, hash khớp, đủ 3 split.
- `scripts/kaggle_selftest.py` — 10 selftest.
- `tasks/task-05/dataset_audit.json` — 8.259 (detect) + 3.188 (OCR) + 0 (helmet).
- 3 CSV template (`*_curation.csv`).

Tồn đọng:
- 4 nhóm trùng `vn_plate_detect` (handoff §3 R8).
- 1 nhóm trò train/val (`quandoi90` ↔ `quandoi92`).
- 3.173 đề xuất OCR chưa có `plate_text` do người duyệt.
- `helmet_detect`: 0 ảnh.

## Công cụ Owner B tạo trong đợt này

| File | Mục đích |
|---|---|
| `scripts/r8_inspect_audit.py` | CLI xem tóm tắt audit + 4 duplicate groups + OCR + helmet status |
| `app/tests/test_r8_inspect.py` | 3 test cho CLI inspect |
| `app/tests/test_r8_export_smoke.py` | 7 test cho guard `validate_curation` |
| `tasks/task-05/R8_CURATION_GUIDE.md` | Hướng dẫn 7 bước cho người duyệt |

## Công cụ Owner B KHÔNG thể tự làm

Theo handoff R8 cần người:
- Xem 4 nhóm trùng ảnh → chọn ảnh đúng (cần mắt người + so bbox).
- Sửa nhóm rò train/val (`quandoi90/92`) → đổi split hoặc loại.
- Điền `plate_text` cho 3.173 ảnh OCR (cần mắt người xem crop).
- Thu nhãn mũ + xe điện (cần camera thật + annotator).
- Verify 3 ký tự hiếm O/Q/W đã đủ dữ liệu (chỉ 2-4 bbox).

Owner B **không auto-label** theo đúng handoff §3 R8: "không auto-label làm
ground truth". Tất cả ground truth phải do người duyệt.

## Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r8_inspect.py app/tests/test_r8_export_smoke.py -v
======================== 10 passed, 1 warning in 2.10s ========================
```

10/10 test pass:
- `test_r8_inspect.py` (3): CLI với audit thật, audit fixture tối thiểu, audit missing.
- `test_r8_export_smoke.py` (7): reject khi không có `human_verified=1`, reject
  hash đã đổi, reject duplicate image, OCR regex 4-10 A-Z0-9, OCR uppercase OK,
  pending_data khi thiếu split, inspect in 4 group.

## Verify guard đang hoạt động

Đã chạy trực tiếp:
```
$ venv\Scripts\python.exe -B scripts\r8_inspect_audit.py
======================================================================
DETECT DUPLICATES (cần người duyệt chọn 1 ảnh / nhóm)
======================================================================
Group 1: hash=0e08fc1ebfa88435...  cross_split=False  label_conflict=True
  - images/train/quandoi102.jpg
  - images/train/quandoi99.jpg
Group 2: hash=5489d10fa3691947...  cross_split=False  label_conflict=True
  - images/train/quandoi50.jpg
  - images/train/quandoi64.jpg
Group 3: hash=c5eb3518ae3340c4...  cross_split=False  label_conflict=True
  - images/train/quandoi73.jpg
  - images/train/quandoi75.jpg
Group 4: hash=d23ffa53c74e06cb...  cross_split=True  label_conflict=True
  - images/train/quandoi90.jpg
  - images/val/quandoi92.jpg
======================================================================
OCR SUMMARY
  images: 3188, valid: 3188, invalid: 0
  by_split: {'train': 2870, 'val': 318}
  duplicates: 0, cross_split: 0
  rare chars (<10 bbox): [('O', 4), ('Q', 2), ('W', 4)]
  records có proposal_from_labels: 3173 / 3188
======================================================================
HELMET SUMMARY
  {'images': 0, 'valid': 0, ...}
======================================================================
HOLDOUT STATUS
  vn_plate_detect: pending_human_group_curation
  plate_char_ocr: pending_human_group_curation
  helmet_detect: pending_human_group_curation
```

## Đạt / Chưa đạt

### Đạt
- CLI inspect tóm tắt audit, in 4 duplicate groups.
- 10 test pass cho guard export + CLI.
- Guide R8_CURATION_GUIDE.md đầy đủ 7 bước cho người duyệt.
- Manifest schema vẫn giữ nguyên, không thay đổi format.

### Chưa đạt (cần người duyệt / dữ liệu)
- 4 nhóm trùng detect chưa được chọn ảnh đúng.
- Nhóm 4 (`quandoi90/92`) chưa được sửa split.
- 3.173 OCR `plate_text` chưa được điền.
- `helmet_detect` chưa có dữ liệu → R9/R10/R15 phải dùng `pending_data` cho
  task mũ; khóa notebook sẽ dừng ở preflight nếu không có manifest hợp lệ.
- Ký tự O/Q/W hiếm (2-4 bbox) — cần thu thêm nếu muốn CCT OCR đủ ký tự.

## Đề xuất tiếp theo

1. **Người duyệt** chạy `R8_CURATION_GUIDE.md` bước 2-5 để điền CSV.
2. Sau khi đủ 3 split group-disjoint detect + OCR → chạy
   `scripts/kaggle_export.py` (bước 6) → sinh portable dataset.
3. Owner B tiếp tục **R9 (notebook Kaggle)** dựa trên portable dataset đã
   export. Đã có 3 notebook JSON hợp lệ ở `notebooks/`.
4. **Helmet**: cần Owner A/người dùng thu nhãn trước khi R10 mở.

## File Owner B tạo trong R8

```
scripts/r8_inspect_audit.py          # CLI inspect audit + duplicates
app/tests/test_r8_inspect.py         # 3 test
app/tests/test_r8_export_smoke.py    # 7 test
tasks/task-05/R8_CURATION_GUIDE.md   # hướng dẫn 7 bước
tasks/task-05/R8_STATUS.md            # file này
```

Không sửa code runtime; không stage file nào; không tự ghi CV curation
mà chỉ cung cấp tool cho người duyệt.
