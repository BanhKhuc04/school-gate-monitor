import test from 'node:test';
import assert from 'node:assert/strict';
import { describeAlert, formatPlate } from '../src/utils/alertDisplay.js';

test('formats motorbike and electric-bike plates', () => {
  assert.equal(formatPlate('89F123792'), '89-F1 237.92');
  assert.equal(formatPlate('29MD112345'), '29-MD1 123.45');
  assert.equal(formatPlate('30A1234'), '30-A 1234');
});

test('violation shows confirmed issue labels, never review-only notes', () => {
  const shown = describeAlert({ type: 'violation', violation_type: 'MULTIPLE', plate_read: null, issues: [
    { code: 'NO_HELMET', status: 'confirmed' }, { code: 'RIDING_THROUGH_GATE', status: 'confirmed' },
    { code: 'PLATE_UNREADABLE', status: 'needs_review' }] });
  assert.equal(shown.title, 'Không đội mũ + Xe chạy qua cổng');
  assert.equal(shown.detail, 'Chưa đọc được biển số');
  assert.equal(shown.tone, 'violation');
});

test('late paired plate is a silent notice, not a new violation', () => {
  const shown = describeAlert({ type: 'plate_paired', plate_read: '89F123792', registered: false });
  assert.equal(shown.title, 'Đã ghép biển 89-F1 237.92 vào lượt vi phạm');
  assert.equal(shown.detail, 'Biển chưa đăng ký');
});

test('recognised plate: registered student vs unknown plate', () => {
  const known = describeAlert({ type: 'plate_recognized', plate_read: '50A41234', registered: true,
    student_name: 'Nguyễn Văn An', student_class: '10A1' });
  assert.deepEqual(known, { tone: 'info', title: 'Đã nhận diện xe 50-A4 1234', detail: 'Nguyễn Văn An · Lớp 10A1' });
  const unknown = describeAlert({ type: 'plate_recognized', plate_read: '89F123792', registered: false });
  assert.equal(unknown.title, 'Biển số chưa đăng ký: 89-F1 237.92');
  assert.equal(unknown.tone, 'warning');
});
