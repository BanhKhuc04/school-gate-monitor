import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user = await login(username, password);

      // Redirect based on role
      if (user.role === 'security') {
        navigate('/guard');
      } else if (user.role === 'admin') {
        navigate('/admin/vehicles');
      } else if (user.role === 'management') {
        navigate('/dashboard');
      } else {
        navigate('/');
      }
    } catch (err) {
      // axios doesn't throw on 4xx by default — check status explicitly
      const msg = err.response?.data?.detail || 'Đăng nhập thất bại';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-surface font-sans">
      {/* Left panel — branding + camera HUD illustration, hidden below lg */}
      <div className="hidden lg:flex lg:w-[46%] xl:w-[42%] flex-col justify-between bg-primary text-inverse-on-surface p-10">
        <div>
          <div className="flex items-center gap-3 mb-10">
            <img src="/favicon.svg" alt="" className="w-10 h-10 rounded-lg bg-surface shrink-0" />
            <div className="flex flex-col leading-tight">
              <span className="font-bold text-base">School Gate Monitor</span>
              <span className="text-xs uppercase tracking-wider text-on-primary-container font-mono">
                Hệ thống AI giám sát cổng trường
              </span>
            </div>
          </div>

          {/* Camera HUD mock */}
          <div className="relative rounded-xl overflow-hidden bg-primary-container aspect-[4/3] mb-8">
            <div className="absolute top-0 left-0 right-0 p-3 flex items-center justify-between font-mono text-[10px] text-on-primary-container">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-error animate-pulse" />
                CAM_01 · CỔNG CHÍNH
              </span>
              <span>AI_ON</span>
            </div>
            <div className="absolute bottom-3 left-3 right-3 bg-primary/85 backdrop-blur-sm rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-tertiary-fixed font-mono text-[11px] font-bold mb-1">
                <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5">
                  <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                CỔNG TRƯỜNG AN TOÀN
              </div>
              <p className="text-xs text-on-primary-container">
                Nhận diện mũ bảo hiểm, biển số &amp; tư thế lên xe theo thời gian thực.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-primary-container p-3">
              <span className="block text-[10px] uppercase tracking-wider text-on-primary-container font-mono mb-1">
                Loại vi phạm phân biệt
              </span>
              <span className="text-xl font-bold font-mono">3</span>
            </div>
            <div className="rounded-lg bg-primary-container p-3">
              <span className="block text-[10px] uppercase tracking-wider text-on-primary-container font-mono mb-1">
                Xử lý tại chỗ
              </span>
              <span className="text-xl font-bold font-mono">Không cần internet</span>
            </div>
          </div>
        </div>

        <p className="text-xs text-on-primary-container">
          Dữ liệu giám sát vận hành theo{' '}
          <span className="text-inverse-on-surface font-semibold">Nghị định 13/2023/NĐ-CP</span>{' '}
          về bảo vệ dữ liệu cá nhân.
        </p>
      </div>

      {/* Right panel — real login form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container text-secondary font-mono text-[11px] font-semibold uppercase tracking-wider mb-5">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
            Cổng thông tin nội bộ
          </span>
          <h1 className="text-2xl font-bold text-on-surface mb-2">Đăng nhập hệ thống</h1>
          <p className="text-sm text-on-surface-variant mb-6">
            Dành cho bảo vệ, quản trị viên và ban giám hiệu được cấp quyền.
          </p>

          {error && (
            <div className="bg-error-container text-on-error-container px-4 py-3 rounded-lg mb-4 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1" htmlFor="username">
                Tên đăng nhập
              </label>
              <input
                id="username"
                type="text"
                className="w-full border border-outline-variant rounded-lg px-3 py-2 text-sm bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-secondary"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-on-surface mb-1" htmlFor="password">
                Mật khẩu
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className="w-full border border-outline-variant rounded-lg px-3 py-2 pr-10 text-sm bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-secondary"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface-variant"
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                >
                  {showPassword ? (
                    <svg viewBox="0 0 24 24" fill="none" className="w-4.5 h-4.5">
                      <path d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.1A9.8 9.8 0 0112 5c5 0 9 4 10 7-.4 1.1-1.1 2.3-2 3.4M6.6 6.6C4.6 8 3.2 9.9 2 12c1.3 3.9 5.3 7 10 7 1.2 0 2.4-.2 3.5-.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" className="w-4.5 h-4.5">
                      <path d="M2 12c1.3-3.9 5.3-7 10-7s8.7 3.1 10 7c-1.3 3.9-5.3 7-10 7s-8.7-3.1-10-7Z" stroke="currentColor" strokeWidth="1.6" />
                      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.6" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="w-full bg-secondary hover:bg-secondary-container text-on-secondary font-semibold py-2.5 px-4 rounded-lg transition-colors disabled:opacity-50"
              disabled={loading}
            >
              {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
            </button>
          </form>

          <div className="mt-6 border border-outline-variant rounded-lg p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant mb-2">
              Tài khoản demo theo vai trò (click để tự điền)
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { role: 'admin', pass: 'admin123', label: 'Quản trị viên' },
                { role: 'security', pass: 'security123', label: 'Bảo vệ cổng' },
                { role: 'management', pass: 'management123', label: 'Ban giám hiệu' },
              ].map((acc) => (
                <button
                  key={acc.role}
                  type="button"
                  onClick={() => { setUsername(acc.role); setPassword(acc.pass); }}
                  className="text-left border border-outline-variant rounded-md px-2 py-1.5 hover:bg-surface-container-low transition-colors"
                >
                  <span className="block text-[11px] font-semibold text-on-surface">{acc.label}</span>
                  <span className="block font-mono text-[10px] text-on-surface-variant">{acc.role}</span>
                </button>
              ))}
            </div>
          </div>

          <p className="text-xs text-outline mt-4 font-mono">
            Phiên đăng nhập dùng JWT, tự hết hạn sau 12 giờ.
          </p>
        </div>
      </div>
    </div>
  );
}
