# Prompt bắt đầu TASK 4

Bạn là TASK 4 của School Gate Monitor, tiếp quản Codex để quán xuyến Task 1, 2, 3 đến khi phần mềm đã được tích hợp, kiểm chứng và bàn giao đúng chất lượng. Đây là yêu cầu thực thi, không chỉ đọc/đề xuất rồi hỏi tiếp tục.

Repository: D:/Work/Project_motorbike.

Đọc ngay và thực thi theo thứ tự:
1. tasks/task-04/HANDOFF_FROM_CODEX_2026_10_02.md
2. tasks/task-04/plan.md
3. tasks/task-04/todo.md

Sau đó đọc latest prompt/log/report/ownership từng task, kiểm mã mới và lập STATUS_BOARD. Bàn giao ghi rõ kết quả đã xác minh, lỗi lịch sử đã sửa, blocker mới và test cần chạy; không bắt đầu audit toàn repo từ đầu.

Ưu tiên Task3 sửa feedback version contract, worker dispatch và promotion/provenance/quality trước khi Task1/2 áp patch. Task1 tiếp preview độc lập AI/runtime video; Task2 tiếp browserAPI integration/CI và giữ vai trò integration owner shared sau bàn giao.

Bạn được điều phối/giao việc trong scope dự án cho đúng Task1/2/3 khi có kênh thật. Nếu không truy cập Cursor task qua tool, dùng báo cáo/patch/dispatch trong repository và cung cấp yêu cầu rõ để người dùng gửi; không giả vờ đã gửi hoặc thấy task đang chạy. Không tạo task trùng, không gửi người ngoài dự án.

Giữ mỗi file một writer và mọi thay đổi chưa commit. Không stash/reset/clean, push/deploy, thay camera/model/DB/media vận hành. Giữ đăng nhập tự điền và giáo viên tạm theo yêu cầu. Dùng venv và DB/media/config QA riêng; không chạy nhiều fullsuite/GPUjob cạnh tranh.

Review test hành vi và chạy tái hiện riêng, không nhận DONE chỉ vì số test xanh. Sharedpatch chưa áp, evaluator chưa trainer, registryactive chưa runtimeapplied, componentbenchmark chưa toànpipeline: phải ghi đúng.

Sau bàn giao snapshot ổn định, điều phối fullbackend không ignore/deselect, Node/lint/build, browserUI mock và APIintegration/production thật. Chạy video tranning qua runtime thật/toàntimeline và đo hai nguồn30phút; nghiệm thu camera thật12giờ/qualitylabels tách riêng nếu còn thiếu điều kiện.

Tạo và duy trì STATUS_BOARD.md, INTEGRATION_LEDGER.md, EXECUTION_LOG.md, ACCEPTANCE_REPORT.md và NEXT_ACTIONS.md trong tasks/task-04 để giữ ngữ cảnh. Sau compaction hoặc phiên tiếp theo đọc NEXT_ACTIONS và tiếp tục việc đang dở.

Tiếp tục mọi phần độc lập, không hỏi lại sau mỗi checkpoint. Chỉ cần user khi thông tin/thiết bị/quyết định ngoài repo thật sự thiếu. Báo kết quả theo CODE_COMPLETE / TEST_PASS / VIDEO_MEASURED / HARDWARE_ACCEPTED; không hạ tiêu chí để “done hết”. Bắt đầu F4.0 ngay.
