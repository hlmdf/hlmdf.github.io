// Exercise the real inline script, including startup and timers, without sending notifications.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(__dirname + '/index.html', 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
const node = id => {
  if (!elements.has(id)) elements.set(id, {
    value: '', style: {}, hidden: true, textContent: '', innerHTML: '',
    classList: { add() {}, remove() {}, toggle() {} },
    querySelector() { return { disabled: false }; },
    reset() { for (const id of ['p-current', 'p-new', 'p-confirm']) node(id).value = ''; },
  });
  return elements.get(id);
};
let timers = [], calls = [], notifications = [], pollCount = 0, failPassword = false;
let selectedChannels = [], configured = { email: false, wecom: false };
const context = {
  document: { getElementById: node, querySelectorAll: selector => selector === '#channels-row input:checked'
    ? selectedChannels.map(value => ({ value })) : [],
    createElement: () => ({ set textContent(value) { this.innerHTML = String(value); } }) },
  window: { addEventListener() {}, scrollTo() {} },
  setTimeout: (callback, delay) => { const t = { callback, delay }; timers.push(t); return t; },
  clearTimeout: t => { timers = timers.filter(x => x !== t); },
  Intl, Date, console,
  Notification: Object.assign(function(title, options) { notifications.push(options.body); }, { permission: 'granted' }),
  fetch: async (url, options) => {
    calls.push({ url, options });
    assert.ok(!url.startsWith('/'), 'API must stay under the deployed subpath');
    let data;
    if (url === 'api/session') data = { authenticated: true, csrf: 'csrf-test' };
    else if (url === 'api/reminders') data = options.method === 'POST' ? { id: 'created' } : [];
    else if (url === 'api/settings') data = { email: { configured: configured.email }, wecom: { webhook_configured: true, configured: configured.wecom }, serverchan: {sendkey_configured: true, configured: false}, pushplus: {token_configured: true, configured: false} };
    else if (url === 'api/test') data = { ok: true };
    else if (url === 'api/password') {
      if (failPassword) return { ok: false, status: 400, json: async () => ({ error: '当前密码不正确' }) };
      data = { ok: true };
    }
    else if (url.startsWith('api/poll')) {
      pollCount++;
      if (pollCount === 3) throw new Error('temporary offline');
      data = { cursor: pollCount, epoch: 'epoch-test', events: pollCount === 2 ? [{ content: '喝水' }] : [] };
    } else throw new Error('Unexpected request ' + url);
    return { ok: true, json: async () => data };
  },
};
context.window.Notification = context.Notification;
vm.createContext(context);
vm.runInContext(source, context);
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  await flush();
  assert.equal(pollCount, 1);
  assert.equal(node('app-panel').hidden, false);
  assert.ok(timers.some(t => t.delay === 15000), 'First poll must schedule the next poll');
  assert.ok(node('channels-row').innerHTML.includes('data-ch="wecom"'));
  node('s-wecom-webhook').value = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key';
  await context.window.testChannel('wecom');
  const saveIndex = calls.findIndex(c => c.url === 'api/settings' && c.options.method === 'PUT');
  const testIndex = calls.findIndex(c => c.url === 'api/test');
  assert.ok(saveIndex >= 0 && testIndex > saveIndex, 'WeCom test must save its configuration first');
  assert.equal(JSON.parse(calls[saveIndex].options.body).wecom.webhook, 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key');
  assert.equal(node('s-wecom-webhook').value, '', 'Saved webhook must not stay in the input');
  assert.ok(node('s-wecom-webhook').placeholder.includes('已保存'));
  for (const [channel, id, field] of [['serverchan', 's-serverchan-key', 'sendkey'], ['pushplus', 's-pushplus-token', 'token']]) {
    assert.ok(node('channels-row').innerHTML.includes('data-ch="' + channel + '"'));
    node(id).value = 'test-secret';
    const before = calls.length;
    await context.window.testChannel(channel);
    const sent = calls.slice(before);
    assert.equal(JSON.parse(sent[0].options.body)[channel][field], 'test-secret');
    assert.ok(sent.findIndex(c => c.url === 'api/test') > 0);
    assert.equal(node(id).value, '');
  }
  node('f-content').value = '测试提醒'; node('f-time').value = '09:00'; node('f-rule-type').value = 'daily';
  selectedChannels = ['email', 'wecom', 'serverchan', 'pushplus'];
  await node('btn-save').onclick();
  assert.ok(node('channel-validation').textContent.includes('邮件'));
  assert.ok(node('channel-validation').textContent.includes('企业微信'));
  assert.ok(node('channel-validation').textContent.includes('Server酱'));
  assert.ok(node('channel-validation').textContent.includes('PushPlus'));
  assert.equal(calls.filter(c => c.url === 'api/reminders' && c.options.method === 'POST').length, 0);
  selectedChannels = ['browser']; context.Notification.permission = 'denied';
  await node('btn-save').onclick();
  assert.ok(node('channel-validation').textContent.includes('授权浏览器通知'));
  assert.equal(calls.filter(c => c.url === 'api/reminders' && c.options.method === 'POST').length, 0);
  selectedChannels = ['wecom']; configured.wecom = true; context.Notification.permission = 'granted';
  await node('btn-save').onclick();
  await flush();
  assert.equal(calls.filter(c => c.url === 'api/reminders' && c.options.method === 'POST').length, 1);
  failPassword = true;
  node('p-current').value = 'wrong'; node('p-new').value = 'abc'; node('p-confirm').value = 'abc';
  await node('password-form').onsubmit({ preventDefault() {} });
  assert.equal(node('p-new').value, 'abc', 'A failed change should preserve entered values');
  assert.equal(node('app-panel').hidden, false);
  assert.equal(node('btn-change-password').disabled, false);
  await timers.find(t => t.delay === 15000).callback();
  await flush();
  assert.deepEqual(notifications, ['喝水']);
  assert.ok(calls.at(-1).url.includes('epoch=epoch-test'));
  assert.equal(calls.at(-1).options.headers['X-CSRF-Token'], 'csrf-test');
  await timers.find(t => t.delay === 15000).callback();
  await flush();
  assert.ok(timers.some(t => t.delay === 15000), 'Network errors must not stop polling');
  assert.equal(pollCount, 3);
  failPassword = false;
  node('p-current').value = 'old'; node('p-new').value = '1'; node('p-confirm').value = '1';
  await node('password-form').onsubmit({ preventDefault() {} });
  const change = calls.findLast(c => c.url === 'api/password');
  assert.equal(JSON.parse(change.options.body).new_password, '1');
  assert.equal(node('p-new').value, '', 'Password fields should clear on success');
  assert.equal(node('app-panel').hidden, true, 'Password change must log out the owner');
  assert.equal(node('login-panel').hidden, false);
  assert.ok(node('login-error').textContent.includes('新密码'));
  assert.ok(!timers.some(t => t.delay === 15000), 'Logout must stop notification polling');
  console.log('PASS: missing channel configuration and notification permission block saves; configured channels save; password logout and polling');
})().catch(error => { console.error(error); process.exitCode = 1; });
