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
    const tags = [r.storage, r.brand_new ? "全新未拆" : "", r.battery ? "電池 " + r.battery + "%" : "", r.warranty]
      .filter(Boolean).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
    return `<div class="item">
      <div><a class="name" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.model || r.title || "（未解析）")}</a> ${pm}${tags}</div>
      <div class="price">${money(r.price)}</div>
      <div class="meta"${extraTitle ? ` title="${esc(extraTitle)}"` : ""}>${esc(extra || r.notes || "")}</div>
      <div class="meta side"><span class="st-${esc(r.status)}">${esc(r.status)}</span> · ${esc((r.post_time || "").slice(5, 16))}</div>
    </div>`;
  }

  function soldNote(r) {
    if (r.days_to_sell == null) return "已售出，售出時間無法推估（依偵測日 " + dayOf(r.sold_detected_at) + " 計）";
    return "上架 " + r.days_to_sell + " 天後售出" + (r.days_basis === "推估" ? "（推估，依最後編輯時間）" : "");
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

  return { esc, money, dayOf, modelUrl, storageSize, compareStorage, itemHtml, soldNote, priceEventText, setMore };
});
