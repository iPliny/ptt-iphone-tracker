"""「二手 iPhone 行情總覽」：每次建置網站時依 data.json 的 trends 產生 market/index.html。

只用 build_data 已排除異常值的公開資料，不另存檔案；數字每次建置都更新。
"""
from seo import social_meta
import json
import os
import re
from datetime import date, timedelta
from html import escape as E
from urllib.parse import quote

import build_site as S
from model_pages import model_path, money, pct_text, storage_key, trend_pct

TITLE = "二手 iPhone 行情總覽"
BRAND = "PTT MacShop交易觀測"
GA_ID = "G-G3GH12TQSZ"
TOP = 10            # 每個排行列幾名
FAST_MIN = 3        # 售出天數至少幾筆才列入「賣得最快」
NUM = ' class="num"'
SUFFIX_ORDER = ["Pro Max", "Pro", "Air", "Plus", "", "e", "mini"]


def model_rank(model):
    """新機型排前面；同一代依 Pro Max、Pro、Air、Plus、標準版、e、mini。"""
    m = re.fullmatch(r"iPhone (\d+)\s*(.*)", model or "")
    if model == "iPhone Air":
        gen, suffix = 17, "Air"
    elif m:
        gen, suffix = int(m[1]), m[2].strip()
    else:
        return (1, 0, 0, model or "")
    order = SUFFIX_ORDER.index(suffix) if suffix in SUFFIX_ORDER else len(SUFFIX_ORDER)
    return (0, -gen, order, model)


def current_rows(data):
    """每組型號×容量的目前行情：只收最新一天還有數字的線，二手與全新並列。"""
    trends = data.get("trends") or {}
    series = trends.get("series") or []
    if not trends.get("start") or not series:
        return [], None
    end = date.fromisoformat(trends["start"]) + timedelta(days=len(series[0]["values"]) - 1)
    rows = {}
    for x in series:
        if x["values"][-1] is None:
            continue
        row = rows.setdefault((x["model"], x["storage"]), {"model": x["model"], "storage": x["storage"]})
        kind = "new" if x["brand_new"] else "used"
        row[kind] = x["values"][-1]
        row[kind + "_7"] = trend_pct(x["values"], 7)
        row[kind + "_30"] = trend_pct(x["values"], 30)
        if kind == "used":
            row["used_values"] = x["values"]
    out = sorted(rows.values(), key=lambda r: (model_rank(r["model"]), storage_key(r["storage"])))
    return out, end.isoformat()


def rankings(data, rows):
    used = [r for r in rows if r.get("used")]
    period = 30 if any(r.get("used_30") is not None for r in used) else 7
    key = f"used_{period}"
    drops = sorted((r for r in used if r.get(key) is not None and r[key] < 0), key=lambda r: r[key])[:TOP]
    cheap = sorted(used, key=lambda r: r["used"])[:TOP]
    fast = sorted((m for m in data.get("models", []) if m.get("median_days") is not None
                   and m.get("days_samples", 0) >= FAST_MIN), key=lambda m: (m["median_days"], -m["sold"]))[:TOP]
    return period, drops, cheap, fast


def label(r):
    return f"{r['model']} {r['storage'] or '容量未提供'}"


def link(r, root):
    href = root + model_path(r["model"]) + ("?s=" + quote(r["storage"]) if r.get("storage") else "")
    return f'<a href="{E(href, quote=True)}">{E(label(r))}</a>'


def faq(day, period):
    return [
        {"q": "二手行情是怎麼算的？",
         "a": "每天結束時仍在 PTT MacShop 版上販售的單支 iPhone 文章，取當天標價的中位數；全新未拆與二手分開算，"
              "明顯抓錯的異常價格不列入。當天在架少於 3 篇的機型容量不計算。"},
        {"q": "這是實際成交價嗎？",
         "a": "不是。PTT 沒有公開成交價，這裡是賣家的刊登價；便宜的文章通常先賣掉，所以在架行情會比成交價略高。"
              "機型頁的「成交中位數」是偵測到售出時的最後標價，可以一起參考。"},
        {"q": "多久更新一次？",
         "a": f"本站每 6 小時回訪 PTT 文章並重建網站，本頁數字是 {day} 的行情。漲跌是和 {period} 天前的行情相比。"},
        {"q": "「賣得最快」怎麼排？",
         "a": f"用發文到偵測售出的天數中位數排序，至少 {FAST_MIN} 筆售出紀錄才列入；第一次看到就已售出的文章，用賣家最後編輯的時間推估。"},
        {"q": "很久沒賣掉的文章怎麼算？",
         "a": "發文 45 天內每 6 小時回訪，之後到 90 天約每天回訪一次。滿 90 天還沒賣掉的文章標成「逾期未售」，"
              "仍算在刊登數與刊登價，但不再算在架，也不算售出。"},
    ]


def page_html(data, root="../"):
    rows, day = current_rows(data)
    url = S.SITE_URL + "market/"
    if not rows:
        day = day or (data.get("generated_at") or "")[:10]
    d = date.fromisoformat(day) if day else date.today()
    title = f"{TITLE}【{d.year}年{d.month}月】各機型二手價格每日更新"
    period, drops, cheap, fast = rankings(data, rows)
    used_count = sum(1 for r in rows if r.get("used"))
    lead = (f"整理 PTT MacShop 版的 iPhone 販售文，{d.year}/{d.month}/{d.day} 共有 {used_count} 組機型容量算得出二手行情。"
            "行情是當天仍在架文章的標價中位數，每 6 小時更新。")
    if drops:
        lead += f"近 {period} 天跌最多的是 {label(drops[0])}（{pct_text(drops[0][f'used_{period}'])}）。"
    description = lead[:150]
    faqs = faq(day, period)
    ld = json.dumps([
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": BRAND, "item": S.SITE_URL},
            {"@type": "ListItem", "position": 2, "name": TITLE, "item": url}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faqs]},
    ], ensure_ascii=False).replace("</", "<\\/")

    def table(caption, head, body):
        ths = "".join(f'<th scope="col"{NUM if i else ""}>{h}</th>' for i, h in enumerate(head))
        return (f'<div class="scroll"><table><caption>{caption}</caption><thead><tr>{ths}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>')

    sections = []
    if drops:
        sections.append(("drops", f"近 {period} 天降價最多", table(
            f"二手行情和 {period} 天前相比", ["機型／容量", "目前行情", "漲跌"],
            [f'<tr><th scope="row">{link(r, root)}</th><td class="num">{money(r["used"])}</td>'
             f'<td class="num">{pct_text(r[f"used_{period}"])}</td></tr>' for r in drops])))
    if cheap:
        sections.append(("cheap", "二手行情最便宜", table(
            "目前二手行情由低到高", ["機型／容量", "目前行情", f"近 {period} 天"],
            [f'<tr><th scope="row">{link(r, root)}</th><td class="num">{money(r["used"])}</td>'
             f'<td class="num">{pct_text(r.get(f"used_{period}"))}</td></tr>' for r in cheap])))
    if fast:
        sections.append(("fast", "賣得最快", table(
            "發文到售出的天數中位數（不分全新與否）", ["機型／容量", "售出天數", "已售", "成交中位數"],
            [f'<tr><th scope="row">{link(m, root)}</th><td class="num">{m["median_days"]} 天'
             f'{"（含推估）" if m.get("days_estimated") else ""}</td><td class="num">{m["sold"]}</td>'
             f'<td class="num">{money(m.get("median_sold_price"))}</td></tr>' for m in fast])))
    if rows:
        sections.append(("all", "各機型二手行情一覽", table(
            "目前行情；全新未拆另列，— 表示在架太少算不出來", ["機型／容量", "二手行情", "7 天", "30 天", "全新未拆"],
            [f'<tr><th scope="row">{link(r, root)}</th><td class="num">{money(r.get("used"))}</td>'
             f'<td class="num">{pct_text(r.get("used_7"))}</td><td class="num">{pct_text(r.get("used_30"))}</td>'
             f'<td class="num">{money(r.get("new"))}</td></tr>' for r in rows])))
    if not sections:
        sections.append(("all", "各機型二手行情一覽", '<p class="empty">行情資料準備中。</p>'))

    toc = "".join(f'<li><a href="#{sid}">{E(h)}</a></li>' for sid, h, _ in sections)
    body = "".join(f'      <section id="{sid}">\n        <h2>{E(h)}</h2>\n        {content}\n      </section>\n'
                   for sid, h, content in sections)
    faq_html = "".join(f"<dt>Q. {E(f['q'])}</dt><dd>A. {E(f['a'])}</dd>" for f in faqs)
    return f"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
  <!-- Google tag (gtag.js)：Google Analytics 4，Search Console 也靠這段驗證擁有權 -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());

    gtag('config', '{GA_ID}');
    if (location.hostname === 'macshop.crawlsnek.com') {{
      gtag('config', 'G-ZCY3R6PPNS', {{content_group: 'PTT MacShop'}});
    }}
  </script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/svg+xml" href="{root}favicon.svg">
  <title>{E(title)}｜{BRAND}</title>
  <meta name="description" content="{E(description)}">
  <link rel="canonical" href="{E(url)}">
{social_meta(title, description, url, S.SITE_URL)}
  <link rel="stylesheet" href="{root}style.css">
  <script type="application/ld+json">{ld}</script>
</head>
<body class="column">
  <header class="top">
    <div class="wrap">
      <nav class="crumbs" aria-label="breadcrumb"><a href="{root}">{BRAND}</a> › <span>{TITLE}</span></nav>
    </div>
  </header>
  <main class="wrap">
    <article class="card col-article">
      <h1>{E(title)}</h1>
      <p class="hint"><time datetime="{E(day or '')}">資料日期 {E(day or '—')}</time> · 每 6 小時更新</p>
      <p>{E(lead)}</p>
      <nav class="toc" aria-label="目次">
        <p class="toc-title">目次</p>
        <ol>{toc}<li><a href="#faq">常見問題</a></li></ol>
      </nav>
{body}      <section id="faq">
        <h2>常見問題</h2>
        <dl class="faq">{faq_html}</dl>
      </section>
      <p class="hint">點機型可看每日行情走勢、各容量比較與 PTT 原文。另有 <a href="{root}column/">二手 iPhone 行情週報</a>、<a href="{root}weekly/">iPhone 二手週報</a> 與 <a href="{root}prices.html">歷代官方價格</a>。</p>
    </article>
  </main>
  <footer class="wrap foot">
    <p>資料來源：PTT MacShop 版標題含「[販售]」與 iPhone 的文章，由 <a href="{root}">{BRAND}</a> 每 6 小時回訪整理。</p>
    <p class="by-crawlsnek">由 <a href="https://crawlsnek.com/">CrawlSnek</a> 提供</p>
  </footer>
</body>
</html>
"""


def render_market(out_dir, data):
    """輸出 market/index.html；回傳網址給 sitemap。"""
    os.makedirs(os.path.join(out_dir, "market"), exist_ok=True)
    with open(os.path.join(out_dir, "market", "index.html"), "w", encoding="utf-8") as f:
        f.write(page_html(data))
    return S.SITE_URL + "market/"
