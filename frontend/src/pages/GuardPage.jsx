import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import AlertBanner from '../components/AlertBanner';
import RecognitionLogPanel from '../components/RecognitionLogPanel';
import PlateReviewPanel from '../components/PlateReviewPanel';
import DebugOverlayControl from '../components/DebugOverlayControl';
import client, { API_BASE_URL } from '../api/client';
import { describeAlert, TONE_COLORS } from '../utils/alertDisplay';
import { useAudioLease } from '../utils/useAudioLease';
import { getVietnameseVoiceStatus } from '../utils/speak';
import { useLang, localeOf } from '../i18n/LanguageContext';

const MAX_LOG_ITEMS = 12;

export default function GuardPage() {
  const { token, user } = useAuth();
  const { lang, t } = useLang();
  const [health, setHealth] = useState(null);
  const [alertLog, setAlertLog] = useState([]);
  const [logTab, setLogTab] = useState('recognition');
  const [activeGate, setActiveGate] = useState('main');
  const [viewMode, setViewMode] = useState('single'); // 'single' | 'split'
  const [voiceStatus, setVoiceStatus] = useState({ supported: false, local: false, voice: null });
  // Nút "Chạy video test": 2 cổng cùng phát 2 video quay sẵn (chỉ admin bấm được).
  const [demo, setDemo] = useState(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState('');
  const idCounter = useRef(0);
  const lease = useAudioLease(activeGate);
  const isAdmin = user?.role === 'admin';

  // gates from API; null = chưa load (hoặc health = null); array = đã load
  const gates = health?.gates ?? null;
  const showGateSelector = gates !== null && gates.length > 1;
  const activeGateName = gates?.find(g => g.id === activeGate)?.name ?? t('Cổng Chính', 'Main gate');
  const activePipeline = gates?.find(g => g.id === activeGate)?.pipeline;
  const isSplit = showGateSelector && viewMode === 'split';

  // Độ trễ khung hình hiển thị trên video panel — cùng API health mà trang admin dùng.
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const res = await client.get('/api/system/health');
        if (!cancelled) setHealth(res.data);
      } catch {
        if (!cancelled) setHealth(null);
      }
      try {
        const res = await client.get('/api/demo');
        if (!cancelled) setDemo(res.data);
      } catch {
        if (!cancelled) setDemo(null);
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Voice readiness probe — surfaces "offline Vietnamese voice" state in the
  // banner area so the operator knows whether the speaker will talk even when
  // WAN is off.
  useEffect(() => {
    const probe = () => setVoiceStatus(getVietnameseVoiceStatus());
    probe();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = probe;
    }
    return () => {
      if ('speechSynthesis' in window) window.speechSynthesis.onvoiceschanged = null;
    };
  }, []);

  // Trong lúc chạy video test: cập nhật vị trí 2 video mỗi giây (xem độ lệch).
  const demoLive = Boolean(demo?.active || demo?.switching);
  useEffect(() => {
    if (!demoLive) return undefined;
    let cancelled = false;
    const id = setInterval(async () => {
      try {
        const res = await client.get('/api/demo');
        if (!cancelled) setDemo(res.data);
      } catch { /* the 5 s poll reports a lost backend */ }
    }, 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, [demoLive]);

  const handleAlert = useCallback((data) => {
    idCounter.current += 1;
    setAlertLog((prev) => [{ ...data, _id: idCounter.current }, ...prev].slice(0, MAX_LOG_ITEMS));
  }, []);

  async function toggleDemo() {
    setDemoBusy(true);
    setDemoError('');
    try {
      const res = await client.post(demo?.active ? '/api/demo/stop' : '/api/demo/start');
      setDemo(res.data);
      if (res.data.active) setViewMode('split'); // xem cả 2 video cùng lúc
    } catch (err) {
      setDemoError(err.response?.data?.detail || t('Không đổi được chế độ video test.', 'Could not switch test-video mode.'));
    } finally {
      setDemoBusy(false);
    }
  }

  const clock = (sec) => `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
  // Nhãn góc trái mỗi khung: LIVE, hoặc VIDEO TEST + vị trí đang phát của video đó.
  const badgeFor = (gateId) => {
    const g = demo?.gates?.[gateId];
    if (g?.playing) {
      return { label: g.position != null ? `VIDEO TEST · ${clock(g.position)}` : 'VIDEO TEST', className: 'bg-warning text-on-warning' };
    }
    if (demo?.active) return { label: t('ĐANG CHUYỂN…', 'SWITCHING…'), className: 'bg-warning/70 text-on-warning' };
    return { label: 'LIVE', className: 'bg-error/90' };
  };

  return (
    <div className="min-h-screen bg-primary text-inverse-on-surface flex flex-col">
      <AlertBanner token={token} onAlert={handleAlert} gate={activeGate}
        audioEnabled={lease.enabled} audioClientId={lease.clientId} />

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4 p-4">
        {/* Video panel */}
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {showGateSelector && !isSplit ? (
              <select
                value={activeGate}
                onChange={e => setActiveGate(e.target.value)}
                className="text-lg font-bold bg-transparent border border-white/30 rounded px-2 py-0.5 text-inverse-on-surface cursor-pointer"
              >
                {gates.map(g => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
            ) : (
              <h1 className="text-lg font-bold">{isSplit ? t('Tất cả camera', 'All cameras') : activeGateName}</h1>
            )}
            {!isSplit && (
              <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-primary-container text-on-primary-container">
                {`CAM_${String(Math.max(0, gates?.findIndex(g => g.id === activeGate) ?? 0) + 1).padStart(2, '0')}`}
              </span>
            )}
            <button
              type="button"
              onClick={lease.toggle}
              disabled={lease.busy}
              data-testid="audio-toggle"
              className={`font-mono text-[11px] px-2.5 py-1 rounded border ${
                lease.enabled
                  ? 'bg-success/90 border-success text-on-success'
                  : 'bg-transparent border-white/30 text-inverse-on-surface/80 hover:bg-white/10'
              }`}
              title={lease.enabled ? t('Bấm để nhường quyền loa', 'Click to release the speaker') : t('Bấm để xin quyền phát loa (cần thao tác của người dùng)', 'Click to take over the speaker (needs a user click)')}
            >
              {lease.busy ? '…' : lease.enabled ? t('🔊 Loa: BẬT', '🔊 Speaker: ON') : t('🔈 Loa: TẮT', '🔈 Speaker: OFF')}
            </button>
            <span
              className={`font-mono text-[11px] px-2 py-0.5 rounded ${
                voiceStatus.local
                  ? 'bg-success/80 text-on-success'
                  : voiceStatus.supported
                    ? 'bg-warning/90 text-on-warning'
                    : 'bg-error/90 text-on-error'
              }`}
              title={voiceStatus.voice
                ? `${t('Giọng', 'Voice')}: ${voiceStatus.voice}${voiceStatus.local ? t(' (local, chạy offline)', ' (local, works offline)') : t(' (remote — cần Internet)', ' (remote — needs Internet)')}`
                : t('Trình duyệt không hỗ trợ Web Speech API', 'This browser does not support the Web Speech API')}
            >
              {voiceStatus.local
                ? '🇻🇳 VI-local'
                : voiceStatus.supported
                  ? 'VI-remote'
                  : 'VI-n/a'}
            </span>
            {lease.error && (
              <span className="text-[11px] text-error ml-1">{lease.error}</span>
            )}
            {isAdmin && demo && (
              <button
                type="button"
                onClick={toggleDemo}
                disabled={demoBusy || (!demo.active && !demo.available)}
                data-testid="demo-toggle"
                className={`font-mono text-[11px] font-bold px-2.5 py-1 rounded border disabled:opacity-50 ${
                  demo.active
                    ? 'bg-warning border-warning text-on-warning'
                    : 'bg-transparent border-white/30 text-inverse-on-surface hover:bg-white/10'
                }`}
                title={demo.available || demo.active
                  ? t('Hai cổng cùng phát 2 video quay sẵn (camera trước + camera sau) để kiểm tra hệ thống', 'Both gates play 2 pre-recorded videos (front + rear camera) to test the system')
                  : t(`Thiếu video test: ${(demo.missing || []).join(', ')} (chép vào data/demo_videos/)`, `Missing test videos: ${(demo.missing || []).join(', ')} (copy them into data/demo_videos/)`)}
              >
                {demoBusy ? '…' : demo.active ? t('■ Dừng video test', '■ Stop test video') : t('▶ Chạy video test', '▶ Run test video')}
              </button>
            )}
            {demoError && (
              <span className="text-[11px] text-error ml-1">{demoError}</span>
            )}
            {showGateSelector && (
              <div className="ml-auto flex items-center rounded-lg border border-white/30 overflow-hidden text-[11px] font-mono">
                <button
                  type="button"
                  onClick={() => setViewMode('single')}
                  className={`px-2.5 py-1 ${viewMode === 'single' ? 'bg-primary-container text-on-primary-container' : 'text-inverse-on-surface/70'}`}
                >
                  {t('1 cổng', '1 gate')}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('split')}
                  className={`px-2.5 py-1 ${viewMode === 'split' ? 'bg-primary-container text-on-primary-container' : 'text-inverse-on-surface/70'}`}
                >
                  {t('Song song', 'Side by side')}
                </button>
              </div>
            )}
          </div>
          {demo?.active && (
            <div data-testid="demo-banner" className="mb-2 rounded-lg bg-warning text-on-warning px-3 py-2 text-sm font-bold">
              {t('ĐANG CHẠY VIDEO TEST — hình là video quay sẵn, không phải camera thật. Vi phạm ghi nhận lúc này có nhãn TEST.', 'TEST VIDEO RUNNING — the picture is pre-recorded video, not a real camera. Violations logged now are tagged TEST.')}
              <span data-testid="demo-sync" className="block font-mono text-[12px] font-semibold mt-0.5">
                {demo.switching
                  ? t('Đang chuyển 2 camera sang video test…', 'Switching both cameras to test video…')
                  : demo.offset_sec != null
                    ? t(`2 video đồng bộ: camera trước ${clock(demo.gates.main?.position ?? 0)} · camera sau ${clock(demo.gates.secondary?.position ?? 0)} · lệch ${demo.offset_sec.toFixed(2)} giây`,
                      `2 videos in sync: front camera ${clock(demo.gates.main?.position ?? 0)} · rear camera ${clock(demo.gates.secondary?.position ?? 0)} · offset ${demo.offset_sec.toFixed(2)} s`)
                    : t('Cả 2 camera đang phát video test.', 'Both cameras are playing test video.')}
              </span>
            </div>
          )}
          {!demo?.active && demo?.switching && (
            <div className="mb-2 rounded-lg bg-primary-container text-on-primary-container px-3 py-2 text-sm">
              {t('Đang chuyển 2 cổng về camera thật…', 'Switching both gates back to the real cameras…')}
            </div>
          )}
          {!isSplit && <DebugOverlayControl key={activeGate} gate={activeGate} name={activeGateName} />}

          {isSplit ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {gates.map(g => (
                <div key={g.id}>
                  <DebugOverlayControl gate={g.id} name={g.name} />
                  <div className="relative rounded-xl overflow-hidden bg-primary-container border border-white/10">
                  <div className={`absolute top-2 left-2 z-10 flex items-center gap-1.5 px-2 py-1 rounded font-mono text-[10px] font-bold ${badgeFor(g.id).className}`}>
                    <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                    {badgeFor(g.id).label}
                  </div>
                  <div className="absolute top-2 right-2 z-10 px-2 py-1 rounded bg-black/50 font-mono text-[10px]">
                    {g.name}
                    {g.pipeline?.last_frame_age_sec != null && ` · ${g.pipeline.last_frame_age_sec.toFixed(1)}s`}
                  </div>
                  <img
                    src={`${API_BASE_URL}/guard/video_feed?token=${token}&gate=${g.id}`}
                    alt={t(`Camera trực tiếp — ${g.name}`, `Live camera feed — ${g.name}`)}
                    className="w-full h-auto block"
                    style={{ maxHeight: 'calc(100vh - 260px)', objectFit: 'contain' }}
                  />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="relative rounded-xl overflow-hidden bg-primary-container border border-white/10">
              <div className={`absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded font-mono text-[11px] font-bold ${badgeFor(activeGate).className}`}>
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                {badgeFor(activeGate).label}
              </div>
              {activePipeline?.last_frame_age_sec != null && (
                <div className="absolute top-3 right-3 z-10 px-2 py-1 rounded bg-black/50 font-mono text-[11px]">
                  {t('Độ trễ khung hình', 'Frame delay')}: {activePipeline.last_frame_age_sec.toFixed(1)}s
                </div>
              )}
              <img
                src={`${API_BASE_URL}/guard/video_feed?token=${token}&gate=${activeGate}`}
                alt={t('Camera trực tiếp', 'Live camera feed')}
                className="w-full h-auto block"
                style={{ maxHeight: 'calc(100vh - 220px)', objectFit: 'contain' }}
              />
            </div>
          )}
        </div>

        {/* Alert log panel */}
        <div className="flex flex-col min-h-0">
          <div role="tablist" aria-label={t('Nhật ký trực tiếp', 'Live log')} className="flex flex-wrap gap-2 mb-3">
            <button role="tab" aria-selected={logTab==='recognition'} onClick={()=>setLogTab('recognition')} className="rounded bg-primary-container text-on-primary-container px-3 py-2 text-sm">{t('Nhận diện trực tiếp', 'Live recognition')}</button>
            <button role="tab" aria-selected={logTab==='plate-review'} onClick={()=>setLogTab('plate-review')} className="rounded bg-primary-container text-on-primary-container px-3 py-2 text-sm">{t('Duyệt biển', 'Plate review')}</button>
            <button role="tab" aria-selected={logTab==='alerts'} onClick={()=>setLogTab('alerts')} className="rounded bg-primary-container text-on-primary-container px-3 py-2 text-sm">{t('Cảnh báo', 'Alerts')}</button>
          </div>
          <div hidden={logTab!=='recognition'}><RecognitionLogPanel key={activeGate} gate={activeGate}/></div>
          {logTab==='plate-review' && <PlateReviewPanel key={activeGate} gate={activeGate} role={user?.role}/>}
          <div hidden={logTab!=='alerts'}>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider text-on-primary-container">
              {t('Cảnh báo gần đây', 'Recent alerts')}
            </h2>
            {alertLog.length > 0 && (
              <span className="font-mono text-[11px] px-2 py-0.5 rounded-full bg-error text-on-error">
                {alertLog.length}
              </span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {alertLog.length === 0 ? (
              <div className="text-sm text-on-primary-container bg-primary-container rounded-lg p-4">
                {t('Chưa có cảnh báo nào trong phiên này.', 'No alerts in this session yet.')}
              </div>
            ) : (
              alertLog.map((a) => {
                const shown = describeAlert(a, lang);
                return (
                <div key={a._id} className="bg-primary-container rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[11px] font-bold px-1.5 py-0.5 rounded text-white"
                      style={{ backgroundColor: TONE_COLORS[shown.tone] }}>
                      {shown.title}
                    </span>
                    <span className="font-mono text-[10px] text-on-primary-container">
                      {new Date(a.timestamp).toLocaleTimeString(localeOf(lang), { hour12: false })}
                    </span>
                  </div>
                  {a.snapshot_url && (
                    <img
                      src={`${API_BASE_URL}${a.snapshot_url}`}
                      alt={t('Ảnh chụp bằng chứng', 'Evidence snapshot')}
                      className="w-full h-auto max-h-48 object-contain rounded border border-white/10 bg-black/20 mb-2"
                    />
                  )}
                  <span className="font-mono text-xs">
                    {shown.detail}
                  </span>
                </div>
                );
              })
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
