import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import BBoxEditor from '../components/training/BBoxEditor.jsx';
import { listDatasets, listSamples, patchSampleBBox } from '../training/api';

export default function BBoxEditorDemoPage() {
  const [params, setParams] = useSearchParams();
  const datasetId = params.get('dataset') || '';
  const sampleId = params.get('sample') || '';
  const [datasets, setDatasets] = useState([]);
  const [samples, setSamples] = useState([]);
  const [loadedDataset, setLoadedDataset] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    listDatasets().then(items => { if (active) setDatasets(items); })
      .catch(e => { if (active) setError(e.response?.data?.detail || 'Không tải được bộ dữ liệu.'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!datasetId) return;
    Promise.resolve().then(() => {
      if (active) { setLoading(true); setSamples([]); }
      return listSamples(datasetId);
    }).then(resp => { if (active) { setSamples(resp.items || []); setLoadedDataset(datasetId); } })
      .catch(e => { if (active) setError(e.response?.data?.detail || 'Không tải được mẫu.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [datasetId, revision]);

  const onSubmit = useCallback(async (sample, bbox) => {
    setBusyId(sample.target_id); setError(''); setNotice('');
    try {
      const resp = await patchSampleBBox(datasetId, sample.target_id, {
        bbox, expectedVersion: sample.version || 0, reason: 'manual_edit',
      });
      setSamples(previous => previous.map(s => s.target_id === sample.target_id ? { ...s, bbox: resp.bbox, version: resp.version } : s));
      setNotice('Đã lưu bbox.');
    } catch (e) {
      if (e.response?.status === 409) {
        setError('Mẫu hoặc bộ dữ liệu đã thay đổi. Đang tải phiên bản mới; kiểm tra lại trước khi lưu.');
        setRevision(value => value + 1);
      } else setError(e.response?.data?.detail || 'Lưu bbox thất bại.');
    } finally { setBusyId(null); }
  }, [datasetId]);

  const selectedDataset = datasets.find(d => d.id === datasetId);
  const visibleSamples = datasetId && loadedDataset === datasetId ? samples.filter(s => !sampleId || s.target_id === sampleId) : [];
  const frozen = selectedDataset?.freeze_state !== 'draft';

  return (
    <section aria-label="Sửa bbox sample" className="p-4 md:p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Sửa bbox</h1>
        <p className="text-sm text-on-surface-variant">Kéo khung hoặc dùng phím mũi tên để chỉnh trên ảnh nguồn. Kiểm tra ảnh trước khi lưu.</p>
      </header>
      <Link to="/settings/ai/datasets" className="inline-block text-sm text-primary underline">Quay lại bộ dữ liệu</Link>
      <label className="block text-sm space-y-1"><span className="block">Bộ dữ liệu</span>
        <select value={datasetId} onChange={e => { setParams(e.target.value ? { dataset: e.target.value } : {}); setNotice(''); setError(''); }}
          className="max-w-full rounded border border-outline-variant bg-surface px-3 py-2" data-testid="bbox-dataset-select">
          <option value="">Chọn bộ dữ liệu</option>
          {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      {error && <p role="alert" className="rounded bg-error-container text-on-error-container p-3 text-sm">{error}</p>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}
      {loading && <p role="status" className="text-sm">Đang tải mẫu…</p>}
      {datasetId && selectedDataset && frozen && <p className="text-sm">Bộ dữ liệu đã đóng băng. Tạo phiên bản mới để sửa nhãn.</p>}
      {!datasetId && <p className="text-sm text-on-surface-variant">Chọn bộ dữ liệu hoặc mở một mẫu từ trang dữ liệu đã duyệt.</p>}
      {datasetId && !loading && !visibleSamples.length && <p className="text-sm text-on-surface-variant">{sampleId ? 'Không tìm thấy mẫu đã chọn trong bộ dữ liệu này.' : 'Bộ dữ liệu chưa có mẫu.'}</p>}
      <div className="space-y-3" data-testid="bbox-editor-list">
        {visibleSamples.map(s => {
          const bbox = s.bbox;
          const imageUrl = '/api/training/datasets/' + encodeURIComponent(datasetId) + '/samples/' + encodeURIComponent(s.target_id) + '/image';
          return <article key={s.target_id} className="rounded border border-outline-variant bg-surface p-3 space-y-2" data-testid="bbox-editor-row">
            <header className="flex flex-wrap justify-between gap-2 text-sm">
              <span className="font-mono break-all">{s.label?.target_text || s.target_id}</span>
              <span>{s.label?.verdict} · phiên bản {s.version || 0}</span>
            </header>
            <BBoxEditor src={imageUrl} initialBBox={bbox} canEdit={!frozen}
              onSubmit={next => onSubmit(s, next)} busy={busyId === s.target_id}
              hints="Mũi tên: di chuyển · Shift: bước lớn · Esc: khôi phục" />
          </article>;
        })}
      </div>
    </section>
  );
}
