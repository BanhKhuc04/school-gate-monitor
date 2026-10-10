# Live recognition visibility — 2026-10-03

The live guard page showed camera video and an empty violation log while the backend was detecting people and vehicles. These findings were reproduced against the running backend and in focused regression tests.

## Causes and fixes

- `GuardPage` did not mount the existing recognition cards component. Restored the default **Nhận diện trực tiếp** tab, alongside **Duyệt biển** and **Cảnh báo**. Camera frame age now follows the selected gate.
- The preview encoder received a copy of the frame before inference, so drawing boxes later in the main loop never appeared in the streamed JPEG. The independent encoder now draws the latest completed detections, including vehicles and independent plates. Boxes expire after one second and are scoped to the camera source epoch; encoding still does not wait for inference/OCR.
- Plate-only OCR returned early when a subsequent crop did not improve the selected crop. This skipped collection of completed OCR futures. It now collects the result regardless of crop replacement, publishes a diagnostic entry, and shows an independent plate card/crop. Independent plates remain unassociated and cannot identify students or create violations.
- The active `models/helmet_best.pt` contained `{0: 'plate'}`, causing `helmet_model_wrong_mapping`. Preserved the invalid artifact in ignored QA storage and restored the validated existing backup `models/backups/helmet_best_20260930_090903.pt`, with classes `{0: 'With Helmet', 1: 'Without Helmet'}`. Restored SHA-256: `c8eb324e365cf4faeab491d9cc301535ec745171b55e8b1acadea62be5101a9d`. Runtime now reports helmet `ready`.
- `AdminRoiPage` still contained the older ROI-only editor. Restored the gate-line mode, two-point drawing, undo, save, reload and delete using the existing `/api/roi/{gate}/line` API. The line is stored separately from the ROI polygon. Removed inaccurate copy promising unconditional speaker output or an automatic default line.

## Verification

- Regression tests reproduced the missing JPEG boxes, invisible guard recognition tab and skipped OCR collection before the fixes.
- 75 focused backend tests passed, including actual preview-thread JPEG output, unchanged-crop OCR completion, source epoch invalidation and independent plate cards.
- 7 Chromium UI tests passed, including crop loading, filtering, pause/hide, model errors, retry, independent plate display without invented person identity, and separate gate-line persistence. The gate-line test also checks two-point validation and deletion/reload.
- Frontend production build and lint passed. Existing bundle-size and lint warnings remain.
- A real browser against the running API showed three recognition cards, detection boxes and the OBS sample image with no JavaScript errors. A separate real-browser check confirmed the restored gate-line editor and save control. No API mocks were used for these checks, and no arbitrary line was saved to the user's DB.
- Local inference on the supplied screenshot found a person (~0.81), motorcycle (~0.83) and actual plate (~0.33). OCR on that reduced screenshot was inaccurate and remains unconfirmed.
- Complete backend run: 1,190 passed, 1 skipped, and one test failed because its OCR-worker test relied on an initialized global training DB. Changed that test to initialize its own temporary database with the production schema; all 29 tests in that closure module then passed. All 12 new visibility/restored-model tests also passed. Production application code did not change after the complete run.

## Manual test state

Frontend: `http://127.0.0.1:5173/guard`; backend: `http://127.0.0.1:8000`.

The user chose to keep **OBS Virtual Camera**, source `1`. It sent black frames initially, then resumed the sample video: live OCR completed seven requests without engine errors, with a partial/unconfirmed read (`89FU23792`). The exact plate is not verified. Later checks saw black output again, so OBS must keep playing the sample and sending its virtual camera output for manual testing. No camera source was changed.

The main gate has no saved gate line; both the current DB and its pre-migration backup have `gate_line_json = NULL`. Configure two endpoints in the restored editor. Recognition remains visible, but OCR for associated vehicles and official gate-crossing decisions still require a correctly configured gate line. The secondary camera remains offline.

QA diagnostics, screenshots and test logs are stored under ignored `qa_logs/`; local credentials are excluded.
