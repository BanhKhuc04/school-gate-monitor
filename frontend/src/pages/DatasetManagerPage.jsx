import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createDataset, freezeDataset, getLeakage, listDatasets, listSamples,
  runSplit,
} from '../training/api';
import { useLang } from '../i18n/LanguageContext';

/** Trang Dữ liệu huấn luyện — Task 3.
 *
 *  Tab 1: Datasets — list, create, freeze, view samples.
 *  Tab 2: Split — chạy 70/15/15 group-aware + leakage checker.
 *
 *  KHÔNG sửa GuardPage / PlateReviewPanel / RecognitionLogPanel (Task 1 giữ).
 *  KHÔNG tự phát bar TTS / loa.
 */
export default function DatasetManagerPage() {
  const { t } = useLang();
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
      setError(e.response?.data?.detail || t('Không tải được danh sách dataset.', 'Could not load the dataset list.'));
    }
  }, [engine, t]);

  useEffect(() => { refresh(); }, [refresh]);

  const onCreate = async () => {
    const name = window.prompt(t('Tên dataset (vd: ocr_v1, plate_det_v1):', 'Dataset name (e.g. ocr_v1, plate_det_v1):'), `ds_${Date.now()}`);
    if (!name) return;
    setBusy(true);
    try {
      await createDataset({ name, engine });
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || t('Tạo dataset thất bại.', 'Failed to create dataset.'));
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
      if (request === sampleRequest.current) setError(e.response?.data?.detail || t('Không tải được samples.', 'Could not load samples.'));
    } finally {
      if (request === sampleRequest.current) setLoadingSamples(false);
    }
  };

  const onFreeze = async (id) => {
    if (!window.confirm(t('Đóng băng bộ dữ liệu? Sau đó nhãn chỉ sửa được trên phiên bản mới.', 'Freeze this dataset? After that, labels can only be edited in a new version.'))) return;
    setBusy(true);
    try {
      await freezeDataset(id);
      await refresh();
    } catch (e) {
      setError(e.response?.data?.detail || t('Freeze thất bại.', 'Freeze failed.'));
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
      setNotice(t(`Đã chia dữ liệu: ${JSON.stringify(result.counts)}`, `Data split: ${JSON.stringify(result.counts)}`));
    } catch (e) {
      setError(e.response?.data?.detail || t('Split thất bại.', 'Split failed.'));
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
      setError(e.response?.data?.detail || t('Không chạy được leakage check.', 'Could not run the leakage check.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label={t('Dữ liệu huấn luyện', 'Training data')} className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">{t('Dữ liệu đã duyệt', 'Reviewed data')}</h1>
        <p className="text-xs opacity-70">
          {t('Xem nhãn, chỉnh bbox và chia dữ liệu theo lượt xe hoặc phiên nguồn trước khi đóng băng.', 'View labels, adjust bboxes and split data by bike pass or source session before freezing.')}
        </p>
      </header>
      <div className="flex flex-wrap gap-4 text-sm">
        <Link to="/settings/ai/reviews" className="text-primary underline">{t('Duyệt mẫu mới', 'Review new samples')}</Link>
        <Link to="/settings/ai/export" className="text-primary underline">{t('Xuất Kaggle', 'Export to Kaggle')}</Link>
      </div>

      <div role="tablist" aria-label={t('Quản lý bộ dữ liệu', 'Dataset management')} className="flex flex-wrap gap-2">
        {['datasets', 'split', 'leakage'].map(k => (
          <button
            key={k} type="button" role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={`rounded px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary ${tab === k ? 'bg-primary text-on-primary' : 'bg-primary-container text-on-primary-container'}`}
          >
            {k === 'datasets' && t('Bộ dữ liệu', 'Datasets')}
            {k === 'split' && t('Chia train / val / test', 'Train / val / test split')}
            {k === 'leakage' && t('Kiểm tra trùng dữ liệu', 'Duplicate data check')}
          </button>
        ))}
      </div>

      {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error}</div>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}

      {tab === 'datasets' && (
        <div className="space-y-3" data-testid="datasets-panel">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label className="flex items-center gap-2">
              {t('Bài toán:', 'Task:')}
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
              + {t('Bộ dữ liệu mới', 'New dataset')}
            </button>
            <button type="button" disabled={busy} onClick={refresh}
              className="rounded border border-outline-variant px-3 py-1">
              {t('Tải lại', 'Reload')}
            </button>
          </div>
          <div className="overflow-x-auto"><table className="w-full text-xs" data-testid="datasets-table">
            <thead>
              <tr className="border-b">
                <th className="text-left py-1">ID</th>
                <th className="text-left py-1">{t('Tên', 'Name')}</th>
                <th className="text-left py-1">{t('Bài toán', 'Task')}</th>
                <th className="text-left py-1">{t('Trạng thái', 'Status')}</th>
                <th className="text-left py-1">{t('Ngày tạo', 'Created')}</th>
                <th className="text-left py-1">{t('Hành động', 'Actions')}</th>
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
                      className="rounded border px-2 py-0.5">{t('Xem', 'View')}</button>
                    {d.freeze_state === 'draft' && (
                      <button type="button" onClick={() => onFreeze(d.id)}
                        className="rounded bg-amber-600 text-white px-2 py-0.5">{t('Đóng băng', 'Freeze')}</button>
                    )}
                  </td>
                </tr>
              ))}
              {!datasets.length && (
                <tr><td colSpan={6} className="py-2 text-center opacity-70">
                  {t('Chưa có dataset nào.', 'No datasets yet.')}
                </td></tr>
              )}
            </tbody>
          </table></div>
          {activeId && <section aria-label={t('Mẫu trong bộ dữ liệu', 'Samples in dataset')} className="rounded border border-outline-variant bg-surface p-4 space-y-3" data-testid="dataset-samples">
            <h2 className="font-semibold">{t('Mẫu trong', 'Samples in')} {datasets.find(d => d.id === activeId)?.name || t('bộ dữ liệu đã chọn', 'the selected dataset')}</h2>
            {loadingSamples ? <p role="status" className="text-sm">{t('Đang tải mẫu…', 'Loading samples…')}</p> : samples.length ? <ul className="divide-y divide-outline-variant">
              {samples.map(s => <li key={s.target_id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
                <div><span className="font-mono">{s.label?.target_text || s.target_id}</span><span className="ml-2 text-on-surface-variant">{s.label?.verdict}</span></div>
                <Link to={`/settings/ai/bbox?${new URLSearchParams({ dataset: activeId, sample: s.target_id })}`} className="rounded border border-primary px-3 py-1 text-primary">{t('Xem / Sửa bbox', 'View / Edit bbox')}</Link>
              </li>)}
            </ul> : <p className="text-sm text-on-surface-variant">{t('Chưa có mẫu. Duyệt mẫu vận hành để bổ sung dữ liệu.', 'No samples yet. Review operational samples to add data.')}</p>}
          </section>}
        </div>
      )}

      {tab === 'split' && (
        <div className="space-y-3" data-testid="split-panel">
          {!activeId && <p className="text-sm opacity-70">{t('Chọn dataset ở tab Datasets trước.', 'Select a dataset in the Datasets tab first.')}</p>}
          {activeId && (
            <>
              <button type="button" disabled={busy} onClick={onSplit}
                className="rounded bg-emerald-600 text-white px-3 py-1 disabled:opacity-50"
                data-testid="run-split">
                {t('Chạy split 70/15/15 theo group', 'Run 70/15/15 group-aware split')}
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
          {!activeId && <p className="text-sm opacity-70">{t('Chọn dataset ở tab Datasets trước.', 'Select a dataset in the Datasets tab first.')}</p>}
          {activeId && (
            <>
              <button type="button" disabled={busy} onClick={onLeakage}
                className="rounded bg-amber-600 text-white px-3 py-1 disabled:opacity-50"
                data-testid="run-leakage">
                {t('Kiểm tra leakage', 'Check leakage')}
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
