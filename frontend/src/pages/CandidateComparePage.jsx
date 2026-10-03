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
      setError(e.response?.data?.detail || 'Không tải được danh sách candidate.');
    }
  }, [engine]);

  useEffect(() => { refresh(); }, [refresh]);

  const onPromote = async (id) => {
    if (!window.confirm(`Áp dụng model ${id.slice(-12)} sau khi kiểm tra metrics và artifact? Runtime cần xác nhận đã tải model.`)) return;
    setBusy(true);
    try {
      const result = await promoteCandidate(id, null);
      await refresh();
      setNotice(result.runtime_applied === true ? 'Runtime đã xác nhận áp dụng model.' : 'Đã gửi yêu cầu áp dụng. Chờ runtime xác nhận model đã tải.');
    } catch (e) {
      setError(e.response?.data?.detail || 'Promote thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onRollback = async () => {
    if (!window.confirm('Yêu cầu quay lại model trước đó? Runtime cần xác nhận đã khôi phục.')) return;
    setBusy(true);
    try {
      const result = await rollbackCandidate(engine);
      await refresh();
      setNotice(result.runtime_applied === true ? 'Runtime đã xác nhận rollback.' : `Đã gửi yêu cầu rollback (${result.rolled_back ? 'registry cập nhật' : 'registry chưa đổi'}). Kiểm tra xác nhận runtime.`);
    } catch (e) {
      setError(e.response?.data?.detail || 'Rollback thất bại.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="So sánh candidate" className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Model, đánh giá & Rollback</h1>
        <p className="text-xs opacity-70">
          Kiểm tra metrics, hash và artifact trước khi áp dụng. Model active trong registry
          chỉ được coi là đang chạy khi runtime xác nhận đã tải.
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
          Quay lại baseline
        </button>
      </div>

      <div className="text-xs space-y-1">
        <p>Model active trong registry:
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
            <th className="text-left py-1">Kết quả / Artifact</th>
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
              <td className="py-1"><details><summary className="cursor-pointer text-primary">Xem thông tin</summary>
                <pre className="max-w-sm overflow-auto whitespace-pre-wrap break-all p-2">{JSON.stringify({ metrics: c.metrics || c.metrics_path || null, model_sha256: c.model_sha256 || null, model_path: c.model_path || null }, null, 2)}</pre>
              </details></td>
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
                    {c.runtime_applied === true ? 'Runtime đã xác nhận' : 'Registry active · chờ xác nhận runtime'}
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
              Chưa có candidate nào cho engine này.
            </td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
