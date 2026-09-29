// Feature 3: Alert priority levels per violation type
export const ALERT_PRIORITY = {
  NO_HELMET: 'high',
  RIDING_THROUGH_GATE: 'high',
  TOO_MANY_RIDERS: 'high',
  NO_PLATE: 'medium',
  PLATE_OBSCURED: 'medium',
  PLATE_NOT_REGISTERED: 'medium',
  PLATE_UNREADABLE: 'medium',
  MULTIPLE: 'high',   // multiple violations = high priority
  default: 'medium',
};

/**
 * Get priority level for a violation type.
 * @param {string} violationType
 * @returns {'high'|'medium'|'low'}
 */
export function getAlertPriority(violationType) {
  return ALERT_PRIORITY[violationType] ?? ALERT_PRIORITY.default;
}
