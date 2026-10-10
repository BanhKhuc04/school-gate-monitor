import { useEffect, useRef, useState } from 'react';
import client, { API_BASE_URL } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorBanner from '../components/ErrorBanner';
import { useLang } from '../i18n/LanguageContext';

const CUSTOM = '__custom__';
const fieldClass = 'w-full rounded-lg border border-outline-variant bg-surface px-3 py-2.5 text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-60';
const errorText = (error, t) => typeof error.response?.data?.detail === 'string'
  ? error.response.data.detail : t('Không kết nối được máy chủ. Vui lòng thử lại.', 'Could not reach the server. Please try again.');

export default function AdminCameraPage() {
  const { t } = useLang();
  // Effects read the current language through a ref so a language switch does not restart them.
  const tRef = useRef(t);
  useEffect(() => { tRef.current = t; });
  const [gates, setGates] = useState([]);
  const [gate, setGate] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    client.get('/api/camera', { signal: controller.signal }).then(({ data }) => {
      setGates(data.gates);
      setGate(current => data.gates.some(g => g.id === current) ? current : data.gates[0]?.id || '');
    }).catch(err => {
      if (!controller.signal.aborted) setError(errorText(err, tRef.current));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);

  return (
    <div className="min-h-screen bg-surface-container-low p-6">
      <div className="max-w-5xl mx-auto">
        <p className="font-mono text-xs uppercase tracking-wider text-secondary mb-2">{t('Hạ tầng camera', 'Camera infrastructure')}</p>
        <h1 className="text-2xl font-bold text-primary mb-2">{t('Cấu hình Camera', 'Camera Setup')}</h1>
        <p className="text-sm text-on-surface-variant mb-6">{t('Chọn nguồn cho từng cổng. Hệ thống chỉ lưu thay đổi khi nhận được hình ảnh từ nguồn mới.', 'Pick a source for each gate. Changes are only saved once the new source delivers a picture.')}</p>
        {loading ? <LoadingSkeleton type="form" rows={3} /> : error ? (
          <div role="alert"><ErrorBanner message={error} onRetry={() => { setLoading(true); setError(''); setRetry(n => n + 1); }} /></div>
        ) : gates.length === 0 ? <EmptyState title={t('Chưa có cổng camera', 'No camera gates yet')} message={t('Cấu hình cổng trong backend để bắt đầu.', 'Configure gates in the backend to get started.')} /> : (
          <>
            <div className="max-w-sm mb-5">
              <label htmlFor="camera-gate" className="block text-sm font-semibold text-primary mb-2">{t('Cổng camera', 'Camera gate')}</label>
              <select id="camera-gate" className={fieldClass} value={gate} disabled={busy} onChange={e => setGate(e.target.value)}>
                {gates.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
            <CameraForm key={gate} gate={gate} onBusyChange={setBusy} />
          </>
        )}
      </div>
    </div>
  );
}

function CameraForm({ gate, onBusyChange }) {
  const { token } = useAuth();
  const { t } = useLang();
  const tRef = useRef(t);
  useEffect(() => { tRef.current = t; });
  const [camera, setCamera] = useState(null);
  const [selected, setSelected] = useState('');
  const [custom, setCustom] = useState('');
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [retry, setRetry] = useState(0);
  const initialized = useRef(false);
  const requestVersion = useRef(0);
  const posting = useRef(false);
  const requestController = useRef(null);
  const busy = submitting || camera?.state === 'checking';

  useEffect(() => { onBusyChange(busy); return () => onBusyChange(false); }, [busy, onBusyChange]);

  useEffect(() => {
    const controller = new AbortController();
    requestController.current = controller;
    let timer;
    async function poll() {
      const version = requestVersion.current;
      try {
        if (posting.current) return;
        const { data } = await client.get(`/api/camera/${encodeURIComponent(gate)}`, { signal: controller.signal });
        if (controller.signal.aborted || version !== requestVersion.current) return;
        setCamera(data);
        setLoadError('');
        if (!initialized.current) {
          setSelected(data.current_preset_id || CUSTOM);
          // URLs returned by the API omit secrets: do not submit a redacted URL as a new source.
          setCustom(/^\d+$/.test(String(data.current)) ? String(data.current) : '');
          initialized.current = true;
        }
      } catch (err) {
        if (!controller.signal.aborted && version === requestVersion.current) setLoadError(errorText(err, tRef.current));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 1500);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [gate, retry]);

  async function apply(event) {
    event.preventDefault();
    if (busy || posting.current) return;
    setActionError('');
    requestVersion.current += 1;
    posting.current = true;
    setSubmitting(true);
    const signal = requestController.current.signal;
    try {
      const payload = selected === CUSTOM ? { source: custom.trim() } : { preset_id: selected };
      const { data } = await client.post(`/api/camera/${encodeURIComponent(gate)}`, payload, { signal });
      if (!signal.aborted) setCamera(data);
    } catch (err) {
      if (!signal.aborted) setActionError(errorText(err, t));
    } finally {
      posting.current = false;
      if (!signal.aborted) setSubmitting(false);
    }
  }

  if (!camera) return loadError
    ? <div role="alert"><ErrorBanner message={loadError} onRetry={() => setRetry(n => n + 1)} /></div>
    : <LoadingSkeleton type="form" rows={4} />;

  const health = camera.health || {};
  const online = health.camera_open && health.thread_alive && health.last_frame_age_sec != null && health.last_frame_age_sec < 5;
  const statusMessage = busy ? t('Đang kiểm tra nguồn mới và chờ khung hình đầu tiên…', 'Checking the new source and waiting for the first frame…')
    : camera.state === 'applied' ? t('Đã áp dụng nguồn camera. Nếu đổi góc nhìn, hãy kiểm tra lại vùng nhận diện ROI.', 'Camera source applied. If the view angle changed, re-check the ROI detection zone.') : '';
  const failure = actionError || (camera.state === 'error' ? camera.error : '');

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
      <form onSubmit={apply} className="bg-surface rounded-xl border border-outline-variant p-5">
        <h2 className="font-semibold text-primary mb-4">{t('Nguồn hình ảnh', 'Video source')}</h2>
        <div className="mb-5 text-sm text-on-surface-variant">
          <span>{online ? t('Nguồn đang chạy: ', 'Active source: ') : t('Nguồn đã cấu hình: ', 'Configured source: ')}</span>
          <span data-testid="current-source" className="font-mono text-on-surface break-all">{String(camera.current ?? '') || t('Chưa có', 'None')}</span>
        </div>
        {loadError && <div role="alert"><ErrorBanner message={loadError} onRetry={() => setRetry(n => n + 1)} /></div>}
        <fieldset disabled={busy || !!loadError} className="space-y-4">
          <div>
            <label htmlFor="camera-source" className="block text-sm font-semibold text-primary mb-2">{t('Nguồn camera', 'Camera source')}</label>
            <select id="camera-source" className={fieldClass} value={selected} onChange={e => { setSelected(e.target.value); setActionError(''); }}>
              {camera.presets.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
              <option value={CUSTOM}>{t('Nhập webcam, URL hoặc file video', 'Enter a webcam, URL or video file')}</option>
            </select>
          </div>
          {selected === CUSTOM && (
            <div>
              <label htmlFor="camera-custom" className="block text-sm font-semibold text-primary mb-2">{t('Chỉ số webcam / URL / đường dẫn video', 'Webcam index / URL / video path')}</label>
              <input id="camera-custom" className={fieldClass} value={custom} maxLength={2048} required autoComplete="off" spellCheck={false}
                onChange={e => { setCustom(e.target.value); setActionError(''); }} placeholder={t(String.raw`0, rtsp://… hoặc D:\\Videos\\demo.mp4`, String.raw`0, rtsp://… or D:\\Videos\\demo.mp4`)} aria-describedby="camera-help" />
              <p id="camera-help" className="text-xs text-on-surface-variant mt-2 leading-relaxed">{t('Webcam là thiết bị gắn với máy chạy backend. File video cũng phải nằm trên máy đó. URL camera cần đầy đủ thông tin kết nối.', 'A webcam is a device attached to the machine running the backend. Video files must be on that machine too. Camera URLs need full connection details.')}</p>
            </div>
          )}
          <button type="submit" disabled={!selected || (selected === CUSTOM && !custom.trim())} className="bg-secondary text-on-secondary font-semibold text-sm py-2.5 px-4 rounded-lg disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            {busy ? t('Đang kiểm tra…', 'Checking…') : t('Kiểm tra và áp dụng', 'Test and apply')}
          </button>
        </fieldset>
        <p role="status" aria-live="polite" className="text-sm text-primary mt-4">{statusMessage}</p>
        {failure && <p role="alert" className="mt-3 text-sm text-error">{failure}</p>}
        <p className="mt-4 text-xs text-on-surface-variant leading-relaxed">{t('Nếu không kết nối được nguồn mới, hệ thống giữ nguồn cũ. Tên webcam có sẵn là cấu hình gợi ý; chỉ số thiết bị có thể khác trên mỗi máy.', 'If the new source cannot connect, the system keeps the old one. Built-in webcam names are suggested presets; device indexes may differ per machine.')}</p>
      </form>
      <section className="bg-surface rounded-xl border border-outline-variant p-5" aria-label={t('Xem camera hiện tại', 'Current camera view')}>
        <div className="flex items-center justify-between gap-3 mb-4">
          <h2 className="font-semibold text-primary">{t('Hình ảnh hiện tại', 'Current picture')} · {camera.name}</h2>
          <span className={`text-xs font-semibold ${online ? 'text-primary' : 'text-error'}`}>{online ? t('Có tín hiệu', 'Signal OK') : t('Mất tín hiệu', 'No signal')}</span>
        </div>
        {online && !previewError ? <img key={`${camera.current}-${previewVersion}`} className="w-full rounded-lg bg-primary aspect-video object-contain"
          src={`${API_BASE_URL}/guard/video_feed?token=${encodeURIComponent(token)}&gate=${encodeURIComponent(gate)}`}
          alt={`Camera ${camera.name}`} onError={() => setPreviewError(true)} />
          : <div className="bg-surface-container-low rounded-lg p-8 text-center text-sm text-on-surface-variant">{online ? t('Không tải được hình ảnh xem trước.', 'Could not load the preview.') : t('Chưa nhận được hình ảnh mới từ camera.', 'No new picture from the camera yet.')}</div>}
        <div className="flex items-center justify-between mt-3 gap-3 text-xs text-on-surface-variant">
          <span>{health.last_frame_age_sec != null ? t(`Khung hình gần nhất: ${health.last_frame_age_sec.toFixed(1)} giây trước`, `Last frame: ${health.last_frame_age_sec.toFixed(1)} s ago`) : t('Đang chờ khung hình', 'Waiting for a frame')}</span>
          <button type="button" className="text-primary underline py-2" onClick={() => { setPreviewError(false); setPreviewVersion(n => n + 1); }}>{t('Tải lại hình', 'Reload picture')}</button>
        </div>
        <a href="/admin/roi" className="inline-block mt-3 text-sm text-primary underline">{t('Kiểm tra vùng nhận diện ROI', 'Check the ROI detection zone')}</a>
      </section>
    </div>
  );
}
