import { useCallback, useEffect, useState } from 'react';
import {
  addSamples, createDataset, freezeDataset, getLeakage, listDatasets, listSamples,
  runSplit,
} from '../training/api';

/** Trang Dữ liệu huấn luyện — Task 3.
 *
 *  Tab 1: Datasets — list, create, freeze, view samples.
 *  Tab 2: Split — chạy 70/15/15 group-aware + leakage checker.
 *
 *  KHÔNG sửa GuardPage / PlateReviewPanel / RecognitionLogPanel (Task 1 giữ).
 *  KHÔNG tự phát bar TTS / loa.
 */
export default function DatasetManagerPage() {
  const [datasets, setDatasets] = useState([]);
  const [engine, setEngine] = useState('plate_ocr');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [samples, setSamples] = useState([]);
  const [leakage, setLeakage] = useState(null);
  const [tab, setTab] = useState('datasets');

  const refresh = useCallback(async () => {
    setError('');
    try {
      const items = await listDatasets(engine);
      setDatasets(items);
    } catch (e) {
      setError(e.response?.data?.detail || 'Không tải được danh sách dataset.');
    }
  }, [engine]);

  useEffect(() => { refresh(); }, [refresh]);

  const onCreate = async () => {
    const name = window.prompt('Tên dataset (vd: ocr_v1, plate_det_v1):', `ds_${Date.now()}`);
    if (!name) return;
    setBusy(true);
    try {
      await createDataset({ name, engine });
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Tạo dataset thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onSelect = async (id) => {
    setActiveId(id);
    setError('');
    setLeakage(null);
    try {
      const resp = await listSamples(id);
      setSamples(resp.items || []);
    } catch (e) {
      setError(e.response?.data?.detail || 'Không tải được samples.');
    }
  };

  const onFreeze = async (id) => {
    if (!window.confirm('Freeze dataset? Sau đó không sửa được.')) return;
    setBusy(true);
    try {
      await freezeDataset(id);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || 'Freeze thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onSplit = async () => {
    if (!activeId) return;
    setBusy(true);
    try {
      const result = await runSplit(activeId, { seed: 42 });
      await onSelect(activeId);
      setError(`Split xong: ${JSON.stringify(result.counts)}`);
    } catch (e) {
      setError(e.response?.data?.detail || 'Split thất bại.');
    } finally {
      setBusy(false);
    }
  };

  const onLeakage = async () => {
    if (!activeId) return;
    setBusy(true);
    try {
      const data = await getLeakage(activeId);
      setLeakage(data.findings);
    } catch (e) {
      setError(e.response?.data?.detail || 'Không chạy được leakage check.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Dữ liệu huấn luyện" className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Dữ liệu huấn luyện (Task 3)</h1>
        <p className="text-xs opacity-70">
          Datasets/samples/splits cho feedback OCR/detector/helmet đã được admin duyệt.
          Feedback lưu ngay nhưng training diễn theo đợt — không tự đổi weights.
        </p>
      </header>

      <div role="tablist" className="tabs tabs-bordered">
        {['datasets', 'split', 'leakage'].map(t => (
          <button
            key={t} type="button" role="tab"
            onClick={() => setTab(t)}
            className={`tab ${tab === t ? 'tab-active' : ''}`}
          >
            {t === 'datasets' && 'Datasets'}
            {t === 'split' && 'Split 70/15/15'}
            {t === 'leakage' && 'Leakage'}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}

      {tab === 'datasets' && (
        <div className="space-y-3" data-testid="datasets-panel">
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
            <button type="button" disabled={busy} onClick={onCreate}
              className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
              data-testid="create-dataset">
              + Dataset mới
            </button>
            <button type="button" disabled={busy} onClick={refresh}
              className="rounded border border-white/30 px-3 py-1">
              Refresh
            </button>
          </div>
          <table className="w-full text-xs" data-testid="datasets-table">
            <thead>
              <tr className="border-b">
                <th className="text-left py-1">ID</th>
                <th className="text-left py-1">Name</th>
                <th className="text-left py-1">Engine</th>
                <th className="text-left py-1">State</th>
                <th className="text-left py-1">Created</th>
                <th className="text-left py-1">Hành động</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map(d => (
                <tr key={d.id} className="border-b hover:bg-primary-container/40">
                  <td className="py-1 font-mono">{d.id.slice(-12)}</td>
                  <td className="py-1">{d.name}</td>
                  <td className="py-1">{d.engine}</td>
                  <td className="py-1">{d.freeze_state}</td>
                  <td className="py-1">{d.created_at}</td>
                  <td className="py-1 space-x-1">
                    <button type="button" onClick={() => onSelect(d.id)}
                      className="rounded border px-2 py-0.5">Xem</button>
                    {d.freeze_state === 'draft' && (
                      <button type="button" onClick={() => onFreeze(d.id)}
                        className="rounded bg-amber-600 text-white px-2 py-0.5">Freeze</button>
                    )}
                  </td>
                </tr>
              ))}
              {!datasets.length && (
                <tr><td colSpan={6} className="py-2 text-center opacity-70">
                  Chưa có dataset nào.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'split' && (
        <div className="space-y-3" data-testid="split-panel">
          {!activeId && <p className="text-sm opacity-70">Chọn dataset ở tab Datasets trước.</p>}
          {activeId && (
            <>
              <button type="button" disabled={busy} onClick={onSplit}
                className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
                data-testid="run-split">
                Chạy split 70/15/15 theo group
              </button>
              <p className="text-xs opacity-70">Dataset {activeId.slice(-12)}</p>
              <div className="overflow-y-auto max-h-[60vh]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-1">target_id</th>
                      <th className="text-left py-1">split</th>
                      <th className="text-left py-1">verdict</th>
                      <th className="text-left py-1">target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {samples.map(s => (
                      <tr key={s.target_id} className="border-b">
                        <td className="py-1 font-mono">{s.target_id.slice(-12)}</td>
                        <td className="py-1">{s._split || '—'}</td>
                        <td className="py-1">{s.label?.verdict}</td>
                        <td className="py-1 font-mono">{s.label?.target_text || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'leakage' && (
        <div className="space-y-3" data-testid="leakage-panel">
          {!activeId && <p className="text-sm opacity-70">Chọn dataset ở tab Datasets trước.</p>}
          {activeId && (
            <>
              <button type="button" disabled={busy} onClick={onLeakage}
                className="rounded bg-amber-600 text-white px-3 py-1 disabled:opacity-50"
                data-testid="run-leakage">
                Kiểm tra leakage
              </button>
              {leakage && (
                <pre className="text-xs bg-primary-container text-on-primary-container p-3 rounded overflow-auto max-h-[60vh]"
                  data-testid="leakage-output">
                  {JSON.stringify(leakage, null, 2)}
                </pre>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}