# Review Task 2 — 2026-10-02

## Kết luận

**Task 2 chưa đủ điều kiện đóng.** Có cải tiến đã kiểm chứng, nhưng PASS trong acceptance report/checklist vượt quá bằng chứng và còn lỗi trên đường chạy thực. Đăng nhập tự điền tài khoản được giữ theo yêu cầu người dùng; các mục auth đã hoãn không phải yêu cầu phải hoàn thành trong lượt này.

Review này chỉ đọc mã và chạy kiểm tra trên dữ liệu tạm. Không sửa mã ứng dụng, không thay camera, không dùng DB/media vận hành, không stash thay đổi của task khác. Repository đang có thay đổi chưa commit; kết quả phản ánh snapshot lúc review, không tự xác định task nào gây ra mọi lỗi tích hợp.

## Kiểm chứng đã thực hiện

Interpreter: `D:\Work\Project_motorbike\venv\Scripts\python.exe`.

- Chạy cả tám file `test_task02_t2_*.py`: **64 passed**.
- Chạy thêm toàn bộ `test_maintenance_worker.py`, file bị loại khỏi regression của báo cáo: **12 passed**.
- Chạy thêm `test_system.py::test_cleanup_admin_ok`: **1 failed**, lỗi `ResponseValidationError` thiếu `deleted_files` và `updated_records`.
- Tổng lượt chạy cách ly: **76 passed, 1 failed, 1 warning, 26.80 giây**. Dùng DB/media/backup/recording tạm, tắt backup media trong môi trường test; không mở pipeline thật.
- Chạy `node --test test/*.test.mjs` tại frontend: **26/26 passed**.
- Probe cleanup dùng DB và file thật trong thư mục tạm: file `hold` và file ở ngoài media root đều bị xóa bởi route admin, mặc dù helper sau đó báo `held=1`.
- Probe backup worker trên dữ liệu tạm: mặc định chỉ tạo một file `app_*.db`, không có bộ media/manifest.
- Probe import: cùng CSV và `import_id`, lần đầu `created=1`, lần sau `created=0, duplicates=1`; không replay kết quả cũ.
- Probe export: không có cột ảnh, tên học sinh `=1+1` được xuất nguyên văn.
- Probe upload admin: bytes `not-an-image` với MIME `image/png` được chấp nhận và lưu.
- Probe production qua app thật, không chạy lifespan/camera/maintenance: `/admin/violations` trả **410**; `/api/khong-ton-tai` trả **200 HTML**. App mới từ `create_app()` trả **404** cho cả hai deep link admin/teacher vì SPA được gắn ngoài factory.

Không chạy lại toàn bộ backend, lint/build hoặc Playwright trong review này. Không đo 100.000 event, LAN hai máy, restore media thật hoặc RPO/RTO. Kết quả 761 passed/9 failed là báo cáo người dùng cung cấp, không phải lượt full regression mới của review này. Trong mã hiện tại có thay đổi Task 1 tiếp tục diễn ra; không tự suy rằng toàn bộ 9 lỗi còn nguyên hoặc đã hết.

## F01 — P1: Route dọn bằng chứng bỏ qua hold và media root

Vị trí: `app/api/system.py:340–356`, `app/db.py:1944–1966`.

Route lấy path cũ rồi tự `os.unlink()` trước khi gọi helper cleanup mới. Query lấy path không loại `evidence_state='hold'`; route chấp nhận path tuyệt đối mà không xác nhận thuộc media root. Helper an toàn chạy sau đó không thể phục hồi file đã bị route xóa.

**Bằng chứng:** probe tạo hai event cũ: một file trong snapshots có trạng thái hold, một file tuyệt đối nằm ngoài snapshots. Sau gọi route, cả hai file không tồn tại, nhưng kết quả vẫn có `held=1`.

**Cần sửa:** bỏ vòng xóa riêng của route; dùng một cơ chế cleanup chung kiểm tra hold/root và cập nhật DB theo kết quả thực. Thêm test qua HTTP cho hold, ngoài root, symlink, PermissionError và crop. Chạy trên bản sao, tuyệt đối không dùng chứng cứ thật để tái hiện.

## F02 — P1: Cleanup API lỗi hợp đồng response

Vị trí: `app/api/system.py:325–366`.

`CleanupResponse` yêu cầu `deleted_files`, `updated_records`, trong khi route trả `deleted/missing/failed/held/attempted/paths_failed`. Đây là lỗi response của ứng dụng; request có thể đã xóa file trước khi trả lỗi server.

**Bằng chứng:** `test_cleanup_admin_ok` thất bại với `ResponseValidationError` trong lượt review, cả khi DB không có file cần xóa.

**Cần sửa:** thống nhất schema, route, frontend và các caller của helper; duy trì trường tương thích nếu cần. Không chỉ thêm giá trị mặc định để che thiếu thống kê. Phải sửa cùng F01.

## F03 — P1: Deep link production và API 404 vẫn sai

Vị trí: `app/main.py:132–159`, `app/tests/conftest.py:19,81,136,195`.

`/admin/violations` còn bị route Jinja cũ trả 410. SPA fallback trả index.html cho API không tồn tại. SPA/assets/dev router được gắn ngoài `create_app()`, nên app factory và app triển khai không tương đương. Các test Task 2 dựng `FastAPI` riêng nên không phát hiện hai lỗi thực.

**Bằng chứng:** request production qua `app.main.app`: admin 410, teacher 200 HTML, API lạ 200 HTML. Qua `create_app()`: admin/teacher 404.

**Cần sửa:** đưa cấu hình route triển khai vào factory, loại 410 cho đường SPA hợp lệ, bảo vệ namespace API/guard khỏi fallback HTML. Test trên factory thật với startup phụ thuộc ngoài được thay thế; kiểm tra refresh admin/teacher và API JSON 404.

## F04 — P1: T2.8 mới có backup DB, chưa có bộ khôi phục hoàn chỉnh

Vị trí: `app/background.py:89–126,216–273`, `app/config.py:383–391`, `app/db.py:1710,1763`, `app/api/system.py:430–442`.

- Mặc định backup 24 giờ và media tắt. Lịch backup phụ thuộc vòng cleanup; đặt backup một giờ nhưng cleanup 24 giờ vẫn không chạy mỗi giờ.
- `compute_backup_manifest()` chỉ là helper cho một DB; không được worker/API backup gọi và lưu thành manifest của bộ dữ liệu.
- Media tùy chọn chỉ copy snapshots; ảnh hồ sơ ở thư mục sibling không được bao phủ. Không có complete marker của bộ DB + media, cơ chế phối hợp giữ file với cleanup hoặc kiểm chứng media theo DB snapshot.
- Dọn backup cũ chỉ xóa file DB; thư mục media tùy chọn không được dọn theo bộ.
- Test restore hiện copy file DB sang vị trí khác; chưa restore ảnh/crop/clip/hồ sơ và kiểm chứng chúng mở/phát được.

**Bằng chứng:** worker mặc định trên thư mục tạm chỉ tạo một `app_*.db`; các test T2.8 đạt không chứng minh các yêu cầu trên.

**Cần sửa:** backup theo bộ DB/media/manifest, marker hoàn tất sau kiểm chứng, lịch giờ độc lập, retention theo bộ và restore thử sang vị trí riêng. T2.8 phải ghi PARTIAL/PENDING cho tới khi cả mã và test hành vi đạt; RPO/RTO thiết bị thật vẫn cần đo riêng.

## F05 — P2: CSV chưa chống submit lặp; preview/export chưa đủ hợp đồng

Vị trí: `app/api/admin.py:255–270,353–371`.

`if import_id: pass` chưa lưu key/hash/kết quả. Replay cùng request trở thành một đợt import khác. Preview so biển đầu vào với DB trước chuẩn hóa và không loại trùng trong cùng CSV nên có thể dự báo sai số tạo mới. Export không có `photo_path`, chưa giữ đầy đủ hồ sơ qua round-trip. Các trường bắt đầu bằng ký hiệu công thức được ghi trực tiếp vào CSV.

**Bằng chứng:** cùng ID/CSV cho hai kết quả khác nhau; export không có cột ảnh và giữ nguyên `=1+1`. Test có tên round-trip hiện chỉ kiểm tra nội dung export, không nhập lại DB sạch và so toàn bộ hồ sơ.

**Cần sửa:** key idempotency lưu bền với hash payload, key cũ/payload khác bị từ chối; preview/confirm dùng cùng chuẩn hóa và quy tắc trùng; kiểm chứng export→import DB sạch đủ trường; xử lý công thức theo hợp đồng xuất bảng tính.

## F06 — P2: Upload admin chưa kiểm tra ảnh thật hoặc giới hạn đọc

Vị trí: `app/api/admin.py:757–779`; nhánh public tương tự ở `app/api/register.py:43–64`.

Upload admin chỉ tin MIME, đọc toàn bộ file, dùng tên timestamp và giữ đuôi do client gửi. Không decode ảnh, giới hạn kích thước file/ảnh giải nén hay UUID như kế hoạch. Public đăng ký đã tắt mặc định là điểm tốt, nhưng bật cờ chưa làm upload trở nên đủ kiểm chứng.

**Bằng chứng:** endpoint upload admin chấp nhận bytes không phải ảnh dưới MIME `image/png` và trả đường dẫn `/media/student_photos/...`, đường dẫn không dùng được với static media đã tắt ở production.

**Cần sửa:** decode thực, giới hạn bytes/pixels, tên UUID/định dạng xác định và URL media có kiểm tra quyền; test tệp giả, quá lớn, cùng thời điểm và ảnh hiển thị thực ở production.

## F07 — P2: CI E2E còn cấu hình sai và chưa có bằng chứng browser đạt

Vị trí: `.github/workflows/ci.yml` bước Start backend/Start frontend preview; `frontend/vite.config.js`, `frontend/playwright.config.js`.

Đã bỏ cho phép test E2E thất bại là cải tiến đúng. Tuy nhiên backend CI mở 8000 trong khi proxy khai báo 8001; chưa có cấu hình mock CV/maintenance/DB/media theo kế hoạch. Readiness dùng curl không kiểm status, có thể nhận 401/500 mà bước vẫn thành công. Production smoke chỉ kiểm import secret, không kiểm route production. Playwright chưa chạy trong báo cáo.

**Cần sửa:** đồng bộ cổng/proxy, startup QA cách ly qua factory thật, readiness kiểm status/nội dung có deadline, browser kiểm login/media/Range/deep link và fail CI khi chúng lỗi. Đo riêng performance 100.000 event/ba client; chưa có số đo thì ghi PENDING.

## F08 — P2: Acceptance report/checklist đánh dấu vượt bằng chứng

Vị trí: `tasks/task-02/ACCEPTANCE_REPORT.md`, `tasks/task-02/todo.md`.

T2.2, T2.7, T2.8, T2.9/Checkpoint được đánh PASS dù production deep link/cleanup lỗi, backup bộ dữ liệu chưa hoàn thành, browser/performance chưa chạy và regression có lỗi. Bộ test loại `test_maintenance_worker.py` không phải full suite. Review chạy file này độc lập cùng các test Task 2 và thấy 12/12 đạt; cần bỏ việc loại test hoặc ghi rõ nguyên nhân lỗi thứ tự khi chạy chung.

Không thể coi 9 lỗi đều vô hại chỉ từ suy đoán hoặc stash nhiều file dùng chung. Lỗi cleanup response là lỗi API thực. Đề xuất thêm `run_generation` không giải thích tự động mọi `AttributeError`; phải dùng traceback và kiểm tra mã hiện tại. Không sửa test thành chấp nhận hành vi sai để đạt xanh.

## Các phần tốt đã kiểm chứng

- Nút tự điền teacher và seed lớp demo có trong mã; 9 test teacher đạt. Giữ cách đăng nhập người dùng đã chọn.
- API client dùng URL tương đối; list/detail violation trả URL media API.
- Có API detail xe, hồ sơ mở rộng và test lịch sử/phân trang cơ bản.
- Có kiểm thử provenance/version/đổi trạng thái; đăng ký public mặc định tắt.
- Helper cleanup có xử lý hold/root/lỗi; cần route sử dụng đúng helper này.
- SQLite Backup API và checksum DB có test thật; cần mở rộng thành bộ khôi phục đầy đủ.
- Node tests và test maintenance đều đạt trong lượt cách ly.

## Thứ tự sửa và đóng Task 2

1. F01 + F02: cleanup HTTP an toàn và hợp đồng response.
2. F03: factory/deep link/API fallback; test app production thực.
3. F04: backup bộ dữ liệu, lịch, retention, restore.
4. F05 + F06: CSV/upload và ảnh hồ sơ production.
5. F07: CI/browser/performance, rồi full regression tích hợp gồm maintenance.
6. F08: cập nhật trạng thái theo bằng chứng; giữ LAN thật/RPO/RTO/Playwright chưa đo ở PENDING.

Các lỗi tích hợp với Task 1 phải phối hợp ownership; không sửa chồng file dùng chung hoặc stash thay đổi của các phiên đang chạy. Không đổi chiến lược đăng nhập trong đợt vá này. Chỉ đóng Task 2 sau khi mã/test/production smoke đạt các tiêu chí được giao và các phần thiết bị chưa nghiệm thu được nêu rõ.
