# Codex kiểm tra kết quả Cursor Pre-E3 — 01/10/2026

## Kết luận

**Đã sửa được một phần, chưa đóng Pre-E3.** Crossing trực tiếp 3+3, gom encounter trước phân trang, trạng thái confirmed + resolved khác mã và đường persist thành công trước alert đã cải thiện. Các test hiện có đạt nhưng còn những nhánh trái yêu cầu tái hiện được. Không sửa application code trong lượt review này; không mở RTSP, load model inference hoặc chạy nghiệm thu thiết bị.

## Kiểm chứng Codex thực hiện

| Lệnh / phép kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| `venv\Scripts\python.exe -B -m pytest app/tests/test_crossing.py app/tests/test_e2_1_violation_issues.py app/tests/test_s5_evidence_before_alert.py app/tests/test_s10_test_isolation.py -p no:cacheprovider --tb=short -q` | **52 passed, 1 warning**, 20.23 giây, exit 0 | DB test tạm; không phải full suite hoặc nghiệm thu production |
| `node --test frontend/test/speak.e2_3.test.mjs` | **9 passed**, exit 0 | Kiểm tra queue và helper filter; chưa kiểm tra lời gọi beep/TTS trong React/browser |
| `npm run lint` tại `frontend` | Exit 0, còn warnings | Có cảnh báo dependency `load`/filter và reconnectTimer, cùng cảnh báo khác |
| `npm run build` tại `frontend` | Exit 0; 709 module; build 5.16 giây | Bundle JS ~850.60 kB; cảnh báo chunk lớn. Build không xác nhận API/browser hoạt động |
| Probe crossing bằng `runpy.run_path` | Các lỗi R01 bên dưới tái hiện | Chỉ module crossing, không mở camera/DB |
| Probe hàm DB trích nguyên AST, SQLite `:memory:` | Scope lớp bị vượt ở R03 | Dữ liệu giả, không đọc/sửa DB vận hành |
| Probe helper Node và nhánh cooldown trích nguyên AST | R02/R04 tái hiện | Không phát âm thanh thật, không ghi media |

Không cộng 52 test này vào 450 test lịch sử vì có thể trùng. Codex chưa chạy lại full suite 450 test, guard integration hoặc browser E2E. Lượt 450 test bỏ hai file guard phải được gọi là **bộ hồi quy có loại trừ**, không phải full suite đầy đủ.

## Các mục cần Cursor sửa tiếp

### R01 — P1: crossing qua vùng biên và giới hạn thời gian vẫn sai

Vị trí: `app/cv/crossing.py:274`, `:300`, `:311`, `:319`.

Probe dùng đường `[0.2,0.5,0.8,0.5]`, tâm x=0.5, `min_frames_per_side=3`, `max_crossing_sec=5`:

- 3+3: y `[0.3,0.3,0.3,0.7,0.7,0.7]` → `[False,False,False,False,False,True]`: đạt trường hợp cơ bản.
- **1+ON+3**: y `[0.3,0.5,0.7,0.7,0.7]`, t `[100,100.2,100.4,100.6,100.8]` → `[False,False,False,False,True]`: sai vì phía A mới một frame. Nhánh ON kiểm tra `side_before_on` nhưng không yêu cầu phía A đã xác nhận đủ ba mẫu.
- **Quá năm giây:** giữ A từ t=100 đến 105, sau đó B tại 106/106.2/106.4 vẫn trả crossing. Nhánh trực tiếp tính elapsed từ lúc streak B bắt đầu, mất mốc phía A nên không chặn cửa sổ toàn lượt.

Yêu cầu: một state machine lưu bằng chứng đủ mẫu của cả hai phía trong cửa sổ hợp lệ; đi qua ON không tạo mẫu cho A/B. Đếm frame mới, giữ mốc thời gian chuẩn, chống lặp. Thêm test hai hướng, 1/2+ON+3 không crossing, quá hạn, rung và frame lặp. Kiểm tra biên 2% đường chéo trong pixel trên ảnh không vuông; API update hiện chỉ dùng tọa độ chuẩn hóa chưa thể hiện kích thước frame. Sửa lỗi tên `pure_streak` khác `pure_side_streak` khi đi vào ON.

### R02 — P1: S5 còn đường tắt phát alert trước bằng chứng

Vị trí: `app/cv/pipeline.py:1360`, `:1367`, `:1477`, `:1523`.

Nhánh cooldown gọi `_push_alert` trực tiếp khi `current_time-last_log < VIOLATION_COOLDOWN`. Key vẫn `plate_matched or 'UNKNOWN'`, nên hai xe chưa đọc biển dùng chung cooldown. Cooldown được cập nhật trước IO; nếu lần ghi trước thất bại, lần sau có thể phát alert không có bằng chứng hoặc bản ghi thành công.

Probe nguyên hàm `_process_violations` với time=101, `_last_log_time={'UNKNOWN':100}`, track=99, no-helmet, xe máy và không plate trả một alert `MULTIPLE`, không đi qua persist. Đây là bằng chứng nhánh cooldown tồn tại; phải có test với ledger xác nhận thật và IO thất bại để kiểm chứng end-to-end.

Đường persist đã chuyển alert sau insert/imwrite, nhưng còn ghi clip đồng bộ trước DB/alert; `_write_clip` không được bọc cùng xử lý lỗi. Clip chậm có thể trì hoãn cảnh báo, clip exception có thể khiến snapshot đã ghi nhưng event không được insert. Future bị bỏ, lỗi không được thu vào health/retry.

Yêu cầu: cooldown theo lượt camera/epoch/track hoặc encounter, không dùng UNKNOWN chung; alert chính thức chỉ từ event đã lưu và snapshot/crop thành công. Clip tác vụ riêng, không chặn cảnh báo. Retry/lỗi IO hữu hạn có metrics; tên media UUID. Test IO đang pending/fail, hai xe chưa biết biển, clip chậm/raise và cảnh báo không trỏ file giả.

Test `test_process_violations_does_not_push_alert_directly` hiện dùng `vehicle_type=None` rồi assert không gọi persist/alert. Đây chỉ kiểm tra early return của người đi bộ; không kiểm tra đường có vi phạm/cooldown và không bắt được lỗi trên.

### R03 — P1: query lấy rows của encounter mất phạm vi lớp

Vị trí: `app/db.py:815`, `:819`; `app/api/admin.py:495`.

COUNT và chọn encounter có `student_class` filter, nhưng query lấy toàn bộ rows của các encounter chỉ dùng `IN (...)`, không áp lại phạm vi quyền. Với encounter có bản ghi khác lớp (ví dụ định danh trùng/ghép sai), giáo viên có thể nhận issues/media/plate của lớp khác.

Probe SQLite in-memory: hai xe A lớp 10A1 và B lớp 10B1, hai bản ghi cùng encounter `shared`. Gọi nguyên hàm `list_violation_encounters(student_class='10A1')` trả `violation_ids=[1,2]`, gồm row lớp 10B1.

Teacher thiếu lớp vẫn chuyển None xuống DB, có thể bỏ bộ lọc hoàn toàn. Đây là mục còn lại được báo cáo thừa nhận, cần ưu tiên cùng lỗi query mới.

Yêu cầu: áp chính sách server cho tất cả rows/detail/media sau gom, fail-closed khi thiếu lớp; cân bằng việc giữ đủ issues với quyền được xem. Test mixed-class encounter, teacher đúng/khác/thiếu lớp và media trực tiếp. Pagination thêm tie-breaker ổn định khi nhiều lượt cùng timestamp; COUNT/page/row-fetch dùng snapshot đọc nhất quán.

### R04 — P1: âm thanh vẫn có thể đọc sai lỗi/chưa xác nhận

Vị trí: `frontend/src/utils/alertFilter.js:21`, `:25`; `frontend/src/components/AlertBanner.jsx:45`, `:155`, `:180`.

Probe helper:

- `violation_type=PLATE_LOW_CONFIDENCE`, issue `NO_HELMET pending` → `silent=false`.
- Cùng payload với issue `NO_HELMET resolved` → `silent=false`.
- Chỉ có `issues=[NO_HELMET confirmed]`, không có violation_type cũ → `silent=true`.

Helper chỉ xét mã, không xét trạng thái xác nhận. Speech vẫn lấy `violation_type` cũ: payload `NO_PLATE` + `NO_HELMET confirmed` được phép phát âm thanh nhưng câu đọc vẫn “xe không có biển số”, thay vì nhắc đội mũ. Dedup vẫn theo track, chưa theo event+issue; timer speech/reconnect không được dọn đầy đủ. Có nguy cơ bỏ lỗi mới hoặc phát câu cũ sau chuyển gate/unmount.

Yêu cầu: xây danh sách issue được phép đọc (confirmed, loại đạt nghiệm thu, bằng chứng sẵn sàng); cùng danh sách quyết định beep và nội dung lời nhắc. Unknown/pending/resolved và OCR yếu không được mở tiếng. Legacy adapter rõ ràng. Dedup event+code, cleanup timer/queue; một máy giữ lease loa. Thêm browser/component tests quan sát AudioContext/speechSynthesis calls và câu đọc, không chỉ helper boolean.

### R05 — P1: test MJPEG treo chưa có kết luận root cause đầy đủ

Vị trí: `app/api/guard.py:94`; `app/tests/test_guard_origin.py:196`.

`_stub_heavy_imports()` chỉ trả `_has_models()`, không stub pipeline. `video_feed.generate()` dùng `while True` không có kết thúc. `TestClient.get()` mặc định thu response body; một MJPEG vô hạn không kết thúc thì lời gọi không trả về kể cả model/pipeline đã khởi tạo xong.

Vì vậy “CUDA/EasyOCR không trả về” chưa phải kết luận duy nhất đã được chứng minh. Stub get_pipeline đơn thuần cũng chưa đủ nếu generator vẫn chạy vô hạn.

Yêu cầu: tách auth/integration stream dùng pipeline giả và stream hữu hạn hoặc client có điều khiển disconnect; kiểm tra frame bytes/content type, cookie/Bearer, Origin và quyền. Kiểm tra timeout/cancel bằng subprocess giới hạn thời gian và kiểm chứng disconnect giải phóng stream. Test không mở RTSP/load weights thật. Sau đó chạy đủ hai file guard cùng suite, ghi danh sách skip thực tế. Runtime camera integration tách riêng, có cấu hình opt-in.

### R06 — P2: metadata và UI E2 chưa được hoàn thiện

Vị trí: `app/cv/pipeline.py:1398`; `frontend/src/pages/AdminViolationsPage.jsx:448`.

Metadata vẫn `sample_count=_frame_seq`, `observed_at=now`, thay vì số mẫu và mốc quan sát ledger. Trang AdminViolations chưa có tích hợp `encounters`/`issues`/`display_status` theo tìm kiếm source; effect tải vẫn chỉ chạy lúc mount. Cần test chuyển trang/lọc và request cũ đến muộn.

Ngoài ra nhánh nhận diện vẫn suy `NO_PLATE` từ thiếu box, `PLATE_OBSCURED` từ OCR rỗng; trường hợp đang đi xe qua cổng bỏ `NO_HELMET` khỏi danh sách. Các quy tắc này trái yêu cầu cần kiểm tra khi chưa rõ biển và giữ mọi lỗi độc lập. Không thể coi thêm issues_json đã hoàn thiện bảng/decision nhiều lỗi.

Yêu cầu: metadata ledger thật; giữ lỗi mũ cùng crossing; OCR pending/error/empty chuyển review; UI dùng đầy đủ issues và state riêng. Không nới assertion để che thiếu isolation. DB test module-shared có thể được dùng có chủ ý, nhưng test cụ thể phải chứng minh record đã tạo và exact result trên bộ dữ liệu cô lập; `total >= 3` không chứng minh đúng COUNT/pagination.

## Prompt gửi Cursor

> Đọc `docs/CODEX_PRE_E3_REVIEW_2026_10_01.md`. Hoàn thiện các mục R01–R06 theo thứ tự: phạm vi lớp và crossing → bằng chứng/cooldown → âm thanh → test stream hữu hạn/isolation → metadata/UI. Đối chiếu mã mới trước khi sửa, giữ thay đổi chưa commit. Bổ sung test tái hiện các probe đã nêu; không thay test để hợp thức hóa hành vi sai. Chạy bộ kiểm thử bằng venv gồm cả guard sau khi cách ly, rồi Node, lint/build và browser E2E bằng nguồn/API/DB/media giả. Cập nhật execution log và acceptance report với artifact, lệnh/exit code và giới hạn. E3.1 kiểm kê video có thể tiếp tục độc lập; chưa đóng Pre-E3 hay bắt đầu nghiệm thu model mới khi các lỗi quyết định/cảnh báo còn mở. Không mở hoặc đổi RTSP, sửa DB/media vận hành, nâng dependency hay triển khai remote trong lượt vá.

Nối hai camera cùng cổng, cookie cùng origin và nghiệm thu 30 phút/12 giờ vẫn là các mục kế tiếp chưa được kiểm chứng trong lượt này. Gương review-only và ghép tự động chưa đạt tiếp tục tắt theo kế hoạch chính.
