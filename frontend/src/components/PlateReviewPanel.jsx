import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import client from '../api/client';

const VERDICT_LABELS = {
  correct: 'Đúng',
  incorrect: 'Sai — nhập lại biển',
  unreadable: 'Không đọc được',
  not_plate: 'Không phải biển',
  wrong_association: 'Ghép nhầm xe',
};

const STATUS_LABELS = {
  pending: 'Chờ duyệt',
  confirmed: 'Đã xác nhận',
  rejected: 'Đã sửa',
};

const STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-900',
  confirmed: 'bg-emerald-100 text-emerald-900',
  rejected: 'bg-slate-200 text-slate-900',
};

/**
 * PlateReviewPanel — FR7 thẻ ảnh duyệt biển.
 *
 * Hiển thị danh sách plate recognition reviews + ảnh crop gốc + đề xuất OCR.
 * User bấm "Đúng" / "Sai" / "Không đọc được" / "Không phải biển" / "Ghép nhầm xe"
 * và có thể nhập chuỗi sửa khi chọn Sai. Feedback lưu qua
 * POST /api/recognition/reviews/{id}/feedback với Idempotency-Key và expected_version.
 *
 * KHÔNG tự gán xe/học sinh — chỉ ghi feedback để tạo dataset.
 */
export default function PlateReviewPanel({gate, role}) {
  const canReview = role === 'admin' || role === 'security';
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [correction, setCorrection] = useState('');
  const idempotencyRef = useRef(crypto.randomUUID());

  const limit = 10;

  const fetchReviews = useCallback(async () => {
    setError('');
    try {
      const params = {gate_id: gate, limit, offset};
      if (statusFilter) params.status = statusFilter;
      const {data} = await client.get('/api/recognition/reviews', {params});
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.response?.data?.detail || 'Không tải được thẻ duyệt biển.');
    }
  }, [gate, statusFilter, offset]);

  useEffect(() => {
    setOffset(0);
    fetchReviews();
  }, [gate, statusFilter, fetchReviews]);

  const submitFeedback = async (review, verdict, correctedText = null) => {
    if (!canReview) {
      setError('Chỉ admin hoặc bảo vệ mới có quyền duyệt biển.');
      return;
    }
    setBusyId(review.review_id);
    setError('');
    const idempotencyKey = `${idempotencyRef.current}:${review.review_id}:${verdict}`;
    try {
      const payload = {verdict, expected_version: review.version};
      if (correctedText) payload.corrected_text = correctedText;
      const {data} = await client.post(
        `/api/recognition/reviews/${review.review_id}/feedback`,
        payload,
        {headers: {'Idempotency-Key': idempotencyKey}}
      );
      // Optimistic local update so the user sees confirmation without a refetch.
      setItems(prev => prev.map(it =>
        it.review_id === review.review_id
          ? {...it, status: data.status, version: data.expected_version}
          : it));
    } catch (err) {
      if (err.response?.status === 409) {
        setError('Đề xuất đã có người sửa — tải lại để cập nhật.');
        fetchReviews();
      } else {
        setError(err.response?.data?.detail || 'Không ghi được feedback.');
      }
    } finally {
      setBusyId(null);
      setEditingId(null);
      setCorrection('');
    }
  };

  const summary = useMemo(() => ({
    pending: items.filter(i => i.status === 'pending').length,
    confirmed: items.filter(i => i.status === 'confirmed').length,
    rejected: items.filter(i => i.status === 'rejected').length,
  }), [items]);

  return (
    <section aria-label="Duyệt biển số" className="flex flex-col gap-3 min-h-0">
      <p className="text-xs text-white/80">
        Thẻ ảnh biển cần người xác nhận. Bấm "Đúng" nếu OCR đọc đúng, "Sai" để sửa.
        Feedback không tự gán xe/học sinh — chỉ tạo dataset cho đợt train tiếp.
      </p>
      <div className="flex flex-wrap gap-2 text-xs">
        <label className="flex items-center gap-2">
          Trạng thái:
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="rounded bg-primary-container text-on-primary-container px-2 py-1"
            aria-label="Lọc trạng thái duyệt"
          >
            <option value="">Tất cả</option>
            <option value="pending">Chờ duyệt</option>
            <option value="confirmed">Đã xác nhận</option>
            <option value="rejected">Đã sửa</option>
          </select>
        </label>
        <span className="rounded bg-slate-100 text-slate-900 px-2 py-1">
          Tổng: {total} · hiện {items.length}
        </span>
        {summary.pending > 0 && <span className="rounded bg-amber-100 text-amber-900 px-2 py-1">Chờ: {summary.pending}</span>}
      </div>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}

      <div className="space-y-3 overflow-y-auto max-h-[70vh] pr-1" data-testid="plate-review-list">
        {!items.length && !error && (
          <p role="status" className="text-sm bg-primary-container text-on-primary-container rounded p-3">
            Không có đề xuất biển nào trong bộ lọc này.
          </p>
        )}
        {items.map(review => {
          const isEditing = editingId === review.review_id;
          const isBusy = busyId === review.review_id;
          return (
            <article
              key={review.review_id}
              data-testid="plate-review-card"
              className="rounded-xl bg-primary-container text-on-primary-container p-3 space-y-3 border border-white/15"
            >
              <header className="flex justify-between gap-2 items-start">
                <div className="space-y-0.5">
                  <p className="font-semibold">
                    Ảnh biển gốc · {review.gate_id}{review.camera_id && ` · ${review.camera_id}`}
                  </p>
                  <p className="text-[11px] opacity-70">
                    frame {review.frame_seq ?? '—'} · epoch {review.source_epoch} ·{' '}
                    {review.observed_at && new Date(review.observed_at).toLocaleString('vi-VN', {hour12: false})}
                  </p>
                </div>
                <span className={`text-xs rounded px-2 py-1 ${STATUS_COLORS[review.status] || STATUS_COLORS.pending}`}>
                  {STATUS_LABELS[review.status] || review.status}
                </span>
              </header>

              <div className="grid grid-cols-[1fr_1.5fr] gap-2">
                <figure className="rounded-lg bg-slate-950/10 overflow-hidden">
                  <figcaption className="px-2 py-1 text-[11px] font-semibold">Ảnh biển gốc</figcaption>
                  {review.crop_media_id ? (
                    <img
                      src={`/api/media/snapshots/${review.crop_media_id}`}
                      alt="Ảnh biển gốc"
                      className="w-full h-[140px] object-contain"
                    />
                  ) : (
                    <div className="h-[140px] flex items-center justify-center text-xs opacity-60">
                      Ảnh chưa lưu (nhận diệt lần đầu)
                    </div>
                  )}
                </figure>
                <div className="space-y-1 text-sm">
                  <p>
                    <span className="opacity-70 text-xs">Đọc thử:</span>{' '}
                    <span className="font-mono text-base tracking-wide">
                      {review.proposal_canonical || '—'}
                    </span>
                  </p>
                  <p className="text-xs opacity-70">
                    engine: {review.proposal_engine}
                    {review.proposal_model_hash && ` · sha256: ${review.proposal_model_hash.slice(0, 12)}…`}
                    {review.proposal_confidence != null && ` · conf ${review.proposal_confidence.toFixed(2)}`}
                  </p>
                  {review.proposal_top_line && (
                    <p className="text-xs">
                      Dòng trên: <span className="font-mono">{review.proposal_top_line}</span> · Dòng dưới: <span className="font-mono">{review.proposal_bottom_line || '—'}</span>
                    </p>
                  )}
                  {review.quality_score != null && (
                    <p className="text-xs opacity-70">
                      Chất lượng: {review.quality_score.toFixed(2)} · độ nét: {review.blur_score?.toFixed(1) ?? '—'} · tương phản: {review.contrast_score?.toFixed(1) ?? '—'}
                    </p>
                  )}
                </div>
              </div>

              {isEditing ? (
                <div className="space-y-2 border border-white/20 rounded p-2">
                  <label className="block text-xs">
                    Biển đúng (nhập lại):
                    <input
                      type="text"
                      value={correction}
                      onChange={e => setCorrection(e.target.value.toUpperCase())}
                      placeholder="VD: 89F1 237 92"
                      className="mt-1 w-full rounded bg-white text-slate-900 px-2 py-1 font-mono"
                      aria-label="Biển đúng"
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={!correction.trim() || isBusy}
                      onClick={() => submitFeedback(review, 'incorrect', correction.trim())}
                      className="rounded bg-amber-600 text-white px-3 py-1 text-sm disabled:opacity-50"
                    >
                      Lưu sửa
                    </button>
                    <button
                      type="button"
                      onClick={() => { setEditingId(null); setCorrection(''); }}
                      className="rounded border border-white/30 px-3 py-1 text-sm"
                    >
                      Huỷ
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2 text-sm" role="group" aria-label="Phản hồi duyệt biển">
                  {canReview ? (
                    <>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'correct')}
                        className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-correct"
                      >
                        Đúng
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => setEditingId(review.review_id)}
                        className="rounded bg-amber-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-incorrect"
                      >
                        Sai — nhập lại biển
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'unreadable')}
                        className="rounded bg-slate-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-unreadable"
                      >
                        Không đọc được
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'not_plate')}
                        className="rounded bg-slate-500 text-white px-3 py-1 disabled:opacity-50"
                      >
                        Không phải biển
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'wrong_association')}
                        className="rounded bg-rose-700 text-white px-3 py-1 disabled:opacity-50"
                      >
                        Ghép nhầm xe
                      </button>
                    </>
                  ) : (
                    <p className="text-xs opacity-70">Bạn không có quyền duyệt — chỉ admin và bảo vệ.</p>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <div className="flex items-center justify-between text-xs">
        <span>Trang {Math.floor(offset / limit) + 1} / {Math.max(1, Math.ceil(total / limit))}</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(o => Math.max(0, o - limit))}
            className="rounded border border-white/30 px-3 py-1 disabled:opacity-50"
          >
            ← Trước
          </button>
          <button
            type="button"
            disabled={offset + limit >= total}
            onClick={() => setOffset(o => o + limit)}
            className="rounded border border-white/30 px-3 py-1 disabled:opacity-50"
          >
            Sau →
          </button>
        </div>
      </div>
    </section>
  );
}
