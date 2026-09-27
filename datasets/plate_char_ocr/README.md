# Plate character-detection dataset

Nguồn: `yolo_plate_ocr_dataset.zip` (user cung cấp, 3188 ảnh + label YOLO).
Không kèm `data.yaml`/classes gốc — mapping dưới đây được giải mã bằng cách
crop file `0.jpg` (ảnh chứa đủ 36 class xếp lưới, dùng làm bảng tra) và xem
trực tiếp từng ô.

## Mapping class (đã xác nhận bằng mắt)

`0-9` = ký tự số `'0'`-`'9'`, `10-35` = chữ cái `'A'`-`'Z'` theo thứ tự
alphabet (bao gồm cả I/J/O/Q/W dù biển số VN thực tế hiếm/không dùng các chữ
này — dataset làm đầy đủ bảng chữ cho tổng quát, không riêng cho VN).

## Đặc điểm ảnh — quan trọng khi dùng để train

- Ảnh là **crop sẵn của riêng biển số** (không phải cả cảnh xe/người) — khớp
  đúng input mà bước đọc ký tự trong pipeline hiện tại nhận được (sau khi
  `plate_best.pt` detect và crop vùng biển số ra, xem `app/cv/pipeline.py`
  chỗ gọi `read_plate(crop)`).
- Ảnh trông giống ảnh chụp/rao vặt biển số (tên file kiểu `xxPlateBazaXXX`,
  `xxxemayXXX`) — **sạch, gần, rõ hơn** so với crop thật lấy từ camera an
  ninh (crop thật sẽ mờ hơn, nghiêng hơn, ánh sáng kém hơn). Khi train xong,
  **bắt buộc phải test lại bằng crop thật lấy từ `data/snapshots/` của hệ
  thống**, không thể tin thẳng độ chính xác trên tập val của dataset này.
- Phân bố class lệch nặng: chữ số (0-9) có hàng nghìn mẫu, một số chữ cái
  hiếm (ví dụ class 24='O', 26='Q', 32='W') chỉ có 2-4 mẫu — không đủ để
  model học tốt các chữ này, cần thêm ảnh hoặc augment riêng nếu biển số
  thực tế có dùng các chữ đó.

## Cấu trúc

```
datasets/plate_char_ocr/
  data.yaml           # Ultralytics format, path/train/val/names
  images/{train,val}/ # gitignored — không commit ảnh
  labels/{train,val}/ # gitignored — không commit label
```

Split 90/10 (2870 train / 318 val), chia theo file gốc, seed cố định (42) để
tái lập được.

## Cách train (khi sẵn sàng)

```bash
yolo detect train data=datasets/plate_char_ocr/data.yaml model=yolov8n.pt epochs=100 imgsz=320
```

`imgsz=320` là đủ vì input là crop biển số nhỏ, không cần ảnh lớn như
detect toàn cảnh.
