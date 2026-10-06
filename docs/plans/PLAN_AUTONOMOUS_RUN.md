# Kế hoạch cho Cursor tự chạy 6 tiếng: hoàn thiện Bước 8-13 + tự test + tự fix

## Context

Bước 1-7 của [docs/plans/TASKS_SPA_AUTH.md](docs/plans/TASKS_SPA_AUTH.md) đã xong và commit (`b26ad45`) — backend đã có auth JWT, CRUD xe/vi phạm/thống kê dạng JSON, bảo vệ video/WS bằng token, CORS. Còn lại **Bước 8-13 (toàn bộ frontend React)** chưa làm.

Từ giờ trở đi, thay vì tôi giao từng prompt và bạn tự test bằng mắt/tai sau mỗi bước (cách đã làm từ đầu dự án), bạn muốn Cursor **tự chạy liên tục 6 tiếng**: tự code, tự test, tự phát hiện lỗi, tự sửa, tự sang bước kế — không cần bạn ngồi canh từng bước.

**Giới hạn thật cần biết trước khi giao việc này**: một số thứ **không thể tự động test được nếu không có người xem/nghe thật** — video có đúng là hình ảnh thật từ camera không, tiếng beep có nghe được không, giao diện có "đẹp/hiện đại" theo con mắt bạn không. Cursor không có mắt/tai. Cách xử lý: Cursor tự test được **mọi thứ có thể kiểm tra bằng code** (API trả đúng status/dữ liệu, DOM có đúng phần tử, WebSocket nhận đúng message, ảnh MJPEG có byte thật không), còn phần cần mắt/tai thật thì Cursor **phải ghi rõ "CẦN BẠN TỰ KIỂM TRA"** vào file log thay vì tự nhận là "xong" — bạn đọc log sau 6 tiếng rồi tự kiểm tra riêng phần đó.

## Chuẩn bị: thêm hạ tầng tự test (làm trước Bước 8)

Dự án hiện chưa có test nào (`pytest`, `playwright` đều chưa cài). Cursor cần tự thiết lập trước khi làm tiếp:

1. **Backend test**: `pytest` + `httpx` (TestClient của FastAPI) — test API mà không cần server đang chạy thật, không cần camera thật (pipeline đã xác nhận không crash app nếu không mở được camera — chỉ log lỗi và dừng thread nền, các route khác vẫn hoạt động bình thường).
2. **Frontend E2E test**: `Playwright` (`npm install -D @playwright/test`, `npx playwright install chromium`) — chạy trình duyệt headless thật, tự động điền form đăng nhập, click, kiểm tra DOM/URL/network request, chụp screenshot lưu lại để bạn xem sau.
3. **Endpoint test-only để giả lập vi phạm** (quan trọng — không có endpoint này thì không thể tự test được banner cảnh báo + tiếng beep vì cần camera thật phát hiện vi phạm): thêm `POST /api/dev/trigger-test-alert` (không cần role, hoặc role bất kỳ đã login) — chỉ đẩy 1 dict giả `{"type": "violation", "violation_type": "NO_HELMET", "plate_read": "TEST123", "timestamp": ...}` thẳng vào `alert_queue` có sẵn của pipeline (dùng lại queue đã có, không viết logic mới). Ghi rõ trong code đây là endpoint **chỉ dùng để test tự động**, cân nhắc xóa hoặc chặn role admin trước khi triển khai thật cho trường.

## Quy tắc bắt buộc khi chạy tự động (đọc kỹ trước khi bắt đầu)

- **Test xong mới commit, commit xong mới sang bước kế** — mỗi bước trong Bước 8-13 là 1 commit riêng, message rõ ràng. Không gộp nhiều bước vào 1 commit — nếu có gì sai sau này, dễ `git revert`/`git bisect`.
- **Không đụng vào**: `app/cv/*` (pipeline, detector, capture, ocr — logic CV đã hoạt động đúng, không phải phạm vi lần này), `app/config.py` phần `CAMERA_INDEX`/model paths (đã cấu hình đúng theo phần cứng thật của người dùng, đụng vào có thể làm hỏng setup OBS đã mất công cấu hình), `data/app.db` (không xóa/reset — có dữ liệu thật), không `git push` (chỉ commit local).
- **Ghi log liên tục** vào file `docs/handover/CURSOR_RUN_LOG.md` (tạo mới nếu chưa có) — sau MỖI bước, append 1 mục: bước nào, đã làm gì, đã tự test gì (và kết quả), có gì cần người xác nhận thủ công (đánh dấu rõ **[CẦN NGƯỜI KIỂM TRA]**), có blocker gì không. Đây là cách duy nhất tôi và bạn biết chuyện gì đã xảy ra trong 6 tiếng đó.
- **Time-box mỗi bước**: nếu 1 bước bị kẹt (ví dụ lỗi cài đặt, dependency conflict) quá khoảng 30-45 phút thử các cách khác nhau mà không ra, ghi rõ blocker vào log kèm đã thử gì, rồi **chuyển sang bước độc lập tiếp theo** thay vì đứng im hết 6 tiếng ở 1 chỗ. Không tự ý "sáng tạo" giải pháp khác xa với docs/plans/PLAN_SPA_AUTH.md nếu bị kẹt — ghi lại và đi tiếp.
- **Nếu xong cả Bước 8-13 mà vẫn còn thời gian trong 6 tiếng**: chuyển sang danh sách "việc thêm nếu còn giờ" ở cuối file này — KHÔNG tự ý bắt đầu làm 50cc/khuôn mặt/dắt xe (những tính năng đó cần quyết định thêm từ người dùng, không nằm trong phạm vi tự động này).

## Bước 8-13, có kèm cách tự test cụ thể

**Bước 8 — Scaffold `frontend/` + Login thật**
- Tự test: Playwright mở `http://localhost:5173/login`, điền username/password của user đã seed (dùng lại user tạo ở Bước 1, hoặc tự seed thêm nếu cần), submit, assert `localStorage` có `token`, assert có điều hướng xảy ra (URL đổi).
- Assert thêm: submit sai mật khẩu → assert có thông báo lỗi hiện trên trang (không phải crash trắng trang).

**Bước 9 — `GuardPage` + `AlertBanner`**
- Tự test: login role `security`, vào `/guard`, assert thẻ `<img>` tồn tại và **`naturalWidth > 0`** sau khi load (chứng minh nhận được byte ảnh thật từ MJPEG stream, dù nội dung ảnh là gì).
- Gọi `POST /api/dev/trigger-test-alert` (đã thêm ở phần Chuẩn bị) trong lúc Playwright đang mở `/guard`, assert banner đỏ xuất hiện trong DOM với đúng `violation_type` vừa gửi.
- **[CẦN NGƯỜI KIỂM TRA]**: tiếng beep có phát ra thật và nghe rõ không — Playwright không nghe được, chỉ assert được là code gọi `AudioContext`/`oscillator.start()` không lỗi (check console error), không assert được âm lượng/chất lượng âm thanh.
- Login role `management`, thử vào `/guard` bằng URL trực tiếp, assert bị redirect đi (không thấy `<img>` video).

**Bước 10 — `AdminVehiclesPage` + `AdminViolationsPage`**
- Tự test: login `admin`, Playwright tự thêm 1 xe test qua form, assert xuất hiện trong bảng ngay; sửa xe đó, assert bảng cập nhật; xóa, assert biến mất. Dọn dẹp: xóa xe test này khỏi DB thật sau khi test xong (đừng để rác trong `registered_vehicles`).
- Vào trang violations, assert bảng render, nếu có `snapshot_url` thì assert request tới URL đó trả về status 200 (ảnh thật tồn tại).
- Login `security`/`management`, thử vào `/admin/vehicles` bằng URL trực tiếp, assert bị chặn.

**Bước 11 — `DashboardPage`**
- Tự test: login `management`, vào `/dashboard`, gọi song song `GET /api/stats/summary` bằng httpx, assert số hiện trên giao diện (đọc DOM text) khớp với số trả về từ API — không chỉ assert "có hiện số" mà phải đúng số.
- **[CẦN NGƯỜI KIỂM TRA]**: biểu đồ có hiển thị đẹp/đúng tỷ lệ trực quan không — Playwright assert được là SVG/canvas của recharts tồn tại trong DOM, không đánh giá được tính thẩm mỹ.

**Bước 12 — Xóa Jinja cũ**
- Tự test: sau khi xóa, gọi `GET /admin` và `GET /guard` (URL HTML cũ) bằng httpx, assert trả về 404 (đã xóa route). Chạy lại toàn bộ test Playwright của Bước 8-11 để đảm bảo React app không bị ảnh hưởng gì (không phụ thuộc ngầm vào template cũ).

**Bước 13 — Build production + SPA fallback**
- Tự test: `npm run build`, tắt hẳn `vite dev` (dừng process), chỉ chạy `uvicorn`, chạy lại TOÀN BỘ bộ Playwright test ở trên nhưng trỏ vào `http://localhost:8000` thay vì `:5173` — nếu tất cả pass nghĩa là bản production hoạt động đúng y hệt bản dev.
- Test riêng: gọi trực tiếp `GET http://localhost:8000/admin/vehicles` (route con của SPA, không phải file thật) bằng httpx, assert trả về nội dung `index.html` (không phải 404) — xác nhận SPA fallback hoạt động.

## Việc thêm nếu còn giờ (sau khi xong hết Bước 8-13)

Theo thứ tự ưu tiên, dừng bất cứ lúc nào hết giờ:
1. Viết thêm test case cho các trường hợp lỗi: thêm xe với biển số trùng (assert 409, không phải 500), gọi API không có token (assert 401 rõ ràng ở mọi endpoint cần auth), token hết hạn/sai format.
2. Thêm loading state (spinner/skeleton) cho các trang khi đang gọi API — hiện tại có thể đang trắng trang khi chờ load, kiểm tra và thêm nếu thiếu.
3. Thêm thông báo lỗi rõ ràng ở frontend khi API lỗi (hiện tại kiểm tra xem có "nuốt lỗi" im lặng ở đâu không).
4. Cập nhật `README.md` với hướng dẫn chạy cả backend + frontend (dev và production), danh sách route mới, cách seed user.
5. Xóa endpoint test-only `POST /api/dev/trigger-test-alert` HOẶC thêm `require_role("admin")` vào nó nếu quyết định giữ lại — ghi rõ quyết định vào `docs/handover/CURSOR_RUN_LOG.md`.

**KHÔNG làm** (ngoài phạm vi, cần người quyết định trước): 50cc classification, nhận diện khuôn mặt, phát hiện dắt xe, đổi model CV, đổi cấu hình camera/OBS.
