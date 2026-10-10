# Đối chiếu báo cáo FR0–FR10 và việc cần làm tiếp — 01/10/2026

## Kết luận

**Regression xanh đã được chạy lại, nhưng chưa xác nhận FR0–FR10 hoàn tất.** Runtime hai camera cùng cổng, capture độc lập AI, gọi reader ký tự và thẻ feedback xuyên luồng vẫn còn thiếu trong mã hiện tại. Những thiếu hụt này không đòi hỏi camera thật mới có thể kiểm thử.

Hai lỗi assertion được nêu ở cuối báo cáo người dùng đã sửa trong working tree: test lazy reader kiểm tra `_model/is_loaded`, test audio dùng 1,45. Không sửa lại theo đề xuất cũ. Tuy nhiên một test reader khác vẫn làm mất module Ultralytics đã được import trước đó.

Lượt này là rà soát, chạy kiểm chứng và ghi tài liệu; **không sửa mã vận hành, model, DB/media hoặc nguồn camera thật**. Không đo FPS/p95/precision/ca 12 giờ; chưa chạy E2E browser thật cho feedback mới.

## Kiểm chứng đã chạy

| Kiểm chứng | Kết quả |
|---|---|
| `.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q` | **650 passed**, không skip, 1 warning python_multipart, 196,27 giây |
| 4 file focused: char_plate_reader, best_plate_api, recognition_reviews, plate_dataset_export | **31 passed**, 1 warning, 30,78 giây |
| `node --test frontend/test/*.test.mjs` | **26 passed**, 0 fail/skip |
| `npm --prefix frontend run lint` | Exit 0; còn warning, trong đó PlateReviewPanel và một số effect |
| `npm --prefix frontend run build` | Exit 0; bundle JS khoảng 870 kB, cảnh báo chunk lớn |
| API review qua `app.main.create_app()` thật, không chạy lifespan, user dependency giả, SQLite tạm riêng | Tái hiện các lỗi contract/phân quyền bên dưới; không nạp weights hoặc mở RTSP |
| Test reader sau khi import Ultralytics thật, tiến trình riêng | Test pass nhưng module Ultralytics gốc không được phục hồi |

Kết quả 26 Node là toàn bộ glob hiện tại; con số 13 trong báo cáo trước là tập con, không phải lỗi mới.

## Những phần chặn nghiệm thu, theo ưu tiên

### R1 — Hai camera cùng cổng chưa được runtime tạo riêng (P1)

`app/cv/pipeline.py:2270` vẫn lưu `_pipelines` theo `gate_id`. `_create_pipeline_locked()` lấy cấu hình GATES và nguồn của gate, tạo một VideoPipeline. `start_all_pipelines()` duyệt gate; không dùng danh sách camera front/rear trong DB để tạo hai pipeline cho cùng gate. `camera_id` trong constructor/metadata không đủ tạo nguồn thứ hai.

**Sửa:** runtime/vòng đời keyed camera_id, mapping gate → camera IDs và adapter endpoint cũ. Chứng minh hai camera cùng gate có nguồn/frame/tracker/epoch riêng, camera switch 202 và lỗi một nguồn không reset nguồn còn lại. Test cameras CRUD không thay thế test startup/runtime này.

### R2 — Capture vẫn chờ AI, chưa có profile front/rear (P1)

`app/cv/pipeline.py:1068` đọc source rồi cùng vòng lặp chờ Future detection tại `1127` và các bước pose; `capture.py` vẫn là wrapper đọc đồng bộ. Constructor vẫn nạp cả mũ/biển/COCO và pool ba detector cho mỗi pipeline. Chưa thấy điều phối GPU/profile nhiệm vụ riêng camera.

`pipeline.py:1158` vẫn bỏ qua khi không thấy person. Đây là đường chặn OCR phía sau dù thấy xe/biển. `_observe_best_plate()` vẫn trigger dựa trên crossing của pipeline, chưa có vùng đọc rear độc lập.

**Sửa:** capture latest-frame/display riêng; AI lấy frame mới; profile front=mũ/hành vi, rear=xe/biển/reader. Rear không cần person để đọc. Test chặn AI/OCR vẫn tăng frame_seq preview; không tính JPEG lặp thành FPS; thử hai nguồn video cách ly trước camera thật.

### R3 — Reader ký tự chưa được gọi trong pipeline (P1)

Có `app/cv/char_plate_reader.py`, decoder và flag `CHAR_PLATE_READER_REVIEW_ONLY`. Tuy nhiên tìm kiếm production code không thấy pipeline tạo/gọi CharPlateReader hoặc merge_with_easyocr. `_ocr_task()` tại `pipeline.py:61` vẫn gọi EasyOCR; `recognition_models()` vẫn báo EasyOCR.

Adapter unit test/hash pin chứng minh helper hoạt động trong mock, chưa chứng minh camera dùng reader. Báo cáo cuối gọi wrapper là “YOLOv26” là sai mô tả; trọng số đã train là YOLOv8n 36 ký tự.

**Sửa:** flag thật đi qua worker/best-crop, gọi reader đúng một attempt/lượt và hiển thị candidate review-only, engine/hash/device thật. Tắt flag giữ baseline. Không auto-gán học sinh từ candidate, không thay detector biển bằng reader ký tự.

### R4 — Thẻ duyệt chưa nối vào UI và chưa có producer review (P1)

`frontend/src/pages/GuardPage.jsx:157` chỉ render RecognitionLogPanel. PlateReviewPanel tồn tại nhưng không có import/render từ trang. `create_recognition_review()` chỉ tìm thấy ở DB helper và test; chưa có caller từ capture/OCR/runtime tạo review và lưu crop nguồn.

**Sửa:** một native best crop được ghi thành công → proposal + media/hash/provenance → review có ID → thẻ duyệt trong GuardPage. Kiểm thử một lượt không vi phạm vẫn tạo được thẻ review, feedback reload còn tồn tại, media trả 200 với ảnh đúng. Không dùng review seed trực tiếp DB để gọi là luồng nhận diện hoàn tất.

### R5 — Feedback contract chưa dùng được đầy đủ (P1)

Các lỗi đã tái hiện qua app factory thật với DB riêng:

| Ca kiểm chứng | Kết quả hiện tại | Điều kiện cần |
|---|---|---|
| GET list/detail review | Không có field `version` | Có version hiện tại; UI dùng để gửi expected_version |
| Current version 0, POST expected_version 50 | HTTP 200, applied=true | Version phải bằng hiện tại; sai version trả 409 |
| POST verdict incorrect không có corrected_text | HTTP 200, status rejected | Từ chối input chưa có chuỗi sửa hợp lệ, giữ nội dung người nhập |
| Key K đã phản hồi thẻ A, dùng K/body đó cho thẻ B | HTTP 200, idempotent_replay=true; thẻ B có **0 feedback** | Key/payload phải gắn review, reviewer và intent; không trả thành công giả cho tài nguyên khác |
| POST thành công | Trả expected_version cũ, không trả version mới | Response/current UI version cập nhật đúng |

`db.list_recognition_reviews()` tại `2213` và `get_recognition_review()` tại `2264` không SELECT version. `record_review_feedback()` tại `2355` chỉ từ chối version thấp hơn, cho version tương lai. Replay kiểm tra verdict/text/note/expected_version, thiếu review_id/reviewer; key chưa có unique constraint tại DB.

PlateReviewPanel dùng `review.version` tại dòng 75 nên khi gắn UI, request có thể thiếu expected_version bắt buộc. Dòng 85 gán version bằng expected_version cũ. Effect dòng 61–64 reset offset khi `fetchReviews` thay đổi; callback lại phụ thuộc offset, nên bấm trang tiếp có thể reset về trang đầu và request cũ ghi đè response mới. Key theo review+verdict cũng không phân biệt hai lần sửa nội dung mới của cùng thẻ.

**Sửa:** hợp đồng trả `version/new_version` rõ; check equality và cập nhật nguyên tử; idempotency claim/replay có ràng buộc DB, trả lại kết quả gốc, khác tài nguyên/payload từ chối. UI tách reset bộ lọc khỏi effect fetch; hủy/bỏ response cũ, giữ intent key qua retry nhưng tạo key mới khi người dùng thực hiện sửa khác. Bổ sung tests các ca trên, không nới assertion để che lỗi.

### R6 — Review read không có giới hạn vai trò/phạm vi, feedback chưa kiểm tra Origin (P1)

`app/api/recognition_reviews.py:39/48` chỉ yêu cầu get_current_user, trả review không lọc quyền. Với user dependency teacher và **không có lớp**, GET list trả HTTP 200/toàn bộ 6 review thử, detail cũng 200. POST feedback của admin giả với Origin ngoài allowlist cũng được nhận 200. App factory hiện không có middleware Origin bao phủ riêng route này.

Phép thử này giả lập tài khoản ở dependency để kiểm tra router; chưa phải test đăng nhập cookie đầy đủ. Nó xác nhận tầng router chưa áp dụng yêu cầu quyền/Origin của kế hoạch.

**Sửa:** dùng cùng quy tắc quyền server cho list/detail/media. Mặc định review dành admin/security/management được cấp; nếu mở cho giáo viên thì phải có quan hệ/phạm vi lớp thật, thiếu lớp từ chối. POST dùng Origin guard nhất quán khi xác thực cookie. Test cookie thật qua app factory, teacher thiếu/khác lớp, tài khoản không được cấp và Origin sai.

### R7 — Test reader còn gây nhiễm import (P2)

`app/tests/test_char_plate_reader.py:102` gán sys.modules["ultralytics"] bằng stub, finally dòng 117 pop thay vì phục hồi module cũ. Phép thử import Ultralytics trước rồi gọi test đã cho:

```json
{"test_function_passed": true, "ultralytics_original_restored": false, "ultralytics_in_sys_modules": false}
```

Đây là lỗi isolation thật dù suite lần này pass. Dùng monkeypatch.setitem hoặc fixture bảo toàn module/package binding. Không chỉ xóa assertion brittle; kiểm chứng chạy riêng và sau các test detector.

### R8 — Một số mục chỉ có công cụ/logic, chưa đạt luồng nghiệm thu (P2)

- Export dataset hiện xuất manifest và **gợi ý key nhóm**, chưa thực hiện split 70/15/15, xác minh crop/hash/box ký tự hoặc chống ảnh gần trùng. Ghi đúng trạng thái “có công cụ xuất”, không gọi toàn tập leakage-safe đã nghiệm thu.
- Audio rate backend/speak mặc định 1,45 đã có, nhưng `alertAudio.js:22` và `AlertBanner.jsx:90` fallback vẫn 1,30. Khi request config lỗi, factory truyền 1,30 nên speak fallback 1,45 không được dùng. Đồng bộ default và test config fetch fail.
- Nút bật loa hiện cần test gesture/resume, lease, speech onstart/error và nghe thực. Node mock không chứng minh loa vật lý phát.
- Conftest vẫn dựng FastAPI app thử riêng; test tích hợp mới phải qua create_app thật, fake capture/model có kiểm soát và không nạp camera/model thật trong HTTP unit test.
- Gương chưa có phép đánh giá/model runtime tương ứng; giữ review-only/unknown khi chưa đủ góc nhìn và nhãn.

## Bằng chứng phép thử API

SQLite tạm: `C:/Users/khucv/AppData/Local/Temp/sgm_fr_review_40g7ztr6/audit.sqlite`.

Output: `C:/Users/khucv/AppData/Local/Temp/sgm_fr_review_40g7ztr6/result.json`. Toàn bộ dữ liệu trong đó là review/user giả. Không truy cập DB/camera vận hành.

## Prompt tiếp theo có thể giao Cursor

> Tiếp tục theo `docs/CODEX_FR0_FR10_REVIEW_2026_10_01.md`. Đừng đánh dấu FR0–FR10 hoàn tất từ 650 unit test. Hai assertion cũ đã sửa; giữ chúng, vá isolation reader bằng fixture phục hồi module. Ưu tiên R5/R6: feedback version, validation, idempotency và quyền/Origin; thêm test hành vi tái hiện trước khi sửa. Sau đó làm R1/R2: hai pipeline theo camera_id cùng gate, profile front/rear, capture/display độc lập AI, rear không cần person/crossing front để đọc. Nối R3/R4: reader ký tự dưới flag review-only → best crop thật được ghi → review API → PlateReviewPanel trong GuardPage → feedback lưu và xuất được. Giữ một OCR attempt/lượt, một beep/câu crossing, camera switch 202, bằng chứng trước audio và gương review-only. Test tích hợp phải đi xuyên create_app production với capture/model thử; test feedback đi từ GET version tới POST, không tự seed version 0 để che thiếu field. Đồng bộ fallback rate 1,45 và kiểm chứng browser gesture/lease/onstart/error. Đính chính execution log/acceptance report và tên model YOLOv8n. Chạy full pytest không skip, toàn bộ Node, lint/build và browser E2E sau từng nhóm. Khi các luồng trên đạt, FR11A chạy hai VIDEO cách ly 30 phút, 1–3 viewer; FR11B sau đó mới dùng hai Imou thật và ca 12 giờ. FR11A không bị chặn bởi thiếu Imou. Không đổi nguồn/DB/media vận hành, nâng dependency hoặc auto-gán học sinh bằng reader chưa nghiệm thu. Tiếp tục các phần độc lập, ghi thiếu thiết bị/nhãn cụ thể.

## Thứ tự và điều kiện chuyển bước

1. **Vá feedback/quyền/isolation**: GET version → người dùng sửa → POST đúng → version mới → reload đúng; key trùng/tương lai/thiếu chuỗi/phạm vi sai phải bị xử lý đúng.
2. **Nối runtime nhận diện**: hai camera/cùng gate + profile + capture độc lập + rear không cần person; reader flag thực được worker gọi.
3. **Nối UI và loa**: crop thật → thẻ → duyệt; event có bằng chứng → một máy có lease → một beep/câu đúng tốc độ. Browser test thành công và nghe thực nếu máy có giọng/loa.
4. **Benchmark FR11A**: hai video cách ly 30 phút, FPS hình mới/AI, p95 tuổi frame, CPU/RAM/VRAM/queue, 1/2/3 viewer. Không cần chờ phần cứng để làm bước này.
5. **FR11B + chất lượng tại trường**: preview/config hai Imou, day/night crop người duyệt, precision/recall/false acceptance và ca 12 giờ. Training thêm chỉ sau phân loại nguyên nhân detector/crop/reader/nguồn ảnh.

Chưa promote model mới hoặc tự ghép hai góc khi các điều kiện chất lượng cũ chưa đạt. Giữ tiêu chí, báo phần thiếu; không hạ ngưỡng để có nhiều tiếng/cảnh báo.
