const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const common = require('../site/common.js');
const watchlist = require('../site/watchlist.js');

// 使用真正建置出的 HTML 與 sitemap，比對機型腳本輸出的 canonical。
test('機型 canonical 與 sitemap 編碼一致，排除容量、追蹤參數與重複 m', (t) => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'macshop-seo-'));
  t.after(() => fs.rmSync(tmp, { recursive: true, force: true }));
  const data = path.join(tmp, 'data'), out = path.join(tmp, 'out');
  fs.mkdirSync(data);
  const models = ['iPhone 17 Pro', 'iPhone 17 Pro Max', 'iPhone SE (第 3 代)'];
  fs.writeFileSync(path.join(data, 'listings.csv'), 'model,status,price\n' +
    models.map(m => `${m},在售,10000`).join('\n'));
  execFileSync(process.env.PYTHON || 'python3',
    [path.join(__dirname, '../site/build_site.py'), '--data', data, '--out', out]);
  const html = fs.readFileSync(path.join(out, 'model.html'), 'utf8');
  const base = html.match(/<meta name="site-url" content="([^"]+)">/)[1];
  const sitemap = fs.readFileSync(path.join(out, 'sitemap.xml'), 'utf8');
  const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]);
  const source = fs.readFileSync(path.join(out, 'model.js'), 'utf8');
  function canonical(search) {
    const links = [];
    const elements = new Map();
    vm.runInNewContext(source, {
      document: {
        querySelector(selector) {
          if (selector === 'meta[name="site-url"]') return { content: base };
          if (!elements.has(selector)) elements.set(selector, {});
          return elements.get(selector);
        },
        createElement: tagName => ({ tagName }),
        head: { appendChild: link => links.push(link) },
      },
      location: { search }, URLSearchParams, PttCommon: common, PttWatchlist: watchlist,
      window: { localStorage: { getItem: () => null } },
      // 網路未回來也應先設定 canonical，不依賴資料載入成功。
      fetch: () => new Promise(() => {}),
    });
    return links;
  }
  for (const model of models) {
    const url = base + common.modelPageUrl(model);
    assert.ok(locs.includes(url));
    assert.ok(url, model);
    const query = '?m=' + encodeURIComponent(model) + '&s=256GB&utm_source=test&m=ignored';
    const links = canonical(query);
    assert.equal(links.length, 1);
    assert.equal(links[0].tagName, 'link');
    assert.equal(links[0].rel, 'canonical');
    assert.equal(links[0].href, url);
  }
  assert.equal(canonical('?m=iPhone+17+Pro')[0].href, base + 'models/iphone-17-pro');
  for (const query of ['', '?s=256GB', '?m=']) assert.deepEqual(canonical(query), []);
});
