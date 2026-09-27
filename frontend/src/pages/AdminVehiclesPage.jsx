import { useState, useEffect } from 'react';
import client from '../api/client';

export default function AdminVehiclesPage() {
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);

  // Form state
  const [plate, setPlate] = useState('');
  const [studentName, setStudentName] = useState('');
  const [studentClass, setStudentClass] = useState('');

  async function loadVehicles() {
    setLoading(true);
    try {
      const res = await client.get('/api/vehicles');
      setVehicles(res.data);
    } catch (err) {
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
        await client.put(`/api/vehicles/${editingId}`, { plate_number: plate, student_name: studentName, student_class: studentClass });
      } else {
        await client.post('/api/vehicles', { plate_number: plate, student_name: studentName, student_class: studentClass });
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
    setStudentName(v.student_name);
    setStudentClass(v.student_class);
    setError('');
  }

  async function handleDelete(id) {
    if (!confirm('Xóa xe này?')) return;
    try {
      await client.delete(`/api/vehicles/${id}`);
      loadVehicles();
    } catch (err) {
      setError('Xóa thất bại');
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Quản lý xe đăng ký</h1>

        {/* Form */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-4">
            {editingId ? `Sửa xe #${editingId}` : 'Thêm xe mới'}
          </h2>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">{error}</div>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            <input
              type="text"
              placeholder="Biển số"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"
              value={plate}
              onChange={(e) => setPlate(e.target.value.toUpperCase())}
              required
            />
            <input
              type="text"
              placeholder="Tên học sinh"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={studentName}
              onChange={(e) => setStudentName(e.target.value)}
              required
            />
            <input
              type="text"
              placeholder="Lớp (VD: 10A1)"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={studentClass}
              onChange={(e) => setStudentClass(e.target.value)}
              required
            />
            <div className="sm:col-span-3 flex gap-2">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
              >
                {editingId ? 'Lưu' : 'Thêm'}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm font-medium py-2 px-4 rounded-lg transition-colors"
                >
                  Hủy
                </button>
              )}
            </div>
          </form>
        </div>

        {/* CSV Import */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-700 mb-3">Nhập danh sách từ CSV</h2>
          <div className="flex flex-wrap gap-3 items-center">
            <input
              type="file"
              id="csv-file"
              accept=".csv"
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
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
                  if (d.errors?.length) {
                    alert('Lỗi: ' + d.errors.slice(0, 5).join('\n'));
                  }
                  loadVehicles();
                } catch (err) {
                  setError(err.response?.data?.detail || 'Lỗi khi nhập CSV');
                }
                e.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => {
                const csv = 'plate_number,student_name,student_class\n"","",""';
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'mau_xe.csv';
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Tải file mẫu CSV
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center text-gray-500 py-8">Đang tải...</div>
        ) : vehicles.length === 0 ? (
          <div className="text-center text-gray-400 py-8">Chưa có xe nào.</div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Biển số</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Học sinh</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Lớp</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {vehicles.map((v) => (
                    <tr key={v.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono font-medium text-gray-800">{v.plate_number}</td>
                      <td className="px-4 py-3 text-gray-700">{v.student_name}</td>
                      <td className="px-4 py-3 text-gray-700">{v.student_class}</td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <button
                          onClick={() => startEdit(v)}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          Sửa
                        </button>
                        <button
                          onClick={() => handleDelete(v.id)}
                          className="text-red-600 hover:text-red-800 text-sm font-medium"
                        >
                          Xóa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
