import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LanguageContext';

export default function SettingsLayout() {
  const { user } = useAuth();
  const { t } = useLang();
  const links = [['/settings', t('Tài khoản của tôi', 'My account')]];
  if (user?.role === 'admin') links.push(
    ['/settings/camera', 'Camera'], ['/settings/roi', t('ROI / Vạch cổng', 'ROI / Gate line')],
    ['/settings/storage', t('Sức khỏe & Lưu trữ', 'Health & Storage')], ['/settings/users', t('Tài khoản', 'Accounts')],
    ['/settings/ai', t('AI nâng cao', 'Advanced AI')],
  );
  return (
    <div>
      <nav aria-label={t('Cài đặt', 'Settings')} className="flex flex-wrap gap-2 border-b border-outline-variant bg-surface px-4 py-3">
        {links.map(([to, label]) => <NavLink key={to} to={to} end={to === '/settings'}
          className={({ isActive }) => `rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${isActive ? 'bg-primary text-on-primary' : 'text-primary hover:bg-primary-container'}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </div>
  );
}
