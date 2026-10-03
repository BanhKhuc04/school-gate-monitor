import {useEffect, useRef, useState} from 'react';
import client from '../api/client';

export function useAudioLease(gate) {
  const [clientId] = useState(() => crypto.randomUUID());
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
