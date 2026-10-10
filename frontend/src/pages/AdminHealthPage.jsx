import { useState, useEffect, useCallback } from 'react';
import client from '../api/client';
import { useLang } from '../i18n/LanguageContext';

function StatusDot({ ok, label }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`w-3 h-3 rounded-full ${ok ? 'bg-[#10b981]' : 'bg-[#c92035]'} shrink-0`}
        style={{ boxShadow: ok ? '0 0 6px #10b981' : '0 0 6px #c92035' }} />
      <span className="text-[12px] font-mono text-[#374151]">{label}</span>
    </div>
  );
}

function StatCell({ label, value, unit, color = 'text-[#374151]' }) {
  return (
    <div className="bg-[#f4f6f9] rounded-xl p-4 text-center">
      <div className={`text-2xl font-bold font-mono ${color}`}>{value ?? '—'}</div>
      <div className="text-[10px] font-mono text-[#6b7280] mt-1">{label}</div>
      {unit && <div className="text-[10px] font-mono text-[#9ca3af]">{unit}</div>}
    </div>
  );
}

export default function AdminHealthPage() {
  const { t } = useLang();
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [cleanupMsg, setCleanupMsg] = useState('');
  const [cleaning, setCleaning] = useState(false);
  const [previewDays, setPreviewDays] = useState('');
  const [previewData, setPreviewData] = useState(null);

  // Legacy top-level alias (backend still sends health.pipeline = main gate's status)
  // used for the header dot + stale-camera banner, which summarize across all gates.
  const p = health?.pipeline || {};
  const cameraStale = p.last_frame_age_sec != null && p.last_frame_age_sec > 5;

  const loadHealth = useCallback(async () => {
    try {
      const res = await client.get('/api/system/health');
      setHealth(res.data);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || err.message || t('Lỗi khi tải trạng thái', 'Error loading status'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, 5000);
    return () => clearInterval(interval);
  }, [loadHealth]);

  async function handleCleanup(days) {
    setCleaning(true);
    setCleanupMsg('');
    setPreviewData(null);
    try {
      const res = await client.post(`/api/system/snapshots/cleanup?older_than_days=${days}`);
      setCleanupMsg(t(`Đã xóa ${res.data.deleted_files} file, cập nhật ${res.data.updated_records} record.`, `Deleted ${res.data.deleted_files} files, updated ${res.data.updated_records} records.`));
      loadHealth();
    } catch (err) {
      setCleanupMsg(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
    } finally {
      setCleaning(false);
    }
  }

  async function handlePreview() {
    const days = parseInt(previewDays, 10);
    if (!days || days < 1 || days > 3650) return;
    try {
      const res = await client.get(`/api/system/snapshots/preview?older_than_days=${days}`);
      setPreviewData(res.data);
    } catch (err) {
      setPreviewData({ error: err.response?.data?.detail || err.message });
    }
  }

  if (loading && !health) {
    return (
      <div className="min-h-screen bg-[#ffffff] p-6 flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-[#6b7280] font-mono text-[12px]">{t('Đang kiểm tra...', 'Checking...')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <p className="font-mono text-xs uppercase tracking-wider text-[#c92035] mb-1">{t('Hạ tầng biên', 'Edge infrastructure')}</p>
        <div className="flex items-center gap-2 mb-1">
          <span className={`w-2.5 h-2.5 rounded-full ${p.running ? 'bg-[#10b981] animate-pulse' : 'bg-[#c92035]'}`} />
          <h1 className="text-2xl font-bold text-[#374151]">{t('Sức khỏe & Lưu trữ Hệ thống', 'System Health & Storage')}</h1>
        </div>
        <p className="text-sm text-[#6b7280] mb-6">{t('Giám sát pipeline nhận diện và dung lượng lưu trữ thật của server.', 'Monitor the recognition pipeline and the server\'s actual storage usage.')}</p>

        {error && (
          <div className="bg-[#f8d7dc] border border-[#f0aab3] text-[#7a1422] px-4 py-3 rounded-xl mb-4 text-[12px] font-mono">
            {error}
          </div>
        )}

        {cameraStale && (
          <div className="bg-[#fef3c7] border border-[#fde68a] text-[#92400e] px-4 py-3 rounded-xl mb-4 text-[12px] flex items-center gap-2">
            <span className="text-[16px]">⚠️</span>
            {t(`Camera có vẻ đứng (${p.last_frame_age_sec}s không có frame mới)`, `Camera seems frozen (no new frame for ${p.last_frame_age_sec}s)`)}
          </div>
        )}

        {/* Pipeline Status */}
        {health?.gates?.map((gate) => {
          const gp = gate.pipeline || {};
          const cameraStale = gp.last_frame_age_sec !== null && gp.last_frame_age_sec > 5;
          return (
            <div key={gate.id} className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider flex items-center gap-2">
                  <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                    <path d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Pipeline · {gate.name}
                </h2>
                <span className="font-mono text-[10px] text-[#6b7280]">{gate.id.toUpperCase()}</span>
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                <StatCell label="FPS" value={gp.fps != null ? gp.fps.toFixed(1) : '—'} unit="fps" />
                <StatCell label={t('Độ trễ xử lý', 'Processing latency')} value={gp.avg_process_latency_ms != null ? gp.avg_process_latency_ms : '—'} unit="ms" color="text-[#f59e0b]" />
                <StatCell
                  label={t('Tỉ lệ đọc biển số', 'Plate read rate')}
                  value={gp.plate_read_success_rate != null ? (gp.plate_read_success_rate * 100).toFixed(0) : '—'}
                  unit={gp.plate_read_success_rate != null ? '%' : t('chưa có dữ liệu', 'no data yet')}
                  color="text-[#10b981]"
                />
                <div className="bg-[#f4f6f9] rounded-xl p-4 text-center">
                  <div className="text-2xl font-bold font-mono text-[#374151]">{gp.frame_count ?? 0}</div>
                  <div className="text-[10px] font-mono text-[#6b7280] mt-1">{t('Tổng frames', 'Total frames')}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <StatusDot ok={gp.running} label={`Pipeline: ${gp.running ? t('ĐANG CHẠY', 'RUNNING') : t('ĐÃ DỪNG', 'STOPPED')}`} />
                <StatusDot ok={gp.thread_alive} label={`Thread: ${gp.thread_alive ? 'Alive' : 'Dead'}`} />
                <StatusDot ok={gp.camera_open} label={`Camera: ${gp.camera_open ? t('Mở', 'Open') : t('Đóng', 'Closed')}`} />
                <StatusDot ok={gp.last_frame_age_sec !== null && !cameraStale}
                  label={`Frame: ${gp.last_frame_age_sec !== null ? `${gp.last_frame_age_sec}s` : 'N/A'}`} />
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-mono text-[#6b7280]">
                    Detect: {gp.last_detection_age_sec !== null ? `${gp.last_detection_age_sec}s` : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-mono text-[#6b7280]">
                    Uptime: {gp.uptime_sec !== null ? `${Math.round(gp.uptime_sec / 60)} ${t('phút', 'min')}` : 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          );
        })}

        {/* Storage Stats */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
              <path d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            {t('Lưu trữ', 'Storage')}
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-4 bg-[#f4f6f9] rounded-xl">
              <div className="text-3xl font-bold font-mono text-[#c92035]">{health?.violations_today ?? 0}</div>
              <div className="text-[10px] font-mono text-[#6b7280] mt-1">{t('Vi phạm hôm nay', 'Violations today')}</div>
            </div>
            <div className="text-center p-4 bg-[#f4f6f9] rounded-xl">
              <div className="text-3xl font-bold font-mono text-[#374151]">{health?.snapshot_count ?? 0}</div>
              <div className="text-[10px] font-mono text-[#6b7280] mt-1">{t('Ảnh snapshot', 'Snapshots')}</div>
              <div className="text-[10px] font-mono text-[#9ca3af]">{health?.snapshot_size_mb ?? 0} MB</div>
            </div>
            <div className="text-center p-4 bg-[#f4f6f9] rounded-xl">
              <div className="text-3xl font-bold font-mono text-[#10b981]">{health?.db_size_mb ?? 0} MB</div>
              <div className="text-[10px] font-mono text-[#6b7280] mt-1">{t('Dung lượng DB', 'DB size')}</div>
            </div>
          </div>
        </div>

        {/* Disk Usage — Đợt 2, Bước 5 */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
              <path d="M3 7h18M3 7v10a2 2 0 002 2h14a2 2 0 002-2V7M3 7l2-4h14l2 4M10 11v4M14 11v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {t('Dung lượng đĩa', 'Disk usage')}
          </h2>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <StatCell
              label={t('Tổng', 'Total')}
              value={health?.disk_total_mb != null ? Math.round(health.disk_total_mb) : '—'}
              unit="MB"
            />
            <StatCell
              label={t('Đã dùng', 'Used')}
              value={health?.disk_used_mb != null ? Math.round(health.disk_used_mb) : '—'}
              unit="MB"
              color="text-[#f59e0b]"
            />
            <StatCell
              label={t('Còn trống', 'Free')}
              value={health?.disk_free_mb != null ? Math.round(health.disk_free_mb) : '—'}
              unit="MB"
              color="text-[#10b981]"
            />
          </div>
          {/* Breakdown theo extension (Đợt 2, Bước 5) */}
          {health?.storage_breakdown && (
            <div className="bg-[#f4f6f9] rounded-xl p-4">
              <div className="text-[10px] font-mono text-[#6b7280] uppercase tracking-wider mb-2">
                {t('Phân bổ theo loại file', 'Breakdown by file type')}
              </div>
              <div className="space-y-1.5">
                {(() => {
                  const b = health.storage_breakdown;
                  const rows = [
                    { key: 'jpg', label: t('Ảnh snapshot (.jpg)', 'Snapshots (.jpg)'), color: 'text-[#374151]' },
                    { key: 'mp4', label: t('Clip vi phạm (.mp4)', 'Violation clips (.mp4)'), color: 'text-[#c92035]' },
                    { key: 'other', label: t('Khác', 'Other'), color: 'text-[#6b7280]' },
                  ];
                  return rows.map(r => (
                    <div key={r.key} className="flex items-center justify-between text-[12px] font-mono">
                      <span className={r.color}>{r.label}</span>
                      <span className="text-[#374151]">
                        <strong>{(b[r.key]?.count ?? 0)}</strong> {t('file', 'files')} · <strong>{(b[r.key]?.size_mb ?? 0).toFixed(2)}</strong> MB
                      </span>
                    </div>
                  ));
                })()}
              </div>
            </div>
          )}
        </div>

        {/* Cleanup */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-2 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
              <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {t('Dọn ảnh cũ', 'Clean up old images')}
          </h2>
          <p className="text-[12px] text-[#6b7280] mb-4">
            {t('Xóa file ảnh/video vi phạm cũ để giải phóng dung lượng. Record vi phạm vẫn giữ lại, chỉ null đường dẫn ảnh/video.', 'Delete old violation image/video files to free up space. Violation records are kept; only the image/video paths are cleared.')}
          </p>

          {/* Preview input */}
          <div className="flex items-center gap-3 mb-4">
            <input
              type="number"
              min="1"
              max="3650"
              placeholder={t('Số ngày tùy chỉnh', 'Custom number of days')}
              className="w-40 bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none"
              value={previewDays}
              onChange={e => setPreviewDays(e.target.value)}
            />
            <button
              onClick={handlePreview}
              className="flex items-center gap-1.5 bg-[#123b6d] hover:bg-[#0d2a4f] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
            >
              {t('Xem trước', 'Preview')}
            </button>
          </div>

          {/* Preview result */}
          {previewData && !previewData.error && (
            <div className="bg-[#fef3c7] border border-[#fcd34d] rounded-lg p-4 mb-4">
              <p className="text-[12px] font-mono text-[#92400e]">
                {t('Ảnh:', 'Images:')} <strong>{previewData.snapshot_count}</strong> {t('file', 'files')} ({previewData.snapshot_count * 0.1 > 1 ? `${(previewData.snapshot_count * 0.1).toFixed(1)}` : '&lt;1'} MB est.)
                · {t('Clip video:', 'Video clips:')} <strong>{previewData.clip_count}</strong> {t('file', 'files')}
              </p>
              <p className="text-[12px] font-mono text-[#92400e] mt-1">
                {t('Tổng cộng:', 'Total:')} <strong>{previewData.file_count}</strong> {t('file', 'files')} · <strong>{previewData.total_size_mb}</strong> MB
              </p>
              <button
                onClick={() => { handleCleanup(parseInt(previewDays, 10)); setPreviewData(null); }}
                disabled={cleaning}
                className="mt-2 bg-[#c92035] hover:bg-[#a0172b] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                {cleaning ? t('Đang xóa...', 'Deleting...') : t('Xác nhận xóa', 'Confirm delete')}
              </button>
            </div>
          )}
          {previewData?.error && (
            <p className="text-[12px] font-mono text-[#c92035] mb-4">{previewData.error}</p>
          )}

          {/* Preset buttons */}
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => handleCleanup(30)}
              disabled={cleaning}
              className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
            >
              &gt;30 {t('ngày', 'days')}
            </button>
            <button
              onClick={() => handleCleanup(90)}
              disabled={cleaning}
              className="flex items-center gap-1.5 bg-[#fde68a] hover:bg-[#f59e0b] hover:text-white text-[#92400e] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
            >
              &gt;90 {t('ngày', 'days')}
            </button>
            <button
              onClick={() => handleCleanup(180)}
              disabled={cleaning}
              className="flex items-center gap-1.5 bg-[#f8d7dc] hover:bg-[#c92035] hover:text-white text-[#7a1422] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
            >
              &gt;180 {t('ngày', 'days')}
            </button>
          </div>
          {cleaning && (
            <div className="mt-3 flex items-center gap-2 text-[#6b7280] text-[12px]">
              <div className="w-4 h-4 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin" />
              {t('Đang dọn...', 'Cleaning up...')}
            </div>
          )}
          {cleanupMsg && (
            <p className={`mt-3 text-[12px] font-mono ${(cleanupMsg.startsWith('Lỗi') || cleanupMsg.startsWith('Error')) ? 'text-[#c92035]' : 'text-[#10b981]'}`}>
              {cleanupMsg}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
