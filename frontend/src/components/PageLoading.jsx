import { useLang } from '../i18n/LanguageContext';

/** Suspense fallback while a lazy page loads. */
export default function PageLoading() {
  const { t } = useLang();
  return <p role="status" className="p-6 text-sm">{t('Đang tải trang…', 'Loading page…')}</p>;
}
