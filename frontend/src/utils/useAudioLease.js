import {useEffect, useRef, useState} from 'react';
import client from '../api/client';

// UUID an toàn cho cả origin HTTP LAN (crypto.randomUUID chỉ có ở secure
// context). Fallback dùng crypto.getRandomValues để tạo UUID v4 format
// RFC 4122 — đảm bảo mỗi tab/instance có UUID khác nhau, audioClientId
// khớp lease owner, WS speaker check pass.
function safeUUID() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {}
  if (typeof crypto === 'undefined' || typeof crypto.getRandomValues !== 'function') {
    // Không có crypto API — fallback Math.random() (UUID format hợp lệ, đủ
    // dùng cho owner identity local).
    const hex = (n) => Math.floor(Math.random() * 0x100).toString(16).padStart(2, '0');
    return ([1e7]+-1e3+-4e3+-8e5+-1e11).replace(/[018]/g, (c) =>
      (c ^ (Math.random() * 16) >> (c / 4)).toString(16));
  }
  const buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  // version 4 + variant theo RFC 4122
  buf[6] = (buf[6] & 0x0f) | 0x40;
  buf[8] = (buf[8] & 0x3f) | 0x80;
  const hex = Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

export function useAudioLease(gate) {
  // State khởi tạo bằng lazy initializer — chỉ chạy 1 lần khi mount,
  // đảm bảo mỗi tab/instance có UUID khác nhau (không bị reset khi re-render).
  const [clientId] = useState(() => safeUUID());
  const [leaseGate, setLeaseGate] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const currentGate = useRef(gate);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    currentGate.current = gate;
    if (leaseGate && leaseGate !== gate) setLeaseGate(null);
  }, [gate, leaseGate]);
  useEffect(() => {
    if (!leaseGate) return;
    let stopped = false;
    const data = {client_id:clientId, gate_id:leaseGate};
    const heartbeat = setInterval(async () => {
      try { await client.post('/guard/audio/lease', data); }
      catch {
        if (!stopped) { setLeaseGate(null); setError('Mất quyền phát loa; vui lòng bật lại.'); }
      }
    }, 5000);
    return () => {
      stopped = true;
      clearInterval(heartbeat);
      client.delete('/guard/audio/lease', {data}).catch(() => {});
    };
  }, [leaseGate, clientId]);
  async function toggle() {
    if (busy) return;
    if (leaseGate === gate) { setLeaseGate(null); return; }
    setBusy(true); setError('');
    const data = {client_id:clientId, gate_id:gate};
    try {
      await client.post('/guard/audio/lease', data);
      if (mounted.current && currentGate.current === gate) setLeaseGate(gate);
      else client.delete('/guard/audio/lease', {data}).catch(() => {});
    } catch (err) {
      if (mounted.current) setError(err.response?.data?.detail || 'Không bật được loa trên máy này.');
    } finally { if (mounted.current) setBusy(false); }
  }
  return {enabled:leaseGate === gate, clientId, busy, error, toggle};
}
