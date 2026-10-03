# TASK 3 — Hoàn thiện vòng sửa nhãn → dataset ảnh thật → training → đánh giá

Bạn tiếp tục TASK 3 trong repository hiện tại. Thực thi đến khi phần khả thi hoàn tất, không dừng ở wrapper/simulation và không hỏi tiếp tục sau từng phần.

Đọc plan/todo/CONTRACTS/OWNERSHIP/log/report Task 3 và `docs/CODEX_TASK123_PROGRESS_AND_RESOLUTION_2026_10_02.md`. Giữ thay đổi chưa commit; không stash/reset/clean, không sửa shared file đang có writer khác, không push/deploy/model live hoặc DB/media vận hành.

## 0. Quyết định đã chốt: A, đúng API lưu feedback

Không thêm hook “sau save review” trong `pipeline.py`. Không polling feedback ở capture/AI hot path. Nơi lưu feedback là `app/api/recognition_reviews.py`.

Phân công:
- **Task 3:** viết collector/worker/reconciliation, test, `integration/FEEDBACK_HOOK_CONTRACT.md` và patch tối thiểu.
- **Task 1:** writer duy nhất thêm hook tại `recognition_reviews.py` sau save thành công, không conflict.
- **Task 2:** integration owner lifecycle worker/router/config/shared API và regression browser cuối sau nhận bàn giao.

Không cần hỏi người dùng chọn A/B/C hoặc duyệt chuyển file nữa. Nếu chưa có bàn giao file, làm collector/test/patch và các phần độc lập; không sửa chồng. Một `try/except` quanh collector đồng bộ không bảo đảm feedback nhanh.

## 1. E0 — Đính chính baseline và status

- 43 helper/API tests đã PASS trong review, nhưng chưa bảo vệ các lỗi export/import/queue/promotion tái hiện.
- Smoke đang lấy label làm prediction và dùng `/tmp/smoke.pt`: đánh dấu rõ **lifecycle simulation**, không gọi training/evaluation accuracy thật, không quảng bá 100% OCR.
- Router backend training và App.jsx pages đã có; kiểm hiện trạng rồi cập nhật integration, không tiếp tục chờ patch đã gắn.
- Registry active chưa là model runtime applied. UI/report phải nói đúng.
- `ocr_engine.py` hiện wrapper read, detector engine wrapper predict; cần runner tối ưu trọng số thật, không coi wrapper là trainer.

## 2. E1 — Thu feedback không chặn người duyệt

- Viết `sample_collector.py` theo hợp đồng enqueue nhẹ, bounded/nonblocking. Input là review_id và feedback/version thực đã lưu. Không đọc/copy ảnh hoặc train trong HTTP handler.
- Worker nền riêng xử lý copy ảnh/provenance/dataset draft; không chạy trong pipeline. Queue đầy/lỗi phải có metric/log và recovery, không làm mất feedback đã lưu.
- Reconciliation theo định danh/version/cursor bền vững từ feedback nguồn; scan batch hữu hạn ở worker ngoài hot path. Không chỉ theo timestamp có thể trùng hoặc bỏ lượt.
- Replay/idempotency không nhân sample. Nhãn sửa lần hai supersede nhãn cũ trong draft, giữ history; dataset frozen cũ bất biến, tạo version mới.
- `correct` chỉ dùng proposal được người duyệt xác nhận; `incorrect` cần corrected text hợp lệ; `unreadable/not_plate/wrong_association` không thành nhãn OCR suy đoán. Mẫu ghép sai loại khỏi train-ready.
- Không kích hoạt training tự động sau mỗi click. Lưu feedback → chuẩn bị dataset là bước riêng với training.

**Đạt E1:** browser/API save thật → worker thu ảnh/nhãn đúng; replay, stale409, queue đầy, worker lỗi/crash/restart đều không mất lịch sử hoặc làm endpoint chậm. Task 1 hook được áp và Task 2 kiểm qua app thật.

## 3. E2 — Sửa ảnh thật, bbox, provenance và portable import/export

Lỗi đã tái hiện: export sample thiếu crop vẫn ra ZIP chỉ manifest/README. Import ảnh PNG thật ghi sample nhưng crop_path=None; ảnh chỉ còn trong preview staging, chưa là asset dataset ổn định. `crop_media_id` không mặc định là tên file.

- Resolve media bằng ID→record/path phía server qua adapter có quyền và containment đúng; copy ảnh nguồn thật vào asset root dataset. Lưu hash, dimensions, đường dẫn tương đối và provenance camera/run/epoch/frame/encounter.
- Editor hiển thị ảnh thật đã decode; sửa chữ và box trên đúng hệ tọa độ ảnh gốc. Lưu optimistic version, idempotency/history; stale409 refetch. Không dùng placeholder thành bằng chứng đã label.
- Export ảnh + nhãn + manifest/hash đầy đủ, không lộ secret/đường dẫn cá nhân không cần thiết. Thiếu ảnh: fail train-ready hoặc gói partial nêu rõ từng sample, không âm thầm PASS.
- Import preview/diff/hash/decode/version; apply copy ảnh vào root bền vững rồi commit metadata có đường dẫn hợp lệ. Sau dọn staging, trainer/export vẫn đọc ảnh được. Preview và apply dùng cùng artifact/hash; lỗi copy không để metadata giả.
- Idempotency import bền vững; cùng gói nhập lại không nhân sample/dataset ngoài ý muốn. Nhãn cũ không ghi đè nhãn mới; corrected labels tạo version/history đúng. Không sửa ảnh pixel để làm nhãn đã đoán trông rõ hơn.
- Sửa ZIP guard: Unix `create_system=3` không phải symlink. Kiểm file mode thực; kiểm containment bằng resolve/relative-path, không `startswith`. Giới hạn file count/uncompressed bytes/ảnh giải nén và dọn staging riêng đúng phạm vi.

**Đạt E2:** vòng thật sửa nhãn→export→import sang thư mục/DB khác→dọn preview→load ảnh/train/export lại giữ ảnh/nhãn/hash. Test Windows/Linux ZIP thường, traversal/symlink/oversize, ảnh giả/mất/hash sai, import lặp và conflict nhãn. Không test manifest-only rồi gọi portable PASS.

## 4. E3 — Freeze/split và dữ liệu đủ tin cậy

- Freeze snapshot ảnh/nhãn/mapping/config/hash bất biến; job chỉ đọc snapshot đã kiểm toàn vẹn, không đọc dataset draft đang sửa.
- Train/val/test 70/15/15 theo video/phiên/encounter; hai góc cùng lượt vào cùng tập. Dedupe exact/near frame trong cùng nguồn; policy biển lặp rõ để không rò dữ liệu. Test set độc lập, không dùng để chỉnh ngưỡng/fine-tune rồi vẫn gọi holdout.
- Crop/chữ OCR khác bbox detector; mũ gán đầu có/không/unknown, không lấy box mũ treo làm đang đội. Hành vi theo đoạn video; gương review-only nếu thiếu góc nhìn.
- Kiểm nhãn tự sinh toàn bộ, rà lần hai ít nhất 20% và mọi mẫu khó. Mờ/chói/khuất ghi unknown, không ép chữ dựa roster hoặc “AI suy luận”.
- Augmentation train-only, hợp lý và giữ target thật; ảnh synthetic phải tách provenance, không dùng làm ground truth nghiệm thu camera.
- Kiểm kê video tranning qua Task 1; thu mẫu tốt native/resolution và nhiều thời điểm. Không tạo ảnh sắc nét giả để tuyên bố đã khôi phục ký tự mất.

**Đạt E3:** freeze/trainer phát hiện chỉnh snapshot/hash sai, leakage và nhãn thiếu. Số lượng mẫu/nguồn/holdout được báo thực; thiếu dữ liệu giữ PENDING_DATA, tiếp tục collector/editor/tests.

## 5. E4 — Sửa queue và điều phối tài nguyên

Lỗi đã tái hiện: hai job queued cùng target chặn nhau; waiting_resource không resume vì runner chỉ nhận queued. Lock in-process và count theo target chưa quản GPU dùng bởi Task 1/runtime hoặc process khác.

- Job queued/waiting không chiếm lease; worker claim job theo thứ tự công bằng. Acquire tài nguyên nguyên tử và có giới hạn một training job trên GPU mục tiêu, kể cả các target khác nhau.
- Nối cơ chế tài nguyên dùng chung đã bàn giao Task 1; không chạy training khi Task 1 benchmark/ca camera chưa có ngân sách. CPU collector/UI/tests vẫn chạy độc lập.
- Resume waiting, heartbeat, timeout/recovery sau crash, retry giới hạn; job cancel phải dừng runner/subprocess thật và giải phóng lease, không chỉ đổi DB status.
- Worker có start/stop bounded theo app lifecycle do Task 2 tích hợp. Nút tạo job UI phải thật sự được worker xử lý, không nằm queued mãi.
- Giữ kiến trúc local đơn giản; chưa thêm microservice chỉ để giải quyết queue.

**Đạt E4:** hai/ba job queued lần lượt chạy, target khác nhau không cùng chiếm GPU; resource busy→waiting→resume; concurrent process claim chỉ một; cancel/crash/restart không orphan hoặc khóa GPU vĩnh viễn.

## 6. E5 — Training thật, ưu tiên OCR biển

- Chọn runner phù hợp engine/label đang dùng. Đọc tài liệu chính thức của trainer và kiểm dependency trong môi trường tách biệt; không nâng dependency trên runtime đang phục vụ camera.
- Plate detector training dùng bbox; OCR training dùng ảnh/chữ chuẩn và trainer nhận dạng chữ tương thích runtime; character detector cần box ký tự, không suy ra từ chuỗi chữ chung. Huấn luyện detector box không được gọi là cải thiện đọc chữ OCR.
- Nếu chưa có trainer OCR được hỗ trợ, hiện chưa khả dụng và triển khai adapter/trainer thật; không đánh dấu completed bằng `readtext()` hoặc `_simulate_train`.
- Runner thật tạo optimizer/loss/checkpoint/log/model hash/config/dataset hash và metrics. Smoke thật tối thiểu phải chạy optimization và tạo artifact loadable, khác simulation lifecycle; không dùng smoke để xét quality/promotion production.
- Evaluation chạy inference trên holdout thật, không lấy label thành prediction. Đo exact whole-plate OCR, CER, abstention/coverage, trường hợp khó và regression cũ; detector/mũ có chỉ số phù hợp riêng.
- Dùng cấu hình phù hợp 4 GB VRAM, budget đã đo và lịch GPU; không tối đa GPU bằng cách làm video lag/OOM. Có progress/error/cancel thật.

**Đạt E5:** ít nhất pipeline trainer được triển khai có test/smoke optimization thật và checkpoint loadable; khi đủ dữ liệu/GPU chạy baseline/candidate đối chứng. Chưa đủ dữ liệu quality vẫn PENDING, không giả train hoặc kết quả.

## 7. E6 — Chặn promotion giả, rollback đúng

Lỗi đã tái hiện: candidate trỏ file không tồn tại, không metrics vẫn promote active. UI truyền null bỏ kiểm tra. Rollback hiện chỉ retire, chưa chọn lại baseline/runtime.

- Server kiểm artifact tồn tại/hash/mapping/runtime contract; job thực completed và evaluation độc lập lưu server đúng dataset/config/model hash. Không tin metrics từ client; không cho omission bỏ gate.
- Candidate simulation/test/nonexistent/thiếu evaluation không eligible. Không baseline/evaluation đủ thì chưa promote, không mặc định đạt.
- So baseline và tiêu chí chất lượng/latency từng target; không chỉ improvement tương đối khi cả hai dưới ngưỡng. Với nhánh OCR tối thiểu 30 biển rõ để báo accuracy; báo số mẫu/lỗi/coverage, không “100%” từ 1/1 smoke.
- Tách candidate eligible/selected/pending_runtime/applied/failed phù hợp contract. Chỉ báo applied khi Task 1 load xác nhận trên cấu hình QA/được phép. Không tự ghi đè active weights.
- Lưu baseline trước đó; rollback chọn lại artifact/config đúng và nhận ack runtime. Fail apply giữ model cũ. Lịch sử nhận diện/bằng chứng không bị viết lại.

**Đạt E6:** smoke/nonexistent/hash sai/mapping sai/metrics thiếu/client giả bị chặn; candidate hợp lệ QA đi qua contract; apply failure giữ baseline; rollback trả baseline thật, không chỉ DB active=null.

## 8. E7 — Regression, tài liệu và đóng phần khả thi

Tạo/cập nhật `CLOSURE_TODO.md`, todo/EXECUTION_LOG/ACCEPTANCE_REPORT, CONTRACTS/OWNERSHIP và integration patches; không xóa lịch sử. Đính chính mọi PASS simulation, thiếu ảnh và routing đã có.

Focused test sau mỗi lát, toàn Task 3 sau checkpoint. Handoff Task 2 browser API thật và full regression chung. Dùng venv cố định, root QA mới, không pollute env/module hoặc ghi staging/metrics vào data live. Trước kiểm thử reset chỉ trạng thái QA do mình tạo.

Checklist:
- [ ] E0 status và baseline đúng.
- [ ] E1 save feedback→collector/worker không chặn, hook Task 1 tích hợp.
- [ ] E2 ảnh/box/version/export/import bền vững đạt round-trip thật.
- [ ] E3 freeze/split/provenance/leakage đạt.
- [ ] E4 queue/lease/resume/cancel/crash đạt.
- [ ] E5 trainer thực/optimization/checkpoint; quality thiếu ghi rõ.
- [ ] E6 promotion/rollback gates đúng.
- [ ] E7 Task 3 tests và browser integration qua app thật; shared patches đã bàn giao.

Mục tiêu cuối: người dùng xem crop → tích đúng/sai hoặc sửa chữ/box → dataset chuẩn → training có kiểm chứng → candidate tốt hơn → áp dụng có rollback. Sửa nhãn không làm model học ngay và không cho phép đoán chữ trên ảnh mất chi tiết. Chỉ báo model tốt hơn sau đánh giá độc lập. Không hỏi tiếp tục sau từng đợt; thiếu nhãn/thiết bị thì nêu đúng phần cần người dùng và hoàn tất phần còn lại.
