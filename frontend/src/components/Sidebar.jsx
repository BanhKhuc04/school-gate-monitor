import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const ICONS = {
  camera: 'M4 8a2 2 0 0 1 2-2h1.5l1-1.5h7l1 1.5H18a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Zm8 2.25a3.25 3.25 0 1 0 0 6.5 3.25 3.25 0 0 0 0-6.5Z',
  alert: 'M12 3 2 20h20L12 3Zm0 6v5m0 3h.01',
  truck: 'M3 7h11v8H3V7Zm11 3h4l3 3v2h-7v-5ZM6.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm11 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z',
  chart: 'M4 20V10m6 10V4m6 16v-7m6 7V8',
  shield: 'M12 3l7 3v6c0 5-3.4 8.4-7 9-3.6-.6-7-4-7-9V6l7-3Z',
  users: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 20c0-3 2.7-5 6-5s6 2 6 5m2 0c0-2.5 2-4.5 6-4.5s6 2 6 4.5',
  zone: 'M4 6h16v12H4V6Zm3 3 4 4 3-3 3 5',
  logout: 'M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3m5-4 4-4-4-4m4 4H9',
  // Task 3 — database icon (collection/folder for training data)
  database: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 6c0 1.7 3.6 3 8 3s8-1.3 8-3V6c0 1.7-3.6 3-8 3s-8-1.3-8-3v6zm0 6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6c0 1.7-3.6 3-8 3s-8-1.3-8-3v6z',
};

function Icon({ path, className }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d={path} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Sidebar() {
  const { user, logout } = useAuth();
  const location = useLocation();

  if (!user) return null;

  const links = [];
  if (user.role === 'security' || user.role === 'admin' || user.role === 'management') {
    links.push({ to: '/guard', label: 'Giám sát', icon: 'camera' });
  }
  if (user.role === 'admin' || user.role === 'management') {
    links.push({ to: '/admin/violations', label: 'Vi phạm', icon: 'alert' });
    links.push({ to: '/admin/vehicles', label: 'Xe đăng ký', icon: 'truck' });
  }
  // Feature 9: teacher — scoped views for homeroom class
  if (user.role === 'teacher') {
    links.push({ to: '/teacher/violations', label: 'Vi phạm lớp tôi', icon: 'alert' });
    links.push({ to: '/teacher/vehicles', label: 'Danh sách xe lớp tôi', icon: 'truck' });
  }
  links.push({ to: '/settings', label: 'Cài đặt', icon: 'shield' });

  const roleLabel = {
    admin: 'Quản trị viên',
    security: 'Bảo vệ ca sáng',
    management: 'Ban giám hiệu',
    teacher: 'Giáo viên chủ nhiệm',
  }[user.role] || user.role;

  return (
    <aside className="md:fixed left-0 top-0 md:h-screen w-full md:w-64 bg-primary text-inverse-on-surface flex flex-col shrink-0">
      <div className="flex items-center gap-3 px-5 h-16 border-b border-white/10">
        <img src="/favicon.svg" alt="" className="w-8 h-8 rounded bg-surface" />
        <div className="leading-tight">
          <div className="font-bold text-sm">School Gate Monitor</div>
          <div className="text-[10px] uppercase tracking-wider text-inverse-on-surface/70 font-mono">
            Điều hành cổng trường AI
          </div>
        </div>
      </div>

      <div className="px-5 py-4 border-b border-white/10">
        <div className="text-[10px] uppercase tracking-wider text-inverse-on-surface/70 font-mono mb-1">
          Vai trò hiện tại
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
          <span className="truncate">{user.username} ({roleLabel})</span>
        </div>
      </div>

      <nav aria-label="Menu chính" className="flex flex-wrap md:block flex-1 px-3 py-3 md:space-y-1 overflow-y-auto">
        {links.map(({ to, label, icon }) => {
          const active = location.pathname === to || location.pathname.startsWith(`${to}/`);
          return (
            <Link
              key={to}
              to={to}
              aria-current={active ? 'page' : undefined}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                active ? 'bg-secondary text-on-secondary' : 'text-inverse-on-surface/80 hover:bg-white/10 hover:text-inverse-on-surface'
              }`}
            >
              <Icon path={ICONS[icon]} className="w-4.5 h-4.5 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      <button
        onClick={logout}
        className="flex items-center gap-3 px-5 py-4 border-t border-white/10 text-sm text-inverse-on-surface/70 hover:text-inverse-on-surface transition-colors"
      >
        <Icon path={ICONS.logout} className="w-4.5 h-4.5" />
        Đăng xuất ca trực
      </button>
    </aside>
  );
}
