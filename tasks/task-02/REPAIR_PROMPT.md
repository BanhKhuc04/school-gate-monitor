# Prompt tiếp tục TASK 2 — vá lỗi thực, kiểm thử tích hợp và đính chính nghiệm thu

Bạn tiếp tục **TASK 2 của School Gate Monitor** trong repository `D:\Work\Project_motorbike`. Đây là yêu cầu **thực thi sửa mã và kiểm chứng đến khi hoàn thành phần có thể làm**, không chỉ đọc, đề xuất hay viết báo cáo.

## 1. Đọc hiện trạng và giữ phạm vi

Đọc trước:

- `D:\Work\Project_motorbike\docs\CODEX_TASK02_REVIEW_2026_10_02.md`.
- `D:\Work\Project_motorbike\tasks\task-02\plan.md`.
- `D:\Work\Project_motorbike\tasks\task-02\OWNERSHIP.md` và `CONTRACTS.md`.
- `D:\Work\Project_motorbike\tasks\task-02\EXECUTION_LOG.md`, `ACCEPTANCE_REPORT.md`, `DEFERRED_AUTH.md`.
- Prompt vá Task 1 tại `D:\Work\Project_motorbike\tasks\task-01\REPAIR_AND_VIDEO_TEST_PROMPT.md`, nếu có, để biết ranh giới tích hợp.

Review Codex đã xác nhận 64 test riêng Task 2 đạt, 12 test maintenance đạt, 26 test Node đạt, nhưng API cleanup lỗi thật; production deep link/404 sai; backup bộ dữ liệu, CSV/upload và CI còn thiếu. Phải xác minh lại trên mã hiện tại vì các task đang tiếp tục sửa. Mục nào đã được sửa và test hành vi đạt thì giữ lại, không triển khai lại.

Ghi commit, git status, interpreter/dependency và diff các file chuẩn bị sửa. Không log secret, RTSP credentials hoặc dữ liệu học sinh thật.

**Giữ nguyên lựa chọn đăng nhập:** nút tự điền admin/bảo vệ/quản lý và nút giáo viên ở dưới; vẫn gọi API login thực. Không chuyển cookie-only, đổi JWT/session strategy, xóa localStorage hoặc triển khai các mục DEFERRED_AUTH. Không ghi đè mật khẩu/tài khoản đang dùng. Seed demo chỉ dùng DB giả/dev được chỉ định.

**Phối hợp nhiều task:**

- Không sửa CV runtime, detector/OCR/tracker, luồng Guard/loa hoặc training của Task 1.
- `app/api/system.py`, `app/db.py`, `app/main.py`, `app/config.py`, schema, fixture chung và proxy có thể là file dùng chung. Đọc ownership hiện tại, ghi rõ phần cần sửa và tránh hai phiên ghi đồng thời.
- Nếu file đang được task khác sửa, hoàn thành patch/test cụ thể trong `tasks/task-02/integration/` kèm tiêu chí và ghi PENDING_INTEGRATION; tiếp tục phần độc lập. Sau khi có quyền tích hợp, áp dụng tuần tự và chạy lại test. Patch chưa tích hợp không được đánh COMPLETE.
- Không stash/reset/clean để chứng minh lỗi thuộc task khác; không commit toàn bộ working tree, push hoặc deploy. Đừng sửa lỗi Task 1 bằng suy đoán thêm `run_generation`; dùng traceback hiện tại và bàn giao đúng owner.

## 2. R0 — Baseline an toàn

Tạo cấu hình QA riêng: DB tạm, media/ảnh hồ sơ/backup/recording tạm, API và frontend cổng riêng. Không dùng DB/media/camera vận hành. Test không mở RTSP, không tải trọng số hoặc chạy model thật; mọi startup phụ thuộc ngoài được thay thế có kiểm soát.

Chạy baseline các test Task 2, maintenance, cleanup API, Node. Lưu danh sách PASS/FAIL/SKIP và traceback gốc. Phân biệt lỗi đã có và lỗi sau sửa; không loại test khó rồi gọi kết quả là full suite.

Đính chính checklist/report cũ: T2.2/T2.7/T2.8/T2.9 và các checkpoint chưa đủ bằng chứng phải về PARTIAL/FAIL/PENDING tương ứng, giữ lịch sử báo cáo. Tạo `tasks/task-02/REPAIR_TODO.md` theo các đợt dưới đây, cập nhật khi đã kiểm chứng.

## 3. R1 — Cleanup an toàn từ API đến file và DB

**Lỗi đã tái hiện:** route admin tự xóa file trước helper an toàn, làm mất file `hold` và file ngoài media root; response model lại yêu cầu `deleted_files/updated_records` nhưng route trả keys khác.

Thực hiện:

1. Bỏ vòng unlink riêng trong route. API và worker dùng một cơ chế cleanup kiểm tra retention/hold/root trước mọi thao tác xóa.
2. Giữ file hold, file đang ghi/upload/backup và chứng cứ chưa hết hạn. Xử lý snapshot, crop, clip theo kết quả từng file; lỗi xóa giữ liên kết DB để retry.
3. Chuẩn hóa path lịch sử có thư mục con; không dùng basename làm mất vị trí thật hoặc ghép nhầm file. Validate resolved path nằm trong đúng root; symlink ngoài root không được xóa. Path không đọc được không mặc nhiên coi là missing.
4. Đồng bộ response schema, endpoint, worker, UI và thống kê. Nếu giữ keys cũ để tương thích, chúng phải có nghĩa rõ và số liệu thực; không mặc định 0 để che lỗi. Response thể hiện partial failure.
5. Batch/thời hạn hữu hạn; không giữ writer lock suốt quét và xóa lượng lớn file. Thiết kế vẫn phải bảo vệ event đang ghi hoặc chuyển sang hold, không chỉ bỏ lock.

**Test bắt buộc qua HTTP và worker:** hold, file tuyệt đối ngoài root, symlink ngoài root, thư mục con, crop-only, PermissionError, lỗi resolve, mất file, partial failure, chạy lại và dry-run. Test response 200 đúng schema; file bị cấm xóa còn nguyên, DB phản ánh đúng việc đã làm. Dùng file tạm thật.

**Đạt:** cleanup không xóa chứng cứ phải giữ, không xóa ngoài root, không mất link do lỗi ghi/xóa và không trả server error sau khi đã làm việc.

## 4. R2 — App factory, production deep link và media thật

**Lỗi đã tái hiện:** app triển khai trả 410 ở `/admin/violations`, API không tồn tại trả 200 HTML; `create_app()` thiếu phần SPA/assets được gắn ngoài factory. Fixture Task 2 dựng app khác nên không thấy lỗi.

Thực hiện:

1. Đưa routers/middleware/assets/SPA fallback cần triển khai vào factory thống nhất. App global và app tạo mới cùng hợp đồng; không nhân đôi startup hay routers.
2. Loại route 410 chặn trang React hợp lệ. Deep link admin/teacher phải tải index.html khi đã có frontend build. `/api/...` và namespace backend không tồn tại trả lỗi JSON đúng HTTP status, không rơi vào SPA. Asset không tồn tại không được trả index.html giả.
3. Cho integration test dùng factory thật với dependency startup QA tắt/thay camera/model/maintenance. Không biến QA bypass thành mặc định trong production.
4. Giữ URL cùng origin cho API/media. Kiểm tra URL ảnh hồ sơ ở list/detail/upload; ảnh và clip hoạt động với phiên đăng nhập hiện tại. Không thay auth strategy để xử lý lỗi đường dẫn.
5. Quyền giáo viên đồng nhất giữa list/detail/history/report/export/media. Giáo viên thiếu lớp bị từ chối; kiểm tra media lịch sử, ảnh hồ sơ và scope qua quan hệ DB, không đoán lớp bằng tên file.

**Test:** production factory thật; refresh `/admin/violations`, `/admin/vehicles`, `/teacher/violations`; API JSON404; guest và teacher đúng/khác/thiếu lớp. Dùng ảnh decode được và MP4 phát/tua được. Range kiểm status, Content-Range, bytes đúng và browser tua video; JPEG marker hoặc file `.bin` không chứng minh ảnh/clip hoạt động.

**Đạt:** deep link 200 HTML đúng trang, API404 JSON, ảnh thực hiển thị và clip phát/tua đúng quyền trong browser.

## 5. R3 — Backup theo bộ và restore thực trên dữ liệu giả

Chia thành các bước nhỏ, kiểm chứng từng bước:

### R3.1 — Tạo bộ backup

- Giữ SQLite Backup API. Lấy DB snapshot, xác định media được DB snapshot tham chiếu: snapshot/crop/clip/ảnh hồ sơ và quan sát camera có liên quan.
- Tạo thư mục backup riêng bằng định danh không trùng, DB và manifest/version chứa file tương đối, size/hash, missing/error.
- Phối hợp cleanup giữ các file được bộ backup đang tạo tham chiếu. Không tự bỏ qua ảnh hồ sơ nằm ngoài snapshots.
- Chỉ ghi marker complete bằng thao tác atomic sau integrity_check DB và kiểm chứng media bắt buộc. Bộ lỗi/đang tạo không xuất hiện như bản mới nhất có thể restore.
- Đo thời gian writer lock; tránh giữ lock suốt copy DB/media lớn mà vẫn chứng minh consistency.

### R3.2 — Lịch và retention

- Lịch backup giờ độc lập cleanup; cleanup24h và backup1h vẫn backup mỗi giờ. Có thao tác cuối ca phù hợp cơ chế ca hiện có.
- Giữ 24 mốc theo giờ và 14 mốc cuối ca theo kế hoạch nếu đủ dung lượng; dọn theo toàn bộ bộ backup. Không bỏ lại media directory vô hạn và không xóa blob còn được bộ giữ lại tham chiếu.
- Copy media tăng dần nếu phù hợp; không thêm kiến trúc lớn khi cách đơn giản đã đáp ứng.
- Thiếu dung lượng/lỗi copy phải có trạng thái lỗi rõ; không xóa bằng chứng còn hạn để làm báo cáo xanh.

### R3.3 — Restore và hướng dẫn

- Restore vào DB/media root mới, không ghi đè dữ liệu vận hành. Đường dẫn phục hồi không phụ thuộc root máy cũ.
- Verify hash, integrity, quan hệ và tài khoản/cấu hình; mở ảnh hồ sơ/snapshot/crop, phát/tua clip sau restore.
- Có lệnh/hướng dẫn backup, verify, restore và dọn bộ cũ. Thử đầy đĩa/copy lỗi/crash giữa chừng bằng fault injection.

**Đạt:** bộ backup hoàn chỉnh được restore sang nơi khác và media mở được; backup lỗi không có complete marker; retention không làm hỏng bộ còn giữ. Test DB copy riêng lẻ không đủ. RPO1h/RTO30phút trên dữ liệu thật vẫn ghi PENDING nếu chưa đo; ghi số đo trên bộ giả riêng.

## 6. R4 — CSV preview/confirm/replay và export không mất dữ liệu

1. Thay `if import_id: pass` bằng idempotency lưu bền: key + payload hash + kết quả. Replay cùng key/payload trả kết quả đã lưu; key cũ/payload khác trả 409. Xử lý hai request đồng thời và retry sau mất kết nối theo contract, không gọi lại tạo batch mới.
2. Preview và confirm dùng cùng chuẩn hóa biển, validation và phát hiện trùng trong DB/cùng file. Count skipped là số dòng, không phải số lỗi của dòng. Ngày sinh phải là ngày hợp lệ.
3. Giới hạn bytes trước khi đọc toàn bộ file lớn, giới hạn số dòng. Trả lỗi từng dòng rõ cho BOM, quoted newline, malformed CSV, thiếu cột và trùng.
4. Export giữ đầy đủ trường hồ sơ theo contract, gồm tham chiếu ảnh. Xử lý công thức bảng tính và thống nhất cách nhập lại để round-trip không thay đổi nội dung hợp lệ.
5. Frontend có preview, confirm, pending/error, chống submit lặp; cùng import key được giữ khi retry.

**Test:** export → import DB sạch → so toàn bộ hồ sơ, Unicode, ảnh, ngày sinh, điện thoại; biển khác cách viết; hai dòng trùng; một dòng nhiều lỗi; cùng key cùng/khác file; concurrent submit và restart; tên bắt đầu bằng ký hiệu công thức. Test không chỉ tìm cột trong export.

## 7. R5 — Upload ảnh thật và vòng đời ảnh hồ sơ

- Admin/public upload dùng kiểm tra ảnh thật chung khi phù hợp; public đăng ký vẫn tắt mặc định.
- Đọc giới hạn 5MB + sentinel, giới hạn pixel/kích thước giải nén, decode thực và lỗi 4xx rõ. Không tin MIME/đuôi file do client gửi.
- Lưu định dạng được phép với UUID; không tên millisecond có thể trùng. Bỏ metadata không cần thiết, kiểm tra quyền/tham chiếu khi gắn ảnh vào hồ sơ.
- Trả URL media dùng được ở production theo quyền hiện tại; không trả `/media/...` khi production đã tắt static.
- Dọn upload bỏ dở theo thời hạn và trạng thái, giữ ảnh đã gắn bản ghi; không sửa/xóa dữ liệu cũ hàng loạt.

**Test:** ảnh PNG/JPEG thật, bytes giả dưới MIME ảnh, quá5MB, ảnh giải nén quá lớn, hai upload đồng thời, traversal/đuôi lạ, lỗi ghi, gắn ảnh/cleanup và browser hiển thị production. Giữ public registration off; không mở lại để demo test.

## 8. R6 — CI, browser và performance

- Đồng bộ backend port/proxy/baseURL trong QA và CI. Không backend8000/proxy8001. Vite preview phải được kiểm tra routing thực, không suy từ devserver.
- Readiness có deadline và kiểm HTTP status/nội dung mong đợi với auth nếu endpoint yêu cầu; `curl -s` nhận401/500 không phải healthy.
- E2E dùng factory triển khai thật với DB/media/demo accounts riêng và CV/maintenance giả. Không mở model/camera thật hoặc dùng dữ liệu vận hành.
- Pytest/Node/lint/build/Playwright/production smoke là check bắt buộc: không `|| true`, `continue-on-error`, deselect hay ignore để che lỗi. Cleanup tiến trình best-effort được phép.
- Nếu dùng xdist, DB/media/ports mỗi worker phải cách ly và kết quả không phụ thuộc thứ tự; nếu chưa chứng minh, dùng runner tuần tự ổn định thay vì quảng bá parallel xanh.
- Đo list/detail/report với 100.000 event giả, ba client: p50/p95, query plan/index và môi trường. Mục tiêu list/detail p95 <=500ms. Không chỉ đánh PASS vì có file workflow; không đo thiếu rồi coi đã đạt.

**Browser flows:** login tự điền bốn vai trò; teacher đúng/khác/thiếu lớp; list/filter/pagination/detail lịch sử ngoài200 dòng; xử lý trạng thái concurrent409; ảnh/clip; CSV preview/confirm/retry; upload; backup/restore UI hoặc lệnh được giao; refresh deep link và API404.

Nếu trình duyệt QA chưa hoạt động, kiểm tra runner/browser sẵn có và khắc phục trong phạm vi dev. Chưa chạy được thì ghi PENDING_BROWSER, tiếp tục phần độc lập; không đóng T2.9.

## 9. R7 — Full regression và kiểm tra tích hợp với Task 1

Dùng interpreter cố định. Chạy toàn bộ backend **gồm maintenance**, không loại file hoặc test guard/pipeline chỉ vì nặng; sửa fixture để không load model/camera trong unit/integration test.

Lệnh chuẩn tại root:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
```

Tại `D:\Work\Project_motorbike\frontend`:

```powershell
node --test test/*.test.mjs
npm run lint
npm run build
npm run test:e2e
```

Chỉ chạy khi đã xác nhận fixture/cấu hình chuyển toàn bộ DB/media/backup sang nơi tạm. Nếu cần launcher QA riêng, lưu launcher và lệnh thực đầy đủ, không chỉ ghi lệnh chuẩn trong báo cáo.

- Chạy focused tests sau mỗi bước, regression chung tại checkpoint R1–R2, R3–R5 và R6–R7.
- Full suite trong fresh process sau tích hợp; kiểm tra chạy riêng/chung và thứ tự nếu phát hiện pollution.
- Với các lỗi Task 1 còn lại, ghi exact traceback, current code, owner và test cần rerun; hoàn thành phần Task 2 độc lập. Không sửa CV vượt scope hoặc báo green khi regression vẫn đỏ.
- Video/training/GPU và nghiệm thu Imou do Task 1 phụ trách. Task 2 không chạy thêm workload GPU trong lúc Task 1 benchmark/training. Ghi dependency và đối chiếu kết quả tích hợp, không dùng test admin để tuyên bố FPS/nhận diện đạt.

## 10. Tài liệu và quy tắc hoàn thành

Cập nhật trong thư mục Task 2:

- `REPAIR_TODO.md`: R0–R7 và từng test/điều kiện, PASS/FAIL/PENDING.
- `EXECUTION_LOG.md`: lỗi tái hiện, patch, test/lệnh/môi trường, trước/sau, rollback, dependency.
- `ACCEPTANCE_REPORT.md`: đính chính PASS cũ; phân biệt mã đã viết, test hành vi, production/browser, phép đo, LAN/restore thật.
- `integration/`: patch cụ thể cho file đang do task khác giữ, trạng thái đã/chưa tích hợp.

Không xóa lịch sử. Auth deferred giữ theo yêu cầu người dùng, không đổi thành lỗi bắt buộc sửa; LAN thật/RPO/RTO thật chưa đo phải ghi riêng. Không sửa tài liệu chung của Task 1 khi chưa được phân ownership.

**Cách làm:** bắt đầu sửa ngay sau baseline, tiếp tục tự chuyển đợt; không kết thúc lượt bằng “sẽ đọc”, “muốn tôi tiếp tục không” hoặc chỉ nêu đề xuất. Checkpoint là điểm kiểm chứng, không phải yêu cầu người dùng duyệt lại. Khi thiếu thiết bị hoặc chờ file dùng chung, ghi đúng blocker và tiếp tục phần độc lập. Không coi hết thời gian một lượt hay test riêng xanh là hoàn thành.

**Chỉ đóng phần sửa Task 2 khi:** F01–F08 đã được xử lý hoặc ghi dependency chưa tích hợp rõ; các tiêu chí phần được giao có bằng chứng; full regression bắt buộc không còn lỗi chưa giải thích và browser/production đã kiểm chứng. Nếu còn pending thì báo PARTIAL, không ghi “T2.0–T2.9 hoàn thành đầy đủ”.
