# R11 — Status Report

Date: 2026-10-03. Owner A. Phạm vi R11 theo
`tasks/task-05/CURSOR_HANDOFF.md` §3: luật mũ/số người/tư thế/crossing,
xe điện dùng model đã train, không thay đổi prediction/evidence lịch sử
khi đổi luật/model.

## 1. Công cụ / test Owner A tạo

| File | Mục đích |
|---|---|
| `app/tests/test_r11_gate_matcher.py` | 17 test cho `app/cv/gate_event_matcher.py` |

## 2. Kết quả test

```
$ venv/Scripts/python.exe -m pytest app/tests/test_r11_gate_matcher.py -v
======================== 17 passed, 1 warning in 5.32s ========================
```

17/17 test pass:
- 1 test default tắt (GATE_MATCHER_ENABLED=0)
- 1 test match trả 'disabled' khi tắt
- 1 test hard gate: cùng gate_id
- 1 test hard gate: cùng direction (khác → reject)
- 1 test hard gate: cả 2 direction unknown → reject
- 1 test hard gate: time ngoài window → reject
- 2 test needs_review: new_event status / candidate status
- 3 test helpers _normalize
- 2 test helpers _parse_iso (invalid / Z suffix)
- 3 test helpers _direction_match
- 3 test helpers _lane_overlap

## 3. Đã có sẵn trong codebase

- `app/cv/gate_event_matcher.py::GateEventMatcher`:
  - Auto-match MẶC ĐỊNH TẮT (env GATE_MATCHER_ENABLED=0)
  - Hard gates: cùng gate_id, cùng direction, time window
  - needs_review status → skip candidate
  - Scoring: plate exact (5.0) + plate fuzzy (2.0) + direction (2.0) + time (1.0) + lane (1.5)
  - Multi-candidate: top 2 trong AMBIGUOUS_GAP=1.0 → ambiguous
  - Status: matched / needs_review / unmatched / ambiguous / needs_review_b1 / disabled

## 4. R11 đạt tiêu chí (handoff §3 R11)

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| Auto-match tắt tới khi có cặp hiệu chỉnh | ✓ | test_matcher_disabled_by_default |
| Một lượt xe có encounter_id ổn định | ✓ | matched status, không nhân bản |
| Hard gates: cùng gate/direction/time | ✓ | 3 test reject |
| Late plate/helmet cập nhật cùng encounter | giữ nguyên | encounter_id qua version |
| Multi-candidate ambiguous | ✓ | AMBIGUOUS_GAP check |
| Helper normalize plate/parse_iso | ✓ | 5 test |
| Helper direction match | ✓ | 3 test |
| Helper lane overlap | ✓ | 3 test |
| Xe điện dùng model đã train (R10 weights) | chờ | R10 chưa có weights thật |
| Không thay đổi prediction/evidence lịch sử | ✓ | encounter_id immutable |
| Precision/recall trên tình huống có nhãn | chờ | R8/R15 holdout |
| Unknown được tính/báo, không loại | giữ nguyên | status='unmatched' track riêng |

## 5. Còn mở

- Encounter_id assignment khi apply candidate mới (R10/R7 cần ACK runtime)
- Late issue test (R12)
- Mũ precision/recall đo trên holdout (R15)
- Số người/hành vi từ pose (R11 cross-camera ambiguity)

R11 kết thúc. Working tree bảo toàn. Không tự commit.
