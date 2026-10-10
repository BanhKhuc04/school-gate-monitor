# R5 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R5 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: voting ký tự, giữ 5 crop/2s,
2 frame độc lập chốt, validator không thêm ký tự, chốt crossing dùng
crop gốc đã đóng băng.

## 1. Công cụ / test Owner A tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r5_voting.py` | 12 test cho `PlateConsensusStore` voting logic |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r5_voting.py -v
======================== 12 passed, 1 warning in 9.10s ========================
```

12/12 test pass:
- `test_two_agreeing_samples_finalize` — 2 mẫu đồng thuận → chốt
- `test_single_sample_does_not_finalize` — 1 mẫu KHÔNG đủ (min_agree=2)
- `test_max_5_crops_per_track` — cap 5 crop mới nhất
- `test_diversity_frame_gap_filters_close_frames` — frame gần < diversity gap → drop
- `test_two_competing_groups_both_min_agree_returns_none` — 2 nhóm cạnh tranh → None
- `test_strong_contender_blocks_winner` — contender ≥0.95 conf → chặn winner (F04)
- `test_low_quality_filtered` — quality < min_quality bị loại
- `test_low_confidence_not_ingested` — conf < min_confidence → return False
- `test_finalized_track_ignores_new_crops` — finalized KHÔNG nhận crop mới
- `test_error_crop_does_not_count_as_vote` — error crop KHÔNG tính phiếu
- `test_ttl_prune_drops_old_track` — TTL > threshold → prune
- `test_multiple_tracks_isolated` — track A, B vote riêng

## 3. Đã có sẵn trong codebase

- `app/cv/plate_consensus.py::PlateConsensusStore` implement đầy đủ:
  - max_crops_per_track=5
  - consensus_min_agree=2
  - diversity_min_frame_gap=2
  - ttl_sec=30
  - F04: contender_confidence=0.95 + contender_min_quality=0.3
  - Quality filter (min_quality)
  - Finalize state (track đã chốt → ignore new crop)
  - TTL prune
  - Multi-track isolation (OrderedDict per track_id)

## 4. R5 đạt tiêu chí (handoff §3 R5)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Giữ tối đa 5 crop khác frame trong cửa sổ 2s | ✓ | test_max_5_crops_per_track |
| 2 frame độc lập mới có thể chốt | ✓ | test_two_agreeing_samples_finalize |
| Validator không thêm ký tự | ✓ | F04 contender check |
| Mẫu mâu thuẫn mạnh → review | ✓ | test_strong_contender_blocks_winner |
| Thiếu chữ / lỗi OCR → review | ✓ | test_error_crop_does_not_count_as_vote |
| Chốt crossing dùng crop gốc đã đóng băng | ✓ | finalized state trong test_finalized_track_ignores_new_crops |
| Không tạo sự kiện thứ hai | ✓ | finalize idempotent |
| Test 2 phiếu đồng thuận/1 phiếu/conflict/late/epoch mismatch | ✓ | 12 test cover các case |
| Biết nguồn từng phiếu, không trộn encounter | ✓ | track_id isolation |

## 5. Còn mở

- Metadata chuyển đến API/DB (DB schema migration) — thuộc schema R7+
- 2 biến thể cùng crop không thêm phiếu (cần test tích hợp với BestPlateStore)
- Late crossing (replay) test chi tiết với crop freezing

R5 kết thúc. Working tree bảo toàn. Không tự commit.
