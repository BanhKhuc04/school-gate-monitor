// Alert silent filter — pure helper extracted from AlertBanner.jsx để test
// được trực tiếp bằng node:test (không cần bundler/JSX runtime).
//
// Pre-E3 fix plan: kiểm tra cả violation_type đơn VÀ issues[] (nếu có).
// Nếu violation_type OCR-only nhưng issues[] chứa ≥1 issue không OCR-only
// (ví dụ OCR + mũ), vẫn cần beep/TTS cho issue mũ.

export const SILENT_VIOLATION_TYPES = new Set([
  'NO_PLATE',
  'PLATE_OBSCURED',
  'PLATE_UNREADABLE',
  'PLATE_LOW_CONFIDENCE',
]);

/**
 * Kiểm tra một alert payload có nên im lặng (không beep, không TTS).
 *
 * @param {object|null|undefined} data - Alert payload từ WebSocket
 * @returns {boolean} true nếu im lặng, false nếu cần beep/TTS
 */
export function isSilentAlert(data) {
  return speakableIssues(data).length === 0;
}

export function speakableIssues(data) {
  if (data?.audio_authorized === false) return [];
  if (!data || ['pending', 'failed'].includes(data.evidence_state)) return [];
  const allowed = ['RIDING_THROUGH_GATE', 'NO_HELMET', 'TOO_MANY_RIDERS', 'PLATE_NOT_REGISTERED'];
  if (data.mirror_alerts_enabled === true) allowed.push('MISSING_MIRROR');
  if (data.alert_finalized === true && data.plate_status === 'UNREADABLE') allowed.push('PLATE_UNREADABLE');
  const issues = Array.isArray(data.issues) && data.issues.length
    ? data.issues
    : [{code: data.violation_type, status: 'confirmed'}]; // legacy payload adapter
  return [...new Set(issues.filter(it => it?.status === 'confirmed' && allowed.includes(it.code))
    .map(it => it.code))].sort((a, b) => allowed.indexOf(a) - allowed.indexOf(b));
}
