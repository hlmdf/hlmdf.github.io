const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(__dirname + '/../../public/movies/index.html', 'utf8');
const source = html.match(/<script>\s*\(function\s*\(\)\s*\{([\s\S]*?)\}\)\(\);\s*<\/script>/)[1];
new vm.Script(source);
function declared(name) {
  const start = source.indexOf('  function ' + name + '(');
  return source.slice(start, source.indexOf('\n  }', start) + 4);
}
let opened = 0, continued = [], warnings = 0;
const nodes = {reviewTags: {value: ''}, reviewPrivate: {checked: false}};
const ctx = {mustAdmin: () => true, saving: false, listedCopy: () => null,
  openWatchedReview: () => opened++, continueAddMovie: data => continued.push(data),
  closeWatchedReview: () => {ctx.pendingWatchedReview = null;}, toast: () => warnings++,
  document: {getElementById: id => nodes[id]}, reviewComment: {value: ''}, reviewRating: ''};
vm.createContext(ctx);
vm.runInContext(declared('addMovie'), ctx);
vm.runInContext(declared('submitWatchedReview'), ctx);
ctx.addMovie({status: 'watched'}, {});
assert.equal(opened, 1);
for (const status of ['want', 'doing']) ctx.addMovie({status}, {});
assert.equal(continued.length, 2);
assert.equal(opened, 1);
ctx.pendingWatchedReview = {data: {title: '测试', status: 'watched'}, el: {}};
ctx.submitWatchedReview({preventDefault() {}});
assert.equal(continued.at(-1).personalRating, '');
assert.equal(continued.at(-1).doubanPrivate, false);
ctx.pendingWatchedReview = {data: {title: '测试', rating: 8.5, status: 'watched'}, el: {}};
ctx.reviewRating = 5; nodes.reviewTags.value = ' 剧情   科幻 '; nodes.reviewPrivate.checked = true;
ctx.reviewComment.value = '😀'.repeat(350);
ctx.submitWatchedReview({preventDefault() {}});
assert.equal(continued.at(-1).personalRating, 5);
assert.equal(continued.at(-1).rating, 8.5);
assert.equal(continued.at(-1).doubanPrivate, true);
assert.equal(continued.at(-1).tags.join(' '), '剧情 科幻');
ctx.pendingWatchedReview = {data: {}, el: {}};
ctx.reviewComment.value += '字';
const count = continued.length;
ctx.submitWatchedReview({preventDefault() {}});
assert.equal(continued.length, count);
assert.equal(warnings, 1);
console.log('Watched review flow passed: optional fields, five stars, privacy, Unicode limit, direct want/doing.');
