import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../api/client';
import { warmUpVoices, speakVietnamese, stopSpeech } from '../utils/speak';
import { getAlertPriority } from '../utils/alertPriority';
import { createAlertAudio, buildAlertMessage } from '../utils/alertAudio';

/**
 * AlertBanner — connects to /guard/ws WebSocket and renders a banner with
 * a short beep + Vietnamese TTS per confirmed violation. The audio pipeline
 * runs through `createAlertAudio` so filtering, deduplication, lease gating,
 * TTL and queueing all live in one tested helper instead of legacy branches.
 *
 * Audio only when the user has acquired a speaker lease via useAudioLease().
 * Other viewers stay silent on the same gate (split-view rule).
 */

export default function AlertBanner({ token, onAlert, gate = 'main',
  audioEnabled = false, audioClientId = null }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const [bannerBg, setBannerBg] = useState('#c92035');
  const timeoutRef = useRef(null);
  const wsRef = useRef(null);
  const audioRef = useRef(null);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  useEffect(() => {
    warmUpVoices();
  }, []);

  // (Re)build the audio helper whenever the lease state changes so disposed
  // AudioContexts and dedup Sets are released when this tab loses the lease.
  useEffect(() => {
    audioRef.current?.dispose?.();
    audioRef.current = null;
    if (!audioEnabled || !audioClientId) return;
    audioRef.current = createAlertAudio({
      beep: (code) => {
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.value = code === 'RIDING_THROUGH_GATE' ? 520
            : code === 'TOO_MANY_RIDERS' ? 460
            : code === 'NO_HELMET' ? 600 : 800;
          gain.gain.value = 0.3;
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start();
          osc.onended = () => ctx.close().catch(() => {});
          setTimeout(() => osc.stop(), 180);
        } catch (e) {
          console.warn('[AlertBanner] beep blocked:', e.message);
        }
        return 220;
      },
      speak: (text, opts) => speakVietnamese(text, opts),
      cancel: () => stopSpeech(),
      config: { rate: 1.25, volume: 1, debug: false },
    });
    return () => {
      audioRef.current?.dispose?.();
      audioRef.current = null;
    };
  }, [audioEnabled, audioClientId]);

  useEffect(() => {
    if (!token) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = new URL(API_BASE_URL || window.location.origin).host;
    const wsUrl = `${wsProtocol}//${wsHost}/guard/ws?token=${token}&gate=${gate}`;

    function handleAlert(data) {
      const priority = getAlertPriority(data.violation_type);
      setMessage('⚠️ CẢNH BÁO: ' + (data.violation_type || data.type));
      setSnapshotUrl(data.snapshot_url || null);
      setVisible(true);
      setBannerBg(priority === 'high' ? '#c92035' : '#f59e0b');
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setVisible(false), 3000);

      // Route through the tested helper when this tab owns the speaker
      // lease. Older tabs without the lease stay silent so the second
      // viewer never doubles an announcement on a single physical speaker.
      if (audioRef.current && audioEnabled) {
        try { audioRef.current.accept(data); }
        catch (e) { console.warn('[AlertBanner] audio.accept failed:', e.message); }
      }

      onAlertRef.current?.(data);
    }

    function connect() {
      let reconnectTimer = null;
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => console.log('[AlertBanner] WS connected');
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            handleAlert(data);
          } catch (e) {
            // Malformed message — ignored on purpose
          }
        };
        ws.onerror = () => {
          // Silently handle WS errors
        };
        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
          reconnectTimer = setTimeout(connect, 3000);
        };
      } catch (e) {
        reconnectTimer = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [token, gate, audioEnabled]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        backgroundColor: bannerBg,
        color: 'white',
        padding: '15px 20px',
        textAlign: 'center',
        fontSize: '18px',
        fontWeight: 'bold',
        zIndex: 1000,
        display: visible ? 'flex' : 'none',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '12px',
      }}
    >
      <span>{message}</span>
      {snapshotUrl && (
        <img
          src={`${API_BASE_URL}${snapshotUrl}`}
          alt="Ảnh chụp bằng chứng"
          style={{ height: '84px', borderRadius: '4px', border: '2px solid white' }}
        />
      )}
    </div>
  );
}

// Re-export for tests/UI showing the warning text without rebuilding it.
export { buildAlertMessage };