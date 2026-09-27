import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../api/client';

/**
 * AlertBanner — connects to /guard/ws WebSocket and shows a banner
 * with audio beep when a violation or face_match alert arrives.
 *
 * Style:
 *   - violation: red (#dc3545)
 *   - face_match: amber (#f59e0b)
 */
export default function AlertBanner({ token }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [alertType, setAlertType] = useState('violation'); // 'violation' | 'face_match'
  const timeoutRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!token) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = API_BASE_URL.replace('http://', '').replace('https://', '');
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
        console.warn('[AlertBanner] Audio blocked:', e.message);
      }
    }

    function handleAlert(data) {
      if (data.type === 'face_match') {
        setAlertType('face_match');
        setMessage(
          '\u{1F3ED} NH\u1eacN DI\u1ec6N KHU\u00d4N M\u1eb6T: ' +
          `${data.matched_label} (${(data.similarity * 100).toFixed(0)}%)`
        );
      } else {
        setAlertType('violation');
        setMessage('\u26a0\ufe0f C\u1ea2NH B\u00c1O: ' + (data.violation_type || data.type));
      }
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
            handleAlert(data);
            playBeep();
          } catch (e) {
            // Malformed message
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
  }, [token]);

  const bgColor = alertType === 'face_match' ? '#f59e0b' : '#dc3545';

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        backgroundColor: bgColor,
        color: alertType === 'face_match' ? '#1c1917' : 'white',
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
