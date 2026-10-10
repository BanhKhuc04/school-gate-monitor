import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import BBoxEditor from '../components/training/BBoxEditor.jsx';
import { listDatasets, listSamples, patchSampleBBox } from '../training/api';
import { useLang } from '../i18n/LanguageContext';

export default function BBoxEditorDemoPage() {
  const { t } = useLang();
  const tRef = useRef(t);
  useEffect(() => { tRef.current = t; });
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
      .catch(e => { if (active) setError(e.response?.data?.detail || tRef.current('Không tải được bộ dữ liệu.', 'Could not load datasets.')); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!datasetId) return;
    Promise.resolve().then(() => {
      if (active) { setLoading(true); setSamples([]); }
      return listSamples(datasetId);
    }).then(resp => { if (active) { setSamples(resp.items || []); setLoadedDataset(datasetId); } })
      .catch(e => { if (active) setError(e.response?.data?.detail || tRef.current('Không tải được mẫu.', 'Could not load samples.')); })
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
      setNotice(tRef.current('Đã lưu bbox.', 'Bbox saved.'));
    } catch (e) {
      if (e.response?.status === 409) {
        setError(tRef.current('Mẫu hoặc bộ dữ liệu đã thay đổi. Đang tải phiên bản mới; kiểm tra lại trước khi lưu.', 'The sample or dataset changed. Loading the new version; check again before saving.'));
        setRevision(value => value + 1);
      } else setError(e.response?.data?.detail || tRef.current('Lưu bbox thất bại.', 'Saving bbox failed.'));
    } finally { setBusyId(null); }
  }, [datasetId]);

  const selectedDataset = datasets.find(d => d.id === datasetId);
  const visibleSamples = datasetId && loadedDataset === datasetId ? samples.filter(s => !sampleId || s.target_id === sampleId) : [];
  const frozen = selectedDataset?.freeze_state !== 'draft';

  return (
    <section aria-label={t('Sửa bbox sample', 'Edit sample bbox')} className="p-4 md:p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">{t('Sửa bbox', 'Edit bbox')}</h1>
        <p className="text-sm text-on-surface-variant">{t('Kéo khung hoặc dùng phím mũi tên để chỉnh trên ảnh nguồn. Kiểm tra ảnh trước khi lưu.', 'Drag the box or use the arrow keys to adjust it on the source image. Check the image before saving.')}</p>
      </header>
      <Link to="/settings/ai/datasets" className="inline-block text-sm text-primary underline">{t('Quay lại bộ dữ liệu', 'Back to datasets')}</Link>
      <label className="block text-sm space-y-1"><span className="block">{t('Bộ dữ liệu', 'Dataset')}</span>
        <select value={datasetId} onChange={e => { setParams(e.target.value ? { dataset: e.target.value } : {}); setNotice(''); setError(''); }}
          className="max-w-full rounded border border-outline-variant bg-surface px-3 py-2" data-testid="bbox-dataset-select">
          <option value="">{t('Chọn bộ dữ liệu', 'Choose dataset')}</option>
          {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      {error && <p role="alert" className="rounded bg-error-container text-on-error-container p-3 text-sm">{error}</p>}
      {notice && <p role="status" className="text-sm text-primary">{notice}</p>}
      {loading && <p role="status" className="text-sm">{t('Đang tải mẫu…', 'Loading samples…')}</p>}
      {datasetId && selectedDataset && frozen && <p className="text-sm">{t('Bộ dữ liệu đã đóng băng. Tạo phiên bản mới để sửa nhãn.', 'Dataset is frozen. Create a new version to edit labels.')}</p>}
      {!datasetId && <p className="text-sm text-on-surface-variant">{t('Chọn bộ dữ liệu hoặc mở một mẫu từ trang dữ liệu đã duyệt.', 'Choose a dataset or open a sample from the reviewed data page.')}</p>}
      {datasetId && !loading && !visibleSamples.length && <p className="text-sm text-on-surface-variant">{sampleId ? t('Không tìm thấy mẫu đã chọn trong bộ dữ liệu này.', 'Selected sample not found in this dataset.') : t('Bộ dữ liệu chưa có mẫu.', 'This dataset has no samples yet.')}</p>}
      <div className="space-y-3" data-testid="bbox-editor-list">
        {visibleSamples.map(s => {
          const bbox = s.bbox;
          const imageUrl = '/api/training/datasets/' + encodeURIComponent(datasetId) + '/samples/' + encodeURIComponent(s.target_id) + '/image';
          return <article key={s.target_id} className="rounded border border-outline-variant bg-surface p-3 space-y-2" data-testid="bbox-editor-row">
            <header className="flex flex-wrap justify-between gap-2 text-sm">
              <span className="font-mono break-all">{s.label?.target_text || s.target_id}</span>
              <span>{s.label?.verdict} · {t('phiên bản', 'version')} {s.version || 0}</span>
            </header>
            <BBoxEditor src={imageUrl} initialBBox={bbox} canEdit={!frozen}
              onSubmit={next => onSubmit(s, next)} busy={busyId === s.target_id}
              hints={t('Mũi tên: di chuyển · Shift: bước lớn · Esc: khôi phục', 'Arrows: move · Shift: big step · Esc: reset')} />
          </article>;
        })}
      </div>
    </section>
  );
}
