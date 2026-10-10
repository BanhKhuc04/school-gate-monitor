// Đọc to cảnh báo (Web Speech API) theo ngôn ngữ giao diện — tiếng Việt thì tự
// tìm giọng nữ nếu máy có. Dùng chung cho AlertBanner (cảnh báo tự động) và các
// nơi khác cần đọc to (chi tiết vi phạm).

// Tên giọng nữ tiếng Việt phổ biện theo hệ điều hành/trình duyệt (Windows,
// Google, Edge). Không có tên khớp nào → rơi về giọng vi-VN đầu tiên trình
// duyệt có (không phải giọng nào cũng khai giới tính trong tên).
const FEMALE_VOICE_HINTS = ['hoaimy', 'nữ', 'female', 'linh', 'mai', 'huyền'];

// Máy thường có NHIỀU giọng vi-VN cài sẵn (Windows + Edge/Chrome mỗi cái 1
// giọng riêng) — nếu chọn lại giọng ở MỖI lần đọc, có lúc getVoices() trả về
// thứ tự khác nhau (danh sách nạp bất đồng bộ) → 2 lần cảnh báo liên tiếp có
// thể đọc bằng 2 giọng khác nhau, nghe như 2 người. Chốt 1 giọng ngay khi có
// đủ danh sách rồi DÙNG LẠI mãi cho tới khi tải lại trang.
// Chốt riêng cho từng ngôn ngữ ('vi' / 'en').
const cachedVoices = {};

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang?.toLowerCase().startsWith(lang));
  if (lang !== 'vi') return voices[0] || null;
  const female = voices.find((v) =>
    FEMALE_VOICE_HINTS.some((hint) => v.name.toLowerCase().includes(hint))
  );
  return female || voices[0] || null;
}

function cachedVoice(lang) {
  if (!cachedVoices[lang]) cachedVoices[lang] = pickVoice(lang);
  return cachedVoices[lang];
}

export function speak(text, lang = 'vi', options = {}) {
  try {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'en' ? 'en-US' : 'vi-VN';
    const voice = cachedVoice(lang);
    if (voice) utterance.voice = voice;
    // Feature 3: priority-based rate/pitch — high = faster/higher pitch
    if (options.rate != null) utterance.rate = options.rate;
    if (options.pitch != null) utterance.pitch = options.pitch;
    if (options.volume != null) utterance.volume = options.volume;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn('[speak] TTS blocked:', e.message);
  }
}

// Chrome nạp danh sách giọng đọc bất đồng bộ — gọi 1 lần sớm (ví dụ lúc app
// khởi động) để chốt sẵn 1 giọng trước khi cần đọc, và lắng nghe
// 'voiceschanged' cho trường hợp danh sách nạp xong sau đó.
export function warmUpVoices() {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.getVoices();
  cachedVoice('vi');
  cachedVoice('en');
  window.speechSynthesis.onvoiceschanged = () => {
    cachedVoice('vi');
    cachedVoice('en');
  };
}

// Giữ tên cũ cho các nơi gọi chưa chuyển sang speak(text, lang).
export function speakVietnamese(text, options = {}) {
  speak(text, 'vi', options);
}
