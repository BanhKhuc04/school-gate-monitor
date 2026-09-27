import { useState, useEffect } from 'react';
import client from '../api/client';

export default function AdminHealthPage() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [cleanupMsg, setCleanupMsg] = useState('');
  const [cleaning, setCleaning] = useState(false);

  async function loadHealth() {
    try {
      const res = await client.get('/api/system/health');
      setHealth(res.data);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Lỗi khi tải trạng thái');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  async function handleCleanup(days) {
    if (!confirm(`Xóa ảnh vi phạm cũ hơn ${days} ngày?`)) return;
    setCleaning(true);
    setCleanupMsg('');
    try {
      const res = await client.post(`/api/system/snapshots/cleanup?older_than_days=${days}`);
      setCleanupMsg(`Đã xóa ${res.data.deleted_files} file, cập nhật ${res.data.updated_records} record.`);
      loadHealth();
    } catch (err) {
      setCleanupMsg('Lỗi khi dọn ảnh: ' + (err.response?.data?.detail || err.message));
    } finally {
      setCleaning(false);
    }
  }

  function StatusDot({ ok, label }) {
    return (
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-3 h-3 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`}
          style={{ boxShadow: ok ? '0 0 6px #22c55e' : '0 0 6px #ef4444' }}
        />
        <span className="text-sm text-gray-700">{label}</span>
      </div>
    );
  }

  function WarningBanner({ message }) {
    if (!message) return null;
    return (
      <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 px-4 py-3 rounded-lg text-sm">
        ⚠️ {message}
      </div>
    );
  }

  if (loading && !health) {
    return (
      <div className="min-h-screen bg-gray-100 p-6 flex items-center justify-center">
        <div className="text-gray-500">Đang tải...</div>
      </div>
    );
  }

  const p = health?.pipeline || {};
  const cameraStale = p.last_frame_age_sec !== null && p.last_frame_age_sec > 5;

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Sức khỏe hệ thống</h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>
        )}

        {cameraStale && (
          <WarningBanner message={`Camera có vẻ đứng (${p.last_frame_age_sec}s không có frame mới)`} />
        )}

        {/* Pipeline Status */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">Pipeline</h2>
          <div className="grid grid-cols-2 gap-4">
            <StatusDot ok={p.running} label={`Pipeline: ${p.running ? 'Đang chạy' : 'Đã dừng'}`} />
            <StatusDot ok={p.thread_alive} label={`Thread: ${p.thread_alive ? 'Alive' : 'Dead'}`} />
            <StatusDot ok={p.camera_open} label={`Camera: ${p.camera_open ? 'Mở' : 'Đóng/Không có'}`} />
            <div className="flex items-center gap-2">
              <span className={`inline-block w-3 h-3 rounded-full ${p.last_frame_age_sec !== null && !cameraStale ? 'bg-green-500' : 'bg-red-500'}`}
                style={{ boxShadow: p.last_frame_age_sec !== null && !cameraStale ? '0 0 6px #22c55e' : '0 0 6px #ef4444' }} />
              <span className="text-sm text-gray-700">
                Frame: {p.last_frame_age_sec !== null ? `${p.last_frame_age_sec}s` : 'N/A'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">
                Detect: {p.last_detection_age_sec !== null ? `${p.last_detection_age_sec}s` : 'N/A'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">
                Frames: {p.frame_count ?? 0}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">
                Uptime: {p.uptime_sec !== null ? `${Math.round(p.uptime_sec / 60)} phút` : 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* Storage */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">Lưu trữ</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center p-4 bg-gray-50 rounded-lg">
              <div className="text-2xl font-bold text-blue-600">{health?.violations_today ?? 0}</div>
              <div className="text-xs text-gray-500 mt-1">Vi phạm hôm nay</div>
            </div>
            <div className="text-center p-4 bg-gray-50 rounded-lg">
              <div className="text-2xl font-bold text-gray-700">{health?.snapshot_count ?? 0}</div>
              <div className="text-xs text-gray-500 mt-1">Ảnh snapshot ({health?.snapshot_size_mb ?? 0} MB)</div>
            </div>
            <div className="text-center p-4 bg-gray-50 rounded-lg">
              <div className="text-2xl font-bold text-green-600">{health?.db_size_mb ?? 0} MB</div>
              <div className="text-xs text-gray-500 mt-1">Dung lượng DB</div>
            </div>
          </div>
        </div>

        {/* Cleanup */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-base font-semibold text-gray-700 mb-3">Dọn ảnh cũ</h2>
          <p className="text-sm text-gray-500 mb-4">
            Xóa file ảnh vi phạm cũ để giải phóng dung lượng. Record vi phạm vẫn giữ lại, chỉ null đường dẫn ảnh.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => handleCleanup(30)}
              disabled={cleaning}
              className="bg-yellow-500 hover:bg-yellow-600 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Dọn ảnh &gt;30 ngày
            </button>
            <button
              onClick={() => handleCleanup(90)}
              disabled={cleaning}
              className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Dọn ảnh &gt;90 ngày
            </button>
            <button
              onClick={() => handleCleanup(180)}
              disabled={cleaning}
              className="bg-red-500 hover:bg-red-600 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Dọn ảnh &gt;180 ngày
            </button>
          </div>
          {cleaning && <p className="text-sm text-gray-500 mt-2">Đang dọn...</p>}
          {cleanupMsg && (
            <p className={`text-sm mt-2 ${cleanupMsg.includes('Lỗi') ? 'text-red-600' : 'text-green-600'}`}>
              {cleanupMsg}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
