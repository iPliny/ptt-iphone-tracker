const {test}=require('node:test');
const assert=require('node:assert/strict');
const jp=require('../site/jp/jp.js');
const at=day=>`2026-10-${String(day).padStart(2,'0')}T09:30:00+09:00`;
const row=(shop,day,price,extra={})=>({shop,model:'iPhone 18 Pro',storage:'256GB',condition:'未開封',carrier:'SIMフリー',color:'',price_jpy:price,observed_at:at(day),since:at(day),source_url:'https://mobile-mix.jp/?category=7',...extra});

test('異常值和兩家邊界：半價、兩倍本身仍可顯示',()=>{
  assert.deepEqual(jp.visiblePrices([200000,210000,90000]),[200000,210000,null]);
  assert.deepEqual(jp.visiblePrices([200000,210000,430000]),[200000,210000,null]);
  assert.deepEqual(jp.visiblePrices([200000,400000,null]),[200000,400000,null]);
  assert.deepEqual(jp.visiblePrices([200000,500000,null]),[null,null,null]);
  assert.deepEqual(jp.visiblePrices([500000,null,null]),[500000,null,null]);
});
test('比較表限未開封SIMフリー主價，價差、最高與色價不收',()=>{
  const latest=[row('mobile-mix',1,212000),row('イオシス',1,192000),row('アメモバ',1,200000),
    row('mobile-mix',1,197000,{color:'グレイシャー'}),row('mobile-mix',1,212000,{color:'バーガンディ'}),
    row('mobile-mix',1,220000,{color:'シルバー',storage:'512GB'}),
    row('イオシス',1,900000,{condition:'中古上限'}),row('アメモバ',1,990000,{carrier:'docomo'})];
  const group=jp.comparison(latest,'iPhone 18 Pro')[0];
  assert.equal(group.highest,212000);assert.equal(group.spread,20000);
  const html=jp.renderComparison({latest,prices:[]},'iPhone 18 Pro');
  assert.match(html,/シルバー 不收/);assert.match(html,/グレイシャー ¥197,000/);
  assert.match(html,/最高/);assert.doesNotMatch(html,/900,000|990,000/);
});
test('異常主價不出現在比較表或色價提示',()=>{
  const latest=[row('mobile-mix',1,430000),row('mobile-mix',1,420000,{color:'シルバー'}),row('イオシス',1,200000),row('アメモバ',1,210000)];
  const html=jp.renderComparison({latest,prices:[]},'iPhone 18 Pro');
  assert.doesNotMatch(html,/430,000|420,000/);assert.match(html,/—/);
});
test('階梯線保留期間前的價格，消失斷線，恢復才重畫',()=>{
  const prices=[row('mobile-mix',1,200000),row('mobile-mix',4,null),row('mobile-mix',6,205000),row('イオシス',2,190000)];
  const timeline=jp.timeline(prices,'iPhone 18 Pro','256GB','7',Date.parse(at(9)));
  assert.equal(timeline.start,Date.parse(at(2)));
  assert.deepEqual(timeline.series[0],[200000,null,205000,205000]);
  assert.deepEqual(timeline.series[3],[200000,190000,205000,205000]);
  const path=jp.stepPath([0,1,2,3],[10,null,20,20],x=>x,y=>y);
  assert.equal(path,'M0.00 10.00 H1.00 M2.00 20.00 H3.00 V20.00');
});
test('走勢和最近變動也排除異常價；只顯示最近7天',()=>{
  const prices=[row('mobile-mix',1,200000),row('イオシス',1,210000),row('アメモバ',1,205000),
    row('mobile-mix',2,199000),row('mobile-mix',5,430000),row('mobile-mix',6,199000),row('イオシス',6,208000),
    row('アメモバ',6,null),row('アメモバ',7,207000)];
  const chart=jp.timeline(prices,'iPhone 18 Pro','256GB','all',Date.parse(at(10)));
  assert.equal(chart.series[0][2],null);
  const changes=jp.recentChanges(prices,Date.parse(at(10)));
  assert.equal(changes.length,3);
  assert.equal(changes[0].old_price,null);assert.equal(changes[0].new_price,207000);
  assert.ok(changes.every(c=>c.new_price!==430000 && c.old_price!==430000));
});
test('最後一次失敗顯示失敗，保留最後成功時間',()=>{
  const [state]=jp.shopStatuses([{shop:'mobile-mix',run_at:at(1),status:'ok'},{shop:'mobile-mix',run_at:at(2),status:'parse_error'}]);
  assert.equal(state.latest.status,'parse_error');assert.equal(state.success.run_at,at(1));
});
test('單點走勢與日圓、日本時間',()=>{
  const chart=jp.timeline([row('mobile-mix',1,200000)],'iPhone 18 Pro','256GB','all',Date.parse(at(1)));
  assert.match(jp.renderChart(chart,315),/<circle/);assert.doesNotMatch(jp.renderChart(chart,315),/NaN|Infinity/);
  assert.equal(jp.dateTime('2026-10-01T00:30:00Z'),'2026-10-01 09:30');
  assert.equal(jp.money(null),'—');assert.equal(jp.money(245000),'¥245,000');
});
test('來源字串經跳脫，非來源連結不輸出',()=>{
  const latest=[row('mobile-mix',1,200000,{source_url:'javascript:alert(1)',shop_updated:'<script>bad</script>'})];
  assert.doesNotMatch(jp.renderComparison({latest,prices:[]},'iPhone 18 Pro'),/javascript:|<script>/);
});
test('日文版介面文字：同一份程式依語言切換，數字與資料不變',()=>{
  const latest=[row('mobile-mix',1,212000),row('イオシス',1,192000),row('mobile-mix',1,220000,{color:'シルバー',storage:'512GB'}),
    row('mobile-mix',1,197000,{color:'グレイシャー'})];
  const prices=[row('mobile-mix',1,212000,{color:'シルバー'})];
  try {
    jp.setLang('ja');
    const html=jp.renderComparison({latest,prices},'iPhone 18 Pro');
    assert.match(html,/価格差/);assert.match(html,/シルバー 買取不可/);assert.match(html,/¥212,000/);
    assert.doesNotMatch(html,/價差|不收|此價自/);
    assert.equal(jp.dateTime('bad'),'記録なし');
    assert.match(jp.renderChart(jp.timeline([row('mobile-mix',1,200000)],'iPhone 18 Pro','256GB','all',Date.parse(at(1))),315),/基本価格の推移/);
  } finally { jp.setLang('zh'); }
  assert.match(jp.renderComparison({latest,prices},'iPhone 18 Pro'),/價差/);
});
