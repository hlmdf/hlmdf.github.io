const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(__dirname + '/../../public/movies/index.html', 'utf8');
const source = html.match(/<script>\s*\(function\s*\(\)\s*\{([\s\S]*?)\}\)\(\);\s*<\/script>/)[1];
new vm.Script(source); // Validate the entire page script as well as the exercised functions.
function declared(name) {
  const start = source.indexOf('  function ' + name + '(');
  assert.ok(start >= 0, name + ' exists');
  const end = source.indexOf('\n  }', start) + 4;
  return source.slice(start, end);
}
let rows = [], added = 0;
const resultList = {
  innerHTML: '',
  querySelectorAll() {
    rows = [...this.innerHTML.matchAll(/class="result-item/g)].map(() => ({
      addEventListener(event, handler) { this.click = handler; }
    }));
    return rows;
  }
};
const context = {
  items: [
    { title: '旧电影', year: 2001, type: 'movie', status: 'watched', douban: 'https://movie.douban.com/subject/100/?from=search' },
    { title: '手动剧集', year: 2020, type: 'tv', status: 'want', douban: '' }
  ], resultList, searchStatus: {}, addStatus: 'watched',
  statusName: status => ({ watched: '看过', doing: '在看', want: '想看' }[status] || '看过'),
  relayAttr: () => '', posterUrl: value => value, mustAdmin: () => true,
  toast() {}, addMovie() { added++; }
};
vm.createContext(context);
for (const name of ['esc', 'doubanSubjectId', 'listedMovie', 'renderSearchResults']) vm.runInContext(declared(name), context);
const results = [
  { title: '别名也能匹配', year: '2001', url: 'https://movie.douban.com/subject/100/' },
  { title: '手动剧集', year: '2020', url: 'https://movie.douban.com/subject/200/', episode: '10' },
  { title: '旧电影', year: '2001', url: 'https://movie.douban.com/subject/999/' }
];
context.renderSearchResults(results, '电影');
assert.equal((resultList.innerHTML.match(/class="result-item added"/g) || []).length, 2);
assert.ok(resultList.innerHTML.includes('已添加过 · 看过'));
assert.ok(resultList.innerHTML.includes('已添加过 · 想看'));
rows[0].click(); rows[1].click(); assert.equal(added, 0);
rows[2].click(); assert.equal(added, 1, 'Different Douban IDs with identical names must remain addable');
context.renderSearchResults([{
  title: '有简介', year: '1994', url: 'https://movie.douban.com/subject/300/',
  director: '弗兰克·德拉邦特', actors: '蒂姆·罗宾斯 / 摩根·弗里曼', regions: '美国', genres: '剧情', intro: '蒙冤入狱'
}], '电影');
assert.ok(resultList.innerHTML.includes('导演'));
assert.ok(resultList.innerHTML.includes('蒂姆·罗宾斯 / 摩根·弗里曼'));
assert.ok(resultList.innerHTML.includes('蒙冤入狱'));
context.isAdmin = true;
context.posterStyle = () => '#000';
context.rateLabels = ['', '很差', '较差', '还行', '推荐', '力荐'];
context.posterUrl = value => value;
context.relayAttr = () => '';
const rateBody = {innerHTML: ''};
context.document = {getElementById: id => id === 'rateBody' ? rateBody : {}};
vm.runInContext(declared('cardHtml'), context);
vm.runInContext(declared('paintRateDialog'), context);
const rated = context.cardHtml({id: 'm1', title: '甲', status: 'watched', personalRating: 4, type: 'movie', actors: ['演员甲'], regions: [], genres: [], director: '导演甲', year: 1994});
assert.ok(rated.includes('>评分 4 星</button>'));
assert.equal(rated.includes('rate-pop'), false);
const blank = context.cardHtml({id: 'm2', title: '乙', status: 'watched', personalRating: '', type: 'movie', actors: [], regions: [], genres: []});
assert.ok(blank.includes('>评分</button>'));
const want = context.cardHtml({id: 'm3', title: '丙', status: 'want', type: 'movie', actors: [], regions: [], genres: []});
assert.equal(want.includes('rate-btn'), false);
context.paintRateDialog({id: 'm1', title: '甲', personalRating: 4, director: '导演甲', actors: ['演员甲'], year: 1994, poster: ''});
assert.ok(rateBody.innerHTML.includes('当前 4 星'));
assert.equal(rateBody.innerHTML.includes('rate-intro'), false);
assert.ok(rateBody.innerHTML.includes('导演甲'));
assert.ok(rateBody.innerHTML.includes('演员甲'));
assert.ok(rateBody.innerHTML.includes('data-stars="5"'));
context.renderSearchResults([{title: '旧电影', year: '2001', url: 'https://movie.douban.com/subject/100/', intro: '完整简介不会被截断'}], '电影');
assert.ok(resultList.innerHTML.includes('class="rdelete"'));
assert.ok(resultList.innerHTML.includes('完整简介不会被截断'));
let removed = null;
context.askDelete = item => { removed = item.title; };
rows[0].click({target: {closest: sel => sel === '.rdelete'}});
assert.equal(removed, '旧电影');
let reminded = '';
context.saving = false;
context.rateLabels = ['', '很差', '较差', '还行', '推荐', '力荐'];
context.askConfirm = text => { reminded = text; };
context.doubanSubjectId = () => '1';
context.render = () => {};
context.savePersonalRating = () => { context.saved = true; };
context.api = () => Promise.resolve({ loggedIn: true });
vm.runInContext(declared('choosePersonalRating'), context);
context.choosePersonalRating({title: '甲', personalRating: 4, douban: 'https://movie.douban.com/subject/1/'}, 5);
assert.ok(reminded.includes('覆盖豆瓣'));
assert.equal(context.saved, undefined);
context.choosePersonalRating({title: '乙', personalRating: '', douban: 'https://movie.douban.com/subject/1/'}, 3);

// Run the real management-password submit handler with isolated form/session mocks.
const nodes = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, { value: '', textContent: '', disabled: false, addEventListener(event, fn) { this[event] = fn; } });
  return nodes.get(id);
};
let loggedOut = false, loginOpened = false, failure = false, sentPath;
context.document = { getElementById: node };
context.passwordForm = node('passwordForm'); context.passwordError = node('passwordError'); context.loginError = node('loginError');
context.closePasswordModal = () => {}; context.closeModal = () => {};
context.setLoggedIn = on => { loggedOut = !on; };
context.openLogin = () => { loginOpened = true; };
context.api = (path, opts) => {
  sentPath = path;
  assert.equal(opts.body.new_password, '1');
  return failure ? Promise.reject(new Error('当前管理密码不正确')) : Promise.resolve({ ok: true });
};
const start = source.indexOf('  passwordForm.addEventListener("submit"');
const end = source.indexOf('\n  });', start) + 6;
vm.runInContext(source.slice(start, end), context);
(async () => {
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(context.saved, true);
  node('currentAdminPassword').value = 'old'; node('newAdminPassword').value = '1'; node('confirmAdminPassword').value = '1';
  failure = true;
  context.passwordForm.submit({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(loggedOut, false);
  assert.ok(context.passwordError.textContent.includes('当前管理密码不正确'));
  failure = false;
  context.passwordForm.submit({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(sentPath, '/api/password');
  assert.equal(loggedOut, true); assert.equal(loginOpened, true);
  assert.ok(context.loginError.textContent.includes('新密码'));
  assert.equal(node('passwordSave').disabled, false);
  console.log('PASS: existing movie badges and click protection; management-password change logs out, failure keeps login');
})().catch(error => { console.error(error); process.exitCode = 1; });
