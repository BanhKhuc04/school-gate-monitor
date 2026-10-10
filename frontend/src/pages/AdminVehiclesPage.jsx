import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import client from '../api/client';
import StudentAutocomplete from '../components/StudentAutocomplete';
import { useAuth } from '../auth/AuthContext';
import { useLang } from '../i18n/LanguageContext';

export default function AdminVehiclesPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useLang();
  const isAdmin = user?.role === 'admin';
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [plate, setPlate] = useState('');
  const [studentName, setStudentName] = useState('');
  const [studentClass, setStudentClass] = useState('');
  const [exporting, setExporting] = useState(false);
  // Feature 11: CSV dry-run preview
  const [csvPreview, setCsvPreview] = useState(null); // { dry_run_results, filename, file }
  // Feature 2+6: Repeat offender summary for badge display
  const [summaryMap, setSummaryMap] = useState({}); // vehicleId -> summary entry

  async function handleExport() {
    setExporting(true);
    try {
      const res = await client.get('/api/vehicles/export', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `xe_dang_ky_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t('Không xuất được file', 'Could not export the file'));
    } finally {
      setExporting(false);
    }
  }

  async function loadVehicles() {
    setLoading(true);
    try {
      const res = await client.get('/api/vehicles');
      setVehicles(res.data);
    } catch {
      setError(t('Không tải được danh sách xe', 'Could not load the bike list'));
    } finally {
      setLoading(false);
    }
  }

  // Feature 2+6: Load violations summary for repeat offender badges
  async function loadSummary() {
    try {
      const res = await client.get('/api/vehicles/violations-summary');
      const map = {};
      for (const entry of res.data || []) {
        map[entry.vehicle_id] = entry;
      }
      setSummaryMap(map);
    } catch { /* ignore — badges just won't show */ }
  }

  useEffect(() => { loadVehicles(); loadSummary(); }, []);

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
      setError(err.response?.data?.detail || t('Lỗi khi lưu', 'Save failed'));
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
    if (!confirm(t('Xóa xe này?', 'Delete this bike?'))) return;
    try {
      await client.delete(`/api/vehicles/${id}`);
      loadVehicles();
    } catch {
      setError(t('Xóa thất bại', 'Delete failed'));
    }
  }

  return (
    <div className="min-h-screen bg-[#ffffff] p-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between gap-2 mb-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10b981] animate-pulse" />
            <h1 className="text-xl font-bold text-[#374151]">{t('Phương tiện Đăng ký', 'Registered Vehicles')}</h1>
          </div>
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 bg-[#123b6d] hover:bg-[#0d2a4f] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {exporting ? t('Đang xuất...', 'Exporting...') : t('Xuất Excel', 'Export to Excel')}
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{t('Tổng xe đăng ký', 'Total registered bikes')}</p>
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
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{t('Đang chỉnh sửa', 'Editing')}</p>
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

        {/* Add/Edit Form + CSV Import — admin only: teacher is read-only (server also enforces 403) */}
        {isAdmin && (
        <>
        <div className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[#d1d5db]">
          <h2 className="text-[13px] font-bold text-[#374151] uppercase tracking-wider mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-[#10b981]" viewBox="0 0 24 24" fill="none">
              <path d="M12 4v16m8-8H4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            {editingId ? t('Chỉnh sửa xe', 'Edit bike') : t('Thêm xe mới', 'Add new bike')}
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
                  {t('Biển số', 'Plate')}
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
                  {t('Tên học sinh', 'Student name')}
                </label>
                <StudentAutocomplete
                  value={studentName}
                  onChange={setStudentName}
                  onSelect={(v) => {
                    setStudentName(v.student_name || '');
                    setPlate(v.plate_number || '');
                    setStudentClass(v.student_class || '');
                  }}
                  placeholder={t('Nguyễn Văn A', 'Nguyen Van A')}
                />
              </div>
              <div>
                <label className="block text-[11px] font-mono font-semibold text-[#6b7280] uppercase tracking-wider mb-1">
                  {t('Lớp', 'Class')}
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
                {editingId ? t('Lưu', 'Save') : t('Thêm xe', 'Add bike')}
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
                  {t('Hủy', 'Cancel')}
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
            {t('Nhập danh sách từ CSV', 'Import list from CSV')}
          </h2>
          <div className="flex flex-wrap gap-3 items-center">
            <label className="flex items-center gap-2 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg cursor-pointer transition-colors">
              <svg className="w-4 h-4 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
              {t('Chọn file CSV', 'Choose CSV file')}
              <input
                type="file"
                accept=".csv"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (!file) return;
                  setError('');
                  try {
                    // Step 1: dry-run
                    const dryRes = await client.post(
                      '/api/vehicles/import?dry_run=true',
                      (() => { const fd = new FormData(); fd.append('file', file); return fd; })(),
                      { headers: { 'Content-Type': 'multipart/form-data' } }
                    );
                    if (dryRes.data.errors?.length === 0 && dryRes.data.created === 0) {
                      // Empty file or only invalid rows
                      alert(t('File CSV không có dòng hợp lệ nào để nhập.', 'The CSV file has no valid rows to import.'));
                      return;
                    }
                    setCsvPreview({ dry_run_results: dryRes.data, filename: file.name, file });
                  } catch (err) {
                    setError(err.response?.data?.detail || t('Lỗi khi đọc file CSV', 'Error reading the CSV file'));
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
              {t('Tải file mẫu CSV', 'Download sample CSV')}
            </button>
          </div>
        </div>
        </>
        )}

        {/* Vehicles Table */}
        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            {t('Đang tải...', 'Loading...')}
          </div>
        ) : vehicles.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center border border-[#d1d5db]">
            <div className="w-12 h-12 rounded-xl bg-[#f4f6f9] flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-[#c92035]" viewBox="0 0 24 24" fill="none">
                <path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z" stroke="currentColor" strokeWidth="1.6"/>
                <path d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
              </svg>
            </div>
            <p className="text-[#6b7280] font-medium">{t('Chưa có xe nào được đăng ký', 'No bikes registered yet')}</p>
            <p className="text-[10px] font-mono text-[#9ca3af] mt-1">{t('Thêm xe mới hoặc nhập danh sách từ file CSV', 'Add a new bike or import a list from a CSV file')}</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left min-w-[600px]">
                <thead>
                  <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">{t('Biển số', 'Plate')}</th>
                    <th className="py-3 px-3 font-semibold">{t('Học sinh', 'Student')}</th>
                    <th className="py-3 px-3 font-semibold">{t('Lớp', 'Class')}</th>
                    <th className="py-3 px-3 font-semibold">{t('Vi phạm 30 ngày', 'Violations (30 days)')}</th>
                    <th className="py-3 px-4 text-right font-semibold">{t('Thao tác', 'Actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {vehicles.map((v) => {
                    const summ = summaryMap[v.id];
                    const recentCount = summ?.recent_count || 0;
                    const isRepeat = summ?.is_repeat_offender;
                    return (
                      <tr key={v.id} className={`hover:bg-[#ffffff] transition-colors ${editingId === v.id ? 'bg-[#f4f6f9]' : ''}`}>
                        <td className="py-3 px-4">
                          <span className="font-mono font-bold text-[11px] px-2 py-0.5 rounded bg-[#f4f6f9] text-[#374151] border border-[#d1d5db]">
                            {v.plate_number}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-medium">{v.student_name || '—'}</td>
                        <td className="py-3 px-3 font-mono text-[11px] text-[#6b7280]">{v.student_class || '—'}</td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5">
                            <span className={`font-mono font-bold text-[12px] ${recentCount > 0 ? 'text-[#c92035]' : 'text-[#10b981]'}`}>
                              {recentCount}
                            </span>
                            {isRepeat && (
                              <span className="px-1.5 py-0.5 bg-[#fee2e2] text-[#991b1b] rounded text-[10px] font-semibold font-mono border border-[#fca5a5]">
                                {t('TÁI PHẠM', 'REPEAT OFFENDER')}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => navigate(`/admin/students/${v.id}/violations`)}
                              className="px-3 py-1 rounded text-[11px] font-semibold text-[#3b82f6] hover:bg-[#dbeafe] transition-colors"
                            >
                              {t('Lịch sử', 'History')}
                            </button>
                            {isAdmin && (
                              <>
                                <button
                                  onClick={() => startEdit(v)}
                                  className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f8d7dc] transition-colors"
                                >
                                  {t('Sửa', 'Edit')}
                                </button>
                                <button
                                  onClick={() => handleDelete(v.id)}
                                  className="px-3 py-1 rounded text-[11px] font-semibold text-[#c92035] hover:bg-[#f8d7dc] transition-colors"
                                >
                                  {t('Xóa', 'Delete')}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 bg-[#f4f6f9] border-t border-[#d1d5db]">
              <span className="font-mono text-[11px] text-[#6b7280]">
                {t('Tổng', 'Total')}: <span className="font-bold text-[#374151]">{vehicles.length}</span> {t('xe', 'bikes')}
              </span>
            </div>
          </div>
        )}

        {/* Feature 11: CSV Dry-run Preview Modal */}
        {csvPreview && (
          <div
            className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
            onClick={() => setCsvPreview(null)}
          >
            <div
              className="bg-white rounded-xl shadow-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-4 border-b border-[#d1d5db]">
                <h2 className="text-base font-bold text-[#374151]">
                  {t('Xem trước CSV', 'CSV preview')} — {csvPreview.filename}
                </h2>
                <button
                  onClick={() => setCsvPreview(null)}
                  className="text-[#6b7280] hover:text-[#374151] text-xl leading-none px-2"
                >
                  ×
                </button>
              </div>
              <div className="p-5">
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="bg-[#d1fae5] rounded-lg p-3 text-center border border-[#6ee7b7]">
                    <p className="text-2xl font-bold font-mono text-[#065f46]">
                      {csvPreview.dry_run_results.created}
                    </p>
                    <p className="text-[11px] font-mono text-[#065f46]">{t('Sẽ thêm mới', 'Will be added')}</p>
                  </div>
                  <div className="bg-[#fef3c7] rounded-lg p-3 text-center border border-[#fcd34d]">
                    <p className="text-2xl font-bold font-mono text-[#92400e]">
                      {csvPreview.dry_run_results.skipped}
                    </p>
                    <p className="text-[11px] font-mono text-[#92400e]">{t('Bị bỏ qua (trùng)', 'Skipped (duplicate)')}</p>
                  </div>
                  <div className="bg-[#fee2e2] rounded-lg p-3 text-center border border-[#fca5a5]">
                    <p className="text-2xl font-bold font-mono text-[#991b1b]">
                      {csvPreview.dry_run_results.errors?.length || 0}
                    </p>
                    <p className="text-[11px] font-mono text-[#991b1b]">{t('Lỗi', 'Errors')}</p>
                  </div>
                </div>

                {csvPreview.dry_run_results.errors?.length > 0 && (
                  <div className="mb-4">
                    <p className="text-[11px] font-mono font-semibold text-[#991b1b] uppercase mb-2">
                      {t('Lỗi', 'Errors')} ({csvPreview.dry_run_results.errors.length})
                    </p>
                    <div className="bg-[#fef2f2] border border-[#fca5a5] rounded-lg p-3 max-h-32 overflow-y-auto">
                      {csvPreview.dry_run_results.errors.map((err, i) => (
                        <p key={i} className="text-[11px] font-mono text-[#991b1b]">
                          {t('Dòng', 'Row')} {err.row}: {err.message}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setCsvPreview(null)}
                    className="flex-1 bg-[#6b7280] hover:bg-[#4b5563] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
                  >
                    {t('Hủy bỏ', 'Cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      const file = csvPreview.file;
                      try {
                        const fd = new FormData();
                        fd.append('file', file);
                        const res = await client.post('/api/vehicles/import', fd, {
                          headers: { 'Content-Type': 'multipart/form-data' },
                        });
                        const d = res.data;
                        alert(t(`Đã nhập: ${d.created} mới, ${d.skipped} trùng, ${d.errors?.length || 0} lỗi`, `Imported: ${d.created} new, ${d.skipped} duplicates, ${d.errors?.length || 0} errors`));
                        if (d.errors?.length) {
                          alert(t('Lỗi: ', 'Errors: ') + d.errors.slice(0, 5).map(e => t(`Dòng ${e.row}: ${e.message}`, `Row ${e.row}: ${e.message}`)).join('\n'));
                        }
                        setCsvPreview(null);
                        loadVehicles();
                        loadSummary();
                      } catch (err) {
                        alert(t('Lỗi khi nhập: ', 'Import failed: ') + (err.response?.data?.detail || err.message));
                      }
                    }}
                    className="flex-1 bg-[#10b981] hover:bg-[#059669] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
                  >
                    {t('Xác nhận nhập', 'Confirm import')} ({csvPreview.dry_run_results.created} {t('mới', 'new')})
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
