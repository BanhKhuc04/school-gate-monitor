import { useCallback, useEffect, useState } from 'react';
import {
  getActiveCandidate, listCandidates, promoteCandidate, rollbackCandidate,
} from '../training/api';

/** Trang Candidate Compare — Task 3.6.
 *  Liệt kê candidate + active + rollback. So sánh dựa trên metrics lưu cùng job.
 *  Promote có guard: nếu candidate kém hơn active hiện tại theo
 *  evaluator.compare_candidates → 400.
 */
export default function CandidateComparePage() {
  const [engine, setEngine] = useState('plate_ocr');
  const [candidates, setCandidates] = useState([]);
  const [active, setActive] = useState(null);
  const [error, setError] = useState('');
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
      setError(e.response?.data?.detail || 'Không tải được danh sách candidate.');
    }
  }, [engine]);

  useEffect(() => { refresh(); }, [refresh]);

  const onPromote = async (id) => {
    if (!window.confirm(`Promote candidate ${id.slice(-12)}? Không rollback tự động nếu kém hơn baseline.`)) return;
    setBusy(true);
    try {
      await promoteCandidate(id, null);
      setError(`Đã promote ${id.slice(-12)}`);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Promote thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onRollback = async () => {
    if (!window.confirm('Rollback — retire candidate active hiện tại?')) return;
    setBusy(true);
    try {
      const result = await rollbackCandidate(engine);
      setError(`Rollback: rolled_back=${result.rolled_back}`);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Rollback thất bại.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="So sánh candidate" className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">So sánh & Khuyến nghị candidate (Task 3.6)</h1>
        <p className="text-xs opacity-70">
          Promotion chỉ khi candidate vượt baseline. Rollback retire candidate active hiện tại.
          KHÔNG sửa prediction/evidence lịch sử.
        </p>
      </header>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}

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
          Quay lại baseline
        </button>
      </div>

      <div className="text-xs space-y-1">
        <p>Active hiện tại:
          {active ? (
            <span className="font-mono ml-2" data-testid="active-candidate">
              {active.id.slice(-12)} · {active.model_class} · promoted_at {active.promoted_at}
            </span>
          ) : (
            <span className="opacity-70 ml-2">Chưa có candidate active.</span>
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
            <th className="text-left py-1">Hành động</th>
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
              <td className="py-1 space-x-1">
                {c.state === 'candidate' && (
                  <button type="button" disabled={busy} onClick={() => onPromote(c.id)}
                    className="rounded bg-emerald-600 text-white px-2 py-0.5"
                    data-testid={`promote-${c.id.slice(-12)}`}>
                    Áp dụng
                  </button>
                )}
                {c.state === 'active' && (
                  <span className="text-xs rounded bg-emerald-100 text-emerald-900 px-2 py-0.5">
                    đang chạy
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
            <tr><td colSpan={6} className="py-2 text-center opacity-70">
              Chưa có candidate nào cho engine này.
            </td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}