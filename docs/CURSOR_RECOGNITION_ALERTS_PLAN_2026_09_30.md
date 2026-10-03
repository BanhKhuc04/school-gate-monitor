# Kế hoạch tiếp theo cho Cursor: nhãn chuẩn, xác nhận nhiều frame và cảnh báo nhanh

> Người dùng duyệt ngày 30/09/2026. Người thực hiện mã, dữ liệu và kiểm thử: **Cursor**.
> Phụ thuộc phần sửa OCR và tách capture/AI của [kế hoạch A–D](CURSOR_DUAL_CAMERA_PERFORMANCE_PLAN_2026_09_30.md).
> Giữ yêu cầu an toàn dữ liệu của [master plan](CURSOR_MASTER_PLAN_2026_09_30.md); cập nhật kết quả trong [execution log](CURSOR_EXECUTION_LOG.md).
> Đây là yêu cầu thực thi đã duyệt, không phải báo cáo các tính năng đã hoàn thành. Người dùng tự gửi prompt cho Cursor; việc tạo tài liệu không đồng nghĩa Agent đã nhận việc.

## 1. Mục tiêu và nguyên lý nhận diện

Áp dụng sau phần sửa OCR và tách luồng hai camera của kế hoạch A–D. Giữ mục tiêu hiển thị ≥15 FPS/camera, AI ≥5 FPS/camera; ưu tiên ít báo sai.

Nguyên lý:

**Ảnh mới → phát hiện đối tượng → ghép đúng người/xe → theo dõi cùng lượt xe → tích lũy bằng chứng riêng từng lỗi → cập nhật bảng → đọc các lỗi đã xác nhận.**

Không đợi OCR mới xử lý lỗi mũ hoặc dắt xe. Không dùng một frame, một box mất hoặc một lần OCR để kết luận vi phạm.

Các quy tắc đã chốt:

| Nội dung | Quy tắc |
|---|---|
| Gương | Kiểm tra **gương trái theo phía người ngồi lái**. Bên khuất hoặc không đủ góc nhìn là “chưa xác định”. |
| Không dắt xe | Mặc định: xác nhận người đang ngồi đi xe **và** xe qua đường cổng. Dắt bộ, đứng yên không báo lỗi này. |
| Biển chưa đọc rõ | Bảng vàng, `needs_review`, **không beep và không đọc loa**. |
| Giọng đọc | Mặc định câu ngắn: tên cổng + lời nhắc; không chờ biển số hoặc đọc tên học sinh. |

## 2. Chuẩn hóa nhãn và dữ liệu huấn luyện

Tạo hướng dẫn gán nhãn có ảnh minh họa đúng/sai, dùng cùng quy ước cho CVAT, training và runtime.

- **Mũ:** phân biệt đầu đang đội mũ, đầu không đội mũ và đầu không quan sát đủ. Mũ cầm tay/treo trên xe không được tính là đang đội. Box cùng bao vùng đầu, tránh mẫu dương khoanh cả người còn mẫu âm chỉ khoanh đầu.
- **Gương:** đánh dấu gương nhìn thấy, liên kết với đúng xe. Gán thêm trạng thái vùng tay lái trái: có gương, thiếu rõ ràng, không quan sát được. Không tạo box cho vật thể vắng mặt.
- **Biển:** box ôm toàn biển, nhận cả một dòng/hai dòng; lưu chuỗi chuẩn chỉ khi đọc rõ. Mẫu mờ, chói, khuất phải ghi nguyên nhân, không đoán ký tự.
- **Hành vi:** gán theo đoạn video gồm `riding`, `pushing`, `walking`, `stationary`, `unknown`. Không dùng một ảnh chân co hoặc chân thẳng làm nhãn chuẩn cho hành vi dắt xe.
- Mỗi mẫu lưu video nguồn, timestamp, gate, đối tượng liên quan và chất lượng quan sát. Nhãn trạng thái để trong manifest riêng, không trộn thành class ID của detector.
- Bổ sung mẫu dễ nhầm: mũ vải, áo mưa, mũ treo, gương giống đầu người, chữ trên áo, xe sát nhau, người che biển và người đứng cạnh xe.

Hiện có 229 ảnh chờ rà mũ, 310 ảnh biển và 245 ảnh nhóm lớp mới; đây chưa phải bằng chứng đã có nhãn chuẩn.

Chia train/validation/test **70/15/15 theo video hoặc phiên ghi hình**; loại ảnh trùng và không chia các frame cùng lượt xe sang nhiều tập. Kiểm tra toàn bộ nhãn tự sinh, rà lần hai ít nhất 20% mẫu và toàn bộ mẫu khó. Xuất detector theo định dạng Ultralytics, giữ mapping class có phiên bản. [Định dạng dữ liệu chính thức](https://docs.ultralytics.com/datasets/detect/)

## 3. Sửa cơ chế quyết định và từng loại lỗi

### Xác nhận nhiều frame nhưng không chờ lâu

Ưu tiên sửa các lỗi đã kiểm tra:

- Bộ đếm hiện vẫn chấp nhận 5 quan sát trải dài 3,6 giây dù cấu hình cửa sổ 2 giây.
- Khi không có track ID, pipeline bỏ qua bước xác nhận nhiều frame.
- Một lần OCR confidence 0,55 có thể được tin dùng.
- Nhánh `standing/unknown` vẫn có thể tạo lỗi chạy qua cổng.

Thay bằng bộ bằng chứng **riêng từng loại lỗi**, khóa theo gate + phiên nguồn + lượt xe:

- Chỉ đếm frame mới, không đếm lại frame/cache; khoảng cách mẫu tối thiểu 100 ms.
- Mặc định xét tối đa 5 quan sát hợp lệ trong 1,5 giây. Xác nhận khi có ít nhất 4 mẫu đồng thuận, tỷ lệ đồng thuận ≥80%, trải dài ít nhất 400 ms.
- Mẫu bị che, quá nhỏ hoặc mờ là `unknown`, không trở thành phiếu “có lỗi” hoặc “không lỗi”.
- Bằng chứng trái chiều rõ ràng chuyển sang cần kiểm tra; không dùng đa số để che mất mâu thuẫn.
- Chưa có track ổn định chỉ hiển thị đang kiểm tra, không phát vi phạm chính thức.
- Các tham số là cấu hình có phiên bản. Chỉ điều chỉnh bằng tập validation; không giảm số mẫu để che việc AI chạy chậm.

Với AI 5 FPS, bốn mẫu mới liên tiếp có thể thu trong khoảng 0,6 giây; đây là thời gian thu mẫu lý tưởng, chưa bao gồm các công đoạn khác.

### Quy tắc từng lỗi

| Loại | Điều kiện xác nhận |
|---|---|
| Không đội mũ | Đầu không đội mũ nhìn rõ, thuộc đúng người đang đi xe, đủ bằng chứng thời gian. Không thấy mũ đơn thuần không đủ. |
| Không dắt xe | Người–xe liên kết ổn định, tư thế và chuyển động phù hợp đang đi xe, đồng thời cắt đường cổng. Giữ yêu cầu ít nhất 3 frame ổn định mỗi phía trong tối đa 5 giây; kiểm tra lại implementation hiện tại. |
| Thiếu gương trái | Có đánh giá vùng tay lái trái đủ rõ và bằng chứng thiếu gương qua nhiều frame. Không suy ra từ việc detector không thấy box gương. |
| Chưa đọc rõ biển | OCR chưa ổn định, biển khuất hoặc chất lượng ảnh yếu → bảng vàng, không phát âm thanh. |
| Không có/che biển | Không tự kết luận từ OCR rỗng hoặc thiếu box. Chuyển cần kiểm tra nếu chưa có bằng chứng trực tiếp. |

Gương là nhánh mới: mặc định chỉ chạy đánh giá và lưu bằng chứng. Chỉ bật cảnh báo thiếu gương cho gate có góc quan sát phù hợp và model đã đạt kiểm chứng.

OCR phải có ít nhất **hai crop khác frame đọc giống toàn biển**, đạt chất lượng và không có kết quả cạnh tranh đáng tin cậy trước khi gán xe/học sinh. Khi chưa đủ, tiếp tục thu mẫu tốt; không đọc lại mọi frame.

## 4. Bảng cảnh báo, API và giọng đọc thống nhất

### Một lượt xe, một bản ghi có thể cập nhật

Bổ sung vào event: `event_id`, `gate_id`, `source_epoch`, `encounter_id`, thời điểm quan sát/xác nhận và danh sách `issues[]`.

Mỗi issue chứa mã lỗi, trạng thái xác nhận, lý do, số mẫu và tham chiếu bằng chứng. Trạng thái AI tách khỏi trạng thái xử lý nghiệp vụ như `pending`, `reviewed`, `resolved`.

- Xác nhận lỗi mũ trước thì cập nhật ngay; OCR và gương bổ sung sau vào cùng event.
- Không gom mất chi tiết thành chữ “Nhiều vi phạm”.
- Giữ trường API cũ trong giai đoạn tương thích; migration bổ sung, không sửa dữ liệu lịch sử.
- Bảng, banner, bộ lọc, báo cáo và lời đọc dùng cùng danh mục mã lỗi.

### Bảng hiển thị

- **Xám:** đang kiểm tra, chỉ hiển thị trực tiếp.
- **Vàng:** cần kiểm tra, chưa đủ bằng chứng.
- **Đỏ:** có lỗi đã xác nhận.

Mỗi dòng hiện cổng, thời gian, các lỗi cụ thể, biển đã xác nhận hoặc “chưa đọc rõ”, ảnh/crop và lý do cần kiểm tra. Một dòng có thể chứa lỗi mũ đỏ và biển vàng; màu vàng của OCR không làm mất cảnh báo mũ.

Không hiển thị confidence model dưới dạng “độ chính xác của kết luận”.

### Giọng đọc

- Câu mẫu: “Cổng chính, mời xuống xe dắt bộ”; “Cổng phụ, vui lòng đội mũ bảo hiểm”.
- Thiếu gương đã xác nhận: “Cổng chính, mời kiểm tra gương trái”.
- Mặc định tốc độ `1.15`, cho chỉnh `0.9–1.4`, có nút nghe thử và bật/tắt âm thanh. Kiểm tra trên giọng tiếng Việt thực có của máy. [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/rate)
- Gộp các lỗi cùng lượt đến trong 300 ms thành câu ngắn, tối đa hai lời nhắc; bảng vẫn hiện đầy đủ.
- Ưu tiên dắt xe → mũ → gương. Không đọc lỗi OCR chưa chắc chắn.
- Hàng đợi tối đa hai câu chờ; bỏ câu chưa phát đã quá 5 giây. Không chồng tiếng hoặc thường xuyên cắt ngang câu.
- Chống đọc lặp theo event + mã lỗi; reconnect không đọc lại lịch sử. Đổi gate hoặc tắt âm thanh phải dọn câu/timer cũ.
- Chỉ bật loa trên máy bảo vệ được chọn; các viewer còn lại vẫn nhận bảng.

## 5. Thứ tự triển khai và nghiệm thu

Cursor thực hiện theo thứ tự:

1. Sửa cửa sổ bằng chứng, bỏ đường tắt một frame và các suy luận sai về biển/tư thế.
2. Thống nhất event nhiều lỗi, bảng và lời đọc.
3. Hoàn thiện nhãn, huấn luyện/đánh giá mũ và gương; sửa ghép đối tượng/OCR.
4. Đo đồng thời hai camera và bật từng nhánh đạt tiêu chí.

Kiểm thử bắt buộc:

- Một frame sai giữa nhiều frame đúng; frame lặp, mất track, đổi nguồn và quan sát vượt cửa sổ thời gian.
- Mũ cầm tay, đầu khuất, hai người chung xe, hai xe sát nhau.
- Dắt xe qua cổng, đứng cạnh xe, ngồi xe đứng yên, đi xe qua hai hướng.
- Gương trái có/thiếu/khuất; ảnh lật và góc không xác định được bên trái.
- Biển hai dòng, mờ, chói, OCR mâu thuẫn, OCR lỗi và kết quả đến trễ.
- Nhiều lỗi cùng xe, nhiều xe cùng lúc, hai viewer, reconnect và hàng đợi tiếng nói.

Mục tiêu mới cho các lỗi được đọc loa: **precision ≥95%**, báo riêng từng loại. Giữ recall ≥70% trên trường hợp rõ và OCR toàn biển ≥50% trên ít nhất 30 biển rõ. Tập test cần tối thiểu 50 lượt vi phạm và 50 lượt không vi phạm; nhánh gương cần riêng ít nhất 30 lượt thiếu rõ và 30 lượt đủ gương rõ trước khi xét bật loa.

Đo thêm: xác nhận lỗi mũ p95 ≤2 giây từ quan sát hợp lệ đầu tiên; lỗi qua cổng p95 ≤1 giây sau khi đủ điều kiện crossing; bảng cập nhật p95 ≤500 ms sau xác nhận; tiếng nói bắt đầu ≤1 giây khi hàng đợi rỗng. Đây là mục tiêu cần nghiệm thu, không phải cam kết đã đạt.

Ghi toàn bộ kết quả vào execution log hiện có. Thiếu góc nhìn hoặc nhãn chuẩn thì giữ nhánh đó ở chế độ cần kiểm tra, tiếp tục các phần độc lập; không hạ tiêu chí hoặc bật cảnh báo thiếu căn cứ.

## 6. Tổ chức thực thi cho Cursor

Phần này đánh số nhiệm vụ để không nhầm với các đợt 1–7 và A–D đã có; không thay đổi yêu cầu đã duyệt ở trên.

### Kiểm tra đầu vào và quan hệ với kế hoạch trước

- Đọc mã/test hiện tại trước khi áp dụng phát hiện lịch sử. Khi tạo tài liệu này, `app/cv/ocr.py` đã chuyển `allowlist`/`paragraph` sang `readtext`; cần kiểm chứng, không sửa lại chỉ vì báo cáo trước ghi lỗi constructor.
- Xác minh phần nền A/B: OCR hoạt động, capture không chờ inference, frame có danh tính nguồn, hàng đợi OCR giới hạn và hiển thị không chờ OCR. Nếu còn thiếu, hoàn thiện phần phụ thuộc đó trước khi tích hợp cảnh báo mới.
- Tiếp tục công việc C về crop/ghép/voting cùng E3 dưới đây. Thử model/tracker ở D vẫn cần môi trường riêng; không phải điều kiện bắt buộc để sửa luật sai ở E1/E2.
- Kế hoạch này cập nhật quy tắc nhiều frame, OCR, mũ/dắt xe/gương và âm thanh. Khi tài liệu cũ mô tả “5 frame liên tiếp”, “một lần OCR đủ tin” hoặc đọc lỗi OCR, dùng quy tắc mới tại đây.
- Giữ hợp đồng chọn camera POST 202, GET checking/applied/error, đổi lỗi giữ nguồn cũ. Không viết lại vi phạm lịch sử khi thêm schema/nhãn.

### Nhiệm vụ và bằng chứng hoàn tất

| ID | Phần việc | Bằng chứng cần ghi vào execution log |
|---|---|---|
| E1.1 | Bộ bằng chứng theo từng lỗi/gate/phiên/lượt | Test 4 mẫu/80%/1,5 giây/400 ms; khoảng cách 100 ms; frame trùng, out-of-order, cửa sổ hết hạn, unknown và mâu thuẫn rõ |
| E1.2 | Luật mũ/dắt xe/biển và không bypass khi thiếu track | Test đứng yên/dắt bộ/unknown không thành riding; crossing đủ hai phía; OCR chưa có/lỗi/rỗng không thành không biển/bị che |
| E1.3 | Bỏ tin OCR một lần, giữ bằng chứng từng crop | Hai crop thật khác frame mới đủ điều kiện; một crop gọi lại không tăng phiếu; ký tự mâu thuẫn không gán học sinh |
| E2.1 | Event nhiều issue + lưu/cập nhật/API tương thích | Một lượt một event, issue độc lập; migration lặp lại an toàn; API cũ hoạt động; DB lịch sử không bị sửa; ảnh/crop tồn tại và đúng sự kiện |
| E2.2 | Bảng/banner/bộ lọc/nhãn thống nhất | Xám/vàng/đỏ đúng trạng thái; đỏ mũ + vàng biển cùng dòng; hiển thị lý do và bằng chứng; không gọi confidence là độ chính xác |
| E2.3 | Giọng đọc và máy phát âm thanh | Test OCR-only hoàn toàn im lặng; gộp 300 ms; hai câu chờ/TTL 5 giây; rate 1.15 và điều chỉnh; dedup, reconnect, đổi gate, tắt loa và nhiều viewer |
| E3.1 | Hướng dẫn nhãn, manifest và split có phiên bản | Ảnh ví dụ đúng/sai; số mẫu được review; rà lần hai 20% + toàn bộ mẫu khó; kiểm trùng và rò video/lượt giữa 70/15/15 |
| E3.2 | Train/eval mũ, gương, ghép đối tượng | Hash model/dữ liệu/cấu hình; kết quả từng lớp trước/sau; đánh giá bên trái theo người lái, góc nhìn/ảnh lật; mẫu khó và unknown riêng |
| E4.1 | Đo end-to-end hai nguồn | Hai nguồn 30 phút, một/hai viewer; FPS thật, CPU/RAM/VRAM, p95 từng giai đoạn; lỗi OCR/chậm/mất mạng/reconnect |
| E4.2 | Kết luận đủ điều kiện bật từng nhánh | Precision/recall/OCR với mẫu số và FP/FN; thiếu mẫu ghi rõ; gương chưa đủ điều kiện vẫn review-only; không tự triển khai vào tiến trình vận hành |

### Quy tắc nghiệm thu không được bỏ qua

- Cửa sổ thời gian và khoảng cách mẫu dùng thời điểm frame nguồn/đồng hồ đơn điệu; không thay bằng thời điểm callback OCR hoàn tất. Mẫu nguồn cũ không được tăng phiếu của nguồn mới.
- Mỗi loại lỗi có bằng chứng riêng. Không cộng một frame lỗi mũ và một frame lỗi biển để thành hai phiếu cho `MULTIPLE`.
- Ngưỡng theo tỷ lệ không cho phép mẫu mâu thuẫn rõ bị bỏ qua. Ghi được số mẫu hợp lệ, số phiếu hỗ trợ, mâu thuẫn, unknown và khoảng thời gian để giải thích quyết định.
- Một lỗi được xác nhận vẫn có thể đi cùng OCR pending/error mà không chờ OCR. Chỉ các issue xác nhận và được phép phát âm thanh mới đi vào hàng đợi TTS; không để trường legacy `MULTIPLE` mở lại tiếng đọc lỗi biển.
- Cập nhật cùng event phải idempotent; kết quả đến trễ không tạo dòng mới, không lùi trạng thái bằng snapshot cũ và không đọc lặp cùng issue. Trạng thái AI không ghi đè quyết định xử lý nghiệp vụ của người dùng.
- `unknown` không được xem là negative khi tính độ chính xác. Báo tỷ lệ trường hợp không xác định và lý do riêng; không bỏ lỗi OCR rỗng trên biển nhìn rõ khỏi mẫu số OCR.
- Bật nhánh gương cần cả điều kiện model và góc nhìn từng gate. Không dùng bên trái ảnh thay cho bên trái người lái; không kết luận thiếu chỉ vì detector không thấy.
- Độ trễ tiếng nói tính đến sự kiện bắt đầu phát thật, không phải thời điểm gọi `speak()`. Kiểm thử khi trình duyệt chưa được bật âm thanh hoặc thiếu giọng tiếng Việt; UI phải báo rõ thay vì ghi thành công giả.
- Các bảng số liệu lịch sử trong log là đầu vào đối chiếu. Không sửa số test/metric cũ thành kết quả mới; thêm lần chạy mới có lệnh, cwd, cấu hình, thời điểm và artifact.

### Prompt giao việc

```text
Thực thi docs/CURSOR_RECOGNITION_ALERTS_PLAN_2026_09_30.md trong dự án hiện tại.
Đọc master plan, kế hoạch hai camera A–D và execution log trước khi sửa.
Kiểm tra working tree; giữ mọi thay đổi chưa commit và kết quả đã có.
Xác minh phần nền sửa OCR/tách luồng A–B, chỉ hoàn thiện phần còn thiếu, sau đó
làm E1 → E2 → E3 → E4 liên tục. Không chỉ trả lại một kế hoạch.
Quy tắc mới là nguồn chốt cho nhãn, xác nhận nhiều frame và âm thanh: gương trái;
dắt xe phải xét hành vi và crossing; biển chưa rõ chỉ bảng vàng, không beep/TTS;
OCR cần hai crop khác frame; mỗi lỗi có bằng chứng riêng và cùng lượt cập nhật
cùng event; giọng đọc ngắn, rate 1.15, chống lặp và không tích tụ câu cũ.
Giữ gương review-only cho tới khi dữ liệu/model/góc nhìn đạt nghiệm thu.
Sau mỗi phần chạy test liên quan và bộ chung, cập nhật docs/CURSOR_EXECUTION_LOG.md
bằng kết quả thực. Thiếu nhãn/thiết bị chỉ chặn phần phụ thuộc; tiếp tục phần độc lập.
Không hạ ngưỡng để ghi DAT. Không sửa camera/DB/media vận hành, không nâng dependency
trong môi trường đang chạy, không push/deploy. Chưa đủ số đo thì báo chưa nghiệm thu.
```
