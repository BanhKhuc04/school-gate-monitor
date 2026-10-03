import { useCallback, useEffect, useState } from 'react';
import { cancelJob, createJob, listDatasets, listJobs } from '../training/api';

/** Trang Training Jobs — queue + state + cancel.
 *  Hiển thị metadata của job (engine, state, dataset_id, created_at, finished_at).
 *  KHÔNG đụng vào weight runtime (chỉ model candidate ở dataset Repo).
 */
export default function TrainingJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ dataset_id: '', target: 'plate_ocr' });

  const refresh = useCallback(async () => {
    setError('');
    try {
      const items = await listJobs();
      setJobs(items);
    } catch (e) {
      setError(e.response?.data?.detail || 'Không tải được danh sách job.');
    }
  }, []);

  const refreshDatasets = useCallback(async () => {
    try {
      const items = await listDatasets();
      setDatasets(items.filter(d => d.freeze_state === 'frozen'));
    } catch (e) { /* ignored */ }
  }, []);

  useEffect(() => { refresh(); refreshDatasets(); }, [refresh, refreshDatasets]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.dataset_id) return;
    setBusy(true);
    try {
      const result = await createJob({
        dataset_id: form.dataset_id,
        target: form.target,
        config: { epochs: 1 },
      });
      setError(`Đã tạo job ${result.job_id} — chờ resource.`);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Tạo job thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onCancel = async (jobId) => {
    if (!window.confirm(`Cancel job ${jobId.slice(-12)}?`)) return;
    setBusy(true);
    try {
      await cancelJob(jobId);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Cancel thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const STATE_COLORS = {
    queued: 'bg-slate-200 text-slate-900',
    waiting_resource: 'bg-amber-100 text-amber-900',
    preparing: 'bg-amber-100 text-amber-900',
    training: 'bg-blue-100 text-blue-900',
    evaluating: 'bg-blue-100 text-blue-900',
    completed: 'bg-emerald-100 text-emerald-900',
    failed: 'bg-red-100 text-red-900',
    cancelled: 'bg-slate-300 text-slate-900',
  };

  return (
    <section aria-label="Training jobs" className="p-6 space-y-4">
      <header>
        <h1 className="text-xl font-bold">Training Jobs (Task 3.5)</h1>
        <p className="text-xs opacity-70">
          Một job GPU một thời điểm. Job ở trạng thái waiting_resource khi GPU bận —
          không tự dừng process Task 1.
        </p>
      </header>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}

      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2 text-sm"
        data-testid="new-job-form">
        <label className="flex items-center gap-2">
          Dataset (frozen):
          <select value={form.dataset_id} onChange={e => setForm({...form, dataset_id: e.target.value})}
            className="rounded bg-primary-container text-on-primary-container px-2 py-1"
            data-testid="dataset-select">
            <option value="">-- chọn --</option>
            {datasets.map(d => (
              <option key={d.id} value={d.id}>{d.name} ({d.engine})</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Target:
          <select value={form.target} onChange={e => setForm({...form, target: e.target.value})}
            className="rounded bg-primary-container text-on-primary-container px-2 py-1">
            <option value="plate_ocr">plate_ocr</option>
            <option value="plate_detector">plate_detector</option>
            <option value="helmet">helmet</option>
          </select>
        </label>
        <button type="submit" disabled={busy || !form.dataset_id}
          className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
          data-testid="submit-job">
          Tạo job
        </button>
      </form>

      <table className="w-full text-xs" data-testid="jobs-table">
        <thead>
          <tr className="border-b">
            <th className="text-left py-1">Job ID</th>
            <th className="text-left py-1">Dataset</th>
            <th className="text-left py-1">Target</th>
            <th className="text-left py-1">State</th>
            <th className="text-left py-1">Created</th>
            <th className="text-left py-1">Finished</th>
            <th className="text-left py-1">Hành động</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map(j => (
            <tr key={j.id} className="border-b">
              <td className="py-1 font-mono">{j.id.slice(-12)}</td>
              <td className="py-1 font-mono">{j.dataset_id.slice(-12)}</td>
              <td className="py-1">{j.target}</td>
              <td className="py-1">
                <span className={`text-xs rounded px-2 py-0.5 ${STATE_COLORS[j.state] || 'bg-slate-100'}`}>
                  {j.state}
                </span>
              </td>
              <td className="py-1">{j.created_at}</td>
              <td className="py-1">{j.finished_at || '—'}</td>
              <td className="py-1 space-x-1">
                {['queued', 'waiting_resource', 'preparing', 'training', 'evaluating'].includes(j.state) && (
                  <button type="button" onClick={() => onCancel(j.id)}
                    className="rounded bg-rose-700 text-white px-2 py-0.5"
                    data-testid={`cancel-${j.id.slice(-12)}`}>
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
          {!jobs.length && (
            <tr><td colSpan={7} className="py-2 text-center opacity-70">
              Chưa có job nào.
            </td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}