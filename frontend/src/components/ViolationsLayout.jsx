import { NavLink, Outlet } from 'react-router-dom';
import { useLang } from '../i18n/LanguageContext';

export default function ViolationsLayout() {
  const { t } = useLang();
  return (
    <div>
      <nav aria-label={t('Vi phạm', 'Violations')} className="flex gap-2 border-b border-outline-variant bg-surface px-4 py-3">
        {[[ '/admin/violations', t('Nhật ký vi phạm', 'Violation log') ], [ '/admin/violations/report', t('Báo cáo & Thống kê', 'Reports & Statistics') ]].map(([to, label]) =>
          <NavLink key={to} to={to} end className={({ isActive }) => `rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${isActive ? 'bg-primary text-on-primary' : 'text-primary hover:bg-primary-container'}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </div>
  );
}
