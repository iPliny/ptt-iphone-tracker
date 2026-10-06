'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {decode, filterRows, amountText, sourceUrl, storageSize} = require('../site/prices.js');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/official-prices.json'), 'utf8'));
const rows = decode(data);
const copy = () => JSON.parse(JSON.stringify(data));

test('預設僅 52 筆台灣上市 Apple 原文價，不混入電信／美國／後續價', () => {
  const found = filterRows(rows);
  assert.equal(found.length, 52);
  assert.ok(found.every(r => r.section === 'tw-launch' && r.evidence === 'A' && r.currency === 'TWD'));
});
test('全部狀態保留待查行，不傳回未核實金額', () => {
  const all = filterRows(rows, {evidence: 'all'});
  assert.equal(all.length, 152);
  assert.equal(filterRows(rows, {evidence: 'pending'}).length, 98);
  assert.ok(all.filter(r => !['A', 'B'].includes(r.evidence)).every(r => r.amount === null));
});
test('機型搜尋、年份及容量篩選；不以起價補其他容量', () => {
  const f = {q: 'iphone 16 pro', year: '2024', storage: '256GB', evidence: 'all'};
  const found = filterRows(rows, f);
  assert.equal(found.length, 2);
  assert.equal(amountText(found.find(r => r.model === 'iPhone 16 Pro')), '待查');
  assert.equal(amountText(found.find(r => r.model === 'iPhone 16 Pro Max')), 'NT$44,900');
  assert.equal(filterRows(rows, {q: 'SE 2'}).length, 1);
  assert.equal(filterRows(rows, {q: '<img onerror=alert(1)>'}).length, 0);
});
test('初代美金與後增容量不當成台灣上市價', () => {
  const us = filterRows(rows, {section: 'us'});
  assert.equal(us.length, 4);
  assert.ok(us.every(r => amountText(r).startsWith('US$')));
  assert.equal(filterRows(rows, {section: 'tw-later'}).length, 1);
  assert.equal(filterRows(rows, {section: 'tw-later', evidence: 'all'}).length, 15);
});
test('價格雙向排序，空值永遠在後；不修改原輸入', () => {
  const before = JSON.stringify(rows);
  for (const sort of ['price-asc', 'price-desc']) {
    const found = filterRows(rows, {evidence: 'all', sort});
    const values = found.filter(r => r.amount !== null).map(r => r.amount);
    assert.deepEqual(values, [...values].sort((a, b) => (a - b) * (sort === 'price-desc' ? -1 : 1)));
    assert.ok(found.slice(values.length).every(r => r.amount === null));
  }
  assert.equal(JSON.stringify(rows), before);
  assert.ok(storageSize('1TB') > storageSize('512GB'));
});
test('格式／未知狀態／重複／待查數值／非正數一律拒絕', () => {
  let d = copy(); d.schema_version = 9; assert.throws(() => decode(d));
  d = copy(); d.columns.reverse(); assert.throws(() => decode(d));
  d = copy(); d.records[0][5] = 'E'; assert.throws(() => decode(d));
  d = copy(); d.records.push(d.records[0]); assert.throws(() => decode(d));
  d = copy(); d.records.find(r => r[5] === 'C')[4] = 99999; assert.throws(() => decode(d), /待查金額/);
  d = copy(); d.records.find(r => r[5] === 'A')[4] = 0; assert.throws(() => decode(d));
});
test('來源 URL 拒絕 script／相對 URL／登入資訊與冒用 Apple 的來源', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,test', '/relative', 'http://example.com', 'https://a:b@example.com']) {
    assert.equal(sourceUrl(url), null);
  }
  const d = copy(); d.sources['5'] = 'https://example.com/not-apple'; assert.throws(() => decode(d), /官方來源/);
});
test('缺值與錯誤數值不顯示零元；待查狀態即使意外帶數值也不展示', () => {
  assert.equal(amountText({evidence: 'N', amount: null}), '不適用');
  assert.equal(amountText({evidence: 'C', amount: 99999}), '待查');
  assert.equal(amountText({evidence: 'A', amount: null}), '待查');
  assert.equal(amountText({evidence: 'A', amount: 0}), '待查');
});
