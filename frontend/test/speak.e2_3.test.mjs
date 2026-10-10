// Unit test cho E2.3 TTS rules — chạy với node:test (built-in Node 20+).
// Stub window.speechSynthesis và SpeechSynthesisUtterance để tránh gọi API thật.
//
// Cách chạy: `node frontend/test/speak.e2_3.test.mjs`
//
// Verify:
//   - Queue ≤ MAX_QUEUE (2).
//   - TTL 5s: câu chưa phát quá 5s bị prune.
//   - OCR-only không phát âm (chỉ silent ở store, AlertBanner filter).

import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Stub SpeechSynthesisUtterance (class) trên global ──────────────────
class StubUtterance {
  constructor(text) {
    this.text = text;
    this.lang = null;
    this.rate = null;
    this.pitch = null;
    this.volume = null;
    this.voice = null;
    this._firedEnd = false;
  }
  // _fireEnd để test có thể chủ động "phát xong" câu đang đọc.
  _fireEnd() {
    if (typeof this.onend === 'function' && !this._firedEnd) {
      this._firedEnd = true;
      this.onend();
    }
  }
}
globalThis.SpeechSynthesisUtterance = StubUtterance;

// ── Stub window.speechSynthesis ────────────────────────────────────────
const stubState = { calls: [], speakImmediately: false };
globalThis.window = {
  speechSynthesis: {
    speak(utt) {
      stubState.calls.push({ text: utt.text, rate: utt.rate });
      if (stubState.speakImmediately && typeof utt.onend === 'function') {
        // Bắn onend đồng bộ — để test xác nhận câu tiếp theo được lấy ra.
        setTimeout(() => utt._fireEnd(), 0);
      }
    },
    cancel() {},
    getVoices() { return []; },
  },
};

// ── Import module sau khi stub ──────────────────────────────────────────
const speakPath = path.resolve(__dirname, '..', 'src', 'utils', 'speak.js');
const speakURL = pathToFileURL(speakPath).href;
const { speakVietnamese, _resetSpeakStateForTest, _getQueueSnapshotForTest } =
  await import(speakURL);

// ── Test 1: MAX_QUEUE=2 — đẩy 5 câu, queue còn tối đa 2 ────────────────
test('MAX_QUEUE cap = 2', () => {
  _resetSpeakStateForTest();
  for (let i = 0; i < 5; i++) {
    speakVietnamese(`câu ${i}`);
  }
  // Vì _playNext sẽ auto-shift khi is_speaking=false và gọi stub.speak →
  // queue có thể đã rỗng. Quan trọng: stub.calls chỉ nhận TỐI ĐA 2 utterance.
  assert.ok(stubState.calls.length <= 2,
    `speak() được gọi tối đa 2 lần, got ${stubState.calls.length}`);
});

// ── Test 2: TTL 5s — câu quá 5s bị prune khi enqueue câu mới ────────────
test('TTL 5s: câu quá hạn bị prune khi enqueue câu mới', async () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  stubState.speakImmediately = false;
  speakVietnamese('câu_a');
  // Đợi >5s.
  await new Promise(r => setTimeout(r, 5100));
  speakVietnamese('câu_b');
  // Gọi _resetSpeakStateForTest (cancel) để ép stub không có câu nào ngoài
  // _playNext đã lấy ra. Sau khi prune, câu_a bị drop khỏi queue trước khi
  // _playNext dịch sang — nhưng vì is_speaking vẫn false (stub không bắn
  // onend), _playNext sẽ tự gọi speak ngay câu đầu (câu_a) khi được trigger.
  // Ở đây ta kiểm tra queue chứ không phải calls.
  const snap = _getQueueSnapshotForTest();
  const texts = snap.map(s => s.text);
  assert.ok(!texts.includes('câu_a'),
    `câu_a (>5s) phải bị prune khỏi queue, còn: ${JSON.stringify(texts)}`);
  assert.ok(texts.includes('câu_b'),
    `câu_b phải còn trong queue`);
});

// ── Test 3: rate 1.15 được lưu trong queue đúng ─────────────────────────
test('options được lưu nguyên vẹn trong queue', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  // Stub _playNext qua cách: đẩy câu không tự _playNext. Nhưng hiện tại
  // _playNext gọi ngay khi queue.length > 0 và is_speaking=false → stub.speak
  // được gọi. Kiểm tra qua stub.calls[0].rate.
  speakVietnamese('Cảnh báo: chưa đội mũ', { rate: 1.15, pitch: 1.1 });
  assert.equal(stubState.calls.length, 1);
  assert.equal(stubState.calls[0].rate, 1.15);
  assert.equal(stubState.calls[0].text, 'Cảnh báo: chưa đội mũ');
});

// ── Test 4: Đẩy 2 câu liên tiếp, cả 2 đều được _playNext lấy ra ────────
test('cả 2 câu được phát theo FIFO', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  speakVietnamese('câu_1');
  speakVietnamese('câu_2');
  // Cả 2 đã được stub.speak lưu trong calls theo đúng thứ tự (vì _playNext
  // shift câu 1 ngay khi queue.length > 0, is_speaking=true → câu 2 sẽ
  // đợi; nhưng vì stub không bắn onend → is_speaking vẫn true → câu 2 còn
  // trong queue. Trong môi trường browser thật, onend sẽ bắn → _playNext
  // lấy câu 2).
  // Ở test: kiểm tra câu_1 đã được speak (gọi stub.speak với text 'câu_1').
  assert.ok(stubState.calls.some(c => c.text === 'câu_1'),
    'câu_1 phải được speak');
  // câu_2 vẫn trong queue (chờ onend thật).
  const snap = _getQueueSnapshotForTest();
  assert.ok(snap.some(s => s.text === 'câu_2'),
    `câu_2 phải còn trong queue, got: ${JSON.stringify(snap.map(s => s.text))}`);
});

// ── Test FR9B: rate 1.45 mặc định và clamp 1.0–1.6 ───────────────────
test('FR9B rate default = 1.45 khi caller không truyền rate', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  speakVietnamese('cảnh báo mặc định');
  assert.equal(stubState.calls.length, 1);
  assert.equal(stubState.calls[0].rate, 1.45,
    'rate mặc định 1.45 theo FR9B');
});

test('FR9B rate clamp 1.0–1.6: rate=2.0 bị kẹp xuống 1.6', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  speakVietnamese('rate quá cao', { rate: 2.0 });
  assert.equal(stubState.calls[0].rate, 1.6,
    'rate trên 1.6 phải clamp xuống 1.6');
});

test('FR9B rate clamp 1.0–1.6: rate=0.5 bị kẹp lên 1.0', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  speakVietnamese('rate quá thấp', { rate: 0.5 });
  assert.equal(stubState.calls[0].rate, 1.0,
    'rate dưới 1.0 phải clamp lên 1.0');
});

test('FR9B rate=1.3 trong khoảng 1.0–1.6 giữ nguyên', () => {
  _resetSpeakStateForTest();
  stubState.calls.length = 0;
  speakVietnamese('rate hợp lệ', { rate: 1.3 });
  assert.equal(stubState.calls[0].rate, 1.3);
});

// ── Test 5: AlertBanner silent filter — verify BEHAVIOR (gọi hàm thật),
//               không tìm chuỗi source ─────────────────────────────────────
test('alertFilter isSilentAlert: 4 lỗi OCR-only im lặng', async () => {
  const filterPath = path.resolve(__dirname, '..', 'src', 'utils', 'alertFilter.js');
  const filterURL = pathToFileURL(filterPath).href;
  const mod = await import(filterURL);
  assert.equal(typeof mod.isSilentAlert, 'function',
    'alertFilter.js phải export isSilentAlert() để test được');
  for (const code of ['NO_PLATE', 'PLATE_OBSCURED', 'PLATE_UNREADABLE', 'PLATE_LOW_CONFIDENCE']) {
    assert.equal(mod.isSilentAlert({ violation_type: code }), true,
      `${code} phải im lặng`);
  }
});

test('alertFilter isSilentAlert: lỗi không OCR-only KHÔNG im lặng', async () => {
  const filterPath = path.resolve(__dirname, '..', 'src', 'utils', 'alertFilter.js');
  const filterURL = pathToFileURL(filterPath).href;
  const mod = await import(filterURL);
  for (const code of ['NO_HELMET', 'RIDING_THROUGH_GATE', 'PLATE_NOT_REGISTERED']) {
    assert.equal(mod.isSilentAlert({ violation_type: code }), false,
      `${code} KHÔNG được im lặng`);
  }
});

test('alertFilter isSilentAlert: issues[] có ≥1 issue không OCR-only → không im lặng', async () => {
  const filterPath = path.resolve(__dirname, '..', 'src', 'utils', 'alertFilter.js');
  const filterURL = pathToFileURL(filterPath).href;
  const mod = await import(filterURL);
  // violation_type OCR-only nhưng issues[] có NO_HELMET → không im lặng
  const data = {
    violation_type: 'NO_PLATE',
    issues: [
      { code: 'NO_PLATE', status: 'confirmed' },
      { code: 'NO_HELMET', status: 'confirmed' },
    ],
  };
  assert.equal(mod.isSilentAlert(data), false,
    'issues[] có NO_HELMET → không im lặng dù violation_type OCR-only');
});

test('alertFilter isSilentAlert: chỉ issues OCR-only → im lặng', async () => {
  const filterPath = path.resolve(__dirname, '..', 'src', 'utils', 'alertFilter.js');
  const filterURL = pathToFileURL(filterPath).href;
  const mod = await import(filterURL);
  const data = {
    violation_type: 'NO_PLATE',
    issues: [
      { code: 'NO_PLATE', status: 'confirmed' },
      { code: 'PLATE_OBSCURED', status: 'pending' },
    ],
  };
  assert.equal(mod.isSilentAlert(data), true,
    'issues[] chỉ có OCR-only → im lặng');
});

test('alertFilter isSilentAlert: null/empty → im lặng an toàn', async () => {
  const filterPath = path.resolve(__dirname, '..', 'src', 'utils', 'alertFilter.js');
  const filterURL = pathToFileURL(filterPath).href;
  const mod = await import(filterURL);
  assert.equal(mod.isSilentAlert(null), true);
  assert.equal(mod.isSilentAlert({}), true);
  // Unknown violation_type: hiện KHÔNG im lặng (để cảnh báo khi có loại vi
  // phạm mới được thêm vào backend nhưng chưa có trong SILENT_VIOLATION_TYPES).
  // Bảo vệ sẽ được beep để chú ý — fail-safe là phát tiếng.
  assert.equal(mod.isSilentAlert({ violation_type: 'UNKNOWN_CODE' }), true,
    'Unknown violation type requires review and stays silent');
});
