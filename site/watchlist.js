// 只保存查價條件；價格與篇數永遠由本次載入的 data.json 計算。
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PttWatchlist = api;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";
  const STORAGE_KEY = "ptt-iphone-tracker:watchlist:v1";
  const MAX_ITEMS = 30;
  const STATUSES = ["", "在售", "交易中", "已售出", "已刪除"];

  function normalize(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const out = {};
    for (const [field, max] of [["model", 120], ["storage", 32]]) {
      const value = raw[field] === undefined ? null : raw[field];
      if (value !== null && (typeof value !== "string" || value.length > max)) return null;
      // null = 不限；空字串 = 原資料未提供，兩者不可合併。
      out[field] = value === null ? null : value.trim();
    }
    const status = raw.status === undefined ? "" : raw.status;
    const q = raw.q === undefined ? "" : raw.q;
    if (typeof status !== "string" || !STATUSES.includes(status.trim()) || typeof q !== "string" || q.length > 200) return null;
    out.status = status.trim();
    out.q = q.trim().replace(/\s+/g, " ");
    return out;
  }

  function key(raw) {
    const f = normalize(raw);
    return f ? JSON.stringify([f.model, f.storage, f.status, f.q.toLowerCase()]) : "";
  }

  function empty(f) {
    return f.model === null && f.storage === null && !f.status && !f.q;
  }

  function createStore(storageProvider) {
    let items = [];
    let memoryOnly = false;
    let notice = "";
    const unavailable = () => {
      memoryOnly = true;
      notice = "瀏覽器無法儲存收藏，目前僅暫存於此頁；重新整理或關閉後可能消失。";
    };
    function reload() {
      if (memoryOnly) return;
      let stored;
      try { stored = storageProvider().getItem(STORAGE_KEY); }
      catch (_) { unavailable(); return; }
      if (stored === null) { items = []; notice = ""; return; }
      try {
        const parsed = JSON.parse(stored);
        if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.items)) throw new Error("format");
        const seen = new Set();
        const valid = [];
        let skipped = false;
        for (const raw of parsed.items) {
          const f = normalize(raw);
          if (!f || empty(f) || seen.has(key(f)) || valid.length >= MAX_ITEMS) { skipped = true; continue; }
          seen.add(key(f)); valid.push(f);
        }
        items = valid;
        notice = skipped ? "部分舊收藏無法使用或重複，已略過；需要的條件可以重新收藏。" : "";
      } catch (_) {
        items = [];
        notice = "舊收藏無法讀取，請重新加入需要的查價條件。";
      }
    }
    function persist() {
      if (memoryOnly) return;
      try {
        storageProvider().setItem(STORAGE_KEY, JSON.stringify({ version: 1, items }));
        notice = "";
      } catch (_) { unavailable(); }
    }
    reload();
    return {
      list: () => items.map((f) => ({ ...f })),
      mode: () => memoryOnly ? "memory" : "persistent",
      notice: () => notice,
      has: (raw) => items.some((f) => key(f) === key(raw)),
      add(raw) {
        const f = normalize(raw);
        if (!f) return "invalid";
        if (empty(f)) return "empty";
        reload();
        if (items.some((saved) => key(saved) === key(f))) return "duplicate";
        if (items.length >= MAX_ITEMS) return "full";
        items.push(f); persist(); return "added";
      },
      remove(savedKey) {
        reload();
        const index = items.findIndex((f) => key(f) === savedKey);
        if (index < 0) return false;
        items.splice(index, 1); persist(); return true;
      },
      reload,
    };
  }
  return { STORAGE_KEY, MAX_ITEMS, normalize, key, createStore };
});
