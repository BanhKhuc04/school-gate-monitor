import { useState, useEffect } from 'react';
import client from '../api/client';

const ROLES = ['admin', 'security', 'management', 'teacher'];
const ROLE_LABELS = {
  admin: 'Admin',
  security: 'Bảo vệ',
  management: 'Quản lý',
  teacher: 'Giáo viên',
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('security');
  const [homeroomClass, setHomeroomClass] = useState('');
  const [editingId, setEditingId] = useState(null);

  async function loadUsers() {
    setLoading(true);
    setError('');
    try {
      const res = await client.get('/api/users');
      setUsers(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Không tải được danh sách user');
    } finally {
      setLoading(false);
    }
  }

  async function loadCurrentUser() {
    try {
      const res = await client.get('/api/auth/me');
      setCurrentUser(res.data);
    } catch { /* ignore */ }
  }

  useEffect(() => {
    loadUsers();
    loadCurrentUser();
  }, []);

  function resetForm() {
    setUsername('');
    setPassword('');
    setRole('security');
    setHomeroomClass('');
    setEditingId(null);
    setError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      const body = { role };
      if (password) body.password = password;
      if (role === 'teacher' && homeroomClass.trim()) body.homeroom_class = homeroomClass.trim().toUpperCase();
      if (editingId) {
        await client.put(`/api/users/${editingId}`, body);
      } else {
        if (!username || !password) return;
        body.username = username.trim();
        await client.post('/api/users', body);
      }
      resetForm();
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Lỗi khi lưu');
    }
  }

  function startEdit(user) {
    setEditingId(user.id);
    setUsername(user.username);
    setPassword('');
    setRole(user.role);
    setHomeroomClass(user.homeroom_class || '');
    setError('');
  }

  async function handleDelete(userId) {
    const user = users.find(u => u.id === userId);
    if (!confirm(`Xóa user "${user?.username}"?`)) return;
    setError('');
    try {
      await client.delete(`/api/users/${userId}`);
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xóa thất bại');
    }
  }

  const ROLE_COLORS = {
    admin: { bg: 'bg-[#dbe3ee]', text: 'text-[#dbe3ee]', dot: 'bg-[#f8d7dc]' },
    security: { bg: 'bg-[#f4f6f9]', text: 'text-[#c92035]', dot: 'bg-[#c92035]' },
    management: { bg: 'bg-[#e8f5e9]', text: 'text-[#2e7d32]', dot: 'bg-[#10b981]' },
    teacher: { bg: 'bg-[#fef3c7]', text: 'text-[#92400e]', dot: 'bg-[#f59e0b]' },
  };

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <p className="font-mono text-xs uppercase tracking-wider text-[#c92035] mb-1">Bảo mật &amp; cấp quyền</p>
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-2xl font-bold text-[#374151]">Quản lý Tài khoản Hệ thống</h1>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-[#eceff3] text-[#6b7280]">
            {users.length} tài khoản
          </span>
        </div>
        <p className="text-sm text-[#6b7280] mb-6">Phân quyền truy cập hệ thống camera AI theo 3 vai trò.</p>

        {/* Role count cards — số thật từ danh sách user, không bịa lịch sử đăng nhập/thiết bị */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
          {ROLES.map((r) => (
            <div key={r} className="bg-white rounded-xl p-4 shadow-sm border border-[#d1d5db]">
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">
                {ROLE_LABELS[r]}
              </p>
              <p className="text-3xl font-bold font-mono text-[#123b6d] mt-1">
                {users.filter((u) => u.role === r).length}
              </p>
            </div>
          ))}
        </div>

        {/* Add/Edit form */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {editingId ? `Sửa tài khoản` : 'Thêm tài khoản mới'}
          </h2>

          {error && (
            <div className="bg-[#f8d7dc] border border-[#f0aab3] text-[#7a1422] px-4 py-3 rounded-xl mb-4 text-[12px] font-mono">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Username
                </label>
                <input
                  type="text"
                  className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none focus:ring-2 focus:ring-[#c92035]"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder={editingId ? '(không đổi)' : 'Username'}
                  required={!editingId}
                  disabled={!!editingId}
                />
              </div>
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  {editingId ? 'Mật khẩu mới' : 'Mật khẩu'}
                </label>
                <input
                  type="password"
                  className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none focus:ring-2 focus:ring-[#c92035]"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required={!editingId}
                />
              </div>
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Vai trò
                </label>
                <div className="relative">
                  <select
                    className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none appearance-none cursor-pointer pr-8"
                    value={role}
                    onChange={e => {
                      setRole(e.target.value);
                      if (e.target.value !== 'teacher') setHomeroomClass('');
                    }}
                  >
                    {ROLES.map(r => (
                      <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                    ))}
                  </select>
                  <svg className="absolute right-2.5 top-2.5 w-4 h-4 text-[#6b7280] pointer-events-none" viewBox="0 0 24 24" fill="none">
                    <path d="M19 9l-7 7-7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
              </div>
              {/* Feature 9: homeroom_class — shown only when role === 'teacher' */}
              {role === 'teacher' && (
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Lớp chủ nhiệm
                </label>
                <input
                  type="text"
                  className="w-full bg-[#fef3c7] rounded-lg px-3 py-2 text-[12px] font-mono text-[#92400e] border-0 outline-none focus:ring-2 focus:ring-[#f59e0b]"
                  value={homeroomClass}
                  onChange={e => setHomeroomClass(e.target.value.toUpperCase())}
                  placeholder="10A1"
                  maxLength={10}
                />
                {!homeroomClass && (
                  <p className="text-[10px] font-mono text-[#c92035] mt-0.5">Bắt buộc cho giáo viên</p>
                )}
              </div>
              )}
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                className="flex items-center gap-1.5 bg-[#c92035] hover:bg-[#c92035] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                {editingId ? 'Lưu' : 'Thêm'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <path d="M6 18L18 6M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  Hủy
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Users table */}
        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Đang tải...
          </div>
        ) : users.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center border border-[#d1d5db]">
            <p className="text-[#6b7280]">Chưa có tài khoản nào.</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[600px]">
                <thead>
                  <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">Username</th>
                    <th className="py-3 px-3 font-semibold">Vai trò</th>
                    <th className="py-3 px-3 font-semibold">Lớp chủ nhiệm</th>
                    <th className="py-3 px-3 font-semibold">Ngày tạo</th>
                    <th className="py-3 px-4 text-right font-semibold">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {users.map((u) => {
                    const colors = ROLE_COLORS[u.role] || ROLE_COLORS.security;
                    return (
                      <tr key={u.id} className="hover:bg-[#ffffff] transition-colors">
                        <td className="py-3 px-4 font-semibold">{u.username}</td>
                        <td className="py-3 px-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono text-[10px] font-semibold ${colors.bg} ${colors.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
                            {ROLE_LABELS[u.role] || u.role}
                          </span>
                          {currentUser?.username === u.username && (
                            <span className="ml-1.5 font-mono text-[10px] text-[#9ca3af]">(bạn)</span>
                          )}
                        </td>
                        {/* Feature 9: show homeroom_class */}
                        <td className="py-3 px-3 font-mono text-[11px]">
                          {u.homeroom_class ? (
                            <span className="px-2 py-0.5 bg-[#fef3c7] text-[#92400e] rounded text-[10px] font-semibold">
                              {u.homeroom_class}
                            </span>
                          ) : (
                            <span className="text-[#9ca3af]">—</span>
                          )}
                        </td>
                        <td className="py-3 px-3 font-mono text-[11px] text-[#6b7280] whitespace-nowrap">
                          {new Date(u.created_at).toLocaleDateString('vi-VN')}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => startEdit(u)}
                              className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f4f6f9] transition-colors"
                            >
                              Sửa
                            </button>
                            {currentUser?.username !== u.username && (
                              <button
                                onClick={() => handleDelete(u.id)}
                                className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f8d7dc] transition-colors"
                              >
                                Xóa
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 bg-[#f4f6f9] border-t border-[#d1d5db]">
              <span className="font-mono text-[11px] text-[#6b7280]">
                Tổng: <span className="font-bold text-[#374151]">{users.length}</span> tài khoản
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
