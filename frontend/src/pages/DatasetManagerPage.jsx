import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createDataset, freezeDataset, getLeakage, listDatasets, listSamples,
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
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [samples, setSamples] = useState([]);
  const [loadingSamples, setLoadingSamples] = useState(false);
  const sampleRequest = useRef(0);
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
    const request = ++sampleRequest.current;
    setActiveId(id);
    setSamples([]);
    setLoadingSamples(true);
    setError('');
    setLeakage(null);
    try {
      const resp = await listSamples(id);
      if (request === sampleRequest.current) setSamples(resp.items || []);
    } catch (e) {
      if (request === sampleRequest.current) setError(e.response?.data?.detail || 'Không tải được samples.');
    } finally {
      if (request === sampleRequest.current) setLoadingSamples(false);
    }
  };

  const onFreeze = async (id) => {
    if (!window.confirm('Đóng băng bộ dữ liệu? Sau đó nhãn chỉ sửa được trên phiên bản mới.')) return;
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
      setNotice(`Đã chia dữ liệu: ${JSON.stringify(result.counts)}`);
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
        <h1 className="text-xl font-bold">Dữ liệu đã duyệt</h1>
        <p className="text-xs opacity-70">
          Xem nhãn, chỉnh bbox và chia dữ liệu theo lượt xe hoặc phiên nguồn trước khi đóng băng.
        </p>
      </header>
      <div className="flex flex-wrap gap-4 text-sm">
        <Link to="/settings/ai/reviews" className="text-primary underline">Duyệt mẫu mới</Link>
        <Link to="/settings/ai/export" className="text-primary underline">Xuất Kaggle</Link>
      </div>

      <div role="tablist" aria-label="Quản lý bộ dữ liệu" className="flex flex-wrap gap-2">
        {['datasets', 'split', 'leakage'].map(t => (
          <button
            key={t} type="button" role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${tab === t ? 'bg-primary text-on-primary' : 'bg-primary-container text-on-primary-container'}`}
          >
            {t === 'datasets' && 'Bộ dữ liệu'}
            {t === 'split' && 'Chia train / val / test'}
            {t === 'leakage' && 'Kiểm tra trùng dữ liệu'}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}

      {tab === 'datasets' && (
        <div className="space-y-3" data-testid="datasets-panel">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label className="flex items-center gap-2">
              Bài toán:
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
              + Bộ dữ liệu mới
            </button>
            <button type="button" disabled={busy} onClick={refresh}
              className="rounded border border-outline-variant px-3 py-1">
              Tải lại
            </button>
          </div>
          <div className="overflow-x-auto"><table className="w-full text-xs" data-testid="datasets-table">
            <thead>
              <tr className="border-b">
                <th className="text-left py-1">ID</th>
                <th className="text-left py-1">Tên</th>
                <th className="text-left py-1">Bài toán</th>
                <th className="text-left py-1">Trạng thái</th>
                <th className="text-left py-1">Ngày tạo</th>
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
                        className="rounded bg-amber-600 text-white px-2 py-0.5">Đóng băng</button>
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
          </table></div>
          {activeId && <section aria-label="Mẫu trong bộ dữ liệu" className="rounded border border-outline-variant bg-surface p-4 space-y-3" data-testid="dataset-samples">
            <h2 className="font-semibold">Mẫu trong {datasets.find(d => d.id === activeId)?.name || 'bộ dữ liệu đã chọn'}</h2>
            {loadingSamples ? <p role="status" className="text-sm">Đang tải mẫu…</p> : samples.length ? <ul className="divide-y divide-outline-variant">
              {samples.map(s => <li key={s.target_id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
                <div><span className="font-mono">{s.label?.target_text || s.target_id}</span><span className="ml-2 text-on-surface-variant">{s.label?.verdict}</span></div>
                <Link to={`/settings/ai/bbox?${new URLSearchParams({ dataset: activeId, sample: s.target_id })}`} className="rounded border border-primary px-3 py-1 text-primary">Xem / Sửa bbox</Link>
              </li>)}
            </ul> : <p className="text-sm text-on-surface-variant">Chưa có mẫu. Duyệt mẫu vận hành để bổ sung dữ liệu.</p>}
          </section>}
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
