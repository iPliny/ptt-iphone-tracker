const test = require('node:test');
const assert = require('node:assert/strict');
const { modelUrl, compareStorage, esc } = require('../site/common.js');

test('同機型不同容量共用一個機型頁網址，容量只是參數', () => {
  assert.equal(modelUrl('iPhone 17 Pro', '256GB'), 'model.html?m=iPhone+17+Pro&s=256GB');
  assert.equal(modelUrl('iPhone 17 Pro', null), 'model.html?m=iPhone+17+Pro');
  assert.equal(modelUrl('iPhone 17 Pro', ''), 'model.html?m=iPhone+17+Pro');
  const back = new URLSearchParams(modelUrl('iPhone 17 Pro Max', '1TB').split('?')[1]);
  assert.equal(back.get('m'), 'iPhone 17 Pro Max');
  assert.equal(back.get('s'), '1TB');
});

test('容量依實際大小排序，無法辨識的放最後', () => {
  const sorted = ['1TB', '未知', '512GB', '2TB', '', '128GB', '256GB', '64GB'].sort(compareStorage);
  assert.deepEqual(sorted, ['64GB', '128GB', '256GB', '512GB', '1TB', '2TB', '', '未知']);
});

test('esc 會跳脫 HTML', () => {
  assert.equal(esc('<a href="x">&\'</a>'), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;');
});


test('共用文章卡片在容量後顯示顏色，空白省略且跳脫 HTML', () => {
  const { itemHtml } = require('../site/common.js');
  const row = { storage: '256GB', color: '藏藍色', model: 'iPhone 17 Pro', price: null };
  const html = itemHtml(row);
  assert.ok(html.indexOf('256GB') < html.indexOf('藏藍色'));
  assert.match(html, /class="chip color-chip"/);
  assert.doesNotMatch(itemHtml({ ...row, color: '' }), /color-chip/);
  assert.match(itemHtml({ ...row, color: '<script>' }), /&lt;script&gt;/);
});
