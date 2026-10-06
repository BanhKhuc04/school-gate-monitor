// Đọc câu cảnh báo bằng các file mp3 thu sẵn (frontend/public/voice/vi, tạo bởi
// scripts/tools/build_voice_pack.py). Máy giám sát chạy trên router không có
// internet và Windows không có giọng vi-VN cài sẵn: giọng Việt của Chrome/Edge
// đọc qua mạng nên mất tiếng khi offline. Pure helper (node:test được).

export const VOICE_BASE = '/voice/vi/';

// Phải khớp chữ với buildAlertMessage (alertAudio.js) và PHRASES của script.
const PHRASES = [
  ['Không đội mũ, vui lòng dắt xe.', 'p_helmet_walk'],
  ['Vui lòng đội mũ.', 'p_helmet'],
  ['Vui lòng dắt xe.', 'p_walk'],
  ['Mời kiểm tra gương trái.', 'p_mirror'],
  ['Mời kiểm tra số người trên xe.', 'p_riders'],
  ['Mời kiểm tra đăng ký xe.', 'p_register'],
  ['Không đọc được biển số.', 'p_unreadable'],
];

// "05" -> không năm, "37" -> ba mươi bảy
function twoDigits(s) {
  return s.length === 2 && s[0] === '0' ? ['n0', `n${Number(s[1])}`] : [`n${Number(s)}`];
}

// "237" -> hai trăm ba mươi bảy, "205" -> hai trăm linh năm, "053" -> không năm mươi ba
export function numberClips(s) {
  if (!/^\d{1,3}$/.test(s)) return null;
  if (s.length < 3) return twoDigits(s);
  if (s[0] === '0') return ['n0', ...twoDigits(s.slice(1))];
  const rest = Number(s.slice(1));
  if (rest === 0) return [`h${s[0]}`];
  if (rest < 10) return [`h${s[0]}`, 'linh', `n${rest}`];
  return [`h${s[0]}`, `n${rest}`];
}

/** Clip keys for one alert sentence, or null when any part has no clip. */
export function clipsForMessage(text) {
  let rest = (text || '').trim();
  const keys = [];
  const plate = rest.match(/^(\d{2}) ([A-Z]\d?|[A-Z]{2}) (\d{1,3}) (\d{2})\.\s*/);
  if (plate) {
    const [, province, series, head, tail] = plate;
    keys.push(...twoDigits(province));
    for (const ch of series) keys.push(/\d/.test(ch) ? `n${ch}` : `l_${ch}`);
    keys.push(...numberClips(head), ...twoDigits(tail));
    rest = rest.slice(plate[0].length);
  }
  while (rest) {
    const hit = PHRASES.find(([phrase]) => rest.startsWith(phrase));
    if (!hit) return null;
    keys.push(hit[1]);
    rest = rest.slice(hit[0].length).trimStart();
  }
  return keys.length ? keys : null;
}

/** Play clips back to back; resolves false if any clip fails to load/play. */
export function playClips(keys, {rate = 1, volume = 1, makeAudio = src => new Audio(src)} = {}) {
  const queue = keys.map(k => {
    const audio = makeAudio(`${VOICE_BASE}${k}.mp3`);
    audio.preload = 'auto';
    audio.playbackRate = rate;
    audio.volume = volume;
    return audio;
  });
  let current = null;
  const done = new Promise(resolve => {
    const next = i => {
      if (i >= queue.length) { resolve(true); return; }
      current = queue[i];
      current.onended = () => next(i + 1);
      current.onerror = () => resolve(false);
      Promise.resolve(current.play()).catch(() => resolve(false));
    };
    next(0);
  });
  done.stop = () => { try { current?.pause(); } catch { /* already stopped */ } queue.length = 0; };
  return done;
}
