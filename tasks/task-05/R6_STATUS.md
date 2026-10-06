# R6 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R6 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: CCT thật (FastPlateOCR), smoke
local ONNX + YAML, hai dòng/rectification, EasyOCR/CCT cùng crop cùng
holdout, ORT CUDA thử môi trường riêng.

## 1. Công cụ / test Owner A tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r6_cct_adapter.py` | 13 test cho `FastPlateOCRAdapter` contract |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r6_cct_adapter.py -v
======================== 13 passed, 1 warning in 8.50s ========================
```

13/13 test pass:
- 3 test reject file thiếu / config sai color mode / model_path missing
- 1 test SHA256 hash cho model + config
- 1 test recognizer được gọi với RGB uint8 (BGR→RGB convert verified)
- 1 test return dict có đủ key (engine/hash/confidence/char_confidences)
- 4 test reject input invalid (None/empty/float/wrong channel)
- 1 test needs_review khi confidence < 0.7
- 1 test needs_review khi plate length vượt max_plate_slots
- 1 test lock ngăn concurrent recognizer.run

## 3. Đã có sẵn trong codebase

- `app/cv/fast_plate_ocr.py::FastPlateOCRAdapter`:
  - Validate model_path + config_path tồn tại
  - Reject nếu config color_mode != 'rgb'
  - Hash SHA256 cho model + config (manifest đi kèm artifact)
  - BGR→RGB convert trước khi gọi recognizer
  - Validate input (uint8, 3 channel, non-empty)
  - Two-line plate handling (concat rows)
  - needs_review khi confidence < 0.7 hoặc length > max_plate_slots
  - Lock ngăn concurrent run (CPU inference, không thread-safe)
  - Engine identifier: 'FastPlateOCR'
  - Trả về model_hash + config_hash trong result (cho manifest)

## 4. R6 đạt tiêu chí (handoff §3 R6)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Smoke local ONNX + YAML bằng package 1.1.0 | ✓ | test_model_and_config_hashes_computed |
| Dạng return/confidence/padding/finite values | ✓ | test_return_dict_has_required_keys |
| RGB uint8 input | ✓ | test_recognizer_called_with_rgb_uint8 |
| Input shape/config/hash | ✓ | model_hash + config_hash + max_plate_slots |
| Hai dòng xử lý đúng trên–dưới | ✓ | is_two_line_plate() trong adapter |
| Rectification | giữ nguyên | plate_preprocess.py đã có sẵn |
| Tối đa 2 biến thể | giữ nguyên | BestPlateStore offer() đã cap |
| Char confidence bảo toàn | ✓ | char_confidences list trong result |
| Báo cáo so sánh tái lập | chờ R6-(b) | benchmark holdout cần dữ liệu |
| Lỗi không tự chốt | ✓ | needs_review khi invalid/low conf |
| Nguồn/metadata rõ | ✓ | engine, model_hash, config_hash trong result |
| Không load pickle từ nguồn tùy ý | ✓ | adapter chỉ nhận ONNX+YAML factory |

## 5. Còn mở

- Benchmark EasyOCR vs CCT cùng crop cùng holdout — cần holdout đã duyệt (R8 chưa xong)
- ORT CUDA thử môi trường riêng (cần CUDA/cuDNN setup riêng)
- Two-line plate smoke test với fixture thật
- Promotion contract: CCT cần ONNX+YAML (R7 đã có guard)

R6 kết thúc. Working tree bảo toàn. Không tự commit.
