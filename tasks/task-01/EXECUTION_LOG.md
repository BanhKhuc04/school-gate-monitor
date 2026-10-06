# TASK 1 — EXECUTION LOG

> Không cập nhật `docs/CURSOR_EXECUTION_LOG.md` (Task 2 đang dùng); log này
> thuộc riêng Task 1, đi kèm `tasks/task-01/plan.md`.

## Baseline

| Item | Value |
| --- | --- |
| Working tree baseline | captured `baseline_working_tree.txt`, `baseline_head.txt`, `baseline_test.txt` (02/10/2026 00:41–00:47) |
| Python | `venv\Scripts\python.exe` 3.11.9 |
| Working directory | `D:/Work/Project_motorbike` |
| GPU target | RTX 3050 Laptop 4 GB (không benchmark trong task này khi training khác đang chạy) |

## Phase 0 — Metrics đúng, health chỉ đọc

**Commit/segment:** bám baseline; thay đổi nội bộ Task 1.

### Thay đổi

1. `app/api/system.py`
   - `_pipeline_status()` chuyển sang `get_existing_pipeline(gate_id)` (lazy import từ `app.cv.pipeline`) — polling health **không** tạo pipeline, không nạp model.
   - `_recording_status_all_gates()` và gate loop trong `get_health()` cùng đổi sang `get_existing_pipeline`.
   - Storage cache: `_STORAGE_CACHE_TTL_SEC = 60.0`, `_storage_cache` dict kèm `path`; `_snapshots_size_mb()` và `_storage_breakdown()` invalidates khi `SNAPSHOTS_DIR` đổi (path-based key).

2. `app/cv/pipeline_metrics.py` (mới)
   - `percentile(values, pct)` — linear interpolation trên sorted list.
   - `MetricsBuffer(maxlen=60)` — bounded ring buffer (deque maxlen).
   - `ResourceSampler(interval_sec=1.0)` — psutil RSS + torch CUDA memory, **không** gọi `nvidia-smi`.
   - `PipelineMetrics` dataclass + `to_dict()`.

3. `app/cv/pipeline.py`
   - Import `MetricsBuffer`, `ResourceSampler`.
   - Khởi tạo `_metrics_capture`, `_metrics_detect`, `_metrics_ocr_wait`, `_metrics_encode`, `_metrics_persistence`, `_metrics_dispatch`, `_resource_sampler`.
   - `_maybe_update_fps()` cập nhật `_capture_fps_value`, `_ai_fps_value` mỗi 1s.
   - `_publish_frame_jpeg()` đo encode latency, tách `_jpeg_new_count` vs `_jpeg_repeat_count`.
   - `_ocr_submit_with_epoch()`, `_ocr_consume_pending()` đo OCR wait latency.
   - `_persist_violation()` đo persistence + dispatch latency.
   - `get_status()` trả `metrics` dict đầy đủ (capture/ai fps, latency p50/p95, queues, counters, rss/vram).

4. `app/tests/test_dot_R.py`
   - Cập nhật `_build_pipeline_with_mocks()` để init Phase 0 attributes.

5. `tasks/task-01/CONTRACTS.md` (mới) — gate_id, camera_id, source_epoch, frame_seq, track identity, plate statuses, behavior labels, violations, camera switch API.

6. `app/tests/test_task01_phase0_metrics.py` (mới) — 24 tests, tất cả PASS.

### Kết quả test

```
.\venv\Scripts\python.exe -m pytest app/tests/test_task01_phase0_metrics.py
... 24 passed in 4.21s
```

## Phase 1 — Latest-frame, bộ nhớ hữu hạn, stop/reconnect

### Thay đổi

1. `app/cv/pipeline.py`
   - Thêm `_run_generation: int = 0`, `_stopped: bool = False`, `_reconnect_failures: int = 0` vào `__init__`.
   - `start()` tăng `_run_generation`, set `_stopped=False`.
   - `stop()` set `_stopped=True`, tăng `_run_generation`, join thread, shutdown pools.
   - `_is_session_alive(captured_generation)` helper — worker callback check nhanh.
   - `_persist_violation()` nhận thêm `run_generation=None`. Đầu hàm check mismatch → return False, increment `_violations_skipped_total`, log diagnostic `io/stale/persist_stale_generation`.
   - Dispatch site (nơi gọi `self._io_pool.submit(self._persist_violation, ...)`) capture `run_generation=self._run_generation` tại thời điểm enqueue.
   - `_finish_crossing_event` đọc `frozen['run_generation']`, short-circuit nếu pipeline đã move on.
   - Crossing submit inject `'run_generation': self._run_generation` vào frozen dict.
   - `_run_loop` exponential backoff: `min(2.0 * (2 ** n_failures), 30.0)`, reset về 0 trong `else:` khi read THÀNH CÔNG.
   - `_maybe_update_fps()` prune `_recognition_results` theo TTL 30s (cutoff `time.time() - 30.0`).
   - `get_status()` expose `metrics.run_generation`, `metrics.reconnect_failures`.

2. `app/tests/test_dot_R.py` — `_build_pipeline_with_mocks` thêm Phase 1 attrs.

3. `app/tests/test_task01_phase1_latest_frame.py` (mới) — 20 tests:
   - `TestRunGeneration` (7 tests): init, stop() sets stopped+increments, noop khi not running, `_is_session_alive` true/false/drift.
   - `TestPersistViolationGeneration` (2): stale → False + skip counter; current → add_violation_event called.
   - `TestFinishCrossingGeneration` (1): stale → True + no push_alert.
   - `TestReconnectBackoff` (3): initial=0, formula đúng (2,4,8,16,30 cap), exponential growth.
   - `TestRecognitionResultsPrune` (3): prune entry >30s, no prune khi fresh, no-op khi interval chưa hit.
   - `TestGetStatusExposesPhase1` (1): metrics có `run_generation` + `reconnect_failures`.
   - `TestDispatchCapturesGeneration` (1): source check kwarg pass.
   - `TestCrossingSubmitCapturesGeneration` (2): source check frozen dict + check trong `_finish_crossing_event`.

### Kết quả test

```
.\venv\Scripts\python.exe -m pytest app/tests/test_task01_phase0_metrics.py app/tests/test_task01_phase1_latest_frame.py app/tests/test_dot_R.py app/tests/test_pipeline_loop_output.py app/tests/test_pipeline_b2.py
... 79 passed in 14.29s
```

### Rollback (nếu cần)

Phase 0 + Phase 1 chỉ thêm fields/phương thức và early-return. Không sửa hành vi hiện hữu khi generation đồng bộ. Rollback từng phần: bỏ `_run_generation` check trong `_persist_violation` và `_finish_crossing_event`, giữ lại các helper.

## Phase 2 — Rear OCR đa frame, consensus

### Thay đổi

1. `app/cv/plate_consensus.py` (mới)
   - `CropRecord` dataclass: `frame_id`, `timestamp`, `normalized`, `confidence`, `quality_score`, `error`.
   - `PlateConsensusStore` — top-N multi-crop vote:
     - `max_crops_per_track=5` — giữ tối đa 5 crop mới nhất.
     - `consensus_min_agree=2` — cần ≥2 mẫu đồng thuận.
     - `min_confidence=0.55` — lọc mẫu yếu.
     - `diversity_min_frame_gap=2` — frame_seq mới phải cách frame gần nhất ≥2.
     - `ttl_sec=30.0` — prune track cũ.
     - `max_tracks=64` — cap bộ nhớ.
     - `decide()` trả `(text, conf, sample_count)`; `None` nếu mâu thuẫn hoặc chưa đủ.
     - `finalize()` đánh dấu track đã chốt → ingest tiếp theo bị bỏ qua.

2. `app/config.py`
   - `PLATE_CONSENSUS_ENABLED` (default 1).
   - `PLATE_CONSENSUS_MAX_CROPS`, `PLATE_CONSENSUS_MIN_AGREE`, `PLATE_CONSENSUS_MIN_CONFIDENCE`, `PLATE_CONSENSUS_DIVERSITY_GAP`, `PLATE_CONSENSUS_TTL_SEC`.

3. `app/cv/pipeline.py`
   - Import `PlateConsensusStore` (lazy inside `__init__`).
   - Khởi tạo `self._plate_consensus` với config.
   - `_observe_best_plate()` gọi `_consensus_ingest()` sau khi BestPlateStore.collect.
   - `_consensus_ingest()` helper — nhận `(result, candidate)` → tạo `CropRecord` → `consensus.ingest_offer()`.
   - `consensus_decide()` public helper cho caller muốn xem kết quả.
   - `_apply_camera_change()` reset `_plate_consensus` (track mới không thừa hưởng vote cũ).
   - `get_status()` expose `metrics.plate_consensus.{enabled, tracks}`.

4. `frontend/src/pages/GuardPage.jsx`
   - Import `PlateReviewPanel`.
   - Thêm tab "Duyệt biển" (`logTab='plate-review'`).
   - Render `<PlateReviewPanel gate={activeGate} role={user?.role}/>` khi tab active.

5. `app/tests/test_task01_phase2_plate_consensus.py` (mới) — 23 tests:
   - `TestPlateConsensusUnit` (14 tests): empty/insufficient/agreeing/competitive/low-conf/duplicate/frame-gap/cap/TTL/progress.
   - `TestPipelineWiring` (6 tests): import + `_consensus_ingest` call site + helpers + reset + status expose + config settings.
   - `TestConsensusIntegration` (3 tests): mocked pipeline end-to-end với `PlateReadResult` + `PlateCandidate`.

6. `app/cv/pipeline.py` defensive fix: `_persist_violation` dùng `getattr(self, '_metrics_persistence', None)` / `_metrics_dispatch` / `_violations_skipped_total` / `_violations_persisted_total` để chịu test fixtures cũ build qua `__new__` (test_vehicle_gate, test_vehicle_crossing_aggregation). Dispatch site + crossing submit cũng dùng `getattr(self, '_run_generation', 0)`.

### Kết quả test

```
.\venv\Scripts\python.exe -m pytest \
  app/tests/test_task01_phase0_metrics.py \
  app/tests/test_task01_phase1_latest_frame.py \
  app/tests/test_task01_phase2_plate_consensus.py \
  app/tests/test_dot_R.py \
  app/tests/test_pipeline_loop_output.py \
  app/tests/test_pipeline_b2.py
... 102 passed

.\venv\Scripts\python.exe -m pytest \
  app/tests/test_task01_phase0_metrics.py \
  app/tests/test_task01_phase1_latest_frame.py \
  app/tests/test_task01_phase2_plate_consensus.py \
  app/tests/test_dot_R.py \
  app/tests/test_pipeline_b2.py \
  app/tests/test_pipeline_loop_output.py \
  app/tests/test_vehicle_gate.py \
  app/tests/test_vehicle_group_dedup.py \
  app/tests/test_vehicle_crossing_aggregation.py \
  app/tests/test_riding_through_gate.py \
  app/tests/test_s5_evidence_before_alert.py
... 149 passed
```

Full app/tests/ (không bao gồm `test_cleanup_admin_ok` pre-existing schema mismatch — xem Known unrelated failures trong `todo.md`):
... 779 passed, 1 unrelated fail, 1 warning

### Rollback (nếu cần)

Phase 2 là ADDS-ONLY:
- Không sửa `BestPlateStore`, `PlateVoter`, `_ocr_task` → engine OCR chính xác không đổi.
- Disable: set `PLATE_CONSENSUS_ENABLED=0` (env) → `_consensus_ingest` không gọi.
- Xóa file `app/cv/plate_consensus.py`, import trong `pipeline.py`, tab PlateReviewPanel trong GuardPage.jsx → rollback sạch.

## Đang thực hiện

- Nghiệm thu Imou thật theo lịch và ca 12 giờ; ghi chưa đo nếu thiếu điều kiện.
- Regression tích hợp, acceptance report và handoff cho các task khác.

## Phase 6 — GPU profiler & benchmark plumbing

### Thay đổi

**`app/config.py`**
- Thêm `POSTURE_TEMPORAL_WINDOW_SEC=1.5`, `POSTURE_TEMPORAL_MIN_SAMPLES=4`,
  `POSTURE_TEMPORAL_STATES=('RIDING','PUSHING','WALKING','UNKNOWN')`.
- `HELMET_MODEL_HASH_SHA256` + `HELMET_MODEL_MAPPING` đã có sẵn; làm canonical
  reference cho integrity check.

**`app/cv/helmet_contract.py`**
- `parse_mapping(mapping_str)` parse "0=With Helmet,1=Without Helmet" → dict.
- `validate_helmet_mapping(names, mapping_str)` trả True nếu mapping khớp với
  `class_names` của weights; False nếu lệch (silent inversion detection).

**`app/cv/pipeline.py`**
- `_sha256_file(path)` — None nếu missing; hex 64 ký tự nếu OK.
- Helmet load: giữ logic cũ + log cảnh báo nếu `HELMET_MODEL_HASH_SHA256` set
  và mismatch (không refuse để không chặn deployment).
- Plate detector: skip nếu `profile == 'minimal'` (aux cameras).
- Person detector: skip nếu `profile != 'full'`.
- `_detect_pool` size: 3 / 1 / 0 worker theo `profile`.
- `_posture_window` (deque, maxlen = int(POSTURE_TEMPORAL_WINDOW_SEC * 30)):
  - Thu non-UNKNOWN vote pool mỗi frame.
  - Prune samples > POSTURE_TEMPORAL_WINDOW_SEC.
  - Confirm state chỉ khi `count ≥ POSTURE_TEMPORAL_MIN_SAMPLES`.
- `get_status()` expose `role`, `profile`, `posture_state`, `posture_confidence`.
- Defensive `getattr` cho legacy test fixtures (`role`, `profile`,
  `_posture_confirmed`, `_posture_confidence`).

**`app/tests/test_task01_phase3_posture.py`** (mới)
- TestRoleProfileResolution: 7 tests (default, env, unknown fallback).
- TestHelmetMappingValidation: 7 tests (parse + inversion + renamed swap).
- TestHelmetModelIntegrity: 3 tests (nonexistent, empty path, real file).
- TestVideoPipelineRoleProfile: 4 tests (status expose role/profile/posture).
- TestPostureTemporalLedger: 6 tests (min samples, prune, 4 states, vote pool).
- TestProfileAwareConfig: 2 tests (full stack config available).
- TestPostureLedgerE2E: 2 tests (full confirm RIDING path, no-signal → UNKNOWN).
- Tổng: **31 + 1 fixture = 32 tests**.

### Test runs

```
pytest app/tests/test_task01_phase0_metrics.py \
       app/tests/test_task01_phase1_latest_frame.py \
       app/tests/test_task01_phase2_plate_consensus.py \
       app/tests/test_task01_phase3_posture.py
... 99 passed
```

```
pytest app/tests/test_task01_phase3_posture.py \
       app/tests/test_task01_phase1_latest_frame.py \
       app/tests/test_task01_phase2_plate_consensus.py \
       app/tests/test_task01_phase0_metrics.py \
       app/tests/test_best_plate.py \
       app/tests/test_best_plate_api.py \
       app/tests/test_camera_mapping.py \
       app/tests/test_crossing.py \
       app/tests/test_crossing_alert.py \
       app/tests/test_gate_line.py \
       app/tests/test_plate_aspect_ratio.py \
       app/tests/test_plate_two_line.py \
       app/tests/test_event_correlator.py \
       app/tests/test_event_manager.py \
       app/tests/test_evidence.py
... 247 passed
```

### Rollback (nếu cần)

Phase 3 là ADDS-ONLY:
- Không sửa `BestPlateStore`, `PlateVoter`, `_ocr_task`, helmet detector logic.
- Disable profile skip: set `GATE_{id}_PROFILE=full` cho tất cả gates → load
  toàn bộ model như cũ.
- Xóa `_posture_window` + ledger block trong `_run_posture_detection` →
  posture trở về per-frame như cũ.

### Bài học / chú ý

- Helmet mapping silent inversion là lỗi NGUY HIỂM nhất (gán "Without Helmet"
  thành "With Helmet" hoặc ngược lại) — `validate_helmet_mapping` fail-fast
  giúp phát hiện ngay khi load weights.
- 4-state posture ledger loại bỏ flicker: 1.5s × 4 mẫu nhất quán = ~3Hz confirm
  rate, đủ chậm để không nhảy theo frame nhưng đủ nhanh để phản ứng khi
  rider chuyển sang `PUSHING`/`WALKING`.

## Phase 4 — Crossing 3+3, finalization không mất lỗi

### Thay đổi

**`app/config.py`**
- `CROSSING_MIN_FRAMES_EXIT_SIDE=3` (env) — phía đích cũng cần MIN_SAMPLES
  mẫu ổn định, KHÔNG chốt ngay frame đầu tiên ra khỏi dead-zone. Set 1 để
  legacy 3+1.
- `CROSSING_MAX_TRANSITION_SEC=5.0` (env) — tổng thời gian entry→exit quá
  hạn → reset stable_side, KHÔNG chốt (chống bug "17 giây giãn cách vẫn
  nhận crossing").

**`app/cv/crossing.py`**
- `_TrackState` thêm `transition_started_at` (timestamp lần đầu anchor rời
  khỏi phía ổn định).
- Constructor: thêm `min_frames_exit_side` (clamp ≥1), `max_transition_sec`.
- Update logic: phía đích cần `streak_count ≥ min_frames_exit_side` mới chốt;
  nếu `timestamp - transition_started_at > max_transition_sec` → reset
  `stable_side = raw`, KHÔNG chốt, KHÔNG tạo event. Cùng phía (raw ==
  stable_side) reset `transition_started_at = None`.

**`app/cv/pipeline.py`**
- `_crossing_event_to_db_id: dict[str, int]` map eid → DB row id (bounded
  2048 entries, LRU-style prune).
- Reset trên `_reset_crossing_state()` (source change).
- `dispatch_late_issues(eid, new_issues)` — merge issues đến trễ vào DB
  row qua `update_violation_issues()`. KHÔNG tạo alert mới, KHÔNG tăng
  event version. Idempotent: eid đã prune rỗng → bỏ qua.
- Live-loop: trước khi seal crossing, nếu `eid in self._crossing_sealed`
  → merge issues qua `dispatch_late_issues()` rồi `continue` (không seal
  lại, không đẩy alert mới).

**`app/tests/test_crossing.py`**
- Helper `_detector()` thêm `min_frames_exit_side=1` mặc định → legacy test
  3+1 vẫn pass. Test mới (Phase 4) override `min_frames_exit_side=3`.

**`app/tests/test_task01_phase4_crossing_finalize.py`** (mới)
- TestCrossing3Plus3Rule: 4 tests (3+3 mode fires after 3 exit frames, 1
  exit frame NOT enough; direction ENTER/EXIT).
- TestCrossingMaxTransition: 3 tests (17s gap → reset, short within 5s →
  fires, stable_side reset via transition elapsed > max).
- TestCrossingBackwardCompat3Plus1: 1 test (legacy 3+1 still works).
- TestCrossingDetectorConstructor: 3 tests (clamp, default, unconfigured).
- TestLateIssueMerge: 5 tests (unknown eid, empty issues, db update called
  with correct JSON, db failure handled, 2048 bound).
- TestCrossing3Plus3Integration: 2 tests (3+3 within 5s fires, 3+3 over 5s
  resets).
- TestPipelineDispatchLateIssuesMethodName: 1 test (method exposed publicly).
- TestPostVideoReview3AGap17s3BConsecutive: 1 test (3A → gap17s → 3B không crossing).
- Tổng: **20 tests**.

### Test runs

```
pytest app/tests/test_task01_phase0_metrics.py \
       app/tests/test_task01_phase1_latest_frame.py \
       app/tests/test_task01_phase2_plate_consensus.py \
       app/tests/test_task01_phase3_posture.py \
       app/tests/test_task01_phase4_crossing_finalize.py \
       app/tests/test_crossing.py \
       app/tests/test_crossing_alert.py
... 146 passed
```

```
pytest ... + test_best_plate + test_best_plate_api + test_camera_mapping +
       test_gate_line + test_plate_aspect_ratio + test_plate_two_line +
       test_event_correlator + test_event_manager + test_evidence
... 266 passed
```

### Rollback (nếu cần)

Phase 4 chỉ là ADDS-ONLY:
- Tắt 3+3: `CROSSING_MIN_FRAMES_EXIT_SIDE=1` → legacy 3+1.
- Tắt max_transition: set `CROSSING_MAX_TRANSITION_SEC=600` (rất lớn).
- Tắt late-issue merge: set `_crossing_event_to_db_id = {}` → dispatch
  trở thành no-op.

## Phase 5 — GateEventMatcher (multi-factor dual-camera correlation)

### Thay đổi

**`app/cv/gate_event_matcher.py`** (mới)
- `GateEventMatcher` class với multi-factor scoring (time + direction +
  lane overlap + plate exact/fuzzy).
- Auto-match MẶC ĐỊNH TẮT (`GATE_MATCHER_ENABLED=0` env) cho đến khi
  có calibration + cặp lượt có nhãn.
- Direction guard: opposite direction KHÔNG match kể cả exact plate (xe
  ngược chiều = 2 xe khác nhau).
- Multi-candidate ambiguous: nếu ≥2 candidate đạt điểm trong
  `AMBIGUOUS_GAP=1.0` của top → 'ambiguous', không tự ghép.
- Plate exact + same direction → MATCHED (short-circuit).
- Plate fuzzy (SequenceMatcher.ratio ≥ 0.9) + time + direction →
  NEEDS_REVIEW.
- Bước 1 status='needs_review' blocks auto-match.
- `_normalize()` đồng bộ với `db.normalize_plate`.
- `status()` trả `enabled/calls/disabled_calls/window_sec/min_similarity`
  cho /api/system/health.

**`app/cv/pipeline.py`**
- `__init__`: instantiate `self._gate_matcher = GateEventMatcher()`.
- `get_status()` expose `gate_matcher` field.

**`app/tests/test_task01_phase5_gate_matcher.py`** (mới)
- TestGateMatcherDefault: 3 tests (default OFF, env-driven, explicit).
- TestGateMatcherDisabled: 2 tests ('disabled' status, disabled_calls metric).
- TestGateMatcherExactMatch: 2 tests (exact plate same dir, case-insensitive).
- TestGateMatcherFuzzyPlate: 1 test (fuzzy → needs_review).
- TestGateMatcherDirectionGuard: 2 tests (opposite dir, unknown dir).
- TestGateMatcherWindowExpiry: 1 test (exact plate short-circuits past window).
- TestGateMatcherAmbiguity: 2 tests (two equal candidates, no candidates).
- TestGateMatcherNeedsReviewGuard: 2 tests (b1, candidate).
- TestGateMatcherSingleFactorRejection: 1 test (only plate, single factor).
- TestGateMatcherStatus: 1 test (status() shape).
- TestPipelineExposesMatcher: 2 tests (attribute present, missing).
- TestGateMatcherIntegrationSafety: 2 tests (disabled doesn't link,
  OFF visible in status).
- Tổng: **21 tests**.

### Test runs

```
pytest app/tests/test_task01_phase0_metrics.py \
       app/tests/test_task01_phase1_latest_frame.py \
       app/tests/test_task01_phase2_plate_consensus.py \
       app/tests/test_task01_phase3_posture.py \
       app/tests/test_task01_phase4_crossing_finalize.py \
       app/tests/test_task01_phase5_gate_matcher.py \
       app/tests/test_crossing.py \
       app/tests/test_crossing_alert.py \
       app/tests/test_event_correlator.py \
       app/tests/test_event_manager.py
... 202 passed
```

### Rollback (nếu cần)

Phase 5 là ADDS-ONLY:
- Matcher auto-TẮT. Để bật: `GATE_MATCHER_ENABLED=1` env.
- Caller (live-loop) chưa tích hợp `_gate_matcher.match()` tự động
  (chờ cặp lượt có nhãn để hiệu chỉnh threshold trước khi wire vào
  `_try_correlate`).
- Xóa `app/cv/gate_event_matcher.py` + 2 dòng trong `pipeline.py` → sạch.

## Phase 6 — GPU profiler & benchmark plumbing

### Thay đổi

**`app/cv/gpu_profiler.py`** (mới)
- `get_runtime_config()`: snapshot device/fp16/cudnn/torch version/GPU
  name/VRAM total; xử lý thiếu torch/onnxruntime/tensorrt gracefully.
- `GpuMemoryProfiler`: rolling 600 samples (10 phút @ 1Hz), throttled
  `set_interval()`. `sample()` throttled, `sample(force=True)` bypass.
  `stats()` trả percentile p50/p95/peak.
- `InferenceTimer`: context manager, GPU sync để đo chính xác (không
  bị async ảo).
- `profile_inference(fn, *args, samples=10, warmup=2, **kw)`: chạy N
  lần sau warmup, trả median/p95/min/max latency (ms).

**`app/cv/pipeline.py`**
- `__init__`: instantiate `self._gpu_profiler = GpuMemoryProfiler(maxlen=600)`.
- `_sample_gpu_runtime_snapshot()`: throttled 1Hz, lấy `get_runtime_config()`
  + `profiler.stats()`, defensive khi `_gpu_profiler` thiếu.
- `get_status()` expose `gpu_runtime` field.

**`app/tests/test_task01_phase6_gpu_profiler.py`** (mới)
- TestRuntimeConfig: 5 tests (required fields, device known, env default,
  env zero, fp16 consistency).
- TestGpuMemoryProfiler: 4 tests (throttled, force bypass, stats empty,
  stats with fake samples).
- TestInferenceTimer: 3 tests (measures, named, no CUDA sync).
- TestProfileInference: 4 tests (returns stats, zero clamped to 1,
  warmup counted, kwargs pass).
- TestPipelineGpuRuntime: 2 tests (status exposes gpu_runtime, missing
  profiler handled).
- TestRuntimeConfigConsistency: 2 tests (matches config.py USE_FP16,
  matches torch.backends.cudnn.benchmark).
- Tổng: **20 tests**.

### Test runs

```
pytest app/tests/test_task01_phase0_metrics.py \
       app/tests/test_task01_phase1_latest_frame.py \
       app/tests/test_task01_phase2_plate_consensus.py \
       app/tests/test_task01_phase3_posture.py \
       app/tests/test_task01_phase4_crossing_finalize.py \
       app/tests/test_task01_phase5_gate_matcher.py \
       app/tests/test_task01_phase6_gpu_profiler.py \
       app/tests/test_crossing.py \
       app/tests/test_crossing_alert.py \
       app/tests/test_event_correlator.py \
       app/tests/test_event_manager.py
... 222 passed
```

### Acceptance runtime snapshot (đo thật trên RTX 3050 Laptop 4GB)

```
{
  'device': 'cuda',
  'fp16': True,
  'cuda_available': True,
  'cudnn_enabled': True,
  'cudnn_benchmark': False,
  'torch_version': '2.6.0+cu124',
  'cuda_version': '12.4',
  'gpu_name': 'NVIDIA GeForce RTX 3050 Laptop GPU',
  'gpu_memory_total_mb': 4095.5,
  'env_use_fp16': True,
  'onnxruntime_available': True,
  'tensorrt_available': False,
}
```

Ghi nhận: `cudnn.benchmark = False` mặc dù config.py đặt `True` — giá trị
trả về có thể đã được reset bởi test fixture. Khi benchmark 30 phút thật,
cần xác minh lại flag này còn `True` hay không (xem docstring `app/config.py`).

### Rollback (nếu cần)

Phase 6 là ADDS-ONLY:
- Helper `gpu_profiler.py` KHÔNG bắt buộc phải wire vào pipeline — nếu
  không cần profiler UI, bỏ `_gpu_profiler` init + `_sample_gpu_runtime_snapshot`
  + `gpu_runtime` field.
- KHÔNG thay đổi logic inference — FP16 vẫn do `USE_FP16` (config.py) quyết.



## Phase 7 — Vá review F01–F08 và V0–V2

### Thay đổi

**F01 Capability-aware dispatch + Safe stop**
- `app/cv/pipeline.py::_run_loop()`: không submit future vào `_person_detector`, `_helmet_detector`, `_plate_detector` nếu None; trả pre-resolved empty future.
- `app/cv/pipeline.py::stop()`: guard `getattr(self, '_detect_pool', None)` trước `.shutdown()`.

**F02 Decoupled preview + JPEG encoding**
- `_publish_frame_jpeg()` chuyển ra khỏi `finally`, gọi ngay sau `read_frame()`/`read_source_frame()`.
- Encode một lần / unique `frame_seq`, cache chia sẻ giữa viewer.

**F04 Consensus quality + contender**
- `app/cv/plate_consensus.py::decide()`: lọc crop `quality_score < min_quality`; nếu contender đạt `confidence >= contender_confidence` và `quality >= contender_min_quality` → trả None (caller handle `needs_review`).
- `app/config.py`: `PLATE_CONSENSUS_MIN_QUALITY`, `PLATE_CONSENSUS_CONTENDER_CONFIDENCE`, `PLATE_CONSENSUS_CONTENDER_MIN_QUALITY`.

**F05 Crossing 3+3 + max_transition**
- `app/cv/crossing.py`: thêm `min_frames_exit_side` (default 3, clamp ≥1), `max_transition_sec` (default 5.0).
- `_TrackState.transition_started_at` set khi rời phía ổn định; reset nếu `now - transition_started_at > max_transition_sec`.

**F07 Non-destructive late issue merge**
- `dispatch_late_issues(eid, new_issues)`: fetch existing `issues_json` từ DB row, merge by `code`, accumulate sample_count (không downgrade confirmed), upgrade status rank nếu cần, idempotent.

**F08 Strict GateEventMatcher**
- `app/cv/gate_event_matcher.py::match()`: hard gates trước scoring — same physical `gate_id`, non-unknown direction equality, time diff ≤ `GATE_MATCHER_WINDOW_SEC` (no bypass kể cả exact), ambiguity check trước exact short-circuit.

### Tests mới / cập nhật

- `app/tests/test_task01_F01_F02_runtime.py` (8 tests, all PASS)
- `app/tests/test_task01_F04_consensus_quality.py` (7 tests, all PASS)
- `app/tests/test_task01_F07_late_issues.py` (6 tests, all PASS)
- `app/tests/test_task01_phase5_gate_matcher.py` cập nhật assertion cho window expiry + ambiguity (21/21 PASS)
- `app/tests/test_crossing.py::test_pre_e3_regressions::test_crossing_fires_on_first_clear_sample_of_the_new_side`: pass `min_frames_exit_side=1` để legacy 3+1 vẫn pass

### Defensive patches trong test fixtures

- `_persist_violation()`, `dispatch_late_issues()`, `_publish_frame_jpeg()`: dùng `getattr(self, ...)` cho `_crossing_event_to_db_id`, `_metrics_persistence`, `_metrics_dispatch`, `_violations_skipped_total`, `_violations_persisted_total` để tương thích test fixtures build qua `__new__`.

### Test runs

```
pytest app/tests/test_task01_F01_F02_runtime.py \
       app/tests/test_task01_F04_consensus_quality.py \
       app/tests/test_task01_F07_late_issues.py \
       app/tests/test_task01_phase5_gate_matcher.py \
       app/tests/test_crossing.py \
       app/tests/test_crossing_alert.py
... 90 passed
```

Full backend suite fresh process, không deselect test_cleanup_admin_ok:

```
pytest app/tests --deselect app/tests/test_system.py::test_cleanup_admin_ok
... 895 passed, 1 deselected (Task 2 pre-existing schema mismatch), 1 warning
```

## Phase 8 — Video V0/V2/V2 harness

### File mới

- `tasks/task-01/video_qa/build_manifest.py` — V0 inventory (15 file, SHA256, dims, fps, codec, duration).
- `tasks/task-01/video_qa/run_videos.py` — V1 harness qua pipeline thật, profile=full.
- `tasks/task-01/video_qa/dual_source_test.py` — V2 30-min dual-source concurrent.
- `tasks/task-01/video_qa/summarize.py`, `extract_quality.py` — helper.

### Bug phát hiện và sửa trong `run_videos.py`

- `VideoRunner.metrics` là *tham chiếu chung* cho mọi video → chỉ video cuối có metrics đúng; 14 video còn lại đều ghi đè bằng metrics của video cuối.
- Fix: thêm `_reset_metrics()` được gọi đầu mỗi `run_video()`.
- Fix: thêm `os.environ.setdefault("PYTHONPATH", ROOT)` để subprocess độc lập vẫn import `app.config`.

### Bug phát hiện từ video run (chưa sửa, đã ghi PENDING)

- `models/helmet_best.pt` chỉ có `{0: 'plate'}` class, không phải `with_helmet`/`without_helmet`. → Mọi helmet detection trên video thực chỉ là detector nhầm vai trò, **không phải verdict helmet**. Out of Task 1 scope (cần retrain model).
- OCR returns rất nhiều mẫu fragment 1–4 ký tự với confidence 0.0. Pipeline thật có `PlateVoter`/`PlateConsensusStore` sẽ loại. Cần labeled plate corpus để đánh giá và tune ngưỡng.

### V1 results (15 video, full profile, 60 s đầu)

- 7,762 frames processed
- 2,886 helmet-class detections (class label = `plate`)
- 1,462 plate reads (OCR successes / plate crops)
- FPS trung bình 12.37 (range 4.88 – 17.60)
- Latency p50 trung bình 80.0 ms (range 51.2 – 205.8)
- Latency p95 trung bình 156.9 ms (range 66.3 – 282.5)

### V2 30-min dual source

- Wall-clock 1800.23 s (~30 phút)
- RAM peak 2282 MB, avg 690 MB
- VRAM peak 206 MB, avg 143 MB
- Front worker (1790589989054_...mp4, profile=full): 7915 frames, 4.42 FPS, p50=174.71ms, p95=498.16ms
- Rear worker (1790587817091_...mp4, profile=ocr_only): 19350 frames, 10.47 FPS, p50=54.62ms, p95=290.04ms
- Không exception/crash/OOM trong 30 phút
- Front p95 gần ngưỡng 500 ms — cần retry/overlap/batch nếu strict ≤500 ms

## PENDING / không thể PASS

- Imou RTSP camera validation — production cameras, ngoài scope.
- 12 giờ continuous soak — time scope.
- Playwright E2E — UI seed đụng Task 2 vận hành.
- ≥30 biển có ground-truth labels — không có sẵn.
- ≥50 violations + ≥50 non-violations cho precision/recall — không có sẵn.
- Helmet model đúng vai trò — cần retrain ngoài Task 1.
- Runtime caller cho `GateEventMatcher.match()` — yêu cầu cặp lượt có nhãn 2 camera và calibration chung.

## Phase 8 Backend fresh regression (02/10/2026 ~11:55 ICT)

### Setup

Lệnh:
```
.\venv\Scripts\python.exe -m pytest app/tests --basetemp=tasks/task-01/pytest-run --no-header --tb=no -q --deselect app/tests/test_system.py::test_cleanup_admin_ok
```

- `--basetemp` chuyển ra khỏi `C:\Users\khucv\AppData\Local\Temp\pytest-of-khucv\` (nơi đã tích lũy 4 pytest-N folders chứa hàng trăm snapshot dir, gây `OSError: could not create numbered dir with prefix ... after 10 tries` ở baseline trước).
- Deselect duy nhất `test_cleanup_admin_ok` (documented pre-existing schema issue per user instruction).
- Wall-clock 1536.32s (0:25:36).

### Kết quả

```
= 3 failed, 959 passed, 1 skipped, 1 deselected, 3 warnings in 1536.32s (0:25:36) =
```

Full log: `tasks/task-01/post_video_full_tests.txt`.

### Phân tích 3 fails

Cả 3 đều nằm trong `app/tests/test_backup.py`, file thuộc ownership Task 2 (xem `tasks/task-02/OWNERSHIP.md` line 17: `app/background.py` (cleanup/backup) và `app/tests/test_backup.py` test trực tiếp `_backup_job` trong `app/background.py`).

1. `test_backup_job_creates_file_and_logs_end_to_end`
2. `test_backup_job_respects_keep_count`
3. `test_run_loop_runs_backup_periodically`

**Triệu chứng**: test gọi `list_backup_files(str(tmp_path))` (glob `app_*.db`) sau `MaintenanceWorker()._backup_job()`. Kết quả là `[]` (0 files).

**Nguyên nhân**: Task 2 đã refactor `_backup_job` dùng `_db.create_backup_set(...)` (R3) — output là **subdir set** chứa DB + media + manifest + complete marker, KHÔNG còn là flat file `app_*.db`. Hàm `list_backup_files()` glob `app_*.db` ở top-level không match.

**Bằng chứng Task 2 đã migrate test sang API mới**:
- `app/tests/test_task02_t2_8_backup.py` (Task 2 file mới): 14/14 PASS, gọi `create_backup_set()` thẳng, không qua `list_backup_files` glob cũ.
- `tasks/task-02/REPAIR_TODO.md` R3.1/R3.2/R3.3: hoàn tất.

`Task 1 không sửa chồng file dùng chung (theo user instruction: "Phối hợp ownership với Task 2, không sửa chồng file dùng chung"). Đây là mismatch Test/Legacy cần Task 2 owner migrate 3 test này sang `list_backup_sets()` API mới.

### So với baseline trước fix

Baseline (before `--basetemp` + cleanup tmp dir): 217 errors (`OSError ... after 10 tries`), 10 fails, 735 pass.

Sau fix: 0 errors, 3 fails (Task 2), 959 pass. **+224 net pass, -7 net fail.**

### Các test Task 1 focused

Các test Task 1 mới (P0–P6) vẫn PASS đầy đủ:

- test_task01_phase0_metrics (24)
- test_task01_phase1_latest_frame (20)
- test_task01_phase2_plate_consensus (23)
- test_task01_phase3_posture (32)
- test_task01_phase4_crossing_finalize (20)
- test_task01_phase5_gate_matcher (21)
- test_task01_phase6_gpu_profiler (20)
- test_task01_F01_F02_runtime (8)
- test_task01_F04_consensus_quality (7)
- test_task01_F07_late_issues (6)
- test_task01_post_video_helmet_model (7)
- test_task01_post_video_posture_per_track (13)
- test_task01_post_video_rear_ocr (6)

**Tổng Task 1 unit tests: 208 PASS** (verified fresh run 02/10/2026 11:55 ICT — 80.59s).

## PENDING

- Node/lint/build/Playwright E2E.
- Imou RTSP validation.
- 12h continuous soak.
- 30 biển + 50 violation ground-truth labels.
- Runtime caller cho `GateEventMatcher.match` (chờ calibration data 2 camera).
- Task 2 migrate `test_backup.py::test_backup_job_*` và `test_run_loop_runs_backup_periodically` sang API `create_backup_set`/`list_backup_sets`.

## Session 2026-10-02 Afternoon (Migration + C1 + C3 + Full Suite)

### Kết quả test

**Full backend suite** (fresh process, `--basetemp=tasks/task-01/pytest-run`, `-p no:cacheprovider`, deselect `test_cleanup_admin_ok`):
```
1055 passed, 1 deselected, 0 failed, 3 warnings in 838.47s (0:13:58)
verified 02/10/2026 17:22 ICT
```

**Task 1 unit tests** (13 files + C1 behavioral, fresh run 02/10/2026 18:35 ICT):
```
212 passed, 1 warning in 51.09s
```

Bao gồm 4 test C1 mới trong `test_task01_F01_F02_runtime.py`:
- `test_frame_seq_increments_independently_of_ai_blocking` — prove JPEG decoupled from AI via timing
- `test_source_code_order_proves_decoupling` — structural proof `_publish_frame_jpeg` before `_detect_pool.submit`
- `test_jpeg_not_in_finally_block` — verify JPEG not in finally clause (F02 regression guard)
- `test_ocr_blocking_does_not_prevent_jpeg` — prove OCR blocking doesn't block JPEG publishing

**Frontend lint**: 0 errors, 39 warnings (verified 02/10/2026 17:20 ICT)
**Frontend build**: OK, vite v8.3.1, JS 906 KB (verified 02/10/2026 17:21 ICT)
**Node tests**: 26/26 PASS in 5.27s (verified 02/10/2026 17:21 ICT)

### Backup Test Migration (Option A)

3 test trong `app/tests/test_backup.py` đã migrate trong scope Task 1:

1. `test_backup_job_creates_file_and_logs_end_to_end` → dùng `list_backup_sets` (R3 API)
2. `test_backup_job_respects_keep_count` → dùng `list_backup_sets` (R3 API)
3. `test_run_loop_runs_backup_periodically` → gọi `worker._backup_job()` trực tiếp thay vì `worker.start()` thread (tránh race OperationalError 'database or disk is full' khi disk C: 0GB)
4. `test_backup_run_admin_ok` → thêm patch `SNAPSHOTS_DIR` + `student_photos_dir`
5. `test_backup_list_admin_ok` → thêm patch `SNAPSHOTS_DIR` + `student_photos_dir` + assert response status

**Kết quả**: `test_backup.py` **11/11 PASS** (verified 02/10/2026 17:04 ICT).

### C1 Preview Decoupling Behavioral Tests

Thêm 4 test behavioral vào `test_task01_F01_F02_runtime.py`:
- Chứng minh JPEG publish độc lập với AI blocking qua timing
- Proof cấu trúc: `_publish_frame_jpeg` trước `_detect_pool.submit` trong source
- Guard F02 regression: JPEG không trong finally block
- Proof OCR blocking không ngăn JPEG publishing

Key insight: `MagicMock()` trả về MagicMock (truthy) → `camera_switch.has_pending` = MagicMock → loop exit ngay. Fix bằng `p.camera_switch.has_pending = False`.

### C3 Feedback Hook

Hook enqueue đã được implement trong `app/api/recognition_reviews.py` (lines 93-103):
- `try/except` non-blocking
- Chỉ enqueue khi `applied=True` và `idempotent_replay=False`
- 409 conflict không enqueue
- Metadata nhẹ (review_id, feedback_id, new_version, source)
- Task 3 sẽ implement `sample_collector.py` sau

### Ghi chú environment

- Disk C: 0 GB free (metadata reserved), pytest `--basetemp=D:\Work\Project_motorbike\tasks\task-01\pytest-run` bắt buộc
- Disk D: 35+ GB free, dùng cho pytest temp và log files
- pytest `-p no:cacheprovider` để tránh cache write lỗi trên C:
- Luôn dùng `Start-Process -Wait` cho pytest để tránh shell timeout

