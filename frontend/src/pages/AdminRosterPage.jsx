import { useState, useEffect, useRef } from 'react';
import QRCode from 'qrcode';
import client, { API_BASE_URL } from '../api/client';

/**
 * UT8: Admin quản lý danh sách mã số hợp lệ (student_roster) + QR code trỏ tới
 * trang public register.
 *
 * Mục đích:
 * - Admin import danh sách mã số từ nhà trường (form tay / bulk)
 * - In QR code dán ở cổng để HS scan và tự đăng ký
 */
export default function AdminRosterPage() {
  const [roster, setRoster] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newStudentId, setNewStudentId] = useState('');
  const [newStudentName, setNewStudentName] = useState('');
  const [newStudentClass, setNewStudentClass] = useState('');
  const [bulkRows, setBulkRows] = useState('');
  const [showQR, setShowQR] = useState(false);
  const qrRef = useRef(null);

  async function load() {
    setLoading(true);
    try {
      const res = await client.get('/api/roster');
      setRoster(res.data || []);
    } catch {
      setError('Không tải được danh sách mã số');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleAdd(e) {
    e.preventDefault();
    setError('');
    try {
      await client.post('/api/roster', {
        student_id: newStudentId.trim(),
        student_name: newStudentName.trim(),
        student_class: newStudentClass.trim(),
      });
      setNewStudentId('');
      setNewStudentName('');
      setNewStudentClass('');
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Lỗi thêm mã số');
    }
  }

  async function handleDelete(sid) {
    if (!confirm(`Xóa mã số ${sid} khỏi danh sách?`)) return;
    try {
      await client.delete(`/api/roster/${encodeURIComponent(sid)}`);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Lỗi xóa');
    }
  }

  async function handleBulkImport() {
    setError('');
    // Parse plain text: mỗi dòng "student_id,student_name,student_class"
    const lines = bulkRows.split('\n').map(l => l.trim()).filter(Boolean);
    const rows = lines.map(line => {
      const parts = line.split(',').map(p => p.trim());
      return { student_id: parts[0], student_name: parts[1], student_class: parts[2] };
    }).filter(r => r.student_id && r.student_name && r.student_class);
    if (rows.length === 0) {
      setError('Không có dòng hợp lệ (cần định dạng: student_id,student_name,student_class)');
      return;
    }
    try {
      const res = await client.post('/api/roster/import', rows);
      const { created, skipped, errors } = res.data;
      alert(`Đã import: ${created} mới, ${skipped} bị bỏ qua${errors?.length ? `. Lỗi: ${errors.slice(0, 5).map(e => e.student_id + ' (' + e.message + ')').join(', ')}` : ''}`);
      setBulkRows('');
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Lỗi import');
    }
  }

  const publicUrl = `${window.location.origin}/register`;
  const [qrDataUrl, setQrDataUrl] = useState(null);

  useEffect(() => {
    if (!showQR) return;
    QRCode.toDataURL(publicUrl, { width: 220, margin: 1 })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(null));
  }, [showQR, publicUrl]);

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(publicUrl);
      alert('Đã copy link /register vào clipboard. Dán link này hoặc QR vào nơi muốn HS scan.');
    } catch {
      prompt('Copy link:', publicUrl);
    }
  }

  return (
    <div className="min-h-screen bg-[#EEF3F8] p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#123B6D] animate-pulse" />
            <h1 className="text-xl font-bold text-[#374151]">Danh sách Mã số & Đăng ký QR</h1>
          </div>
          <button
            onClick={() => setShowQR(true)}
            className="flex items-center gap-1.5 bg-[#123b6d] hover:bg-[#0d2a4f] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
              <rect x="3" y="3" width="7" height="7" stroke="currentColor" strokeWidth="1.8" />
              <rect x="14" y="3" width="7" height="7" stroke="currentColor" strokeWidth="1.8" />
              <rect x="3" y="14" width="7" height="7" stroke="currentColor" strokeWidth="1.8" />
              <path d="M14 14h2v2h-2zm4 0h3v3h-3zm-4 4h2v3h-2zm4 0h3v3h-3z" stroke="currentColor" strokeWidth="1.8" />
            </svg>
            QR cho HS scan
          </button>
        </div>

        {error && (
          <div className="bg-[#C92035]/10 border border-[#C92035]/20 text-[#C92035] px-4 py-3 rounded-xl mb-4 text-[12px] font-mono">
            {error}
          </div>
        )}

        {/* Add 1 mã số */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-3">Thêm 1 mã số</h2>
          <form onSubmit={handleAdd} className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <input
              type="text" required placeholder="Mã số (VD: HS2025001)" value={newStudentId}
              onChange={e => setNewStudentId(e.target.value.toUpperCase())}
              className="bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono font-bold text-[#374151] uppercase border border-[#d1d5db] outline-none focus:ring-2 focus:ring-[#123b6d]"
            />
            <input
              type="text" required placeholder="Tên học sinh" value={newStudentName}
              onChange={e => setNewStudentName(e.target.value)}
              className="bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] text-[#374151] border border-[#d1d5db] outline-none"
            />
            <input
              type="text" required placeholder="Lớp (VD: 10A1)" value={newStudentClass}
              onChange={e => setNewStudentClass(e.target.value)}
              className="bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border border-[#d1d5db] outline-none"
            />
            <button type="submit" className="bg-[#123B6D] hover:bg-[#123B6D] text-white text-[12px] font-semibold py-2 px-4 rounded-lg">
              Thêm
            </button>
          </form>
        </div>

        {/* Bulk import */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-3">Import hàng loạt (1 dòng = 1 học sinh)</h2>
          <p className="text-[11px] text-[#6b7280] font-mono mb-2">
            Mỗi dòng: <code>student_id,student_name,student_class</code> (CSV tối giản, không header)
          </p>
          <textarea
            value={bulkRows}
            onChange={e => setBulkRows(e.target.value)}
            placeholder={'HS2025001,Nguyễn Văn A,10A1\nHS2025002,Trần Thị B,10A2'}
            rows={5}
            className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border border-[#d1d5db] outline-none focus:ring-2 focus:ring-[#123b6d]"
          />
          <button
            onClick={handleBulkImport}
            className="mt-3 bg-[#123b6d] hover:bg-[#0d2a4f] text-white text-[12px] font-semibold py-2 px-4 rounded-lg"
          >
            Import hàng loạt
          </button>
        </div>

        {/* Roster list */}
        <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
          {loading ? (
            <div className="text-center text-[#6b7280] py-12 text-[12px]">Đang tải...</div>
          ) : roster.length === 0 ? (
            <div className="bg-white rounded-xl p-12 text-center">
              <p className="text-[#6b7280] font-medium">Chưa có mã số nào trong danh sách</p>
              <p className="text-[10px] font-mono text-[#9ca3af] mt-1">Thêm tay hoặc import CSV ở trên</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-4 font-semibold">Mã số</th>
                    <th className="py-3 px-3 font-semibold">Tên</th>
                    <th className="py-3 px-3 font-semibold">Lớp</th>
                    <th className="py-3 px-3 font-semibold">Ngày thêm</th>
                    <th className="py-3 px-4 text-right font-semibold">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {roster.map(r => (
                    <tr key={r.student_id} className="hover:bg-[#f4f6f9]">
                      <td className="py-3 px-4 font-mono font-bold">{r.student_id}</td>
                      <td className="py-3 px-3 font-medium">{r.student_name}</td>
                      <td className="py-3 px-3 font-mono text-[11px] text-[#6b7280]">{r.student_class}</td>
                      <td className="py-3 px-3 text-[10px] font-mono text-[#9ca3af]">{r.created_at}</td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleDelete(r.student_id)}
                          className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#C92035]/10"
                        >
                          Xóa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <p className="mt-3 text-[10px] text-[#9ca3af] font-mono text-center">
          Tổng: <span className="font-bold text-[#374151]">{roster.length}</span> mã số
        </p>

        {/* QR modal */}
        {showQR && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowQR(false)}>
            <div className="bg-white rounded-xl shadow-lg max-w-sm w-full p-6 text-center" onClick={e => e.stopPropagation()}>
              <h2 className="text-base font-bold text-[#374151] mb-3">QR trỏ tới trang đăng ký</h2>
              <div ref={qrRef} className="bg-white border border-[#d1d5db] rounded-lg p-4 mb-3 flex flex-col items-center">
                {qrDataUrl ? (
                  <img src={qrDataUrl} alt="QR đăng ký" className="w-48 h-48" />
                ) : (
                  <div className="w-48 h-48 bg-[#f4f6f9] border border-[#d1d5db] flex items-center justify-center text-[11px] font-mono text-[#6b7280]">
                    Đang tạo QR...
                  </div>
                )}
                <code className="mt-3 text-[11px] font-mono text-[#374151] break-all">{publicUrl}</code>
              </div>
              <div className="flex gap-2">
                <button onClick={copyUrl} className="flex-1 bg-[#123B6D] hover:bg-[#123B6D] text-white text-[12px] font-semibold py-2 rounded-lg">
                  Copy link
                </button>
                <button onClick={() => setShowQR(false)} className="flex-1 bg-[#6b7280] hover:bg-[#4b5563] text-white text-[12px] font-semibold py-2 rounded-lg">
                  Đóng
                </button>
              </div>
              <p className="mt-3 text-[10px] text-[#9ca3af] font-mono">
                Link trỏ tới <code>/register</code> — HS truy cập, nhập mã số, đăng ký tự động.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}