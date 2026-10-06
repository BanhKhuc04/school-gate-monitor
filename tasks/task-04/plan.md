# TASK 4 — Điều phối Task 1/2/3 và nghiệm thu tích hợp School Gate Monitor

## 1. Nhiệm vụ được giao

Bạn tiếp quản Codex làm người quán xuyến dự án: theo dõi Task 1/2/3, review mã/test/report, xác định lỗi thật, giao việc rõ theo ownership, quản tích hợp và chốt nghiệm thu. Đây là yêu cầu thực thi liên tục, không chỉ lập kế hoạch hay nhắc user liên tục “cho tiếp tục”.

Đọc `HANDOFF_FROM_CODEX_2026_10_02.md` trước. Giữ scope/mục tiêu/cấu hình đã chốt; không bắt đầu refactor toàn hệ thống, chuyển kiến trúc hoặc auth khi chưa có nhu cầu đo được.

Bạn có thể giao yêu cầu công việc cho đúng Task1/2/3 trong scope School Gate Monitor khi có kênh/identity thực. Không tự tạo task trùng. Nếu tools không thấy Cursor task, quản qua docs/log/patch và đưa dispatch cho user; không tuyên bố đã gửi. Không nhắn người ngoài dự án qua email/Slack.

## 2. Quyền và nguyên tắc phối hợp

- Task4 sở hữu docs `tasks/task-04/*`, triage, dependency, quality gate và báo cáo tổng.
- Task1/2/3 tiếp tục giữ mã thuộc scope. Task2 là integration owner shared hiện tại. Task4 chỉ áp/sửa shared sau owner bàn giao và ghi nhận quyền; không ghi đè đang sửa.
- Một file/một writer; diff snapshot trước/sau mỗi patch, không reset/stash/clean/untracked cleanup toàn tree.
- Các phần riêng chạy song song; migration/shared patch/GPU/full-suite chạy theo lịch tuần tự. Không ba full suite hay hai GPU benchmark/training cùng lúc.
- Tài liệu cũ có thể sai; mã/test/log mới có provenance là nguồn xác minh. Mỗi lỗi chỉ đóng khi có test hành vi và handoff đã áp, không “patch đã viết” là resolved.
- Không giảm test/threshold để PASS. Không đổi assertion thành config hiện tại khi config làm sai requirement; phân biệt fixture lỗi với production lỗi bằng tái hiện.
- Không nâng dependency runtime/live, thay RTSP/exposure/firmware/model/config ca đang chạy, xóa DB/media/model/video/log người dùng hoặc push/deploy.
- Giữ login autofill và teacher demo theo yêu cầu; auth-hardening đã defer. Scope dữ liệu vẫn phải đúng.

## 3. F4.0 — Tiếp quản có chứng cứ (scope nhỏ: docs và snapshot)

1. Ghi HEAD/branch/git status ngắn, versions thực cài và các task files mới. Không liệt kê recursive toàn bộ pytest/media tree.
2. Đọc handoff, latest prompts/log/acceptance, ownership và actual source/tests. Kiểm thread/process thật nếu có tool; không suy active từ file update hoặc reportDONE.
3. Tạo `STATUS_BOARD.md` gồm issue_id, severity, owner, file, requirement, reproduction, snapshot/run, state, next action và dependency. Dedup lỗi lịch sử đã sửa.
4. Ghi shared-file ownership trong `INTEGRATION_LEDGER.md`, ai nhận file/khi nào/patch/checks.

**Đạt:** có bảng tiến độ thực của ba task, phân biệt reported/verified và lỗi còn tái hiện. Không đòi user gửi lại toàn bộ chat đã có handoff.

## 4. F4.1 — Chặn ba blocker Task3 trước bàn giao (đọc/repro/giao sửa)

Đọc `tasks/task-03/PRE_INTEGRATION_FIX_PROMPT_2026_10_02.md`.

- Contract feedback không dùng echo expected_version làm saved_version; dùng feedback_id/review_id hoặc additive committed saved_version chuẩn. Worker/cursor đọc DB version thật. Task1 hook sau save success, không conflict.
- Worker dispatch thống nhất runner interface; process_once thực ba target, pending/unsupported đúng, waiting resume/cancel/lifecycle thật.
- Promotion require trained/loadable artifact, SHA256 thực, completed operation, evaluation provenance + quality gates; reject OCR0%/queued/no baseline invalid, preserve baseline và runtime ack.

Task3 tiếp tục phân biệt baseline evaluator và optimization trainer: evaluator marker chỉ đính chính status, chưa đạt training người dùng cần. Detector/helmet placeholder chưa training. Không báo chỉ cần labels thì model học ngay khi thiếu runner.

**Đạt:** owner thêm test đỏ→sửa→test xanh cho hành vi từng blocker; contract/lifecycle patches mới nhất không trái nhau. Task4 kiểm lại bằng phép thử độc lập QA trước cho tích hợp.

## 5. F4.2 — Task1 runtime và Task2 UI/API (hai scope độc lập)

### Task1 checkpoint

Kiểm runtime block AI 2–3s nhưng nhiều frame/JPEG mới vẫn tiến; frame_seq nguồn thực và overlay TTL. OCR/rear không person, model mũ mapping/hash đúng, temporal/association/crossing và media-before-audio. Test không chỉ grep source. Các lỗi log cũ về backup/cleanup không giữ blocker nếu test mới đạt.

### Task2 checkpoint

Giữ R3 backup đã có37 test và cleanup/media teacher25 test làm baseline, rerun khi code đổi. UI E2E mock đầy đủ nhãn/route đúng, teacher fixture đúng. Browser API thật đủ roles/scope/media/Range/deep links/filter/version/CSV/upload/restore. CI test mode thật không startup camera/CUDA chỉ vì router.

**Đạt:** mỗi owner bàn giao code/test/log/snapshot; shared patch được nhận đúng owner, test mock không gọi là production integration.

## 6. F4.3 — Tích hợp một lát xuyên hệ thống

Task2 áp patch đã review trong snapshot ổn định; Task4 verify. Thứ tự:
1. Feedback API save→hook metadata đúng→collector background không chặn.
2. Collector lưu crop/label/provenance/history đúng vào draft; retry/queue đầy/restart không mất review; source flat/mediaID thực đúng.
3. BBox/OCR correction optimistic version; export/import sang root khác vẫn đọc ảnh sau cleanupstaging; freeze/split không leakage.
4. UI create job→worker→pending/evaluate/train đúng operation→metrics/artifact→candidate gate→pending_runtime; applied/rollback chỉ khi Task1 QA ack.
5. Startup/shutdown worker có giới hạn, init training DB đúng, default không auto train trong ca live, metrics/lỗi nhìn thấy.

**Đạt:** integration test production factory QA và browser API thật chứng minh luồng, không tất cả responses intercept/mock. Thiếu dữ liệu không ngăn test plumbing; training thật/quality có trạng thái riêng.

## 7. F4.4 — Regression cuối trên snapshot ổn định

Chuẩn bị rootQA mới và mọi config bindings DB/media/backup/recording/training/assets. Không dùng appDB/camera thật. Dùng venv cố định, basetemp UUID mới (không thư mục task khác), backup fixture nhỏ. Theo dõi diskfree/log processes riêng; không xóa rộng temp user.

Full backend:

```powershell
.\venv\Scripts\python.exe -m pytest app/tests -p no:cacheprovider --tb=short -q
```

Thêm basetemp mới/configQA đúng khi chạy thực. Không ignore/deselect để bỏ failure. Focused được chọn test, ghi focused. Skip có lý do cụ thể, không skip flow quan trọng vì init model thật.

Frontend từ thư mục frontend, kiểm exit code mỗi bước:

```powershell
npm run lint
npm run build
node --test test/*.test.mjs
npx playwright test
```

Tách UI mock/API integration, test bản frontend build + production factory với QA secret hợp lệ. Refresh SPA đúng; API404 JSON; media có quyền. Health401 không là full readiness. Không dùng test missingsecret làm toàn bộ production-route proof.

Lưu run ID/lệnh/env được che/log exit/version/hash/start-end/source snapshot. Nếu mã thay trong run, đánh dấu superseded và rerun phần ảnh hưởng/suite cần thiết saufreeze. Lỗi tooling ghi rõ, thử process mới; không tuyên bố tất cảPASS từ run bị abort hoặc outputtruncated.

**Đạt:** fullsuite/node/lint/build/browser/production đủ gate và không còn softwareblocker. Không fix một reportcount dự kiến; báo count cuối thực.

## 8. F4.5 — Video, nhãn và nghiệm thu thiết bị

- Task1 dùng runtime thật với inventory mọi video tranning, EOF/toàn timeline và coverage; DB/media QA. Harness __new__/Worker riêng chỉ componentbenchmark, không acceptance cảpipeline.
- Runtime hai nguồn30 phút, đoạn1/2/3viewer, frames mới/displayAIlatency/queue/dropCPU/RAM/VRAM và GPU đo đúng. Không torchallocated=utilization hoặc detecttime=camera→screen.
- Task3 chuẩn bị người dùng sửa labels trên ảnh rõ: ≥30 biển rõ riêng testOCR, ≥50violation/50clean và nhánhgương/ghép có bộ riêng. Training/val/test táchnguồn, không train holdout rồi nhận qualitytest.
- Trainer thật chạy sau GPUlease/lịch có; baseline/candidate cùng holdout/config và runtimebudget. Blur mất chữ không đoán roster/AIsharpen thành nhãn thật.
- Ca12 giờ Imou/LAN/RPO/RTO chỉ khi có thiết bị/lịch được phép. Không tự coi hardwarepending chặn fix UI/collector/API.

**Đạt:** tất cả mục có trạng thái VIDEO_MEASURED/HARDWARE_ACCEPTED hoặc PENDING cụ thể, không hạ ngưỡng chốt trong handoff.

## 9. F4.6 — Đóng và giữ ngữ cảnh cho lần tiếp tục

Task4 duy trì `todo.md`, `STATUS_BOARD.md`, `INTEGRATION_LEDGER.md`, `EXECUTION_LOG.md`, `ACCEPTANCE_REPORT.md`, `NEXT_ACTIONS.md`.

`NEXT_ACTIONS` ngắn nhưng đủ resume: code snapshot, current owner/claim, issue còn mở, lệnh/run mới nhất, logpath, next concrete3 actions, dữ liệu cần user. Đọc nó sau compaction/newsession, không restart từđầu hoặc hỏi “làm tiếp không”.

Tổng báo cáo `docs/FINAL_SOFTWARE_INTEGRATION_ACCEPTANCE_2026_10_02.md` phối hợp Task2, không haiwriter; tách software/readiness/quality/hardware. Không overwrite loglịch sử hoặc sửa PASS giả không đính chính.

## 10. Cách giao tiếp và điều kiện dừng

- Update ngắn khi có finding/đổi hướng/checkpoint, theo giới hạn giao tiếp của môi trường. Không spam báo đang đọc/source. Không hỏi confirm thường lệ đã được giao.
- Nếu user hỏi tiến độ, trả ngắn rồi tiếp tục công việc; không hiểu mọi câu hỏi như hủy việc.
- Nếu task Cursor dừng chỉ đọc, dispatch nêu file/issue/test/acceptance và yêu cầu thực thi, không chỉ “tiếp tục” chung chung.
- Không nhận taskDONE khi patch chưaáp, test cấu trúc thay testhành vi, bỏtest hoặc metricskhôngđại diện. Reopen đúng issue, không kết luận toàn repo “không dùng được” từ mộtfixture.
- Khi thực sự thiếu nhãn/camera/account/lease/filewriter, ghi pending rõ và vẫn làm độc lập; chỉ hỏi user phần ngoài khả năng. Không hứa tự chạy nền sau turn nếu môi trường không hỗ trợ.
- SOFTWARE_DONE khi tất cả software gates thật đạt. MODEL_QUALITY_ACCEPTED và HARDWARE_ACCEPTED khi có phép đo riêng. User muốn “done hết” không cho phép gộp ba trạng thái.
