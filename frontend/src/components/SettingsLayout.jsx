import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function SettingsLayout() {
  const { user } = useAuth();
  const links = [['/settings', 'Tài khoản của tôi']];
  if (user?.role === 'admin') links.push(
    ['/settings/camera', 'Camera'], ['/settings/roi', 'ROI / Vạch cổng'],
    ['/settings/storage', 'Sức khỏe & Lưu trữ'], ['/settings/users', 'Tài khoản'],
    ['/settings/ai', 'AI nâng cao'],
  );
  return (
    <div>
      <nav aria-label="Cài đặt" className="flex flex-wrap gap-2 border-b border-outline-variant bg-surface px-4 py-3">
        {links.map(([to, label]) => <NavLink key={to} to={to} end={to === '/settings'}
          className={({ isActive }) => `rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${isActive ? 'bg-primary text-on-primary' : 'text-primary hover:bg-primary-container'}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </div>
  );
}
