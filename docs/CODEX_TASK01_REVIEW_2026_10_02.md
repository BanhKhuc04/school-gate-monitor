# Review TASK 1 — 02/10/2026

## Kết luận

**REQUEST CHANGES — chưa thể chấp nhận báo cáo “Task 1 hoàn thành đầy đủ”.**

Có cải tiến và test mới, nhưng còn lỗi trong luồng thực, helper chưa có runtime caller, và test đang chấp nhận hành vi trái tiêu chí. Chưa nghiệm thu nhận diện/độ mượt trên hai camera. Review này không sửa mã ứng dụng hoặc tài liệu kết quả của Task 1/Task 2.

## Kiểm chứng đã thực hiện

- Interpreter: `venv/Scripts/python.exe`, Python 3.11.9, Windows.
- Chạy lại bảy file `test_task01_phase0_metrics.py` đến `test_task01_phase6_gpu_profiler.py`: **159 passed, 1 warning, 35.79s**.
- DB test trỏ APP_DB_PATH vào thư mục tạm riêng; pytest cache tắt. Không mở model/camera thật hoặc chạy maintenance trên dữ liệu vận hành.
- Chưa chạy lại toàn bộ 342 test hoặc full suite của toàn repository. 342 PASS là báo cáo của bên triển khai, không phải kết quả review đã tự chạy đủ.
- Ca bổ sung dùng dữ liệu trong bộ nhớ, module thuần/helper thực và AST lấy nguyên block từ pipeline; không ghi DB/media vận hành. Ca AST không thay thế integration test live loop.

## F01 — P0: camera rear/ocr_only lỗi ở vòng detect thực

`app/cv/pipeline.py` phần init đặt `_person_detector=None` khi profile không phải full, nhưng dòng 1585 luôn gọi `_person_detector.detect_tracked`.

Tái hiện biểu thức dispatch thực với profile rear: `AttributeError: 'NoneType' object has no attribute 'detect_tracked'`.

Profile minimal cũng có `_detect_pool=None` nhưng loop và stop dùng pool không có guard tương ứng. Exception xử lý AI nằm chung nhánh reconnect camera, nên lỗi phần mềm có thể kéo camera vào reconnect không cần thiết.

**Cần sửa:** dispatch theo capability thực; rear phải có đường vehicle/plate tracking đủ để OCR không phụ thuộc person. Minimal có hành vi rõ ràng. Integration test chạy loop thật với capture/detector giả theo từng profile, không chỉ assert config là số dương.

## F02 — P1: hình hiển thị vẫn chờ inference

`start()` tạo một thread `_run_loop`; trong loop chờ `person_future.result()`, các detector khác và pose trước khi `_publish_frame_jpeg` ở finally (dòng 1785). Capture có luồng riêng giúp đọc hình mới, nhưng JPEG mà viewer nhận vẫn được xuất từ luồng AI.

**Cần sửa:** preview/encode có nhịp độc lập với AI/pose/OCR/DB; cùng frame chỉ encode một lần, overlay có epoch/TTL. Test chặn Future detector và quan sát JPEG seq/timestamp vẫn tiến từ capture, không chỉ gọi trực tiếp helper publish.

## F03 — P1: multi-frame OCR chưa được nối thành đường quyết định

`_observe_best_plate` (1171) vẫn chỉ trigger OCR khi có gate line và điều kiện approaching/imminent. BestPlateStore chỉ một attempt mỗi track; `offer()` bỏ crop mới khi đã attempt.

`consensus_decide()` có helper nhưng chưa được dùng để quyết định kết quả chính trong live pipeline. Consensus ingest chủ yếu nhận một kết quả từ BestPlateStore. `resolve_plate()` vẫn có thể đánh dấu confident từ một crop.

Tái hiện BestPlateStore thật với worker giả:

```text
one_crop.is_confident = True
one_crop.sample_count = 1
second_crop_accepted = False
second_ocr_started = False
```

**Cần sửa:** scheduling bounded 3–5 crop khác frame, OCR bắt đầu khi ảnh đủ chất lượng dù không có line/person/crossing; chỉ consensus đã xác nhận mới dùng lookup/gán học sinh. Technical retry không thành mẫu mới. Test xuyên luồng hai frame/crop thật qua worker giả và observing API/card, không chỉ gọi `_consensus_ingest` thủ công hai lần.

## F04 — P1: consensus chấp nhận đối chứng mạnh và crop chất lượng 0

`PlateConsensusStore.decide` chỉ từ chối nếu ít nhất hai nhóm đều đủ MIN_AGREE. Một kết quả khác confidence cao chưa đủ hai phiếu bị bỏ qua. Quality được tính trung bình nhưng không có điều kiện loại trong decide/ingest.

Tái hiện:

```text
A(conf=.8), B(conf=.99), A(conf=.8) => decide A, 2 samples
hai mẫu quality_score=0 => decide A, 2 samples
```

**Cần sửa:** chính sách competitive evidence/quality rõ ràng, không tự xác nhận khi có kết quả cạnh tranh đáng tin. Chỉ tính crop hợp lệ của frame độc lập, trạng thái mâu thuẫn cần kiểm tra; kiểm tra cap/TTL và không eviction nhầm track đang cập nhật khi đạt max_tracks.

## F05 — P1: crossing vẫn chốt sau khoảng trống 17 giây

`transition_started_at` ở crossing.py:231 bắt đầu từ frame đầu ở phía đích, không kiểm khoảng trống kể từ quan sát phía đầu.

Tái hiện: A tại 1000.0/1000.1/1000.2, B tại 1017.1/1017.2/1017.3 => `[False, False, True]`.

Test `test_17_seconds_gap_no_cross` dùng ba frame B cách nhau sáu giây, chỉ kiểm target-side accumulation kéo dài, không tái hiện khoảng trống 17 giây rồi B liên tiếp.

**Cần sửa:** TTL/mất liên tục và giới hạn transition từ quan sát phía đầu phù hợp; reset/rearm đúng. Thêm ca 17 giây gap rồi ba B liên tiếp, dead zone, duplicate frame, camera switch. 3+3 ngắn vẫn phải đạt.

## F06 — P1: posture temporal là state toàn camera, chưa bảo vệ từng lượt xe

`pipeline.py:2757` lấy mode posture của mọi group rồi lưu một deque toàn pipeline. `_posture_confirmed` chỉ được expose vào status, chưa được dùng thay posture từng group trong nhánh quyết định. Ledger không kiểm agreement >=80%, khoảng mẫu >=100ms/span >=400ms theo hợp đồng; hết mẫu vẫn giữ state cũ.

Tái hiện block thực: hai track, mỗi track chỉ hai mẫu RIDING => state chung RIDING; khi hết toàn bộ window, state vẫn RIDING và số mẫu 0.

**Cần sửa:** bằng chứng theo camera/epoch/encounter/track; dùng kết quả đúng nhóm vào quyết định. Unknown/expired trả trạng thái chưa xác định thích hợp. Test gọi phương thức thực cho hai xe và mâu thuẫn, không sao chép Counter logic vào test rồi chỉ assert trên bản sao.

## F07 — P1: late issue đang overwrite, không merge và không phân phối update

`dispatch_late_issues()` (1280) serialize danh sách mới rồi gọi `update_violation_issues`, là thao tác thay toàn bộ issues_json. Không tăng event version hoặc publish update cho viewer.

Tái hiện helper thực với DB adapter giả: ban đầu NO_HELMET, cập nhật muộn chỉ RIDING_THROUGH_GATE => còn duy nhất RIDING_THROUGH_GATE.

**Cần sửa:** merge theo mã lỗi/người/bằng chứng đúng hợp đồng, giữ issue đã xác nhận, atomic/versioned, phát event update. Không phát lại lỗi cũ; lỗi mới thật sự cần lời nhắc được xử lý theo TTL/lease/audio contract. DB update trả False phải được xử lý, không báo thành công.

## F08 — P1: matcher mới chưa tích hợp và có điều kiện ghép không an toàn

GateEventMatcher chỉ được khởi tạo và expose status; không có runtime caller `.match()` trong pipeline. `_try_correlate()` vẫn gọi correlator cũ.

Khi bật matcher và gọi trực tiếp:

```text
cùng biển/hướng, cách 30 giây => matched
hai ứng viên cùng biển/hướng => matched (ứng viên đầu)
ứng viên khác gate_id => matched
```

Nhánh exact return ngay trước ambiguity check, không enforce thời gian/same gate/camera role. Direction `unknown` ở cả hai bên cũng có nguy cơ được coi cùng hướng vì chỉ so equality. Bbox hai camera không cùng hệ tọa độ, không được dùng overlap trực tiếp nếu chưa hiệu chỉnh chung.

**Cần sửa:** hard gates trước scoring; đánh giá toàn bộ ứng viên rồi loại ambiguity, chỉ nhận biển confirmed, lane/hướng theo calibration. Nối runtime với feature flag mặc định OFF và chứng minh OFF không chạy nhánh ghép cũ ngoài chính sách.

Test `test_beyond_window_no_match` đang assert matched, `test_two_equal_candidates_ambiguous` cho phép cả matched/ambiguous. Phải sửa về hành vi yêu cầu và test strict. Thiếu calibration được phép giữ OFF, không đồng nghĩa thiếu runtime wiring được coi hoàn thành.

## F09 — Chưa đủ bằng chứng: Phase 6 và bàn giao

- GPU profiler/runtime snapshot không phải benchmark 30 phút. CUDA available/config fp16 không chứng minh từng model/input thực chạy trên GPU/FP16.
- Chưa có số đo hai nguồn cách ly: FPS hình mới/AI, p95 latency, RAM/VRAM đầu/cuối, fairness, frame/job bỏ.
- Chưa thấy ACCEPTANCE_REPORT.md và HANDOFF.md riêng Task 1; có thể lập báo cáo PENDING ngay, không cần đợi mọi task commit hoặc cùng ghi docs chung.
- Full regression sau tích hợp Task 2 và nghiệm thu Imou/ca 12 giờ còn pending. Commit không phải điều kiện duy nhất để chạy regression; cần snapshot tích hợp ổn định và phối hợp người đang sửa.

## Phần có tiến bộ

- Có buffer metrics và JPEG cache, generation guard đầu persistence, kiểm tra mapping/hash mũ.
- Crossing đã đòi ba frame phía đích cho lượt ngắn.
- Matcher mới mặc định tắt, profiler có giới hạn sample.
- Bảy file test mới hiện đều pass và có log/checklist từng phase.

Đây là nền tảng để sửa tiếp, chưa là bằng chứng các chức năng hoàn chỉnh đã chạy đúng.

## Thứ tự vá đề xuất cho chủ Task 1

1. F01 runtime rear/minimal và F02 preview độc lập AI.
2. F03/F04 scheduling OCR multi-crop, đường xác nhận và competitive evidence.
3. F05 crossing timeout, F06 temporal theo track, F07 issue merge/version/update.
4. F08 matcher strict + runtime flag OFF an toàn; không bật auto-match khi chưa nghiệm thu.
5. Sửa test đang chấp nhận lỗi; chạy targeted và regression trên snapshot tích hợp ổn định.
6. Benchmark hai nguồn cách ly 30 phút; lập ACCEPTANCE_REPORT/HANDOFF riêng; nghiệm thu thiết bị thật sau khi phần mềm ổn.

Không hạ ngưỡng, không đổi camera/model/DB/media vận hành để làm báo cáo đạt. Các đề xuất này thuộc review; chưa được triển khai trong lượt này.
