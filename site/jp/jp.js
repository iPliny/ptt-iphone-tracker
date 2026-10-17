/* 日本資料使用獨立命名空間；不載入 PTT 的 app.js，也不修改其資料。 */
(function () {
  'use strict';
  const SHOPS = ['mobile-mix', 'イオシス', 'アメモバ'];
  const STORAGES = ['256GB', '512GB', '1TB', '2TB'];
  const DAY = 86400000;
  // 介面文字：中文版 jp/、日文版 jp/ja/ 共用同一份程式，依 <html lang> 切換。
  const I18N = {
    zh: {none:'尚無紀錄', notBuying:'不收', since:'此價自 ', jst:'（日本時間）', shopUpdated:'；店家更新日：', unmarked:'未標示',
      storage:'容量', spread:'價差', best:'最高', preparing:'資料準備中', noPublic:'此期間沒有可公開的價格',
      chartLabel:'各店與當下最高買取價階梯走勢，日圓，日本時間', chartTitle:c=>c+'・SIMフリー主價走勢',
      cond:{'未開封':'未開封','中古上限':'中古'}, notOffered:'不收中古', highest:'當下最高價',
      loadFailed:'資料暫時無法載入，請稍後重試', checked:'最近確認：', removed:'下架／不收', restored:'重新收購',
      up:'上漲 ', down:'下跌 ', noChanges:'最近 7 天沒有改價紀錄', ok:'抓取正常', failed:'暫時抓不到',
      notStarted:'尚未開始抓取', lastOk:'最後成功：', moreChanges:n=>'更多（還有 '+n+' 筆）', collapseChanges:'收起',
      flashFallback:'，各店沒有改價。以下是最近一次有改價的抓取：', flashPastCount:n=>'該次共 '+n+' 筆改價',
      flashAt:'最新一次抓取：', flashNone:'這次各店都沒有改價', flashUp:'提價最多', flashDown:'砍價最多', flashCount:n=>'這次共 '+n+' 筆改價', csv:{latest:'最新報價', prices:'價格歷史', runs:'抓取紀錄'}},
    ja: {none:'記録なし', notBuying:'買取不可', since:'この価格の開始：', jst:'（日本時間）', shopUpdated:'／店舗の更新日：', unmarked:'記載なし',
      storage:'容量', spread:'価格差', best:'最高', preparing:'データ準備中', noPublic:'この期間に公開できる価格はありません',
      chartLabel:'各店と現在の最高買取価格の推移（円・日本時間）', chartTitle:c=>c+'・SIMフリーの基本価格の推移',
      cond:{'未開封':'未開封','中古上限':'中古'}, notOffered:'中古買取なし', highest:'現在の最高価格',
      loadFailed:'データを読み込めませんでした。しばらくしてから再度お試しください', checked:'最終確認：', removed:'掲載終了／買取不可', restored:'買取再開',
      up:'値上げ ', down:'値下げ ', noChanges:'直近 7 日間の価格変更はありません', ok:'取得正常', failed:'一時的に取得できません',
      notStarted:'未取得', lastOk:'最終取得成功：', moreChanges:n=>'さらに表示（残り '+n+' 件）', collapseChanges:'閉じる',
      flashFallback:'は価格変更なし。直近で価格変更があった取得：', flashPastCount:n=>'その取得での価格変更 '+n+' 件',
      flashAt:'最新の取得：', flashNone:'今回はどの店舗も価格変更なし', flashUp:'最大の値上げ', flashDown:'最大の値下げ', flashCount:n=>'今回の価格変更 '+n+' 件', csv:{latest:'最新価格', prices:'価格履歴', runs:'取得ログ'}},
  };
  let T = I18N.zh;
  const setLang = lang => { T = String(lang || '').startsWith('ja') ? I18N.ja : I18N.zh; };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => Number.isFinite(value) ? '¥' + value.toLocaleString('en-US') : '—';
  const dateTime = value => {
    const d = new Date(value);
    if (!Number.isFinite(+d)) return T.none;
    return new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Tokyo', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}).format(d);
  };
  // 頁面切換的狀態：未開封或中古上限（各店中古最高收購價）；比較表、走勢、變動、快報都跟著換。
  const CONDITIONS = ['未開封', '中古上限'];
  let COND = '未開封';
  const setCondition = value => { COND = CONDITIONS.includes(value) ? value : '未開封'; return COND; };
  const condLabel = () => T.cond[COND];
  const mainRow = row => row.condition === COND && row.carrier === 'SIMフリー' && !row.color;
  const publicRow = row => row.condition === COND && row.carrier === 'SIMフリー';
  const key = row => [row.shop, row.model, row.storage, row.condition, row.carrier, row.color || ''].join('|');
  const safeURL = value => {
    try {
      const u = new URL(value);
      return u.protocol === 'https:' && ['mobile-mix.jp','k-tai-iosys.com','amemoba.com'].includes(u.hostname) ? u.href : '';
    } catch (_) { return ''; }
  };

  function visiblePrices(values) {
    // 用同一份原始快照計算，避免過濾先後順序改變中位數。
    return values.map((price, i) => {
      if (!Number.isFinite(price) || price <= 0) return null;
      const others = values.filter((p, j) => j !== i && Number.isFinite(p) && p > 0).sort((a,b) => a-b);
      if (!others.length) return price;
      const m = Math.floor(others.length / 2);
      const median = others.length % 2 ? others[m] : (others[m-1] + others[m]) / 2;
      return price < median / 2 || price > median * 2 ? null : price;
    });
  }

  function comparison(latest, model) {
    return STORAGES.filter(storage => latest.some(r => r.model === model && r.storage === storage && mainRow(r))).map(storage => {
      const rows = SHOPS.map(shop => latest.find(r => r.shop === shop && r.model === model && r.storage === storage && mainRow(r)) || null);
      const values = visiblePrices(rows.map(r => r?.price_jpy ?? null));
      const present = values.filter(Number.isFinite);
      return {storage, rows, values, highest:present.length ? Math.max(...present) : null,
        spread:present.length >= 2 ? Math.max(...present)-Math.min(...present) : null};
    });
  }

  function timeline(prices, model, storage, days, end) {
    const events = prices.filter(r => mainRow(r) && r.model === model && r.storage === storage && SHOPS.includes(r.shop) && Number.isFinite(Date.parse(r.observed_at)))
      .map(r => ({...r, time:Date.parse(r.observed_at)})).sort((a,b) => a.time-b.time);
    if (!events.length) return {times:[], series:[], start:end, end};
    end = Math.max(end, events[events.length-1].time);
    const start = days === 'all' ? events[0].time : Math.max(events[0].time, end - Number(days)*DAY);
    const times = [...new Set([start, ...events.filter(r => r.time >= start && r.time <= end).map(r => r.time), end])].sort((a,b)=>a-b);
    const values = SHOPS.map(()=>null), series = [...SHOPS, '當下最高價'].map(()=>[]);
    let index=0;
    for (const time of times) {
      while (index < events.length && events[index].time <= time) {
        const row = events[index++];
        values[SHOPS.indexOf(row.shop)] = row.price_jpy;
      }
      const visible = visiblePrices(values);
      visible.forEach((p,i) => series[i].push(p));
      const present=visible.filter(Number.isFinite);
      series[3].push(present.length ? Math.max(...present) : null);
    }
    return {times, series, start, end};
  }

  function stepPath(times, values, x, y) {
    let path='', active=false;
    times.forEach((time,i) => {
      const px=x(time).toFixed(2), price=values[i];
      if (active) path += ' H' + px;
      if (Number.isFinite(price)) {
        path += (active ? ' V' : ' M'+px+' ') + y(price).toFixed(2);
        active=true;
      } else active=false;
    });
    return path.trim();
  }

  function recentChanges(prices, end) {
    const events = prices.filter(publicRow).filter(r => SHOPS.includes(r.shop) && Number.isFinite(Date.parse(r.observed_at)))
      .slice().sort((a,b)=>Date.parse(a.observed_at)-Date.parse(b.observed_at));
    const current = new Map(), changes=[];
    // 同一次抓取的各店一起更新後才檢查異常，避免假想的中間快照。
    for (let index=0; index<events.length;) {
      const at=events[index].observed_at, batch=[];
      while(index<events.length && events[index].observed_at===at) batch.push(events[index++]);
      const previous = new Map(current);
      batch.forEach(r => current.set(key(r),r));
      const approved = (snapshot,row) => {
        if (!Number.isFinite(row.price_jpy)) return true;
        const bases=SHOPS.map(shop=>snapshot.get([shop,row.model,row.storage,COND,'SIMフリー',''].join('|'))?.price_jpy ?? null);
        const i=SHOPS.indexOf(row.shop), main=bases[i];
        if (row.color && !Number.isFinite(main)) return false;
        // 色價只與同規格各店的主價核對，不把顏色減價當成另一家店。
        bases[i]=row.price_jpy;
        return visiblePrices(bases)[i] !== null;
      };
      for(const row of batch) {
        const old=previous.get(key(row));
        if (!old || old.price_jpy===row.price_jpy || Date.parse(at)<end-7*DAY || Date.parse(at)>end) continue;
        if (!approved(previous,old) || !approved(current,row)) continue;
        changes.push({...row, old_price:old.price_jpy, new_price:row.price_jpy});
      }
    }
    return changes.reverse();
  }

  // 最新成功抓取沒改價時，回溯最近 7 天內有主價改價的成功抓取。
  function flash(prices, runs) {
    const successes=runs.filter(r=>r.status==='ok' && Number.isFinite(Date.parse(r.run_at)))
      .slice().sort((a,b)=>Date.parse(b.run_at)-Date.parse(a.run_at));
    const latest_at=successes[0]?.run_at;
    if (!latest_at) return null;
    const batches=new Map();
    for (const row of recentChanges(prices, Date.parse(latest_at))) {
      if (row.color || !Number.isFinite(row.old_price) || !Number.isFinite(row.new_price)) continue;
      const time=Date.parse(row.observed_at);
      if (!batches.has(time)) batches.set(time, []);
      batches.get(time).push({...row, delta:row.new_price-row.old_price});
    }
    const at=successes.find(r=>batches.has(Date.parse(r.run_at)))?.run_at || latest_at;
    const changes=batches.get(Date.parse(at)) || [];
    const pick=(sign)=>changes.filter(r=>Math.sign(r.delta)===sign).sort((a,b)=>sign*(b.delta-a.delta))[0] || null;
    return {latest_at, at, count:changes.length, up:pick(1), down:pick(-1)};
  }

  function renderFlash(result) {
    if (!result) return '<p class="empty">'+T.preparing+'</p>';
    const fallback=result.latest_at && result.latest_at!==result.at;
    const line=(r,label)=>r?'<p class="jp-flash-item '+(r.delta>0?'up':'down')+'"><strong>'+esc(r.shop)+'</strong> '+esc(r.model+' '+r.storage)+' '+label
      +' <span class="amount">'+(r.delta>0?'+':'−')+money(Math.abs(r.delta))+'</span><span class="detail">'+money(r.old_price)+' → '+money(r.new_price)+'</span></p>':'';
    const body=result.count?line(result.up,T.flashUp)+line(result.down,T.flashDown)+'<p class="hint">'+esc((fallback?T.flashPastCount:T.flashCount)(result.count))+'</p>'
      :'<p class="empty">'+T.flashNone+'</p>';
    const intro=fallback?T.flashAt+esc(dateTime(result.latest_at))+T.jst+T.flashFallback+esc(dateTime(result.at))+T.jst
      :T.flashAt+esc(dateTime(result.at))+T.jst;
    return '<p class="hint">'+intro+'</p>'+body;
  }

  function renderChanges(changes, expanded=false) {
    if (!changes.length) return '<p class="empty">'+T.noChanges+'</p>';
    const visible=expanded?changes:changes.slice(0,10);
    const rows=visible.map(r=>{
      const delta=Number.isFinite(r.new_price)&&Number.isFinite(r.old_price)?r.new_price-r.old_price:null;
      const change=delta===null?(r.new_price===null?T.removed:T.restored):(delta>0?T.up:T.down)+money(Math.abs(delta));
      return '<div class="jp-change"><time datetime="'+esc(r.observed_at)+'">'+esc(dateTime(r.observed_at))+'</time><strong>'+esc(r.shop)+'</strong><span class="spec">'+esc(r.model+' '+r.storage+(r.color?' · '+r.color:''))+'</span><span class="amount">'+money(r.old_price)+' → '+money(r.new_price)+'<span class="delta">'+esc(change)+'</span></span></div>';
    }).join('');
    const button=changes.length>10?'<button type="button" class="jp-changes-toggle" aria-expanded="'+expanded+'" aria-controls="changes-list">'+esc(expanded?T.collapseChanges:T.moreChanges(changes.length-10))+'</button>':'';
    return '<div id="changes-list">'+rows+'</div>'+button;
  }

  function shopStatuses(runs) {
    return SHOPS.map(shop=>{
      const all=runs.filter(r=>r.shop===shop).slice().sort((a,b)=>Date.parse(a.run_at)-Date.parse(b.run_at));
      return {shop, latest:all[all.length-1], success:all.filter(r=>r.status==='ok').at(-1)};
    });
  }

  function colorNotes(data, row, values, shopIndex) {
    if (!row || row.shop !== 'mobile-mix') return '';
    const colors=data.latest.filter(r=>r.shop===row.shop && r.model===row.model && r.storage===row.storage && publicRow(r) && r.color);
    if (!colors.length) return '';
    const palette=[...new Set([...data.latest,...data.prices].filter(r=>r.shop===row.shop && r.model===row.model && publicRow(r) && r.color).map(r=>r.color))];
    return '<ul class="jp-colors">'+palette.map(color=>{
      const found=colors.find(r=>r.color===color);
      const candidate=values.slice(); candidate[shopIndex]=found?.price_jpy ?? null;
      const price=visiblePrices(candidate)[shopIndex];
      return '<li>'+esc(color)+' '+(found ? money(price) : T.notBuying)+'</li>';
    }).join('')+'</ul>';
  }

  function renderComparison(data, model) {
    const groups=comparison(data.latest,model);
    if (!groups.length) return '<p class="empty">'+T.preparing+'</p>';
    // 整份資料都沒有這個狀態的店（mobile-mix 只收未開封）標示不收，不和「—」待確認混在一起。
    const offered=SHOPS.map(shop=>data.latest.some(r=>r.shop===shop && mainRow(r)));
    return '<table class="jp-table"><thead><tr><th scope="col">'+T.storage+'</th>'+SHOPS.map(s=>'<th scope="col">'+s+'</th>').join('')+'<th scope="col">'+T.spread+'</th></tr></thead><tbody>'+groups.map(group=>
      '<tr><th scope="row">'+group.storage+'</th>'+group.rows.map((row,i)=>{
        const price=group.values[i], best=price!==null && price===group.highest;
        const info=row ? T.since+dateTime(row.since)+T.jst+T.shopUpdated+(row.shop_updated || T.unmarked) : '';
        const url=row ? safeURL(row.source_url) : '';
        if (!offered[i]) return '<td data-label="'+SHOPS[i]+'"><div><span class="jp-none">'+T.notOffered+'</span></div></td>';
        const label='<span class="jp-price">'+money(price)+'</span>';
        return '<td data-label="'+SHOPS[i]+'"'+(best?' class="jp-best"':'')+'><div>'+(url?'<a href="'+esc(url)+'" title="'+esc(info)+'">'+label+'</a>':label)+(best?'<span class="jp-badge">'+T.best+'</span>':'')+(price!==null?colorNotes(data,row,group.rows.map(r=>r?.price_jpy ?? null),i):'')+'</div></td>';
      }).join('')+'<td data-label="'+T.spread+'"><span class="jp-spread">'+money(group.spread)+'</span></td></tr>').join('')+'</tbody></table>';
  }

  function renderChart(chart, width) {
    if (!chart.times.length) return '<p class="empty">'+T.preparing+'</p>';
    const all=chart.series.flat().filter(Number.isFinite);
    if (!all.length) return '<p class="empty">'+T.noPublic+'</p>';
    const w=Math.max(260,width), h=w<500?260:300, left=72, right=12, top=18, bottom=42;
    const min=Math.min(...all), max=Math.max(...all), pad=Math.max((max-min)*.15,2000);
    const low=Math.max(0,min-pad), high=max+pad, span=chart.end-chart.start;
    const x=t=>span ? left+(t-chart.start)/span*(w-left-right) : (left+w-right)/2;
    const y=p=>top+(high-p)/(high-low)*(h-top-bottom);
    let svg='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+T.chartLabel+'"><title>'+esc(T.chartTitle(condLabel()))+'</title>';
    for(let i=0;i<4;i++) {
      const price=low+(high-low)*i/3, py=y(price);
      svg+='<line class="grid" x1="'+left+'" x2="'+(w-right)+'" y1="'+py+'" y2="'+py+'"/><text class="axis" x="'+(left-7)+'" y="'+(py+4)+'" text-anchor="end">'+money(Math.round(price/1000)*1000)+'</text>';
    }
    [chart.start,chart.end].filter((t,i,a)=>!i||t!==a[0]).forEach((t,i)=>{
      svg+='<text class="axis" x="'+x(t)+'" y="'+(h-17)+'" text-anchor="'+(span?(i?'end':'start'):'middle')+'">'+esc(dateTime(t).slice(5))+'</text>';
    });
    chart.series.forEach((values,i)=>{
      svg+='<path class="jp-series shop-'+i+(i===3?' jp-high':'')+'" d="'+stepPath(chart.times,values,x,y)+'"/>';
      chart.times.forEach((time,j)=>{
        if(!Number.isFinite(values[j]) || (j>0 && values[j]===values[j-1] && j<chart.times.length-1)) return;
        svg+='<circle class="shop-'+i+'" cx="'+x(time)+'" cy="'+y(values[j])+'" r="'+(i===3?3:2.5)+'" fill="currentColor"><title>'+esc((SHOPS[i]||T.highest)+' '+dateTime(time)+T.jst+' '+money(values[j]))+'</title></circle>';
      });
    });
    return svg+'</svg>';
  }

  const api={SHOPS, setLang, setCondition, visiblePrices, comparison, timeline, stepPath, recentChanges, flash, renderFlash, renderChanges, shopStatuses, renderComparison, renderChart, dateTime, money};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  if(typeof document==='undefined') return;

  async function boot() {
    const get=id=>document.getElementById(id);
    setLang(document.documentElement.lang);
    const base=document.body.dataset.base || '';
    let data;
    try {
      const response=await fetch(base+'data.json');
      if(!response.ok) throw new Error('load failed');
      data=await response.json();
    } catch (_) {
      get('updated').textContent=T.loadFailed;
      return;
    }
    const end=Date.parse(data.generated_at);
    const last=data.latest.map(r=>r.last_checked).filter(Boolean).sort().at(-1);
    get('updated').textContent=last?T.checked+dateTime(last)+T.jst:T.preparing;
    const params=new URLSearchParams(location.search);
    setCondition(params.get('c')==='used'?'中古上限':'未開封');
    const compare=()=>{get('comparison').innerHTML=renderComparison(data,get('compare-model').value);};
    const chart=()=>{
      const model=get('trend-model').value;
      const available=STORAGES.filter(s=>data.prices.some(r=>r.model===model && r.storage===s && mainRow(r)));
      for(const option of get('trend-storage').options) option.disabled=available.length>0 && !available.includes(option.value);
      if(available.length && !available.includes(get('trend-storage').value)) get('trend-storage').value=available[0];
      get('trend').innerHTML=renderChart(timeline(data.prices,model,get('trend-storage').value,get('trend-days').value,end),get('trend').clientWidth);
    };
    get('legend').innerHTML=[...SHOPS,T.highest].map((s,i)=>'<span><i class="jp-key shop-'+i+(i===3?' best':'')+'"></i>'+s+'</span>').join('');
    let changes=[], expanded=false;
    // 切換未開封／中古：標籤、說明文字與四個區塊一起重畫；網址加 ?c=used 方便分享。
    const render=()=>{
      document.querySelectorAll('[data-cond-label]').forEach(el=>{el.textContent=condLabel();});
      document.querySelectorAll('[data-cond-only]').forEach(el=>{el.hidden=el.dataset.condOnly!==COND;});
      document.querySelectorAll('.jp-cond button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cond===COND)));
      // 切換語言時保留目前狀態。
      document.querySelectorAll('.jp-lang').forEach(el=>{
        el.dataset.href=el.dataset.href||el.getAttribute('href');
        el.setAttribute('href',el.dataset.href+(COND==='中古上限'?'?c=used':''));
      });
      get('flash').innerHTML=renderFlash(flash(data.prices,data.runs||[]));
      compare();chart();
      changes=recentChanges(data.prices,end);expanded=false;
      get('changes').innerHTML=renderChanges(changes,expanded);
    };
    document.querySelectorAll('.jp-cond button').forEach(b=>b.addEventListener('click',()=>{
      if (b.dataset.cond===COND) return;
      setCondition(b.dataset.cond);
      const url=new URL(location.href);
      if (COND==='中古上限') url.searchParams.set('c','used'); else url.searchParams.delete('c');
      history.replaceState(null,'',url);
      render();
    }));
    get('compare-model').addEventListener('change',compare);
    ['trend-model','trend-storage','trend-days'].forEach(id=>get(id).addEventListener('change',chart));
    window.addEventListener('resize',chart);
    render();
    get('changes').addEventListener('click',event=>{
      if (!event.target.closest('.jp-changes-toggle')) return;
      expanded=!expanded;
      get('changes').innerHTML=renderChanges(changes,expanded);
      get('changes').querySelector('.jp-changes-toggle').focus();
    });
    get('statuses').innerHTML=shopStatuses(data.runs).map(s=>'<article><strong>'+s.shop+'</strong><p'+(s.latest&&s.latest.status!=='ok'?' class="failed"':'')+'>'+(s.latest?(s.latest.status==='ok'?T.ok:T.failed):T.notStarted)+'</p><p>'+T.lastOk+(s.success?esc(dateTime(s.success.run_at))+T.jst:T.none)+'</p></article>').join('');
    get('downloads').innerHTML=(data.downloads||[]).map(name=>['latest','prices','runs'].includes(name)?'<a href="'+base+'../data/jp/'+name+'.csv" download>'+T.csv[name]+' CSV</a>':'').join('');
  }
  boot();
})();
