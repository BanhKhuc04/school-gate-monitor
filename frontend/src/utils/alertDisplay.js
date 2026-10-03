// Human-readable Vietnamese text for one live notification (banner + list).
// Pure helper so node:test can cover it without a JSX runtime.
import { VIOLATION_LABELS } from './violationLabels.js';
import { getAlertPriority } from './alertPriority.js';

export function formatPlate(plate) {
  const m = (plate || '').match(/^(\d{2})([A-Z]{1,2}\d?)(\d{4,5})$/);
  if (!m) return plate || '';
  const n = m[3].length === 5 ? `${m[3].slice(0, 3)}.${m[3].slice(3)}` : m[3];
  return `${m[1]}-${m[2]} ${n}`;
}

export function describeAlert(data) {
  if (data?.type === 'plate_recognized') {
    const plate = formatPlate(data.plate_read);
    if (data.registered) {
      const who = [data.student_name, data.student_class && `Lớp ${data.student_class}`].filter(Boolean).join(' · ');
      return { tone: 'info', title: `Đã nhận diện xe ${plate}`, detail: who || 'Xe đã đăng ký' };
    }
    return { tone: 'warning', title: `Biển số chưa đăng ký: ${plate}`, detail: 'Không có trong danh sách xe của trường' };
  }
  const issues = Array.isArray(data?.issues) && data.issues.length
    ? data.issues.filter(i => i?.status === 'confirmed')
    : [{ code: data?.violation_type }];
  const labels = [...new Set(issues.map(i => VIOLATION_LABELS[i.code] || i.code).filter(Boolean))];
  const plate = data?.plate_matched || data?.plate_read;
  return {
    tone: getAlertPriority(data?.violation_type) === 'high' ? 'violation' : 'warning',
    title: labels.join(' + ') || 'Vi phạm',
    detail: plate ? `Biển ${formatPlate(plate)}` : 'Chưa đọc được biển số',
  };
}

export const TONE_COLORS = { violation: '#c92035', warning: '#d97706', info: '#15803d' };
