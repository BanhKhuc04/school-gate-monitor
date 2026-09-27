/**
 * Axios client for the School Gate Monitor API.
 *
 * baseURL hardcoded to http://localhost:8000 — no .env file for this small project.
 * All API calls go through this instance so the auth interceptor is shared.
 */
import axios from 'axios';

// ponytail: export as constant so GuardPage + AlertBanner can reuse it
// instead of hardcoding 'http://localhost:8000' in multiple places.
export const API_BASE_URL = 'http://localhost:8000';

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
