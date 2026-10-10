import { Link } from 'react-router-dom';
import { useLang } from '../i18n/LanguageContext';

const steps = (t) => [
  { title: t('Duyệt mẫu', 'Review samples'), to: '/settings/ai/reviews', action: t('Mở mẫu cần duyệt', 'Open samples to review'), detail: t('Xác nhận chữ và ghép đúng xe từ ảnh nguồn. Mẫu đã duyệt được đưa vào bộ dữ liệu.', 'Confirm the text and match the right bike from the source image. Approved samples go into the dataset.') },
  { title: t('Xuất Kaggle', 'Kaggle export'), to: '/settings/ai/export', action: t('Chọn bộ dữ liệu', 'Choose dataset'), detail: t('Xuất ảnh, nhãn và manifest đã kiểm tra. Huấn luyện nặng thực hiện trên Kaggle.', 'Export checked images, labels and manifest. Heavy training runs on Kaggle.') },
  { title: t('Nhập và đánh giá model', 'Import and evaluate model'), to: '/settings/ai/jobs', action: t('Mở đánh giá baseline', 'Open baseline evaluation'), detail: t('Đánh giá baseline hiện có trên bộ dữ liệu đóng băng. Nhập weights từ Kaggle đang được bổ sung.', 'Evaluate the current baseline on a frozen dataset. Importing weights from Kaggle is coming soon.'), pending: true },
  { title: t('Áp dụng / rollback', 'Apply / rollback'), to: '/settings/ai/models', action: t('Xem model và kết quả', 'View models and results'), detail: t('Kiểm tra artifact, metrics và điều kiện áp dụng. Trạng thái registry cần được runtime xác nhận.', 'Check artifacts, metrics and apply conditions. Registry status must be confirmed by the runtime.') },
];

export default function AdvancedAiPage() {
  const { t } = useLang();
  return (
    <section className="p-4 md:p-6 space-y-5" aria-label={t('AI nâng cao', 'Advanced AI')}>
      <header className="space-y-1">
        <h1 className="text-xl font-bold">{t('AI nâng cao', 'Advanced AI')}</h1>
        <p className="text-sm text-on-surface-variant">{t('Cải thiện model theo từng đợt từ mẫu đã được người duyệt.', 'Improve the model in rounds from human-reviewed samples.')}</p>
      </header>
      <ol className="divide-y divide-outline-variant rounded border border-outline-variant bg-surface">
        {steps(t).map((step, i) => <li key={step.to} className="flex flex-col sm:flex-row sm:items-center gap-3 p-4">
          <span aria-hidden="true" className="font-mono font-bold text-primary">0{i + 1}</span>
          <div className="flex-1 space-y-1">
            <h2 className="font-semibold">{step.title}</h2>
            <p className="text-sm text-on-surface-variant">{step.detail}</p>
            {step.pending && <p className="text-xs text-error">{t('Nhập model: chưa khả dụng', 'Model import: not available yet')}</p>}
          </div>
          <Link to={step.to} className="shrink-0 rounded border border-primary px-3 py-2 text-sm text-primary hover:bg-primary-container focus-visible:outline-2 focus-visible:outline-primary">{step.action}</Link>
        </li>)}
      </ol>
      <Link to="/settings/ai/datasets" className="inline-block text-sm text-primary underline">{t('Quản lý dữ liệu và sửa bbox trên mẫu đã chọn', 'Manage data and edit bboxes on selected samples')}</Link>
    </section>
  );
}
