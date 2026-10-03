# Kết quả vá Pre-E3 — Codex, 01/10/2026

Đã sửa trực tiếp các lỗi tái hiện R01–R06 trong `CODEX_PRE_E3_REVIEW_2026_10_01.md`, theo yêu cầu của người dùng. Giữ các thay đổi chưa commit của Cursor, không nâng dependency, không mở/đổi RTSP, không sửa DB hoặc media vận hành, không push/deploy.

Đây là kết quả sửa mã và kiểm thử cách ly. Chưa phải nghiệm thu độ chính xác hoặc sức tải của hai camera Imou thật.

## Thay đổi và bằng chứng

| Mục | Hành vi sau sửa | Kiểm chứng |
|---|---|---|
| R01 — Crossing | Cần ba frame mới ổn định mỗi phía trong cửa sổ năm giây. ON không bổ sung mẫu; frame lặp không được tính. Margin dùng 2% đường chéo pixel khi pipeline truyền kích thước ảnh. Một track chỉ crossing một lần. | `test_crossing.py`, `test_pre_e3_regressions.py`: 1+ON+3, 3+1/3+2/3+3, hai hướng, quá hạn, frame lặp, ảnh 1920×1080. |
| R02 — Bằng chứng/cooldown | Bỏ alert trực tiếp trong cooldown. Định danh lượt chứa gate, camera, phiên nguồn, track và phiên khởi động; các xe chưa đọc biển không dùng chung UNKNOWN. Snapshot/crop UUID phải ghi thành công, tồn tại và có dung lượng; DB phải thành công trước alert. Clip chạy ở pool riêng. Lỗi persist được thu lại, tối đa ba lần retry trước khoảng nghỉ 60 giây. | Test pipeline với ledger thật: hai xe, IO lỗi, DB lỗi, tệp không tồn tại, clip exception, cooldown và queue đầy. |
| R03 — Phạm vi lớp | COUNT/page/row-fetch đọc trong một transaction; row-fetch áp lại class scope. Teacher thiếu lớp bị từ chối. Detail và media đối chiếu quan hệ DB, không đoán quyền từ filename. Media hỗ trợ đường dẫn phẳng và lịch sử lồng thư mục, kiểm tra resolved path. | Encounter cùng ID nhưng khác lớp không rò dữ liệu; ảnh đúng quyền trả 200 và decode JPEG thật; khác/thiếu lớp bị chặn. Test 201 encounter với pagination và đủ issues. |
| R04 — Âm thanh | Chỉ issue confirmed, loại được cho phép và bằng chứng sẵn sàng được phát. OCR/pending/resolved im lặng cả beep lẫn TTS. Mixed OCR+mũ đọc lời nhắc mũ. Coalesce 300 ms, dedup event+issue, TTL và cleanup timer/queue. Viewer mặc định im lặng. Một guard/admin chủ động nhận lease loa 15 giây, heartbeat 5 giây; WS đánh dấu quyền loa của từng viewer. | Node quan sát callback beep/TTS; Chromium quan sát AudioContext/SpeechSynthesis và lời đọc. Lease có test xung đột, hết hạn, release, Origin/role; hai WS nhận cùng sự kiện nhưng chỉ chủ lease có quyền loa. |
| R05 — Guard/isolation | MJPEG có formatter dùng chung và giới hạn frame trong fixture test. Pipeline giả, không mở nguồn thật trong guard test. Không còn loại trừ hai file guard. WS dùng một consumer mỗi gate, queue 64 mỗi viewer, timeout gửi một giây, không giữ threading.Lock qua await; có theo dõi disconnect. | Guard auth/cookie/Bearer/query/Origin/bytes; hai viewer, gate riêng, client chậm và cleanup. Full suite chạy đủ. |
| R06 — Metadata/UI/quyết định | Số mẫu, thời điểm đầu và frame refs lấy từ ledger. Tối đa năm mẫu hợp lệ, không đếm lại frame đã hết cửa sổ; cooldown ledger không che mâu thuẫn rõ. Không có track ổn định thì không xác nhận. OCR rỗng/yếu/lỗi không suy ra thiếu/che biển, không gán roster. Giữ lỗi mũ cùng crossing. Bảng dùng encounter, từng issue và lý do; lọc/phân trang bỏ response cũ. Business status mới là pending, AI review nằm trong issues. | Test quyết định dùng hàm pipeline thật, không sao chép logic. Chromium kiểm tra hai màu cùng dòng, pagination, lỗi/retry, phản hồi cũ đến trễ. |

Phát hiện bổ sung qua vòng xử lý thật: `_frame_seq` không tăng, `_publish_frame_jpeg()` chưa được gọi và detector người vẫn dùng `detect()` thay vì `detect_tracked()`. Đã nối cả ba vào `_run_loop`. Hai test mới chạy chính vòng lặp với nguồn giả, cả trường hợp có/không có người và frame skip, xác nhận bốn frame có bốn JPEG khác nhau và tracking được gọi. Các test helper cũ không đủ chứng minh phần này đã hoạt động.

Queue đầu vào realtime giới hạn 256, enqueue không chặn IO; đầy thì bỏ cập nhật cũ, tăng `io_health.alerts_dropped`. Bản ghi đã lưu vẫn ở DB. Queue chưa thay thế cơ chế outbox/replay bền vững của kế hoạch hệ thống.

## Kết quả cuối

| Lệnh | Kết quả |
|---|---|
| `venv\Scripts\python.exe -B -m pytest app/tests -p no:cacheprovider --tb=short -q` | **500 passed**, 0 failed, 0 skipped; 126.03 giây; exit 0. Có một PendingDeprecationWarning từ Starlette/python_multipart. |
| `node --test frontend/test/alertAudio.test.mjs frontend/test/speak.e2_3.test.mjs` | **17 passed**, 0 skipped; exit 0. |
| `npx playwright test e2e/test_camera.spec.js e2e/test_pre_e3.spec.js --project=chromium` tại frontend | **9 passed**, 23.1 giây; exit 0. API/WS/audio/camera của browser được giả lập; không đo giọng loa hay camera thật. |
| `npm run lint` tại frontend | Exit 0; còn cảnh báo lint, gồm các cảnh báo effect/ref và Fast Refresh. Chưa tuyên bố lint sạch. |
| `npm run build` tại frontend | Exit 0; 711 module; JS 855.66 kB, gzip 250.41 kB; còn cảnh báo chunk >500 kB. |

Không cộng các lượt chạy từng nhóm vào tổng 500. Các test cũ yêu cầu vi phạm từ một frame/không track/OCR rỗng đã được thay bằng test hành vi đúng theo kế hoạch. Không hạ ngưỡng để làm test đạt.

Ảnh giao diện với dữ liệu tổng hợp: [pre-e3-violations-preview.png](pre-e3-violations-preview.png).

## Cách dùng và giới hạn còn lại

- Sau cập nhật, đăng nhập lại để browser nhận cookie dùng cho ảnh/clip được bảo vệ. Axios đã bật `withCredentials`; Bearer của script được giữ.
- Trên trang bảo vệ, nhấn **Bật loa trên máy này** ở đúng máy được chọn. Các viewer khác tiếp tục nhận bảng, không tự giành quyền loa. Lease là trạng thái trong một backend process, phù hợp cấu hình một worker đã chốt.
- Chưa hoàn tất ánh xạ/runtime hai camera trước/sau cùng cổng, capture/hiển thị thực sự độc lập AI, điều phối GPU và ghép hai góc. JPEG đã được nối vào loop, nhưng test này không chứng minh hình vẫn tiến khi AI bị chặn lâu.
- Frontend vẫn còn base URL localhost, localStorage/query token. Chưa hoàn thành same-origin/cookie-only, đối chiếu quyền với tài khoản hiện tại, session revocation, HTTPS và SPA production deep link. Test API dùng test app hiện có; không coi đó là kiểm chứng toàn app factory/lifespan production.
- Chưa có outbox/replay sau crash và resync WS đầy đủ; cập nhật bị bỏ cần đối chiếu lịch sử DB. Một encounter có thể gom nhiều row lịch sử; chưa hoàn tất upsert duy nhất ở DB cho toàn vòng đời event.
- Ledger đã trả conflict kể cả sau confirm; chuyển trạng thái các sự kiện đã lưu khi bằng chứng mới mâu thuẫn vẫn cần hoàn thiện cùng luồng event cập nhật, không được xem test ledger là nghiệm thu luồng này.
- Chưa đo OCR toàn biển, precision/recall, mirror, ghép hai camera, FPS/p95/RAM/VRAM, phát/tua clip trên trình duyệt thật hoặc ca 12 giờ. E3.1 kiểm kê/nhãn và E3.2 đánh giá model tiếp tục theo kế hoạch; gương và tự ghép chưa được nghiệm thu không được bật tự động.

## Đối chiếu và quay lại

Bản sao trước sửa của các tệp chính tại `C:\Users\khucv\AppData\Local\Temp\codex_pre_e3_backup_nddetd0m`, có manifest. Dùng để đối chiếu từng hunk với trạng thái hiện tại; chỉ áp dụng ngược phần của lượt Codex sau khi kiểm tra thay đổi mới của Cursor. Không reset toàn working tree hoặc khôi phục DB/media vận hành. Không tạo commit trong lượt này để tránh gom nhầm thay đổi đang có của người dùng.
