import { useAuth } from '../auth/AuthContext';

const roles = { admin: 'Quản trị viên', security: 'Bảo vệ', management: 'Ban giám hiệu', teacher: 'Giáo viên chủ nhiệm' };

export default function AccountSettingsPage() {
  const { user } = useAuth();
  return (
    <section className="p-6 space-y-4" aria-label="Tài khoản của tôi">
      <h1 className="text-xl font-bold">Cài đặt</h1>
      <dl className="max-w-lg divide-y divide-outline-variant rounded border border-outline-variant bg-surface px-4">
        <div className="flex flex-wrap justify-between gap-2 py-3"><dt>Tài khoản</dt><dd className="font-medium">{user?.username}</dd></div>
        <div className="flex flex-wrap justify-between gap-2 py-3"><dt>Vai trò</dt><dd>{roles[user?.role] || user?.role}</dd></div>
        {user?.homeroom_class && <div className="flex justify-between gap-2 py-3"><dt>Lớp chủ nhiệm</dt><dd>{user.homeroom_class}</dd></div>}
      </dl>
      <p className="text-sm text-on-surface-variant">Các mục cấu hình hiển thị theo quyền của tài khoản.</p>
    </section>
  );
}
