import { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import client from '../api/client';

export default function DebugOverlayControl({ gate, name }) {
  const { user } = useAuth();
  const allowed = user?.role === 'admin' || user?.role === 'management';
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!allowed) return;
    let active = true;
    client.get('/guard/debug_overlay', { params: { gate } })
      .then(({ data }) => { if (active) { setEnabled(data.enabled); setLoaded(true); } })
      .catch(e => { if (active) setError(e.response?.data?.detail || 'Không đọc được cấu hình khung AI.'); });
    return () => { active = false; };
  }, [allowed, gate]);
  async function change(next) {
    setBusy(true); setError('');
    try {
      const { data } = await client.post('/guard/debug_overlay', null, { params: { gate, enabled: next } });
      setEnabled(data.enabled);
    } catch (e) { setError(e.response?.data?.detail || 'Đổi khung AI thất bại.'); }
    finally { setBusy(false); }
  }
  if (!allowed) return null;
  return (
    <div className="my-2 rounded bg-primary-container text-on-primary-container p-2 text-xs space-y-1">
      <label className="flex flex-wrap items-center gap-2">
        <input type="checkbox" checked={enabled} disabled={!loaded || busy} onChange={e => change(e.target.checked)} aria-label={`Khung AI — ${name}`} />
        <span>Hiển thị khung AI · {name}</span>
        <span className="text-on-surface-variant">Áp dụng cho mọi người xem camera này.</span>
      </label>
      {error && <p role="alert" className="text-error">{error}</p>}
    </div>
  );
}
