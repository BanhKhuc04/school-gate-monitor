// Shared Vietnamese labels for violation_type, used by both the violations
// table and the dashboard charts so labels never drift out of sync.
export const VIOLATION_LABELS = {
  NO_HELMET: 'Không đội mũ',
  PLATE_NOT_REGISTERED: 'Biển số lạ',
  NO_PLATE: 'Không có biển số',
  PLATE_OBSCURED: 'Biển số bị che/mờ',
  PLATE_UNREADABLE: 'Không đọc được biển số',
  PLATE_LOW_CONFIDENCE: 'Biển số cần kiểm tra',
  MULTIPLE: 'Nhiều vi phạm',
  RIDING_THROUGH_GATE: 'Xe chạy qua cổng',
  TOO_MANY_RIDERS: 'Chở quá số người quy định',
};

// Danh sách lỗi cụ thể của 1 bản ghi/cảnh báo. violation_type chỉ là "MULTIPLE"
// khi có nhiều lỗi — violation_details (chuỗi "A,B" từ DB hoặc mảng từ WebSocket)
// mới cho biết đó là những lỗi nào.
export function violationDetailList(v) {
  const raw = Array.isArray(v?.violation_details)
    ? v.violation_details
    : String(v?.violation_details || '').split(',');
  const list = raw.map(s => s.trim()).filter(Boolean);
  return list.length ? list : [v?.violation_type].filter(Boolean);
}

export function violationText(v) {
  return violationDetailList(v).map(t => VIOLATION_LABELS[t] || t).join(' + ');
}
