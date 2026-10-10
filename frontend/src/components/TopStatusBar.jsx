import { useState, useEffect } from 'react';
import { useAuth } from '../auth/AuthContext';
import client from '../api/client';

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

// ponytail: poll /api/system/health mỗi 10s thay vì WebSocket riêng cho status bar —
// dữ liệu này đổi chậm (pipeline lên/xuống), không cần realtime tới mức WS.
function useHealthGates(enabled) {
  const [gatesHealth, setGatesHealth] = useState({});
  const [gatesList, setGatesList] = useState([]);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    function fetchHealth() {
      client.get('/api/system/health').then((res) => {
        if (!cancelled) {
          const map = {};
          (res.data.gates || []).forEach(g => { map[g.id] = g.pipeline || {}; });
          setGatesHealth(map);
          setGatesList(res.data.gates || []);
        }
      }).catch(() => {
        if (!cancelled) { setGatesHealth({}); setGatesList([]); }
      });
    }
    fetchHealth();
    const id = setInterval(fetchHealth, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, [enabled]);
  return { gatesHealth, gatesList };
}

export default function TopStatusBar({ activeGate = 'main' }) {
  const { user } = useAuth();
  const now = useClock();
  // Teacher role can't call /api/system/health (403) — skip polling entirely for them.
  const { gatesHealth, gatesList } = useHealthGates(user?.role !== 'teacher');
  const pipeline = gatesHealth[activeGate] || {};

  const timeStr = now.toLocaleTimeString('vi-VN', { hour12: false });

  return (
    <header className="min-h-14 bg-surface border-b border-outline-variant flex flex-wrap md:flex-nowrap items-center justify-between px-4 md:px-6 py-3 gap-3 text-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`w-2 h-2 rounded-full ${pipeline?.running ? 'bg-emerald-500' : 'bg-outline'}`} />
        <span className="font-mono text-xs text-on-surface-variant">
          PIPELINE: {pipeline === null ? 'KHÔNG XÁC ĐỊNH' : pipeline.running ? 'ĐANG CHẠY' : 'DỪNG'}
        </span>
        {gatesList.map(gate => {
          const gp = gatesHealth[gate.id] || {};
          return [
            <span key={"dot-" + gate.id} className="text-outline mx-1">•</span>,
            <span key={"s-" + gate.id} className="flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${gp.camera_open ? 'bg-emerald-500' : 'bg-secondary'}`} />
              <span className="font-mono text-xs text-on-surface-variant">
                {gate.name?.toUpperCase()}: {gp.camera_open ? 'ONLINE' : 'OFFLINE'}
              </span>
            </span>
          ];
        })}
      </div>
      <div className="flex items-center gap-4">
        <span className="font-mono text-xs text-on-surface-variant">{timeStr} GMT+7</span>
        <span className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center text-xs font-bold">
          {user?.username?.[0]?.toUpperCase() || '?'}
        </span>
      </div>
    </header>
  );
}
