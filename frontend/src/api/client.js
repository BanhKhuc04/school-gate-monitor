/**
 * Axios client for the School Gate Monitor API.
 *
 * API gọi về CÙNG địa chỉ với trang đang mở: chạy dev (vite :5173) thì vite
 * proxy /api, /media, /guard/* sang backend :8000 (xem vite.config.js); chạy
 * production (backend :8000 phục vụ luôn giao diện) thì trùng gốc sẵn. Nhờ vậy
 * mở giao diện từ máy khác/điện thoại trong cùng mạng (http://<ip-máy>:8000)
 * vẫn chạy — trước đây cứng 'http://localhost:8000' nên máy khác mở vào là
 * gọi nhầm về chính nó. Đè bằng VITE_API_BASE_URL nếu backend ở máy khác.
 * All API calls go through this instance so the auth interceptor is shared.
 */
import axios from 'axios';

// ponytail: export as constant so GuardPage + AlertBanner can reuse it
// instead of hardcoding the backend address in multiple places.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

// ── Request interceptor: attach JWT from localStorage ──────────────────────────
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: auto-logout on 401 (except login page itself) ───────
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginPage = typeof window !== 'undefined' && window.location.pathname === '/login';
    const isLoginRequest = error.config?.url?.includes('/api/auth/login');
    // Only redirect to login if we're not ALREADY on the login page AND this
    // isn't a login failure. Login page must show error, not redirect away.
    if (error.response?.status === 401 && !isLoginPage && !isLoginRequest) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
