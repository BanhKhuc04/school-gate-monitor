import { Link } from 'react-router-dom';
import PlateReviewPanel from '../components/PlateReviewPanel';

export default function AiReviewPage() {
  return (
    <section className="p-4 md:p-6 space-y-4" aria-label="Duyệt mẫu AI">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Duyệt mẫu</h1>
        <p className="text-sm text-on-surface-variant">Đọc ảnh gốc trước khi xác nhận. Mẫu thiếu bằng chứng được giữ ở trạng thái cần duyệt.</p>
      </header>
      <PlateReviewPanel role="admin" />
      <Link to="/settings/ai/datasets" className="text-sm text-primary underline">Mở bộ dữ liệu đã duyệt</Link>
    </section>
  );
}
