/**
 * Format an ISO/SQL datetime string for display (vi-VN locale).
 * Falls back to the raw string if parsing fails.
 */
export function formatDate(isoStr) {
  if (!isoStr) return '';
  try {
    return new Date(isoStr).toLocaleString('vi-VN');
  } catch {
    return isoStr;
  }
}
