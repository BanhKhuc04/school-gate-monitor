import { Link } from 'react-router-dom';

const steps = [
  { title: 'Duyệt mẫu', to: '/settings/ai/reviews', action: 'Mở mẫu cần duyệt', detail: 'Xác nhận chữ và ghép đúng xe từ ảnh nguồn. Mẫu đã duyệt được đưa vào bộ dữ liệu.' },
  { title: 'Xuất Kaggle', to: '/settings/ai/export', action: 'Chọn bộ dữ liệu', detail: 'Xuất ảnh, nhãn và manifest đã kiểm tra. Huấn luyện nặng thực hiện trên Kaggle.' },
  { title: 'Nhập và đánh giá model', to: '/settings/ai/jobs', action: 'Mở đánh giá baseline', detail: 'Đánh giá baseline hiện có trên bộ dữ liệu đóng băng. Nhập weights từ Kaggle đang được bổ sung.', pending: true },
  { title: 'Áp dụng / rollback', to: '/settings/ai/models', action: 'Xem model và kết quả', detail: 'Kiểm tra artifact, metrics và điều kiện áp dụng. Trạng thái registry cần được runtime xác nhận.' },
];

export default function AdvancedAiPage() {
  return (
    <section className="p-4 md:p-6 space-y-5" aria-label="AI nâng cao">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">AI nâng cao</h1>
        <p className="text-sm text-on-surface-variant">Cải thiện model theo từng đợt từ mẫu đã được người duyệt.</p>
      </header>
      <ol className="divide-y divide-outline-variant rounded border border-outline-variant bg-surface">
        {steps.map((step, i) => <li key={step.title} className="flex flex-col sm:flex-row sm:items-center gap-3 p-4">
          <span aria-hidden="true" className="font-mono font-bold text-primary">0{i + 1}</span>
          <div className="flex-1 space-y-1">
            <h2 className="font-semibold">{step.title}</h2>
            <p className="text-sm text-on-surface-variant">{step.detail}</p>
            {step.pending && <p className="text-xs text-error">Nhập model: chưa khả dụng</p>}
          </div>
          <Link to={step.to} className="shrink-0 rounded border border-primary px-3 py-2 text-sm text-primary hover:bg-primary-container focus-visible:outline-2 focus-visible:outline-primary">{step.action}</Link>
        </li>)}
      </ol>
      <Link to="/settings/ai/datasets" className="inline-block text-sm text-primary underline">Quản lý dữ liệu và sửa bbox trên mẫu đã chọn</Link>
    </section>
  );
}
