const test = require('node:test');
const assert = require('node:assert/strict');
const {
  STORAGE_KEY,
  MAX_ITEMS,
  normalize,
  key,
  createStore,
} = require('../site/watchlist.js');

const selection = (overrides = {}) => ({
  model: 'iPhone 16 Pro',
  storage: '256GB',
  status: '在售',
  q: '',
  ...overrides,
});

function storageFixture(initialValue = null) {
  let value = initialValue;
  const writes = [];
  const storage = {
    getItem(storageKey) {
      assert.equal(storageKey, STORAGE_KEY);
      return value;
    },
    setItem(storageKey, nextValue) {
      assert.equal(storageKey, STORAGE_KEY);
      writes.push(nextValue);
      value = nextValue;
    },
  };
  return { storage, writes, read: () => value };
}

test('正規化篩選條件，只保留查詢條件並整理空白', () => {
  assert.deepEqual(normalize({}), {
    model: null, storage: null, status: '', q: '',
  });
  assert.deepEqual(normalize({
    model: '  iPhone 16 Pro  ',
    storage: ' 256GB ',
    status: ' 在售 ',
    q: '  原廠\t 保固\n中  ',
    price: 25000,
    source_url: 'https://example.invalid/listing',
  }), selection({ q: '原廠 保固 中' }));
  assert.equal(normalize({ storage: '' }).storage, '');
  assert.equal(normalize({ storage: null }).storage, null);
});

test('不接受損毀或過長的篩選資料', () => {
  for (const invalid of [
    null, [], 'iPhone', 1, true,
    { model: [] }, { model: 16 }, { storage: 256 },
    { q: null }, { q: {} }, { status: null },
    { status: '成交確認' },
    { model: 'x'.repeat(121) },
    { storage: 'x'.repeat(33) },
    { q: 'x'.repeat(201) },
  ]) {
    assert.equal(normalize(invalid), null, JSON.stringify(invalid));
  }
  assert.ok(normalize({ model: 'x'.repeat(120), storage: 'x'.repeat(32), q: 'x'.repeat(200) }));
  for (const status of ['', '在售', '交易中', '已售出', '已刪除']) {
    assert.equal(normalize({ status }).status, status);
  }
});

test('同一搜尋忽略大小寫與連續空白，但容量及狀態各自區分', () => {
  assert.equal(key(selection({ q: '  APPLE\tCare ' })), key(selection({ q: 'apple care' })));
  assert.notEqual(key(selection()), key(selection({ storage: '512GB' })));
  assert.notEqual(key(selection()), key(selection({ status: '已售出' })));
  assert.notEqual(key(selection({ storage: null })), key(selection({ storage: '' })));
});

test('收藏寫入瀏覽器後，新實例可以還原，且不保存價格等未知欄位', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  assert.equal(STORAGE_KEY, 'ptt-iphone-tracker:watchlist:v1');
  assert.equal(store.mode(), 'persistent');
  assert.equal(store.add(selection({ price: 25000, observedAt: '2026-09-30' })), 'added');
  assert.equal(fixture.writes.length, 1);
  assert.deepEqual(JSON.parse(fixture.read()), { version: 1, items: [selection()] });
  const reopened = createStore(() => fixture.storage);
  assert.deepEqual(reopened.list(), [selection()]);
  assert.equal(reopened.has(selection()), true);
  assert.equal(fixture.writes.length, 1, '讀取收藏不應重新寫入');
});

test('相同條件只收藏一次，保留第一筆的搜尋文字', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  const first = selection({ q: 'Apple Care' });
  assert.equal(store.add(first), 'added');
  assert.equal(store.add(selection({ q: ' apple   care ' })), 'duplicate');
  assert.equal(store.has(selection({ q: 'APPLE CARE' })), true);
  assert.deepEqual(store.list(), [first]);
  assert.equal(fixture.writes.length, 1);
});

test('容量未知、容量不限、不同容量與售出狀態可分別收藏', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  const choices = [
    selection({ storage: null }),
    selection({ storage: '' }),
    selection({ storage: '256GB' }),
    selection({ storage: '512GB' }),
    selection({ status: '已售出' }),
  ];
  for (const choice of choices) assert.equal(store.add(choice), 'added');
  assert.equal(store.list().length, choices.length);
  for (const choice of choices) assert.equal(store.has(choice), true);
});

test('全空條件與無效輸入不寫入，但精確查未知容量可收藏', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  assert.equal(store.add({}), 'empty');
  assert.equal(store.add({ q: ' \t\n ' }), 'empty');
  assert.equal(store.add({ status: 'unknown' }), 'invalid');
  assert.equal(store.add(null), 'invalid');
  assert.equal(store.has(null), false);
  assert.equal(fixture.writes.length, 0);
  assert.equal(store.add({ storage: '' }), 'added');
  assert.equal(store.list().length, 1);
});

test('刪除指定收藏會保存結果，刪除不存在的收藏不覆寫', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  const other = selection({ storage: '512GB' });
  store.add(selection());
  store.add(other);
  assert.equal(store.remove(key(selection())), true);
  assert.equal(store.has(selection()), false);
  assert.deepEqual(createStore(() => fixture.storage).list(), [other]);
  const writesAfterRemoval = fixture.writes.length;
  assert.equal(store.remove(key(selection())), false);
  assert.equal(fixture.writes.length, writesAfterRemoval);
});

test('呼叫端修改輸入或清單副本，不會改壞已收藏的內容', () => {
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  const input = selection();
  store.add(input);
  input.model = 'changed input';
  const returned = store.list();
  returned[0].storage = 'changed output';
  returned.push(selection({ model: 'injected' }));
  assert.deepEqual(store.list(), [selection()]);
});

test('禁止存取 storage 時退回本頁暫存，仍能新增、重讀與刪除', () => {
  const store = createStore(() => { throw new Error('SecurityError'); });
  assert.equal(store.mode(), 'memory');
  assert.ok(store.notice().length > 0);
  assert.equal(store.add(selection()), 'added');
  store.reload();
  assert.equal(store.has(selection()), true);
  assert.equal(store.remove(key(selection())), true);
  assert.deepEqual(store.list(), []);
});

test('storage 讀取失敗不讓頁面崩潰，本頁收藏在重讀後仍存在', () => {
  const storage = {
    getItem() { throw new Error('read unavailable'); },
    setItem() { assert.fail('記憶體模式不應嘗試寫入'); },
  };
  const store = createStore(() => storage);
  assert.equal(store.mode(), 'memory');
  assert.ok(store.notice().length > 0);
  assert.equal(store.add(selection()), 'added');
  store.reload();
  assert.deepEqual(store.list(), [selection()]);
});

test('storage 寫入失敗保留已載入與新收藏，改以本頁暫存操作', () => {
  const existing = selection();
  const added = selection({ storage: '512GB' });
  const storage = {
    getItem() { return JSON.stringify({ version: 1, items: [existing] }); },
    setItem() { throw new Error('QuotaExceededError'); },
  };
  const store = createStore(() => storage);
  assert.equal(store.add(added), 'added');
  assert.equal(store.mode(), 'memory');
  assert.ok(store.notice().length > 0);
  store.reload();
  assert.deepEqual(store.list(), [existing, added]);
  assert.equal(store.remove(key(existing)), true);
  assert.deepEqual(store.list(), [added]);
});

test('刪除時寫入失敗，仍保留本頁已刪除的結果', () => {
  const storage = {
    getItem() { return JSON.stringify({ version: 1, items: [selection()] }); },
    setItem() { throw new Error('write blocked'); },
  };
  const store = createStore(() => storage);
  assert.equal(store.remove(key(selection())), true);
  assert.equal(store.mode(), 'memory');
  store.reload();
  assert.deepEqual(store.list(), []);
});

test('損毀 JSON 與不支援格式顯示提示，不主動覆寫原本資料', () => {
  for (const raw of [
    '{not json',
    'null',
    '[]',
    JSON.stringify({ version: 2, items: [selection()] }),
    JSON.stringify({ version: 1, items: 'broken' }),
  ]) {
    const fixture = storageFixture(raw);
    const store = createStore(() => fixture.storage);
    assert.deepEqual(store.list(), [], raw);
    assert.ok(store.notice().length > 0, raw);
    assert.equal(fixture.read(), raw);
    assert.equal(fixture.writes.length, 0);
  }
});

test('讀取時排除壞項目與重複條件，不把無效內容重新寫回', () => {
  const first = selection({ q: 'Apple Care', price: 999 });
  const unknownStorage = selection({ storage: '' });
  const raw = JSON.stringify({
    version: 1,
    items: [null, [], {}, { q: 42 }, { status: 'unsupported' }, first,
      selection({ q: ' apple   CARE ' }), unknownStorage],
  });
  const fixture = storageFixture(raw);
  const store = createStore(() => fixture.storage);
  assert.deepEqual(store.list(), [selection({ q: 'Apple Care' }), unknownStorage]);
  assert.equal(fixture.writes.length, 0);
  assert.equal(fixture.read(), raw);
});

test('另一個實例更新後，reload 能同步新增與刪除', () => {
  const fixture = storageFixture();
  const firstTab = createStore(() => fixture.storage);
  const secondTab = createStore(() => fixture.storage);
  firstTab.add(selection());
  secondTab.reload();
  assert.equal(secondTab.has(selection()), true);
  secondTab.remove(key(selection()));
  firstTab.reload();
  assert.deepEqual(firstTab.list(), []);
});

test('最多保存 30 筆，刪除後可以補入，載入超量資料也限制筆數', () => {
  assert.equal(MAX_ITEMS, 30);
  const choices = Array.from({ length: MAX_ITEMS + 1 }, (_, index) => selection({ q: `query ${index}` }));
  const fixture = storageFixture();
  const store = createStore(() => fixture.storage);
  for (const choice of choices.slice(0, MAX_ITEMS)) assert.equal(store.add(choice), 'added');
  assert.equal(store.add(choices[MAX_ITEMS]), 'full');
  assert.equal(fixture.writes.length, MAX_ITEMS);
  assert.equal(store.remove(key(choices[0])), true);
  assert.equal(store.add(choices[MAX_ITEMS]), 'added');
  assert.equal(store.list().length, MAX_ITEMS);

  const overfull = storageFixture(JSON.stringify({ version: 1, items: choices }));
  const restored = createStore(() => overfull.storage);
  assert.deepEqual(restored.list(), choices.slice(0, MAX_ITEMS));
  assert.equal(overfull.writes.length, 0);
});
