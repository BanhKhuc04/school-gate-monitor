import { useState, useEffect } from 'react';
import client from '../api/client';
import { formatDate } from '../utils/format';

const ROLES = ['admin', 'security', 'management'];
const ROLE_LABELS = { admin: 'Admin', security: 'Bảo vệ', management: 'Quản lý' };

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('security');
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
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadUsers();
    loadCurrentUser();
  }, []);

  function resetForm() {
    setUsername('');
    setPassword('');
    setRole('security');
    setEditingId(null);
    setError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      if (editingId) {
        const body = {};
        body.role = role;
        if (password) body.password = password;
        await client.put(`/api/users/${editingId}`, body);
      } else {
        if (!username || !password) return;
        await client.post('/api/users', {
          username: username.trim(),
          password,
          role,
        });
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

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Quản lý tài khoản</h1>

        {/* Form */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">
            {editingId ? `Sửa user #${editingId}` : 'Thêm user mới'}
          </h2>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                type="text"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder={editingId ? '(không đổi username)' : 'Username'}
                required={!editingId}
                disabled={!!editingId}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {editingId ? 'Mật khẩu mới (để trống = giữ)' : 'Mật khẩu'}
              </label>
              <input
                type="password"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required={!editingId}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Vai trò</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={role}
                onChange={e => setRole(e.target.value)}
              >
                {ROLES.map(r => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-4 flex gap-2 items-end">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
              >
                {editingId ? 'Lưu' : 'Thêm'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  Hủy
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center text-gray-500 py-8">Đang tải...</div>
        ) : users.length === 0 ? (
          <div className="text-center text-gray-400 py-8">Chưa có user nào.</div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Username</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Vai trò</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Ngày tạo</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-800">{u.username}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          u.role === 'admin' ? 'bg-purple-100 text-purple-700' :
                          u.role === 'security' ? 'bg-blue-100 text-blue-700' :
                          'bg-green-100 text-green-700'
                        }`}>
                          {ROLE_LABELS[u.role] || u.role}
                        </span>
                        {currentUser?.username === u.username && (
                          <span className="ml-1 text-xs text-gray-400">(bạn)</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatDate(u.created_at)}</td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <button
                          onClick={() => startEdit(u)}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          Sửa
                        </button>
                        {currentUser?.username !== u.username && (
                          <button
                            onClick={() => handleDelete(u.id)}
                            className="text-red-600 hover:text-red-800 text-sm font-medium"
                          >
                            Xóa
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 bg-gray-50 text-xs text-gray-500 border-t">
              Tổng: {users.length} tài khoản
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
