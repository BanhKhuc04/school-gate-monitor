import { useState, useEffect } from 'react';
import client from '../api/client';

// Violation type labels for display
const VIOLATION_LABELS = {
  'NO_HELMET': 'Không đội mũ',
  'PLATE_NOT_REGISTERED': 'Biển số lạ',
  'PLATE_UNREADABLE': 'Không đọc được biển số',
  'MULTIPLE': 'Nhiều vi phạm',
  'RIDING_THROUGH_GATE': 'Xe chạy qua cổng',
};
const PAGE_SIZE = 20;

export default function AdminViolationsPage() {
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Pagination state
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  // Filter state
  const [filterPlate, setFilterPlate] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    const params = {
      limit: PAGE_SIZE,
      offset: offset,
    };
    if (filterPlate) params.plate = filterPlate;
    if (filterType) params.violation_type = filterType;
    if (filterDateFrom) params.date_from = filterDateFrom + 'T00:00:00';
    if (filterDateTo) params.date_to = filterDateTo + 'T23:59:59';
    try {
      const res = await client.get('/api/violations', { params });
      const data = res.data;
      setViolations(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Không tải được danh sách vi phạm';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [offset]);

  function handleFilter(e) {
    e.preventDefault();
    setOffset(0);
    load();
  }

  function clearFilters() {
    setFilterPlate('');
    setFilterType('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setOffset(0);
    load();
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Lịch sử vi phạm</h1>

        {/* Filter form */}
        <form onSubmit={handleFilter} className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <input
              type="text"
              placeholder="Biển số"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={filterPlate}
              onChange={e => setFilterPlate(e.target.value)}
            />
            <select
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
            >
              <option value="">Tất cả loại</option>
              {Object.entries(VIOLATION_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <input
              type="date"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={filterDateFrom}
              onChange={e => setFilterDateFrom(e.target.value)}
            />
            <input
              type="date"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={filterDateTo}
              onChange={e => setFilterDateTo(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Lọc
            </button>
            <button
              type="button"
              onClick={clearFilters}
              className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-sm font-medium py-2 px-4 rounded-lg transition-colors"
            >
              Xóa lọc
            </button>
          </div>
        </form>

        {loading ? (
          <div className="text-center text-gray-500 py-8">Đang tải...</div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
            {error}
          </div>
        ) : violations.length === 0 ? (
          <div className="text-center text-gray-400 py-8">Không có vi phạm nào.</div>
        ) : (
          <>
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Thời gian</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Loại vi phạm</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Biển số</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Lớp</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Học sinh</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Ảnh</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {violations.map((v) => (
                      <tr key={v.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{v.timestamp}</td>
                        <td className="px-4 py-3">
                          <span className="inline-block bg-red-100 text-red-700 px-2 py-0.5 rounded text-xs font-medium">
                            {VIOLATION_LABELS[v.violation_type] || v.violation_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-gray-800">{v.plate_read || '—'}</td>
                        <td className="px-4 py-3 text-gray-700">{v.student_class || '—'}</td>
                        <td className="px-4 py-3 text-gray-700">{v.student_name || '—'}</td>
                        <td className="px-4 py-3">
                          {v.snapshot_url ? (
                            <a
                              href={v.snapshot_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:text-blue-800 text-sm"
                            >
                              Xem ảnh
                            </a>
                          ) : (
                            <span className="text-gray-400 text-sm">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
                <span>Hiển thị {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, total)} / {total} vi phạm</span>
                <div className="flex gap-2">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                  >
                    ← Trước
                  </button>
                  <span className="px-3 py-1">Trang {currentPage}/{totalPages}</span>
                  <button
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="px-3 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
                  >
                    Sau →
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
