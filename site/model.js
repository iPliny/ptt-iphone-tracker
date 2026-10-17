// 預產靜態機型頁與原有 model.html?m=<型號>&s=<容量> 共用互動行為。
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const { esc, money, dayOf, modelUrl, modelPageUrl, compareStorage, itemHtml, soldNote, daysCell, priceEventText } = PttCommon;
  const PAGE = 10;
  const EVENT_LIMIT = 10;

  const params = new URLSearchParams(location.search);
  const staticModel = document.body && document.body.dataset.model || "";
  const model = staticModel || params.get("m") || "";
  // 同一機型的容量／篩選參數共用 canonical；空白機型不宣告 canonical。
  if (model) {
    let canonical = $('link[rel="canonical"]');
    if (!canonical || !canonical.href) {
      canonical = document.createElement("link");
      document.head.appendChild(canonical);
    }
    canonical.rel = "canonical";
    canonical.href = $('meta[name="site-url"]').content + modelPageUrl(model);
  }
  let storage = params.get("s");  // null = 全部容量
  let D = null;
  let mine = [];       // 這個機型的全部文章
  let storages = [];   // 這個機型出現過的容量，依大小排序
  let listLimit = PAGE;
  const watchlist = PttWatchlist.createStore(() => window.localStorage);
  let watchFeedbackTimer;

  if (!staticModel) document.title = (model || "機型行情") + " · PTT MacShop交易觀測";
  $("#model-name").textContent = model || "未指定機型";

  fetch((staticModel ? "../" : "") + "data.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch((e) => {
      const message = "資料載入失敗（" + e.message + "）";
      $("#updated").textContent = staticModel
        ? $("#updated").textContent + " · 即時" + message + "，顯示建置時資料" : message;
    });

  function init(data) {
    D = data;
    mine = D.listings.filter((r) => r.model === model);
    $("#updated").textContent = "最後回訪 " + (D.last_checked || "—") + " · 這個機型共追蹤 " + mine.length + " 篇";
    if (!model || (!mine.length && !(D.model_totals || []).some((r) => r.model === model))) {
      $("#model-main").hidden = true;
      $("#watch-model").hidden = true;
      $("#missing-text").innerHTML = (model ? "目前資料裡沒有「" + esc(model) + "」的文章。" : "網址沒有指定機型。") +
        ' <a href="' + (staticModel ? "../" : "./") + '">回到總覽</a>，從型號行情表點選機型。';
      $("#model-missing").hidden = false;
      return;
    }
    storages = Array.from(new Set(mine.map((r) => r.storage))).sort(compareStorage);
    if (storage !== null && !storages.includes(storage)) storage = null;
    $("#model-main").hidden = false;
    $("#watch-model").hidden = false;

    $("#storage-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-storage]");
      if (b) choose(b.dataset.storage === "*" ? null : b.dataset.storage);
    });
    $("#compare").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-storage]");
      if (b) choose(b.dataset.storage);
    });
    $("#status-f").addEventListener("change", () => { listLimit = PAGE; renderList(); });
    $("#sort-f").addEventListener("change", () => { listLimit = PAGE; renderList(); });
    $("#more").addEventListener("click", () => { listLimit += PAGE; renderList(); });
    $("#watch-model").addEventListener("click", toggleWatch);
    window.addEventListener("storage", (e) => {
      if (e.key !== null && e.key !== PttWatchlist.STORAGE_KEY) return;
      try { if (e.storageArea !== window.localStorage) return; } catch (_) { return; }
      watchlist.reload();
      renderWatch();
    });
    render();
  }

  function choose(s) {
    storage = s;
    listLimit = PAGE;
    const query = new URLSearchParams();
    if (storage !== null) query.set("s", storage);
    history.replaceState(null, "", staticModel
      ? location.pathname + (query.toString() ? "?" + query : "") : modelUrl(model, storage));
    render();
  }

  function selected() {
    return storage === null ? mine : mine.filter((r) => r.storage === storage);
  }

  function statsFor(s) {
    if (s === null) return (D.model_totals || []).find((m) => m.model === model) || null;
    return D.models.find((m) => m.model === model && m.storage === s) || null;
  }

  const storageLabel = (s) => s || "容量未提供";

  function render() {
    renderTabs();
    renderWatch();
    renderApple();
    renderKpis();
    renderTrend();
    renderChart();
    renderCompare();
    renderColors();
    renderList();
    renderEvents();
  }

  function renderTabs() {
    const tabs = [["*", "全部容量", mine.length]].concat(
      storages.map((s) => [s, storageLabel(s), mine.filter((r) => r.storage === s).length]));
    $("#storage-tabs").innerHTML = tabs.map(([key, label, n]) => {
      const on = key === "*" ? storage === null : storage === key;
      return `<button type="button" data-storage="${esc(key)}" class="${on ? "on" : ""}" aria-pressed="${on}">${esc(label)} <span class="count">${n}</span></button>`;
    }).join("");
  }

  // ---------- Apple 原廠：在售給官網連結與現行售價，停售給最終官方售價 ----------
  function renderApple() {
    const a = (D.apple || {})[model];
    $("#apple").hidden = !a;
    if (!a) return;
    const onSale = !!a.buy_url;
    const caps = storage !== null ? [storage] : Object.keys(a.prices).sort(compareStorage);
    const rows = caps.map((s) => `<tr><td>${esc(storageLabel(s))}</td><td class="num">${a.prices[s]
      ? money(a.prices[s]) : `<span class="muted">${onSale ? "官網沒有這個容量" : "查無官方價格"}</span>`}</td></tr>`).join("");
    const head = onSale
      ? `<a class="buy" href="${esc(a.buy_url)}" target="_blank" rel="noopener">到 Apple 官網購買 ↗</a>`
      : `<span class="muted">官網已停售${a.discontinued ? "（" + esc(a.discontinued) + "）" : ""}</span>`;
    const sources = (a.sources || []).map((u, i) =>
      `<a href="${esc(u)}" target="_blank" rel="noopener">來源${a.sources.length > 1 ? i + 1 : ""}</a>`).join("、");
    $("#apple").innerHTML = `<div class="card-head"><h2>Apple 原廠</h2>${head}</div>` +
      `<div class="scroll"><table><thead><tr><th>容量</th><th class="num">${onSale ? "官網售價" : "最終官方售價"}</th></tr></thead><tbody>${rows}</tbody></table></div>` +
      `<p class="hint">${onSale
        ? "官網售價為 " + esc(a.checked_at) + " 在 Apple 台灣官網查到的價格，購買前請以官網為準。"
        : "最終官方售價是 Apple 台灣官網停售前最後的建議售價。" + (sources ? "（" + sources + "）" : "")}</p>`;
  }

  function renderKpis() {
    const m = statsFor(storage);
    const days = m && m.median_days != null
      ? m.median_days + " 天" : "—";
    const daysNote = m && m.days_samples
      ? m.days_samples + " 筆樣本" + (m.days_estimated ? "（推估）" : "") : "還沒有售出天數";
    const cards = [
      ["刊登", m ? m.listed : selected().length, m ? "在架 " + m.active + " · 已售 " + m.sold + (m.multi ? " · 多品項 " + m.multi : "") : "沒有可用的標價"],
      ["刊登中位數", money(m && m.median_price), m ? money(m.min_price) + " – " + money(m.max_price) : ""],
      ["成交中位數", money(m && m.median_sold_price), "售出時的最後標價"],
      ["售出天數中位數", days, daysNote],
    ];
    $("#kpis").innerHTML = cards.map(([label, v, note]) =>
      `<div class="kpi"><div class="label">${label}</div><div class="value">${esc(v)}</div><div class="note">${esc(note) || "&nbsp;"}</div></div>`
    ).join("");
  }

  // ---------- 行情走勢：每天在架文章的標價中位數 ----------
  const TREND_COLORS = 5;  // style.css 的 .s1～.s5，顏色跟著容量（或全新／二手）走

  function trendLines() {
    const T = D.trends || { series: [] };
    const all = T.series.filter((x) => x.model === model);
    if (storage !== null) {
      return all.filter((x) => x.storage === storage).sort((a, b) => a.brand_new - b.brand_new)
        .map((x) => ({ ...x, label: storageLabel(x.storage) + (x.brand_new ? " 全新未拆" : " 二手"), cls: x.brand_new ? "s2" : "s1" }));
    }
    // 全部容量：每個容量一條二手線；整個機型都沒有二手行情時改用全新
    const used = all.filter((x) => !x.brand_new);
    const pick = used.length ? used : all;
    return pick.sort((a, b) => compareStorage(a.storage, b.storage)).map((x) => ({
      ...x, label: storageLabel(x.storage) + (x.brand_new ? " 全新未拆" : " 二手"),
      cls: "s" + (storages.indexOf(x.storage) % TREND_COLORS + 1),
    }));
  }

  function lastIndex(values) {
    for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return i;
    return -1;
  }

  function changeText(values, days) {
    const i = lastIndex(values);
    const before = i - days >= 0 ? values[i - days] : null;
    if (i < 0 || before == null) return "—";
    const pct = (values[i] - before) / before * 100;
    const r = Math.round(pct * 10) / 10;
    return r === 0 ? "持平" : (r > 0 ? "+" : "−") + Math.abs(r).toFixed(1) + "%";
  }

  function renderTrend() {
    const T = D.trends || {};
    const lines = trendLines();
    $("#trend-card").hidden = !lines.length;
    if (!lines.length) return;
    const dates = lines[0].values.map((_, i) => {
      const d = new Date(T.start + "T00:00:00Z");
      d.setUTCDate(d.getUTCDate() + i);
      return d.toISOString().slice(0, 10);
    });
    $("#trend-summary").innerHTML = lines.map((l) => {
      const i = lastIndex(l.values);
      return `<div class="trend-item"><div class="label"><span class="key ${l.cls}"></span>${esc(l.label)}</div>` +
        `<div class="value">${money(l.values[i])}</div>` +
        `<div class="note">7 天 ${changeText(l.values, 7)} · 30 天 ${changeText(l.values, 30)}</div></div>`;
    }).join("");

    const W = 900, H = 220, L = 64, R = 16, T0 = 12, B = 26;
    const vals = lines.flatMap((l) => l.values.filter((v) => v != null));
    // 縱軸用整數刻度（$500、$1,000…），線不貼著上下緣
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const step = [100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000].find((w) => Math.max(hi - lo, 1) / w <= 3) || 50000;
    let y0 = Math.floor(lo / step) * step, y1 = Math.ceil(hi / step) * step;
    if (lo - y0 < step * 0.2) y0 = Math.max(0, y0 - step);
    if (y1 - hi < step * 0.2) y1 += step;
    const n = dates.length;
    const x = (i) => L + (W - L - R) * (n > 1 ? i / (n - 1) : 0.5);
    const y = (v) => T0 + (H - T0 - B) * (1 - (v - y0) / (y1 - y0));
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(model)} 每日行情走勢">`;
    for (let v = y0; v <= y1; v += step) {
      s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      s += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${money(v)}</text>`;
    }
    const ticks = Math.min(5, n - 1);
    for (let k = 0; k <= ticks; k++) {
      const i = ticks ? Math.round((n - 1) * k / ticks) : 0;
      s += `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="${k === 0 ? "start" : k === ticks ? "end" : "middle"}">${dates[i].slice(5)}</text>`;
    }
    lines.forEach((l) => {
      // 在架篇數不夠的日子留空，線斷開；只有一天的段落畫成點
      let d = "", run = 0;
      l.values.forEach((v, i) => {
        if (v == null) { run = 0; return; }
        d += (run ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
        run++;
      });
      s += `<path class="trend-line ${l.cls}" d="${d}"/>`;
      l.values.forEach((v, i) => {
        const lone = v != null && l.values[i - 1] == null && l.values[i + 1] == null;
        if (lone || i === lastIndex(l.values)) s += `<circle class="trend-dot ${l.cls}" cx="${x(i)}" cy="${y(v)}" r="4"/>`;
      });
    });
    s += `<line class="crosshair" id="trend-x" x1="0" x2="0" y1="${T0}" y2="${H - B}" visibility="hidden"/>`;
    s += `<rect class="trend-hit" x="${L}" y="${T0}" width="${W - L - R}" height="${H - T0 - B}"/>`;
    $("#trend").innerHTML = s + '</svg><div class="tip" id="trend-tip" hidden></div>';

    const svg = $("#trend svg"), tip = $("#trend-tip"), cross = $("#trend-x");
    const move = (e) => {
      const box = svg.getBoundingClientRect();
      const px = (e.clientX - box.left) / box.width * W;
      const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
      cross.setAttribute("visibility", "visible");
      tip.innerHTML = `<div class="tip-date">${dates[i]}</div>` + lines.map((l) =>
        `<div class="tip-row"><span class="key ${l.cls}"></span><strong>${money(l.values[i])}</strong> <span class="muted">${esc(l.label)}</span></div>`).join("");
      tip.hidden = false;
      const left = x(i) / W * box.width;
      tip.style.left = Math.min(left + 12, box.width - tip.offsetWidth - 4) + "px";
    };
    const leave = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); };
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerleave", leave);
    renderDist(lines);
  }

  // 目前在架價格區間：只在單一容量時畫，避免不同容量混在一起
  function renderDist(lines) {
    const box = $("#dist");
    const first = lines[0];
    const prices = storage === null || !first ? [] : mine.filter((r) => r.storage === storage &&
      r.brand_new === first.brand_new && r.price && (r.status === "在售" || r.status === "交易中")).map((r) => r.price);
    box.hidden = prices.length < 3;
    if (box.hidden) return;
    const lo = Math.min(...prices), hi = Math.max(...prices);
    const step = [500, 1000, 2000, 2500, 5000, 10000, 20000].find((w) => Math.floor(hi / w) - Math.floor(lo / w) < 8) || 50000;
    const start = Math.floor(lo / step) * step;
    const bins = Array.from({ length: Math.floor(hi / step) - Math.floor(lo / step) + 1 }, (_, k) => ({ from: start + k * step, n: 0 }));
    prices.forEach((p) => { bins[Math.floor((p - start) / step)].n++; });
    const top = bins.reduce((a, b) => (b.n > a.n ? b : a));
    const pct = (b) => Math.round(b.n / prices.length * 100);
    box.innerHTML = `<h3>目前在架價格區間（${esc(first.label)}）</h3>` +
      `<p class="dist-top">最多集中在 ${money(top.from)}–${money(top.from + step - 1)}，約占 ${pct(top)}%。</p>` +
      `<div class="dist-bars">` + bins.map((b) =>
        `<div class="dist-bar" title="${money(b.from)}–${money(b.from + step - 1)}：${pct(b)}%">` +
        `<span class="dist-pct">${b.n ? pct(b) + "%" : ""}</span>` +
        `<span class="dist-fill ${first.cls}" style="height:${Math.max(b.n ? 4 : 0, pct(b) / pct(top) * 80)}px"></span>` +
        `<span class="dist-label">${money(b.from)}</span></div>`).join("") + "</div>";
  }

  // ---------- 價格散布圖 ----------
  function renderChart() {
    const pts = selected().filter((r) => r.price && /^\d{4}-\d{2}-\d{2}/.test(r.post_time));
    if (!pts.length) { $("#chart").innerHTML = '<p class="empty">沒有可畫的標價</p>'; return; }
    const W = 900, H = 240, L = 64, R = 16, T = 12, B = 26;
    const t = (r) => Date.parse(r.post_time.slice(0, 10) + "T00:00:00Z") + Number(r.post_time.slice(11, 13) || 0) * 3600e3;
    let x0 = Math.min(...pts.map(t)), x1 = Math.max(...pts.map(t));
    if (x1 - x0 < 2 * 86400e3) { x0 -= 86400e3; x1 += 86400e3; }
    let y0 = Math.min(...pts.map((r) => r.price)), y1 = Math.max(...pts.map((r) => r.price));
    const pad = Math.max(500, (y1 - y0) * 0.08);
    y0 = Math.max(0, y0 - pad); y1 += pad;
    const x = (v) => L + (W - L - R) * (v - x0) / (x1 - x0);
    const y = (v) => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(model)} 各文章標價分布">`;
    for (let i = 0; i <= 4; i++) {
      const v = y0 + (y1 - y0) * i / 4;
      s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      s += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${money(Math.round(v / 100) * 100)}</text>`;
    }
    for (let i = 0; i <= 5; i++) {
      const v = x0 + (x1 - x0) * i / 5;
      s += `<text class="axis" x="${x(v)}" y="${H - 8}" text-anchor="${i === 0 ? "start" : i === 5 ? "end" : "middle"}">${new Date(v).toISOString().slice(5, 10)}</text>`;
    }
    const m = statsFor(storage);
    if (m && m.median_price) {
      s += `<line class="median" x1="${L}" x2="${W - R}" y1="${y(m.median_price)}" y2="${y(m.median_price)}"><title>刊登中位數 ${money(m.median_price)}</title></line>`;
    }
    // 已售出畫在最上層，比較容易看到成交價落點
    const order = { "已刪除": 0, "在售": 1, "交易中": 2, "已售出": 3 };
    pts.slice().sort((a, b) => order[a.status] - order[b.status]).forEach((r) => {
      s += `<a href="${esc(r.url)}" target="_blank" rel="noopener"><circle class="pt st-${esc(r.status)}" cx="${x(t(r))}" cy="${y(r.price)}" r="5">` +
        `<title>${esc(r.post_time.slice(0, 16))} · ${esc(storageLabel(r.storage))} · ${money(r.price)} · ${esc(r.status)}</title></circle></a>`;
    });
    $("#chart").innerHTML = s + "</svg>";
  }

  // ---------- 各容量比較 ----------
  const COLS = [
    ["storage", "容量"], ["listed", "刊登", 1], ["active", "在架", 1], ["sold", "已售", 1],
    ["median_price", "刊登中位數", 1], ["median_sold_price", "成交中位數", 1], ["min_price", "最低", 1],
    ["max_price", "最高", 1], ["median_days", "售出天數", 1],
  ];

  function renderCompare() {
    const rows = storages.map((s) => statsFor(s) || { storage: s, listed: selectedCount(s) });
    $("#compare-card").hidden = storages.length < 2;
    const fmt = (k, v, m) => {
      if (v == null) return "—";
      if (/price/.test(k)) return money(v);
      return v;
    };
    $("#compare").innerHTML = "<thead><tr>" + COLS.map(([, label, num]) =>
      `<th class="${num ? "num" : ""}">${label}</th>`).join("") + "</tr></thead><tbody>" +
      rows.map((m) => `<tr class="${m.storage === storage ? "current" : ""}">` + COLS.map(([k, , num]) => k === "storage"
        ? `<td><button type="button" class="linkish" data-storage="${esc(m.storage)}">${esc(storageLabel(m.storage))}</button></td>`
        : `<td${num ? ' class="num"' : ""}>${(k === "median_days" ? daysCell(m) : esc(fmt(k, m[k], m)))}</td>`).join("") + "</tr>").join("") + "</tbody>";
  }

  function renderColors() {
    const rows = (D.colors || []).filter((r) => r.model === model && r.storage === storage)
      .sort((a, b) => (a.relative == null) - (b.relative == null) ||
        (a.relative - b.relative) || a.color.localeCompare(b.color, "zh-Hant"));
    $("#color-card").hidden = !mine.some((r) => r.color);
    const comparable = rows.filter((r) => r.relative != null);
    const best = comparable[0];
    $("#color-best").hidden = comparable.length < 2;
    if (best) {
      const pct = Math.round(Math.abs(best.relative) * 100);
      const diff = pct === 0 ? "與中位數相同" : "比中位數" + (best.relative < 0 ? "低 " : "高 ") + pct + "%";
      const tied = comparable.filter((r) => r.relative === best.relative);
      $("#color-best").textContent = tied.length === comparable.length
        ? "目前各顏色的刊登價沒有明顯差異（" + tied.map((r) => r.color).join("、") + "）。"
        : tied.length > 1
        ? "目前刊登價比較：" + tied.map((r) => r.color).join("、") + "的校正後相對值並列最低（" + diff + "）。"
        : "目前刊登價最低的顏色：" + best.color + "（" + diff + "，" + best.samples + " 篇）";
    }
    // 全部容量混了不同容量，價格中位數會被大容量拉高，只留相對值
    const showPrice = storage !== null;
    const columns = ["顏色", "刊登", "已售"].concat(showPrice ? ["二手刊登價中位數"] : [], ["相對同型號同容量"]);
    const cell = (text, index, cls = "") => `<td data-label="${columns[index]}" class="${index ? "num " : ""}${cls}">${text}</td>`;
    $("#color-table").innerHTML = "<thead><tr>" + columns.map((c, i) =>
      `<th scope="col" class="${i ? "num" : ""}">${c}</th>`).join("") + "</tr></thead><tbody>" + rows.map((r) => {
      const pct = Math.round(Math.abs(r.relative || 0) * 100);
      const relative = r.relative == null ? "樣本不足" : (r.relative < 0 ? "−" : r.relative > 0 ? "+" : "") + pct + "%";
      const tone = r.relative == null ? "muted" : r.relative < 0 ? "relative-low" : r.relative > 0 ? "relative-high" : "";
      return "<tr>" + cell(esc(r.color), 0) + cell(r.listed, 1) + cell(r.sold, 2) +
        (showPrice ? cell(r.median_price == null ? "樣本不足" : money(r.median_price), 3) : "") +
        cell(relative, columns.length - 1, tone) + "</tr>";
    }).join("") + (rows.length ? "" : `<tr><td colspan="${columns.length}" class="empty">這個容量尚無可比較的顏色價格資料</td></tr>`) + "</tbody>";
    const missing = selected().filter((r) => !r.color).length;
    $("#color-note").textContent = "顏色由標題與規格欄判斷，未標示顏色的 " + missing +
      " 篇不列入；每個顏色至少 3 篇才顯示數字。價格欄只算二手機；相對值是和同型號、同容量、同為全新或二手的刊登價中位數比較，全新機不會拉高某個顏色。異常價格不列入。";
  }

  function selectedCount(s) {
    return mine.filter((r) => r.storage === s).length;
  }

  // ---------- 文章 ----------
  function renderList() {
    const status = $("#status-f").value;
    const sort = $("#sort-f").value;
    const rows = selected().filter((r) => !status || r.status === status);
    if (sort !== "time") {
      const dir = sort === "price-asc" ? 1 : -1;
      rows.sort((a, b) => (a.price == null) - (b.price == null) || dir * (a.price - b.price));
    }
    $("#list-title").textContent = (storage === null ? "全部容量" : storageLabel(storage)) + "的文章（" + rows.length + "）";
    $("#list").innerHTML = rows.length
      ? `<div class="items">${rows.slice(0, listLimit).map((r) => itemHtml(r, r.status === "已售出" ? soldNote(r) : "")).join("")}</div>`
      : '<p class="empty">沒有符合的文章</p>';
    PttCommon.setMore($("#more"), rows.length - listLimit);
  }

  function renderEvents() {
    const byUrl = {};
    selected().forEach((r) => { byUrl[r.url] = r; });
    const events = D.events.filter((e) => e.event === "價格變動" && byUrl[e.url]).slice(0, EVENT_LIMIT);
    $("#events").innerHTML = events.length
      ? `<div class="items">${events.map((e) => {
        const { what, explanation } = priceEventText(e);
        return itemHtml(byUrl[e.url], dayOf(e.time).slice(5) + " " + e.time.slice(11, 16) + " " + what, explanation);
      }).join("")}</div>`
      : '<p class="empty">最近沒有改價紀錄</p>';
  }

  // ---------- 收藏（與首頁共用同一份收藏） ----------
  function watchFilter() {
    return { model, storage, status: "", q: "" };
  }

  function renderWatch() {
    const saved = watchlist.has(watchFilter());
    const label = model + " " + (storage === null ? "全部容量" : storageLabel(storage));
    const b = $("#watch-model");
    b.textContent = saved ? "★" : "☆";
    b.title = saved ? "取消收藏" : "收藏";
    b.setAttribute("aria-pressed", String(saved));
    b.setAttribute("aria-label", (saved ? "取消收藏 " : "收藏 ") + label);
  }

  function toggleWatch() {
    const f = watchFilter();
    let message;
    if (watchlist.has(f)) {
      watchlist.remove(PttWatchlist.key(f));
      message = watchlist.mode() === "memory" ? "已從本頁暫存移除；瀏覽器無法儲存變更。" : "已移除收藏。";
    } else {
      const result = watchlist.add(f);
      message = {
        added: watchlist.mode() === "memory" ? "已加入本頁暫存收藏；瀏覽器無法永久儲存。" : "已收藏，只儲存在這個瀏覽器。",
        duplicate: "這組條件已收藏，不會重複加入。",
        full: "最多可收藏 " + PttWatchlist.MAX_ITEMS + " 組條件；請先到首頁移除不需要的項目。",
      }[result] || "這組條件無法收藏。";
    }
    renderWatch();
    clearTimeout(watchFeedbackTimer);
    $("#watch-feedback").textContent = message;
    watchFeedbackTimer = setTimeout(() => { $("#watch-feedback").textContent = ""; }, 7000);
  }
})();
