# Prompt tiếp theo cho Cursor: vá các điểm còn thiếu trước E3 và nghiệm thu hai camera

Ngày bàn giao: 01/10/2026 (Asia/Bangkok). Codex lập và bàn giao kế hoạch; Cursor thực hiện sửa mã trong repository hiện tại. Tài liệu này bổ sung kế hoạch ổn định hệ thống ngày 30/09, không thay các tiêu chí nghiệm thu và giới hạn vận hành đã chốt.

**Ưu tiên tiếp theo là hoàn thiện E2 và nền tảng hai camera. E3.1 kiểm kê dữ liệu có thể làm song song; huấn luyện E3.2 thực hiện sau khi luồng nhận diện và đánh giá đã ổn định.**

## 1. Kết quả đối chiếu báo cáo

Codex đã kiểm tra mã hiện tại và chạy phép thử cách ly trong lượt rà soát trước khi bàn giao:

- **Crossing vẫn sai yêu cầu 3+3:** chuỗi ba frame phía A rồi một frame phía B đã trả `True`. Test `test_three_above_one_below_crosses` cũng đang khẳng định hành vi sai này là đúng.
- **OCR-only vẫn phát beep:** `playAlertSound()` chạy trước bộ lọc im lặng. Bộ lọc chỉ chặn TTS và chưa bao gồm `PLATE_LOW_CONFIDENCE`.
- **Cảnh báo vẫn phát trước khi ghi bằng chứng:** pipeline đẩy alert ngay sau khi gửi tác vụ ghi media/DB vào pool.
- **Bảng encounter chưa hoàn chỉnh:** phân trang bản ghi trước rồi mới gom lượt xe; `total` chỉ là số nhóm trong trang đang lấy. Một issue `resolved` có thể khiến cả nhóm thành resolved dù còn lỗi khác.
- **Hai camera cùng cổng chưa được nối đầy đủ:** pipeline vẫn mặc định `camera_id = gate_id`; encounter tạo từ `gate + track_id + epoch`, có nguy cơ trùng khi hai camera cùng track ID và epoch.
- **Metadata bằng chứng chưa đúng:** `sample_count` đang lấy số thứ tự frame, không phải số mẫu xác nhận.
- Frontend vẫn dùng `localhost:8001` và token trong localStorage; endpoint encounter vẫn cần chặn giáo viên không có lớp.

`venv` đã cài OpenCV 4.10.0.84, Ultralytics 8.2.103 và EasyOCR 1.7.2 theo metadata package. Chưa cần cài thêm dependency. Kiểm tra metadata không chứng minh import, CUDA hay camera thật hoạt động. Codex chạy lại **5 test Node đạt**, nhưng đây là unit test; test “OCR-only silent” chỉ kiểm tra mã có bộ lọc, chưa chứng minh không beep/TTS.

**411 test đạt trong báo cáo chưa đủ chứng minh toàn hệ thống đúng. Codex chưa chạy lại toàn bộ bộ test trong lượt đối chiếu này.** Cursor đối chiếu lại mã mới trước khi sửa; không triển khai lại phần đã được sửa và có test hành vi đúng yêu cầu.

## 2. Đợt tiếp theo — vá hành vi và sửa test

Cursor tiếp tục trong repository hiện tại, giữ nguyên thay đổi chưa commit và thực hiện:

1. **Sửa crossing đúng 3+3.** Ba frame ổn định phía đầu và ba frame mới ổn định phía đích mới xác nhận; xử lý đi qua vùng biên, rung, quay đầu và hết hạn năm giây. Sửa test đang chấp nhận 3+1; thêm kiểm thử 3+1, 3+2 không xác nhận và 3+3 xác nhận một lần. Giữ biên chống rung theo 2% đường chéo trong tọa độ pixel, kể cả ảnh không vuông; frame lặp không tạo thêm mẫu.
2. **Hoàn thiện event nhiều lỗi.** Lấy số mẫu, thời điểm quan sát đầu tiên và tham chiếu frame từ ledger. Tách trạng thái AI khỏi trạng thái xử lý nghiệp vụ; xử lý một lỗi không được che lỗi khác còn tồn tại. Khi có lỗi đã xác nhận còn hiệu lực, dòng vẫn đỏ; chỉ có lỗi chưa chắc chắn thì vàng; đang quan sát thì xám. Trạng thái xử lý trình bày riêng.
3. **Gom encounter trước khi phân trang tại DB.** Trả tổng số lượt phù hợp bộ lọc, giữ đầy đủ issues của mỗi lượt; kiểm tra hơn 200 bản ghi và lượt có lỗi nằm ở hai trang cũ. Thứ tự ổn định; `limit` trong 1–200, `offset >= 0`; không tải toàn bộ dữ liệu vào Python để chữa phân trang.
4. **Hoàn thiện bảng React.** Hiển thị từng lỗi đỏ/vàng trong cùng dòng, lý do cần kiểm tra và bằng chứng; trạng thái tải lỗi không được hiện thành “không có dữ liệu”. Kiểm tra lọc, chuyển trang, request cũ đến muộn và retry.
5. **Sửa âm thanh theo hành vi.** OCR chưa rõ không beep/TTS. Xét `issues[]`; lỗi mũ đã xác nhận vẫn đọc khi OCR vàng. Dedup theo event + mã lỗi, cho phép đọc lỗi mới được bổ sung; dọn timer khi tắt loa, đổi phạm vi hoặc unmount. Giữ queue tối đa hai câu chờ, TTL năm giây, gộp 300 ms và tốc độ mặc định 1.15 theo kế hoạch chính; reconnect không đọc lịch sử. Bổ sung kiểm thử phát âm thanh bằng lời gọi thực của lớp audio/speech đã stub, không tìm chuỗi source.
6. **Ghi snapshot/crop và DB thành công trước âm thanh chính thức.** Bảng có thể cập nhật `evidence_state=pending`; không trả URL giả. Mô phỏng ghi ảnh thất bại, DB bận và ổ đĩa đầy. Clip có thể bổ sung sau; lỗi ghi phải hiện trong health/log và trạng thái event, retry hữu hạn.
7. **Sửa test gây nhiễm môi trường.** Thay gán trực tiếp `sys.modules["cv2"]` bằng fixture có hoàn trả; khôi phục biến môi trường và module sau test. Không kết luận mọi lỗi chỉ do interpreter trước khi kiểm tra chạy riêng và chạy chung. Dùng interpreter venv cố định; ghi lý do từng skip và xử lý skip sai điều kiện khi dependency thực có sẵn.

## 3. Nối hai camera và chuẩn bị E3

- Khởi tạo pipeline theo `camera_id`, ánh xạ cả trước/sau vào cùng cổng; trạng thái track khóa theo camera + phiên nguồn + track. Admin xác nhận vai trò bằng hình xem trước, không đoán từ tên nguồn cũ.
- Mỗi lượt nội bộ camera có định danh riêng. Chỉ liên kết vào encounter chung khi phép ghép trước/sau đã được hiệu chỉnh và kiểm chứng; mặc định tự ghép tắt. Track ID giống nhau ở hai camera không được làm trùng lượt. Giữ API cũ và hợp đồng chọn nguồn POST 202, GET `checking/applied/error`; nguồn lỗi giữ nguồn cũ.
- Giữ capture/hiển thị độc lập AI/OCR, JPEG dùng chung cho viewer và model chỉ phục vụ nhiệm vụ cần thiết của từng góc. Giữ ảnh nguồn đủ chi tiết; detect/hiển thị thu nhỏ giữ tỷ lệ. Queue hữu hạn, kết quả phiên cũ bị loại; OCR chậm không được làm hình đứng.
- Hoàn thiện cùng origin và cookie browser; chặn giáo viên thiếu lớp tại list/detail/media và endpoint encounter. Giữ Bearer cho script trong giai đoạn chuyển tiếp; browser không gửi token qua URL/localStorage. Kiểm chứng bằng app factory/router/middleware thực, media đúng quyền phải trả nội dung thật.
- **E3.1:** kiểm kê 14 video tại `C:\Users\khucv\Downloads\tranning`, hash, manifest và chia tập 70/15/15 theo video/phiên, giữ các góc cùng lượt trong cùng tập; rà nhãn mũ, biển và hành vi. Không đoán nhãn mơ hồ. Chỉ xác nhận cùng phiên/cùng lượt khi có bằng chứng; thiếu metadata thì ghi thiếu, không coi hai video bất kỳ là cặp đồng bộ.
- **E3.2:** đo baseline rồi mới huấn luyện/so sánh model. Gương giữ review-only; dữ liệu thiếu ghi rõ, tiếp tục phần độc lập. Nhãn tự sinh phải rà lại; giữ test riêng, không dùng test để chỉnh ngưỡng. Model mới chỉ được đưa vào cấu hình sử dụng khi vượt baseline và đạt tiêu chí độ trễ/chất lượng.

## 4. Kiểm chứng và bàn giao

Dùng interpreter cố định, chạy từ root repository:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
node --test frontend/test/speak.e2_3.test.mjs
```

Chạy thêm tại thư mục `frontend`:

```powershell
npm run lint
npm run build
npm run test:e2e
```

E2E dùng backend, DB/media và nguồn thử cách ly; không tự mở RTSP đang vận hành. Kiểm thử browser thực cho bảng, beep/TTS, cookie, hai viewer và reconnect. Test âm thanh phải quan sát lệnh phát, không chỉ tìm chuỗi trong source. Không dùng app thử thiếu router/middleware production làm bằng chứng nghiệm thu production.

Đo hai nguồn video cách ly 30 phút trước, sau đó nghiệm thu hai Imou thật theo kế hoạch hiện có: FPS hình mới, FPS AI, p95 latency, RAM/VRAM, precision từng lỗi và OCR toàn biển. Kiểm thử 30 phút là bước kiểm tra ban đầu; nghiệm thu vận hành vẫn cần ca 12 giờ. Tiếp tục giữ các mục tiêu: hiển thị ≥15 frame mới/giây/camera, AI ≥5 FPS/camera, latency nội bộ p95 ≤500 ms, precision lỗi đọc loa ≥95% mỗi loại, recall ≥70% trường hợp rõ và OCR toàn biển ≥50% trên ít nhất 30 biển rõ. Thiếu mẫu hoặc thiết bị thì ghi chưa đo/chưa nghiệm thu.

Cập nhật `docs/CURSOR_EXECUTION_LOG.md` và `docs/SYSTEM_ACCEPTANCE_REPORT_2026_09_30.md`, phân biệt **đã viết mã / test hành vi đạt / đã đo video / đã nghiệm thu camera thật**. Mỗi đợt ghi lỗi tái hiện, thay đổi, lệnh/exit code, trước/sau, artifact và rollback. Giữ lịch sử, đính chính bằng mục mới khi kết quả cũ không đúng yêu cầu.

Không thay nguồn vận hành, sửa DB/media thật, ghi đè thay đổi chưa commit, nâng dependency hoặc bật model mới chưa vượt baseline. Không push/triển khai VPS. Migration bổ sung tương thích; không drop bảng/cột chứa dữ liệu thật để rollback. Khi cần rollback, khôi phục cấu hình/mã có kiểm soát và kiểm chứng trên bản sao.

Tiếp tục các đợt độc lập, không dừng để hỏi sau từng bước. Khi thiếu góc nhìn, nhãn chuẩn hoặc thiết bị thật, ghi chính xác phần thiếu và giữ tính năng đó chưa nghiệm thu.
