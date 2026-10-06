const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const common = require('../site/common.js');
const watchlist = require('../site/watchlist.js');

// 執行完整機型頁腳本，使用最小 DOM 替身驗證容量切換與資料呈現；不需網路。
async function render(colors, listings) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: false, value: '', innerHTML: '', textContent: '', listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; }, setAttribute() {},
    });
    return elements.get(id);
  }
  const data = { colors, listings, models: [], events: [], last_checked: '' };
  const storage = new Map();
  const context = {
    document: { querySelector: element }, location: { search: '?m=iPhone+17+Pro+Max' },
    history: { replaceState() {} }, URLSearchParams, PttCommon: common, PttWatchlist: watchlist,
    window: { addEventListener() {}, localStorage: {
      getItem: (k) => storage.get(k) || null, setItem: (k, v) => storage.set(k, v), removeItem: (k) => storage.delete(k),
    } },
    fetch: async () => ({ ok: true, json: async () => data }), setTimeout, clearTimeout,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../site/model.js'), 'utf8'), context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.doesNotMatch(element('#updated').textContent, /資料載入失敗/);
  return { element, choose(s) {
    element('#storage-tabs').listeners.click({ target: { closest: () => ({ dataset: { storage: s } }) } });
  } };
}
const model = 'iPhone 17 Pro Max';
const row = (color, relative, storage = null, n = 3) => ({ model, color, relative, storage,
  samples: n, listed: n, sold: 1, median_price: relative == null ? null : 30000 });
const listing = (color, storage = '256GB') => ({ model, color, storage, post_time: '', status: '在售', price: null });

test('顏色表按相對值排序，樣本不足最後；容量切換和未標顏色篇數同步', async () => {
  const { element, choose } = await render([
    row('銀色', .03), row('藏藍色', null, null, 2), row('宇宙橙色', -.05),
    row('銀色', null, '256GB', 2),
  ], [listing('銀色'), listing(''), listing('', '512GB')]);
  const html = element('#color-table').innerHTML;
  assert.ok(html.indexOf('宇宙橙色') < html.indexOf('銀色'));
  assert.ok(html.indexOf('銀色') < html.indexOf('藏藍色'));
  assert.match(html, /−5%/);
  assert.match(html, /\+3%/);
  assert.match(html, /樣本不足/);
  assert.match(element('#color-best').textContent, /宇宙橙色（比中位數低 5%，3 篇）/);
  assert.match(element('#color-note').textContent, /未標示顏色的 2 篇/);
  choose('256GB');
  assert.match(element('#color-note').textContent, /未標示顏色的 1 篇/);
  assert.doesNotMatch(element('#color-table').innerHTML, /宇宙橙色/);
  assert.equal(element('#color-best').hidden, true);
});

test('同值並列不任選一種顏色當最低；沒有顏色時隱藏卡片', async () => {
  let view = await render([row('銀色', 0), row('藏藍色', 0)], [listing('銀色')]);
  assert.match(view.element('#color-best').textContent, /並列最低/);
  assert.match(view.element('#color-best').textContent, /銀色/);
  assert.match(view.element('#color-best').textContent, /藏藍色/);
  view = await render([], [listing('')]);
  assert.equal(view.element('#color-card').hidden, true);
});

test('舊版 data.json 無 colors 仍能載入；顏色內容跳脫 HTML', async () => {
  const old = await render(undefined, [listing('')]);
  assert.equal(old.element('#color-card').hidden, true);
  const view = await render([row('<img src=x>', null)], [listing('<img src=x>')]);
  assert.match(view.element('#color-table').innerHTML, /&lt;img src=x&gt;/);
  assert.doesNotMatch(view.element('#color-table').innerHTML, /<img/);
});
