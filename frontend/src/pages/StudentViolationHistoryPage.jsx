import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import client, { API_BASE_URL } from '../api/client';
import { formatDate } from '../utils/format';
import { VIOLATION_LABELS } from '../utils/violationLabels';
import ViolationTimeline from '../components/ViolationTimeline';

/**
 * Feature 2+6: Violation history page for a specific student's vehicle.
 * Route: /admin/students/:vehicleId/violations
 * Shows all violations for the vehicle + repeat offender status + chronological timeline.
 */
export default function StudentViolationHistoryPage() {
  const { vehicleId } = useParams();
  const navigate = useNavigate();
  const [vehicle, setVehicle] = useState(null);
  const [summary, setSummary] = useState(null);
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  useEffect(() => {
    if (!vehicleId) return;
    setLoading(true);
    setError('');
    Promise.all([
      client.get(`/api/vehicles/${vehicleId}`),
      client.get(`/api/vehicles/${vehicleId}/violations`),
      client.get('/api/vehicles/violations-summary'),
    ])
      .then(([vRes, violRes, summRes]) => {
        setVehicle(vRes.data);
        // violations-summary returns an array; find the entry for this vehicle
        const entry = (summRes.data || []).find(s => String(s.vehicle_id) === String(vehicleId));
        setSummary(entry || null);
        // paginate locally
        const items = violRes.data?.items || violRes.data || [];
        setViolations(items.slice(0, PAGE_SIZE));
      })
      .catch(err => {
        setError(err.response?.data?.detail || 'Không tải được lịch sử vi phạm');
      })
      .finally(() => setLoading(false));
  }, [vehicleId]);

  const total = summary?.total_violations || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = page + 1;

  // Repeat offender threshold from config
  const REPEAT_THRESHOLD = 3;

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-4xl mx-auto">

        {/* Back link */}
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-[#6b7280] hover:text-[#374151] text-[12px] font-medium mb-4 transition-colors"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
            <path d="M19 12H5m0 0l7 7m-7-7l7-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Quay lại danh sách xe
        </button>

        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2.5 h-2.5 rounded-full bg-[#c92035] animate-pulse" />
          <h1 className="text-xl font-bold text-[#374151]">Lịch sử vi phạm</h1>
        </div>
        <p className="text-sm text-[#6b7280] mb-6 font-mono text-[11px]">
          {vehicle ? `${vehicle.student_name} · Lớp ${vehicle.student_class} · Biển số ${vehicle.plate_number}` : 'Đang tải...'}
        </p>

        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Đang tải...
          </div>
        ) : error ? (
          <div className="bg-[#f8d7dc] border border-[#f0aab3] text-[#7a1422] px-4 py-3 rounded-xl text-[12px] font-mono">
            {error}
          </div>
        ) : (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div className="bg-white rounded-xl p-4 shadow-sm border border-[#d1d5db]">
                <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Tổng vi phạm</p>
                <p className="text-3xl font-bold font-mono text-[#374151] mt-1">{total}</p>
              </div>
              <div className="bg-white rounded-xl p-4 shadow-sm border border-[#d1d5db]">
                <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Vi phạm trong 30 ngày</p>
                <p className="text-3xl font-bold font-mono text-[#374151] mt-1">
                  {summary?.recent_count || 0}
                </p>
              </div>
              <div className="bg-white rounded-xl p-4 shadow-sm border border-[#d1d5db]">
                <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Ngày không vi phạm</p>
                <p className="text-3xl font-bold font-mono text-[#10b981] mt-1">
                  {summary?.clean_days || 0}
                </p>
              </div>
              {/* Repeat offender badge */}
              <div className={`rounded-xl p-4 shadow-sm border ${summary?.is_repeat_offender ? 'bg-[#fee2e2] border-[#fca5a5]' : 'bg-white border-[#d1d5db]'}`}>
                <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Tình trạng</p>
                <p className={`text-2xl font-bold font-mono mt-1 ${summary?.is_repeat_offender ? 'text-[#991b1b]' : 'text-[#065f46]'}`}>
                  {summary?.is_repeat_offender ? 'Tái phạm' : 'Bình thường'}
                </p>
              </div>
            </div>

            {/* Repeat offender alert */}
            {summary?.is_repeat_offender && (
              <div className="bg-[#fee2e2] border border-[#fca5a5] rounded-xl p-4 mb-6 flex items-start gap-3">
                <svg className="w-5 h-5 text-[#991b1b] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none">
                  <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <div>
                  <p className="text-[12px] font-bold text-[#991b1b]">
                    Cảnh báo tái phạm
                  </p>
                  <p className="text-[11px] font-mono text-[#7a1422] mt-0.5">
                    Học sinh đã có {summary?.recent_count} vi phạm trong 30 ngày qua
                    (ngưỡng: {REPEAT_THRESHOLD}). Cần theo dõi đặc biệt.
                  </p>
                </div>
              </div>
            )}

            {/* Violations list */}
            {violations.length === 0 ? (
              <div className="bg-white rounded-xl p-12 text-center border border-[#d1d5db]">
                <p className="text-[#6b7280] font-medium">Không có vi phạm nào được ghi nhận</p>
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
                <div className="overflow-x-auto w-full">
                  <table className="w-full text-left min-w-[700px]">
                    <thead>
                      <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                        <th className="py-3 px-4 font-semibold">Thời gian</th>
                        <th className="py-3 px-2 font-semibold">Loại vi phạm</th>
                        <th className="py-3 px-2 font-semibold">Trạng thái</th>
                        <th className="py-3 px-2 font-semibold">Biển số</th>
                        <th className="py-3 px-2 font-semibold">Hành động</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                      {violations.map((v) => (
                        <tr key={v.id} className="hover:bg-[#f4f6f9] transition-colors">
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span className="font-mono font-bold text-[11px]">
                              {new Date(v.timestamp).toLocaleTimeString('vi-VN', { hour12: false })}
                            </span>
                            <span className="block font-mono text-[10px] text-[#6b7280]">
                              {new Date(v.timestamp).toLocaleDateString('vi-VN')}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${
                              v.violation_type === 'NO_HELMET'
                                ? 'bg-[#f8d7dc] text-[#7a1422] border-[#f0aab3]'
                                : v.violation_type === 'PLATE_NOT_REGISTERED'
                                ? 'bg-[#d9dfe8] text-[#c92035] border-[#f0aab3]'
                                : 'bg-[#f4f6f9] text-[#374151] border-[#d1d5db]'
                            }`}>
                              {VIOLATION_LABELS[v.violation_type] || v.violation_type}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${
                              v.status === 'resolved'
                                ? 'bg-[#d1fae5] text-[#065f46] border-[#6ee7b7]'
                                : v.status === 'reopened'
                                ? 'bg-[#fee2e2] text-[#991b1b] border-[#fca5a5]'
                                : v.status === 'reviewed'
                                ? 'bg-[#dbeafe] text-[#1e40af] border-[#93c5fd]'
                                : 'bg-[#fef3c7] text-[#92400e] border-[#fcd34d]'
                            }`}>
                              {v.status === 'resolved' ? 'Đã xử lý'
                                : v.status === 'reopened' ? 'Mở lại'
                                : v.status === 'reviewed' ? 'Đã xem'
                                : 'Chưa xử lý'}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            <span className="font-mono font-bold text-[11px]">
                              {v.plate_read || '—'}
                            </span>
                          </td>
                          <td className="py-3 px-2">
                            {v.snapshot_url ? (
                              <span className="inline-block w-16 h-12 rounded overflow-hidden border border-[#d1d5db]">
                                <img
                                  src={`${API_BASE_URL}${v.snapshot_url}`}
                                  alt="Ảnh vi phạm"
                                  className="w-full h-full object-cover"
                                />
                              </span>
                            ) : (
                              <span className="text-[#d1d5db] text-[10px] font-mono">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="bg-[#f4f6f9] px-4 py-3 flex items-center justify-between">
                    <p className="font-mono text-[11px] text-[#6b7280]">
                      Trang {currentPage}/{totalPages}
                    </p>
                    <div className="flex gap-2">
                      <button
                        disabled={page === 0}
                        onClick={() => setPage(p => p - 1)}
                        className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                      >
                        ← Trước
                      </button>
                      <button
                        disabled={page >= totalPages - 1}
                        onClick={() => setPage(p => p + 1)}
                        className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                      >
                        Sau →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
