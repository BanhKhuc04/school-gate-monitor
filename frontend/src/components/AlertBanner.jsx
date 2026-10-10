import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../api/client';
import { warmUpVoices, speakVietnamese, speakEnglish, stopSpeech, getVietnameseVoiceStatus } from '../utils/speak';
import { clipsForMessage, playClips } from '../utils/offlineVoice';
import { createAlertAudio, buildAlertMessage } from '../utils/alertAudio';
import { describeAlert, TONE_COLORS } from '../utils/alertDisplay';
import { useLang } from '../i18n/LanguageContext';

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
  const { lang, t } = useLang();
  const langRef = useRef(lang);
  langRef.current = lang;
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const [bannerBg, setBannerBg] = useState('#c92035');
  const timeoutRef = useRef(null);
  const wsRef = useRef(null);
  const audioRef = useRef(null);
  const clipPlayback = useRef(null);
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
          gain.gain.value = 0.7;
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
      // Recorded clips unless this machine has a LOCAL Vietnamese voice: the
      // browsers' Vietnamese voices are online-only, and a LAN without
      // internet still reports navigator.onLine === true.
      speak: (text, opts) => {
        if (lang === 'en') { speakEnglish(text, opts); return; }
        const clips = getVietnameseVoiceStatus().local ? null : clipsForMessage(text);
        if (!clips) { speakVietnamese(text, opts); return; }
        clipPlayback.current?.stop();
        clipPlayback.current = playClips(clips, { rate: opts?.rate ?? 1, volume: opts?.volume ?? 1 });
        clipPlayback.current.then(ok => { if (!ok) speakVietnamese(text, opts); });
      },
      cancel: () => { clipPlayback.current?.stop(); stopSpeech(); },
      config: { rate: lang === 'en' ? 1.1 : 1.45, volume: 1, debug: false },
      lang,
    });
    return () => {
      audioRef.current?.dispose?.();
      audioRef.current = null;
    };
  }, [audioEnabled, audioClientId, lang]);

  useEffect(() => {
    if (!token) return;
    // Cleanup helper — đóng WS + clear reconnect timer khi unmount/đổi gate.
    let stopped = false;
    let reconnectTimer = null;
    let currentWs = null;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = new URL(API_BASE_URL || window.location.origin).host;
    // QUAN TRỌNG (review F2): phải gửi client_id=audioClientId để backend
    // nhận diện speaker owner từ lease. Thiếu client_id → owns_audio()
    // luôn false → mọi alert có audio_authorized=false → helper bị dedup,
    // audio im lặng dù lease HTTP 200.
    const params = new URLSearchParams();
    params.set('token', token);
    params.set('gate', gate);
    if (audioClientId) {
      params.set('client_id', audioClientId);
    }
    const wsUrl = `${wsProtocol}//${wsHost}/guard/ws?${params.toString()}`;

    function handleAlert(data) {
      if (data?.type === 'gate_crossed') return;
      const { tone, title, detail } = describeAlert(data, langRef.current);
      setMessage(`${tone === 'info' ? '✅' : '⚠️'} ${title} — ${detail}`);
      setSnapshotUrl(data.snapshot_url || null);
      setVisible(true);
      setBannerBg(TONE_COLORS[tone]);
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
      if (stopped) return;
      try {
        const ws = new WebSocket(wsUrl);
        currentWs = ws;
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
          if (stopped) return;
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
          }, 3000);
        };
      } catch (e) {
        if (stopped) return;
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, 5000);
      }
    }

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (currentWs) {
        currentWs.onclose = null;
        currentWs.close();
      }
      if (wsRef.current === currentWs) wsRef.current = null;
    };
  }, [token, gate, audioEnabled, audioClientId]);

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
          alt={t('Ảnh chụp bằng chứng', 'Evidence snapshot')}
          style={{ height: '84px', borderRadius: '4px', border: '2px solid white' }}
        />
      )}
    </div>
  );
}

// Re-export for tests/UI showing the warning text without rebuilding it.
export { buildAlertMessage };