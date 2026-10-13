const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { DailyQuota, dayKey } = require('./daily-quota');

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'daily-quota-'));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(dir)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(dir).startsWith('daily-quota-'));
    fs.rmSync(dir, { recursive: true, force: true });
  });
  let now = new Date('2026-10-13T15:59:59Z');
  const filename = path.join(dir, 'usage.json');
  return { filename, clock: () => now, advance: value => { now = new Date(value); } };
}

test('100 uploads per IP, then Shanghai midnight restores 100', t => {
  const f = fixture(t), quota = new DailyQuota(f.filename, 100, f.clock);
  for (let i = 0; i < 100; i++) assert.equal(quota.reserve('1.2.3.4'), '2026-10-13');
  assert.equal(quota.reserve('1.2.3.4'), false);
  assert.equal(quota.info('1.2.3.4').remaining, 0);
  assert.equal(quota.info('5.6.7.8').remaining, 100);
  f.advance('2026-10-13T16:00:00Z');
  assert.equal(quota.info('1.2.3.4').remaining, 100);
  assert.equal(quota.info('1.2.3.4').date, '2026-10-14');
});

test('counts survive process restarts within the same day', t => {
  const f = fixture(t), quota = new DailyQuota(f.filename, 100, f.clock);
  quota.reserve('1.2.3.4');
  assert.equal(new DailyQuota(f.filename, 100, f.clock).info('1.2.3.4').used, 1);
});

test('failed uploads refund only their reserved day', t => {
  const f = fixture(t), quota = new DailyQuota(f.filename, 100, f.clock);
  const old = quota.reserve('1.2.3.4');
  quota.refund('1.2.3.4', old);
  assert.equal(quota.info('1.2.3.4').used, 0);
  quota.reserve('1.2.3.4');
  f.advance('2026-10-13T16:00:00Z');
  quota.reserve('1.2.3.4');
  quota.refund('1.2.3.4', old);
  assert.equal(quota.info('1.2.3.4').used, 1, 'An old failed request must not refund a new-day upload');
});

test('legacy lifetime totals migrate to a fresh daily budget', t => {
  const f = fixture(t);
  fs.writeFileSync(f.filename, JSON.stringify({ '1.2.3.4': 100 }));
  const quota = new DailyQuota(f.filename, 100, f.clock);
  assert.equal(quota.info('1.2.3.4').remaining, 100);
  assert.equal(JSON.parse(fs.readFileSync(f.filename)).version, 2);
});

test('month boundaries use Shanghai calendar days', () => {
  assert.equal(dayKey(new Date('2026-10-31T15:59:59Z')), '2026-10-31');
  assert.equal(dayKey(new Date('2026-10-31T16:00:00Z')), '2026-11-01');
});
