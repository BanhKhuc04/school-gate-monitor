// Đọc to tiếng Việt (Web Speech API), ưu tiên giọng LOCAL đã cài sẵn trên
// máy để chạy được khi WAN/Internet bị ngắt. Nếu không có, fallback các
// giọng vi-VN remote (có thể fail khi offline); cuối cùng vẫn trả về text
// để UI tự hiển thị + fallback sang clip audio local.
//
// Lưu ý: `localService` là tín hiệu cấu hình — không thay thế việc nghe
// thử khi WAN tắt. Khi build nghiệm thu cần cold-start trình duyệt rồi bật
// loa thật để xác nhận.

const FEMALE_VOICE_HINTS = ['hoaimy', 'nữ', 'female', 'linh', 'mai', 'huyền'];
let cachedVoice = null;

function pickVietnameseFemaleVoice() {
  if (!('speechSynthesis' in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  const viVoices = voices.filter((v) => v.lang?.toLowerCase().startsWith('vi'));
  if (!viVoices.length) return null;

  // 1) Ưu tiên LOCAL + female (chạy offline)
  const localFemale = viVoices.find((v) =>
    v.localService === true &&
    FEMALE_VOICE_HINTS.some((hint) => v.name.toLowerCase().includes(hint))
  );
  if (localFemale) return localFemale;

  // 2) Bất kỳ LOCAL vi-VN
  const local = viVoices.find((v) => v.localService === true);
  if (local) return local;

  // 3) Female remote (có thể không ổn định khi WAN tắt)
  const remoteFemale = viVoices.find((v) =>
    FEMALE_VOICE_HINTS.some((hint) => v.name.toLowerCase().includes(hint))
  );
  if (remoteFemale) return remoteFemale;

  // 4) Bất kỳ vi-VN
  return viVoices[0] || null;
}

export function getVietnameseVoiceStatus() {
  if (!('speechSynthesis' in window)) {
    return { supported: false, local: false, voice: null };
  }
  const voice = cachedVoice || pickVietnameseFemaleVoice();
  return {
    supported: true,
    local: !!(voice && voice.localService === true),
    voice: voice ? voice.name : null,
  };
}

export function speakVietnamese(text, options = {}) {
  try {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'vi-VN';
    if (!cachedVoice) cachedVoice = pickVietnameseFemaleVoice();
    if (cachedVoice) utterance.voice = cachedVoice;
    if (options.rate != null) utterance.rate = options.rate;
    if (options.pitch != null) utterance.pitch = options.pitch;
    if (options.volume != null) utterance.volume = options.volume;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn('[speak] TTS blocked:', e.message);
  }
}

export function stopSpeech() {
  try { window.speechSynthesis?.cancel(); } catch {}
}

export function warmUpVoices() {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.getVoices();
  if (!cachedVoice) cachedVoice = pickVietnameseFemaleVoice();
  window.speechSynthesis.onvoiceschanged = () => {
    if (!cachedVoice) cachedVoice = pickVietnameseFemaleVoice();
  };
}