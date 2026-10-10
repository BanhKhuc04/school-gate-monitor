import { localeOf } from '../i18n/LanguageContext';

/**
 * Format an ISO/SQL datetime string for display in the current UI language.
 * Falls back to the raw string if parsing fails.
 */
export function formatDate(isoStr, lang = 'vi') {
  if (!isoStr) return '';
  try {
    return new Date(isoStr).toLocaleString(localeOf(lang));
  } catch {
    return isoStr;
  }
}
