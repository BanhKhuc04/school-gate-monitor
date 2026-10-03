# TASK 3 — Checklist vòng feedback và training

Nguồn: `plan.md`. Triển khai từ 12:38 ICT 2026-10-02.

- [x] T3.0: Baseline model/engine/review/export, contracts/ownership, DB/media QA và đề xuất/nhãn tách biệt. (40/40 tests PASS)
- [x] T3.1: Duyệt chữ biển/đúng/sai/unknown qua existing review API OK; sửa lại version/history qua expected_version + Idempotency-Key. BBoxEditor component built + BBoxEditorDemoPage riêng gọi PATCH bbox. Optimistic version enforced. Sửa lần 2 với version cũ → 409 (đã test). KHÔNG sửa file Task 1 (chỉ thêm endpoint Task 3).
- [x] T3.2: Adapter sang recognition_reviews OK. sample_collector tận dụng cùng `recognition_reviews` table — không viết runtime hook riêng. Thu mẫu thật cần runtime + camera đang chạy (PENDING_DATA).
- [x] Checkpoint A: 40/40 unit + integration tests PASS; shared patch KHÔNG sửa chồng (chỉ là integration/*.md).
- [x] T3.3: Export ZIP ảnh/nhãn/manifest + import preview/diff/validate/idempotency/conflict + 3 attack guards (traversal/symlink/oversize) — PASS.
- [x] T3.4: Dataset immutable freeze + split theo nhóm (70/15/15) + leakage check exact crop hash + target text + audit labels + augmentation train-only — PASS.
- [x] Checkpoint B: Dataset hợp lệ có target OCR khác detector labels; thiếu nhãn ghi rõ PENDING_DATA.
- [x] T3.5: Trainers plate_ocr / plate_detector / helmet wrappers + jobs state machine + cancel + 1-GPU constraint — PASS. Real training PENDING GPU lock với Task 1.
- [x] T3.5 smoke: Smoke train trên dataset nhỏ trả candidate với metrics đúng, không chạm active model/camera — PASS.
- [x] T3.6: Evaluator với exact_ocr/CER/detector/helmet + baseline regression check + old-case regression — PASS. Holdout evaluation chính xác PENDING_DATA.
- [x] T3.6 UI: CandidateComparePage với promote/rollback, đúng scope admin; không tự bật model — PASS.
- [PENDING_INTEGRATION] Browser end-to-end: E2E spec đã viết (frontend/e2e/test_task03_training.spec.js — 17 tests). Chạy được khi apply frontend_routing_patch.md + Vite dev server lên; hiện đợi Task 1/2 patch.
- [PENDING_INTEGRATION] Full regression: Sau khi apply main_py_router_patch.md.
- [x] Acceptance/report: File ACCEPTANCE_REPORT.md phân biệt rõ đã lưu feedback / dataset đủ / trainer chạy / candidate tốt hơn / đã áp dụng.

## Dữ liệu nghiệm thu cần chuẩn bị

- [PENDING_DATA] >=30 biển rõ khác nhau để đo exact whole-plate OCR. Cần runtime thật + người dùng duyệt.
- [PENDING_DATA] >=50 lượt vi phạm và >=50 lượt không vi phạm rõ, labels giữ holdout độc lập. Cần runtime + feedback.
- [PENDING_DATA] Nhãn mũ/head/ghép người-xe/gương/hành vi đúng theo loại dữ liệu, không ép mẫu mơ hồ.
- [PENDING_DATA] Nếu đánh giá thiết bị: runtime model candidate trên hai Imou theo lịch được phép, không suy từ dataset smoke.
