// PTT每日交易觀測：讀取 build_site.py 產生的 data.json 並繪製頁面，不依賴任何外部套件。
(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => (n == null || n === "" ? "—" : "$" + Number(n).toLocaleString("zh-TW"));
  const dayOf = (ts) => (ts || "").slice(0, 10);
  const PAGE = 10;

  let D = null;
  let byUrl = {};
  let dayIdx = {};
  let current = "";
  let tab = "new";
  let listLimit = PAGE;
  let dayLimit = PAGE;
  let showAllModels = false;
  let modelSort = { key: "listed", asc: false };
  const watchlist = PttWatchlist.createStore(() => window.localStorage);
  let watchScope = { model: null, storage: null };
  let watchFeedbackTimer;

  // 收藏的讀取與移除不依賴市場資料成功載入。
  renderWatchlist();
  $("#watch-list").addEventListener("click", (e) => {
    const button = e.target.closest("button[data-watch-action]");
    if (!button) return;
    const savedKey = button.dataset.watchKey;
    const f = watchlist.list().find((item) => PttWatchlist.key(item) === savedKey);
    if (!f) return;
    if (button.dataset.watchAction === "remove") {
      watchlist.remove(savedKey);
      updateWatchUi();
      announceWatchRemoval();
      const nextButton = $("#watch-list button[data-watch-action='remove']");
      (nextButton || $(".watch-shortcut")).focus();
    } else if (D) {
      watchScope = { model: f.model, storage: f.storage };
      $("#status-f").value = f.status;
      $("#list-q").value = f.q;
      listLimit = PAGE;
      renderAll();
      $("#listings-title").focus();
      $("#listings-section").scrollIntoView({ block: "start" });
    }
  });
  window.addEventListener("storage", (e) => {
    if (e.key !== null && e.key !== PttWatchlist.STORAGE_KEY) return;
    // sessionStorage 的同名事件不應改動 localStorage 收藏。
    try { if (e.storageArea !== window.localStorage) return; } catch (_) { return; }
    watchlist.reload();
    updateWatchUi();
  });

  fetch("data.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch((e) => { $("#updated").textContent = "資料載入失敗（" + e.message + "）"; });

  function init(data) {
    D = data;
    D.listings.forEach((r) => { byUrl[r.url] = r; });
    D.days.forEach((d, i) => { dayIdx[d.date] = i; });
    $("#updated").textContent = "最後回訪 " + (D.last_checked || "—") + " · 共追蹤 " + D.counts.total + " 篇";

    const days = D.days.map((d) => d.date);
    if (days.length) {
      $("#day").min = days[0];
      $("#day").max = days[days.length - 1];
    }
    $("#day").addEventListener("change", (e) => select(e.target.value));
    $("#prev-day").addEventListener("click", () => step(-1));
    $("#next-day").addEventListener("click", () => step(1));
    $("#latest-day").addEventListener("click", () => select(days[days.length - 1]));
    document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
      tab = b.dataset.tab;
      document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
      dayLimit = PAGE;
      renderDayList();
    }));
    $("#model-q").addEventListener("input", renderModels);
    $("#status-f").addEventListener("change", () => { listLimit = PAGE; renderAll(); });
    $("#list-q").addEventListener("input", () => { listLimit = PAGE; renderAll(); });
    $("#more").addEventListener("click", () => { listLimit += PAGE; renderAll(); });
    $("#day-more").addEventListener("click", () => { dayLimit += PAGE; renderDayList(); });
    $("#models-more").addEventListener("click", () => { showAllModels = !showAllModels; renderModels(); });
    $("#save-filter").addEventListener("click", () => saveWatch(currentFilters()));
    $("#clear-watch-scope").addEventListener("click", () => {
      watchScope = { model: null, storage: null };
      listLimit = PAGE;
      renderAll();
      $("#list-q").focus();
    });
    $("#models").addEventListener("click", (e) => {
      const button = e.target.closest("button[data-watch-model]");
      if (!button) return;
      const f = { model: button.dataset.watchModel, storage: button.dataset.watchStorage, status: "", q: "" };
      if (watchlist.has(f)) {
        watchlist.remove(PttWatchlist.key(f));
        updateWatchUi();
        announceWatchRemoval();
      } else saveWatch(f);
      // 更新表格後，把鍵盤焦點留在同一個收藏按鈕。
      const next = Array.from($("#models").querySelectorAll("button[data-watch-model]")).find((b) =>
        b.dataset.watchModel === f.model && b.dataset.watchStorage === f.storage);
      if (next) next.focus({ preventScroll: true });
    });

    renderWatchlist();
    renderModels();
    renderAll();
    select(days.length ? days[days.length - 1] : "");
  }

  function step(delta) {
    const i = dayIdx[current];
    const next = D.days[(i == null ? D.days.length : i) + delta];
    if (next) select(next.date);
  }

  function select(date) {
    current = date;
    dayLimit = PAGE;
    $("#day").value = date;
    const i = dayIdx[date];
    $("#prev-day").disabled = !(i > 0);
    $("#next-day").disabled = i == null || i >= D.days.length - 1;
    renderKpis();
    renderChart();
    renderDayList();
  }

  // ---------- 當日指標 ----------
  function renderKpis() {
    const i = dayIdx[current];
    const d = i == null ? { new: 0, sold: 0, deleted: 0, price_changes: 0, on_shelf: 0 } : D.days[i];
    const p = i > 0 ? D.days[i - 1] : null;
    const diff = (k) => {
      if (!p) return "";
      const v = d[k] - p[k];
      return v === 0 ? "與前一天持平" : "比前一天 " + (v > 0 ? "+" : "") + v;
    };
    const cards = [
      ["新刊登", d.new, diff("new")],
      ["售出", d.sold, diff("sold")],
      ["刪文", d.deleted, diff("deleted")],
      ["改價", d.price_changes, diff("price_changes")],
      ["日終在架", d.on_shelf, diff("on_shelf")],
    ];
    $("#kpis").innerHTML = cards.map(([label, v, note]) =>
      `<div class="kpi"><div class="label">${label}</div><div class="value">${v}</div><div class="note">${esc(note) || "&nbsp;"}</div></div>`
    ).join("");
  }

  // ---------- 近 30 天圖 ----------
  function renderChart() {
    const days = D.days.slice(-30);
    if (!days.length) { $("#chart").innerHTML = '<p class="empty">還沒有資料</p>'; return; }
    const W = 900, H = 220, L = 34, R = 34, T = 10, B = 26;
    const cw = (W - L - R) / days.length;
    const maxBar = Math.max(1, ...days.map((d) => Math.max(d.new, d.sold)));
    const maxShelf = Math.max(1, ...days.map((d) => d.on_shelf));
    const y = (v) => T + (H - T - B) * (1 - v / maxBar);
    const ys = (v) => T + (H - T - B) * (1 - v / maxShelf);
    const bw = Math.max(2, Math.min(14, cw / 2 - 2));
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="近 30 天新刊登與售出">`;
    [0, 0.5, 1].forEach((f) => {
      const v = Math.round(maxBar * f);
      s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      s += `<text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
      s += `<text class="axis" x="${W - R + 6}" y="${ys(maxShelf * f) + 4}">${Math.round(maxShelf * f)}</text>`;
    });
    let path = "";
    days.forEach((d, i) => {
      const x = L + i * cw;
      const cx = x + cw / 2;
      s += `<rect class="hit${d.date === current ? " sel" : ""}" data-date="${d.date}" x="${x}" y="${T}" width="${cw}" height="${H - T - B}"><title>${d.date}：新刊登 ${d.new}、售出 ${d.sold}、在架 ${d.on_shelf}</title></rect>`;
      s += `<rect class="bar-new" pointer-events="none" x="${cx - bw - 1}" y="${y(d.new)}" width="${bw}" height="${y(0) - y(d.new)}"/>`;
      s += `<rect class="bar-sold" pointer-events="none" x="${cx + 1}" y="${y(d.sold)}" width="${bw}" height="${y(0) - y(d.sold)}"/>`;
      path += (i ? "L" : "M") + cx + "," + ys(d.on_shelf);
      if (i % Math.ceil(days.length / 8) === 0 || i === days.length - 1) {
        s += `<text class="axis" x="${cx}" y="${H - 8}" text-anchor="middle">${d.date.slice(5)}</text>`;
      }
    });
    s += `<path class="shelf" pointer-events="none" d="${path}"/></svg>`;
    $("#chart").innerHTML = s;
    $("#chart").querySelectorAll(".hit").forEach((r) => r.addEventListener("click", () => select(r.dataset.date)));
  }

  // ---------- 當日清單 ----------
  function itemHtml(r, extra, extraTitle = "") {
    const pm = (r.status === "在售" || r.status === "交易中") && r.pm_count >= 1
      ? `<span class="chip pm" title="${esc(r.pm_count)} 位網友推文表示已私訊">私${esc(r.pm_count)}</span>` : "";
    const tags = [r.storage, r.brand_new ? "全新未拆" : "", r.battery ? "電池 " + r.battery + "%" : "", r.warranty]
      .filter(Boolean).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
    return `<div class="item">
      <div><a class="name" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.model || r.title || "（未解析）")}</a> ${pm}${tags}</div>
      <div class="price">${money(r.price)}</div>
      <div class="meta"${extraTitle ? ` title="${esc(extraTitle)}"` : ""}>${esc(extra || r.notes || "")}</div>
      <div class="meta side"><span class="st-${esc(r.status)}">${esc(r.status)}</span> · ${esc(r.post_time.slice(5, 16))}</div>
    </div>`;
  }

  function renderDayList() {
    const date = current;
    $("#day-title").textContent = date ? date + " 動態" : "當日動態";
    let items = [];  // 每項是一個回傳 HTML 的函式，只畫出要顯示的那幾篇
    if (tab === "new") {
      items = D.listings.filter((r) => dayOf(r.post_time) === date).map((r) => () => itemHtml(r));
    } else if (tab === "sold") {
      items = D.listings.filter((r) => r.status === "已售出" && dayOf(r.sold_at) === date)
        .map((r) => () => itemHtml(r, soldNote(r)));
    } else if (tab === "price" || tab === "deleted") {
      items = D.events.filter((e) => dayOf(e.time) === date &&
        (tab === "price" ? e.event === "價格變動" : /已刪除$/.test(e.detail)))
        .map((e) => () => {
          const r = byUrl[e.url] || { url: e.url, post_time: "", status: "", title: e.url };
          const estimated = e.time_basis === "ptt_edit";
          const what = tab === "price" ? (estimated ? "改價 " : "發現改價 ") +
            e.detail.replace(/(\d+)/g, (n) => money(n)) : "刪文";
          const explanation = tab === "price" ? (estimated ?
            `${e.time}（台灣時間），依當次 PTT 最新編輯時間推估；系統發現時間：${e.detected_at}` :
            `系統發現時間：${e.detected_at || e.time}；沒有可用的當次編輯時間`) : "";
          return itemHtml(r, e.time.slice(11, 16) + " " + what, explanation);
        });
    }
    $("#day-list").innerHTML = items.length
      ? `<div class="items">${items.slice(0, dayLimit).map((f) => f()).join("")}</div>`
      : '<p class="empty">這天沒有紀錄</p>';
    setMore("#day-more", items.length - dayLimit);
  }

  function soldNote(r) {
    if (r.days_to_sell == null) return "已售出，售出時間無法推估（依偵測日 " + dayOf(r.sold_detected_at) + " 計）";
    return "上架 " + r.days_to_sell + " 天後售出" + (r.days_basis === "推估" ? "（推估，依最後編輯時間）" : "");
  }

  // ---------- 型號行情 ----------
  const MODEL_COLS = [
    ["model", "型號"], ["storage", "容量"], ["listed", "刊登", 1], ["active", "在架", 1], ["sold", "已售", 1],
    ["median_price", "刊登中位數", 1], ["median_sold_price", "成交中位數", 1], ["min_price", "最低", 1],
    ["max_price", "最高", 1], ["median_days", "售出天數", 1],
  ];

  function renderModels() {
    const q = $("#model-q").value.trim().toLowerCase();
    const matched = D.models.filter((m) => !q || (m.model + " " + m.storage).toLowerCase().includes(q));
    // 只有 1 篇刊登的型號參考價值低，預設收起來；搜尋時照樣列出
    const hidden = q ? 0 : matched.filter((m) => m.listed <= 1).length;
    const rows = showAllModels || q ? matched : matched.filter((m) => m.listed > 1);
    const { key, asc } = modelSort;
    rows.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === "number" ? x - y : String(x).localeCompare(String(y), "zh-Hant", { numeric: true });
      return asc ? c : -c;
    });
    const fmt = (k, v, m) => {
      if (v == null) return "—";
      if (/price/.test(k)) return money(v);
      if (k === "median_days" && m.days_estimated) {
        return v + (m.days_estimated === m.days_samples ? "（推估）" : "（" + m.days_estimated + "/" + m.days_samples + " 推估）");
      }
      return v;
    };
    const head = '<tr><th class="watch-column">收藏</th>' + MODEL_COLS.map(([k, label, num]) =>
      `<th data-k="${k}" class="${num ? "num " : ""}${k === key ? "sorted" + (asc ? " asc" : "") : ""}">${label}</th>`).join("") + "</tr>";
    const body = rows.map((m) => {
      const saved = watchlist.has({ model: m.model, storage: m.storage });
      return `<tr><td class="watch-column"><button type="button" class="ghost watch-model" data-watch-model="${esc(m.model)}" data-watch-storage="${esc(m.storage)}" aria-label="${saved ? "取消收藏" : "收藏"} ${esc(m.model)} ${esc(m.storage || "容量未提供")}" aria-pressed="${saved}">${saved ? "★ 已收藏" : "☆ 收藏"}</button></td>` + MODEL_COLS.map(([k, , num]) =>
        `<td${num ? ' class="num"' : ""}>${esc(fmt(k, m[k], m))}</td>`).join("") + "</tr>";
    }).join("");
    $("#models").innerHTML = "<thead>" + head + "</thead><tbody>" +
      (body || `<tr><td colspan="${MODEL_COLS.length + 1}" class="empty">沒有符合的型號</td></tr>`) + "</tbody>";
    $("#models").querySelectorAll("th[data-k]").forEach((th) => th.addEventListener("click", () => {
      const k = th.dataset.k;
      modelSort = { key: k, asc: modelSort.key === k ? !modelSort.asc : k === "model" || k === "storage" };
      renderModels();
    }));
    const btn = $("#models-more");
    btn.hidden = hidden === 0;
    btn.textContent = showAllModels ? "收起只有 1 篇刊登的型號" : "顯示更多（另有 " + hidden + " 個只有 1 篇刊登的型號）";
  }

  // ---------- 全部文章 ----------
  function renderAll() {
    const rows = matchingListings(currentFilters());
    $("#all-list").innerHTML = rows.length
      ? `<div class="items">${rows.slice(0, listLimit).map((r) => itemHtml(r)).join("")}</div>`
      : '<p class="empty">沒有符合的文章</p>';
    setMore("#more", rows.length - listLimit);
    renderFilterState();
  }

  // ---------- 免登入收藏：保存條件，使用本次載入的資料 ----------
  function currentFilters() {
    return PttWatchlist.normalize({ ...watchScope, status: $("#status-f").value, q: $("#list-q").value });
  }

  function matchingListings(f) {
    if (!D || !f) return [];
    return D.listings.filter((r) =>
      (f.model === null || r.model === f.model) &&
      (f.storage === null || r.storage === f.storage) &&
      (!f.status || r.status === f.status) &&
      (!f.q || [r.model, r.storage, r.notes, r.title].join(" ").toLowerCase().includes(f.q.toLowerCase())));
  }

  function watchLabel(f) {
    return [f.model === null ? "" : f.model || "型號未提供",
      f.storage === null ? "" : f.storage || "容量未提供",
      f.status, f.q ? "搜尋「" + f.q + "」" : ""].filter(Boolean).join(" · ");
  }

  function renderWatchlist() {
    const saved = watchlist.list();
    $("#watch-count").textContent = saved.length;
    $("#watch-notice").hidden = !watchlist.notice();
    $("#watch-notice").textContent = watchlist.notice();
    $("#watch-list").innerHTML = saved.length ? saved.map((f) => {
      const label = watchLabel(f);
      const count = D ? matchingListings(f).length : null;
      const detail = count === null ? "市場資料尚未載入，仍可移除收藏" :
        count ? "本次載入資料符合 " + count + " 篇" : "本次載入資料沒有符合的文章，收藏仍保留";
      const savedKey = esc(PttWatchlist.key(f));
      return `<div class="watch-entry"><div><strong>${esc(label)}</strong><p class="hint">${esc(detail)}</p></div><div class="watch-actions"><button type="button" data-watch-action="view" data-watch-key="${savedKey}" aria-label="查看 ${esc(label)}"${D ? "" : " disabled"}>查看</button><button type="button" class="ghost" data-watch-action="remove" data-watch-key="${savedKey}" aria-label="移除 ${esc(label)}">移除</button></div></div>`;
    }).join("") : '<p class="empty">尚無收藏。可在型號行情按「收藏」，或篩選文章後收藏目前條件。</p>';
  }

  function renderFilterState() {
    const f = currentFilters();
    const scoped = watchScope.model !== null || watchScope.storage !== null;
    $("#watch-scope").hidden = !scoped;
    $("#watch-scope").textContent = scoped ? "限定：" + watchLabel({ ...watchScope, status: "", q: "" }) : "";
    $("#clear-watch-scope").hidden = !scoped;
    $("#save-filter").disabled = !f || (!scoped && !f.status && !f.q);
    $("#save-filter").textContent = watchlist.has(f) ? "✓ 目前條件已收藏" : "收藏目前條件";
  }

  function updateWatchUi() {
    renderWatchlist();
    if (D) { renderModels(); renderFilterState(); }
  }

  function saveWatch(f) {
    const result = watchlist.add(f);
    updateWatchUi();
    const messages = {
      added: watchlist.mode() === "memory" ? "已加入本頁暫存收藏；瀏覽器無法永久儲存。" : "已收藏，只儲存在這個瀏覽器。",
      duplicate: "這組條件已收藏，不會重複加入。",
      empty: "請先選擇型號、文章狀態或輸入搜尋條件。",
      invalid: "這組條件無法收藏，請調整後再試。",
      full: "最多可收藏 " + PttWatchlist.MAX_ITEMS + " 組條件；請先移除不需要的項目。",
    };
    announceWatch(messages[result]);
  }

  function announceWatchRemoval() {
    announceWatch(watchlist.mode() === "memory" ? "已從本頁暫存移除；瀏覽器無法儲存變更。" : "已移除收藏。");
  }

  function announceWatch(message) {
    clearTimeout(watchFeedbackTimer);
    $("#watch-feedback").textContent = message;
    watchFeedbackTimer = setTimeout(() => { $("#watch-feedback").textContent = ""; }, 7000);
  }

  function setMore(sel, rest) {
    const btn = $(sel);
    btn.hidden = rest <= 0;
    btn.textContent = "顯示更多（還有 " + rest + " 篇）";
  }
})();
