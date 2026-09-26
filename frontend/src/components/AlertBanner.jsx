import { useState, useEffect, useRef } from 'react';

/**
 * AlertBanner — connects to /guard/ws WebSocket and shows a red banner
 * with audio beep when a violation alert arrives.
 */
export default function AlertBanner({ token }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const timeoutRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!token) return;

    // GuardPage always serves video from :8000; use same for WS
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = 'localhost:8000'; // always :8000 regardless of dev/prod
    const wsUrl = `${wsProtocol}//${wsHost}/guard/ws?token=${token}`;

    function playBeep() {
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 800;
        gain.gain.value = 0.3;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.2);
      } catch (e) {
        // Audio might be blocked by browser without user interaction — silently ignore
        console.warn('[AlertBanner] Audio playback blocked:', e.message);
      }
    }

    function showBanner(violationType) {
      setMessage('\u26a0\ufe0f C\u1ea2NH B\u00c1O: ' + violationType);
      setVisible(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setVisible(false), 3000);
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
            showBanner(data.violation_type);
            playBeep();
          } catch (e) {
            // Malformed message — ignore
          }
        };
        ws.onerror = () => {
          // Silently handle WS errors — don't let them propagate to window
        };
        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
          // Reconnect after 3s if component still mounted
          reconnectTimer = setTimeout(connect, 3000);
        };
      } catch (e) {
        // Failed to construct WebSocket — retry later
        reconnectTimer = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [token]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        backgroundColor: '#dc3545',
        color: 'white',
        padding: '15px 20px',
        textAlign: 'center',
        fontSize: '18px',
        fontWeight: 'bold',
        zIndex: 1000,
        display: visible ? 'block' : 'none',
      }}
    >
      {message}
    </div>
  );
}
