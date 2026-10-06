# TASK 2 — Sửa admin, dữ liệu, media, backup và kiểm chứng vận hành

Ngày bàn giao: 02/10/2026. Prompt thực thi dành cho Cursor tại `D:/Work/Project_motorbike`.

## 1. Nhiệm vụ và quyết định của người dùng

Tiếp tục sửa các điểm yếu ngoài TASK 1 của School Gate Monitor. Đọc mã hiện tại trước mỗi đợt, tái hiện lỗi rồi sửa từng luồng hoàn chỉnh từ giao diện đến API và DB. Giữ FastAPI, React và SQLite; không refactor toàn bộ hoặc đổi framework.

**Yêu cầu đăng nhập đã chốt:**

- Chưa thay cơ chế đăng nhập/JWT/Bearer/cookie/localStorage trong task này. Giữ giao diện đăng nhập hiện có và ba nút demo Quản trị viên, Bảo vệ, Ban giám hiệu.
- Bấm nút demo chỉ tự điền tài khoản và mật khẩu; người dùng vẫn bấm Đăng nhập và server vẫn xác thực bình thường. Không giả lập đăng nhập hoặc gán quyền ở frontend.
- Thêm nút **Giáo viên** ở hàng bên dưới ba nút hiện có. Tài khoản demo đề xuất `teacher` / `teacher123`, role `teacher`, lớp demo mặc định `10A1`, có thể cấu hình lớp khi seed. Đây là credential demo, không phải credential camera hay tài khoản thật.
- Sửa điều hướng giáo viên đến `/teacher/violations`; giữ màn hình xe và lịch sử trong phạm vi lớp. Không đưa giáo viên vào trang admin, cấu hình camera hoặc quản lý tài khoản.
- Những lỗi thu hồi JWT cũ, chuyển toàn bộ browser sang cookie-only, bỏ token khỏi localStorage/URL, rate limit đăng nhập và hardening phiên **được hoãn theo yêu cầu người dùng**, phải ghi rõ còn tồn tại. Không ghi Task 2 đã đạt nghiệm thu bảo mật đầy đủ.
- Sửa cùng origin/LAN cho API và media vẫn thuộc Task 2: đây là sửa kết nối, không thay phương thức đăng nhập. Giữ Bearer interceptor và cookie hiện có khi chuyển URL.

**Kết quả cần có:** admin lưu đúng hồ sơ; lịch sử và báo cáo đúng; ảnh/clip đúng quyền xem được; import/export đáng tin cậy; cleanup không làm mất liên kết giả; backup có thể restore cả DB và bằng chứng; CI không che lỗi; demo giáo viên dùng được.

## 2. Làm song song với Task 1, không sửa chồng

Đọc `tasks/task-01/plan.md`, `OWNERSHIP.md`, `CONTRACTS.md` nếu đã có. Ghi phạm vi thực tế vào `tasks/task-02/OWNERSHIP.md` trước khi sửa. Tài liệu ownership chỉ là thỏa thuận, không phải khóa tự động.

### 2.1. Task 2 được sửa khi chưa có task khác nhận file

- `app/api/admin.py`, `app/api/register.py`, `app/api/media.py`, `app/api/users.py`, `app/background.py`.
- Các trang Login, AdminVehicles, StudentViolationHistory, AdminRoster, AdminUsers, AdminViolations, PublicRegister, Dashboard.
- `frontend/src/api/client.js`, `frontend/vite.config.js`; trong AuthContext chỉ thay đổi tối thiểu để giữ `homeroom_class` trả từ login nếu cần, không đổi cách lưu/xác thực token.
- `frontend/src/App.jsx`, Sidebar, RequireRole: chỉ điều hướng và phân quyền hiển thị admin/giáo viên; giữ nguyên các route/thành phần giám sát Task 1.
- Script seed demo/backup/restore, test admin/media/data/maintenance, E2E riêng của Task 2, `.github/workflows/ci.yml` và tài liệu `tasks/task-02/`.
- Nếu Task 3/4/5 sau này nhận một phần trong danh sách này, cập nhật bàn giao ownership trước khi viết; không triển khai cùng file ở hai phiên.

### 2.2. File dùng chung, Task 1 đang là bên tích hợp

- `app/db.py`, `app/schemas.py`, `app/config.py`, `app/main.py`, `app/api/camera.py`, `app/api/roi.py`, fixture chung `app/tests/conftest.py`.
- Không đồng thời ghi các file này. Ghi nhu cầu, hợp đồng, migration và patch dự thảo vào `tasks/task-02/integration/` để bên tích hợp tiếp nhận. Patch phải ghi baseline và được đối chiếu lại diff mới trước khi áp dụng; không áp dụng mù khi code đã đổi.
- Có thể tạo module nghiệp vụ nhỏ dùng helpers hiện có nếu giúp tách ownership; không tạo tầng DB/migration thứ hai hoặc vòng import để né phối hợp.
- Sau khi file được bàn giao, tích hợp và chạy lại test liên quan. Code phụ thuộc patch chưa tích hợp phải ghi `integration_pending`, không đánh dấu hoàn tất chỉ vì test mock đạt.
- Không sửa `app/cv/*`, `app/api/guard.py`, GuardPage, RecognitionLogPanel, PlateReviewPanel, AlertBanner, speak/alertAudio/alertFilter/useAudioLease hoặc benchmark nhận diện của Task 1.
- Event UUID, encounter, camera/gate, `issues[]`, version, bằng chứng và thời gian UTC dùng hợp đồng Task 1. Không tự thay nghĩa trường hoặc thuật toán cảnh báo.

### 2.3. Dữ liệu và tài nguyên

- Ghi `git status`, diff liên quan, interpreter và dependency thực cài. Không stash/reset/clean/commit thay đổi của người khác; không xóa dữ liệu/model/log vì thấy ở root.
- QA dùng DB tạm hoặc SQLite Backup API tạo bản sao, media/output tạm và API port riêng. Không dùng nguồn RTSP vận hành, không khởi tạo YOLO/EasyOCR để test admin.
- Không nâng dependency trên môi trường đang chạy, thay camera, đổi exposure/firmware, kill backend hoặc task khác. Không push/deploy VPS.
- Không chạy training/benchmark GPU trong Task 2. Không mở thêm tiến trình maintenance trên DB/media thật.
- Nhật ký và acceptance của Task 2 ghi riêng; bàn giao bản tổng hợp để cập nhật log chung một lần, tránh nhiều phiên ghi cùng tài liệu.

## 3. Hiện trạng audit cần tái xác nhận

Audit 02/10/2026 là điểm bắt đầu, không mặc định lỗi còn tồn tại sau khi task khác sửa:

1. POST tạo xe chỉ chuyển `plate_number`, `student_name`, `student_class` xuống DB, bỏ photo/dob/phone/student_id.
2. Trang lịch sử gọi GET chi tiết xe chưa có; chỉ lưu `items.slice(0, 20)`, đổi page không tải/chọn dữ liệu mới.
3. API client cố định `http://localhost:8001`; nhiều URL media cũ vẫn là `/media/...` dù production tắt static mount.
4. Lịch sử và scope media JOIN hồ sơ xe hiện tại bằng biển số, khiến đổi/xóa/chuyển chủ xe ảnh hưởng dữ liệu lịch sử.
5. CSV export có BOM nhưng import decode `utf-8` và không loại BOM; dòng thiếu cột gọi `.strip()` trên None gây lỗi.
6. Cleanup bỏ qua lỗi unlink rồi NULL snapshot/clip; chưa xử lý crop và trạng thái giữ chứng cứ.
7. Backup media mặc định tắt; chưa bao phủ ảnh hồ sơ; dọn bản DB không dọn bộ media tương ứng; lịch backup phụ thuộc chu kỳ cleanup.
8. Export vi phạm dùng bộ lọc đang nhập thay vì bộ lọc đã áp dụng, bỏ biển chọn từ autocomplete.
9. Thống kê dùng ngày UTC của timestamp so với ngày local; còn đếm `violation_type` cũ thay vì các lỗi trong `issues[]`.
10. Cập nhật trạng thái nghiệp vụ chưa có kiểm tra version; kiểm tra admin cuối và thao tác đổi/xóa tài khoản nằm ở các bước riêng.
11. Đăng ký công khai chưa có xác minh; upload tin MIME, tên theo mili giây; admin upload không có giới hạn dung lượng.
12. CI có `npm run test:e2e || true` và `continue-on-error`; production routes job chưa kiểm tra deep link thật. SPA còn trả 410 cho `/admin/violations`.
13. Nút giáo viên chưa có; script seed hiện chỉ chấp nhận ba role cũ.

Các phép thử chỉ dùng AST/helper và dữ liệu trong bộ nhớ đã xác nhận (1), CSV BOM/dòng thiếu và cleanup commit sau unlink fail. Chưa thay cho integration test app thật.

## 4. Các đợt thực hiện

### T2.0 — Baseline, ownership và hợp đồng

- Tạo OWNERSHIP, CONTRACTS, EXECUTION_LOG cho Task 2; nêu dependency tích hợp Task 1.
- Đọc schema/routes/tests thực tế, ghi ma trận `verified / reproduced / integration_pending / insufficient_evidence / deferred_by_user`.
- Chạy baseline backend và frontend phù hợp trên môi trường cách ly. Ghi riêng lỗi baseline, lỗi phát sinh và test cần hardware.
- Chuẩn bị fixture gồm hai lớp demo, admin/security/management/teacher, xe và event nhiều lỗi, ảnh/clip có nội dung hợp lệ. Tất cả là dữ liệu giả.
- Integration test phải đi qua app factory, router và middleware triển khai thực, có injection/config tắt camera/model/maintenance thật. Nếu factory chưa hỗ trợ, bàn giao thay đổi bootstrap tối thiểu cho Task 1; không coi app thử dựng riêng là bằng chứng production hoạt động.

**Đạt khi:** baseline tái lập được, QA không chạm DB/media/camera thật, biết rõ file nào được ghi.

### T2.1 — Giữ đăng nhập nhanh, bổ sung demo giáo viên

- Giữ ba nút và hành vi tự điền hiện tại. Thêm Giáo viên bên dưới, button `type=button`, hỗ trợ bàn phím, không submit lặp; khi đang login thì khóa thao tác gửi.
- Nút giáo viên tự điền username/password demo; form vẫn POST login thật. Thêm giáo viên vào mô tả đối tượng dùng trên trang.
- Seed hỗ trợ role teacher và bắt buộc `homeroom_class` không rỗng sau trim. Ưu tiên mở rộng script seed hiện có, có lệnh tạo demo idempotent, không tự reset password/role/class của tài khoản đã tồn tại.
- Nếu username demo trùng tài khoản khác, báo xung đột và dùng tên demo cấu hình riêng đồng bộ với nút; không ghi đè người dùng.
- Chỉ tạo demo trong cấu hình local/dev/demo được chỉ định; test dùng DB giả. Không đưa học sinh thật vào lớp demo hoặc tự tạo/chỉnh roster thật. Chế độ demo không được bypass auth.
- Giáo viên login đến `/teacher/violations`, xem xe/lịch sử cùng lớp; reload và deep link đúng vai trò. Không redirect vòng lặp hoặc về trang không có quyền.
- Giữ trường lớp trong state user nếu frontend cần hiển thị, nhưng quyền dữ liệu vẫn quyết định phía server. Không thêm token mới, session service, OTP hoặc đổi chiến lược auth.

**Đạt khi:** bốn nút tự điền đúng, teacher demo login thành công, thiếu lớp bị từ chối và không xem dữ liệu lớp khác. Auth hardening hoãn được ghi rõ.

### T2.2 — API cùng origin và media nhất quán

- Dùng URL cùng origin mặc định cho API/media. Dev qua Vite proxy có backend target cấu hình local; production frontend build và backend/reverse proxy cùng origin.
- Giữ cách gửi Bearer và nhận cookie hiện tại. Không yêu cầu người dùng thay quy trình login để sửa LAN.
- Không hardcode localhost vào URL được gửi tới browser. Đọc consumers hiện tại, giữ tương thích cách nối `API_BASE_URL + path`; không sửa chồng component Task 1.
- Chuẩn hóa list/detail/encounter/history/upload trả URL media cùng hợp đồng `/api/media/...` hoặc media-ID đã tích hợp. Không còn đường dẫn đĩa Windows hay URL token trong phần Task 2 mới viết.
- Media gắn quan hệ DB tới event/vehicle/student; permission list/detail/export/ảnh/clip cùng chính sách. Giáo viên thiếu lớp luôn 403; không suy ra lớp từ tên file.
- Ảnh hồ sơ: bảo vệ việc xem theo quyền nghiệp vụ; admin xem đầy đủ, teacher/management chỉ khi luồng và scope cho phép. Không mở static để tránh lỗi ảnh.
- Tắt static media công khai khi dùng dữ liệu thật, kể cả cấu hình LAN thử; profile demo dùng dữ liệu giả. Không hạ auth endpoint để chữa 404.
- Production SPA mở/refresh `/admin/violations`, `/teacher/violations`, lịch sử hợp lệ; bỏ 410 ở route SPA thực có. `/api/khong-ton-tai` vẫn JSON 404, không trả index HTML. Cấu hình SPA dùng cùng app factory để test được bản triển khai thật.
- Kiểm tra FileResponse/Range trên Starlette thực cài; clip phát và tua được với phiên hiện tại, không suy từ docs phiên bản khác.

**Đạt khi:** LAN client khác không gọi localhost của chính nó; ảnh trả 200 nội dung ảnh thật, clip và Range đúng; đúng lớp được xem, khác lớp 403; deep link production hoạt động. HTTPS/cookie-only nghiệm thu bảo mật vẫn hoãn.

### T2.3 — Hồ sơ xe/học sinh và lịch sử dùng được

- POST/PUT lưu đủ trường được hỗ trợ: plate, name, class, student_id, dob, phone, photo_path. Test tạo và tải lại từ DB; không chỉ mock gọi helper.
- Validation thống nhất create/update/import/public register; trim, length/date/phone bounds hợp lý, không ép biển OCR mơ hồ thành hồ sơ. Trùng biển update trả 409 thay vì 500.
- Bổ sung GET `/api/vehicles/{id}` với scope phù hợp, đặt route tránh xung đột `/export`, `/violations-summary`.
- History có server pagination `limit=1..200`, `offset>=0`, total đúng và sort timestamp+ID ổn định. Frontend tải theo page và reset page khi đổi vehicle; bỏ request cũ, không giữ slice 20 cố định.
- Xe/roster có search và pagination server, không tải toàn trường mỗi lần chỉ để tìm detail/autocomplete. Giữ response cũ qua adapter khi cần, không âm thầm đổi array thành object làm vỡ consumers.
- Khóa submit khi mutation đang chạy; chỉ báo thành công sau API thành công. Lỗi có retry; không biến lỗi load thành dữ liệu rỗng. Revoke ObjectURL preview sau dùng/unmount.
- Thao tác xóa/sửa hồ sơ không làm mất chứng cứ lịch sử. Dùng archive/registration version và định danh ổn định phù hợp dữ liệu hiện có; tránh cascade xóa event/media.

**Đạt khi:** hồ sơ đầy đủ round-trip, trang lịch sử hơn 100 event tải mọi trang đúng, detail ngoài 200 dòng mới nhất mở được; update trùng biển 409; teacher đúng/khác lớp đúng quyền.

### T2.4 — Bảo toàn danh tính lịch sử và xử lý đồng thời

- Phối hợp Task 1 bổ sung định danh quan hệ và snapshot dữ liệu cần thiết tại lúc event được xác nhận: người/xe/lớp/biển hoặc registration version. Giới hạn dữ liệu cá nhân ở mức nghiệp vụ cần thiết.
- Chốt bằng văn bản: giáo viên xem lịch sử theo lớp đã lưu tại thời điểm sự kiện, trừ cơ chế bàn giao phạm vi được cấp rõ ràng; không tự chuyển quyền lịch sử chỉ vì sửa hồ sơ hiện tại.
- Dữ liệu cũ thiếu provenance giữ `legacy/unknown`. Không tự suy đoán lớp hoặc chủ xe lịch sử từ hồ sơ hiện tại rồi ghi là sự thật đã xác nhận. Có adapter tạm rõ ràng và từ chối khi không chứng minh scope.
- Test sửa biển, chuyển lớp, archive xe, tái sử dụng biển: event cũ giữ danh tính và phạm vi hợp lệ, media không đổi chủ ngoài ý muốn.
- Status mutation dùng expected version, update và audit cùng transaction; xung đột trả 409, frontend tải lại và báo rõ. Không dùng riêng check-then-write ngoài transaction.
- Tách version workflow nếu cần khỏi event version AI theo hợp đồng Task 1, không ghi đè `issues[]`/evidence/encounter khi người dùng đổi pending/reviewed/resolved/reopened.
- Account CRUD vẫn dùng auth hiện tại; sửa quy tắc giữ admin cuối trong transaction, normalize lớp teacher. Không triển khai JWT revocation trong đợt này. Test hai admin thao tác đồng thời không để hệ thống mất toàn bộ admin.

**Đạt khi:** history không đổi người khi sửa hồ sơ; hai operator không ghi đè im lặng; hai thao tác hạ quyền đồng thời giữ ít nhất một admin. Migration bổ sung, lặp an toàn, không sửa dữ liệu cũ theo suy đoán.

### T2.5 — Import/export và upload/đăng ký

- CSV decode BOM đúng (`utf-8-sig` hoặc xử lý tương đương), parser chuẩn hỗ trợ quoted field/dấu phẩy/newline; dòng thiếu cột không làm 500. Kiểm tra header trùng/sai, dòng thiếu, trùng trong file và trùng DB.
- Export xe rồi import vào DB trống phải giữ các trường hỗ trợ. Nếu không export đủ hồ sơ, ghi rõ định dạng và không quảng cáo phục hồi toàn hồ sơ.
- Preview thể hiện chính xác số sẽ tạo/bỏ/trùng/lỗi và mẫu đại diện, không báo `created` cho dòng thực tế sẽ thất bại. Confirm tham chiếu nội dung đã preview bằng hash/token; thay file phải preview lại.
- Confirm chống gửi lặp theo import ID/idempotency; kết quả retry không tạo hồ sơ trùng. Lưu trạng thái/kết quả đủ để biết partial success thay vì yêu cầu timeout rồi không biết đã ghi gì.
- Giới hạn ban đầu CSV 5 MB và 10.000 dòng, configurable và có lỗi rõ. Không retry mọi OperationalError vô điều kiện; chỉ lock/busy, deadline hữu hạn. Chia transaction ngắn/batch vừa để không giữ writer quá lâu gây ảnh hưởng Task 1.
- Export dùng đúng `appliedFilters` gồm xe autocomplete, loại lỗi và ngày đã áp dụng. Export toàn bộ kết quả theo hợp đồng, không âm thầm cắt 100.000 dòng; giới hạn phải được thông báo hoặc dùng chunk/stream phù hợp.
- Chống spreadsheet formula injection ở trường văn bản có thể do người dùng nhập, bảo toàn dữ liệu gốc trong DB; test khi mở bằng spreadsheet.
- Roster import dùng parser đúng nếu hỗ trợ CSV; mọi dòng lỗi được báo, không lọc bỏ âm thầm. Không ràng buộc student_id unique cho dữ liệu thật trước khi kiểm tra quy tắc và duplicates. Trong luồng public một học sinh–một đăng ký active, enforce tại DB/transaction, không chỉ pre-check.
- Public registration **tắt mặc định** khi dùng dữ liệu thật. Demo có thể bật cho roster giả; khóa lookup/upload/register cùng flag, không chỉ ẩn form. Khi tắt trả trạng thái dịch vụ rõ, không lộ roster/biển.
- Upload admin và demo public: decode ảnh thực, reject file giả MIME/SVG nếu không có xử lý phù hợp, max 5 MB, giới hạn decoded dimensions/pixel count, UUID filename, format output cho phép, loại metadata không cần thiết.
- photo_path phải trỏ tới upload ID hợp lệ thuộc scope, không nhận đường dẫn tùy ý của client. Dọn upload chưa gắn bản ghi sau TTL, có giới hạn và log lỗi; không xóa ảnh đang tham chiếu hoặc thuộc backup/hold.

**Đạt khi:** BOM/quoted/thiếu cột/trùng/confirm lặp đều có kết quả đúng; export khớp bảng; fake image/oversize bị chặn; hai upload cùng mili giây không ghi đè; register tắt không tra được dữ liệu thật.

### T2.6 — Báo cáo đúng thời gian, đúng đơn vị đếm

- Lưu UTC, lọc ngày nghiệp vụ theo `Asia/Bangkok`/UTC+7 đã cấu hình. Chuyển đầu/cuối ngày sang UTC, dùng khoảng `[start, next_day_start)`; không ghép chuỗi local rồi so với timestamp UTC.
- Chuẩn hóa truy vấn timestamp cũ có format khác bằng adapter/migration an toàn đã kiểm tra; không giả định lexical comparison luôn đúng giữa ISO và SQLite datetime string.
- Báo riêng số lượt xe/encounter, số event, số issue đã xác nhận và số cần kiểm tra. Loại lỗi đếm từ `issues[]` theo hợp đồng Task 1, adapter dữ liệu legacy rõ ràng; không đếm người bị lỗi OCR vàng là vi phạm chắc chắn.
- Thống kê theo lớp dùng provenance lịch sử đã tích hợp; ghi unknown nếu thiếu. Dashboard nêu thời gian cập nhật, scope, khoảng ngày và có refresh/retry.
- Các chỉ số tái phạm/clean days có định nghĩa thống nhất; cấu hình ngưỡng từ API, không hardcode khác server. Không dùng số lượng log làm độ chính xác AI.

**Đạt khi:** event UTC tối thuộc ngày Việt Nam tiếp theo được tính đúng; 00:00/23:59:59 và ranh giới tháng đúng; một lượt có hai lỗi đếm một lượt và hai issue, không nhân do nhiều camera/update.

### T2.7 — Cleanup giữ liên kết chính xác

- Snapshot/crop/clip xử lý theo media record thực tế và chính sách retention/hold. Default 90 ngày theo kế hoạch hiện có; không cleanup record được giữ phục vụ kiểm tra.
- Validate path thực nằm trong allowed media root trước unlink; không xóa path tuyệt đối tùy ý lấy từ DB. Không theo symlink ra ngoài root.
- Chỉ clear/đánh dấu đường dẫn từng media sau khi đã xóa thành công hoặc xác minh không còn file; PermissionError/OSError giữ liên kết và trạng thái lỗi để retry.
- Không clear cả batch nếu một file fail, không báo success hoàn toàn khi có lỗi. Lưu số attempted/deleted/missing/failed/held và lỗi đã che dữ liệu nhạy cảm.
- Crop thuộc cùng vòng đời chứng cứ; file đang upload/ghi clip/backup không bị xóa. Bản ghi lịch sử giữ lại, không cascade mất audit.
- Job có batch và thời hạn hữu hạn, không giữ writer lock qua nhiều thao tác file/scan. Metrics/log không quét toàn media mỗi poll/frame.

**Đạt khi:** PermissionError, mất file, path ngoài root, hold, crop và chạy cleanup hai lần đều đúng; thất bại không làm biến mất link DB hoặc xóa chứng cứ còn hạn.

### T2.8 — Backup bộ dữ liệu hoàn chỉnh và restore thử

- Giữ SQLite Backup API; đo thời gian giữ `_write_lock`, tránh khóa toàn bộ ghi event suốt bản copy lớn. Consistency phải được chứng minh trước khi giảm lock, không chỉ bỏ lock để chạy nhanh.
- Mỗi bộ backup gồm DB, manifest/version, snapshot/crop/clip/ảnh hồ sơ được DB tham chiếu, checksum hoặc kiểm chứng tương đương. Liệt kê missing media, không ghi complete nếu bộ bắt buộc còn thiếu.
- Phối hợp giữ file được snapshot DB tham chiếu khỏi cleanup trong lúc backup. Atomic complete marker: backup dang dở không được chọn là bản mới nhất có thể restore.
- Media UUID copy tăng dần nếu phù hợp; nếu lưu blob dùng chung thì retention phải tính reference của các manifest. Dọn toàn bộ bộ backup hết hạn, không xóa blob còn được bản khác dùng.
- Lịch độc lập: mốc backup giờ và cuối ca, cleanup không quyết định tần suất backup. Giữ 24 mốc theo giờ và 14 mốc cuối ca nếu đĩa cho phép; không tự xóa chứng cứ thật để đủ dung lượng.
- Dung lượng cảnh báo <15%; nghiêm trọng <5% hoặc <5 GB. Hiển thị/log rõ khi không tạo được backup. Không coi backup cùng ổ là bảo vệ khỏi hỏng ổ.
- Restore vào thư mục và DB riêng, không ghi đè DB/media vận hành. Kiểm tra `integrity_check`, quan hệ và media hash, tài khoản/cấu hình; mở ảnh và phát/tua clip sau restore.
- Hướng dẫn thao tác backup/restore/đầy đĩa và rollback migration. Không hardcode đường dẫn machine-specific vào bản có thể phục hồi.

**Đạt khi:** backup đang có writer trên DB giả vẫn khôi phục đúng; đủ media được manifest xác nhận; lỗi copy/disk full không có complete marker; purge không bỏ lại bộ media vô hạn; restore thành công sang vị trí khác. Mục tiêu RPO một giờ/RTO 30 phút cần đo, chưa mặc định đạt.

### T2.9 — CI và regression không che lỗi

- Backend tests, frontend lint/build, Node tests và Playwright bắt buộc phải fail job khi thất bại. Bỏ `|| true`/`continue-on-error` ở lệnh test; cleanup tiến trình best-effort vẫn được phép để giữ job dọn dẹp.
- E2E dùng backend cùng app factory thật với DB/media giả và dependency CV thay thế. Không khởi tạo model/camera thật trong login/admin/media test; không skip các success path vì fixture thiếu.
- Cổng và proxy backend/frontend đồng bộ. Readiness phải kiểm HTTP status/nội dung với deadline, không dùng `curl -s` thành công transport để coi 401/500 là healthy.
- Production test build SPA rồi request deep link thật, API 404 JSON, cookie/media đúng quyền và clip Range theo phiên bản đang cài. Không thay thế bằng test import config/secret.
- Test isolation: fixture DB/env/module có hoàn trả, mỗi xdist worker có dữ liệu riêng. Không làm yếu assertion để chấp nhận rows từ test khác; so output exact sau setup sạch.
- Test logic quan trọng dùng hành vi thật: hồ sơ round-trip, CSV round-trip, delete-failed cleanup, restore và access forbidden. Không chỉ grep source hoặc chấp nhận 404 cho luồng thành công.
- Đo list/detail/report trên dữ liệu giả 100.000 event với ba client, ghi p50/p95, query plan/index. Mục tiêu list/detail p95 <=500 ms trên máy mục tiêu; không tính tải model vào phép đo admin.
- Chỉ đổi dependency khi có lỗi tương thích xác nhận và được tích hợp riêng; không broad upgrade. Ghi versions thực cài, interpreter và OS của từng kết quả.

**Đạt khi:** CI đỏ khi test cố tình fail, xanh khi tất cả check bắt buộc đạt; fresh process full suite đạt sau tích hợp, không xóa/skip test khó để báo xanh.

## 5. Thứ tự, lệnh kiểm tra và mốc bàn giao

Thứ tự: **T2.0 → T2.1 → T2.2 → T2.3/T2.4 → T2.5/T2.6 → T2.7/T2.8 → T2.9**. Chuẩn bị fixtures và backup trên DB giả có thể làm lúc chờ file dùng chung. Không dừng hỏi sau từng đợt; tiếp tục phần độc lập khi còn dependency tích hợp.

Chạy targeted tests trước, rồi regression phù hợp. Sau tích hợp cuối chạy fresh process:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
node --test frontend/test/*.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Nếu shell không mở rộng wildcard Node, liệt kê file rồi truyền danh sách cho node; không bỏ test. E2E phải dùng config/fixtures/port cách ly đã xác minh; lệnh trên không được tự mở DB/camera thật. Không chạy full suite cùng lúc Task 1 đang đo GPU. Không coi test môi trường khác hoặc selective suite là full suite.

Sau mỗi 2–3 đợt: chạy checkpoint test, kiểm tra diff và tương thích Task 1. Không bắt buộc người dùng xác nhận giữa các đợt. Việc cần thông tin bên ngoài như LAN/HTTPS/ổ backup thứ hai ghi rõ phần chưa nghiệm thu và tiếp tục các phần độc lập.

Tạo/cập nhật trong Task 2:

- `tasks/task-02/todo.md`: checklist, trạng thái từng đợt.
- `tasks/task-02/OWNERSHIP.md`, `CONTRACTS.md`: file được ghi, response/API/migration và dependency.
- `tasks/task-02/EXECUTION_LOG.md`: bug tái hiện, thay đổi, lệnh/kết quả, môi trường, số đo và rollback.
- `tasks/task-02/ACCEPTANCE_REPORT.md`: PASS/FAIL/PENDING từng tiêu chí; phân biệt viết mã, test hành vi, production smoke, LAN thật và restore thật.
- `tasks/task-02/integration/`: yêu cầu/patch các file dùng chung, tình trạng nhận/tích hợp và test sau tích hợp.
- `tasks/task-02/DEFERRED_AUTH.md`: các lỗi đăng nhập/phiên hoãn theo quyết định người dùng. Không xóa mục này hoặc đánh dấu đã xử lý bằng nút demo.

**Không được kết luận “sửa hết” nếu còn patch chưa tích hợp, test bắt buộc fail, restore chưa kiểm chứng hoặc auth đã hoãn.** Báo chính xác phần đã hoàn thành và phần còn lại. Không thay định nghĩa đạt để chốt báo cáo.
