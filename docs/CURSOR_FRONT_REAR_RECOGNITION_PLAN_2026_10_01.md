# Prompt giao Cursor: camera trước nhận mũ/hành vi, camera sau đọc biển, cảnh báo nhanh

## 1. Yêu cầu và phạm vi

Tiếp tục School Gate Monitor theo working tree hiện tại. Đọc mã, `tasks/plan.md`, `tasks/todo.md`, execution log và báo cáo training trước khi sửa. Hoàn thành hoặc phối hợp với phiên Cursor đang sửa cùng phần mã; không chạy hai phiên chỉnh `pipeline.py` đồng thời. Không refactor toàn bộ dự án.

Máy đích: i7-12700H, RAM 16 GB, RTX 3050 Laptop 4 GB. Hai camera Imou nối LAN, quan sát **cùng một cổng vật lý**. Phân công:

| Nguồn | Nhiệm vụ mặc định | Tác vụ không chạy mặc định |
|---|---|---|
| Cam 1 — trước, chéo bên phải người lái | Người–xe, đầu có/không mũ, đang đi xe/dắt bộ, crossing; gương khi nhìn rõ và đã kiểm chứng | OCR biển toàn cảnh thường xuyên |
| Cam 2 — sau | Track xe, tìm biển, chọn crop nguồn nét nhất, đọc ký tự, ảnh bằng chứng phía sau | Pose và model mũ cho mọi người |

Cam 2 có thể hỗ trợ hướng di chuyển, sự hiện diện và số xe. Chưa tự phát lỗi mũ/hành vi từ góc sau nếu chưa nghiệm thu riêng. Không bật thêm các nhánh nhận diện chỉ để dùng hết GPU.

Mục tiêu trước mắt: hai hình mới chạy mượt, nhận diện thật có thẻ ảnh, đọc được biển rõ, xác định vì sao chưa có cảnh báo, và nghe được câu cảnh báo ngắn trên máy bảo vệ. Các mốc chất lượng và ca 12 giờ ở cuối phải được đo; không tuyên bố đạt trong ngày chỉ vì test xanh.

## 2. Hiện trạng đã đối chiếu ngày 01/10/2026

Đây là rà soát mã và báo cáo đã lưu; chưa chạy lại toàn bộ test hoặc nghiệm thu hai Imou trong lượt lập kế hoạch này. Cursor xác nhận lại các điểm sau với mã lúc bắt đầu.

| Điểm trong repository | Kết luận và việc cần làm |
|---|---|
| `app/cv/pipeline.py`: `_pipelines` khóa theo `gate_id`; `start_all_pipelines()` duyệt GATES | Bảng cameras đã có nhưng runtime chưa tạo riêng hai nguồn front/rear trong cùng gate. Không coi tạo thêm một gate là hoàn thành yêu cầu này. |
| `VideoPipeline.__init__()` nạp mũ, biển và COCO, tạo pool detect 3 worker | Chưa có hồ sơ tác vụ front/rear để giảm inference không cần thiết. |
| `_run_loop()` đọc `read_source_frame()` rồi chờ các Future detect/pose trước vòng đọc tiếp | OCR đã async và có JPEG cache, nhưng đọc hình/hiển thị chưa độc lập hoàn toàn với AI. Flags FFmpeg không thay thế được luồng đọc liên tục. |
| Nhánh `if not person_dets: ... continue` | Có thể thấy box biển nhưng không đi tiếp tới OCR. Cam sau phải xử lý xe/biển độc lập với điều kiện thấy người. |
| `recognition_models()` báo EasyOCR; `_observe_best_plate()` gọi `_ocr_task` | Bộ đọc ký tự vừa train chưa tích hợp vào runtime. |
| `best_plate.py` | Đã có chọn crop nguyên độ phân giải, chấm chất lượng và một lần OCR mỗi lượt. Giữ hợp đồng này, sửa nơi chọn/trigger còn thiếu; không quay lại OCR mọi frame. |
| `_observe_best_plate()` chỉ trigger gần đường crossing | Cam sau cần vùng đọc biển riêng; việc chưa cấu hình crossing không được làm thẻ OCR im lặng. Crossing vẫn bắt buộc cho kết luận chạy xe qua cổng. |
| `_process_vehicle_crossings()` | Luồng live hiện gom lỗi và chốt ở crossing. Cần nêu rõ đây là lý do cảnh báo chưa phát khi xe chỉ xuất hiện/đứng yên; không sửa bằng cách báo mọi người vào ROI. |
| `crossing.py` | Mã hiện dùng 3 quan sát phía đầu + 1 quan sát rõ phía đích, có latch/rearm. Ghi phiên bản quy tắc này; không âm thầm quay lại kế hoạch 3+3 cũ. Rà track quá hạn và quay đầu bằng test hành vi. |
| `alertAudio.js`, `alertFilter.js`, `useAudioLease.js` | Có gom một audio job/lượt, TTL, lọc bằng chứng và lease phát loa. Cần kiểm chứng trên browser thật để tìm tầng chặn tiếng. |
| `config.py`, `speak.js` | Default rate 1,30, giới hạn 1,40; volume TTS đã là 1,0. Chỉ tăng biến env sẽ không vượt clamp. |
| `crossing_alert.py` | Chưa đọc được biển có thể được gom thành lời nhắc ở sự kiện finalized theo yêu cầu mới nhất; phải phân biệt lỗi kỹ thuật/OCR đang chờ với kết quả kết thúc chưa đọc rõ. |
| Tìm kiếm feedback trong backend/frontend | Chưa thấy luồng xác nhận/sửa chuỗi biển có lưu provenance để tạo dataset. Cần thêm. |
| `scripts/verify_step3_2cameras.py` | Dùng hai video khác nhau như hai gate, chưa cô lập DB/media và chưa chứng minh hai góc cùng lượt. Không chạy script này với dữ liệu vận hành. Sửa cấu hình cách ly trước khi dùng. |

Thông tin model phải lấy từ trọng số/config thực, không từ tên file hoặc README. Runtime hiện có YOLOv8 cho detector, YOLOv8-pose, ByteTrack, EasyOCR; CUDA và FP16 đã có trong mã. YOLO11/BoT-SORT chưa được coi là đang dùng chỉ vì có file tham khảo.

Kiểm tra model mũ bằng `helmet_contract.py`: default `models/helmet_best.pt` từng chứa lớp plate; bản backup `models/backups/helmet_best_20260930_090903.pt` có mapping mũ phù hợp. Không ghi đè weights. Báo model/path/hash/device/classes **thực được nạp** và thử ảnh có/không mũ. Mapping đúng chưa chứng minh chất lượng.

## 3. Kiến trúc mục tiêu và định danh

```text
Cam 1 RTSP → capture giữ frame mới → hiển thị/JPEG riêng
                                  → AI trước → bằng chứng mũ/hành vi → crossing → event
Cam 2 RTSP → capture giữ frame mới → hiển thị/JPEG riêng
                                  → track xe → ROI biển → best crop → OCR → thẻ duyệt biển
Quan sát trước/sau → liên kết thận trọng khi đã hiệu chỉnh → cập nhật cùng event
Event + snapshot/crop đã lưu → WebSocket cùng cổng → 1 máy có lease → 1 beep + 1 câu
Phản hồi người dùng → dữ liệu đã duyệt → train offline → đánh giá độc lập → model có phiên bản
```

- `gate_id` là cổng vật lý; `camera_id` riêng, ổn định, có role `front/rear` và hồ sơ tác vụ. Admin xác nhận bằng preview, không đoán từ tên camera.
- Track khóa theo `(camera_id, run_id, source_epoch, vehicle_track_id)`. ID người chỉ hỗ trợ ghép/bằng chứng mũ, không thay khóa xe.
- Lượt nội bộ từng camera có `camera_encounter_id`. `encounter_id` chung chỉ xuất hiện sau liên kết đã kiểm chứng; không ghép vì cùng số track hoặc gần timestamp.
- Giữ ROI polygon, gate line hai điểm chuẩn hóa, vehicle bottom-center anchor; thêm vùng đọc biển rear độc lập. Cấu hình có version.
- Giữ POST đổi nguồn trả 202 và GET `checking/applied/error`; nguồn lỗi giữ camera cũ. Endpoint cũ phục vụ camera chính qua adapter; thêm camera selector mà không đổi nghĩa gate lịch sử.
- Migration bổ sung, idempotent; không viết lại dữ liệu vi phạm cũ. API/health chỉ đọc registry, không tự mở camera hoặc nạp model.

## 4. Thứ tự thực hiện

### P0 — Baseline và xác định vì sao chưa có tiếng

1. Ghi git status/commit, interpreter, dependency thực, hash/class/device từng model, nguồn được che credentials. Dùng `venv` của dự án; không cài/hạ dependency trên tiến trình đang chạy.
2. Test dùng SQLite backup/DB tạm, media tạm, video hoặc capture giả, port riêng; mặc định không tự mở RTSP thật.
3. Thêm hoặc hoàn thiện bảng chẩn đoán có thẻ ảnh và reason code ở đúng các tầng: capture → detector → ghép xe/người → head/mũ → posture → crossing → đủ mẫu → persist → publish → nhận WS → quyền loa → beep → TTS started/error.
4. Với một lượt không báo, hiển thị lý do cụ thể: model lỗi, ngoài ROI, thiếu track/xe, đầu khuất, posture unknown, chưa có line, chưa crossing, thiếu mẫu, event trùng, bằng chứng lỗi/chưa xong, lease không có, browser chặn, queue hết hạn. Không dùng nhãn “đang chạy” để che module lỗi.
5. Nút **Bật loa và nghe thử** phải khởi động/resume AudioContext bằng thao tác người dùng, lấy lease rồi phát beep và câu thử. UI báo trạng thái loa/giọng tiếng Việt/lease/lỗi playback. Không tạo vi phạm giả trong DB thật để thử loa. Quan sát `onstart/onend/onerror`; log gọi `speak()` không chứng minh đã nghe tiếng.

**Đạt P0:** nghe thử được trên máy được chọn; một sự kiện hợp lệ trong test end-to-end tạo đúng một beep/TTS; nhận diện chưa đủ điều kiện có lý do rõ và không phát vi phạm giả.

### P1 — Chạy đúng hai camera cùng cổng, có hồ sơ nhiệm vụ

1. Chuyển registry/vòng đời/switch sang camera_id, giữ adapter theo gate. Cấu hình API và UI chọn camera có role và preview.
2. Front nạp COCO track, mũ và pose có điều kiện. Rear nạp track xe, detector biển, reader ký tự khi được bật; không bắt thấy người trước khi đọc biển.
3. Hai camera có capture, tracker, epoch, best-crop store, pending job và metrics riêng. Restart/đổi nguồn một camera không reset camera còn lại.
4. Giao diện hiển thị hai preview cùng một bảng lượt xe; thẻ rear được hiển thị ngay dù chưa ghép vào lượt front. Không tự gán xe/học sinh từ một quan sát chưa ghép chắc.

**Đạt P1:** test hai camera cùng track ID/epoch không trộn crop/mũ/biển; nguồn hỏng giữ nguồn cũ; một camera offline không dừng nguồn còn lại; rear có xe/biển nhưng không thấy người vẫn có crop/OCR.

### P2 — Hình mới, chọn ảnh nét, dùng GPU có kiểm soát

1. Mỗi camera một luồng đọc/decode liên tục. AI chỉ nhận **một frame mới nhất**, không queue toàn bộ video. JPEG một lần/frame hiển thị, dùng chung 2–3 viewer. Chặn AI/OCR vẫn thấy frame_seq hình tăng.
2. Frame mang camera/run/epoch/seq, timestamp nguồn nếu có, thời gian nhận monotonic. Crop lấy từ ảnh nguồn chưa vẽ; detect/display thu nhỏ riêng, giữ tỷ lệ. Không vẽ overlay quá hạn 500 ms; hình quá hai giây không mới phải báo mất tín hiệu/hình cũ.
3. Điều phối GPU có giới hạn và công bằng. Bắt đầu benchmark với tối đa một lượt inference GPU đang thực thi; tăng concurrency chỉ nếu p95/FPS tốt hơn và không OOM. Model có một bên sở hữu thực thi; không gọi cùng instance đồng thời. Tracker state riêng từng camera. Không thêm một model/pool theo mỗi viewer hoặc mỗi reconnect.
4. Giữ CUDA/FP16 hiện có, xác minh tensor/device thực. Chỉ thử TensorRT/YOLO11 trong môi trường riêng sau baseline. CUDA inference không có nghĩa RTSP đang hardware decode.
5. Profile front: ưu tiên track/helmet, pose chỉ người ghép xe cần phân loại. Profile rear: track + plate trong ROI ở kích thước phù hợp; thử 5/10 FPS tìm biển khi xe vào vùng đọc. Tăng tần suất chọn ảnh khác với OCR nhiều lần. Đo tổng tải trước khi tăng.
6. Hàng đợi OCR toàn hệ thống tối đa 8, tối đa một tác vụ chạy/chờ mỗi khóa xe; đầy thì giữ crop tốt hơn/báo số job bỏ, không fallback OCR đồng bộ. Kết quả epoch/frame cũ bị loại.
7. RAM/VRAM có headroom theo peak đo được; không đặt mục tiêu GPU 100%. Không vừa training vừa demo trên VRAM 4 GB. Ghi CPU/RAM/VRAM, queue, frame bỏ, thời gian capture/detect/pose/OCR/encode và tuổi hình.

**Đạt P2:** OCR cố tình chậm không đứng hình; thêm viewer không tăng encode/model instances; queue hữu hạn; hai nguồn đạt mục tiêu sau đo, không suy FPS từ việc gửi lặp JPEG.

### P3 — Chỉnh chất lượng ảnh rear và cơ chế best crop

**Phải phân biệt:** FPS nguồn, FPS AI, tần suất chọn crop và **thời gian phơi sáng**. Tăng lưu snapshot hoặc tăng JPEG quality không sửa được chi tiết đã nhòe trong ảnh nguồn.

1. Ghi model/firmware Imou, main stream/substream, độ phân giải/FPS/bitrate/codec/keyframe, focus/exposure/gain/WDR/IR có thật. Không giả định camera hỗ trợ manual shutter hay OpenCV `cap.set()` thay được cấu hình RTSP.
2. Dùng main stream nguyên độ phân giải để chọn crop; display có thể nhỏ. Thu thử biển đứng yên và di chuyển tại vùng đọc, ban ngày và tối; lưu ảnh nguồn so sánh. Giữ TCP baseline, đo latency thực trước khi thay decode/backend.
3. Nếu model hỗ trợ, đề xuất operator thử exposure 1/250 và 1/500 giây trong điều kiện đủ sáng, so sánh độ nét/cháy sáng/nhiễu; đây là điểm bắt đầu thử, không là preset đã nghiệm thu cho Imou. Trời tối cần điều chỉnh ánh sáng/gain/IR phù hợp; không giảm exposure đến mức ảnh đen. Không tự sửa firmware/mật khẩu hoặc cấu hình thiết bị khi chưa được giao thao tác đó.
4. Góc rear hướng gần vuông mặt biển tại vùng đọc, tránh che bởi người/xe cạnh, lấy nét tại nơi xe đi qua. Đo số pixel biển và từng ký tự. Mốc thử crop rộng khoảng 120–200 pixel là mục tiêu bố trí cần kiểm chứng trên biển xe máy, không bảo đảm OCR đạt.
5. Chọn best crop theo đầy đủ bbox/kích thước, sharpness, exposure/contrast, perspective và detector confidence. Laplacian cao có thể là nhiễu nên không dùng riêng. So các crop cùng track ở nguyên độ phân giải, tránh điểm cao giả do sharpen/upscale.
6. Detector toàn cảnh → ROI xe native khi cần → tọa độ nguồn chính xác → best candidate. Kiểm thử biển hai dòng, một dòng, cắt mép, xe sát nhau. Không bắt box biển phải có tỷ lệ rộng/cao ≥1,5.
7. Giữ một lần plate recognition attempt/lượt, chọn crop trước trigger; tối đa một retry **lỗi kỹ thuật cùng crop**. Rear trigger tại vùng đọc khi chất lượng đạt hoặc lượt sắp rời vùng; không phụ thuộc front đã thấy người/crossing. Crop và kết quả đã freeze không được âm thầm thay sau khi người dùng duyệt.
8. Không dùng ảnh gen/super-resolution để đoán thêm nét ký tự rồi coi là bằng chứng. Nếu có rectification/upscale/CLAHE, luôn giữ ảnh nguồn song song và đánh giá trước/sau; không upscale 2–3× vô điều kiện với crop vốn đã lớn.

**Đạt P3:** người xem đọc được nhiều crop nguồn hơn sau cấu hình/chọn ảnh; báo tỷ lệ crop đọc được trên các lượt khác nhau, tách ngày/tối; nếu ảnh nguồn không đủ chi tiết, ghi đúng yêu cầu điều chỉnh góc/ánh sáng.

### P4 — Đưa bộ đọc ký tự đã train vào chế độ duyệt có kiểm soát

Trọng số có sẵn:

`runs/plate_ocr_20261001_183323/character_train_v2/weights/best.pt`

SHA256: `c30f244fca6699ac3ece5836426d704bb391ba05d259a1e3455cc6b5075ba4a6`.

Đây là YOLOv8n 36 lớp **ký tự trên crop**, không phải detector vị trí biển. Không thay `models/plate_best.pt` bằng file này. Đọc `docs/CODEX_PLATE_TRAINING_RESULT_2026_10_01.md` và `scripts/plate_char_tools.py` trước tích hợp.

Kết quả trước: raw full-string đúng 38/40 crop rõ được Codex rà bằng mắt, median crop video khoảng 21,8 ms so EasyOCR 107,5 ms. Có một chuỗi thiếu ký tự vẫn vượt kiểm tra confidence/format. Những số này chưa phải nghiệm thu cổng và cần người xác nhận nhãn.

1. Tạo adapter reader dùng decoder đã thử, feature flag và model contract 36 lớp. Bước đầu `review_only`, engine/version/device hiện đúng trên UI. Không chạy EasyOCR và model mới cho mọi crop trong production; so đối chứng offline trên cùng crop.
2. Giữ raw ký tự, confidence từng ký tự, cạnh tranh, thứ tự dòng và lý do từ chối. Chặn trường hợp thiếu chữ, chữ trùng bị mất, sai dòng, box cạnh tranh. Không dùng format để bịa chữ I từ số 1 hoặc điền ký tự chưa nhìn thấy.
3. Một crop có thể được xử lý hai dòng nhưng vẫn là một attempt. Kiểm tra số ký tự và spacing theo layout; chuỗi hợp lệ về format chưa có nghĩa đọc đúng.
4. Candidate hiện **đọc thử — cần xác nhận**. Trong giai đoạn thử, chỉ plate được người duyệt xác nhận mới lookup/gán xe. Tách `candidate`, `human_confirmed`, `auto_confirmed`, `unreadable`, `technical_error`; chưa đủ bằng chứng thì không tự kết luận biển không đăng ký.
5. Chỉ bật auto-confirm sau tập riêng tại cổng đạt tiêu chí false acceptance/coverage ở mục 9; lưu flag/weights/config rollback. Khi fail, tiếp tục thẻ duyệt thay vì hạ threshold.

**Đạt P4:** runtime rear thực dùng model ký tự dưới cờ thử; crop/video đúng engine; case mất ký tự không được tự gán học sinh; model sai mapping/lỗi không làm chết preview.

### P5 — Thẻ ảnh và phản hồi đúng/sai của người dùng

Thay danh sách text dài bằng thẻ theo lượt xe. Mỗi thẻ có ảnh ngữ cảnh/người (front), vùng đầu/mũ, xe, crop biển rear **chỉ khi ghép chắc**; chưa ghép hiển thị thẻ rear riêng. Ảnh phóng to phải lấy crop nguồn, ghi thời điểm; không hiển thị crop cũ như ảnh mới.

Thẻ biển hiển thị ví dụ:

```text
Ảnh biển gốc | Đọc thử: 89-F1 237.92 | model/version | ảnh lúc ...
[Đúng] [Sai — nhập lại biển] [Không đọc được] [Không phải biển/ghép nhầm xe]
```

Không hỏi người dùng đoán ký tự mờ. Nút “Đúng” chỉ xác nhận nguyên đề xuất đang xem. “Sai” cho sửa toàn chuỗi, giữ cả bản có dấu và canonical bỏ dấu phân cách; không tự đổi chữ/số. Cần người duyệt kiểm tra cả crop có thuộc đúng xe không.

**Hợp đồng bổ sung — thiết kế schema trước khi code:**

- `GET /api/recognition/reviews`: danh sách có phân trang, lọc gate/camera/status; limit 1–100, offset ≥0, tổng đúng.
- `GET /api/recognition/reviews/{review_id}`: candidate version và media IDs có quyền xem, lý do/engine, dữ liệu phản hồi hiện tại.
- `POST /api/recognition/reviews/{review_id}/feedback`: `expected_version`, `verdict` (`correct/incorrect/unreadable/not_plate/wrong_association`), `corrected_text` khi incorrect, ghi chú tùy chọn; `Idempotency-Key` ổn định qua retry.
- Payload cùng key khác nội dung bị từ chối; version cũ trả 409; cùng key/cùng payload trả cùng kết quả. Không cập nhật online model weights.

Schema lưu `review_id`, crop media ID/hash, camera/gate/run/epoch/frame, camera encounter, proposal raw/canonical, model hash/config version, quality và observation time. Feedback lưu riêng reviewer/time/version/verdict/corrected text; giữ lịch sử sửa thay vì ghi đè nhãn âm thầm.

Chỉ admin và bảo vệ có quyền được cấp mới duyệt; viewer khác chỉ xem theo phạm vi. Cookie/Origin, server validation và media permissions như hệ thống hiện có. Không gửi base64 ảnh lớn ở poll/WebSocket. Lưu crop một lần theo UUID; log realtime 500 dòng vẫn ở RAM, chỉ crop/feedback được chọn và retention được cấu hình mới lưu lâu dài.

**Đạt P5:** người dùng duyệt đúng/sai thực, reload còn feedback; hai người sửa cùng candidate phát hiện xung đột; double-click không ghi trùng; feedback không biến thành vi phạm mới hoặc tự sửa lịch sử gán học sinh.

### P6 — Mũ, dắt xe và gương theo góc camera thực

**Dắt xe nên ưu tiên cam nào?** Với mô tả camera trước chéo bên phải, ưu tiên cam 1 vì có cơ hội thấy hông, thân, quan hệ với yên/tay lái và người đi cạnh xe. Đây là lựa chọn thiết kế theo hình học, cần so clip hai góc; không có quy tắc “front luôn tốt hơn rear”. Nếu người/xe che mất hông và thân, cam sau hỗ trợ hoặc giữ unknown.

- Giữ `RIDING / WALKING_WITH_BIKE / UNKNOWN`. Không thấy chân không đồng nghĩa đã dắt xe; di chuyển cùng xe cũng chưa đủ kết luận riding.
- Riding dùng pelvis/torso/seat geometry, temporal person–bike association, overlap đúng vùng và chuyển động; chân chỉ hỗ trợ khi nhìn được. Feature unavailable không thành điểm 0 hay phiếu negative. Giữ các test SideViewRiding, bổ sung clip góc trước-phải thấp, chân khuất, người đứng cạnh/ngồi đứng yên/dắt bộ.
- Helmet: đầu có/không mũ nhìn rõ của đúng người; mũ cầm/treo, tóc/mũ vải, đầu khuất và gương xe là hard negatives. Bằng chứng mới riêng từng người–xe; không có box helmet chưa đủ để báo không mũ.
- Xác nhận nhiều frame cho mũ/hành vi vẫn dùng quy tắc hiện có đã kiểm chứng (4/5 mẫu mới trong 1,5 giây, span ≥400 ms, spacing ≥100 ms, unknown không bỏ phiếu); không giảm ngưỡng để tạo tiếng.
- Lỗi không dắt xe chỉ khi confirmed riding + crossing cấu hình đúng chiều. Crossing nhanh vẫn cần track ổn định, frame mới, latch/rearm; quan sát quá cũ hoặc track mất không được tự crossing.
- **Gương:** phải định nghĩa trái/phải theo người lái, không theo trái/phải màn hình. Cam trước-phải có thể không quan sát được gương trái. Chưa chốt phía kiểm tra thì cấu hình `visible_side`, ghi rõ gương khuất unknown, không hardcode câu “gương trái”.
- Chỉ có box “mirror” chưa đủ chứng minh cả hai gương hoặc thiếu gương. Dữ liệu cần box gương thấy được + vùng tay lái theo xe + trạng thái `present / clearly_absent / not_observable`, phía rider_left/rider_right/unknown. Không tạo box cho vật thể vắng mặt.
- Chưa có model/góc nhìn/tập đánh giá đạt thì gương **review-only**, hiện ảnh và nguyên nhân. Không bật TTS “thiếu gương” từ việc detector không thấy box.

**Đạt P6:** dắt bộ/đứng yên/unknown không bị báo riding; mũ treo không thành mũ đội; gương khuất không thành thiếu. Có báo cáo riêng các ca ở góc trước-phải.

### P7 — Cảnh báo ngắn, nhanh, đủ lỗi và không lặp

Giữ yêu cầu người dùng mới nhất: một vehicle crossing event → tối đa một beep và một câu TTS tổng hợp. Không chạy nhánh legacy và nhánh mới cùng phát. Không phát lại khi thêm crop/biển rear muộn, reconnect hoặc viewer mới.

1. Front đủ lỗi/crossing thì lưu snapshot/crop + DB rồi phát; không chờ rear OCR nhiều giây. Rear evidence bổ sung sau vào cùng event khi ghép chắc. Media pending/fail và technical OCR error có trạng thái riêng.
2. Phân biệt **vi phạm đã xác nhận** với **thông báo cần kiểm tra**. `PLATE_UNREADABLE` là thông báo hệ thống chưa đọc được, không là bằng chứng che/không có biển hoặc biển không đăng ký. Chỉ nhắc khi lượt đọc đã kết thúc; không nhắc do camera sau đang tải/OCR còn chờ deadline front. Lỗi kỹ thuật hiện health riêng, không báo thành lỗi người đi xe.
3. Giữ các câu người dùng đã yêu cầu, bỏ câu dẫn dài:
   - Biển đã xác nhận: “89 F1 237 92. Vui lòng dắt xe.”
   - Mũ + riding: “Không đội mũ, vui lòng dắt xe.”
   - Lượt đọc kết thúc chưa rõ: “Không đọc được biển số.”
   - Gương đã nghiệm thu: “Mời kiểm tra gương phải/trái.” đúng phía cấu hình.
4. Ưu tiên dắt xe → mũ → gương → kiểm tra đăng ký; bảng hiện tất cả issues. Thông báo biển chưa rõ không được lấn át lỗi mũ. Nếu yêu cầu một câu không đủ đọc mọi lỗi trong ngân sách thời gian, dùng câu tổng hợp ngắn và liệt kê đầy đủ trên bảng, không tạo chuỗi beep rời.
5. Tăng default thử **1,45**, cho chỉnh **1,0–1,6**, sửa clamp đồng bộ backend/JS/UI. Kiểm tra giọng vi-VN thực và lưu cấu hình; rate engine có thể khác nhau nên đo thời lượng nghe thật. Volume ứng dụng 1,0, không tự tăng master volume Windows.
6. Câu không đọc biển nhắm khoảng ≤3 giây; có biển/tổng hợp nhắm ≤4 giây, phải đo. Hàng đợi ≤2 câu chờ, TTL 5 giây; bỏ câu hết hạn có counter/UI, không drop âm thầm rồi báo hệ thống phát đầy đủ.
7. Lease vẫn chỉ một máy/cổng, heartbeat 5 giây, lease 15 giây. Nút bật loa phải mở audio trong gesture và nghe thử. Có trạng thái mất lease/browser blocked/no Vietnamese voice, thao tác retry; tắt/đổi gate/unmount dọn timer/queue/audio.
8. Chốt ranh giới front/rear để không báo `PLATE_UNREADABLE` giả vì plate chưa đến: tối đa 150–200 ms chờ reader đang gần xong như hiện tại; chưa đến thì ghi `rear_plate_pending` trên bảng. Nếu muốn nhắc biển chưa rõ riêng sau cửa sổ rear, cấu hình chính sách **một audio job của cả lượt** và báo tradeoff độ trễ; không tự phát câu thứ hai trái yêu cầu.

**Đạt P7:** cùng lượt nhiều lỗi vẫn một beep/câu; xe hợp lệ không beep vi phạm; thẻ nhận diện không nói; chỉ máy có lease phát; mũ/riding không bị chặn bởi rear pending; tốc độ cài đặt được áp dụng thật.

### P8 — Phản hồi thành dataset và chỉ train phần còn yếu

Người dùng tích đúng/sửa sai giúp tạo nhãn chuẩn; hệ thống **không tự thông minh lên ngay sau một click**. Training là đợt offline có phiên bản và phép đánh giá trước khi đổi model.

1. Xuất crop đã duyệt cùng context, raw/corrected string, source video/camera/encounter, chất lượng và model hash. Giữ hộp ký tự hiện có nếu hợp lệ; feedback full string chưa cung cấp bbox ký tự. Cần người rà/công cụ gợi ý căn chỉnh box trước khi fine-tune detector ký tự. Không ép chuỗi sửa vào những box đã thiếu ký tự.
2. Đo và phân loại lỗi: không tìm thấy biển → train **detector toàn cảnh/ROI**; crop sai/ghép nhầm → sửa geometry/association; crop rõ đọc sai → train **reader ký tự**; source mờ → chỉnh capture/camera/ánh sáng trước. ZIP hiện có chỉ đủ hỗ trợ reader ký tự.
3. Đề xuất đợt thu đầu: ≥100 crop biển được người duyệt từ ≥30 xe/biển khác nhau, gồm ngày/tối; ưu tiên chữ số lặp, ký tự gần nhau, biển hai dòng và các lỗi thực. Có thêm ảnh toàn cảnh với box biển để train detector. Đây là mốc bắt đầu kiểm kê, không là bảo đảm đủ training.
4. Thiếu gương: thu clip thật có/thiếu/khuất, nhiều dòng xe, vùng tay lái trái/phải nhìn rõ; cần tập nghiệm thu riêng ít nhất 30 lượt thiếu rõ + 30 có rõ trước bật loa. Thiếu mũ: gán box cùng vùng đầu cho cả hai nhãn; hành vi gán đoạn video, không gán bằng một pose tĩnh.
5. Gán class có version và manifest trạng thái riêng. Chia 70/15/15 theo video/phiên/encounter, giữ hai góc cùng lượt ở cùng tập; chống ảnh gần trùng, rà toàn bộ nhãn auto và rà lần hai ≥20% cùng toàn bộ mẫu khó.
6. Có thể dùng ảnh tổng hợp để minh họa hướng dẫn label hoặc bổ sung train sau khi model real-data baseline yếu. Ảnh tổng hợp phải đánh dấu nguồn, được người rà, không vào validation/test, không tạo số liệu nghiệm thu và không chỉnh ký tự trong ảnh chứng cứ. Nếu thử tỉ lệ tổng hợp 10–20% train, coi là thí nghiệm có đối chứng, giữ lại chỉ khi tập thật tốt hơn. Ưu tiên augmentation có kiểm soát trên ảnh thật; không coi ảnh gen sắc nét là thay thế dữ liệu Imou.
7. Train offline trong thư mục/version riêng, không vừa training vừa chạy demo hai camera. Không ghi đè weights đang chạy. Báo seed/hash/split/lệnh/VRAM, exact whole-plate accuracy, false acceptance, rejection và thời gian trước/sau. Rollback bằng config/version cũ.

**Đạt P8:** từ phản hồi xuất được bộ dữ liệu có provenance; nhãn đủ được người duyệt; giữ test chưa dùng chỉnh threshold; model mới chỉ promote khi tốt hơn baseline và đạt acceptance.

## 5. Ghép trước/sau và gán xe/học sinh

Tự ghép hai góc vẫn mặc định tắt cho tới khi hiệu chỉnh lane/ROI, hướng và thời gian di chuyển. Thu clip đồng bộ cùng lượt; video không đồng bộ không chứng minh ghép đúng.

Một ứng viên duy nhất phù hợp trong vùng/làn/hướng/thời gian đã đo có thể được thử liên kết. Nhiều xe gần nhau, track mất, sai thứ tự hoặc biển mâu thuẫn → chưa ghép, người kiểm tra. Không dùng giống một phần biển hoặc cùng track ID để gán. Rear plate confirmed không có nghĩa front rider đã được nhận dạng cá nhân; không thêm face recognition trong đợt này.

Chỉ enrich cùng event sau phép ghép đạt; tăng event_version, không tạo bản ghi vi phạm hoặc audio mới. Khi mất rear, front vẫn xử lý mũ/hành vi; khi mất front, rear vẫn đọc/thẻ biển, chỉ phát các thông báo của góc sau đã được duyệt chính sách.

## 6. Kiểm chứng theo từng lát cắt

Ưu tiên thin slices trong `tasks/todo.md`: chẩn đoán loa → runtime front/rear → capture độc lập → best crop rear → reader review-only → feedback → hành vi/gương → audio → dataset/benchmark. Sau mỗi slice chạy focused behavior test, sau mỗi checkpoint chạy suite/lint/build. Không đánh dấu đạt dựa trên tìm chuỗi trong mã.

Nhóm test bắt buộc:

- Model sai class/device; rear không có person nhưng có vehicle/plate; hai cam cùng track ID, đổi nguồn khi OCR đang chạy.
- Chặn detect/pose/OCR nhưng capture/display frame vẫn mới; queue đầy/slow viewer; restart lặp không nhân pool/model; overlay quá hạn.
- ROI tọa độ letterbox và native bbox; plate hai dòng, mép bị cắt, crop nhiễu, cháy sáng, xe sát nhau; best crop thay trước trigger và không đổi sau freeze; OCR attempts 1/1.
- Decoder mất ký tự lặp (`71H155118` → `71H15518`), thiếu chữ series, O/0, I/1, box cạnh tranh. Format hợp lệ sai chuỗi vẫn bị review; không lookup/gán sai.
- Mũ treo/cầm, đầu khuất, người đi bộ cạnh xe, ngồi đứng yên, dắt bộ, chân khuất nhưng pelvis/torso đủ; unknown + crossing không báo riding.
- Feedback đúng/sai/không đọc được/ghép sai; replay cùng key, khác payload, version conflict, phân quyền/media và persistence sau reload.
- Nhiều lỗi, rear pending/late, lưu DB/media lỗi, một audio job/lượt, reconnect không phát lịch sử; browser real phát beep/TTS onstart, speed/volume thực, tắt loa/lease hết hạn.
- Ghép hai góc: hai xe cạnh/đuôi nhau, ngược chiều, mất một nguồn, timestamp lệch, một phía không đọc biển. Kiểm tra cả từ chối đúng và liên kết thành công.

Lệnh dùng từ repository root:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
node --test frontend/test/*.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
```

Chạy Playwright theo cấu hình hiện có với API/video cách ly; test loa thủ công trên máy bảo vệ là kiểm chứng bổ sung. Model GPU nặng không nạp trong unit test HTTP; integration model thật riêng có timeout. Không bỏ test đang treo để gọi “full suite”.

## 7. Nguồn kỹ thuật

- Ảnh biển nhòe cần xem exposure, góc, ánh sáng và chi tiết pixel; không chỉ tần suất snapshot. Các giá trị thử cho Imou phải xác minh theo model thực: [Axis — License plate capture](https://whitepapers.axis.com/en-us/license-plate-capture).
- Một YOLO instance không được inference đồng thời từ nhiều thread; cân bằng ownership và RAM: [Ultralytics — Thread-safe inference](https://docs.ultralytics.com/guides/yolo-thread-safe-inference/). Tài liệu hiện tại dùng model mới hơn; đối chiếu API với Ultralytics 8.2.103 thực cài.
- Rate phụ thuộc engine/voice, cần nghe thử: [MDN — SpeechSynthesisUtterance.rate](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/rate). Web Audio có hạn chế autoplay/gesture: [MDN — Autoplay guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay).

## 8. Mốc demo cần hoàn thành trước

1. Hai camera đúng front/rear hiển thị cùng cổng, thẻ ảnh có track/camera/time và model thực.
2. Rear crop nét nhất + reader mới ở review-only; người dùng tích đúng/sửa sai lưu được.
3. Một lượt lỗi có bằng chứng thật kích hoạt đúng một beep và câu ngắn ở máy bật loa; nếu chưa phát có reason code, không yêu cầu user đoán.
4. Bảng mũ/hành vi nhiều frame tiến được; gương chưa đạt hiện review-only rõ ràng.
5. Báo số đo 30 phút; ghi phần còn cần góc camera/ánh sáng/nhãn, không viết “chuẩn doanh nghiệp” từ số unit test.

## 9. Tiêu chí cần đo và báo cáo

| Hạng mục | Mục tiêu/điều kiện |
|---|---|
| Hình mới | ≥15 FPS mỗi camera khi source cấp đủ FPS; không tính JPEG lặp |
| AI | ≥5 frame mới/giây mỗi camera với profile cần thiết |
| Trễ | p95 nhận frame → chuẩn bị hiển thị ≤500 ms; camera → màn hình đo đồng hồ riêng, mục tiêu ≤1,5 giây |
| Cảnh báo | Mũ p95 ≤2 giây từ quan sát hợp lệ; crossing ≤1 giây sau đủ điều kiện; bảng ≤500 ms sau xác nhận |
| Âm thanh | Onstart ≤1 giây khi queue rỗng, snapshot/crop/DB đã sẵn sàng; một beep/câu mỗi lượt; rate và thời lượng đo thực |
| OCR tối thiểu demo | Full-string đúng ≥50% trên ≥30 biển/xe khác nhau nhìn rõ tại cổng; báo riêng ngày/tối và tất cả lượt, không chỉ crop dễ |
| Promote reader tự động | Trên ≥100 lượt biển rõ độc lập được người duyệt: full-string accuracy mục tiêu ≥85%; sai trong các kết quả auto-accepted ≤2%; coverage auto-accepted ≥70%. Đây là mục tiêu mới cần đo, không kết quả 40 crop trước. Luôn báo cả số mẫu; tự gán nhầm học sinh là lỗi chặn promote. |
| Mũ/riding đọc loa | Precision ≥95% từng loại, recall ≥70% trường hợp rõ; ≥50 lượt vi phạm + ≥50 không vi phạm độc lập |
| Gương | ≥30 thiếu rõ + ≥30 có rõ, góc nhìn đúng phía; không đủ thì review-only |
| Ghép hai góc | ≥50 cặp được gán nhãn, thêm ≥20 tình huống khó; không ghép sai trong tập nghiệm thu; báo coverage/từ chối, không coi không ghép gì là đạt |
| Trống | 10 phút cảnh trống: 0 vi phạm |
| Tải/ổn định | 30 phút hai video cách ly, 1/2/3 viewer; sau đó ca 12 giờ hai Imou, không hang/OOM/queue tăng dài hạn |

Giữ toàn bộ yêu cầu bảo mật/phân quyền/media/backup theo kế hoạch ổn định hệ thống trước. Ghi `docs/CURSOR_EXECUTION_LOG.md` và acceptance report: lỗi tái hiện, thay đổi, lệnh/kết quả, trước/sau, rollback, thiếu dữ liệu. Tách **đã viết mã / test hành vi / đã đo video / đã nghiệm thu camera thật**.

## 10. Thông tin còn cần từ thiết bị/người dùng

- Model/firmware và preview thực của hai Imou; source cam 2 và thông số exposure có hỗ trợ hay không. Credentials giữ local secret, không ghi vào tài liệu/log/API.
- Phía gương cần kiểm tra: cam trước-phải không bảo đảm thấy gương trái. Khi chưa chốt, chỉ đánh giá phía quan sát được, phía khuất unknown.
- Clip đồng bộ front/rear, nhãn riding/pushing và crop biển thật người dùng duyệt; nhãn gương thiếu/có rõ. Thiếu phần nào ghi rõ, tiếp tục các phần độc lập.

Không đổi nguồn vận hành để benchmark, sửa/xóa DB/media thật, nâng dependency live, ghi đè thay đổi chưa commit, push/deploy hoặc tự đổi cấu hình/mật khẩu thiết bị. Triển khai liên tục các phần độc lập; không dừng sau mỗi task để hỏi lại. Chỉ yêu cầu người dùng khi cần thao tác/thiết bị/nhãn không có trong repository.
