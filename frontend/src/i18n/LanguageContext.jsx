import { createContext, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Song ngữ Việt / English cho toàn bộ giao diện.
 *
 * ponytail: không dùng thư viện i18n + file key riêng — mỗi chuỗi viết thẳng
 * cặp `t('Tiếng Việt', 'English')` ngay tại chỗ dùng, đọc code thấy luôn cả 2
 * bản, không bao giờ lệch key. Chỉ 2 ngôn ngữ nên không cần gì hơn.
 *
 * Ngôn ngữ chọn theo thứ tự: `?lang=en|vi` trên URL (tiện quay video demo) →
 * lựa chọn lần trước (localStorage) → mặc định tiếng Việt.
 */
export const LANGS = ['vi', 'en'];

function initialLang() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('lang');
    if (LANGS.includes(fromUrl)) return fromUrl;
    const stored = localStorage.getItem('lang');
    if (LANGS.includes(stored)) return stored;
  } catch {
    // localStorage bị chặn (private mode) — dùng mặc định
  }
  return 'vi';
}

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
    try {
      localStorage.setItem('lang', lang);
    } catch {
      // bỏ qua — chỉ là ghi nhớ lựa chọn
    }
  }, [lang]);

  // Memo để `t` chỉ đổi khi đổi ngôn ngữ — trang nào đưa `t` vào deps của
  // useEffect/useCallback chỉ tải lại đúng 1 lần lúc bấm VI/EN.
  const value = useMemo(() => ({ lang, setLang, t: (vi, en) => (lang === 'en' ? en : vi) }), [lang]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLang must be used inside LanguageProvider');
  return ctx;
}

/** Locale cho toLocaleString/Intl theo ngôn ngữ đang chọn. */
export function localeOf(lang) {
  return lang === 'en' ? 'en-GB' : 'vi-VN';
}
