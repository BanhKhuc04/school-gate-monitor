import { useState, useEffect, useRef } from 'react';
import client from '../api/client';

export default function AdminFacesPage() {
  const [faces, setFaces] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('faces'); // 'faces' | 'events'

  // Enroll form state
  const [labelName, setLabelName] = useState('');
  const [vehicleId, setVehicleId] = useState('');
  const [photo, setPhoto] = useState(null);
  const [enrollError, setEnrollError] = useState('');
  const [enrollSuccess, setEnrollSuccess] = useState('');
  const [enrolling, setEnrolling] = useState(false);
  const fileRef = useRef(null);

  async function loadFaces() {
    try {
      const res = await client.get('/api/faces');
      setFaces(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Không tải được danh sách khuôn mặt');
    }
  }

  async function loadEvents() {
    try {
      const res = await client.get('/api/faces/events?limit=50');
      setEvents(res.data.items || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Không tải được sự kiện');
    }
  }

  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([loadFaces(), tab === 'events' ? loadEvents() : Promise.resolve()])
      .finally(() => setLoading(false));
  }, [tab]);

  async function handleEnroll(e) {
    e.preventDefault();
    setEnrollError('');
    setEnrollSuccess('');
    if (!labelName.trim()) {
      setEnrollError('Vui lòng nhập tên người');
      return;
    }
    if (!photo) {
      setEnrollError('Vui lòng chọn ảnh');
      return;
    }
    setEnrolling(true);
    const formData = new FormData();
    formData.append('label_name', labelName.trim());
    if (vehicleId) formData.append('vehicle_id', vehicleId);
    formData.append('photo', photo);
    try {
      const res = await client.post('/api/faces/enroll', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setEnrollSuccess(`Đã đăng ký khuôn mặt cho "${res.data.label_name}" (ID: ${res.data.id})`);
      setLabelName('');
      setVehicleId('');
      setPhoto(null);
      if (fileRef.current) fileRef.current.value = '';
      loadFaces();
    } catch (err) {
      setEnrollError(err.response?.data?.detail || 'Đăng ký thất bại');
    } finally {
      setEnrolling(false);
    }
  }

  async function handleDelete(faceId) {
    if (!confirm('Xóa khuôn mặt này?')) return;
    try {
      await client.delete(`/api/faces/${faceId}`);
      loadFaces();
    } catch (err) {
      setError(err.response?.data?.detail || 'Xóa thất bại');
    }
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    try {
      return new Date(isoStr).toLocaleString('vi-VN');
    } catch {
      return isoStr;
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Quản lý khuôn mặt</h1>

        {/* Tab switcher */}
        <div className="flex gap-1 mb-6 bg-gray-200 rounded-lg p-1 w-fit">
          <button
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'faces'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-600 hover:text-gray-800'
            }`}
            onClick={() => setTab('faces')}
          >
            Danh sách đã đăng ký
          </button>
          <button
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'events'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-600 hover:text-gray-800'
            }`}
            onClick={() => setTab('events')}
          >
            Sự kiện nhận diện
          </button>
        </div>

        {/* ── Faces tab ─────────────────────────────────────────── */}
        {tab === 'faces' && (
          <>
            {/* Enroll form */}
            <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
              <h2 className="text-base font-semibold text-gray-700 mb-4">Đăng ký khuôn mặt mới</h2>
              {enrollError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4 text-sm">
                  {enrollError}
                </div>
              )}
              {enrollSuccess && (
                <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded mb-4 text-sm">
                  {enrollSuccess}
                </div>
              )}
              <form onSubmit={handleEnroll} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Tên người <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Nguyễn Văn A"
                    value={labelName}
                    onChange={e => setLabelName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    ID xe (tùy chọn)
                  </label>
                  <input
                    type="number"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="1"
                    value={vehicleId}
                    onChange={e => setVehicleId(e.target.value)}
                    min="1"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Ảnh khuôn mặt <span className="text-red-500">*</span>
                  </label>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    capture="user"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                    onChange={e => setPhoto(e.target.files[0] || null)}
                    required
                  />
                </div>
                <div className="sm:col-span-2 lg:col-span-4 flex gap-2 items-end">
                  <button
                    type="submit"
                    disabled={enrolling}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
                  >
                    {enrolling ? 'Đang đăng ký...' : 'Đăng ký'}
                  </button>
                  <span className="text-xs text-gray-500">
                    Ảnh rõ mặt, nhìn thẳng, đủ ánh sáng
                  </span>
                </div>
              </form>
            </div>

            {/* Faces list */}
            {loading ? (
              <div className="text-center text-gray-500 py-8">Đang tải...</div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm mb-4">
                {error}
              </div>
            ) : faces.length === 0 ? (
              <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
                Chưa có khuôn mặt nào được đăng ký.
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Tên</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">ID Xe</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Ngày đăng ký</th>
                        <th className="text-right px-4 py-3 font-medium text-gray-600">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {faces.map((f) => (
                        <tr key={f.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-gray-500">#{f.id}</td>
                          <td className="px-4 py-3 font-medium text-gray-800">{f.label_name}</td>
                          <td className="px-4 py-3 text-gray-600">{f.vehicle_id || '—'}</td>
                          <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatDate(f.created_at)}</td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => handleDelete(f.id)}
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
                <div className="px-4 py-3 bg-gray-50 text-xs text-gray-500 border-t">
                  Tổng: {faces.length} khuôn mặt
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Events tab ─────────────────────────────────────────── */}
        {tab === 'events' && (
          <>
            {loading ? (
              <div className="text-center text-gray-500 py-8">Đang tải...</div>
            ) : events.length === 0 ? (
              <div className="bg-white rounded-xl shadow-sm p-8 text-center text-gray-400">
                Chưa có sự kiện nhận diện khuôn mặt nào.
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">ID</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Người nhận diện</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Độ tương đồng</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">ID Xe</th>
                        <th className="text-left px-4 py-3 font-medium text-gray-600">Thời gian</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {events.map((ev) => (
                        <tr key={ev.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-gray-500">#{ev.id}</td>
                          <td className="px-4 py-3 font-medium text-amber-700">{ev.matched_label || '—'}</td>
                          <td className="px-4 py-3">
                            {ev.similarity != null ? (
                              <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                ev.similarity >= 0.7
                                  ? 'bg-green-100 text-green-700'
                                  : ev.similarity >= 0.5
                                  ? 'bg-yellow-100 text-yellow-700'
                                  : 'bg-red-100 text-red-700'
                              }`}>
                                {(ev.similarity * 100).toFixed(1)}%
                              </span>
                            ) : '—'}
                          </td>
                          <td className="px-4 py-3 text-gray-600">{ev.vehicle_id || '—'}</td>
                          <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatDate(ev.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="px-4 py-3 bg-gray-50 text-xs text-gray-500 border-t">
                  {events.length} sự kiện gần nhất
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
