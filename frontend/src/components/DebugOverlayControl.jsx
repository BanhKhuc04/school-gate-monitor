import { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import client from '../api/client';
import { useLang } from '../i18n/LanguageContext';

export default function DebugOverlayControl({ gate, name }) {
  const { user } = useAuth();
  const { t } = useLang();
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
      .catch(e => { if (active) setError(e.response?.data?.detail || t('Không đọc được cấu hình khung AI.', 'Could not read the AI overlay setting.')); });
    return () => { active = false; };
  }, [allowed, gate, t]);
  async function change(next) {
    setBusy(true); setError('');
    try {
      const { data } = await client.post('/guard/debug_overlay', null, { params: { gate, enabled: next } });
      setEnabled(data.enabled);
    } catch (e) { setError(e.response?.data?.detail || t('Đổi khung AI thất bại.', 'Could not change the AI overlay.')); }
    finally { setBusy(false); }
  }
  if (!allowed) return null;
  return (
    <div className="my-2 rounded bg-primary-container text-on-primary-container p-2 text-xs space-y-1">
      <label className="flex flex-wrap items-center gap-2">
        <input type="checkbox" checked={enabled} disabled={!loaded || busy} onChange={e => change(e.target.checked)} aria-label={`${t('Khung AI', 'AI overlay')} — ${name}`} />
        <span>{t('Hiển thị khung AI', 'Show AI overlay')} · {name}</span>
        <span className="text-on-surface-variant">{t('Áp dụng cho mọi người xem camera này.', 'Applies to everyone watching this camera.')}</span>
      </label>
      {error && <p role="alert" className="text-error">{error}</p>}
    </div>
  );
}
