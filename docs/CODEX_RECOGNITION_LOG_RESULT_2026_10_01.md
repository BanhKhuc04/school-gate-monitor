# Khôi phục đường nhận diện và log trực tiếp — 2026-10-01

## Phạm vi và hiện trạng

Triển khai theo yêu cầu người dùng: sửa model mũ, track ID/ghép đối tượng, OCR async và thêm log nhận diện trong bộ nhớ. Đây không phải nghiệm thu độ chính xác hay hoàn tất kế hoạch hai camera.

Working tree có nhiều thay đổi từ các lượt trước; không reset, commit, push, nâng dependency hoặc ghi đè trọng số. Snapshot trước sửa tại `C:\Users\khucv\AppData\Local\Temp\recognition_log_backup_ol8kxl8q`; chỉ dùng snapshot để đối chiếu, không khôi phục hàng loạt khi có chỉnh sửa mới.

Phiên backend thử dùng SQLite/media riêng trong `C:\Users\khucv\AppData\Local\Temp\school_gate_camera_check_8yhc0fa9`. Không thay DB/media/cấu hình vận hành. Camera .9 đã kết nối ở lượt trước; trong lượt này người dùng chuyển nguồn sang OBS Virtual Camera index 1. Đã giữ lựa chọn đó qua restart.

## Lỗi tái hiện và sửa

1. `helmet_best.pt` có mapping `{0: plate}`. Tắt riêng nhánh mũ nếu mapping không đúng, đưa lý do vào API/log; người/biển/camera tiếp tục hoạt động. `HELMET_MODEL_PATH` cho phép cấu hình model riêng. Không ghi đè file hiện có.
2. `_rescale_dets` bỏ `track_id`; hàm `_group_by_person` bị định nghĩa hai lần và bản chạy không trả ID. Hợp nhất thành một hàm, giữ ID người/xe qua resize và ROI. Giữ ID người làm khóa bằng chứng hiện tại.
3. Ghép mũ vào vùng đầu; mũ cầm thấp không được coi là đang đội. Ghép biển với xe; nhiều ứng viên gần nhau chuyển chưa chắc chắn, không tự gán.
4. Track có OCR chưa xong vẫn submit thêm và thay Future. Thêm `return` khi pending; giới hạn tám yêu cầu mỗi pipeline, một worker. Không fallback OCR đồng bộ khi thiếu track.
5. OCR lấy ảnh nguồn trước khi vẽ box/pose. Kết quả thu đúng một lần, kiểm tra phiên/frame/track/tuổi mẫu; frame lặp không cộng phiếu. Hai mẫu đủ confidence giống toàn biển mới được xác nhận; kết quả cạnh tranh đáng tin cậy ngăn xác nhận.
6. Kết quả OCR trả sau khi detector mất box biển vẫn được thu và hiện lên log theo frame crop gốc; không phải chờ box xuất hiện lại. Lỗi engine giữ trường `error`, không trở thành bằng chứng che/không có biển.
7. Quan sát mũ/OCR chạy độc lập với nhánh tạo vi phạm. Chưa ghép xe, thiếu track, ngoài ROI, tư thế chưa rõ, đường cắt chưa cấu hình, thiếu mẫu, cooldown và lỗi lưu bằng chứng đều có lý do hiển thị.

Giữ nguyên xác nhận nhiều frame và lưu bằng chứng trước âm thanh. Không tự tạo đường cắt; gương/fusion hai camera không được bật thêm.

## Model mũ dùng trong phiên thử

| File | Mapping | SHA-256 |
|---|---|---|
| `models/helmet_best.pt` | `{0: plate}` — không hợp lệ cho mũ | `ef083bb37f490afa2120a26b590edcea7d2174322a3d187a1c3084d1d46c9d3f` |
| `models/backups/helmet_best_20260930_090903.pt` | `With Helmet`, `Without Helmet` | `c8eb324e365cf4faeab491d9cc301535ec745171b55e8b1acadea62be5101a9d` |

Đã đối chiếu inference của backup trên ảnh mẫu có mũ/đầu trần trước khi chọn trong launcher thử. Mapping đúng và vài ảnh đúng không chứng minh precision/recall. API runtime xác nhận model sẵn sàng; trang trực tiếp đã hiện box mũ và trạng thái “Có mũ”.

Khi khởi động bằng launcher khác, đặt biến môi trường trước khi import app:

```powershell
$env:HELMET_MODEL_PATH = 'D:\Work\Project_motorbike\models\backups\helmet_best_20260930_090903.pt'
```

Launcher thử hiện tại đã đặt biến này. Cấu hình `.env` vận hành chưa được thay; nếu không đặt biến trên và file mặc định vẫn sai lớp, nhánh mũ sẽ báo chưa khả dụng.

## API và giao diện

`GET /guard/recognition_log?gate=main&after_seq=0&limit=100` dùng phiên/Bearer hiện có, chỉ admin/security/management. `limit` 1–100, cursor không âm, gate phải tồn tại. Endpoint chỉ đọc registry/snapshot, không mở camera/model/DB/media.

Mỗi pipeline có buffer 500 dòng và cache chống lặp hữu hạn. Dòng chứa seq, UTC timestamp, gate/camera, source epoch, frame sequence, track, stage, status, reason code và kết quả quan sát. Không lưu ảnh/credential hay thêm bảng DB. Hai viewer đọc không lấy mất dòng nhau. Đổi nguồn xóa buffer/cache; tác vụ IO cũ không thêm dòng vào phiên mới.

Trang `/guard`: tab **Nhận diện trực tiếp** mở mặc định, bên cạnh tab **Cảnh báo**. Poll một giây sau mỗi request, chống trùng, hủy request/timer khi đổi gate hoặc rời trang. Có lọc ID người/xe, giai đoạn, tạm dừng cuộn và xóa cục bộ. Lỗi tải có retry, giữ dữ liệu cũ. Log không gọi beep/TTS. Chữ trên nền sáng đã được kiểm tra và sửa tương phản.

![Giao diện nhận diện](recognition-log-preview.jpg)

## Kiểm chứng

Các regression ban đầu được chạy trước sửa và thất bại tại track/Future/contract/log còn thiếu. Đã thêm test hành vi, gồm vòng lặp thật với nguồn/detector/OCR điều khiển được, thay vì chỉ tìm chuỗi trong source.

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ `app/tests` bằng venv, không ignore/deselect | **519 passed, 1 warning**, 171.20 giây |
| Node âm thanh/filter | **17 passed** |
| Chromium camera + bảng/âm thanh + log mới | **12 passed**, 42.0 giây |
| Frontend build | exit 0; còn cảnh báo chunk lớn hiện có |
| Frontend lint | exit 0; còn warning ở các phần hiện có, log mới không có warning |
| Kiểm tra liên quan sau chỉnh thông báo lý do | **42 passed**, 15.36 giây |
| Runtime/API + browser đang mở | Pipeline/camera chạy; model mũ ready; log hiện trạng thái và lý do |

Test mới bảo vệ: giữ track xuyên resize/ROI/grouping; mũ cầm tay và biển cạnh hai xe; model sai lớp chỉ tắt mũ; Future không bị thay; frame trùng/OCR mâu thuẫn/track-frame sai/mẫu quá hạn bị loại; lỗi engine; OCR hoàn tất khi box mất; raw crop không dính overlay; nguồn trống vẫn cập nhật JPEG và không tạo vi phạm; log bounded/throttle/reset/2 viewer; vai trò và endpoint chỉ đọc; UI filter/pause/clear/error/unmount/silent.

Sửa test cũ đang khẳng định Future bị thay là đúng. Test nguồn trống trước đây chỉ gọi `_draw_roi`; đã đổi một ca sang `_run_loop` thật, kể cả nhánh model mũ bị tắt. Các patch DB connection trong file này dùng monkeypatch hoàn trả, tránh nhiễm test khác. Không bỏ các test guard/stream khỏi bộ chung.

Lệnh tái chạy:

```powershell
.\venv\Scripts\python.exe -B -m pytest app/tests -p no:cacheprovider --tb=short -q
node --test frontend/test/alertAudio.test.mjs frontend/test/speak.e2_3.test.mjs
cd frontend
npm run lint
npm run build
npx playwright test e2e/test_camera.spec.js e2e/test_pre_e3.spec.js e2e/test_recognition.spec.js --project=chromium
```

Chromium sử dụng API/media/WS giả trên Vite test port 5186, không thay nguồn hoặc ghi DB vận hành. API runtime kiểm tra riêng với phiên thử cổng 8001; frontend đang mở cổng 5174.

## Phép đo và phần chưa nghiệm thu

`scripts/benchmark_recognition_log.py` dùng cùng frame video local, model thật/pose/OCR/JPEG, DB/media tạm; ép CPU để tách khỏi GPU của viewer đang chạy. Bỏ khởi tạo OCR/model khỏi timing; đo cả bật/tắt và thời gian trực tiếp ở hàm diagnostic. Kết quả JSON trong `docs/benchmarks/RECOGNITION_LOG_OVERHEAD*_2026_10_01.json`; giữ cả các phép đo ban đầu để đối chiếu.

**Chưa nghiệm thu**: precision/recall mũ/biển, OCR ≥50% trên 30 biển rõ, camera trống 10 phút, độ mượt hai camera với viewer, ngân sách tăng chi phí ≤5% trên máy vận hành và ca 12 giờ. Video thử chưa được gán nhãn nên không tính accuracy. Việc detector COCO bỏ lỡ xe ở video đang xem vẫn làm OCR chưa được gắn vào track đó; log hiện lý do, không tự suy xe từ box biển và không tự gán học sinh.

Trong phép kiểm tra CPU 40 frame trước khi tái dùng model, chi phí diagnostic trực tiếp khoảng 4.9 ms cho cả lượt (0.038–0.044%), nhưng chênh lệch median toàn pipeline là +8.52%; không được đánh dấu đạt ≤5% từ số trực tiếp. Phép đo tái dùng model có median tắt 10.876s, bật 11.798s (+8.48%). Các cặp bật/tắt lần lượt -1.26%, +0.13%, +13.06%, median theo cặp +0.13%; diagnostic trực tiếp 0.040–0.046%. Do độ dao động giữa các lượt lớn và chưa có viewer trong phép đo, **tiêu chí tổng ≤5% vẫn chưa được nghiệm thu**. Giữ nguyên số đo, không chọn riêng một cặp để đánh dấu đạt. FPS CPU của phép thử không phải FPS hiển thị hoặc FPS GPU hai Imou.

Đường cắt của phiên camera hiện chưa cấu hình. Không có cảnh báo “không dắt xe” chỉ vì xe xuất hiện trong ROI. Các nhánh khác tiếp tục yêu cầu đủ bằng chứng.

## Quay lại cấu hình trước

Tắt riêng log bằng `RECOGNITION_LOG_ENABLED=0` trước khi khởi động backend. Không hạ ngưỡng bằng chứng hoặc quay lại lỗi Future/track để tăng FPS. Đổi đường dẫn model qua môi trường, kiểm tra mapping và khởi động lại tiến trình thử. Không copy snapshot mã đè working tree đã thay đổi thêm; chỉ hoàn tác từng hunk đã đối chiếu khi cần.

Dừng phiên thử bằng đúng PID launcher trong thư mục phiên và tiến trình Python con của nó. Không dừng toàn bộ Python/Vite hoặc đổi nguồn camera vật lý. Model/DB/media vận hành và thay đổi trước đó được giữ nguyên.
