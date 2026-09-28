import { useState, useEffect, useCallback } from 'react';
import client, { API_BASE_URL } from '../api/client';
import { formatDate } from '../utils/format';
import { VIOLATION_LABELS } from '../utils/violationLabels';

const PAGE_SIZE = 20;

// Color coding per violation type — Vanguard design system
const VIOLATION_COLORS = {
  NO_HELMET: {
    bg: 'bg-[#f8d7dc]', text: 'text-[#7a1422]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Không đội mũ bảo hiểm',
  },
  PLATE_NOT_REGISTERED: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Biển số chưa đăng ký',
  },
  PLATE_UNREADABLE: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Không đọc được biển số',
  },
  MULTIPLE: {
    bg: 'bg-[#dbe3ee]', text: 'text-[#dbe3ee]',
    border: 'border-[#bcc7de]', dot: 'bg-[#f8d7dc]',
    label: 'Nhiều lỗi đồng thời',
  },
  RIDING_THROUGH_GATE: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Đi xe qua cổng',
  },
};

function ViolationBadge({ type }) {
  const colors = VIOLATION_COLORS[type] || VIOLATION_COLORS.NO_HELMET;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${colors.bg} ${colors.text} ${colors.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {colors.label}
    </span>
  );
}

export default function AdminViolationsPage() {
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filterPlate, setFilterPlate] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const params = { limit: PAGE_SIZE, offset };
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
      setError(err.response?.data?.detail || err.message || 'Không tải được danh sách vi phạm');
    } finally {
      setLoading(false);
    }
  }, [offset, filterPlate, filterType, filterDateFrom, filterDateTo]);

  useEffect(() => { load(); }, []);

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
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          <span className="w-2.5 h-2.5 rounded-full bg-[#c92035] animate-pulse" />
          <h1 className="text-xl font-bold text-[#374151]">Nhật ký Giám sát &amp; Vi phạm Cổng trường</h1>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">Tổng vi phạm hôm nay</p>
              <p className="text-3xl font-bold font-mono text-[#374151] mt-1">{total}</p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#f8d7dc] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">NO_HELMET</p>
              <p className="text-3xl font-bold font-mono text-[#374151] mt-1">
                {violations.filter(v => v.violation_type === 'NO_HELMET').length}
              </p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#f8d7dc] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M12 2a4 4 0 00-4 4v3H6a2 2 0 00-2 2v7a2 2 0 002 2h12a2 2 0 002-2v-7a2 2 0 00-2-2h-2V6a4 4 0 00-4-4z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">PLATE_NOT_REGISTERED</p>
              <p className="text-3xl font-bold font-mono text-[#374151] mt-1">
                {violations.filter(v => v.violation_type === 'PLATE_NOT_REGISTERED').length}
              </p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#f8d7dc] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.6"/>
                <path d="M3 10h18" stroke="currentColor" strokeWidth="1.6"/>
              </svg>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">MULTIPLE</p>
              <p className="text-3xl font-bold font-mono text-[#374151] mt-1">
                {violations.filter(v => v.violation_type === 'MULTIPLE').length}
              </p>
            </div>
            <div className="w-11 h-11 rounded-lg bg-[#dbe3ee] flex items-center justify-center">
              <svg className="w-6 h-6 text-[#f8d7dc]" viewBox="0 0 24 24" fill="none">
                <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
          </div>
        </div>

        {/* Filter form */}
        <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] p-4 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
            <div className="flex items-center bg-[#f4f6f9] rounded-lg px-3 py-2 gap-2">
              <svg className="w-4 h-4 text-[#6b7280] shrink-0" viewBox="0 0 24 24" fill="none">
                <path d="M15 15l6 6m-11-4a7 7 0 110-14 7 7 0 010 14z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              <input
                type="text"
                placeholder="Tìm biển số..."
                className="bg-transparent border-0 outline-none w-full font-mono text-[11px] text-[#374151] placeholder:text-[#9ca3af]"
                value={filterPlate}
                onChange={e => setFilterPlate(e.target.value)}
              />
            </div>
            <div className="relative">
              <select
                className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] text-[#374151] border-0 outline-none appearance-none cursor-pointer pr-8 font-mono"
                value={filterType}
                onChange={e => setFilterType(e.target.value)}
              >
                <option value="">Tất cả loại vi phạm</option>
                {Object.entries(VIOLATION_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <svg className="absolute right-2.5 top-2.5 w-4 h-4 text-[#6b7280] pointer-events-none" viewBox="0 0 24 24" fill="none">
                <path d="M19 9l-7 7-7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <input
              type="date"
              className="bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none w-full"
              value={filterDateFrom}
              onChange={e => setFilterDateFrom(e.target.value)}
            />
            <input
              type="date"
              className="bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] font-mono text-[#374151] border-0 outline-none w-full"
              value={filterDateTo}
              onChange={e => setFilterDateTo(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleFilter}
              className="flex items-center gap-1.5 bg-[#c92035] hover:bg-[#c92035] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                <path d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              Lọc
            </button>
            <button
              type="button"
              onClick={clearFilters}
              className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                <path d="M6 18L18 6M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Xóa lọc
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Đang tải dữ liệu...
          </div>
        ) : error ? (
          <div className="bg-[#f8d7dc] border border-[#f0aab3] text-[#7a1422] px-4 py-3 rounded-xl text-[12px] font-mono">
            {error}
          </div>
        ) : violations.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center border border-[#d1d5db]">
            <div className="w-12 h-12 rounded-xl bg-[#f4f6f9] flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
            <p className="text-[#6b7280] font-medium">Không có vi phạm nào được ghi nhận</p>
            <p className="text-[10px] font-mono text-[#9ca3af] mt-1">Thử thay đổi bộ lọc hoặc chờ camera phát hiện vi phạm</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse min-w-[900px]">
                <thead>
                  <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">Thời gian</th>
                    <th className="py-3 px-2 text-center font-semibold">Ảnh</th>
                    <th className="py-3 px-2 font-semibold">Loại vi phạm</th>
                    <th className="py-3 px-2 font-semibold">Biển số</th>
                    <th className="py-3 px-2 font-semibold">Học sinh</th>
                    <th className="py-3 px-2 font-semibold">Lớp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {violations.map((v) => (
                    <tr key={v.id} className="hover:bg-[#ffffff] transition-colors">
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className="font-mono font-bold text-[11px]">
                          {new Date(v.timestamp).toLocaleTimeString('vi-VN', { hour12: false })}
                        </span>
                        <span className="block font-mono text-[10px] text-[#6b7280]">
                          {new Date(v.timestamp).toLocaleDateString('vi-VN')}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-center">
                        {v.snapshot_url ? (
                          <a
                            href={`${API_BASE_URL}${v.snapshot_url}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block w-20 h-14 rounded overflow-hidden border border-[#d1d5db] hover:opacity-80 transition-opacity"
                          >
                            <img
                              src={`${API_BASE_URL}${v.snapshot_url}`}
                              alt="Ảnh vi phạm"
                              className="w-full h-full object-cover"
                            />
                          </a>
                        ) : (
                          <span className="text-[#d1d5db] font-mono text-[10px]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2">
                        <ViolationBadge type={v.violation_type} />
                      </td>
                      <td className="py-3 px-2">
                        <span className="font-mono font-bold text-[11px] px-1.5 py-0.5 rounded bg-[#f4f6f9] text-[#374151]">
                          {v.plate_read || '—'}
                        </span>
                      </td>
                      <td className="py-3 px-2 font-medium">
                        {v.student_name || <span className="text-[#d1d5db]">—</span>}
                      </td>
                      <td className="py-3 px-2 text-[#6b7280] font-mono text-[11px]">
                        {v.student_class || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="bg-[#f4f6f9] px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-3">
                <span className="font-mono text-[11px] text-[#6b7280]">
                  Hiển thị <span className="font-bold text-[#374151]">{(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, total)}</span> / <span className="font-bold text-[#374151]">{total}</span> vi phạm
                </span>
                <div className="flex items-center gap-2">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                  >
                    ← Trước
                  </button>
                  <span className="font-mono text-[11px] font-semibold text-[#374151]">
                    Trang {currentPage}/{totalPages}
                  </span>
                  <button
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                  >
                    Sau →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
