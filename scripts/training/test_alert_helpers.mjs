
// Inline stub: tránh 'vi' prefix trong regex match khi gọi từ test.
// Load alertFilter.js + alertPriority.js + alertAudio.js directly via node ESM.
import { speakableIssues, isSilentAlert } from '../../frontend/src/utils/alertFilter.js';
import { getAlertPriority } from '../../frontend/src/utils/alertPriority.js';
import { buildAlertMessage } from '../../frontend/src/utils/alertAudio.js';

let ok = 0, fail = 0;
function eq(name, got, want) {
  const pass = JSON.stringify(got) === JSON.stringify(want);
  if (pass) ok++;
  else { fail++; console.error(`FAIL ${name}: got=${JSON.stringify(got)} want=${JSON.stringify(want)}`); }
}

// 1) speakableIssues + isSilentAlert — helmet
const helmet = {
  violation_type: 'NO_HELMET',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_HELMET', status: 'confirmed'}],
};
eq('helmet speakable', speakableIssues(helmet), ['NO_HELMET']);
eq('helmet not silent', isSilentAlert(helmet), false);

// 2) silent: OCR-only
const ocr_only = {
  violation_type: 'NO_PLATE',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_PLATE', status: 'confirmed'}],
};
eq('ocr silent', isSilentAlert(ocr_only), true);
eq('ocr speakable empty', speakableIssues(ocr_only), []);

// 3) audio_authorized=false → all silent
const muted = { ...helmet, audio_authorized: false };
eq('muted silent', isSilentAlert(muted), true);
eq('muted speakable empty', speakableIssues(muted), []);

// 4) pending evidence → silent
const pending = { ...helmet, evidence_state: 'pending' };
eq('pending silent', isSilentAlert(pending), true);

// 5) priority
eq('priority helmet', getAlertPriority('NO_HELMET'), 'high');
eq('priority riding', getAlertPriority('RIDING_THROUGH_GATE'), 'high');
eq('priority plate', getAlertPriority('PLATE_NOT_REGISTERED'), 'medium');
eq('priority unknown', getAlertPriority('XXX'), 'medium');

// 6) buildAlertMessage — helmet only (chèn plate prefix nếu confirmed)
const helmet_msg = buildAlertMessage({
  violation_type: 'NO_HELMET',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'NO_HELMET', status: 'confirmed'}],
});
eq('helmet msg', helmet_msg, 'Vui lòng đội mũ.');

// 7) buildAlertMessage — helmet + riding
const both_msg = buildAlertMessage({
  violation_type: 'MULTIPLE',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [
    {code: 'NO_HELMET', status: 'confirmed'},
    {code: 'RIDING_THROUGH_GATE', status: 'confirmed'},
  ],
});
eq('helmet+riding msg', both_msg, 'Không đội mũ, vui lòng dắt xe.');

// 8) buildAlertMessage — with confirmed plate → insert "59 Z1 23 45."
const plate_msg = buildAlertMessage({
  violation_type: 'PLATE_NOT_REGISTERED',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_read: '59Z12345',
  plate_status: 'CONFIRMED',
  issues: [{code: 'PLATE_NOT_REGISTERED', status: 'confirmed'}],
});
eq('plate msg has plate prefix', plate_msg.includes('59 Z1 23 45.'), true);
eq('plate msg has reg suffix', plate_msg.includes('kiểm tra đăng ký xe'), true);

// 9) buildAlertMessage — unreadable plate (CẦN alert_finalized=true mới speakable)
const unread_msg = buildAlertMessage({
  violation_type: 'PLATE_UNREADABLE',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_status: 'UNREADABLE',
  alert_finalized: true,
  issues: [{code: 'PLATE_UNREADABLE', status: 'confirmed'}],
});
eq('unread msg', unread_msg, 'Không đọc được biển số.');

// 9b) unreadable KHÔNG có alert_finalized → silent (vẫn đúng — gate finalized)
const unread_pending = buildAlertMessage({
  violation_type: 'PLATE_UNREADABLE',
  evidence_state: 'committed',
  audio_authorized: true,
  plate_status: 'UNREADABLE',
  issues: [{code: 'PLATE_UNREADABLE', status: 'confirmed'}],
});
eq('unread not finalized → silent', isSilentAlert(unread_pending), true);

// 10) buildAlertMessage — no speakable issues
const none_msg = buildAlertMessage({
  violation_type: 'PLATE_OBSCURED',
  evidence_state: 'committed',
  audio_authorized: true,
  issues: [{code: 'PLATE_OBSCURED', status: 'confirmed'}],
});
eq('no speakable → empty', none_msg, '');

console.log(`RESULT ok=${ok} fail=${fail}`);
process.exit(fail > 0 ? 1 : 0);
