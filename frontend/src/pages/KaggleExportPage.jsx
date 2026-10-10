import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { exportZip, listDatasets } from '../training/api';

export default function KaggleExportPage() {
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    listDatasets().then(items => { if (active) setDatasets(items.filter(d => d.freeze_state === 'frozen')); })
      .catch(e => { if (active) setError(e.response?.data?.detail || 'Không tải được bộ dữ liệu.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function onExport(e) {
    e.preventDefault();
    setBusy(true); setError(''); setResult(null);
    try { setResult(await exportZip(datasetId)); }
    catch (err) { setError(err.response?.data?.detail || 'Xuất dữ liệu thất bại.'); }
    finally { setBusy(false); }
  }
  return (
    <section className="p-4 md:p-6 space-y-4" aria-label="Xuất Kaggle">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Xuất Kaggle</h1>
        <p className="text-sm text-on-surface-variant">Chọn bộ dữ liệu đóng băng để xuất ZIP portable gồm ảnh, nhãn và manifest. Tải ZIP lên dataset riêng tư trên Kaggle.</p>
      </header>
      {error && <p role="alert" className="rounded bg-error-container text-on-error-container p-3 text-sm">{error}</p>}
      <form onSubmit={onExport} className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm"><span className="block">Bộ dữ liệu đã đóng băng</span>
          <select value={datasetId} onChange={e => { setDatasetId(e.target.value); setResult(null); }} disabled={busy || loading}
            className="max-w-full rounded border border-outline-variant bg-surface px-3 py-2" data-testid="export-dataset-select">
            <option value="">{loading ? 'Đang tải…' : 'Chọn bộ dữ liệu'}</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name} ({d.engine})</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy || !datasetId} className="rounded bg-primary text-on-primary px-4 py-2 text-sm disabled:opacity-50">{busy ? 'Đang xuất…' : 'Xuất ZIP'}</button>
      </form>
      {!loading && !datasets.length && <p className="text-sm">Chưa có bộ dữ liệu đóng băng. <Link className="text-primary underline" to="/settings/ai/datasets">Duyệt và đóng băng dữ liệu</Link> trước khi xuất.</p>}
      {result && <div role="status" className="rounded border border-outline-variant bg-surface p-4 text-sm space-y-2">
        <p className="font-medium">Đã tạo ZIP trên máy chủ local</p>
        <p className="font-mono break-all">{result.zip_path}</p>
        <p>{result.sample_count ?? '—'} mẫu · {result.asset_count ?? '—'} ảnh · {((result.size || 0) / 1024 / 1024).toFixed(2)} MB</p>
        {result.missing_files?.length > 0 && <p className="text-error">Thiếu {result.missing_files.length} ảnh nguồn. Bổ sung ảnh trước khi huấn luyện.</p>}
      </div>}
    </section>
  );
}
