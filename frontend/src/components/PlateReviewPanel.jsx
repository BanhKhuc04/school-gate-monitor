import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import client from '../api/client';
import { useLang, localeOf } from '../i18n/LanguageContext';

const VERDICT_LABELS = (t) => ({
  correct: t('Đúng', 'Correct'),
  incorrect: t('Sai — nhập lại biển', 'Wrong — re-enter plate'),
  unreadable: t('Không đọc được', 'Unreadable'),
  not_plate: t('Không phải biển', 'Not a plate'),
  wrong_association: t('Ghép nhầm xe', 'Wrong bike match'),
});

const STATUS_LABELS = (t) => ({
  pending: t('Chờ duyệt', 'Pending'),
  confirmed: t('Đã xác nhận', 'Confirmed'),
  rejected: t('Đã sửa', 'Corrected'),
});

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
  const { lang, t } = useLang();
  const tRef = useRef(t);
  useEffect(() => { tRef.current = t; });
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
      setError(err.response?.data?.detail || tRef.current('Không tải được thẻ duyệt biển.', 'Could not load plate review cards.'));
    }
  }, [gate, statusFilter, offset]);

  useEffect(() => {
    setOffset(0);
    fetchReviews();
  }, [gate, statusFilter, fetchReviews]);

  const submitFeedback = async (review, verdict, correctedText = null) => {
    if (!canReview) {
      setError(t('Chỉ admin hoặc bảo vệ mới có quyền duyệt biển.', 'Only admins or guards can review plates.'));
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
        setError(t('Đề xuất đã có người sửa — tải lại để cập nhật.', 'Someone already changed this proposal — reloading.'));
        fetchReviews();
      } else {
        setError(err.response?.data?.detail || t('Không ghi được feedback.', 'Could not save feedback.'));
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
    <section aria-label={t('Duyệt biển số', 'Plate review')} className="flex flex-col gap-3 min-h-0">
      <p className="text-xs text-white/80">
        {t('Thẻ ảnh biển cần người xác nhận. Bấm "Đúng" nếu OCR đọc đúng, "Sai" để sửa. Feedback không tự gán xe/học sinh — chỉ tạo dataset cho đợt train tiếp.', 'Plate images that need human confirmation. Click "Correct" if OCR read it right, "Wrong" to fix it. Feedback never assigns a bike/student — it only builds the dataset for the next training round.')}
      </p>
      <div className="flex flex-wrap gap-2 text-xs">
        <label className="flex items-center gap-2">
          {t('Trạng thái:', 'Status:')}
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="rounded bg-primary-container text-on-primary-container px-2 py-1"
            aria-label={t('Lọc trạng thái duyệt', 'Filter review status')}
          >
            <option value="">{t('Tất cả', 'All')}</option>
            <option value="pending">{t('Chờ duyệt', 'Pending')}</option>
            <option value="confirmed">{t('Đã xác nhận', 'Confirmed')}</option>
            <option value="rejected">{t('Đã sửa', 'Corrected')}</option>
          </select>
        </label>
        <span className="rounded bg-slate-100 text-slate-900 px-2 py-1">
          {t('Tổng:', 'Total:')} {total} · {t('hiện', 'showing')} {items.length}
        </span>
        {summary.pending > 0 && <span className="rounded bg-amber-100 text-amber-900 px-2 py-1">{t('Chờ:', 'Pending:')} {summary.pending}</span>}
      </div>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}

      <div className="space-y-3 overflow-y-auto max-h-[70vh] pr-1" data-testid="plate-review-list">
        {!items.length && !error && (
          <p role="status" className="text-sm bg-primary-container text-on-primary-container rounded p-3">
            {t('Không có đề xuất biển nào trong bộ lọc này.', 'No plate proposals match this filter.')}
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
                    {t('Ảnh biển gốc', 'Original plate image')} · {review.gate_id}{review.camera_id && ` · ${review.camera_id}`}
                  </p>
                  <p className="text-[11px] opacity-70">
                    frame {review.frame_seq ?? '—'} · epoch {review.source_epoch} ·{' '}
                    {review.observed_at && new Date(review.observed_at).toLocaleString(localeOf(lang), {hour12: false})}
                  </p>
                </div>
                <span className={`text-xs rounded px-2 py-1 ${STATUS_COLORS[review.status] || STATUS_COLORS.pending}`}>
                  {STATUS_LABELS(t)[review.status] || review.status}
                </span>
              </header>

              <div className="grid grid-cols-[1fr_1.5fr] gap-2">
                <figure className="rounded-lg bg-slate-950/10 overflow-hidden">
                  <figcaption className="px-2 py-1 text-[11px] font-semibold">{t('Ảnh biển gốc', 'Original plate image')}</figcaption>
                  {review.crop_media_id ? (
                    <img
                      src={`/api/media/snapshots/${review.crop_media_id}`}
                      alt={t('Ảnh biển gốc', 'Original plate image')}
                      className="w-full h-[140px] object-contain"
                    />
                  ) : (
                    <div className="h-[140px] flex items-center justify-center text-xs opacity-60">
                      {t('Ảnh chưa lưu (nhận diệt lần đầu)', 'Image not saved (first detection)')}
                    </div>
                  )}
                </figure>
                <div className="space-y-1 text-sm">
                  <p>
                    <span className="opacity-70 text-xs">{t('Đọc thử:', 'OCR read:')}</span>{' '}
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
                      {t('Dòng trên:', 'Top line:')} <span className="font-mono">{review.proposal_top_line}</span> · {t('Dòng dưới:', 'Bottom line:')} <span className="font-mono">{review.proposal_bottom_line || '—'}</span>
                    </p>
                  )}
                  {review.quality_score != null && (
                    <p className="text-xs opacity-70">
                      {t('Chất lượng:', 'Quality:')} {review.quality_score.toFixed(2)} · {t('độ nét:', 'sharpness:')} {review.blur_score?.toFixed(1) ?? '—'} · {t('tương phản:', 'contrast:')} {review.contrast_score?.toFixed(1) ?? '—'}
                    </p>
                  )}
                </div>
              </div>

              {isEditing ? (
                <div className="space-y-2 border border-white/20 rounded p-2">
                  <label className="block text-xs">
                    {t('Biển đúng (nhập lại):', 'Correct plate (re-enter):')}
                    <input
                      type="text"
                      value={correction}
                      onChange={e => setCorrection(e.target.value.toUpperCase())}
                      placeholder={t('VD: 89F1 237 92', 'e.g. 89F1 237 92')}
                      className="mt-1 w-full rounded bg-white text-slate-900 px-2 py-1 font-mono"
                      aria-label={t('Biển đúng', 'Correct plate')}
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={!correction.trim() || isBusy}
                      onClick={() => submitFeedback(review, 'incorrect', correction.trim())}
                      className="rounded bg-amber-600 text-white px-3 py-1 text-sm disabled:opacity-50"
                    >
                      {t('Lưu sửa', 'Save fix')}
                    </button>
                    <button
                      type="button"
                      onClick={() => { setEditingId(null); setCorrection(''); }}
                      className="rounded border border-white/30 px-3 py-1 text-sm"
                    >
                      {t('Huỷ', 'Cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2 text-sm" role="group" aria-label={t('Phản hồi duyệt biển', 'Plate review feedback')}>
                  {canReview ? (
                    <>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'correct')}
                        className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-correct"
                      >
                        {VERDICT_LABELS(t).correct}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => setEditingId(review.review_id)}
                        className="rounded bg-amber-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-incorrect"
                      >
                        {VERDICT_LABELS(t).incorrect}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'unreadable')}
                        className="rounded bg-slate-600 text-white px-3 py-1 disabled:opacity-50"
                        data-testid="feedback-unreadable"
                      >
                        {VERDICT_LABELS(t).unreadable}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'not_plate')}
                        className="rounded bg-slate-500 text-white px-3 py-1 disabled:opacity-50"
                      >
                        {VERDICT_LABELS(t).not_plate}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => submitFeedback(review, 'wrong_association')}
                        className="rounded bg-rose-700 text-white px-3 py-1 disabled:opacity-50"
                      >
                        {VERDICT_LABELS(t).wrong_association}
                      </button>
                    </>
                  ) : (
                    <p className="text-xs opacity-70">{t('Bạn không có quyền duyệt — chỉ admin và bảo vệ.', 'You cannot review — admins and guards only.')}</p>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <div className="flex items-center justify-between text-xs">
        <span>{t('Trang', 'Page')} {Math.floor(offset / limit) + 1} / {Math.max(1, Math.ceil(total / limit))}</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(o => Math.max(0, o - limit))}
            className="rounded border border-white/30 px-3 py-1 disabled:opacity-50"
          >
            ← {t('Trước', 'Previous')}
          </button>
          <button
            type="button"
            disabled={offset + limit >= total}
            onClick={() => setOffset(o => o + limit)}
            className="rounded border border-white/30 px-3 py-1 disabled:opacity-50"
          >
            {t('Sau', 'Next')} →
          </button>
        </div>
      </div>
    </section>
  );
}
