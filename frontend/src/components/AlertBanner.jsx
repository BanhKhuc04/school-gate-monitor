import { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../api/client';

/**
 * AlertBanner — connects to /guard/ws WebSocket and shows a red banner
 * with a distinct beep pattern + Vietnamese TTS per violation type, plus
 * a snapshot thumbnail if one is available.
 *
 * ponytail: còi/loa vật lý qua GPIO chưa được xây dựng — chưa có phần cứng
 * (không có speaker/relay/GPIO nào để lái). Khi có phần cứng thật, thêm một
 * lệnh gọi API riêng ở đây (hoặc side-effect ở backend khi push alert) để
 * kích còi vật lý; audio hiện tại chỉ chạy trong trình duyệt của bảo vệ.
 */

// Mỗi loại vi phạm có tần số + số nhịp beep riêng để phân biệt bằng tai
// trước khi nghe rõ nội dung TTS.
const ALERT_SOUNDS = {
  NO_HELMET: { freq: 600, beeps: 1, beepDuration: 0.3, gap: 0.1 },
  PLATE_NOT_REGISTERED: { freq: 1000, beeps: 2, beepDuration: 0.15, gap: 0.1 },
  PLATE_UNREADABLE: { freq: 1000, beeps: 2, beepDuration: 0.15, gap: 0.1 },
  RIDING_THROUGH_GATE: { freq: 500, beeps: 3, beepDuration: 0.15, gap: 0.1 },
  MULTIPLE: { freq: 700, beeps: 2, beepDuration: 0.2, gap: 0.1 },
  default: { freq: 800, beeps: 1, beepDuration: 0.2, gap: 0.1 },
};

function buildSpeechText(data) {
  const plate = data.plate_matched || data.plate_read;
  const plateText = plate ? `xe biển số ${plate}` : 'xe không đọc được biển số';
  switch (data.violation_type) {
    case 'NO_HELMET':
      return `Cảnh báo: ${plateText} chưa đội mũ bảo hiểm`;
    case 'PLATE_NOT_REGISTERED':
      return `Cảnh báo: ${plateText} chưa đăng ký`;
    case 'PLATE_UNREADABLE':
      return 'Cảnh báo: không đọc được biển số xe';
    case 'RIDING_THROUGH_GATE':
      return `Cảnh báo: ${plateText} đang chạy xe qua cổng, vui lòng dắt xe`;
    case 'MULTIPLE':
      return `Cảnh báo: ${plateText} vi phạm nhiều lỗi`;
    default:
      return `Cảnh báo vi phạm: ${plateText}`;
  }
}

export default function AlertBanner({ token, onAlert, gate = 'main' }) {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const timeoutRef = useRef(null);
  const wsRef = useRef(null);
  const onAlertRef = useRef(onAlert);
  onAlertRef.current = onAlert;

  useEffect(() => {
    // Chrome nạp danh sách giọng đọc bất đồng bộ — gọi sớm 1 lần để giọng nữ
    // tiếng Việt kịp có mặt trước khi cảnh báo đầu tiên cần đọc.
    window.speechSynthesis?.getVoices();
  }, []);

  useEffect(() => {
    if (!token) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = API_BASE_URL.replace('http://', '').replace('https://', '');
    const wsUrl = `${wsProtocol}//${wsHost}/guard/ws?token=${token}&gate=${gate}`;

    // Phát chuỗi beep phân biệt theo loại vi phạm, trả về tổng thời lượng
    // (ms) để lên lịch TTS phát ngay sau khi beep kết thúc.
    function playAlertSound(key) {
      const sound = ALERT_SOUNDS[key] || ALERT_SOUNDS.default;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        for (let i = 0; i < sound.beeps; i++) {
          const startAt = ctx.currentTime + i * (sound.beepDuration + sound.gap);
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.value = sound.freq;
          gain.gain.value = 0.3;
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(startAt);
          osc.stop(startAt + sound.beepDuration);
        }
      } catch (e) {
        console.warn('[AlertBanner] Audio blocked:', e.message);
      }
      return Math.round((sound.beeps * (sound.beepDuration + sound.gap)) * 1000);
    }

    // Tên giọng nữ tiếng Việt phổ biến theo hệ điều hành/trình duyệt (Windows,
    // Google, Edge). Không có tên khớp nào → tự động rơi về giọng vi-VN đầu tiên
    // (tốt hơn để trình duyệt tự chọn, vì không phải giọng nào cũng khai tên).
    const FEMALE_VOICE_HINTS = ['hoaimy', 'nữ', 'female', 'linh', 'mai', 'huyền'];

    function pickVietnameseFemaleVoice() {
      const voices = window.speechSynthesis.getVoices();
      const viVoices = voices.filter((v) => v.lang?.toLowerCase().startsWith('vi'));
      const female = viVoices.find((v) =>
        FEMALE_VOICE_HINTS.some((hint) => v.name.toLowerCase().includes(hint))
      );
      return female || viVoices[0] || null;
    }

    function speak(text) {
      try {
        if (!window.speechSynthesis) return;
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'vi-VN';
        const voice = pickVietnameseFemaleVoice();
        if (voice) utterance.voice = voice;
        window.speechSynthesis.speak(utterance);
      } catch (e) {
        console.warn('[AlertBanner] TTS blocked:', e.message);
      }
    }

    function handleAlert(data) {
      setMessage('⚠️ CẢNH BÁO: ' + (data.violation_type || data.type));
      setSnapshotUrl(data.snapshot_url || null);
      setVisible(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setVisible(false), 3000);

      // Beep trước để bảo vệ chú ý ngay, TTS đọc nội dung ngay sau đó.
      const beepDurationMs = playAlertSound(data.violation_type || 'default');
      setTimeout(() => speak(buildSpeechText(data)), beepDurationMs + 50);

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
  }, [token, gate]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        backgroundColor: '#c92035',
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
