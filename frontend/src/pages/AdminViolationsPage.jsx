import { useState, useEffect } from 'react';
import client from '../api/client';

export default function AdminViolationsPage() {
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await client.get('/api/violations');
      setViolations(res.data);
    } catch {
      // non-admin may get 403, show empty
      setViolations([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Lịch sử vi phạm</h1>

        {loading ? (
          <div className="text-center text-gray-500 py-8">Đang tải...</div>
        ) : violations.length === 0 ? (
          <div className="text-center text-gray-400 py-8">Không có vi phạm nào.</div>
        ) : (
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
                          {v.violation_type}
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
        )}
      </div>
    </div>
  );
}
