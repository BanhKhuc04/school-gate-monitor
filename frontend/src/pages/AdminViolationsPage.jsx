import { useState, useEffect, useCallback } from 'react';
import client, { API_BASE_URL } from '../api/client';
import { formatDate } from '../utils/format';
import { violationLabel, violationLabels } from '../utils/violationLabels';
import { speak } from '../utils/speak';
import { useLang, localeOf } from '../i18n/LanguageContext';
import { useAuth } from '../auth/AuthContext';
import StudentAutocomplete from '../components/StudentAutocomplete';

const PAGE_SIZE = 20;

// Color coding per violation type — Vanguard design system
const VIOLATION_COLORS = {
  NO_HELMET: {
    bg: 'bg-[#f8d7dc]', text: 'text-[#7a1422]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Không đội mũ bảo hiểm', en: 'No helmet',
  },
  PLATE_NOT_REGISTERED: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Biển số chưa đăng ký', en: 'Unregistered plate',
  },
  NO_PLATE: {
    bg: 'bg-[#fef3c7]', text: 'text-[#92400e]',
    border: 'border-[#fcd34d]', dot: 'bg-[#d97706]',
    label: 'Không có biển số', en: 'No plate',
  },
  PLATE_OBSCURED: {
    bg: 'bg-[#fef3c7]', text: 'text-[#92400e]',
    border: 'border-[#fcd34d]', dot: 'bg-[#d97706]',
    label: 'Biển số bị che/mờ', en: 'Plate obscured/blurry',
  },
  PLATE_UNREADABLE: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Không đọc được biển số', en: 'Plate unreadable',
  },
  PLATE_LOW_CONFIDENCE: {
    bg: 'bg-[#ede9fe]', text: 'text-[#5b21b6]',
    border: 'border-[#c4b5fd]', dot: 'bg-[#7c3aed]',
    label: 'Biển số cần kiểm tra', en: 'Plate needs review',
  },
  MULTIPLE: {
    bg: 'bg-[#dbe3ee]', text: 'text-[#7a1422]',
    border: 'border-[#bcc7de]', dot: 'bg-[#c92035]',
    label: 'Nhiều lỗi đồng thời', en: 'Multiple violations',
  },
  RIDING_THROUGH_GATE: {
    bg: 'bg-[#d9dfe8]', text: 'text-[#c92035]',
    border: 'border-[#f0aab3]', dot: 'bg-[#c92035]',
    label: 'Đi xe qua cổng', en: 'Riding through gate',
  },
  TOO_MANY_RIDERS: {
    bg: 'bg-[#fce7f3]', text: 'text-[#9d174d]',
    border: 'border-[#fbcfe8]', dot: 'bg-[#db2777]',
    label: 'Chở quá số người', en: 'Too many riders',
  },
};

// Feature 10: Status color map
const STATUS_COLORS = {
  pending: {
    bg: 'bg-[#fef3c7]', text: 'text-[#92400e]',
    border: 'border-[#fcd34d]', dot: 'bg-[#f59e0b]',
    label: 'Chưa xử lý', en: 'Pending',
  },
  needs_review: {
    bg: 'bg-[#ede9fe]', text: 'text-[#5b21b6]',
    border: 'border-[#c4b5fd]', dot: 'bg-[#7c3aed]',
    label: 'AI cần kiểm tra', en: 'AI needs review',
  },
  reviewed: {
    bg: 'bg-[#dbeafe]', text: 'text-[#1e40af]',
    border: 'border-[#93c5fd]', dot: 'bg-[#3b82f6]',
    label: 'Đã xem', en: 'Reviewed',
  },
  resolved: {
    bg: 'bg-[#d1fae5]', text: 'text-[#065f46]',
    border: 'border-[#6ee7b7]', dot: 'bg-[#10b981]',
    label: 'Đã xử lý', en: 'Resolved',
  },
  reopened: {
    bg: 'bg-[#fee2e2]', text: 'text-[#991b1b]',
    border: 'border-[#fca5a5]', dot: 'bg-[#ef4444]',
    label: 'Mở lại', en: 'Reopened',
  },
};

// Đợt 2, Bước 3: trạng thái ghép 2 camera trước+sau
const CORRELATION_COLORS = {
  matched: {
    bg: 'bg-[#d1fae5]', text: 'text-[#065f46]',
    border: 'border-[#6ee7b7]', dot: 'bg-[#10b981]',
    label: 'Ghép 2 camera', en: 'Matched 2 cameras',
  },
  needs_review: {
    bg: 'bg-[#fef3c7]', text: 'text-[#92400e]',
    border: 'border-[#fcd34d]', dot: 'bg-[#d97706]',
    label: 'Cần kiểm tra ghép', en: 'Match needs review',
  },
  unmatched: {
    bg: 'bg-[#f4f6f9]', text: 'text-[#6b7280]',
    border: 'border-[#d1d5db]', dot: 'bg-[#9ca3af]',
    label: 'Không ghép được', en: 'Not matched',
  },
};

// Label of a color entry in the UI language.
function labelOf(colors, lang) {
  return lang === 'en' ? colors.en : colors.label;
}

function CorrelationBadge({ status, onClick }) {
  const { lang, t } = useLang();
  // status: 'matched' | 'needs_review' | 'unmatched' | null
  if (!status) return null;
  const colors = CORRELATION_COLORS[status] || CORRELATION_COLORS.unmatched;
  const isClickable = onClick && status === 'matched';
  return (
    <button
      type="button"
      onClick={isClickable ? onClick : undefined}
      disabled={!isClickable}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${colors.bg} ${colors.text} ${colors.border} ${isClickable ? 'cursor-pointer hover:opacity-80 transition-opacity' : 'cursor-default'}`}
      title={isClickable ? t('Click để mở bản ghi camera kia', 'Click to open the other camera record') : labelOf(colors, lang)}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {labelOf(colors, lang)}
    </button>
  );
}

function ViolationBadge({ type }) {
  const { lang } = useLang();
  const colors = VIOLATION_COLORS[type] || VIOLATION_COLORS.NO_HELMET;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${colors.bg} ${colors.text} ${colors.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {labelOf(colors, lang)}
    </span>
  );
}

function StatusBadge({ status }) {
  const { lang } = useLang();
  const colors = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold font-mono border ${colors.bg} ${colors.text} ${colors.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {labelOf(colors, lang)}
    </span>
  );
}

function buildSummaryText(v, lang) {
  const plate = v.plate_matched || v.plate_read;
  const label = violationLabel(v.violation_type, lang);
  const time = new Date(v.timestamp).toLocaleTimeString(localeOf(lang), { hour12: false });
  if (lang === 'en') {
    const who = v.student_name ? `student ${v.student_name}, class ${v.student_class}` : 'identity unknown';
    const plateText = plate ? `plate ${plate}` : 'plate unreadable';
    return `Violation at ${time}. ${plateText}. ${who}. Violation: ${label}.`;
  }
  const who = v.student_name ? `học sinh ${v.student_name}, lớp ${v.student_class}` : 'chưa xác định danh tính';
  const plateText = plate ? `biển số ${plate}` : 'không đọc được biển số';
  return `Vi phạm lúc ${time}. ${plateText}. ${who}. Lỗi: ${label}.`;
}

// Feature 4 + 10 + Step 3: Enhanced modal with video, status, audit log, cross-camera link
function ViolationDetailModal({ violation, onClose, onUpdate, linkedViolation, onOpenLinked }) {
  const { user } = useAuth();
  const { lang, t } = useLang();
  const [auditLog, setAuditLog] = useState([]);
  const [updating, setUpdating] = useState(false);

  // Feature 10: Load audit log when modal opens
  useEffect(() => {
    if (!violation?.id) return;
    client.get(`/api/violations/${violation.id}/audit-log`)
      .then(res => setAuditLog(res.data || []))
      .catch(() => setAuditLog([]));
  }, [violation?.id]);

  if (!violation) return null;
  const v = violation;

  async function handleStatus(status) {
    setUpdating(true);
    try {
      await client.patch(`/api/violations/${v.id}/status`, { status });
      onUpdate?.();
      onClose();
    } catch (err) {
      alert(t('Lỗi: ', 'Error: ') + (err.response?.data?.detail || err.message));
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-[#d1d5db]">
          <h2 className="text-base font-bold text-[#374151]">{t('Chi tiết vi phạm', 'Violation details')}</h2>
          <button
            onClick={onClose}
            className="text-[#6b7280] hover:text-[#374151] text-xl leading-none px-2"
            aria-label={t('Đóng', 'Close')}
          >
            ×
          </button>
        </div>

        {/* Feature 4: Video clip — show video if available, else img */}
        {v.clip_url ? (
          <video
            controls
            muted
            className="w-full max-h-[50vh] bg-black"
            src={`${API_BASE_URL}${v.clip_url}`}
          />
        ) : v.snapshot_url ? (
          <img
            src={`${API_BASE_URL}${v.snapshot_url}`}
            alt={t('Ảnh chụp vi phạm', 'Violation snapshot')}
            className="w-full max-h-[50vh] object-contain bg-black"
          />
        ) : (
          <div className="w-full h-40 flex items-center justify-center bg-[#f4f6f9] text-[#9ca3af] text-sm">
            {t('Không có ảnh/video', 'No photo/video')}
          </div>
        )}

        <div className="p-5 space-y-3">
          {/* Feature 10: Badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <ViolationBadge type={v.violation_type} />
            <StatusBadge status={v.status || 'pending'} />
            {/* Đợt 2, Bước 3: badge ghép 2 camera */}
            <CorrelationBadge
              status={v.correlation_status}
              onClick={onOpenLinked && v.linked_violation_id ? () => onOpenLinked(v.linked_violation_id) : null}
            />
            {v.gate_id && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono border bg-[#f4f6f9] text-[#374151] border-[#d1d5db]">
                Camera: {v.gate_id}
              </span>
            )}
          </div>

          <dl className="grid grid-cols-3 gap-y-2 text-[13px]">
            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Thời gian', 'Time')}</dt>
            <dd className="col-span-2 text-[#374151] font-mono">
              {new Date(v.timestamp).toLocaleString(localeOf(lang), { hour12: false })}
            </dd>

            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Biển số đọc được', 'Plate read')}</dt>
            <dd className="col-span-2 text-[#374151] font-mono font-bold">{v.plate_read || '—'}</dd>

            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Biển số khớp', 'Matched plate')}</dt>
            <dd className="col-span-2 text-[#374151] font-mono">{v.plate_matched || '—'}</dd>

            {v.plate_confidence != null && (
              <>
                <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Độ tin cậy biển số', 'Plate confidence')}</dt>
                <dd className="col-span-2 text-[#374151] font-mono">{Math.round(v.plate_confidence * 100)}%</dd>
              </>
            )}

            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Học sinh', 'Student')}</dt>
            <dd className="col-span-2 text-[#374151] font-semibold">
              {v.student_name || <span className="text-[#9ca3af] font-normal">{t('Chưa xác định (biển số chưa đăng ký)', 'Unknown (plate not registered)')}</span>}
            </dd>

            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Lớp', 'Class')}</dt>
            <dd className="col-span-2 text-[#374151]">{v.student_class || '—'}</dd>

            <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Tư thế', 'Posture')}</dt>
            <dd className="col-span-2 text-[#374151]">{v.posture_status || '—'}</dd>

            {/* Đợt 2, Bước 3: thông tin ghép 2 camera */}
            {v.linked_violation_id != null && (
              <>
                <dt className="text-[#6b7280] font-mono text-[11px] uppercase">{t('Ghép với cổng kia', 'Matched with other gate')}</dt>
                <dd className="col-span-2 text-[#374151]">
                  <button
                    type="button"
                    onClick={() => onOpenLinked && onOpenLinked(v.linked_violation_id)}
                    className="font-mono text-[#123b6d] hover:text-[#0d2a4f] hover:underline"
                  >
                    {t('Mở vi phạm', 'Open violation')} #{v.linked_violation_id}
                  </button>
                  {linkedViolation && (
                    <span className="ml-2 text-[#6b7280] text-[11px]">
                      (gate {linkedViolation.gate_id || '—'} ·{' '}
                      {new Date(linkedViolation.timestamp).toLocaleTimeString(localeOf(lang), { hour12: false })})
                    </span>
                  )}
                </dd>
              </>
            )}
          </dl>

          {/* Feature 10: Status action buttons (admin/security/management only, not teacher) */}
          {user?.role !== 'teacher' && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleStatus('reviewed')}
                disabled={updating || v.status === 'reviewed'}
                className="flex items-center gap-1.5 bg-[#3b82f6] hover:bg-[#2563eb] disabled:opacity-40 text-white text-[12px] font-semibold py-2 px-3 rounded-lg transition-colors"
              >
                ✓ {t('Đánh dấu đã xem', 'Mark as reviewed')}
              </button>
              <button
                type="button"
                onClick={() => handleStatus('resolved')}
                disabled={updating || v.status === 'resolved'}
                className="flex items-center gap-1.5 bg-[#10b981] hover:bg-[#059669] disabled:opacity-40 text-white text-[12px] font-semibold py-2 px-3 rounded-lg transition-colors"
              >
                ✓ {t('Đánh dấu đã xử lý', 'Mark as resolved')}
              </button>
              <button
                type="button"
                onClick={() => handleStatus('reopened')}
                disabled={updating}
                className="flex items-center gap-1.5 bg-[#6b7280] hover:bg-[#4b5563] disabled:opacity-40 text-white text-[12px] font-semibold py-2 px-3 rounded-lg transition-colors"
              >
                ↺ {t('Mở lại', 'Reopen')}
              </button>
            </div>
          )}

          {/* Feature 10: Audit log */}
          {auditLog.length > 0 && (
            <div className="border border-[#d1d5db] rounded-lg p-3 bg-[#f9fafb]">
              <p className="text-[11px] font-mono font-semibold text-[#6b7280] uppercase mb-2">{t('Lịch sử xử lý', 'Handling history')}</p>
              <div className="space-y-1.5">
                {auditLog.map((entry) => (
                  <div key={entry.id} className="text-[12px] font-mono text-[#374151]">
                    <span className="font-semibold">{entry.actor_username}</span>
                    {t(' đã ', ' set ')}
                    <span className="text-[#10b981] font-semibold">
                      {(STATUS_COLORS[entry.action] && labelOf(STATUS_COLORS[entry.action], lang)) || entry.action}
                    </span>
                    {entry.note && <span className="text-[#6b7280]"> — {entry.note}</span>}
                    {t(' lúc ', ' at ')}
                    <span className="text-[#9ca3af]">{formatDate(entry.created_at, lang)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => speak(buildSummaryText(v, lang), lang)}
            className="flex items-center gap-2 bg-[#123b6d] hover:bg-[#0d2a4f] text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
              <path d="M11 5L6 9H2v6h4l5 4V5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
              <path d="M15.5 8.5a5 5 0 010 7M18.5 5.5a9 9 0 010 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            {t('Đọc to thông tin', 'Read aloud')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminViolationsPage() {
  const { lang, t } = useLang();
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filterPlate, setFilterPlate] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [selectedViolation, setSelectedViolation] = useState(null);
  const [linkedViolation, setLinkedViolation] = useState(null);
  const [filterVehicle, setFilterVehicle] = useState(null); // selected vehicle from autocomplete
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [clearing, setClearing] = useState(false);
  const [notice, setNotice] = useState('');

  // Bước 3: mở modal violation theo id (khi click "Mở vi phạm #X" trong modal).
  // Thử tìm trong list hiện tại trước để khỏi gọi API thừa (list đã load qua
  // /api/violations có thể đã chứa id này — tùy page), nếu không thấy thì fetch
  // qua endpoint /api/violations với plate filter không — chính xác nhất là fetch
  // /api/violations/{id} nhưng API chưa có route đó. Dùng tạm limit lớn + date
  // filter rộng để chắc chắn tìm được id. Tránh cho user stuck vì không mở
  // được bản ghi bên kia.
  const openLinkedViolation = useCallback(async (id) => {
    const found = violations.find(v => v.id === id);
    if (found) {
      setSelectedViolation(found);
      return;
    }
    try {
      const res = await client.get('/api/violations', { params: { limit: 200 } });
      const item = (res.data?.items || []).find(v => v.id === id);
      if (item) setSelectedViolation(item);
    } catch (err) {
      console.error('[AdminViolations] Không fetch được linked violation:', err);
    }
  }, [violations]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const params = { limit: PAGE_SIZE, offset };
    if (filterVehicle?.plate_number) params.plate = filterVehicle.plate_number;
    else if (filterPlate) params.plate = filterPlate;
    if (filterType) params.violation_type = filterType;
    if (filterDateFrom) params.date_from = filterDateFrom + 'T00:00:00';
    if (filterDateTo) params.date_to = filterDateTo + 'T23:59:59';
    try {
      const res = await client.get('/api/violations', { params });
      const data = res.data;
      setViolations(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || t('Không tải được danh sách vi phạm', 'Could not load violations'));
    } finally {
      setLoading(false);
    }
  }, [offset, filterPlate, filterType, filterDateFrom, filterDateTo, t]);

  useEffect(() => { load(); }, []);

  function handleFilter(e) {
    e.preventDefault();
    setOffset(0);
    load();
  }

  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const params = {};
      if (filterPlate) params.plate = filterPlate;
      if (filterType) params.violation_type = filterType;
      if (filterDateFrom) params.date_from = filterDateFrom + 'T00:00:00';
      if (filterDateTo) params.date_to = filterDateTo + 'T23:59:59';
      const res = await client.get('/api/violations/export', { params, responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vi_pham_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || t('Không xuất được file', 'Could not export file'));
    } finally {
      setExporting(false);
    }
  }

  // Xóa vi phạm: "test" = chỉ bản ghi sinh ra khi chạy video test (nhãn TEST);
  // "all" = tất cả (backend sao lưu DB + dời ảnh/clip vào data/backups trước).
  async function handleClear(scope) {
    const question = scope === 'test'
      ? t('Xóa tất cả vi phạm có nhãn TEST (sinh ra khi chạy video test)?', 'Delete all violations labelled TEST (created by test video runs)?')
      : t('Xóa TOÀN BỘ vi phạm? Dữ liệu và ảnh/clip được sao lưu vào data/backups trước khi xóa.', 'Delete ALL violations? Data and photos/clips are backed up to data/backups before deleting.');
    if (!window.confirm(question)) return;
    setClearing(true);
    setNotice('');
    try {
      const { data } = await client.post('/api/violations/clear', { scope });
      setNotice(t(
        `Đã xóa ${data.deleted} vi phạm${data.backup ? ` (sao lưu: ${data.backup})` : ''}.`,
        `Deleted ${data.deleted} violations${data.backup ? ` (backup: ${data.backup})` : ''}.`,
      ));
      setOffset(0);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || t('Không xóa được vi phạm', 'Could not delete violations'));
    } finally {
      setClearing(false);
    }
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
        <div className="flex items-center justify-between gap-2 mb-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#c92035] animate-pulse" />
            <h1 className="text-xl font-bold text-[#374151]">{t('Nhật ký Giám sát & Vi phạm Cổng trường', 'School Gate Monitoring & Violation Log')}</h1>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
          {isAdmin && (
            <>
              <button
                type="button"
                onClick={() => handleClear('test')}
                disabled={clearing}
                data-testid="clear-test-violations"
                className="bg-[#fef3c7] hover:bg-[#fde68a] disabled:opacity-50 text-[#92400e] border border-[#fcd34d] text-[12px] font-semibold py-2 px-3 rounded-lg transition-colors"
                title={t('Xóa các vi phạm có nhãn TEST (từ video test)', 'Delete violations labelled TEST (from test videos)')}
              >
                {clearing ? t('Đang xóa...', 'Deleting...') : t('Xóa vi phạm test', 'Delete test violations')}
              </button>
              <button
                type="button"
                onClick={() => handleClear('all')}
                disabled={clearing}
                data-testid="clear-all-violations"
                className="bg-white hover:bg-[#f8d7dc] disabled:opacity-50 text-[#c92035] border border-[#f0aab3] text-[12px] font-semibold py-2 px-3 rounded-lg transition-colors"
                title={t('Xóa toàn bộ vi phạm (có sao lưu trước khi xóa)', 'Delete all violations (backed up first)')}
              >
                {t('Xóa tất cả vi phạm', 'Delete all violations')}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-1.5 bg-[#123b6d] hover:bg-[#0d2a4f] disabled:opacity-50 text-white text-[12px] font-semibold py-2 px-4 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            {exporting ? t('Đang xuất...', 'Exporting...') : t('Xuất Excel', 'Export Excel')}
          </button>
          </div>
        </div>

        {notice && (
          <div className="mb-4 bg-[#e7f6ec] border border-[#a7dcb9] text-[#1e6b3a] px-4 py-2 rounded-xl text-[12px] font-semibold">
            {notice}
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl p-4 flex items-center justify-between shadow-sm border border-[#d1d5db]">
            <div>
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{t('Tổng vi phạm hôm nay', 'Total violations today')}</p>
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
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{violationLabel('NO_HELMET', lang)}</p>
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
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{violationLabel('PLATE_NOT_REGISTERED', lang)}</p>
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
              <p className="text-[10px] font-mono font-semibold uppercase text-[#6b7280] tracking-wider">{violationLabel('MULTIPLE', lang)}</p>
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
            {/* Feature 5: Smart autocomplete instead of raw plate text input */}
            <StudentAutocomplete
              value={filterPlate}
              onChange={v => {
                if (typeof v === 'string') setFilterPlate(v);
              }}
              onSelect={(v) => {
                setFilterVehicle(v);
                setFilterPlate('');
              }}
              placeholder={t('Tìm theo biển số hoặc tên...', 'Search by plate or name...')}
            />
            <div className="relative">
              <select
                className="w-full bg-[#f4f6f9] rounded-lg px-3 py-2 text-[12px] text-[#374151] border-0 outline-none appearance-none cursor-pointer pr-8 font-mono"
                value={filterType}
                onChange={e => setFilterType(e.target.value)}
              >
                <option value="">{t('Tất cả loại vi phạm', 'All violation types')}</option>
                {Object.entries(violationLabels(lang)).map(([k, v]) => (
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
              {t('Lọc', 'Filter')}
            </button>
            <button
              type="button"
              onClick={clearFilters}
              className="flex items-center gap-1.5 bg-[#f4f6f9] hover:bg-[#eceff3] text-[#374151] text-[12px] font-medium py-2 px-4 rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                <path d="M6 18L18 6M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              {t('Xóa lọc', 'Clear filters')}
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center text-[#6b7280] py-12">
            <div className="w-8 h-8 border-2 border-[#c92035] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            {t('Đang tải dữ liệu...', 'Loading data...')}
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
            <p className="text-[#6b7280] font-medium">{t('Không có vi phạm nào được ghi nhận', 'No violations recorded')}</p>
            <p className="text-[10px] font-mono text-[#9ca3af] mt-1">{t('Thử thay đổi bộ lọc hoặc chờ camera phát hiện vi phạm', 'Try changing the filters or wait for the cameras to detect a violation')}</p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-[#d1d5db] overflow-hidden">
            <div className="overflow-x-auto w-full">
              <table className="w-full text-left border-collapse min-w-[900px]">
                <thead>
                  <tr className="bg-[#f4f6f9] text-[#6b7280] font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4 font-semibold">{t('Thời gian', 'Time')}</th>
                    <th className="py-3 px-2 text-center font-semibold">{t('Ảnh', 'Photo')}</th>
                    <th className="py-3 px-2 font-semibold">{t('Loại vi phạm', 'Violation type')}</th>
                    <th className="py-3 px-2 font-semibold">{t('Trạng thái', 'Status')}</th>
                    <th className="py-3 px-2 font-semibold">{t('Biển số', 'Plate')}</th>
                    <th className="py-3 px-2 font-semibold">{t('Học sinh', 'Student')}</th>
                    <th className="py-3 px-2 font-semibold">{t('Lớp', 'Class')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f4f6f9] text-[12px] text-[#374151]">
                  {violations.map((v) => (
                    <tr
                      key={v.id}
                      className="hover:bg-[#f4f6f9] transition-colors cursor-pointer"
                      onClick={() => setSelectedViolation(v)}
                    >
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className="font-mono font-bold text-[11px]">
                          {new Date(v.timestamp).toLocaleTimeString(localeOf(lang), { hour12: false })}
                        </span>
                        <span className="block font-mono text-[10px] text-[#6b7280]">
                          {new Date(v.timestamp).toLocaleDateString(localeOf(lang))}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-center">
                        {v.snapshot_url ? (
                          <span className="inline-block w-20 h-14 rounded overflow-hidden border border-[#d1d5db] hover:opacity-80 transition-opacity">
                            <img
                              src={`${API_BASE_URL}${v.snapshot_url}`}
                              alt={t('Ảnh vi phạm', 'Violation photo')}
                              className="w-full h-full object-cover"
                            />
                          </span>
                        ) : (
                          <span className="text-[#d1d5db] font-mono text-[10px]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2">
                        <ViolationBadge type={v.violation_type} />
                        {v.is_test ? (
                          <span className="ml-1 font-mono text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#fde68a] text-[#92400e]"
                            title={t('Ghi nhận khi chạy video test, không phải camera thật', 'Recorded from a test video, not a real camera')}>TEST</span>
                        ) : null}
                      </td>
                      <td className="py-3 px-2">
                        <StatusBadge status={v.status || 'pending'} />
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
                <p className="font-mono text-[11px] text-[#6b7280]">
                  {t('Hiển thị', 'Showing')} <span className="font-bold text-[#374151]">{(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, total)}</span> / <span className="font-bold text-[#374151]">{total}</span> {t('vi phạm', 'violations')}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                  >
                    ← {t('Trước', 'Previous')}
                  </button>
                  <span className="font-mono text-[11px] font-semibold text-[#374151]">
                    {t('Trang', 'Page')} {currentPage}/{totalPages}
                  </span>
                  <button
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="px-3 py-1 rounded bg-white border border-[#d1d5db] text-[11px] font-mono font-semibold disabled:opacity-40 hover:bg-[#ffffff] transition-colors"
                  >
                    {t('Sau', 'Next')} →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <ViolationDetailModal
        violation={selectedViolation}
        linkedViolation={linkedViolation}
        onClose={() => { setSelectedViolation(null); setLinkedViolation(null); }}
        onUpdate={load}
        onOpenLinked={openLinkedViolation}
      />
    </div>
  );
}
