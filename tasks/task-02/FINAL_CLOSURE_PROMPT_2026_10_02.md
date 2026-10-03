# TASK 2 — Hoàn thiện admin/browser QA và đóng regression tích hợp

Bạn tiếp tục TASK 2, thực thi đến khi mọi phần khả thi đã sửa và kiểm chứng. Không chỉ tóm tắt rồi hỏi người dùng có tiếp tục. Đây là phần bổ sung cho REPAIR_PROMPT hiện có, không thay/xóa kế hoạch hoặc sửa lại công việc đã đạt.

## 0. Baseline đã cập nhật và phạm vi

Đọc `REPAIR_PROMPT.md`, REPAIR_TODO, EXECUTION_LOG, ACCEPTANCE_REPORT Task 2 và `docs/CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md`. Mã mới là nguồn xác minh; report cũ cung cấp ca tái hiện.

- **R3.4 và backup đã có 37 passed** cho `test_task02_t2_8_backup.py`, `test_backup.py`, `test_maintenance_worker.py`. Giữ implementation đúng; không sửa trở lại file backup flat chỉ vì log fail lịch sử.
- Codex đã chạy lại cleanup admin + teacher/media: **25 passed**. Không tiếp tục ghi cleanup schema cũ là blocker nếu kiểm hiện tại đạt.
- Lỗi disk-full/temp là sự cố môi trường của run đó; không dùng nó kết luận mọi lỗi full regression khác cũng do môi trường.
- Không chọn “No follow-up needed” chỉ vì nhóm backup xanh: browser integration, full regression và training integration vẫn còn.

Giữ đăng nhập tạm người dùng yêu cầu: bấm tài khoản tự điền username/password và có lựa chọn giáo viên phía dưới; vẫn login API thật. Chưa migrate chiến lược auth/localStorage/cookie/JWT revocation. Quyền teacher/media, lỗi login và navigation vẫn phải đúng.

Task 2 làm **integration owner** cho file shared sau khi nhận bàn giao Task 1/3: `main.py`, router/sidebar, config/schema/DB hoặc fixture dùng chung khi cần. Đăng ký nhận quyền file rõ ràng rồi áp patch, đọc lại diff trước khi ghi. Không ghi file đang được owner khác chỉnh; tiếp tục phần riêng trong khi đợi bàn giao. Không stash/reset/clean, push/deploy hoặc sửa DB/media/camera thật.

## 1. D1 — Khôi phục môi trường QA kiểm chứng

- Thử process/shell mới nếu phiên cũ hỏng; xác nhận interpreter/Node/ports/dung lượng. Không kill tiến trình không thuộc run QA của mình. Không xóa rộng `%TEMP%`, dữ liệu người dùng hoặc thư mục task khác.
- Dùng root QA mới, DB mới/SQLite backup QA, media/backup/recording mới, port riêng và log đầy đủ. Trước full suite kiểm các config binding thực sự trỏ QA.
- Backup tests tạo ảnh/DB nhỏ riêng; không copy toàn bộ media vận hành sang mỗi tmp_path khiến hàng chục GB bị nhân đôi. Vẫn kiểm copy ảnh thật, hash/manifest/restore/copy fail và worker route.
- Backend unit/integration không khởi tạo RTSP/model thật chỉ vì import router. Dùng factory triển khai thật với dependency/config CV giả. Không dựng app riêng rồi dùng làm bằng chứng production.
- Readiness phân biệt liveness, route đã sẵn sàng, health bảo vệ cần token. HTTP 401 chỉ chứng minh endpoint có trả lời, không chứng minh app đã sẵn sàng cho luồng nghiệp vụ.

**Đạt D1:** một run QA mới khởi động/dừng sạch, không đụng nguồn live, không tăng dung lượng không giới hạn. Ghi dung lượng trước/sau và process do run tạo.

## 2. D2 — Hoàn thiện UI E2E, không giảm assertion

- Chạy lại đầy đủ suite hiện có, không chỉ 38/39 hoặc 27/42. Sửa crop alt/label với Task 1 theo contract “Ảnh người”, “Ảnh đầu / mũ”, “Ảnh biển số”; không skip test vì khác owner.
- Fixture same-origin phải intercept đúng API và không chặn JS module `/src/...`. Khi mock `/me`, trả đúng user/role/homeroom_class của phiên; teacher phải tới `/teacher/violations`.
- Chờ route/heading/hành vi đích đúng. `not.toHaveURL(/login/)` đơn độc không chứng minh đã vào trang đúng quyền. Không dùng timeout dài hoặc selector lỏng để che lỗi.
- Chờ localStorage chỉ là đồng bộ fixture. Nếu nghi race product, lấy trace/console/network, tái hiện trên API thật rồi sửa tối thiểu trong scope; test backend homeroom_class không chứng minh React navigation.
- Cards mũ/OCR có nhiều mẫu mới, không mock một mẫu đã confirmed rồi coi đó là chứng minh temporal consensus.
- Kiểm beep/TTS bằng spy lệnh phát, timer, dedup, tắt loa/reconnect. Giữ test tiếng nói logic riêng và ghi giới hạn: giọng Việt/autoplay thật vẫn cần máy bảo vệ.

**Đạt D2:** mọi UI mock E2E đạt, nhãn Việt đúng, không skip quan trọng, không bỏ kiểm route/crops/quyền để chuyển xanh.

## 3. D3 — Browser integration với backend QA thật

Tạo nhóm tách biệt với UI mock. Browser gọi API thật qua cùng origin; chỉ thay camera/detector/OCR nguồn giả và runtime phụ thuộc nặng khi cần. Không intercept toàn bộ API/login/DB/media/WS ở nhóm này.

Test:
- Login admin/security/management/teacher, sai password, logout/reload, điều hướng đúng, class được truyền đúng.
- Teacher đúng lớp/khác lớp/không có lớp; list/detail/export/ảnh/clip cùng phạm vi. Khách không truy cập dữ liệu nhạy cảm.
- Phân trang >200 bản ghi, filter reset trang, encounter gom trước paginate, detail cũ ngoài các dòng gần nhất. Response lỗi phải hiện error/retry, không thành empty.
- Cập nhật version đồng thời: 409 và reload; CSV preview/import lại/formula/round-trip; upload ảnh thật/giả/quá lớn.
- Ảnh thật phải 200 và decode; clip thật phải stream/tua Range đúng quyền, không dùng 404 hoặc GIF giả làm bằng chứng media backend.
- Hai viewer nhận cùng event/upsert; reconnect không phát lịch sử. Slow client không chặn bên khác theo contract Task 1.
- Backup manual/list/worker cùng bộ R3; restore vào root mới và mở được media; cleanup hold/root/dry-run/failure đúng.

## 4. D4 — Nhận và kiểm integration Task 3

Router training và trang App.jsx hiện đã có; đối chiếu hiện trạng trước khi ghi PENDING hoặc áp patch lại.

- Task 1 giữ `recognition_reviews.py` để thêm enqueue hook sau save theo hợp đồng Task 3; không đưa polling feedback vào pipeline.
- Task 3 giữ collector/asset/dataset/worker/trainer. Task 2 tích hợp lifecycle worker/router/config/sidebar theo patch đã bàn giao, không tự xây thêm implementation trùng.
- Kiểm luồng browser dùng backend thật: xem crop thật → sửa chữ/box → lưu version → dataset có ảnh → export/import → freeze → tạo job → trạng thái worker thật → metrics/candidate.
- Tách lifecycle simulation khỏi training thật; candidate smoke/nonexistent/không evaluation bị cấm promote. UI không báo “đã áp dụng camera” khi chỉ đổi registry.
- Nếu chưa đủ nhãn/GPU cho evaluation chất lượng, kiểm plumbing bằng runner thật tối thiểu hợp lệ và ghi PENDING_DATA cho chất lượng; không fake metrics cho production.

**Đạt D4:** phần software integration khả thi hoạt động end-to-end; shared patch đã áp vào app thực, không chỉ nằm trong docs.

## 5. D5 — CI và bản build production

- CI tách UI mock và API integration thật, cấu hình QA tắt camera/model live; port/proxy/readiness rõ. Không gọi uvicorn production app bình thường là test mode chỉ nhờ comment.
- Full backend sequential trước khi bật xdist; nếu parallel, mỗi worker phải có DB/media/backup/config riêng, không cùng training DB/dataset path.
- Node test là gate riêng; lint/build đầy đủ. Test bắt buộc không `continue-on-error`/`|| true`. Cleanup process có xử lý lỗi riêng và không biến fail test thành xanh.
- Build frontend rồi chạy production factory với QA secret/config hợp lệ. Refresh `/admin/violations`, teacher/training pages là SPA hợp lệ; API404 JSON, không HTML; media vẫn có quyền. Kiểm thiếu secret là test khác, không thay thế route smoke.
- Thu log/traces/video/screenshots của lỗi và provenance run. Không log mật khẩu, camera credential hoặc thông tin học sinh thật.

## 6. D6 — Regression cuối, không bỏ các test còn lỗi

Chỉ bắt đầu full run khi các owner bàn giao snapshot ổn định. Nếu file tiếp tục đổi giữa run, ghi run không đại diện snapshot cuối rồi chạy lại sau thay đổi; không chạy nhiều full suite cạnh tranh.

Lệnh backend cốt lõi (thêm config QA và basetemp mới cho run):

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
```

Frontend chạy từ thư mục frontend, kiểm exit code từng lệnh:

```powershell
npm run lint
npm run build
node --test test/*.test.mjs
npx playwright test
```

Không `--ignore`, `--deselect`, `-k` để bỏ failure trong final run. Focused run có thể chọn test, phải ghi rõ không phải full. Skip cũ phải rà lý do, không bỏ luồng guard/media/training để khỏi khởi tạo model.

Mỗi failure phải có traceback mới và nguyên nhân xác nhận. Fixture thiếu field thì sửa fixture/mock đúng invariant, không thêm fallback production che lỗi. Runtime thật thiếu field thì sửa production. Không mặc định test cũ sai, không đổi assertion sang config hiện tại nếu test bảo vệ requirement khác.

Nếu shell chết: giữ log/run ID, thử môi trường process mới; không viết “mọi test PASS”. Nếu thật sự chưa chạy được, ghi TOOLING_BLOCKED cụ thể và bàn giao lệnh/run chưa thực hiện; tiếp tục việc không cần công cụ đó.

## 7. Bàn giao và Definition of Done

Cập nhật `CLOSURE_TODO.md`, REPAIR_TODO/EXECUTION_LOG/ACCEPTANCE_REPORT, giữ lịch sử. Task 2 tổng hợp `docs/FINAL_SOFTWARE_INTEGRATION_ACCEPTANCE_2026_10_02.md` sau bàn giao ba task; ghi test count thực cuối thay vì đặt trước một con số.

Checklist:
- [ ] D1 QA/config/dung lượng/process kiểm chứng đúng.
- [ ] D2 toàn UI mock E2E đạt, assertions không bị hạ.
- [ ] D3 browser integration API/media/quyền thật đạt.
- [ ] D4 training flow software đã nối, trạng thái trung thực.
- [ ] D5 CI/production routes/build đạt.
- [ ] D6 full backend + Node + lint + build + browser cuối không bỏ failure.
- [ ] Báo cáo snapshot cuối, còn pending dữ liệu/thiết bị tách riêng.

LAN hai máy, RPO/RTO media vận hành, camera thật 12 giờ và accuracy nhãn độc lập không được suy từ unit/E2E giả. Software PASS chỉ khi software thật đạt; không tự gọi hệ thống HARDWARE_ACCEPTED. Tiếp tục các phần độc lập không hỏi sau từng đợt; chỉ cần người dùng khi thiếu thông tin/thiết bị ngoài repo.
