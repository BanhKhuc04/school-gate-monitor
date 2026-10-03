import { createContext, useContext, useState, useEffect } from 'react';
import client from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const [token, setToken] = useState(() => localStorage.getItem('token'));

  useEffect(() => {
    if (user) {
      localStorage.setItem('user', JSON.stringify(user));
    } else {
      localStorage.removeItem('user');
    }
  }, [user]);

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }, [token]);

  /**
   * Login with username + password.
   * @returns {object} user {username, role}
   * @throws {Error} if credentials are invalid (HTTP status != 2xx)
   */
  const login = async (username, password) => {
    const res = await client.post('/api/auth/login', { username, password });
    // axios doesn't throw on 4xx by default — explicitly check status
    if (res.status !== 200) {
      throw new Error(res.data?.detail || 'Login failed');
    }
    const { access_token, username: u, role, homeroom_class } = res.data;
    setToken(access_token);
    // Lưu homeroom_class cho teacher để UI hiện "lớp tôi". Quyền dữ liệu vẫn
    // do server quyết định — FE chỉ hiển thị, KHÔNG dùng để filter phía client.
    const userData = { username: u, role, homeroom_class: homeroom_class || null };
    setUser(userData);
    return userData;
  };

  const logout = async () => {
    try {
      // Gọi API để xóa session cookie (chỉ có tác dụng khi dùng cookie session)
      await client.post('/api/auth/logout');
    } catch {
      // ignore errors — client-side cleanup vẫn phải chạy
    } finally {
      setToken(null);
      setUser(null);
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    }
  };

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
