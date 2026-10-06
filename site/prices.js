/* 歷史價格獨立查詢；不讀寫行情 data.json、收藏或私人 Drive。 */
(function () {
  'use strict';
  const COLUMNS = ['section', 'year', 'model', 'storage', 'amount', 'evidence', 'price_type', 'effective_date', 'issuer', 'source_id', 'note'];
  const EVIDENCE = {A: 'Apple 原文', B: '電信官方（非 Apple 直售）', C: '轉載待原件', F: '時點待複核', N: '台灣不適用'};
  const SECTIONS = {
    'tw-launch': '台灣上市價／首發方案（TWD）',
    'tw-later': '台灣後續容量／調價（TWD）',
    us: '初代美國價格（USD）'
  };
  const NOTES = {
    'tw-launch': '歷史上市價，不是現在售價。電信首發方案另標定價主體；待查金額顯示「待查」，不是零元。',
    'tw-later': '這裡是後來新增的容量或後續調價，不可覆寫原上市定價；「初發年」仍是機型初次發表年。',
    us: '以美元列示，未換算新台幣；不含各州另計稅負與電信服務資費，不作台灣空機基準。'
  };
  const normal = value => String(value || '').normalize('NFKC').toLowerCase().replace(/iphone|[\s()第代_-]/g, '');
  const storageSize = value => Number.parseFloat(value) * (/TB$/i.test(value) ? 1000 : 1);
  function sourceUrl(value) {
    try {
      const u = new URL(value);
      return u.protocol === 'https:' && !u.username && !u.password ? u.href : null;
    } catch (_) { return null; }
  }
  function decode(data) {
    if (!data || data.schema_version !== 1 || JSON.stringify(data.columns) !== JSON.stringify(COLUMNS) ||
        !Array.isArray(data.records) || !data.sources || typeof data.updated_at !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}$/.test(data.updated_at) || !Number.isInteger(data.withheld_records) || data.withheld_records < 0) {
      throw new Error('價格資料格式不符');
    }
    const keys = new Set();
    return data.records.map(values => {
      if (!Array.isArray(values) || values.length !== COLUMNS.length) throw new Error('價格欄位不符');
      const r = Object.fromEntries(COLUMNS.map((name, i) => [name, values[i]]));
      if (!Object.hasOwn(SECTIONS, r.section) || !Object.hasOwn(EVIDENCE, r.evidence) ||
          !Number.isInteger(r.year) || r.year < 2007 || r.year > Number(data.updated_at.slice(0, 4)) ||
          !['model', 'storage', 'price_type', 'issuer', 'source_id', 'note'].every(k => typeof r[k] === 'string') ||
          !/^\d+(GB|TB)$/.test(r.storage) || !r.model.trim() ||
          !(r.effective_date === null || typeof r.effective_date === 'string')) throw new Error('價格記錄不符');
      const published = r.evidence === 'A' || r.evidence === 'B';
      if (published ? !Number.isInteger(r.amount) || r.amount <= 0 : r.amount !== null) {
        throw new Error('禁止公開待查金額');
      }
      r.source_url = sourceUrl(data.sources[r.source_id]);
      if (!r.source_url) throw new Error('來源連結不符');
      const host = new URL(r.source_url).hostname;
      if ((r.evidence === 'A' && host !== 'www.apple.com') ||
          (r.evidence === 'B' && host !== 'corp.taiwanmobile.com')) throw new Error('官方來源主體不符');
      r.currency = r.section === 'us' ? 'USD' : 'TWD';
      const key = [r.section, r.model, r.storage, r.price_type, r.effective_date].join('|');
      if (keys.has(key)) throw new Error('價格記錄重複');
      keys.add(key);
      return r;
    });
  }
  function filterRows(rows, f = {}) {
    const q = normal(f.q);
    const evidence = f.evidence || 'A';
    const sort = f.sort || 'newest';
    const out = rows.filter(r => r.section === (f.section || 'tw-launch') &&
      (evidence === 'all' || (evidence === 'pending' ? !['A', 'B'].includes(r.evidence) : r.evidence === evidence)) &&
      (!f.year || String(r.year) === String(f.year)) && (!f.storage || r.storage === f.storage) &&
      (!q || normal(r.model).includes(q)));
    return out.sort((a, b) => {
      if (sort.startsWith('price-')) {
        if (a.amount === null && b.amount !== null) return 1;
        if (b.amount === null && a.amount !== null) return -1;
        if (a.amount !== null && b.amount !== null && a.amount !== b.amount) {
          return (a.amount - b.amount) * (sort === 'price-desc' ? -1 : 1);
        }
      }
      return (a.year - b.year) * (sort === 'oldest' ? 1 : -1) ||
        a.model.localeCompare(b.model, 'en', {numeric: true}) || storageSize(a.storage) - storageSize(b.storage) ||
        String(a.effective_date || '').localeCompare(String(b.effective_date || ''));
    });
  }
  function amountText(r) {
    if (r.evidence === 'N') return '不適用';
    if (!['A', 'B'].includes(r.evidence) || !Number.isInteger(r.amount) || r.amount <= 0) return '待查';
    return `${r.currency === 'USD' ? 'US$' : 'NT$'}${r.amount.toLocaleString('en-US')}`;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {decode, filterRows, amountText, sourceUrl, storageSize};
  if (typeof document === 'undefined') return;

  const $ = id => document.getElementById(id);
  const controls = {section: $('price-section'), evidence: $('price-evidence'), year: $('price-year'), storage: $('price-storage'), q: $('price-query'), sort: $('price-sort')};
  let rows = [];
  function node(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function fillOptions(select, values) {
    while (select.options.length > 1) select.remove(1);
    values.forEach(value => { const option = node('option', String(value)); option.value = String(value); select.append(option); });
  }
  function readUrl() {
    const params = new URLSearchParams(location.search);
    for (const [key, el] of Object.entries(controls)) {
      const value = params.get(key) || '';
      if (key === 'q') el.value = value.slice(0, 120);
      else if (Array.from(el.options).some(o => o.value === value)) el.value = value;
    }
  }
  function render() {
    const f = Object.fromEntries(Object.entries(controls).map(([key, el]) => [key, el.value]));
    const matches = filterRows(rows, f);
    const body = document.createDocumentFragment();
    for (const r of matches) {
      const tr = node('tr');
      const model = node('td', r.model, 'price-model');
      model.append(node('span', `${r.year} 年`, 'price-note'));
      const timing = node('td', r.price_type);
      timing.append(node('span', `適用：${r.effective_date || '日期待查'} · ${r.issuer}`, 'price-note'));
      if (r.note) timing.append(node('span', r.note, 'price-note'));
      const evidence = node('td');
      evidence.append(node('span', EVIDENCE[r.evidence], 'chip'));
      const a = node('a', ['A', 'B'].includes(r.evidence) ? '查閱官方來源 ↗' : '查看來源線索 ↗', 'price-source');
      a.href = r.source_url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.setAttribute('aria-label', `${r.model} ${r.storage}：${EVIDENCE[r.evidence]}來源（另開視窗）`);
      evidence.append(document.createElement('br'), a);
      tr.append(model, node('td', r.storage), node('td', amountText(r), 'num price-amount'), timing, evidence);
      body.append(tr);
    }
    $('price-rows').replaceChildren(body);
    $('price-empty').hidden = matches.length > 0;
    $('price-table-scroll').hidden = matches.length === 0;
    $('price-result').textContent = `${matches.length} 筆記錄 · ${new Set(matches.map(r => r.model)).size} 個機型 · ${matches.filter(r => r.amount !== null).length} 筆有來源支持的金額`;
    $('price-section-note').textContent = NOTES[f.section];
    $('price-caption').textContent = SECTIONS[f.section];
    const url = new URL(location.href);
    url.search = '';
    for (const [key, value] of Object.entries(f)) if (value) url.searchParams.set(key, value);
    try { history.replaceState(null, '', url); } catch (_) { /* file:// 預覽不支援時不影響查詢。 */ }
  }
  async function load() {
    $('price-error').hidden = true; $('price-retry').hidden = true;
    $('price-coverage').textContent = '載入查核資料中…';
    Object.values(controls).forEach(el => { el.disabled = true; });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('official-prices.json', {cache: 'no-cache', signal: controller.signal});
      if (!response.ok) throw new Error('載入失敗');
      const data = await response.json();
      rows = decode(data);
      fillOptions(controls.year, [...new Set(rows.map(r => r.year))].sort((a, b) => b - a));
      fillOptions(controls.storage, [...new Set(rows.map(r => r.storage))].sort((a, b) => storageSize(a) - storageSize(b)));
      readUrl();
      $('price-coverage').textContent = `底稿日期 ${data.updated_at} · 收錄 ${new Set(rows.map(r => r.model)).size} 個機型、${rows.length} 筆記錄（含待查及不適用） · 另 ${data.withheld_records} 筆機型／索引待核記錄暫不刊出。`;
      render();
    } catch (_) {
      rows = [];
      $('price-rows').replaceChildren();
      $('price-table-scroll').hidden = true; $('price-empty').hidden = true;
      $('price-result').textContent = '';
      $('price-coverage').textContent = '查核資料尚未載入。';
      $('price-error').hidden = false; $('price-retry').hidden = false;
    } finally {
      clearTimeout(timeout);
      Object.values(controls).forEach(el => { el.disabled = rows.length === 0; });
    }
  }
  $('price-filters').addEventListener('submit', e => e.preventDefault());
  $('price-filters').addEventListener('input', () => { if (rows.length) render(); });
  $('price-filters').addEventListener('change', () => { if (rows.length) render(); });
  $('price-filters').addEventListener('reset', () => { setTimeout(() => { if (rows.length) render(); }, 0); });
  $('price-retry').addEventListener('click', load);
  load();
})();
