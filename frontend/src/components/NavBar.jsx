import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function NavBar() {
  const { user, logout } = useAuth();
  const location = useLocation();

  if (!user) return null;

  const links = [];
  if (user.role === 'admin') {
    links.push({ to: '/admin/users', label: 'Tài khoản' });
    links.push({ to: '/admin/vehicles', label: 'Xe đăng ký' });
    links.push({ to: '/admin/violations', label: 'Vi phạm' });
    links.push({ to: '/admin/health', label: 'Hệ thống' });
  }
  if (user.role === 'security' || user.role === 'admin') {
    links.push({ to: '/guard', label: 'Camera' });
  }
  if (user.role === 'management' || user.role === 'admin') {
    links.push({ to: '/dashboard', label: 'Dashboard' });
  }

  return (
    <nav className="bg-white shadow-sm border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          {/* Logo + brand */}
          <div className="flex items-center gap-6">
            <span className="font-semibold text-gray-800 text-sm">School Gate Monitor</span>
            <div className="flex items-center gap-1">
              {links.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    location.pathname === to
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

          {/* User info + logout */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">
              {user.username}
              <span className="ml-1 text-xs text-gray-400">({user.role})</span>
            </span>
            <button
              onClick={logout}
              className="text-sm text-gray-500 hover:text-red-600 transition-colors"
            >
              Đăng xuất
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
