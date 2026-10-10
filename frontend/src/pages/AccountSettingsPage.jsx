import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LanguageContext';

export default function AccountSettingsPage() {
  const { user } = useAuth();
  const { t } = useLang();
  const roles = {
    admin: t('Quản trị viên', 'Administrator'),
    security: t('Bảo vệ', 'Guard'),
    management: t('Ban giám hiệu', 'School management'),
    teacher: t('Giáo viên chủ nhiệm', 'Homeroom teacher'),
  };
  return (
    <section className="p-6 space-y-4" aria-label={t('Tài khoản của tôi', 'My account')}>
      <h1 className="text-xl font-bold">{t('Cài đặt', 'Settings')}</h1>
      <dl className="max-w-lg divide-y divide-outline-variant rounded border border-outline-variant bg-surface px-4">
        <div className="flex flex-wrap justify-between gap-2 py-3"><dt>{t('Tài khoản', 'Account')}</dt><dd className="font-medium">{user?.username}</dd></div>
        <div className="flex flex-wrap justify-between gap-2 py-3"><dt>{t('Vai trò', 'Role')}</dt><dd>{roles[user?.role] || user?.role}</dd></div>
        {user?.homeroom_class && <div className="flex justify-between gap-2 py-3"><dt>{t('Lớp chủ nhiệm', 'Homeroom class')}</dt><dd>{user.homeroom_class}</dd></div>}
      </dl>
      <p className="text-sm text-on-surface-variant">{t('Các mục cấu hình hiển thị theo quyền của tài khoản.', 'Settings shown depend on your account permissions.')}</p>
    </section>
  );
}
