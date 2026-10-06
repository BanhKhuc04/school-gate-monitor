import test from 'node:test';
import assert from 'node:assert/strict';
import { createAlertAudio } from '../src/utils/alertAudio.js';

function harness() {
  let now = 1000, next = 0;
  const timers = new Map(), beeps = [], speech = [];
  let cancelled = 0;
  const audio = createAlertAudio({
    beep: code => { beeps.push(code); return 0; },
    speak: text => speech.push(text), cancel: () => cancelled++,
    now: () => now, setTimer: (fn, delay) => { timers.set(++next, {fn, at: now + delay}); return next; },
    clearTimer: id => timers.delete(id), gateName: 'Cổng chính',
  });
  function advance(ms) {
    now += ms;
    for (const [id, timer] of [...timers]) if (timer.at <= now) { timers.delete(id); timer.fn(); }
  }
  const event = (code, status='confirmed', extra={}) => ({event_id:'e1', evidence_state:'persisted',
    violation_type:'NO_PLATE', issues:[{code, status}], ...extra});
  return {audio, advance, beeps, speech, event, timers, cancelled: () => cancelled};
}

test('pending/resolved/OCR-only never beep or speak', () => {
  const h=harness();
  for (const status of ['pending','deferred','resolved','conflict']) h.audio.accept(h.event('NO_HELMET',status));
  h.audio.accept(h.event('PLATE_LOW_CONFIDENCE')); h.advance(600);
  assert.deepEqual(h.beeps, []); assert.deepEqual(h.speech, []);
});

test('lost server speaker authorization is silent', () => {
  const h=harness();
  h.audio.accept(h.event('NO_HELMET','confirmed',{audio_authorized:false}));
  h.advance(600); h.advance(1);
  assert.deepEqual(h.beeps, []); assert.deepEqual(h.speech, []);
});
test('mixed OCR and confirmed helmet reads the helmet instruction', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET')); h.advance(600); h.advance(1);
  assert.deepEqual(h.beeps, ['NO_HELMET']);
  assert.match(h.speech[0], /đội mũ/); assert.doesNotMatch(h.speech[0], /biển số/);
});
test('issues-only payload is supported and failed evidence is silent', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET','confirmed',{violation_type:undefined}));
  h.advance(600); h.advance(1); assert.equal(h.speech.length,1);
  h.audio.accept(h.event('RIDING_THROUGH_GATE','confirmed',{evidence_state:'failed'}));
  h.advance(600); assert.equal(h.beeps.length,1);
});
test('dedup by sealed event rejects even a newly confirmed late issue', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET')); h.advance(600); h.advance(1);
  h.audio.accept(h.event('NO_HELMET')); h.advance(600); h.advance(1);
  assert.equal(h.speech.length,1);
  h.audio.accept(h.event('RIDING_THROUGH_GATE')); h.advance(600); h.advance(1);
  assert.equal(h.speech.length,1);
  // Lỗi thứ 2 của CÙNG xe (cùng event_id) không còi lại — chỉ xe khác/encounter
  // khác mới còi mới, tránh "còi liên tù tì" khi 1 xe phạm nhiều lỗi liên tiếp.
  assert.equal(h.beeps.length,1);
});
test('coalesces legacy same-event issues into the requested short sentence', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET')); h.audio.accept(h.event('RIDING_THROUGH_GATE'));
  h.advance(600); h.advance(1); assert.equal(h.beeps.length,1);
  assert.equal(h.speech[0], 'Không đội mũ, vui lòng dắt xe.');
});
test('dispose clears timers and speech before they can fire', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET')); h.audio.dispose(); h.advance(1000);
  assert.deepEqual(h.beeps,[]); assert.deepEqual(h.speech,[]); assert.equal(h.cancelled(),1);
});
test('old queued/replayed alerts are dropped', () => {
  const h=harness(); h.audio.accept(h.event('NO_HELMET')); h.advance(6000);
  h.audio.accept(h.event('RIDING_THROUGH_GATE','confirmed',{replayed:true})); h.advance(600);
  assert.deepEqual(h.beeps,[]); assert.deepEqual(h.speech,[]);
});
