# Kế hoạch: Nhận diện gương + Nhiều người vào/ra cổng cùng lúc

> Viết cho nhánh `codex/alpr-yolo11-local` (commit `7db755f`). Đường dẫn file và
> tên hàm bên dưới lấy từ nhánh đó. Làm **Phần A trước**: Phần B (gương) cần
> biết chiều đi của xe để phân biệt gương trái/phải.

---

## Hiện trạng: code đang làm được gì, thiếu gì

Đã có sẵn và dùng lại được:
- `app/cv/crossing.py`: `CrossingDetector` xác định xe cán vạch bằng điểm neo
  (đáy giữa bbox xe), có chiều `enter`/`exit`, dead-zone, latch, cooldown.
- `app/cv/detector.py`: ByteTrack gán ID cho từng đối tượng.
- `app/cv/pipeline.py`: ghép người với xe (`_vertical_overlap`), đếm người
  trên xe (`_count_riders_per_vehicle`), gắn `rider_track_id` /
  `passenger_track_ids`.
- `app/cv/gate_event_matcher.py`: ghép camera trước/sau, có yếu tố "cùng chiều".

Vấn đề khi **1 người vào + 1 người ra cùng lúc** (đã đọc code xác nhận):

| # | Vấn đề | Chỗ trong code | Hậu quả |
|---|---|---|---|
| 1 | ~~Loa cảnh báo tức thì không kiểm tra chiều~~ — **kiểm tra lại: hàm `_check_instant_gate_alert` không được vòng lặp chính gọi (code chết)**. Cảnh báo thật đi qua `_process_vehicle_crossings`, vốn đã lọc chiều qua `has_crossed` | `_check_instant_line_crossing` | Không ảnh hưởng thực tế — người đi ra **không** bị loa nhắc |
| 2 | Chỉ ghi nhận 1 chiều: `crossing_motion()` mặc định `down` (camera trước) / `up` (camera sau) → `allowed_direction` loại bỏ chiều còn lại | `app/config.py` `crossing_motion`, `_make_crossing_detector` | Người đi ra **không được ghi lại**, không đếm được ra/vào |
| 3 | Người đi bộ (không có xe) không bao giờ qua `CrossingDetector` | `_update_crossing`: `if vehicle is None: return False` | Không đếm được người đi bộ vào/ra |
| 4 | `_pedestrian_count` / `_rider_count` cộng **mỗi frame** mỗi group | `pipeline.py` ~dòng 2489 | Số đếm là "số lần thấy", không phải "số người" |
| 5 | Hai người đi ngược chiều lướt qua nhau → ByteTrack có thể **tráo ID** | `detector.py` (ByteTrack thuần, không ReID) | Chiều bị đảo: người vào bị ghi là ra và ngược lại |
| 6 | ID của tracker xe và tracker người có thể trùng số, nhưng dùng chung 1 bảng `_tracks` khi fallback `track_id` | `_update_crossing`: `tid = vehicle_track_id or track_id` | Hai đối tượng khác nhau có thể dùng chung lịch sử crossing |

---

## PHẦN A: Nhiều người vào/ra cùng lúc, nhận diện đúng chiều

### A0. Dữ liệu kiểm chứng (làm đầu tiên, khoảng 1 buổi)

Quay 15–20 clip ngắn (10–30 s) **tại đúng cổng, đúng vị trí camera**, mỗi kịch bản 2–3 lần:

1. 1 xe vào + 1 xe ra cùng lúc (2 làn đối nhau)
2. 1 xe vào + 1 người đi bộ ra
3. 2 người đi bộ ngược chiều, đi **sát và lướt qua nhau** ngay tại vạch (dễ tráo ID nhất)
4. 1 xe chở 2 người vào + 1 xe 1 người ra
5. Nhóm 3–4 học sinh đi bộ vào cùng lúc
6. Xe dắt bộ vào, xe chạy ra
7. Xe dừng ngay trên vạch rồi đi tiếp; xe lùi lại ra ngoài (không tính là vào)

Ghi đáp án vào `datasets/gate_direction_gt.csv`:

```
clip,giay,doi_tuong,chieu,so_nguoi
c03_lot_qua.mp4,4.2,pedestrian,enter,1
c03_lot_qua.mp4,4.5,pedestrian,exit,1
```

**Tiêu chí đạt:**
- Đúng chiều ≥ 98% số lượt.
- Không đếm trùng.
- Không có lượt "ra" nào làm phát loa.
- Kịch bản 3 không tráo chiều.

### A1. Ghi nhận CẢ 2 chiều, chỉ cảnh báo chiều VÀO

- `CrossingDetector` luôn ghi nhận cả `enter` và `exit` (`allowed_direction=None`).
- Lọc chiều ở **tầng quyết định** chứ không lọc ở tầng phát hiện:
  - `enter` → xét vi phạm (mũ, chở quá người, gương...) + loa.
  - `exit` → chỉ ghi log ra/vào, **không** phát loa, không tạo vi phạm (trừ khi admin bật).
- Giữ `crossing_motion()` để biết "đi xuống trong ảnh = vào" cho từng camera,
  nhưng dùng nó để **gán nhãn** chiều, không phải để loại bỏ.
- Lùi xe: đã đi qua vạch (`enter`) rồi lùi ngược lại (`exit`) trong < N giây
  với cùng track → ghi là "quay đầu", huỷ lượt vào.

### A2. Cảnh báo chỉ cho chiều VÀO (đã đúng sẵn)

Đọc lại code: cảnh báo/vi phạm chỉ seal khi `has_crossed`, mà `has_crossed`
chỉ bật cho chiều `allowed_direction` (chiều vào). Hàm loa tức thì
`_check_instant_gate_alert` là code chết. Đã thêm test khẳng định lượt RA
không bao giờ bật `has_crossed`.

### A3. Người đi bộ cũng được tính qua vạch (bug #3)

- Group không có xe → dùng điểm neo = **đáy giữa bbox người** (chân), đưa vào
  `CrossingDetector`.
- Khóa lịch sử crossing theo cặp `("veh", id)` / `("ped", id)` thay vì số
  trần, để ID xe và ID người không bao giờ dùng chung lịch sử (bug #6).
- Người ngồi trên xe **không** tính riêng: kế thừa chiều của xe
  (`rider_track_id`, `passenger_track_ids` đã có sẵn).

### A4. Chống tráo ID khi 2 người lướt qua nhau (bug #5)

Áp dụng **cả ba** biện pháp, chi phí GPU gần như bằng 0:

1. **Hai vạch (vùng đệm)** thay cho 1 vạch: chỉ chốt `enter` khi điểm neo đi
   qua vạch A **rồi** vạch B theo đúng thứ tự (`exit` thì ngược lại). Track bị
   tráo giữa chừng sẽ không đi đủ A→B nên không bị đếm sai. Admin vẽ 2 vạch
   song song cách nhau khoảng 0,5–1 m trên trang ROI.
2. **Kiểm tra vận tốc nhất quán:** chiều suy ra từ dịch chuyển trung bình
   8–10 frame cuối phải **cùng dấu** với chiều cán vạch. Không khớp → trạng
   thái `review`, không tự chốt.
3. **Chặn nhảy vị trí:** điểm neo nhảy > ~1/3 chiều cao bbox trong 1 frame,
   hoặc đổi hướng chuyển động ngược hẳn → đánh dấu "nghi tráo ID", reset lịch
   sử crossing của track đó.

Nếu sau A0 vẫn còn tráo ID ở kịch bản 3, thử **BoT-SORT** của ultralytics
(có GMC, ReID tùy chọn). Phải đo FPS trên RTX 3050 trước khi bật.

### A5. Đếm đúng số người (bug #4)

- Đếm theo **track đã chốt crossing**, không đếm theo frame.
- Bảng mới `gate_passages`:
  `(id, gate_id, camera, track_key, object_type[pedestrian|motorbike|bicycle], direction[enter|exit|u_turn], persons_count, crossed_at, confidence, status[ok|review])`.
- Dashboard: số vào/ra theo giờ, tách người đi bộ / người đi xe.

### A6. Hai camera trước/sau

Sau A1, cả 2 camera đều ghi cả 2 chiều. Yếu tố "cùng chiều" trong
`gate_event_matcher.py` lúc này mới có dữ liệu để dùng. **Không bật**
auto-match (`GATE_MATCHER_ENABLED`) cho đến khi có cặp lượt kiểm chứng từ A0.

### A7. Test

- **Unit test** (`app/tests/test_bidirectional_crossing.py`): 2 track giả lập
  đi ngược chiều cùng lúc; 2 track tráo ID tại vạch; người đi bộ; xe chở 2
  người; lùi xe; dừng trên vạch.
- **Replay test:** chạy pipeline trên clip A0, so với `gate_direction_gt.csv`,
  in bảng đúng/sai theo kịch bản.
- Toàn bộ test hiện có (`test_crossing*.py`, `test_vehicle_crossing_aggregation.py`...)
  vẫn phải pass.

---

## PHẦN B: Camera nhận diện gương chiếu hậu

### B0. Bài toán và giới hạn (đọc kỹ trước khi làm)

- Mục tiêu: phát hiện xe máy **thiếu gương bên trái người lái** (luật bắt buộc
  có gương trái).
- Kế hoạch cũ (`tasks/task-01/plan.md`) đã chốt và vẫn đúng: camera trước đặt
  lệch phải **không đảm bảo thấy gương trái**, nên chỉ review, không cảnh báo
  khi chưa đủ góc nhìn và dữ liệu.
- **Không bao giờ** báo "thiếu gương" chỉ vì model không thấy gương. Không thấy
  ≠ không có (gương có thể bị tay, đầu hoặc người khác che, hoặc ảnh quá nhỏ).

### B1. Đặt camera (quan trọng nhất, quyết định làm được hay không)

- Gương rất nhỏ. Dataset 300 ảnh bạn gửi có xe rộng trung vị **76 px** (nhỏ
  nhất 31 px), nên gương chỉ khoảng 5–8 px, **quá nhỏ để model nhận ra**.
- Yêu cầu tại điểm quyết định: **xe rộng ≥ 250 px** trong khung hình, để gương
  khoảng ≥ 15–20 px.
- Vị trí đề xuất: camera **chính diện hoặc lệch trái** so với làn vào, cao
  2,2–2,8 m, chúc xuống 20–30°, cách vạch 4–6 m. Nếu camera trước hiện tại
  phải giữ góc lệch phải cho mũ/biển, cân nhắc **camera thứ 3** chỉ cho gương.
- Cấu hình mỗi camera: `MIRROR_LEFT_OBSERVABLE=1` chỉ bật cho camera nhìn
  thấy được gương trái (cờ đã có trong `tasks/task-01/CONTRACTS.md`).

### B2. Dữ liệu

**Dataset `VN_street_motorbike_300` (bạn gửi):**
- 300 ảnh crop xe máy từ camera giao thông TP.HCM, nguồn Kaggle, giấy phép
  CC BY 4.0 (phải ghi nguồn khi dùng).
- Phân bố góc: 210 trước, 60 ngang, 30 sau.
- **Chưa có nhãn gương** (`mirror_count_visible = null`). Chỉ có box xe + tag góc.
- Ảnh nhỏ (rộng trung vị 152 px), xe nhỏ nên chỉ dùng làm **dữ liệu phụ / tiền
  huấn luyện**, không đủ để làm model chính.

**Cách gán nhãn trong CVAT** (import file zip CVAT 1.1 sẵn có):
1. Thêm label `mirror` (rectangle). Vẽ box quanh **mặt gương** (không vẽ cả cần gương).
2. Thêm tag cho cả ảnh `mirror_state` với các giá trị:
   `both | only_left | only_right | none | occluded | too_small`.
   Trái/phải tính **theo người lái**: ảnh chụp từ phía trước thì gương trái
   người lái nằm **bên phải ảnh**.
3. Loại ảnh có xe rộng < 60 px (đánh `too_small`, không đưa vào train).
4. Mở rộng vùng crop **lên trên 25–30%**, vì gương thường nhô cao hơn tay lái
   và có thể bị cắt mất khỏi box xe.

**Dữ liệu chính, quay tại cổng** (bắt buộc trước khi bật cảnh báo):
- ≥ 300 lượt xe qua cổng có crop rõ.
- Trong đó ≥ 100 xe **thiếu gương trái rõ ràng** và ≥ 100 xe đủ gương (kế
  hoạch cũ ghi tối thiểu 30/30; 100/100 mới đo precision đáng tin).
- Có thể dàn dựng: tháo gương trái 3–5 xe, chạy qua cổng nhiều lần, nhiều giờ
  khác nhau (sáng, trưa, chiều).

### B3. Model và cách quyết định

- **2 tầng:**
  1. Pipeline hiện có phát hiện và track xe.
  2. Crop xe (đã mở rộng phía trên), đưa qua model **YOLO11n 1 lớp `mirror`**,
     imgsz 320. Chỉ chạy trên xe **đang vào** và **gần vạch**, 3–5 crop/xe,
     chạy batch. RTX 3050 dư sức.
- **Trái/phải theo hình học:**
  - So tâm box gương với tâm tay lái (giữa box xe). Xe đi **về phía camera**
    (`enter` ở camera trước): gương trái người lái = bên phải ảnh. Camera sau
    thì ngược lại.
  - Chiều đi lấy từ Phần A.
- **Quyết định theo cả lượt xe, không theo 1 frame:**
  - Chọn K = 5 frame tốt nhất: xe gần chính diện, rộng ≥ 250 px, không mờ.
  - `có gương trái`: thấy ở ≥ 2/5 frame.
  - `thiếu gương trái`: **cả 5/5 frame tốt** đều không thấy gương phía trái,
    **và** vùng đó không bị người hoặc tay che (dùng pose keypoint cổ tay/vai
    trái đã có trong `pose.py`).
  - Mọi trường hợp khác → `unknown`. **Không bao giờ cảnh báo từ `unknown`.**

### B4. Triển khai theo từng nấc

1. **Shadow:** chạy ngầm, chỉ ghi log, không hiện UI. Chạy khoảng 1 tuần.
2. **Review-only:** hiện ở trang vi phạm với nhãn "cần xác nhận", bảo vệ hoặc
   admin bấm đúng/sai.
3. **Bật cảnh báo loa** chỉ khi đạt trên ≥ 100 ca đã review:
   - Precision "thiếu gương" ≥ 95%.
   - Recall ≥ 70%: chấp nhận bỏ sót còn hơn báo nhầm.
4. Thứ tự ưu tiên loa (đã chốt trong kế hoạch cũ): dắt xe → mũ → gương.

### B5. Test

- Unit: logic trái/phải theo chiều đi; quyết định K frame; occluded → unknown;
  xe nhỏ → unknown.
- Đánh giá model: tách tập test **theo ngày quay** (không trộn frame cùng 1
  lượt xe vào cả train và test).

---

## Thứ tự làm và ước lượng

| Bước | Việc | Ước lượng |
|---|---|---|
| 1 | A0: quay clip + ghi đáp án | 1 buổi |
| 2 | A1 + A2: 2 chiều + sửa loa (sửa bug nghiêm trọng nhất) | 1 ngày |
| 3 | A3 + A5: người đi bộ + đếm đúng + bảng `gate_passages` | 1–2 ngày |
| 4 | A4: 2 vạch + chống tráo ID, replay trên clip A0 | 1–2 ngày |
| 5 | B1: chỉnh/lắp camera gương, kiểm tra kích thước xe ≥ 250 px | 0,5 ngày |
| 6 | B2: gán nhãn 300 ảnh + quay dữ liệu cổng | 2–4 ngày |
| 7 | B3: train YOLO11n `mirror` + logic quyết định | 1–2 ngày |
| 8 | B4: shadow → review-only → bật cảnh báo | 1–2 tuần theo dõi |

---

## Tiến độ (cập nhật 2026-10-06)

**Phần A — đã làm:**
- [x] A1: `CrossingDetector` ghi nhận CẢ 2 chiều vào `passages` (chiều ra
      không tạo vi phạm) — `app/cv/crossing.py`.
- [x] A2: xác nhận chiều ra không bao giờ cảnh báo (test).
- [x] A3: người đi bộ qua vạch bằng điểm chân, key `('ped', id)` riêng.
- [x] A4 (một phần): khôi phục lượt khi 2 người lướt qua nhau và tracker tráo
      ID đúng tại vạch ("2 lượt bật lại ngược phía cùng lúc cùng chỗ" →
      1 vào + 1 ra, status `review`). Cấu hình `CROSSING_BOUNCE_BAND`.
- [x] Lượt chốt ở CẢ 2 chiều đều latch: track vừa đi RA rồi quay đầu (hoặc bị
      tráo sang người đi vào) không còn sinh thêm lượt VÀO giả / vi phạm giả.
- [x] Bug #6: key dự phòng theo người đổi thành `('rider', id)`, không còn đụng ID xe.
- [x] A5: `PassageLedger` đếm theo người (người trên xe không bị đếm thêm
      như người đi bộ), bảng `gate_passages`, API
      `GET /api/stats/passages?date=YYYY-MM-DD&gate_id=`.
- [ ] A0: quay clip tại cổng + đáp án → replay đo độ chính xác thật.
- [ ] A4 phần còn lại (2 vạch, BoT-SORT): chỉ làm nếu A0 cho thấy còn sai.
- [ ] Hiển thị số vào/ra trên Dashboard.

**Phần B — đã làm:**
- [x] `app/cv/mirror.py`: trái/phải theo người lái từ chiều đi; quyết định
      theo K frame; `unknown` mặc định, không bao giờ cảnh báo từ `unknown`.
- [x] `scripts/prepare_mirror_dataset.py`: tạo task CVAT từ bộ 300 ảnh (90 ảnh
      xe < 60 px tự gắn `too_small`), chuyển nhãn CVAT → YOLO, chia train/val
      theo ảnh gốc.
- [x] `scripts/train_mirror.py`: YOLO11n 1 lớp `mirror`, imgsz 320.
- [ ] Gán nhãn gương trong CVAT (cần người làm).
- [ ] Quay dữ liệu tại cổng, train, đo precision.
- [ ] Nối `MirrorVote` vào pipeline ở chế độ shadow (sau khi có `models/mirror_best.pt`).
