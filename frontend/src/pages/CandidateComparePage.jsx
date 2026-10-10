import { useCallback, useEffect, useState } from 'react';
import {
  getActiveCandidate, listCandidates, promoteCandidate, rollbackCandidate,
} from '../training/api';
import { useLang } from '../i18n/LanguageContext';

/** Trang Candidate Compare — Task 3.6.
 *  Liệt kê candidate + active + rollback. So sánh dựa trên metrics lưu cùng job.
 *  Promote có guard: nếu candidate kém hơn active hiện tại theo
 *  evaluator.compare_candidates → 400.
 */
export default function CandidateComparePage() {
  const { t } = useLang();
  const [engine, setEngine] = useState('plate_ocr');
  const [candidates, setCandidates] = useState([]);
  const [active, setActive] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setError('');
    try {
      const [c, a] = await Promise.all([
        listCandidates(engine),
        getActiveCandidate(engine),
      ]);
      setCandidates(c);
      setActive(a);
    } catch (e) {
      setError(e.response?.data?.detail || t('Không tải được danh sách candidate.', 'Could not load the candidate list.'));
    }
  }, [engine, t]);

  useEffect(() => { refresh(); }, [refresh]);

  const onPromote = async (id) => {
    if (!window.confirm(t(`Áp dụng model ${id.slice(-12)} sau khi kiểm tra metrics và artifact? Runtime cần xác nhận đã tải model.`, `Apply model ${id.slice(-12)} after checking metrics and artifact? The runtime must confirm the model is loaded.`))) return;
    setBusy(true);
    try {
      const result = await promoteCandidate(id, null);
      await refresh();
      setNotice(result.runtime_applied === true ? t('Runtime đã xác nhận áp dụng model.', 'Runtime confirmed the model is applied.') : t('Đã gửi yêu cầu áp dụng. Chờ runtime xác nhận model đã tải.', 'Apply request sent. Waiting for the runtime to confirm the model is loaded.'));
    } catch (e) {
      setError(e.response?.data?.detail || t('Promote thất bại.', 'Promote failed.'));
    } finally {
      setBusy(false);
    }
  };

  const onRollback = async () => {
    if (!window.confirm(t('Yêu cầu quay lại model trước đó? Runtime cần xác nhận đã khôi phục.', 'Request a rollback to the previous model? The runtime must confirm the restore.'))) return;
    setBusy(true);
    try {
      const result = await rollbackCandidate(engine);
      await refresh();
      setNotice(result.runtime_applied === true ? t('Runtime đã xác nhận rollback.', 'Runtime confirmed the rollback.') : t(`Đã gửi yêu cầu rollback (${result.rolled_back ? 'registry cập nhật' : 'registry chưa đổi'}). Kiểm tra xác nhận runtime.`, `Rollback request sent (${result.rolled_back ? 'registry updated' : 'registry unchanged'}). Check the runtime confirmation.`));
    } catch (e) {
      setError(e.response?.data?.detail || t('Rollback thất bại.', 'Rollback failed.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label={t('So sánh candidate', 'Candidate comparison')} className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">{t('Model, đánh giá & Rollback', 'Models, evaluation & Rollback')}</h1>
        <p className="text-xs opacity-70">
          {t('Kiểm tra metrics, hash và artifact trước khi áp dụng. Model active trong registry chỉ được coi là đang chạy khi runtime xác nhận đã tải.', 'Check metrics, hash and artifact before applying. The active model in the registry only counts as running once the runtime confirms it is loaded.')}
        </p>
      </header>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}

      <div className="flex items-center gap-2 text-sm">
        <label className="flex items-center gap-2">
          Engine:
          <select value={engine} onChange={e => setEngine(e.target.value)}
            className="rounded bg-primary-container text-on-primary-container px-2 py-1">
            <option value="plate_ocr">Plate OCR</option>
            <option value="plate_detector">Plate Detector</option>
            <option value="helmet">Helmet</option>
          </select>
        </label>
        <button type="button" disabled={busy} onClick={refresh}
          className="rounded border px-2 py-1">Refresh</button>
        <button type="button" disabled={busy || !active} onClick={onRollback}
          className="rounded bg-rose-700 text-white px-3 py-1 disabled:opacity-50"
          data-testid="rollback-button">
          {t('Quay lại baseline', 'Roll back to baseline')}
        </button>
      </div>

      <div className="text-xs space-y-1">
        <p>{t('Model active trong registry:', 'Active model in registry:')}
          {active ? (
            <span className="font-mono ml-2" data-testid="active-candidate">
              {active.id.slice(-12)} · {active.model_class} · promoted_at {active.promoted_at}
            </span>
          ) : (
            <span className="opacity-70 ml-2">{t('Chưa có candidate active.', 'No active candidate yet.')}</span>
          )}
        </p>
      </div>

      <table className="w-full text-xs" data-testid="candidates-table">
        <thead>
          <tr className="border-b">
            <th className="text-left py-1">ID</th>
            <th className="text-left py-1">Engine</th>
            <th className="text-left py-1">State</th>
            <th className="text-left py-1">Model class</th>
            <th className="text-left py-1">Created</th>
            <th className="text-left py-1">{t('Kết quả / Artifact', 'Results / Artifact')}</th>
            <th className="text-left py-1">{t('Hành động', 'Actions')}</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map(c => (
            <tr key={c.id} className="border-b">
              <td className="py-1 font-mono">{c.id.slice(-12)}</td>
              <td className="py-1">{c.engine}</td>
              <td className="py-1">{c.state}</td>
              <td className="py-1">{c.model_class}</td>
              <td className="py-1">{c.created_at}</td>
              <td className="py-1"><details><summary className="cursor-pointer text-primary">{t('Xem thông tin', 'View details')}</summary>
                <pre className="max-w-sm overflow-auto whitespace-pre-wrap break-all p-2">{JSON.stringify({ metrics: c.metrics || c.metrics_path || null, model_sha256: c.model_sha256 || null, model_path: c.model_path || null }, null, 2)}</pre>
              </details></td>
              <td className="py-1 space-x-1">
                {c.state === 'candidate' && (
                  <button type="button" disabled={busy} onClick={() => onPromote(c.id)}
                    className="rounded bg-emerald-600 text-white px-2 py-0.5"
                    data-testid={`promote-${c.id.slice(-12)}`}>
                    {t('Áp dụng', 'Apply')}
                  </button>
                )}
                {c.state === 'active' && (
                  <span className="text-xs rounded bg-emerald-100 text-emerald-900 px-2 py-0.5">
                    {c.runtime_applied === true ? t('Runtime đã xác nhận', 'Runtime confirmed') : t('Registry active · chờ xác nhận runtime', 'Registry active · awaiting runtime confirmation')}
                  </span>
                )}
                {c.state === 'retired' && (
                  <span className="text-xs rounded bg-slate-200 text-slate-900 px-2 py-0.5">
                    retired
                  </span>
                )}
              </td>
            </tr>
          ))}
          {!candidates.length && (
            <tr><td colSpan={7} className="py-2 text-center opacity-70">
              {t('Chưa có candidate nào cho engine này.', 'No candidates for this engine yet.')}
            </td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
