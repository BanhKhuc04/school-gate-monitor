import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import safetyBanner from '../assets/students-safety-banner.jpg';
import schoolLogo from '../assets/school-gate-logo.jpg';

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
      {/* Keep the banner in the build so its URL follows the deployed assets. */}
      <aside className="hidden lg:flex lg:w-[45%] shrink-0 flex-col justify-between gap-8 border-r border-outline-variant bg-primary/5 p-8 xl:p-10">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="flex items-center gap-3">
              <img src={schoolLogo} alt="" width="48" height="48" className="w-12 h-12 rounded-2xl border border-outline-variant bg-surface p-1 shrink-0 shadow-sm" />
              <div className="flex flex-col gap-1">
                <span className="font-bold text-lg text-primary">School Gate Monitor</span>
                <span className="text-xs uppercase tracking-wide text-on-surface-variant">
                Hệ thống AI giám sát cổng trường
                </span>
              </div>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-error-container px-3 py-1.5 text-[11px] font-bold uppercase text-on-error-container">
              <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
              Cổng trường an toàn
            </span>
          </div>

          <figure className="overflow-hidden rounded-3xl border border-outline-variant bg-surface p-3 shadow-sm mb-6">
            <img
              src={safetyBanner}
              alt="Học sinh đội mũ bảo hiểm trước cổng Trung tâm GDNN-GDTX Mỹ Hào. Cổng trường an toàn — Vững bước tương lai."
              width="1024"
              height="576"
              fetchPriority="high"
              className="block w-full aspect-video rounded-2xl object-contain"
            />
          </figure>

          <section aria-label="Giải pháp giám sát cổng trường" className="rounded-3xl border border-outline-variant bg-surface p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h2 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-primary">
                <span className="h-2 w-2 shrink-0 rounded-full bg-secondary" />
                Giải pháp giám sát &amp; nhận diện thông minh
              </h2>
              <span className="rounded-full bg-primary-container px-2.5 py-1 text-[11px] font-medium text-on-primary-container">AI tại cổng trường</span>
            </div>
            <p className="text-sm leading-relaxed text-on-surface mb-5">
              Hệ thống tự động nhận diện mũ bảo hiểm, biển số và phương tiện vào cổng,
              góp phần xây dựng văn hóa giao thông học đường văn minh.
            </p>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-2xl border border-outline-variant bg-primary-container px-2 py-4 text-primary">
                <p className="text-base xl:text-lg font-bold mb-1">Tức thời</p>
                <p className="text-xs">Nhận diện trực tiếp</p>
              </div>
              <div className="rounded-2xl bg-secondary px-2 py-4 text-on-secondary">
                <p className="text-base xl:text-lg font-bold mb-1">Tại chỗ</p>
                <p className="text-xs">Xử lý trên máy</p>
              </div>
              <div className="rounded-2xl border border-outline-variant bg-surface-container-low px-2 py-4 text-on-surface">
                <p className="text-base xl:text-lg font-bold mb-1">An toàn</p>
                <p className="text-xs">Bảo vệ học sinh</p>
              </div>
            </div>
          </section>
        </div>

        <p className="border-t border-outline-variant pt-5 text-xs leading-relaxed text-on-surface-variant">
          Dữ liệu giám sát vận hành theo{' '}
          <span className="text-primary font-semibold">Nghị định 13/2023/NĐ-CP</span>{' '}
          về bảo vệ dữ liệu cá nhân.
        </p>
      </aside>

      {/* Right panel — real login form */}
      <main className="min-w-0 flex-1 flex items-center justify-center p-6 lg:p-10">
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-8 lg:hidden">
            <img src={schoolLogo} alt="" width="40" height="40" className="w-10 h-10 rounded-xl border border-outline-variant p-1" />
            <span className="font-bold text-primary">School Gate Monitor</span>
          </div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container text-secondary font-mono text-[11px] font-semibold uppercase tracking-wider mb-5">
            <span className="w-1.5 h-1.5 rounded-full bg-secondary" />
            Cổng thông tin nội bộ
          </span>
          <h1 className="text-2xl font-bold text-on-surface mb-2">Đăng nhập hệ thống</h1>
          <p className="text-sm text-on-surface-variant mb-6">
            Dành cho bảo vệ, quản trị viên và ban giám hiệu được cấp quyền.
          </p>

          {error && (
            <div role="alert" className="bg-error-container text-on-error-container px-4 py-3 rounded-lg mb-4 text-sm">
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
              className="w-full bg-secondary hover:bg-secondary/90 text-on-secondary font-semibold py-2.5 px-4 rounded-lg transition-colors disabled:opacity-50"
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

          <p className="text-xs text-on-surface-variant mt-4">
            Phiên đăng nhập tự hết hạn sau 12 giờ.
          </p>
        </div>
      </main>
    </div>
  );
}
