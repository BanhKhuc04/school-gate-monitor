import { Link } from 'react-router-dom';
import PlateReviewPanel from '../components/PlateReviewPanel';
import { useLang } from '../i18n/LanguageContext';

export default function AiReviewPage() {
  const { t } = useLang();
  return (
    <section className="p-4 md:p-6 space-y-4" aria-label={t('Duyệt mẫu AI', 'AI sample review')}>
      <header className="space-y-1">
        <h1 className="text-xl font-bold">{t('Duyệt mẫu', 'Review samples')}</h1>
        <p className="text-sm text-on-surface-variant">{t('Đọc ảnh gốc trước khi xác nhận. Mẫu thiếu bằng chứng được giữ ở trạng thái cần duyệt.', 'Check the original image before confirming. Samples without enough evidence stay pending review.')}</p>
      </header>
      <PlateReviewPanel role="admin" />
      <Link to="/settings/ai/datasets" className="text-sm text-primary underline">{t('Mở bộ dữ liệu đã duyệt', 'Open reviewed datasets')}</Link>
    </section>
  );
}
