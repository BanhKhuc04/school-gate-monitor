import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../auth/AuthContext';
import client, { API_BASE_URL } from '../api/client';
import { useLang } from '../i18n/LanguageContext';

/**
 * Vẽ vùng nhận diện (ROI) đa giác trên khung hình camera — vật thể có tâm
 * nằm ngoài vùng này sẽ bị bỏ qua khi detect (xem app/cv/roi.py).
 * Click để thêm điểm, "Lưu vùng" gửi lên server, "Xoá vùng" tắt ROI (detect
 * toàn khung hình như cũ).
 */
export default function AdminRoiPage() {
  const { token } = useAuth();
  const { t } = useLang();
  const [gates, setGates] = useState([]);
  const [activeGate, setActiveGate] = useState('main');
  const [mode, setMode] = useState('roi'); // 'roi' | 'line'
  const [points, setPoints] = useState([]); // [{x,y}] tỉ lệ 0..1 — vùng ROI
  const [linePoints, setLinePoints] = useState([]); // tối đa 2 điểm {x,y} — vạch mốc
  const [msg, setMsg] = useState('');
  const [saving, setSaving] = useState(false);
  const containerRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    client.get('/api/system/health')
      .then(res => setGates(res.data?.gates ?? []))
      .catch(() => setGates([]));
  }, []);

  useEffect(() => {
    setMsg('');
    client.get(`/api/roi/${activeGate}`)
      .then(res => {
        const saved = res.data?.points ?? [];
        setPoints(saved.map(([x, y]) => ({ x, y })));
      })
      .catch(() => setPoints([]));
    client.get(`/api/roi/${activeGate}/line`)
      .then(res => {
        const line = res.data?.line;
        setLinePoints(line ? [{ x: line[0], y: line[1] }, { x: line[2], y: line[3] }] : []);
      })
      .catch(() => setLinePoints([]));
  }, [activeGate]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (points.length > 0) {
      ctx.strokeStyle = '#00c8ff';
      ctx.fillStyle = 'rgba(0, 200, 255, 0.15)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((p, i) => {
        const px = p.x * canvas.width, py = p.y * canvas.height;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      if (points.length >= 3) ctx.closePath();
      ctx.fill();
      ctx.stroke();

      points.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x * canvas.width, p.y * canvas.height, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#00c8ff';
        ctx.fill();
      });
    }

    if (linePoints.length > 0) {
      ctx.strokeStyle = '#ff9900';
      ctx.lineWidth = 3;
      if (linePoints.length === 2) {
        ctx.beginPath();
        ctx.moveTo(linePoints[0].x * canvas.width, linePoints[0].y * canvas.height);
        ctx.lineTo(linePoints[1].x * canvas.width, linePoints[1].y * canvas.height);
        ctx.stroke();
      }
      linePoints.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x * canvas.width, p.y * canvas.height, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#ff9900';
        ctx.fill();
      });
    }
  }, [points, linePoints]);

  useEffect(() => {
    draw();
    window.addEventListener('resize', draw);
    return () => window.removeEventListener('resize', draw);
  }, [draw]);

  function handleCanvasClick(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setMsg('');
    if (mode === 'line') {
      // Click thứ 3 trở đi → bắt đầu vẽ lại từ đầu (chỉ giữ tối đa 2 điểm)
      setLinePoints(prev => (prev.length >= 2 ? [{ x, y }] : [...prev, { x, y }]));
      return;
    }
    setPoints(prev => [...prev, { x, y }]);
  }

  function handleUndo() {
    if (mode === 'line') {
      setLinePoints(prev => prev.slice(0, -1));
      return;
    }
    setPoints(prev => prev.slice(0, -1));
  }

  async function handleSave() {
    if (mode === 'line') {
      if (linePoints.length !== 2) {
        setMsg(t('Lỗi: cần đúng 2 điểm để tạo vạch mốc.', 'Error: exactly 2 points are needed for the gate line.'));
        return;
      }
      setSaving(true);
      setMsg('');
      try {
        const line = [linePoints[0].x, linePoints[0].y, linePoints[1].x, linePoints[1].y];
        await client.post(`/api/roi/${activeGate}/line`, { line });
        setMsg(t('Đã lưu vạch mốc.', 'Gate line saved.'));
      } catch (err) {
        setMsg(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
      } finally {
        setSaving(false);
      }
      return;
    }
    if (points.length > 0 && points.length < 3) {
      setMsg(t('Lỗi: cần ít nhất 3 điểm để tạo vùng.', 'Error: at least 3 points are needed for a zone.'));
      return;
    }
    setSaving(true);
    setMsg('');
    try {
      const body = { points: points.map(p => [p.x, p.y]) };
      await client.post(`/api/roi/${activeGate}`, body);
      setMsg(t('Đã lưu vùng nhận diện.', 'Detection zone saved.'));
    } catch (err) {
      setMsg(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    if (mode === 'line') {
      setSaving(true);
      setMsg('');
      try {
        await client.delete(`/api/roi/${activeGate}/line`);
        setLinePoints([]);
        setMsg(t('Đã xoá vạch mốc.', 'Gate line cleared.'));
      } catch (err) {
        setMsg(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
      } finally {
        setSaving(false);
      }
      return;
    }
    setSaving(true);
    setMsg('');
    try {
      await client.post(`/api/roi/${activeGate}`, { points: [] });
      setPoints([]);
      setMsg(t('Đã xoá vùng — detect toàn khung hình.', 'Zone cleared — detecting on the full frame.'));
    } catch (err) {
      setMsg(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-3xl mx-auto">
        <p className="font-mono text-xs uppercase tracking-wider text-[#c92035] mb-1">{t('Hạ tầng biên', 'Edge infrastructure')}</p>
        <h1 className="text-2xl font-bold text-[#374151] mb-1">{t('Vùng nhận diện (ROI) & Vạch mốc', 'Detection zone (ROI) & Gate line')}</h1>
        <p className="text-sm text-[#6b7280] mb-4">
          {mode === 'roi'
            ? t('Click lên khung hình để vẽ vùng — vật thể có tâm nằm ngoài vùng này sẽ không bị bắt lỗi. Để trống = detect toàn khung hình.', 'Click on the frame to draw a zone — objects whose centre is outside it are not flagged. Leave empty = detect on the full frame.')
            : t('Click 2 điểm để vẽ vạch cổng (màu cam). Hệ thống dùng vạch này để theo dõi xe đi qua cổng.', 'Click 2 points to draw the gate line (orange). The system uses it to track bikes passing through the gate.')}
        </p>

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode('roi')}
            aria-pressed={mode === 'roi'}
            className={`text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors ${mode === 'roi' ? 'bg-[#123B6D] text-white' : 'bg-[#f4f6f9] text-[#374151] hover:bg-[#eceff3]'}`}
          >
            {t('Vùng nhận diện (ROI)', 'Detection zone (ROI)')}
          </button>
          <button
            onClick={() => setMode('line')}
            aria-pressed={mode === 'line'}
            className={`text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors ${mode === 'line' ? 'bg-[#ff9900] text-white' : 'bg-[#f4f6f9] text-[#374151] hover:bg-[#eceff3]'}`}
          >
            {t('Vạch mốc (cảnh báo sớm)', 'Gate line (early warning)')}
          </button>
        </div>

        {gates.length > 1 && (
          <select
            value={activeGate}
            onChange={e => setActiveGate(e.target.value)}
            className="mb-4 bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none"
          >
            {gates.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        )}

        <div
          ref={containerRef}
          className="relative w-full bg-black rounded-xl overflow-hidden"
          style={{ aspectRatio: '16 / 9' }}
        >
          <img
            src={`${API_BASE_URL}/guard/video_feed?token=${token}&gate=${activeGate}`}
            alt="camera feed"
            className="absolute inset-0 w-full h-full object-contain"
          />
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className="absolute inset-0 w-full h-full cursor-crosshair"
          />
        </div>

        <div className="flex flex-wrap gap-3 mt-4">
          <button
            onClick={handleUndo}
            disabled={(mode === 'line' ? linePoints.length : points.length) === 0}
            className="bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            {t('Hoàn tác điểm cuối', 'Undo last point')}
          </button>
          <button
            onClick={handleClear}
            disabled={saving}
            className="bg-[#f8d7dc] hover:bg-[#c92035] hover:text-white text-[#7a1422] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            {mode === 'line' ? t('Xoá vạch mốc', 'Clear gate line') : t('Xoá vùng', 'Clear zone')}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-[#c92035] hover:bg-[#a0172b] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            {saving ? t('Đang lưu...', 'Saving...') : mode === 'line' ? t('Lưu vạch mốc', 'Save gate line') : t('Lưu vùng', 'Save zone')}
          </button>
        </div>

        {msg && (
          <p className={`mt-3 text-[12px] font-mono ${(msg.includes('Lỗi') || msg.includes('Error')) ? 'text-[#c92035]' : 'text-[#10b981]'}`}>
            {msg}
          </p>
        )}
      </div>
    </div>
  );
}
