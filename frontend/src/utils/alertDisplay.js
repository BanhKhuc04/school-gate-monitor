// Human-readable text for one live notification (banner + list), in the UI
// language ('vi' default, 'en').
// Pure helper so node:test can cover it without a JSX runtime.
import { violationLabel } from './violationLabels.js';
import { getAlertPriority } from './alertPriority.js';

export function formatPlate(plate) {
  const m = (plate || '').match(/^(\d{2})([A-Z]{1,2}\d?)(\d{4,5})$/);
  if (!m) return plate || '';
  const n = m[3].length === 5 ? `${m[3].slice(0, 3)}.${m[3].slice(3)}` : m[3];
  return `${m[1]}-${m[2]} ${n}`;
}

export function describeAlert(data, lang = 'vi') {
  const t = (vi, en) => (lang === 'en' ? en : vi);
  if (data?.type === 'plate_recognized') {
    const plate = formatPlate(data.plate_read);
    if (data.registered) {
      const who = [data.student_name, data.student_class && t(`Lớp ${data.student_class}`, `Class ${data.student_class}`)].filter(Boolean).join(' · ');
      return { tone: 'info', title: t(`Đã nhận diện xe ${plate}`, `Recognized bike ${plate}`), detail: who || t('Xe đã đăng ký', 'Registered bike') };
    }
    return { tone: 'warning', title: t(`Biển số chưa đăng ký: ${plate}`, `Unregistered plate: ${plate}`), detail: t('Không có trong danh sách xe của trường', 'Not on the school vehicle list') };
  }
  if (data?.type === 'gate_pass') {
    const plate = data.plate_read ? formatPlate(data.plate_read) : '';
    return plate
      ? { tone: 'info', title: t(`Xe qua cổng: ${plate}`, `Bike passed gate: ${plate}`), detail: data.student_name || t('Không vi phạm', 'No violation') }
      : { tone: 'warning', title: t('Xe qua cổng', 'Bike passed gate'), detail: t('Không đọc được biển số', 'Plate unreadable') };
  }
  if (data?.type === 'plate_paired') {
    const plate = formatPlate(data.plate_read);
    const who = [data.student_name, data.student_class && t(`Lớp ${data.student_class}`, `Class ${data.student_class}`)].filter(Boolean).join(' · ');
    return { tone: data.registered ? 'info' : 'warning', title: t(`Đã ghép biển ${plate} vào lượt vi phạm`, `Matched plate ${plate} to the violation`),
      detail: data.registered ? (who || t('Xe đã đăng ký', 'Registered bike')) : t('Biển chưa đăng ký', 'Unregistered plate') };
  }
  const issues = Array.isArray(data?.issues) && data.issues.length
    ? data.issues.filter(i => i?.status === 'confirmed')
    : [{ code: data?.violation_type }];
  const labels = [...new Set(issues.map(i => violationLabel(i.code, lang)).filter(Boolean))];
  const plate = data?.plate_matched || data?.plate_read;
  return {
    tone: getAlertPriority(data?.violation_type) === 'high' ? 'violation' : 'warning',
    title: labels.join(' + ') || t('Vi phạm', 'Violation'),
    detail: plate ? t(`Biển ${formatPlate(plate)}`, `Plate ${formatPlate(plate)}`) : t('Chưa đọc được biển số', 'Plate not read yet'),
  };
}

export const TONE_COLORS = { violation: '#c92035', warning: '#d97706', info: '#15803d' };
