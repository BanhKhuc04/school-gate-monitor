import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../auth/AuthContext';
import client, { API_BASE_URL } from '../api/client';

/**
 * Vẽ vùng nhận diện (ROI) đa giác trên khung hình camera — vật thể có tâm
 * nằm ngoài vùng này sẽ bị bỏ qua khi detect (xem app/cv/roi.py).
 * Click để thêm điểm, "Lưu vùng" gửi lên server, "Xoá vùng" tắt ROI (detect
 * toàn khung hình như cũ).
 */
export default function AdminRoiPage() {
  const { token } = useAuth();
  const [gates, setGates] = useState([]);
  const [activeGate, setActiveGate] = useState('main');
  const [points, setPoints] = useState([]); // [{x,y}] tỉ lệ 0..1
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
  }, [activeGate]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (points.length === 0) return;

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
  }, [points]);

  useEffect(() => {
    draw();
    window.addEventListener('resize', draw);
    return () => window.removeEventListener('resize', draw);
  }, [draw]);

  function handleCanvasClick(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPoints(prev => [...prev, { x, y }]);
    setMsg('');
  }

  function handleUndo() {
    setPoints(prev => prev.slice(0, -1));
  }

  async function handleSave() {
    if (points.length > 0 && points.length < 3) {
      setMsg('Lỗi: cần ít nhất 3 điểm để tạo vùng.');
      return;
    }
    setSaving(true);
    setMsg('');
    try {
      const body = { points: points.map(p => [p.x, p.y]) };
      await client.post(`/api/roi/${activeGate}`, body);
      setMsg('Đã lưu vùng nhận diện.');
    } catch (err) {
      setMsg('Lỗi: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    setSaving(true);
    setMsg('');
    try {
      await client.post(`/api/roi/${activeGate}`, { points: [] });
      setPoints([]);
      setMsg('Đã xoá vùng — detect toàn khung hình.');
    } catch (err) {
      setMsg('Lỗi: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-3xl mx-auto">
        <p className="font-mono text-xs uppercase tracking-wider text-[#c92035] mb-1">Hạ tầng biên</p>
        <h1 className="text-2xl font-bold text-[#374151] mb-1">Vùng nhận diện (ROI)</h1>
        <p className="text-sm text-[#6b7280] mb-6">
          Click lên khung hình để vẽ vùng — vật thể có tâm nằm ngoài vùng này sẽ không bị bắt lỗi. Để trống = detect toàn khung hình.
        </p>

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
            disabled={points.length === 0}
            className="bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            Hoàn tác điểm cuối
          </button>
          <button
            onClick={handleClear}
            disabled={saving}
            className="bg-[#f8d7dc] hover:bg-[#c92035] hover:text-white text-[#7a1422] text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors disabled:opacity-50"
          >
            Xoá vùng
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-[#c92035] hover:bg-[#a0172b] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            {saving ? 'Đang lưu...' : 'Lưu vùng'}
          </button>
        </div>

        {msg && (
          <p className={`mt-3 text-[12px] font-mono ${msg.includes('Lỗi') ? 'text-[#c92035]' : 'text-[#10b981]'}`}>
            {msg}
          </p>
        )}
      </div>
    </div>
  );
}
