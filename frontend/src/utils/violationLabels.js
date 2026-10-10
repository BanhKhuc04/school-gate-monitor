// Shared labels for violation_type, used by the violations table, the
// dashboard charts and the guard feed so labels never drift out of sync.
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
  PLATE_FROM_REAR_CAMERA: 'Biển lấy từ camera sau',
  PLATE_PAIRING_AMBIGUOUS: 'Không ghép được biển (nhiều xe cùng lúc)',
};

export const VIOLATION_LABELS_EN = {
  NO_HELMET: 'No helmet',
  PLATE_NOT_REGISTERED: 'Unregistered plate',
  NO_PLATE: 'No plate',
  PLATE_OBSCURED: 'Plate obscured/blurry',
  PLATE_UNREADABLE: 'Plate unreadable',
  PLATE_LOW_CONFIDENCE: 'Plate needs review',
  MULTIPLE: 'Multiple violations',
  RIDING_THROUGH_GATE: 'Riding through gate',
  TOO_MANY_RIDERS: 'Too many riders',
  PLATE_FROM_REAR_CAMERA: 'Plate from rear camera',
  PLATE_PAIRING_AMBIGUOUS: 'Plate not matched (several bikes at once)',
};

/** Label map for the given UI language ('vi' | 'en'). */
export function violationLabels(lang = 'vi') {
  return lang === 'en' ? VIOLATION_LABELS_EN : VIOLATION_LABELS;
}

/** Display label of one violation code; unknown codes come back unchanged. */
export function violationLabel(type, lang = 'vi') {
  return violationLabels(lang)[type] ?? type;
}
