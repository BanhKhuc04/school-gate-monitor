import { useState, useEffect } from 'react';
import client from '../api/client';

export default function AdminVehiclesPage() {
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [plate, setPlate] = useState('');
  const [studentName, setStudentName] = useState('');
  const [studentClass, setStudentClass] = useState('');

  async function loadVehicles() {
    setLoading(true);
    try {
      const res = await client.get('/api/vehicles');
      setVehicles(res.data);
    } catch {
      setError('Không tải được danh sách xe');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadVehicles(); }, []);

  function resetForm() {
    setPlate('');
    setStudentName('');
    setStudentClass('');
    setEditingId(null);
    setError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      if (editingId) {
        await client.put(`/api/vehicles/${editingId}`, {
          plate_number: plate, student_name: studentName, student_class: studentClass
        });
      } else {
        await client.post('/api/vehicles', {
          plate_number: plate, student_name: studentName, student_class: studentClass
        });
      }
      resetForm();
      loadVehicles();
    } catch (err) {
      setError(err.response?.data?.detail || 'Lỗi khi lưu');
    }
  }

  function startEdit(v) {
    setEditingId(v.id);
    setPlate(v.plate_number);
    setStudentName(v.student_name || '');
    setStudentClass(v.student_class || '');
    setError('');
  }

  async function handleDelete(id) {
    if (!confirm('Xóa xe này?')) return;
    try {
      await client.delete(`/api/vehicles/${id}`);
      loadVehicles();
    } catch {
      setError('Xóa thất bại');
    }
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          <span className="w-2.5 h-2.5 rounded-full bg-[#10b981] animate-pulse" />
          <h1 className="text-xl font-bold text-[#374151]">Phương tiện Đăng ký</h1>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Tổng xe đăng ký</p>
              <p className="text-3xl font-bold font-mono text-[#374151] mt-1">{vehicles.length}</p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#e8f5e9] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#10b981]" viewBox="0 0 24 24" fill="none">
                <path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z" stroke="currentColor" strokeWidth="1.6"/>
                <path d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10M13 16l4-4m0 0l4 4m-4-4v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Đang chỉnh sửa</p>
              <p className="text-3xl font-bold font-mono text-[#c92035] mt-1">{editingId ? '1' : '0'}</p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#f8d7dc] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
          </div>
        </div>

        {/* Add/Edit Form */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#10b981]" viewBox="0 0 24 24" fill="none">
              <path d="M12 4v16m8-8H4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            {editingId ? 'Chỉnh sửa xe' : 'Thêm xe mới'}
          </h2>

          {error && (
            <div className="bg-[#f8d7dc] border border-[#f0aab3] text-[#7a1422] px-4 py-3 rounded-xl mb-4 text-[12px] font-mono">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Biển số
                </label>
                <input
                  type="text"
                  className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono font-bold text-[#374151] uppercase border-0 outline-none focus:ring-2 focus:ring-[#c92035] tracking-wider"
                  value={plate}
                  onChange={e => setPlate(e.target.value.toUpperCase())}
                  placeholder="29MD-123.45"
                  required
                />
              </div>
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Tên học sinh
                </label>
                <input
                  type="text"
                  className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] text-[#374151] border-0 outline-none focus:ring-2 focus:ring-[#c92035]"
                  value={studentName}
                  onChange={e => setStudentName(e.target.value)}
                  placeholder="Nguyễn Văn A"
                  required
                />
              </div>
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  Lớp
                </label>
                <input
                  type="text"
                  className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none focus:ring-2 focus:ring-[#c92035]"
                  value={studentClass}
                  onChange={e => setStudentClass(e.target.value)}
                  placeholder="10A1"
                  required
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                className="flex items-center gap-1.5 bg-[#10b981] hover:bg-[#059669] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                {editingId ? 'Lưu' : 'Thêm xe'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <path d="M6 18L18 6M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  Hủy
                </button>
              )}
            </div>
          </form>
        </div>

        {/* CSV Import */}
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-3 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#c92035]" viewBox="0 0 24 24" fill="none">
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5-5m0 0l5 5m-5-5v12M16 16l-4 4m0 0l4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Nhập danh sách từ CSV
          </h2>
          <div className="flex flex-wrap gap-3 items-center">
            <label className="flex items-center gap-2 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg cursor-pointer transition-colors">
              <svg className="w-4 h-4 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              Chọn file CSV
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (!file) return;
                  const formData = new FormData();
                  formData.append('file', file);
                  setError('');
                  try {
                    const res = await client.post('/api/vehicles/import', formData, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });
                    const d = res.data;
                    alert(`Đã nhập: ${d.created} mới, ${d.skipped} trùng, ${d.errors?.length || 0} lỗi`);
                    if (d.errors?.length) alert('Lỗi: ' + d.errors.slice(0, 5).join('\n'));
                    loadVehicles();
                  } catch (err) {
                    setError(err.response?.data?.detail || 'Lỗi khi nhập CSV');
                  }
                  e.target.value = '';
                }}
              />
            </label>
            <button
              type="button"
              onClick={() => {
                const csv = 'plate_number,student_name,student_class\n"29A1-123.45","Nguyễn Văn A","10A1"';
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'mau_xe.csv';
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#6b7280] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              Tải file mẫu CSV
            </button>
          </div>
        </div>

        {/* Vehicles Table */}
        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Đang tải...
          </div>
        ) : vehicles.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center border border-[#d1d5db]">
            <div className="w-12 h-12 rounded-xl bg-[#f4f6f9] flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z" stroke="currentColor" strokeWidth="1.6"/>
                <path d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
            <p className="text-[#6b7280] font-medium">Chưa có xe nào được đăng ký</p>
            <p className="text-[10px] font-mono text-[#9ca3af] mt-1">Thêm xe mới hoặc nhập danh sách từ file CSV</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[600px]">
                <thead>
                  <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">Biển số</th>
                    <th className="py-3 px-3 font-semibold">Học sinh</th>
                    <th className="py-3 px-3 font-semibold">Lớp</th>
                    <th className="py-3 px-4 text-right font-semibold">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {vehicles.map((v) => (
                    <tr key={v.id} className={`hover:bg-[#ffffff] transition-colors ${editingId === v.id ? 'bg-[#f4f6f9]' : ''}`}>
                      <td className="py-3 px-4">
                        <span className="font-mono font-bold text-[11px] px-2 py-0.5 rounded bg-[#f4f6f9] text-[#374151] border border-[#d1d5db]">
                          {v.plate_number}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-medium">{v.student_name || '—'}</td>
                      <td className="py-3 px-3 font-mono text-[11px] text-[#6b7280]">{v.student_class || '—'}</td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => startEdit(v)}
                            className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f8d7dc] transition-colors"
                          >
                            Sửa
                          </button>
                          <button
                            onClick={() => handleDelete(v.id)}
                            className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f8d7dc] transition-colors"
                          >
                            Xóa
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 bg-[#f4f6f9] border-t border-[#d1d5db]">
              <span className="font-mono text-[11px] text-[#6b7280]">
                Tổng: <span className="font-bold text-[#374151]">{vehicles.length}</span> xe
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
