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

test('快報：只看最新一次成功抓取的主價，取漲最多與跌最多',()=>{
  const prices=[row('mobile-mix',1,200000),row('イオシス',1,190000),row('アメモバ',1,195000),
    row('mobile-mix',1,170000,{model:'iPhone 17 Pro'}),row('イオシス',1,165000,{model:'iPhone 17 Pro'}),
    row('mobile-mix',2,203000),row('イオシス',2,185000),row('アメモバ',2,196000),
    row('mobile-mix',2,175000,{model:'iPhone 17 Pro'}),row('mobile-mix',2,150000,{color:'シルバー'}),
    row('アメモバ',2,168000,{model:'iPhone 17 Pro'})];
  const runs=SHOPS_RUNS(1).concat(SHOPS_RUNS(2));
  const f=jp.flash(prices,runs);
  assert.equal(f.latest_at,at(2));assert.equal(f.at,at(2));
  assert.equal(f.count,4);
  assert.equal(f.up.shop,'mobile-mix');assert.equal(f.up.model,'iPhone 17 Pro');assert.equal(f.up.delta,5000);
  assert.equal(f.down.shop,'イオシス');assert.equal(f.down.delta,-5000);
  jp.setLang('zh');
  const html=jp.renderFlash(f);
  assert.doesNotMatch(html,/最近一次有改價|各店沒有改價|該次共/);
  assert.match(html,/這次共 4 筆改價/);
  assert.match(html,/mobile-mix<\/strong> iPhone 17 Pro 256GB 提價最多 <span class="amount">\+¥5,000/);
  assert.match(html,/イオシス<\/strong> iPhone 18 Pro 256GB 砍價最多 <span class="amount">−¥5,000/);
  jp.setLang('ja');
  assert.match(jp.renderFlash(f),/最大の値上げ/);
  assert.doesNotMatch(jp.renderFlash(f),/直近で価格変更があった取得|その取得で/);
  jp.setLang('zh');
});
test('快報：最新一次沒有改價或尚無抓取',()=>{
  const prices=[row('mobile-mix',1,200000),row('イオシス',1,190000),row('mobile-mix',2,203000)];
  const f=jp.flash(prices,SHOPS_RUNS(1).concat(SHOPS_RUNS(2),SHOPS_RUNS(10)));
  assert.equal(f.latest_at,at(10));assert.equal(f.at,at(10));
  assert.equal(f.count,0);assert.match(jp.renderFlash(f),/這次各店都沒有改價/);
  jp.setLang('ja');assert.match(jp.renderFlash(f),/今回はどの店舗も価格変更なし/);jp.setLang('zh');
  assert.equal(jp.flash(prices,[{shop:'mobile-mix',status:'fetch_error',run_at:at(4)}]),null);
});

test('快報：最新一次沒改價，沿用前一次的漲跌與筆數，中日文標示兩個時間',()=>{
  const previous='2026-10-14T20:08:00+09:00', latest='2026-10-15T01:29:00+09:00';
  const prices=[row('mobile-mix',13,200000),row('イオシス',13,190000),row('アメモバ',13,195000),
    row('mobile-mix',14,203000,{observed_at:previous}),row('イオシス',14,185000,{observed_at:previous}),
    row('アメモバ',14,196000,{observed_at:previous})];
  const runs=[...SHOPS_RUNS(13),...jp.SHOPS.map(shop=>({shop,status:'ok',run_at:previous})),
    ...jp.SHOPS.map(shop=>({shop,status:'ok',run_at:latest})),{shop:'mobile-mix',status:'fetch_error',run_at:at(16)}];
  const f=jp.flash(prices,runs.reverse());
  assert.equal(f.latest_at,latest);assert.equal(f.at,previous);assert.equal(f.count,3);
  assert.equal(f.up.shop,'mobile-mix');assert.equal(f.up.delta,3000);
  assert.equal(f.down.shop,'イオシス');assert.equal(f.down.delta,-5000);
  for (const lang of ['zh','ja']) {
    try {
      jp.setLang(lang);
      const html=jp.renderFlash(f);
      assert.ok(html.includes(jp.dateTime(latest)));assert.ok(html.includes(jp.dateTime(previous)));
      assert.equal((html.match(/（日本時間）/g)||[]).length,2);
      assert.match(html,lang==='zh'?/各店沒有改價。以下是最近一次有改價的抓取：/:/は価格変更なし。直近で価格変更があった取得：/);
      assert.match(html,lang==='zh'?/該次共 3 筆改價/:/その取得での価格変更 3 件/);
      assert.doesNotMatch(html,lang==='zh'?/這次共/:/今回の価格変更/);
    } finally { jp.setLang('zh'); }
  }
});

test('快報回溯：跳過色價、首次觀測、異常價、不成功的批次和非主價',()=>{
  const prices=[row('mobile-mix',7,200000),row('イオシス',7,190000),row('アメモバ',7,195000),
    row('mobile-mix',7,198000,{color:'シルバー'}),row('mobile-mix',7,150000,{condition:'中古上限'}),
    row('mobile-mix',7,180000,{carrier:'docomo'}),row('mobile-mix',8,201000),
    row('イオシス',9,191000), // 沒有成功抓取，不採用
    row('mobile-mix',10,199000,{color:'シルバー'}),
    row('mobile-mix',10,151000,{condition:'中古上限'}),row('mobile-mix',10,181000,{carrier:'docomo'}),
    row('アメモバ',10,160000,{model:'iPhone 17 Pro'}), // 首次觀測
    row('アメモバ',11,500000)]; // 異常價
  const runs=[...SHOPS_RUNS(7),...SHOPS_RUNS(8),{shop:'イオシス',status:'parse_error',run_at:at(9)},
    ...SHOPS_RUNS(10),...SHOPS_RUNS(11),...SHOPS_RUNS(12)];
  const f=jp.flash(prices,runs);
  assert.equal(f.latest_at,at(12));assert.equal(f.at,at(8));assert.equal(f.count,1);
  assert.equal(f.up.delta,1000);assert.equal(f.down,null);
});

test('快報回溯：7 天邊界可採用，超過一毫秒不採用',()=>{
  const prices=[row('mobile-mix',1,200000),row('mobile-mix',8,201000)];
  const included=jp.flash(prices,[...SHOPS_RUNS(8),...SHOPS_RUNS(15)]);
  assert.equal(included.at,at(8));assert.equal(included.count,1);
  const excluded=jp.flash(prices,[...SHOPS_RUNS(8),{shop:'mobile-mix',status:'ok',run_at:'2026-10-15T09:30:00.001+09:00'}]);
  assert.equal(excluded.at,excluded.latest_at);assert.equal(excluded.count,0);
});

test('最近變動：25 筆收合為 10 筆，更多剩 15 筆，展開全部並可收起',()=>{
  const changes=Array.from({length:25},(_,i)=>({...row('mobile-mix',15,201000,{model:'機型 '+i}),old_price:200000,new_price:201000}));
  for (const lang of ['zh','ja']) {
    try {
      jp.setLang(lang);
      const collapsed=jp.renderChanges(changes);
      assert.equal((collapsed.match(/class="jp-change"/g)||[]).length,10);
      assert.match(collapsed,lang==='zh'?/更多（還有 15 筆）/:/さらに表示（残り 15 件）/);
      assert.match(collapsed,/<button type="button"[^>]+aria-expanded="false"[^>]+aria-controls="changes-list"/);
      assert.ok(collapsed.indexOf('機型 0')<collapsed.indexOf('機型 9'));
      assert.doesNotMatch(collapsed,/機型 10/);
      const expanded=jp.renderChanges(changes,true);
      assert.equal((expanded.match(/class="jp-change"/g)||[]).length,25);
      assert.match(expanded,/aria-expanded="true"/);
      assert.match(expanded,lang==='zh'?/>收起<\//:/>閉じる<\//);
      assert.equal(jp.renderChanges(changes,false),collapsed);
      for (const length of [0,1,10]) assert.doesNotMatch(jp.renderChanges(changes.slice(0,length)),/<button/);
      assert.match(jp.renderChanges([]),lang==='zh'?/最近 7 天沒有改價紀錄/:/直近 7 日間の価格変更はありません/);
    } finally { jp.setLang('zh'); }
  }
});
function SHOPS_RUNS(day){return jp.SHOPS.map(shop=>({run_at:at(day),shop,status:'ok',rows:'10',error:''}));}
