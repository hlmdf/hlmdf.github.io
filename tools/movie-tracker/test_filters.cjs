const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(__dirname + '/../../public/movies/index.html', 'utf8');
const source = html.match(/<script>\s*\(function\s*\(\)\s*\{([\s\S]*?)\}\)\(\);\s*<\/script>/)[1];
function declared(name) {
  const start = source.indexOf('  function ' + name + '(');
  return source.slice(start, source.indexOf('\n  }', start) + 4);
}
const buttons = ['all', 'watched', 'doing', 'want'].map(status => ({getAttribute: () => status}));
const entries = [
  {id: 'old', title: '测试甲', type: 'movie', status: 'watched', year: 2020, rating: 9, regions: ['中国'], genres: ['剧情']},
  {id: 'middle', title: '测试乙', type: 'tv', status: 'doing', year: 2025, rating: 8, regions: ['美国'], genres: ['科幻']},
  {id: 'new', title: '测试丙', type: 'movie', status: 'want', year: 2020, rating: 7, regions: ['中国'], genres: ['剧情']}
];
const ctx = {items: entries, curStatus: 'all', curType: 'all', curRegion: 'all', curGenre: 'all', curDecade: 'all', keyword: '', curSort: 'added', document: {querySelectorAll: () => buttons}};
vm.createContext(ctx);
for (const name of ['match', 'matchFilters', 'sortMovies', 'renderCounts']) vm.runInContext(declared(name), ctx);
function counts() {
  ctx.renderCounts();
  return buttons.map(button => Number(button.innerHTML.match(/class="count">(\d+)/)[1]));
}
assert.deepEqual(counts(), [3, 1, 1, 1]);
for (const [key, value, expected] of [
  ['curType', 'movie', [2, 1, 0, 1]], ['curRegion', '美国', [1, 0, 1, 0]],
  ['curGenre', '剧情', [2, 1, 0, 1]], ['curDecade', '2020', [2, 1, 0, 1]],
  ['keyword', '丙', [1, 0, 0, 1]]
]) {
  ctx[key] = value; assert.deepEqual(counts(), expected);
  ctx[key] = key === 'keyword' ? '' : 'all';
}
ctx.curType = 'movie'; ctx.curRegion = '中国'; ctx.curGenre = '剧情'; ctx.curDecade = '2020'; ctx.curStatus = 'watched';
assert.deepEqual(counts(), [2, 1, 0, 1], 'Status tabs show available results in each status');
assert.deepEqual(entries.filter(ctx.match).map(x => x.id), ['old']);
ctx.keyword = '不存在'; assert.deepEqual(counts(), [0, 0, 0, 0]);
assert.deepEqual(ctx.sortMovies(entries.slice()).map(x => x.id), ['new', 'middle', 'old']);
assert.deepEqual(entries.map(x => x.id), ['old', 'middle', 'new'], 'Rendering must not reorder stored items');
ctx.curSort = 'year'; assert.equal(ctx.sortMovies(entries.slice())[0].id, 'middle');
ctx.curSort = 'rating'; assert.equal(ctx.sortMovies(entries.slice())[0].id, 'old');
assert.ok(source.includes('var curSort = "added"'));
assert.ok(source.includes('document.getElementById("sortFilter").value = "added"'));
console.log('PASS: default addition order, year/rating sorts, each filter, combined filters and status counts.');
