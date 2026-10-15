const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const common = require('../site/common.js');
const watchlist = require('../site/watchlist.js');
const model = 'iPhone 18 Pro';
const base = 'https://macshop.example.test/';

function dataset() {
  const listings = Array.from({ length: 24 }, (_, i) => ({
    model, storage: i % 2 ? '512GB' : '256GB', price: 30000 + i * 100,
    status: i < 18 ? '在售' : '已售出', color: '', url: 'https://www.ptt.cc/item/' + i,
    post_time: '2026-10-15 10:00:00', notes: '',
  }));
  return { listings, models: [], model_totals: [{ model, listed: 24, active: 18, sold: 6 }],
    events: [], apple: {}, colors: [], last_checked: '2026-10-16 00:23:20' };
}

async function page({ staticPage = true, search = '', data = dataset(), fail = false, saved = new Map() } = {}) {
  const elements = new Map();
  const links = staticPage ? [{ rel: 'canonical', href: base + common.modelPageUrl(model) }] : [];
  const history = [], requests = [];
  function element(selector) {
    if (selector === 'link[rel="canonical"]') return links[0] || null;
    if (selector === 'meta[name="site-url"]') return { content: base };
    if (!elements.has(selector)) elements.set(selector, {
      hidden: false, value: selector === '#sort-f' ? 'time' : '',
      textContent: selector === '#updated' ? '最後回訪 snapshot' : '',
      innerHTML: 'snapshot', listeners: {}, attributes: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute(name, value) { this.attributes[name] = value; },
    });
    return elements.get(selector);
  }
  const document = {
    title: staticPage ? model + ' 預先產生的標題' : '', body: { dataset: staticPage ? { model } : {} },
    querySelector: element, createElement: () => ({}), head: { appendChild: link => links.push(link) },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../site/model.js'), 'utf8'), {
    document, location: { search, pathname: staticPage ? '/models/iphone-18-pro.html' : '/model.html' },
    history: { replaceState: (...args) => history.push(args[2]) }, URLSearchParams,
    PttCommon: common, PttWatchlist: watchlist,
    window: { addEventListener() {}, localStorage: {
      getItem: k => saved.get(k) || null, setItem: (k, v) => saved.set(k, v), removeItem: k => saved.delete(k),
    } },
    fetch: async url => { requests.push(url); if (fail) throw Error('offline'); return { ok: true, json: async () => data }; },
    setTimeout: () => 1, clearTimeout() {},
  });
  await new Promise(resolve => setImmediate(resolve));
  return { document, element, links, history, requests, saved,
    choose(storage) { element('#storage-tabs').listeners.click({ target: { closest: () => ({ dataset: { storage } }) } }); } };
}

test('靜態頁重用 canonical、保留預產標題，讀取根目錄資料，查詢 m 不覆蓋機型身分', async () => {
  const view = await page({ search: '?m=other&s=256GB&utm_source=test' });
  assert.deepEqual(view.requests, ['../data.json']);
  assert.equal(view.links.length, 1);
  assert.equal(view.links[0].href, base + 'models/iphone-18-pro.html');
  assert.equal(view.document.title, model + ' 預先產生的標題');
  assert.equal(view.element('#model-name').textContent, model);
  assert.match(view.element('#list-title').textContent, /256GB的文章（12）/);
  view.choose('512GB');
  assert.equal(view.history.at(-1), '/models/iphone-18-pro.html?s=512GB');
  view.choose('*');
  assert.equal(view.history.at(-1), '/models/iphone-18-pro.html');
  assert.equal(view.links.length, 1);
});

test('原 model.html 查詢入口保留容量網址與篩選行為，canonical 指向預產標準頁', async () => {
  const view = await page({ staticPage: false, search: '?m=iPhone+18+Pro&s=256GB' });
  assert.deepEqual(view.requests, ['data.json']);
  assert.equal(view.links.length, 1);
  assert.equal(view.links[0].href, base + 'models/iphone-18-pro.html');
  view.choose('512GB');
  assert.equal(view.history.at(-1), 'model.html?m=iPhone+18+Pro&s=512GB');
  assert.match(view.element('#list-title').textContent, /512GB的文章/);
});

test('靜態與舊入口都保留狀態篩選、價格排序及更多文章', async () => {
  for (const staticPage of [true, false]) {
    const view = await page({ staticPage, search: '?m=iPhone+18+Pro' });
    assert.match(view.element('#more').textContent, /還有 14 篇/);
    view.element('#more').listeners.click();
    assert.match(view.element('#more').textContent, /還有 4 篇/);
    view.element('#status-f').value = '已售出';
    view.element('#status-f').listeners.change();
    assert.match(view.element('#list-title').textContent, /文章（6）/);
    assert.equal(view.element('#more').hidden, true);
    view.element('#sort-f').value = 'price-desc';
    view.element('#sort-f').listeners.change();
    const html = view.element('#list').innerHTML;
    assert.ok(html.indexOf('/item/23') < html.indexOf('/item/18'));
  }
});

test('新舊入口同機型與容量共用收藏，重新載入可還原', async () => {
  const saved = new Map();
  const current = await page({ search: '?s=256GB', saved });
  current.element('#watch-model').listeners.click();
  assert.equal(current.element('#watch-model').attributes['aria-pressed'], 'true');
  const legacy = await page({ staticPage: false, search: '?m=iPhone+18+Pro&s=256GB', saved });
  assert.equal(legacy.element('#watch-model').attributes['aria-pressed'], 'true');
  legacy.element('#watch-model').listeners.click();
  const reloaded = await page({ search: '?s=256GB', saved });
  assert.equal(reloaded.element('#watch-model').attributes['aria-pressed'], 'false');
});

test('資料請求失敗仍保留靜態內容，舊入口仍明確顯示載入錯誤', async () => {
  const staticView = await page({ fail: true });
  assert.equal(staticView.element('#list').innerHTML, 'snapshot');
  assert.equal(staticView.element('#model-main').hidden, false);
  assert.match(staticView.element('#updated').textContent, /snapshot.*顯示建置時資料/);
  const legacy = await page({ staticPage: false, search: '?m=iPhone+18+Pro', fail: true });
  assert.equal(legacy.element('#updated').textContent, '資料載入失敗（offline）');
});

test('無效容量退回全部容量，機型消失不留下錯誤的靜態內容', async () => {
  const view = await page({ search: '?s=not-real' });
  assert.match(view.element('#list-title').textContent, /全部容量/);
  const data = dataset(); data.listings = []; data.model_totals = [];
  const missing = await page({ data });
  assert.equal(missing.element('#model-main').hidden, true);
  assert.equal(missing.element('#model-missing').hidden, false);
});

test('僅有多品項資料的機型仍可顯示刊登統計，不虛構單支文章', async () => {
  const data = dataset();
  data.listings = [];
  data.model_totals = [{ model, listed: 1, multi: 1, active: 0, sold: 0, median_price: 30000 }];
  const view = await page({ data });
  assert.equal(view.element('#model-main').hidden, false);
  assert.match(view.element('#kpis').innerHTML, /多品項 1/);
  assert.match(view.element('#list-title').textContent, /文章（0）/);
  assert.equal(view.element('#more').hidden, true);
});
