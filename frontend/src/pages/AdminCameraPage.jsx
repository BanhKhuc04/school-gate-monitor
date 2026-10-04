import { useState, useEffect } from 'react';
import client from '../api/client';

/**
 * Đổi nguồn camera cho từng cổng (webcam index, file video, hoặc rtsp:// URL).
 * Lưu xong server tự restart pipeline cổng đó — mất vài giây nạp lại model.
 */
export default function AdminCameraPage() {
  const [gates, setGates] = useState([]);
  const [presets, setPresets] = useState([]);
  const [drafts, setDrafts] = useState({}); // {gate_id: source đang nhập}
  const [savingGate, setSavingGate] = useState(null);
  const [msg, setMsg] = useState({}); // {gate_id: text}

  useEffect(() => {
    client.get('/api/camera')
      .then(res => {
        const list = res.data?.gates ?? [];
        setGates(list);
        setPresets(res.data?.presets ?? []);
        setDrafts(Object.fromEntries(list.map(g => [g.id, g.source])));
      })
      .catch(err => setMsg({ _: 'Lỗi: ' + (err.response?.data?.detail || err.message) }));
  }, []);

  async function handleSave(gateId) {
    const source = (drafts[gateId] ?? '').trim();
    if (!source) {
      setMsg(m => ({ ...m, [gateId]: 'Lỗi: nguồn camera không được để trống.' }));
      return;
    }
    setSavingGate(gateId);
    setMsg(m => ({ ...m, [gateId]: '' }));
    try {
      // Restart pipeline nạp lại model có thể lâu hơn timeout mặc định 10s.
      await client.post(`/api/camera/${gateId}`, { source }, { timeout: 120000 });
      setGates(gs => gs.map(g => (g.id === gateId ? { ...g, source } : g)));
      setMsg(m => ({ ...m, [gateId]: 'Đã lưu — camera đang khởi động lại.' }));
    } catch (err) {
      setMsg(m => ({ ...m, [gateId]: 'Lỗi: ' + (err.response?.data?.detail || err.message) }));
    } finally {
      setSavingGate(null);
    }
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-3xl mx-auto">
        <p className="font-mono text-xs uppercase tracking-wider text-[#c92035] mb-1">Hạ tầng biên</p>
        <h1 className="text-2xl font-bold text-[#374151] mb-1">Cấu hình Camera</h1>
        <p className="text-sm text-[#6b7280] mb-6">
          Chọn nguồn cho từng cổng: số thứ tự webcam (0, 1, …), đường dẫn file video, hoặc địa chỉ rtsp://.
          Lưu xong camera cổng đó sẽ khởi động lại trong vài giây.
        </p>

        {msg._ && <p className="mb-4 text-[12px] font-mono text-[#c92035]">{msg._}</p>}

        <div className="space-y-4">
          {gates.map(g => (
            <div key={g.id} className="bg-[#f4f6f9] rounded-xl p-4">
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="text-[14px] font-semibold text-[#374151]">{g.name}</h2>
                <span className="text-[11px] font-mono text-[#6b7280] truncate ml-3">Đang dùng: {g.source}</span>
              </div>

              {presets.length > 0 && (
                <select
                  value=""
                  onChange={e => e.target.value && setDrafts(d => ({ ...d, [g.id]: e.target.value }))}
                  className="w-full mb-2 bg-white rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none"
                >
                  <option value="">— Chọn nhanh nguồn có sẵn —</option>
                  {presets.map(p => <option key={p.source} value={p.source}>{p.label}</option>)}
                </select>
              )}

              <div className="flex gap-2">
                <input
                  type="text"
                  value={drafts[g.id] ?? ''}
                  onChange={e => setDrafts(d => ({ ...d, [g.id]: e.target.value }))}
                  placeholder="0 | C:\video\cong.mp4 | rtsp://..."
                  className="flex-1 min-w-0 bg-white rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none"
                />
                <button
                  onClick={() => handleSave(g.id)}
                  disabled={savingGate !== null}
                  className="bg-[#c92035] hover:bg-[#a0172b] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors shrink-0"
                >
                  {savingGate === g.id ? 'Đang khởi động lại...' : 'Lưu & khởi động lại'}
                </button>
              </div>

              {msg[g.id] && (
                <p className={`mt-2 text-[12px] font-mono ${msg[g.id].includes('Lỗi') ? 'text-[#c92035]' : 'text-[#10b981]'}`}>
                  {msg[g.id]}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
