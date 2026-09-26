/**
 * Axios client for the School Gate Monitor API.
 *
 * baseURL hardcoded to http://localhost:8000 — no .env file for this small project.
 * All API calls go through this instance so the auth interceptor is shared.
 */
import axios from 'axios';

const client = axios.create({
  baseURL: 'http://localhost:8000',
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

// ── Response interceptor: auto-logout on 401 ──────────────────────────────────
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
