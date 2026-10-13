const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(__dirname + '/../../public/movies/index.html', 'utf8').match(/<script>\s*\(function\s*\(\)\s*\{([\s\S]*?)\}\)\(\);\s*<\/script>/)[1];
function declared(name) {
  const start = source.indexOf('  function ' + name + '(');
  return source.slice(start, source.indexOf('\n  }', start) + 4);
}
let pending, loadMore;
const ctx = {lastSearchList: [], lastSearchKeyword: 'test', searchNextStart: 0, searchHasMore: false, searchLoading: false, searchSeq: 1, searchTimer: null, clearTimeout,
  resultList: {}, searchStatus: {}, searchMoreBtn: {addEventListener: (_, fn) => loadMore = fn},
  renderSearchResults: list => {ctx.lastSearchList = list;}, doubanSearch: () => new Promise((resolve, reject) => {pending = {resolve, reject};})};
vm.createContext(ctx);
for (const name of ['normalizeSuggest', 'normalizeSearchPage', 'appendSearchPage', 'updateSearchMore', 'resetSearch']) vm.runInContext(declared(name), ctx);
const start = source.indexOf('  searchMoreBtn.addEventListener("click"');
vm.runInContext(source.slice(start, source.indexOf('\n  });', start) + 6), ctx);
const entry = id => ({url: '/subject/' + id, title: 'title'});
(async () => {
  ctx.appendSearchPage({results: [entry(1)], nextStart: 10, hasMore: true}, 'test');
  ctx.updateSearchMore(); assert.equal(ctx.searchMoreBtn.hidden, false);
  loadMore(); assert.equal(ctx.searchMoreBtn.disabled, true);
  pending.resolve({results: [entry(1), entry(2)], nextStart: 12, hasMore: false});
  await new Promise(setImmediate);
  assert.equal(ctx.lastSearchList.length, 2); assert.equal(ctx.searchMoreBtn.hidden, true);
  ctx.searchHasMore = true; loadMore(); pending.reject(new Error('offline'));
  await new Promise(setImmediate);
  assert.equal(ctx.lastSearchList.length, 2); assert.equal(ctx.searchMoreBtn.disabled, false); assert.equal(ctx.searchMoreBtn.hidden, false);
  loadMore(); const old = pending; ctx.resetSearch('new query');
  old.resolve({results: [entry(3)], nextStart: 20, hasMore: true});
  await new Promise(setImmediate);
  assert.equal(ctx.lastSearchList.length, 0); assert.equal(ctx.searchMoreBtn.hidden, true);
  const page = ctx.normalizeSearchPage({items: [], total: 0}, 0);
  assert.equal(page.hasMore, false);
  console.log('PASS: append, deduplication, end-of-results, retry and stale-response protection.');
})().catch(error => {console.error(error); process.exitCode = 1;});
