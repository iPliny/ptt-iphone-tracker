// 首頁與機型頁共用的小工具；同時可在 Node 測試中載入。
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PttCommon = api;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => (n == null || n === "" ? "—" : "$" + Number(n).toLocaleString("zh-TW"));
  const dayOf = (ts) => (ts || "").slice(0, 10);

  // days 由建置端提供升冪、連續的日期；索引運算不受瀏覽器時區影響。
  function periodRange(days, endDate, n = 7) {
    const end = days.findIndex((d) => d.date === endDate);
    if (end < 0 || !Number.isInteger(n) || n < 1) return null;
    const start = Math.max(0, end - n + 1);
    return { start, end, startDate: days[start].date, endDate: days[end].date, count: end - start + 1 };
  }

  function sumPeriod(days, start, end) {
    const total = { new: 0, sold: 0, deleted: 0, price_changes: 0, on_shelf: 0 };
    if (start < 0 || end < start || end >= days.length) return total;
    for (let i = start; i <= end; i++) {
      for (const key of ["new", "sold", "deleted", "price_changes"]) total[key] += days[i][key];
    }
    total.on_shelf = days[end].on_shelf;
    return total;
  }

  function previousPeriod(days, range, n = 7) {
    if (!range || range.start < n) return null; // 不拿不足 n 天的前期來比較。
    return periodRange(days, days[range.start - 1].date, n);
  }

  function periodNavigation(days, endDate, n = 7) {
    const range = periodRange(days, endDate, n);
    if (!range) return { previous: null, next: null };
    return {
      previous: range.end >= n ? days[range.end - n].date : null,
      next: range.end < days.length - 1 ? days[Math.min(range.end + n, days.length - 1)].date : null,
    };
  }

  function periodTitle(range) {
    if (!range) return "當週動態";
    const sameYear = range.startDate.slice(0, 4) === range.endDate.slice(0, 4);
    const fmt = (date) => sameYear ? date.slice(5) : date;
    return `${fmt(range.startDate)}～${fmt(range.endDate)} 動態（${range.count} 天）`;
  }

  function inPeriod(ts, range) {
    const date = dayOf(ts);
    return !!range && date >= range.startDate && date <= range.endDate;
  }

  // 只使用已經過建置端異常價格排除的公開資料，不從其他來源補回事件。
  function periodItems(data, tab, range) {
    let rows, field;
    if (tab === "new" || tab === "sold") {
      field = tab === "new" ? "post_time" : "sold_at";
      rows = data.listings.filter((r) => inPeriod(r[field], range) && (tab === "new" || r.status === "已售出"));
    } else if (tab === "price" || tab === "deleted") {
      field = "time";
      rows = data.events.filter((e) => inPeriod(e.time, range) &&
        (tab === "price" ? e.event === "價格變動" : /已刪除$/.test(e.detail)));
    } else return [];
    return rows.sort((a, b) => b[field].localeCompare(a[field]));
  }

  // 機型頁網址：同一機型共用一頁，容量只是頁內分頁。
  function modelUrl(model, storage) {
    const p = new URLSearchParams({ m: model });
    if (storage != null && storage !== "") p.set("s", storage);
    return "model.html?" + p.toString();
  }

  // 容量依實際大小排序（64GB < 128GB < … < 1TB < 2TB），無法辨識的放最後。
  function storageSize(s) {
    const m = /^(\d+(?:\.\d+)?)\s*(GB|TB)$/i.exec(String(s || "").trim());
    if (!m) return Infinity;
    return Number(m[1]) * (m[2].toUpperCase() === "TB" ? 1024 : 1);
  }

  function compareStorage(a, b) {
    const x = storageSize(a), y = storageSize(b);
    if (x !== y) return x === Infinity ? 1 : y === Infinity ? -1 : x - y;
    return String(a || "").localeCompare(String(b || ""), "zh-Hant");
  }

  function itemHtml(r, extra, extraTitle = "") {
    const pm = (r.status === "在售" || r.status === "交易中") && r.pm_count >= 1
      ? `<span class="chip pm" title="${esc(r.pm_count)} 位網友推文表示已私訊">私${esc(r.pm_count)}</span>` : "";
    const tags = [r.storage, r.color, r.brand_new ? "全新未拆" : "", r.battery ? "電池 " + r.battery + "%" : "", r.warranty]
      .filter(Boolean).map((t) => `<span class="chip${r.color && t === r.color ? " color-chip" : ""}">${esc(t)}</span>`).join("");
    return `<div class="item">
      <div><a class="name" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.model || r.title || "（未解析）")}</a> ${pm}${tags}</div>
      <div class="price">${money(r.price)}</div>
      <div class="meta"${extraTitle ? ` title="${esc(extraTitle)}"` : ""}>${esc(extra || r.notes || "")}</div>
      <div class="meta side"><span class="st-${esc(r.status)}">${esc(r.status)}</span> · ${esc((r.post_time || "").slice(5, 16))}</div>
    </div>`;
  }

  function soldNote(r) {
    if (r.days_to_sell == null) return "已售出，售出時間無法推估（依偵測日 " + dayOf(r.sold_detected_at) + " 計）";
    return "上架 " + r.days_to_sell + " 天後售出" + (r.days_basis === "推估" ? "（推估）" : "");
  }

  // 表格的售出天數欄：有推估樣本只標「（推估）」，不列筆數；沒推估的列放同寬的隱形標記，讓數字對齊。
  function daysCell(m) {
    const est = m.median_days != null && m.days_estimated;
    return (m.median_days == null ? "—" : esc(m.median_days)) +
      `<span class="est"${est ? "" : ' aria-hidden="true" style="visibility:hidden"'}>（推估）</span>`;
  }

  // 改價事件的顯示文字與滑鼠提示；時間語意見 AGENTS.md「改價時間」。
  function priceEventText(e) {
    const estimated = e.time_basis === "ptt_edit";
    const what = (estimated ? "改價 " : "發現改價 ") + e.detail.replace(/(\d+)/g, (n) => money(n));
    const explanation = estimated ?
      `${e.time}（台灣時間），依當次 PTT 最新編輯時間推估；系統發現時間：${e.detected_at}` :
      `系統發現時間：${e.detected_at || e.time}；沒有可用的當次編輯時間`;
    return { what, explanation };
  }

  function setMore(btn, rest) {
    btn.hidden = rest <= 0;
    btn.textContent = "顯示更多（還有 " + rest + " 篇）";
  }

  return { esc, money, dayOf, periodRange, sumPeriod, previousPeriod, periodNavigation, periodTitle, inPeriod, periodItems,
    modelUrl, storageSize, compareStorage, itemHtml, soldNote, daysCell, priceEventText, setMore };
});
