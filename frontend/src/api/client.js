/**
 * Axios client for the School Gate Monitor API.
 *
 * baseURL dùng '' (relative) để axios tự lấy cùng origin với frontend (window.location).
 * Dev: Vite proxy config (`/api`, `/media`, `/guard/*`) chuyển tiếp sang backend
 *      đang chạy ở `http://localhost:8000` (xem vite.config.js).
 * Prod: reverse proxy cùng domain trỏ `/api`, `/media` về backend FastAPI.
 *
 * T2.2 — không hardcode URL localhost vào request gửi đi; axios tự resolve
 * theo base URL của page hiện tại. Khi cần ép dùng cùng origin (vd. môi trường
 * LAN với IP khác) thì không cần đổi code — chỉ cần frontend được serve qua
 * reverse proxy trỏ về backend.
 *
 * Lưu ý tương thích:
 * - URL kiểu `http://localhost:8000/...` đã có sẵn trong code (vd. trong
 *   components/RecognitionLogPanel/PlateReviewPanel của Task 1) vẫn hoạt động
 *   với Vite proxy và IP LAN trong dev. KHÔNG sửa những URL đó trong Task 2.
 */
import axios from 'axios';

export const API_BASE_URL = '';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  withCredentials: true, // receive the HttpOnly session used by protected images/clips
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
