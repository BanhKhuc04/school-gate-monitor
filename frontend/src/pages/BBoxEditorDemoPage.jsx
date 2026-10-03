import { useCallback, useEffect, useMemo, useState } from 'react';
import BBoxEditor, {BBoxValid, normalizeBBox} from '../components/training/BBoxEditor.jsx';
import {listSamples, patchSampleBBox} from '../training/api';

/** Trang demo BBoxEditor — Task 3 T3.1.
 *
 *  Liệt kê samples của dataset đã chọn, mỗi sample có:
 *    - Ảnh crop từ source.media_url (nếu backend trả về) hoặc placeholder
 *    - BBox editor để chỉnh (move + 8 handles, keyboard arrow)
 *    - Nút "Lưu bbox" gọi PATCH /api/training/datasets/{id}/samples/{target_id}/bbox
 *      với expected_version từ version hiện tại
 *
 *  KHÔNG auto-fill học sinh, KHÔNG tự động infer bbox từ corrected_text,
 *  KHÔNG thay model runtime.
 *
 *  Optimistic version: 409 khi stale → UI refetch sample để lấy version mới.
 */
export default function BBoxEditorDemoPage() {
  const [datasetId, setDatasetId] = useState('');
  const [samples, setSamples] = useState([]);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [pending, setPending] = useState({}); // target_id -> { bbox, version }

  const reload = useCallback(async () => {
    if (!datasetId) return;
    setError('');
    try {
      const resp = await listSamples(datasetId);
      setSamples(resp.items || []);
      setPending({});
    } catch (e) {
      setError(e.response?.data?.detail || 'Không tải được samples.');
    }
  }, [datasetId]);

  useEffect(() => { reload(); }, [reload]);

  const onBBoxChange = useCallback((targetId, bbox) => {
    setPending(p => ({...p, [targetId]: {...(p[targetId] || {}), bbox}}));
  }, []);

  const onSubmit = useCallback(async (sample, bbox, reason) => {
    const targetId = sample.target_id;
    const version = sample.version || 0;
    setBusyId(targetId);
    setError('');
    try {
      const resp = await patchSampleBBox(datasetId, targetId, {
        bbox, expectedVersion: version, reason,
      });
      setSamples(prev => prev.map(s =>
        s.target_id === targetId ? {...s, bbox: resp.bbox, version: resp.version} : s));
      setPending(p => {
        const {[targetId]: _, ...rest} = p;
        return rest;
      });
    } catch (e) {
      if (e.response?.status === 409) {
        setError('Version đã thay đổi — đang tải lại sample…');
        await reload();
      } else {
        setError(e.response?.data?.detail || 'Sửa bbox thất bại.');
      }
    } finally {
      setBusyId(null);
    }
  }, [datasetId, reload]);

  const sampleBBoxes = useMemo(() => {
    const out = {};
    samples.forEach(s => {
      const pendingBBox = pending[s.target_id]?.bbox;
      out[s.target_id] = pendingBBox || s.bbox;
    });
    return out;
  }, [samples, pending]);

  return (
    <section aria-label="Sửa bbox sample" className="p-6 space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-bold">Sửa bbox sample (Task 3)</h1>
        <p className="text-xs opacity-70">
          Kéo các handle để resize, kéo vùng trong để di chuyển. Arrow keys để chỉnh
          chính xác (Shift = 5x). Lưu sẽ tăng version — không thể ghi đè.
        </p>
      </header>

      <div className="flex items-center gap-2 text-sm">
        <label className="flex items-center gap-2">
          Dataset ID:
          <input
            value={datasetId}
            onChange={e => setDatasetId(e.target.value)}
            placeholder="dsv_xxx"
            className="rounded border px-2 py-1 font-mono w-72"
            data-testid="dataset-id-input"
          />
        </label>
        <button type="button" onClick={reload} disabled={!datasetId}
          className="rounded border px-3 py-1 disabled:opacity-50"
          data-testid="reload-samples">
          Tải samples
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-3" data-testid="bbox-editor-list">
        {!datasetId && (
          <p className="text-sm opacity-70">Nhập dataset ID để bắt đầu.</p>
        )}
        {datasetId && !samples.length && (
          <p className="text-sm opacity-70">Dataset này chưa có sample nào.</p>
        )}
        {samples.map(s => {
          const bbox = sampleBBoxes[s.target_id];
          const valid = bbox && BBoxValid(bbox);
          const dirty = !!pending[s.target_id]?.bbox && JSON.stringify(bbox) !== JSON.stringify(s.bbox);
          const cropUrl = s.source?.crop_url || s.crop_url || null;
          const isBusy = busyId === s.target_id;
          return (
            <article key={s.target_id}
              className="rounded border border-slate-300 bg-white p-3 space-y-2"
              data-testid="bbox-editor-row">
              <header className="flex items-center justify-between text-xs">
                <div className="font-mono">{s.target_id}</div>
                <div>
                  verdict: <strong>{s.label?.verdict}</strong> · version:{' '}
                  <strong>{s.version || 0}</strong> {dirty && '(unsaved)'}
                </div>
              </header>
              <BBoxEditor
                src={cropUrl}
                initialBBox={bbox}
                canEdit={valid}
                imageKind="crop"
                onChange={nb => onBBoxChange(s.target_id, nb)}
                onSubmit={nb => onSubmit(s, nb, 'manual_edit')}
                busy={isBusy}
                hints="Drag handle để resize; Esc để reset; Enter để lưu."
              />
            </article>
          );
        })}
      </div>
    </section>
  );
}