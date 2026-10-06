# T8 — Giao diện vận hành và AI nâng cao

Ngày kiểm tra: 2026-10-03. Chưa stage hoặc commit; giữ cấu trúc Outlet của các thay đổi App/Layout đã có.

## Đã triển khai

- Admin/management có bốn mục chính: Giám sát, Vi phạm, Xe đăng ký, Cài đặt. Bảo vệ/giáo viên chỉ thấy các chức năng theo quyền; giáo viên giữ route và dữ liệu theo lớp.
- Báo cáo nằm trong Vi phạm. Camera, ROI/vạch cổng, sức khỏe/lưu trữ và tài khoản nằm trong Cài đặt. Route cũ redirect, giữ query/hash; backend vẫn quyết định quyền.
- AI nâng cao dành cho admin: duyệt mẫu, chọn bộ dữ liệu đóng băng để xuất ZIP local, đánh giá baseline, xem model/rollback. Nhập weights Kaggle được đánh dấu chưa khả dụng vì chưa có API.
- Chọn mẫu trong bộ dữ liệu mở đúng bbox qua query dataset/sample. Không nhập Dataset ID bằng tay. Ảnh lấy qua endpoint admin mới; mẫu đóng băng/ảnh lỗi khóa lưu. Sửa có expected_version, xử lý409 và giữ ảnh/bbox cùng bộ dữ liệu khi đổi chọn nhanh.
- BBox hỗ trợ phím mũi tên, Esc và resize handle bằng bàn phím. Bỏ min-height gây lệch tọa độ khi ảnh nhỏ trên mobile.
- Nhãn job phân biệt đánh giá baseline với huấn luyện; không gọi baseline “đã train”. Registry active chờ xác nhận runtime, không ghi “đang chạy” khi thiếu bằng chứng.
- Toggle khung AI trên Giám sát cho admin/management, từng camera. UI nói rõ áp dụng cho mọi viewer camera đó. API từ chối camera chưa chạy thì giữ trạng thái cũ và hiện lỗi.
- Layout có mobile navigation. Route được lazy-load; shell giữ nguyên khi tải trang. JS đầu vào giảm từ866.73KB xuống333.01KB (gzip107.50KB); phần báo cáo tải riêng378.88KB.

## Kiểm thử

- `npm run build`: đạt, không còn cảnh báo chunk>500KB.
- `npm run lint`: exit0, có cảnh báo hiện hữu về effect/unused/fast-refresh; chưa tuyên bố sạch toàn bộ lint.
- `npx playwright test --config playwright.task05.config.js`: **9/9 đạt,22.3giây**.
- Browser dùng API FastAPI thật, SQLite/media riêng, không chạy lifespan CV/training/maintenance. Login, datasets, role403, ảnh bbox200×100, PATCH và version1 được kiểm với dữ liệu thật trong fixture. Guard preview và WebSocket được stub vì fixture không mở camera; trường hợp ảnh thiếu được chủ động mock404.
- Kiểm tra alias/report/menu, quyền admin/management/security/teacher, giữ selection, đóng băng, ảnh lỗi, keyboard/Esc, debug scope/camera409 và teacher/securityPOST403.
- Screenshot desktop1440 và mobile320 được xem; sửa tràn/đè statusbar trên mobile. Trang AI không có pageerror và không tràn ngang ở320px.
- Artifact QA gồm tất cả lượt chạy khoảng1.63MB, lưu dưới `qa_logs/task05_ui/`.

## Phần còn mở

- Import weights Kaggle và xác nhận apply/rollback runtime cần hoàn thiện backend/model registry. Không có nút giả cho tác vụ này.
- Candidate list API chưa trả metrics JSON; UI hiển thị hash/path nhưng kết quả số chỉ xuất hiện khi API cung cấp. Không suy diễn metrics từ tên file.
- ZIP export hiện trả đường dẫn local, chưa có tải file qua HTTP. Test T8 chưa xuất kho vận hành hoặc upload Kaggle.
- Browser suite này xác nhận giao diện/API; không thay thế nghiệm thu video/camera, previewFPS, ghép trước/sau hay độ đúng nhận diện.
- Các bộ E2E lịch sử còn có giả định nhãn menu/URL cũ và một số mock schema đã lệch trước đợt này. Khi chạy lại cần đối chiếu redirect canonical, không hạ quyền hoặc bỏ kiểm tra dữ liệu để làm xanh.

## File đã sửa/tạo

Nguồn frontend:

- `frontend/src/App.jsx`
- `frontend/src/components/Layout.jsx`
- `frontend/src/components/Sidebar.jsx`
- `frontend/src/components/TopStatusBar.jsx`
- `frontend/src/components/SettingsLayout.jsx` (mới)
- `frontend/src/components/ViolationsLayout.jsx` (mới)
- `frontend/src/components/DebugOverlayControl.jsx` (mới)
- `frontend/src/components/training/BBoxEditor.jsx`
- `frontend/src/pages/AccountSettingsPage.jsx` (mới)
- `frontend/src/pages/AdvancedAiPage.jsx` (mới)
- `frontend/src/pages/AiReviewPage.jsx` (mới)
- `frontend/src/pages/KaggleExportPage.jsx` (mới)
- `frontend/src/pages/BBoxEditorDemoPage.jsx`
- `frontend/src/pages/DatasetManagerPage.jsx`
- `frontend/src/pages/TrainingJobsPage.jsx`
- `frontend/src/pages/CandidateComparePage.jsx`
- `frontend/src/pages/GuardPage.jsx`
- `frontend/vite.config.js`
- `frontend/vite.qa.config.js`

Kiểm thử và báo cáo:

- `frontend/playwright.task05.config.js` (mới)
- `frontend/e2e/task05LiveBackend.py` (mới)
- `frontend/e2e/task05Vite.mjs` (mới)
- `frontend/e2e/test_task05_navigation.spec.js` (mới)
- `tasks/task-05/UI_REPORT.md` (mới)

Không sửa backend, không thêm package, không thay quyền API.
