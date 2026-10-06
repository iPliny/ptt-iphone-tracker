const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const common = require('../site/common.js');
const { periodRange, sumPeriod, previousPeriod, periodNavigation, periodTitle, periodItems } = common;

function daysFrom(start, count) {
  return Array.from({ length: count }, (_, i) => ({
    date: new Date(Date.parse(start + 'T00:00:00Z') + i * 86400000).toISOString().slice(0, 10),
    new: i + 1, sold: i % 3, deleted: i % 2, price_changes: i * 2, on_shelf: 100 + i,
  }));
}

test('10 天資料取最後 7 天；四項逐日相加，在架只取期末', () => {
  const days = daysFrom('2026-09-27', 10);
  const range = periodRange(days, '2026-10-06');
  assert.deepEqual(range, { start: 3, end: 9, startDate: '2026-09-30', endDate: '2026-10-06', count: 7 });
  const total = sumPeriod(days, range.start, range.end);
  for (const key of ['new', 'sold', 'deleted', 'price_changes']) {
    assert.equal(total[key], days.slice(-7).reduce((sum, d) => sum + d[key], 0));
  }
  assert.equal(total.on_shelf, 109);
  assert.equal(previousPeriod(days, range), null);
});

test('只有 4 天時照實顯示日期和天數，前期不足不比較', () => {
  const days = daysFrom('2026-10-01', 4);
  const range = periodRange(days, '2026-10-04');
  assert.equal(range.count, 4);
  assert.equal(periodTitle(range), '10-01～10-04 動態（4 天）');
  assert.equal(previousPeriod(days, range), null);
  assert.deepEqual(periodNavigation(days, '2026-10-04'), { previous: null, next: null });
});

test('前後一週固定移動 7 天，最舊不足一週可看但不能再往前', () => {
  const days = daysFrom('2026-09-27', 10);
  assert.deepEqual(periodNavigation(days, '2026-10-06'), { previous: '2026-09-29', next: null });
  assert.deepEqual(periodNavigation(days, '2026-09-29'), { previous: null, next: '2026-10-06' });
  assert.equal(periodTitle(periodRange(days, '2026-09-29')), '09-27～09-29 動態（3 天）');
  assert.equal(periodNavigation(days, '2026-10-03').previous, null);
  assert.equal(periodNavigation(days, '2026-10-04').previous, '2026-09-27');
});

test('完整前 7 天才比較，期末在架與前期最後一天比；日模式仍比昨天', () => {
  const days = daysFrom('2026-09-21', 16);
  const range = periodRange(days, '2026-10-06');
  const previous = previousPeriod(days, range);
  assert.deepEqual(previous, { start: 2, end: 8, startDate: '2026-09-23', endDate: '2026-09-29', count: 7 });
  assert.equal(sumPeriod(days, previous.start, previous.end).on_shelf, 108);
  assert.equal(previousPeriod(days, periodRange(days, days[12].date)), null);
  assert.equal(previousPeriod(days, periodRange(days, days[13].date)).count, 7);
  assert.equal(previousPeriod(days, periodRange(days, '2026-10-06', 1), 1).endDate, '2026-10-05');
});

test('跨月用 MM-DD，跨年用完整日期；空資料或無效日期不產生區間', () => {
  assert.equal(periodTitle(periodRange(daysFrom('2026-09-28', 7), '2026-10-04')), '09-28～10-04 動態（7 天）');
  assert.equal(periodTitle(periodRange(daysFrom('2026-12-29', 7), '2027-01-04')), '2026-12-29～2027-01-04 動態（7 天）');
  assert.equal(periodRange([], ''), null);
  assert.equal(periodRange(daysFrom('2026-10-01', 4), '2026-10-05'), null);
  assert.deepEqual(periodNavigation([], ''), { previous: null, next: null });
});

test('四分頁沿用時間欄位和條件、含起訖日且由新到舊、不修改輸入或補回排除事件', () => {
  const range = periodRange(daysFrom('2026-09-30', 7), '2026-10-06');
  const data = {
    listings: [
      { url: 'a', post_time: '2026-09-30 00:00:00', sold_at: '2026-10-06 23:59:59', status: '已售出' },
      { url: 'b', post_time: '2026-10-06 23:59:59', sold_at: '2026-09-30 00:00:00', status: '已售出' },
      { url: 'c', post_time: '2026-09-29 23:59:59', sold_at: '2026-10-05 10:00:00', status: '在售' },
      { url: 'd', post_time: '2026-10-07 00:00:00', sold_at: '', status: '在售' },
    ],
    events: [
      { time: '2026-09-30 00:00:00', event: '價格變動', detail: '10000 → 9000' },
      { time: '2026-10-06 23:59:59', event: '價格變動', detail: '9000 → 8000' },
      { time: '2026-10-05 09:10:00', event: '狀態變更', detail: '在售 → 已刪除' },
      { time: '2026-10-07 00:00:00', event: '價格變動', detail: '8000 → 7500' },
    ],
  };
  const snapshot = JSON.stringify(data);
  assert.deepEqual(periodItems(data, 'new', range).map(r => r.url), ['b', 'a']);
  assert.deepEqual(periodItems(data, 'sold', range).map(r => r.url), ['a', 'b']);
  assert.deepEqual(periodItems(data, 'price', range).map(r => r.time), ['2026-10-06 23:59:59', '2026-09-30 00:00:00']);
  assert.equal(periodItems(data, 'deleted', range).length, 1);
  assert.equal(periodItems(data, 'price', periodRange(daysFrom('2026-09-30', 7), '2026-10-06', 1)).length, 1);
  assert.equal(periodItems(data, 'new', null).length, 0);
  assert.equal(JSON.stringify(data), snapshot);
});

// 用最小 DOM 替身執行首頁，測試狀態切換與實際畫面接線，無外部套件或網路。
async function render(data) {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: '', innerHTML: '', textContent: '', hidden: false, listeners: {}, attrs: {},
      dataset: {}, classes: new Set(),
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute(name, value) { this.attrs[name] = value; },
      querySelectorAll(sel) {
        if (sel !== '.hit') return [];
        return [...this.innerHTML.matchAll(/data-date="([^"]+)"/g)].map((m) => {
          const hit = element('hit:' + m[1]); hit.dataset.date = m[1]; return hit;
        });
      },
      classList: { toggle(name, on) { if (on) element(id).classes.add(name); else element(id).classes.delete(name); } },
    });
    return elements.get(id);
  };
  const tabs = ['new', 'sold', 'price', 'deleted'].map(tab => {
    const el = element('tab:' + tab); el.dataset.tab = tab; return el;
  });
  const context = {
    document: { querySelector: element, querySelectorAll: () => tabs },
    PttCommon: common, PttWatchlist: require('../site/watchlist.js'),
    window: { addEventListener() {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } },
    fetch: async () => ({ ok: true, json: async () => data }), setTimeout, clearTimeout,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../site/app.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.doesNotMatch(element('#updated').textContent, /資料載入失敗/);
  return { element, click: (id) => element(id).listeners.click() };
}
function fixture(count = 16) {
  return { days: daysFrom('2026-09-21', count), listings: [], events: [], models: [], counts: { total: 0 } };
}

test('首頁預設日模式；週切換、兩方向、日期與長條回日模式，按鈕狀態和比較同步', async () => {
  const data = fixture();
  const { element: el, click } = await render(data);
  assert.equal(el('#latest-day').attrs['aria-pressed'], 'true');
  assert.match(el('#kpis').innerHTML, /日終在架/);
  const originalModels = el('#models').innerHTML, originalAll = el('#all-list').innerHTML;
  click('#latest-week');
  assert.equal(el('#day-title').textContent, '09-30～10-06 動態（7 天）');
  assert.equal(el('#latest-week').attrs['aria-pressed'], 'true');
  assert.equal(el('#latest-day').attrs['aria-pressed'], 'false');
  assert.equal(el('#prev-day').attrs['aria-label'], '前一週');
  assert.equal(el('#next-day').disabled, true);
  assert.match(el('#kpis').innerHTML, /期末在架/);
  assert.match(el('#kpis').innerHTML, /比前一週 \+49/);
  assert.match(el('#kpis').innerHTML, /比前一週 \+7/);
  assert.equal((el('#chart').innerHTML.match(/class="hit sel"/g) || []).length, 7);
  assert.match(el('#day-list').innerHTML, /這週沒有紀錄/);
  assert.equal(el('#models').innerHTML, originalModels);
  assert.equal(el('#all-list').innerHTML, originalAll);
  click('#prev-day');
  assert.equal(el('#day').value, '2026-09-29');
  assert.doesNotMatch(el('#kpis').innerHTML, /前一週/);
  click('#prev-day');
  assert.equal(el('#day-title').textContent, '09-21～09-22 動態（2 天）');
  assert.equal(el('#prev-day').disabled, true);
  click('#next-day'); click('#next-day');
  assert.equal(el('#day').value, '2026-10-06');
  click('hit:2026-10-04');
  assert.equal(el('#day-title').textContent, '2026-10-04 動態');
  assert.equal(el('#latest-week').attrs['aria-pressed'], 'false');
  assert.equal(el('#latest-day').attrs['aria-pressed'], 'false');
  assert.equal((el('#chart').innerHTML.match(/class="hit sel"/g) || []).length, 1);
  click('#latest-week');
  el('#day').listeners.change({ target: { value: '2026-10-03' } });
  assert.equal(el('#day-title').textContent, '2026-10-03 動態');
  assert.equal(el('#prev-day').attrs['aria-label'], '前一天');
  click('#latest-day');
  assert.equal(el('#latest-day').attrs['aria-pressed'], 'true');
  assert.match(el('#kpis').innerHTML, /比前一天/);
  assert.match(el('#day-list').innerHTML, /這天沒有紀錄/);
});

test('週事件加日期、每次 10 篇、換期間或分頁重設分頁；短週比較留白', async () => {
  const data = fixture(4);
  data.events = Array.from({ length: 23 }, (_, i) => ({ time: `2026-09-24 14:${String(i).padStart(2, '0')}:00`,
    url: 'https://example.test/' + i, event: '價格變動', detail: '10000 → 9000' }));
  const { element: el, click } = await render(data);
  click('#latest-week'); click('tab:price');
  assert.match(el('#day-title').textContent, /（4 天）/);
  assert.doesNotMatch(el('#kpis').innerHTML, /前一週/);
  assert.match(el('#day-list').innerHTML, /09-24 14:22 發現改價/);
  assert.equal((el('#day-list').innerHTML.match(/class="item"/g) || []).length, 10);
  click('#day-more');
  assert.equal((el('#day-list').innerHTML.match(/class="item"/g) || []).length, 20);
  click('#day-more');
  assert.equal((el('#day-list').innerHTML.match(/class="item"/g) || []).length, 23);
  assert.equal(el('#day-more').hidden, true);
  click('#latest-day');
  assert.equal((el('#day-list').innerHTML.match(/class="item"/g) || []).length, 10);
  assert.doesNotMatch(el('#day-list').innerHTML, /09-24 14:22 發現改價/);
  click('#day-more'); click('tab:new'); click('tab:price');
  assert.equal((el('#day-list').innerHTML.match(/class="item"/g) || []).length, 10);
});

test('空資料可載入且期間按鈕停用', async () => {
  const { element: el } = await render(fixture(0));
  for (const id of ['#latest-day', '#latest-week', '#prev-day', '#next-day']) assert.equal(el(id).disabled, true);
  assert.match(el('#day-list').innerHTML, /這天沒有紀錄/);
});
