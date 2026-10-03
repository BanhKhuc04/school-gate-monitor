# Kiểm thử video Imou và huấn luyện bộ đọc biển số — 01/10/2026

## Kết luận

Đã huấn luyện xong một YOLOv8n chuyên nhận 36 ký tự trên ảnh crop biển, 35 epoch trên RTX 3050 Laptop. Bộ đọc mới cải thiện rõ so với EasyOCR hiện tại trong các phép thử dưới đây. Trọng số mới giữ ở bản thử nghiệm: một trường hợp thiếu ký tự vẫn được nhận với confidence cao. Chưa dùng để tự gán xe/học sinh và chưa thay model vận hành.

Biển nhìn rõ trong video: **89-F1 237.92**, chuẩn hóa `89F123792`.

## Đầu vào và cách kiểm chứng

- Video: `C:/Users/khucv/Videos/2026-10-01 18-33-23.mp4`, 1280×720, 30 FPS, 4.679 frame, 155,97 giây.
- SHA256 video: `a6a90541b3dd2ce27d121209bf3df92d90524f77e5a6026c1d41e99c94273548`.
- Dataset: `C:/Users/khucv/Downloads/yolo_plate_ocr_dataset.zip`, 3.188 ảnh và 3.188 nhãn YOLO. Nhãn là box **ký tự**, không cung cấp box biển trong toàn cảnh. Mapping được kiểm tra trên ảnh bảng chữ: 0–9 là số; 10–35 là A–Z.
- Loại ảnh bảng chữ `0.jpg`. Giữ 3.187 ảnh có nhãn hợp lệ về cú pháp, class, tọa độ và khả năng decode. Kiểm tra đường dẫn ZIP, kích thước giải nén và trùng tên trên Windows trước khi tạo bộ dữ liệu riêng.
- Chia theo nhóm tên ảnh gốc, pixel trùng và chuỗi biển đủ định dạng: **2.249 train / 483 validation / 455 test**. Tổng 2.255 nhóm. Không dùng frame video này để huấn luyện trọng số.
- ZIP không có video/session ID nên chưa thể chứng minh đã loại mọi ảnh gần trùng. Chưa rà toàn bộ nhãn bằng mắt.
- Chọn trước 48 ảnh biển Việt Nam trong test để rà bằng mắt qua ảnh nguồn; 40 rõ, 8 mơ hồ không đưa vào tính điểm. Đính chính 3 chuỗi nhãn thiếu/sai ký tự trong tập tham chiếu riêng. Đây là rà soát bằng thị giác của Codex, cần người xác nhận lại trước nghiệm thu thực tế.
- Video chỉ có một biển lặp lại. Video cũng được dùng để tái hiện lỗi decoder, nên không phải tập nghiệm thu độc lập của toàn pipeline.

## Huấn luyện

| Thuộc tính | Giá trị |
|---|---|
| Model | YOLOv8n, head 36 lớp ký tự |
| Khởi tạo | `yolov8n.pt` local, không đổi dependency |
| Epoch | 35 |
| Input | 320, giữ tỷ lệ bằng letterbox |
| Batch | 32 |
| Optimizer | AdamW, lr0=0,001 |
| Workers / cache | 0 / false, hạn chế RAM trên Windows |
| Seed | 20261001 |
| Augmentation | Không lật, mosaic=0; xoay/nghiêng/phối cảnh nhẹ |
| Phần cứng | RTX 3050 Laptop 4 GB, CUDA |
| Phiên bản thực cài | Ultralytics 8.2.103, Torch 2.6.0+cu124, OpenCV 4.10.0, NumPy 2.4.6 |

Lần đầu dừng ở validation vì Ultralytics 8.2.103 gọi `np.trapz`, đã bị NumPy 2.4 bỏ. Script huấn luyện/đánh giá dùng alias tương đương `np.trapezoid` trong tiến trình thử nghiệm. Có test thực gọi `ultralytics.utils.metrics.compute_ap`. Không sửa site-packages hoặc dependency của backend.

NumPy thực cài 2.4.6 đang ngoài khoảng `<2.0` của requirements; cần xử lý môi trường riêng trong một đợt kiểm chứng dependency, không nâng/hạ môi trường đang chạy trong lượt này.

Tham khảo: [NumPy 2.4 release notes](https://numpy.org/doc/stable/release/2.4.0-notes.html), [numpy.trapezoid](https://numpy.org/doc/stable/reference/generated/numpy.trapezoid.html), [Ultralytics training](https://docs.ultralytics.com/modes/train/).

Một số lớp rất ít mẫu sau loại bảng chữ: O=3, Q=1, W=3. Các lớp này chưa đủ dữ liệu để nghiệm thu.

## Kết quả

### So sánh trên cùng crop

| Tập | EasyOCR hiện tại đọc đúng toàn chuỗi | Bộ đọc ký tự mới đọc đúng toàn chuỗi |
|---|---:|---:|
| 11 crop nguồn từ đầu video, cùng một xe | 0/11 | **10/11** |
| 40 ảnh test đã rà bằng mắt | 8/40 (20%) | **38/40 (95%)** |
| 455 ảnh test, so với chuỗi dựng từ nhãn gốc | 55/455 (12,1%) | **414/455 (91,0%)** |

Hai hàng đầu dùng tham chiếu đọc từ ảnh nguồn. Hàng 455 ảnh có nhãn chưa được rà toàn bộ, không được dùng để tuyên bố độ chính xác thực tế 91% tại cổng trường. Kết quả 95% trên 40 ảnh cũng không phải precision cảnh báo hoặc chất lượng của hai camera.

Ngưỡng xác nhận thử nghiệm: confidence thấp nhất của các ký tự ≥0,70, đủ định dạng được hỗ trợ và không có cạnh tranh đáng tin cậy. Ký tự do YOLO đọc giữ nguyên, không biến chữ số thành một chữ cái chưa được quan sát.

- 11 crop video: **7 xác nhận đúng**, 4 chưa xác nhận; không có biển sai được xác nhận trong nhóm này. EasyOCR cũ có 3 kết quả sai vượt ngưỡng.
- 40 ảnh rõ: bộ đọc mới xác nhận 37, đúng 36, **sai 1** (`4xemay2369.jpg`: đọc thiếu một ký tự). EasyOCR xác nhận 13, đúng 7, sai 6.
- Một trường hợp YOLO thiếu chữ series được chặn bằng kiểm tra chuỗi nguyên dạng; không suy ra chữ I từ chữ số 1.
- Median trên crop video: EasyOCR khoảng **107,5 ms**, bộ đọc ký tự khoảng **21,8 ms**. Thời gian còn phụ thuộc viewer/backend và tác vụ cùng máy. Đây là thời gian OCR riêng, không phải FPS hay camera→màn hình.

Metric box ký tự trên 455 ảnh test: precision 96,22%, recall 96,97%, mAP50 97,47%, mAP50–95 73,66%. Các metric này đo **box ký tự**, không đo toàn biển, ghép đúng xe hoặc cảnh báo.

### Tìm biển trong video

Lấy mẫu 5 FPS xuyên suốt video: 780 frame. Detector biển toàn cảnh hiện tại trả box trên 55 frame; thử thêm cơ chế hiện có tìm trong vùng xe/người khi toàn cảnh không thấy biển trả box trên 75 frame, phục hồi 20 lượt quan sát. Đây là số frame có box, **không phải recall**, vì chưa gán nhãn tất cả frame có biển.

Tăng input toàn cảnh lên 960 không cải thiện ổn định: lấy mẫu 1 FPS chỉ thu được 8 box, so với 11 box tại các mốc 1 giây của phép thử 640. Vì vậy chưa tăng input toàn hệ thống.

Đoạn xa, quay mặt trước, biển quá nghiêng hoặc chuyển động nhòe vẫn khó nhận. Bộ đọc mới cải thiện bước đọc ký tự; cần thêm nhãn box biển toàn cảnh buổi tối để huấn luyện detector tìm biển và kiểm chứng ghép với đúng xe.

## Decoder và kiểm thử

- Sắp ký tự theo dòng và vị trí; xử lý một dòng nghiêng và hai dòng.
- Khi box cùng vị trí có nhãn phụ yếu hơn ít nhất 0,20 confidence, bỏ nhãn phụ. Khi hai nhãn gần nhau về confidence, từ chối đọc chắc chắn.
- Chuỗi xác nhận phải khớp định dạng nguyên dạng; không tự sửa ký tự thiếu thành chữ/số khác.
- 15 test mới bảo vệ split nhóm, nhãn lỗi, đường dẫn ZIP, trùng tên Windows, ký tự cạnh tranh, thứ tự dòng, alias NumPy và không tạo chữ series chưa quan sát.
- Kết quả backend cuối: **621 passed, 1 warning, 239,60 giây; không skip**. Xem `runs/plate_ocr_20261001_183323/backend_acceptance_tests.log`. Frontend không thay đổi trong lượt huấn luyện này.

## Tệp bàn giao

- Trọng số: `runs/plate_ocr_20261001_183323/character_train_v2/weights/best.pt`.
- SHA256: `c30f244fca6699ac3ece5836426d704bb391ba05d259a1e3455cc6b5075ba4a6`.
- Model card: `runs/plate_ocr_20261001_183323/model_card.json`.
- Dataset audit/split: `runs/plate_ocr_20261001_183323/character_dataset/audit.json`.
- Tham chiếu 40 ảnh rõ/8 ảnh chưa rõ: `runs/plate_ocr_20261001_183323/manual_reference.json`.
- Kết quả so sánh cuối: `runs/plate_ocr_20261001_183323/comparison/comparison_final.json` và `manual_comparison_final.json`.
- Ảnh so sánh: `runs/plate_ocr_20261001_183323/ocr_comparison.jpg`.
- Video minh họa: `runs/plate_ocr_20261001_183323/candidate_video/preview_h264.mp4` — 5 FPS lấy mẫu, không âm thanh; không dùng video xuất này để đo độ mượt vận hành.
- Video/JSON baseline và lần thử 960 nằm trong `baseline/`, `baseline_960/` cùng thư mục thử nghiệm.

Trọng số mới nhận đầu vào **crop biển**. Không chép trọng số 36 ký tự này vào `models/plate_best.pt`: file đó dùng cho bước tìm box biển trong toàn cảnh. Backend hiện tại tiếp tục dùng EasyOCR; trong lượt này chỉ thay đổi công cụ huấn luyện/đánh giá, test và báo cáo.

Model biển vận hành giữ nguyên SHA256 `5b57ca666211a4b7dffd6fed662dcfda3c0504eed2534338660372ce80290817`.

## Chạy lại

Từ `D:/Work/Project_motorbike`, dùng interpreter venv. Chọn thư mục output mới cho mỗi lần chạy để giữ lịch sử:

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_plate_char_dataset --zip C:\Users\khucv\Downloads\yolo_plate_ocr_dataset.zip --output runs/plate_next/character_dataset
.\venv\Scripts\python.exe -m scripts.train_plate_char --data runs/plate_next/character_dataset/data.yaml --output runs/plate_next/character_train --epochs 35 --batch 32 --imgsz 320 --device 0
.\venv\Scripts\python.exe -m scripts.evaluate_plate_video --video 'C:\Users\khucv\Videos\2026-10-01 18-33-23.mp4' --output runs/plate_next/baseline --device 0
.\venv\Scripts\python.exe -m scripts.evaluate_plate_char --model runs/plate_next/character_train/weights/best.pt --dataset runs/plate_next/character_dataset --video-baseline runs/plate_next/baseline/results.json --output runs/plate_next/comparison --device 0
.\venv\Scripts\python.exe -m scripts.evaluate_plate_video --video 'C:\Users\khucv\Videos\2026-10-01 18-33-23.mp4' --output runs/plate_next/video --device 0 --character-model runs/plate_next/character_train/weights/best.pt --region-scan
.\venv\Scripts\python.exe -m pytest app/tests -q -p no:cacheprovider --tb=short
```

## Công việc cần trước khi đưa vào vận hành

1. Rà và sửa box/nhãn ký tự bị thiếu, nhất là chữ/số sát nhau; xác nhận lại tập 40 ảnh bởi người kiểm tra. Không đưa các frame đã dùng debug vào tập nghiệm thu độc lập.
2. Bổ sung nhiều xe, nhiều biển và video ở đúng hai góc camera trường, gồm ban đêm/chuyển động. Gán nhãn toàn cảnh cho detector biển; hiện ZIP chỉ phục vụ đọc ký tự.
3. Tích hợp reader vào worker OCR hiện có theo cấu hình lựa chọn engine, kiểm tra mapping 36 lớp, giữ source/epoch/frame và một crop/lượt. Khi ghép ký tự chưa chắc chắn phải giữ `needs_review`, không tự gán học sinh.
4. Kiểm chứng false acceptance trên tập validation độc lập, rồi chạy thử trong chế độ xem xét trước khi thay engine sử dụng. Chưa bật theo kết quả 40 ảnh hoặc một xe lặp lại.
5. Đo lại hai nguồn sau khi không còn tác vụ train/eval: capture/AI/display FPS, p95 latency, RAM/VRAM và 12 giờ vận hành. Không suy các chỉ tiêu này từ tốc độ model.

## Mở kết quả

- [Video nhận diện thử](D:/Work/Project_motorbike/runs/plate_ocr_20261001_183323/candidate_video/preview_h264.mp4)
- [Ảnh so sánh OCR](D:/Work/Project_motorbike/runs/plate_ocr_20261001_183323/ocr_comparison.jpg)
- [Trọng số thử nghiệm](D:/Work/Project_motorbike/runs/plate_ocr_20261001_183323/character_train_v2/weights/best.pt)
- [Model card](D:/Work/Project_motorbike/runs/plate_ocr_20261001_183323/model_card.json)
