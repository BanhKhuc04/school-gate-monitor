import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import AlertBanner from '../components/AlertBanner';
import client, { API_BASE_URL } from '../api/client';
import { VIOLATION_LABELS } from '../utils/violationLabels';

const MAX_LOG_ITEMS = 12;

function formatClock(date) {
  return date.toLocaleTimeString('vi-VN', { hour12: false });
}

export default function GuardPage() {
  const { token, user } = useAuth();
  const [health, setHealth] = useState(null);
  const [clock, setClock] = useState(() => new Date());
  const [alertLog, setAlertLog] = useState([]);
  const idCounter = useRef(0);

  // Trạng thái pipeline/camera — cùng API health mà trang admin dùng, chỉ hiển thị tối giản cho bảo vệ.
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const res = await client.get('/api/system/health');
        if (!cancelled) setHealth(res.data);
      } catch {
        if (!cancelled) setHealth(null);
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleAlert = useCallback((data) => {
    idCounter.current += 1;
    setAlertLog((prev) => [{ ...data, _id: idCounter.current }, ...prev].slice(0, MAX_LOG_ITEMS));
  }, []);

  const pipelineOk = health?.pipeline?.running;
  const cameraOk = health?.pipeline?.camera_open;

  return (
    <div className="min-h-screen bg-primary text-inverse-on-surface flex flex-col">
      <AlertBanner token={token} onAlert={handleAlert} />

      {/* Status strip */}
      <div className="flex flex-wrap items-center gap-4 px-6 py-3 border-b border-white/10 font-mono text-xs">
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${pipelineOk ? 'bg-tertiary-fixed' : 'bg-error'}`} />
          PIPELINE: {pipelineOk ? 'ĐANG CHẠY' : health ? 'NGƯNG' : 'ĐANG KIỂM TRA...'}
        </span>
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${cameraOk ? 'bg-tertiary-fixed' : 'bg-error'}`} />
          CỔNG CHÍNH: {cameraOk ? 'ONLINE' : health ? 'OFFLINE' : '...'}
        </span>
        <span className="ml-auto text-on-primary-container">{user?.username} · {user?.role}</span>
        <span>{formatClock(clock)}</span>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4 p-4">
        {/* Video panel */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <h1 className="text-lg font-bold">Cổng Chính</h1>
            <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-primary-container text-on-primary-container">
              CAM_01
            </span>
          </div>
          <div className="relative rounded-xl overflow-hidden bg-primary-container border border-white/10">
            <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded bg-error/90 font-mono text-[11px] font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
              LIVE
            </div>
            {health?.pipeline?.last_frame_age_sec != null && (
              <div className="absolute top-3 right-3 z-10 px-2 py-1 rounded bg-black/50 font-mono text-[11px]">
                Độ trễ khung hình: {health.pipeline.last_frame_age_sec.toFixed(1)}s
              </div>
            )}
            <img
              src={`${API_BASE_URL}/guard/video_feed?token=${token}`}
              alt="Live camera feed"
              className="w-full h-auto block"
              style={{ maxHeight: 'calc(100vh - 220px)', objectFit: 'contain' }}
            />
          </div>
        </div>

        {/* Alert log panel */}
        <div className="flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider text-on-primary-container">
              Cảnh báo gần đây
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
                Chưa có cảnh báo nào trong phiên này.
              </div>
            ) : (
              alertLog.map((a) => (
                <div key={a._id} className="bg-primary-container rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-[11px] font-bold px-1.5 py-0.5 rounded bg-error text-on-error">
                      {VIOLATION_LABELS[a.violation_type] || a.violation_type}
                    </span>
                    <span className="font-mono text-[10px] text-on-primary-container">
                      {new Date(a.timestamp).toLocaleTimeString('vi-VN', { hour12: false })}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {a.snapshot_url && (
                      <img
                        src={`${API_BASE_URL}${a.snapshot_url}`}
                        alt="Ảnh chụp bằng chứng"
                        className="w-14 h-14 object-cover rounded border border-white/10 shrink-0"
                      />
                    )}
                    <span className="font-mono text-xs">
                      {a.plate_matched || a.plate_read || 'Không đọc được biển số'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
