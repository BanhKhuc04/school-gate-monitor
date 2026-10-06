import { NavLink, Outlet } from 'react-router-dom';

export default function ViolationsLayout() {
  return (
    <div>
      <nav aria-label="Vi phạm" className="flex gap-2 border-b border-outline-variant bg-surface px-4 py-3">
        {[[ '/admin/violations', 'Nhật ký vi phạm' ], [ '/admin/violations/report', 'Báo cáo & Thống kê' ]].map(([to, label]) =>
          <NavLink key={to} to={to} end className={({ isActive }) => `rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${isActive ? 'bg-primary text-on-primary' : 'text-primary hover:bg-primary-container'}`}>{label}</NavLink>)}
      </nav>
      <Outlet />
    </div>
  );
}
