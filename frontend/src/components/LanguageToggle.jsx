import { useLang, LANGS } from '../i18n/LanguageContext';

/** Nút gạt VI | EN — dùng ở thanh trạng thái trên cùng và trang đăng nhập. */
export default function LanguageToggle({ className = '' }) {
  const { lang, setLang, t } = useLang();
  return (
    <div
      role="group"
      aria-label={t('Ngôn ngữ', 'Language')}
      className={`inline-flex rounded-md border border-outline-variant overflow-hidden font-mono text-xs ${className}`}
    >
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          className={`px-2.5 py-1 font-bold uppercase transition-colors ${
            lang === code ? 'bg-primary text-on-primary' : 'bg-surface text-on-surface-variant hover:bg-surface-container'
          }`}
        >
          {code}
        </button>
      ))}
    </div>
  );
}
