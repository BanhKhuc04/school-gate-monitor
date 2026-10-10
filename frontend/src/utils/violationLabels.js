// Shared bilingual labels for violation_type, used by the violations table,
// the dashboard charts and the guard feed so labels never drift out of sync.
const VIOLATION_LABELS_BY_LANG = {
  NO_HELMET: { vi: 'Không đội mũ', en: 'No helmet' },
  PLATE_NOT_REGISTERED: { vi: 'Biển số lạ', en: 'Unregistered plate' },
  NO_PLATE: { vi: 'Không có biển số', en: 'No plate' },
  PLATE_OBSCURED: { vi: 'Biển số bị che/mờ', en: 'Plate obscured' },
  PLATE_UNREADABLE: { vi: 'Không đọc được biển số', en: 'Plate unreadable' },
  PLATE_LOW_CONFIDENCE: { vi: 'Biển số cần kiểm tra', en: 'Plate needs review' },
  MULTIPLE: { vi: 'Nhiều vi phạm', en: 'Multiple violations' },
  RIDING_THROUGH_GATE: { vi: 'Xe chạy qua cổng', en: 'Riding through gate' },
  TOO_MANY_RIDERS: { vi: 'Chở quá số người quy định', en: 'Too many riders' },
};

export const VIOLATION_TYPES = Object.keys(VIOLATION_LABELS_BY_LANG);

/** Nhãn hiển thị của 1 mã vi phạm theo ngôn ngữ; mã lạ → trả nguyên mã. */
export function violationLabel(type, lang = 'vi') {
  return VIOLATION_LABELS_BY_LANG[type]?.[lang] ?? type;
}

// Bản tiếng Việt dạng map phẳng — giữ cho các trang chưa chuyển sang violationLabel().
export const VIOLATION_LABELS = Object.fromEntries(
  VIOLATION_TYPES.map((type) => [type, VIOLATION_LABELS_BY_LANG[type].vi]),
);
