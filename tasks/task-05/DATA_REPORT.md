# T6A/B — Lát audit dữ liệu và xuất bộ đã duyệt

Ngày: 2026-10-03. **Đã hoàn thành audit và công cụ export; chưa hoàn thành notebook/training Kaggle.** Dừng mở thêm implementation theo yêu cầu chuyển sang plan bàn giao Cursor. Không train local, tải dataset/weights, thay đổi nhãn nguồn hoặc stage/commit.

## Kết quả kiểm tra toàn bộ nhãn hiện có

| Bộ dữ liệu | Ảnh | Train / val hiện có | Hợp lệ cấu trúc | Kết luận |
|---|---:|---:|---:|---|
| `vn_plate_detect` | 8.259 | 7.434 / 825 | 8.259 | 8.452 bbox; 4 nhóm ảnh trùng pixel, có 1 nhóm lọt train/val |
| `plate_char_ocr` | 3.188 | 2.870 / 318 | 3.188 | 36 lớp ký tự; không phát hiện ảnh trùng pixel |
| `helmet_detect` | 0 | 0 / 0 | 0 | `pending_data`; chưa có nhãn để train |

Không phát hiện nhãn mồ côi hoặc bbox lỗi class/range/NaN trong ba bộ. Đây là kiểm tra cấu trúc, không chứng minh nhãn đúng hoặc độ đúng nhận diện. Chưa có nhãn xe điện được kiểm chứng trong phạm vi ba bộ này. Chưa audit pool CVAT, video hoặc ảnh gần trùng.

Ảnh trùng trong detect có bbox khác nhau, cần chọn một ảnh và duyệt lại nhãn:

- `images/train/quandoi102.jpg` và `images/train/quandoi99.jpg`.
- `images/train/quandoi50.jpg` và `images/train/quandoi64.jpg`.
- `images/train/quandoi73.jpg` và `images/train/quandoi75.jpg`.
- `images/train/quandoi90.jpg` và `images/val/quandoi92.jpg`: trùng giữa train/val.

OCR có 3.173 đề xuất chuỗi từ thứ tự bbox ký tự trên–dưới, trái–phải. Cột `proposal_from_labels` chỉ hỗ trợ người duyệt; `plate_text` để trống và mọi dòng `human_verified=0`. 15 ảnh không tạo đề xuất, gồm ảnh legend/quá nhiều ký tự hoặc bố cục không phù hợp. Ký tự O/Q/W chỉ có 4/2/4 bbox; chưa đủ cơ sở xác nhận chất lượng cho các ký tự hiếm.

**Các split hiện có không được gọi là holdout độc lập.** Người duyệt phải xác định `group_id` từ video/session/encounter thực tế, chia nhóm sang train/val/test và xác minh nhãn. Không suy ra nhóm từ tên file. Bộ public hiện có thiếu nguồn nhóm đã được kiểm chứng; cần bổ sung provenance hoặc thu dữ liệu vận hành cho holdout.

## Công cụ đã có

- `scripts/kaggle_dataset_audit.py`: đọc dữ liệu, kiểm bbox và mapping, hash file/nhãn/pixel, phát hiện ảnh trùng và xuất JSON + CSV duyệt. Bỏ qua `path` tuyệt đối trong YAML, dùng root được truyền. Từ chối ghi đè kết quả/CSV đã có để giữ công việc duyệt.
- `scripts/kaggle_export.py`: chỉ lấy dòng `human_verified=1`; kiểm hash ảnh/nhãn, group và split, từ chối cùng group giữa các split hoặc cùng ảnh/pixel nhiều lần. OCR chỉ dùng chuỗi người duyệt đã nhập, không sửa ký tự hoặc dùng dự đoán làm nhãn.
- Export detect tạo thư mục ảnh/nhãn theo split và `data.yaml` tương đối. Export OCR tạo CSV `image_path,plate_text`, RGB64×128, 10 slots, alphabet0–9/A–Z/pad. Manifest giữ hash, mapping, group, số mẫu và nguồn; hash tính đúng trên bytes đã ghi ở Windows.
- Kiểm lại file nguồn trước khi tạo output, không ghi đè phiên bản export, giới hạn tổng file được chọn ≤1GB và yêu cầu ≥10GB trống + chỗ dự kiến. Chỉ copy ảnh/nhãn được chọn; không đọc DB/hồ sơ học sinh.
- Công cụ xuất **thư mục portable**, chưa tạo/upload Kaggle Dataset hoặc notebook. ZIP trên UI dùng API export hiện có của backend, không phải công cụ curation này.

Audit JSON + ba CSV khoảng10,04MB. Không copy cả kho dữ liệu hoặc tạo các biến thể crop.

## Kiểm chứng

- `venv/Scripts/python.exe -B scripts/kaggle_selftest.py`: **10/10 đạt**,0,110giây. Bao gồm label lỗi, thứ tự hai dòng, loại legend, không ghi đè CSV, group rò split, ảnh trùng, hash đổi, giữ sửa chuỗi của người duyệt, round-trip detect/OCR, hash manifest Windows, đường dẫn portable và dung lượng dưới10GB.
- Ba script compile bằng `compile()` đạt; không sinh `__pycache__`.
- Export thử fixture ba ảnh đạt cho detect và OCR, kiểm toàn bộ đường dẫn CSV/manifest và hash. Không dùng GPU. Fixture kiểm dung lượng dùng mock; các kiểm hash/nhãn/group dùng file thật.
- Export CSV thực chưa duyệt bị chặn `pending_data: no human-reviewed samples selected`, output không được tạo.
- `git diff --check` phạm vi scripts/frontend đạt. Chưa chạy full regression, chưa train hoặc công bố metrics model.

Ví dụ audit một phiên bản mới (không dùng lại thư mục CSV đang duyệt):

```powershell
venv/Scripts/python.exe -B scripts/kaggle_dataset_audit.py --output tasks/task-05/review-next/dataset_audit.json
```

Sau khi người duyệt điền nhóm/split và nhãn, export riêng từng bài toán:

```powershell
venv/Scripts/python.exe -B scripts/kaggle_export.py --audit tasks/task-05/dataset_audit.json --dataset vn_plate_detect --curation tasks/task-05/vn_plate_detect_curation.csv --kind detect --output data_exports/plate_v1
venv/Scripts/python.exe -B scripts/kaggle_export.py --audit tasks/task-05/dataset_audit.json --dataset plate_char_ocr --curation tasks/task-05/plate_char_ocr_curation.csv --kind ocr --output data_exports/ocr_v1
```

## Phần Cursor tiếp tục

1. Duyệt bốn nhóm trùng/bbox khác nhau; bổ sung provenance, chia theo nhóm và giữ test độc lập. Duyệt các đề xuất OCR, xác minh mapping 36 ký tự từ nguồn nhãn. Thu/gán nhãn mũ, xe điện và các ca camera khó; không auto-label làm ground truth.
2. Viết ba notebook riêng: `yolo11_plate.ipynb`, `yolo11_helmet_electric.ipynb`, `cct_plate_ocr.ipynb`. Chúng **chưa được tạo** trong lát này. Preflight manifest/hash/group/split; dừng `pending_data` nếu nhãn thiếu. Mũ và xe điện train từng bài toán với mapping được người duyệt chốt.
3. YOLO dùng Ultralytics8.4.168 và YOLO11n; giữ best/last, config, mapping, metrics và hash, cache/plots tắt. Resume từ checkpoint, dùng `save_dir` ghi được trên Kaggle và cùng manifest; không ép upgrade Torch local. Baseline/challenger đánh giá cùng holdout.
4. CCT dùng FastPlateOCR1.1.0 train extras chỉ trong Kaggle. CSV đúng `image_path,plate_text`; config RGB64×128/10slots đi cùng artifact. CLI `--weights-path` chỉ nạp weights và tạo optimizer mới, **không được gọi là resume đầy đủ**. Resume đầy đủ cần load compiled `last.keras` giữ optimizer qua `load_keras_model`, đúng config/manifest/batch và `initial_epoch`. Kiểm số bước trước khi tiếp tục.
5. Xuất CCT ONNX uint8/channels_last, YAML/config/hash và metrics; xác minh OCR cùng crop với EasyOCR. Import artifact local và xác nhận runtime/rollback vẫn thuộc các task backend tiếp theo. Không ghi “đã train” cho đánh giá baseline.

Hợp đồng đã đối chiếu với [Ultralytics training](https://docs.ultralytics.com/modes/train/), [FastPlateOCR dataset](https://github.com/ankandrew/fast-plate-ocr/blob/master/docs/training/dataset.md), [train CLI](https://github.com/ankandrew/fast-plate-ocr/blob/master/docs/training/cli/train.md) và [export CLI](https://github.com/ankandrew/fast-plate-ocr/blob/master/docs/training/cli/export.md); đồng thời đọc source package đã cài cho resume/config. Chưa thực thi train notebook nên chưa xác nhận khả năng chạy Kaggle end-to-end.

## File tạo/sửa của lát dữ liệu

1. `scripts/kaggle_dataset_audit.py`
2. `scripts/kaggle_export.py`
3. `scripts/kaggle_selftest.py`
4. `tasks/task-05/dataset_audit.json`
5. `tasks/task-05/vn_plate_detect_curation.csv`
6. `tasks/task-05/plate_char_ocr_curation.csv`
7. `tasks/task-05/helmet_detect_curation.csv`
8. `tasks/task-05/DATA_REPORT.md`

QA thử ban đầu còn thư mục nhỏ `qa_logs/task05_dataset_fixture`, hash manifest của lần thử đầu không hợp lệ và không được dùng làm dataset. Selftest sau sửa chạy trong thư mục tạm tự dọn. Không stage/commit file nào; báo cáo UI riêng ở `UI_REPORT.md`.
