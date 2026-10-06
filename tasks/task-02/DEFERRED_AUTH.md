# TASK 2 — Auth deferred theo yêu cầu người dùng

> Các hạng mục bảo mật đăng nhập/phiên được **hoãn** theo quyết định người dùng
> (nêu trong `tasks/task-02/plan.md`). KHÔNG đánh dấu Task 2 đạt nghiệm thu bảo mật
> đầy đủ khi các mục này còn tồn tại.

## Đã hoãn (chưa triển khai trong Task 2)

- **JWT revocation / blocklist khi đăng xuất.** Logout chỉ xóa cookie phía
  client; Bearer token vẫn dùng được cho tới khi hết hạn. Tồn tại cố ý theo
  yêu cầu "không thay đổi cơ chế JWT trong task này".
- **Cookie-only authentication.** Vẫn chấp nhận `Authorization: Bearer` từ localStorage.
- **Rate-limit đăng nhập** (lockout theo username hoặc IP sau N lần sai).
- **Password policy** (độ dài tối thiểu, ký tự đặc biệt, expiry).
- **Session hardening** (rotate session id sau login, kiểm tra user-agent, kiểm
  tra IP).
- **CSRF protection** cho state-changing request khi chỉ dùng cookie.
- **JWT_SECRET_KEY rotation** & kiểm tra secret yếu.

## Đã giữ nguyên theo yêu cầu

- Cơ chế JWT/cookie/Bearer/localStorage hiện có.
- Ba nút demo (Quản trị viên, Bảo vệ, Ban giám hiệu) — chỉ tự điền form.
- Thêm nút Giáo viên — cùng cơ chế tự điền, KHÔNG bypass auth.
- Bản production chưa tắt hard-code `http://localhost:8001` trong tất cả URL gửi đi;
  Task 2 chỉ sửa `frontend/src/api/client.js` để ưu tiên cùng origin (Task 2.2).

## Bằng chứng chưa hoàn tất

- Test `app/tests/test_auth.py::TestLogout::test_me_after_logout_still_works_with_bearer`
  đang assert rằng Bearer vẫn hoạt động sau logout. Đây là regression test cố ý
  cho hành vi hiện tại, không phải bằng chứng bảo mật đầy đủ.

## Khi nào bỏ trạng thái hoãn

- Khi Task 3 (auth hardening) chạy và chốt danh sách thay đổi, dời mục tương
  ứng sang `tasks/task-03/EXECUTION_LOG.md` hoặc file hợp nhất. Không tự xóa.