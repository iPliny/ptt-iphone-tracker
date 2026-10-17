"""日本買取頁的靜態內容：各機型中文／日文頁，以及主頁比較表的預先內容。

只讀 jp_build 產生的 payload（latest.csv），不另存資料；價格異常判斷與 jp.js 的 visiblePrices 相同。
"""
import json
import re
from html import escape as E
from pathlib import Path
from urllib.parse import urlsplit

SHOPS = ["mobile-mix", "イオシス", "アメモバ"]
STORAGES = ["256GB", "512GB", "1TB", "2TB"]
MODELS = ["iPhone 18 Pro", "iPhone 18 Pro Max", "iPhone 17 Pro", "iPhone 17 Pro Max", "iPhone 17", "iPhone Air"]
CONDITIONS = ["未開封", "中古上限"]
SOURCE_HOSTS = {"mobile-mix.jp", "k-tai-iosys.com", "amemoba.com"}
GA_ID = "G-G3GH12TQSZ"

# 介面文字與 jp.js 的 I18N 對應；改字時兩邊一起改。
TEXT = {
    "zh": {
        "lang": "zh-Hant-TW", "brand": "PTT MacShop交易觀測", "top": "日本買取價比較", "h1": "{m} 日本買取價比較",
        "title": "{m} 日本買取價比較【{y}年{mo}月】mobile-mix・イオシス・アメモバ",
        "lead": "{m} 在日本二手店的收購價（SIMフリー），{t}（日本時間）確認。",
        "best": "未開封 {s} 最高是 {shop} {p}",
        "best_used": "中古 {s} 最高是 {shop} {p}",
        "cond": {"未開封": "未開封", "中古上限": "中古"},
        "cond_note": {"未開封": "イオシス「未使用品」與アメモバ「新品」列為未開封；mobile-mix 依顏色另有價格，見互動頁。",
                      "中古上限": "中古價是各店中古機的收購上限（外觀、電池等狀態最好時），實際依店家查定；mobile-mix 只收未開封。"},
        "h2": "{c}・SIMフリー買取價", "storage": "容量", "spread": "價差", "max": "最高", "none_shop": "不收中古",
        "empty": "目前沒有可公開的價格。", "interactive": "查看價格走勢與最近變動", "others": "其他機型",
        "foot": "價格以店家頁面為準，每天約日本時間 9、15、21 點抓取，實際時間可能延後。本頁只顯示日圓。",
        "by": '由 <a href="https://crawlsnek.com/">CrawlSnek</a> 提供', "switch": "日本語", "sep": "；", "end": "。",
        "desc_tail": "比較 mobile-mix、イオシス、アメモバ 的未開封與中古買取價，每天更新。",
    },
    "ja": {
        "lang": "ja", "brand": "PTT MacShop交易觀測", "top": "iPhone 買取価格比較", "h1": "{m} 買取価格比較",
        "title": "{m} 買取価格比較【{y}年{mo}月】mobile-mix・イオシス・アメモバ",
        "lead": "{m} の買取価格（SIMフリー）を店舗ごとに比較。{t}（日本時間）時点の価格です。",
        "best": "未開封 {s} の最高は {shop} の {p}",
        "best_used": "中古 {s} の最高は {shop} の {p}",
        "cond": {"未開封": "未開封", "中古上限": "中古"},
        "cond_note": {"未開封": "イオシスの「未使用品」とアメモバの「新品」を未開封としてまとめています。mobile-mix のカラー別価格は比較ページをご覧ください。",
                      "中古上限": "中古の価格は各店が掲載している中古買取の上限額（外装・バッテリーなどの状態が最も良い場合）です。実際の金額は各店の査定によります。mobile-mix は未開封のみ買取しています。"},
        "h2": "{c}・SIMフリーの買取価格", "storage": "容量", "spread": "価格差", "max": "最高", "none_shop": "中古買取なし",
        "empty": "現在公開できる価格はありません。", "interactive": "価格推移と最近の価格変更を見る", "others": "ほかの機種",
        "foot": "価格は各店のページが優先です。毎日 9 時・15 時・21 時ごろ（日本時間）に取得しています。実際の取得は遅れることがあります。",
        "by": '提供：<a href="https://crawlsnek.com/">CrawlSnek</a>', "switch": "中文", "sep": "。", "end": "。",
        "desc_tail": "mobile-mix・イオシス・アメモバの未開封・中古の買取価格を毎日更新。",
    },
}


def slug(model):
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def money(value):
    return "—" if value is None else "¥" + format(value, ",")


def visible_prices(values):
    """和 jp.js 相同：與其他店中位數相比低於一半或高於兩倍的價格不公開。"""
    out = []
    for i, price in enumerate(values):
        if not isinstance(price, int) or price <= 0:
            out.append(None)
            continue
        others = sorted(p for j, p in enumerate(values) if j != i and isinstance(p, int) and p > 0)
        if not others:
            out.append(price)
            continue
        m = len(others) // 2
        median = others[m] if len(others) % 2 else (others[m - 1] + others[m]) / 2
        out.append(None if price < median / 2 or price > median * 2 else price)
    return out


def main_rows(latest, condition):
    return [r for r in latest if r.get("condition") == condition and r.get("carrier") == "SIMフリー" and not r.get("color")]


def comparison(latest, model, condition):
    rows = [r for r in main_rows(latest, condition) if r.get("model") == model]
    # 只有中古會標示「不收中古」；未開封缺價一律顯示 —。
    offered = [condition == "未開封" or any(r["shop"] == shop for r in main_rows(latest, condition)) for shop in SHOPS]
    groups = []
    for storage in STORAGES:
        found = [next((r for r in rows if r["shop"] == shop and r["storage"] == storage), None) for shop in SHOPS]
        if not any(found):
            continue
        values = visible_prices([r["price_jpy"] if r else None for r in found])
        present = [v for v in values if v is not None]
        groups.append({"storage": storage, "rows": found, "values": values,
                       "highest": max(present) if present else None,
                       "spread": max(present) - min(present) if len(present) >= 2 else None})
    return groups, offered


def source(url):
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return ""
    return url if parts.scheme == "https" and parts.hostname in SOURCE_HOSTS else ""


def table(groups, offered, t):
    head = "".join(f'<th scope="col">{E(s)}</th>' for s in SHOPS)
    body = []
    for g in groups:
        cells = []
        for i, shop in enumerate(SHOPS):
            if not offered[i]:
                cells.append(f'<td data-label="{E(shop)}"><div><span class="jp-none">{t["none_shop"]}</span></div></td>')
                continue
            price, row = g["values"][i], g["rows"][i]
            best = price is not None and price == g["highest"]
            label = f'<span class="jp-price">{money(price)}</span>'
            url = source(row["source_url"]) if row else ""
            if url:
                label = f'<a href="{E(url, quote=True)}" rel="noopener">{label}</a>'
            badge = f'<span class="jp-badge">{t["max"]}</span>' if best else ""
            cls = ' class="jp-best"' if best else ""
            cells.append(f'<td data-label="{E(shop)}"{cls}><div>{label}{badge}</div></td>')
        body.append(f'<tr><th scope="row">{E(g["storage"])}</th>{"".join(cells)}'
                    f'<td data-label="{t["spread"]}"><span class="jp-spread">{money(g["spread"])}</span></td></tr>')
    return (f'<table class="jp-table"><thead><tr><th scope="col">{t["storage"]}</th>{head}'
            f'<th scope="col">{t["spread"]}</th></tr></thead><tbody>{"".join(body)}</tbody></table>')


def best_line(groups, t, key):
    for g in groups:
        if g["highest"] is not None:
            shop = SHOPS[g["values"].index(g["highest"])]
            return t[key].format(s=g["storage"], shop=shop, p=money(g["highest"]))
    return ""


def checked_at(latest):
    times = sorted(r["last_checked"] for r in latest if r.get("last_checked"))
    return times[-1][:16].replace("T", " ") if times else ""


def model_url(site_url, lang, model):
    return site_url + ("jp/ja/" if lang == "ja" else "jp/") + slug(model) + "/"


def page_html(payload, model, lang, site_url, models=MODELS):
    """models 是本次實際產生頁面的機型，「其他機型」只連到這些頁。"""
    t = TEXT[lang]
    latest = payload.get("latest") or []
    when = checked_at(latest)
    year, month = (when[:4], str(int(when[5:7]))) if when else ("", "")
    title = t["title"].format(m=model, y=year, mo=month)
    new_groups, new_offered = comparison(latest, model, "未開封")
    used_groups, used_offered = comparison(latest, model, "中古上限")
    bests = [b for b in (best_line(new_groups, t, "best"), best_line(used_groups, t, "best_used")) if b]
    lead = t["lead"].format(m=model, t=when or "—") + (t["sep"].join(bests) + t["end"] if bests else "")
    description = lead + t["desc_tail"] if len(lead + t["desc_tail"]) <= 160 else lead
    url = model_url(site_url, lang, model)
    other_lang = "zh" if lang == "ja" else "ja"
    root = "../../../" if lang == "ja" else "../../"   # 網站根目錄
    jp_root = "../../" if lang == "ja" else "../"      # jp/（jp.css 所在）
    home = "../"                                       # 同語言的日本買取主頁
    ld = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": t["brand"], "item": site_url},
        {"@type": "ListItem", "position": 2, "name": t["top"], "item": site_url + ("jp/ja/" if lang == "ja" else "jp/")},
        {"@type": "ListItem", "position": 3, "name": model, "item": url}]}, ensure_ascii=False).replace("</", "<\\/")
    sections = []
    for cond, sid, groups, offered in (("未開封", "new", new_groups, new_offered),
                                       ("中古上限", "used", used_groups, used_offered)):
        content = table(groups, offered, t) if groups else f'<p class="empty">{t["empty"]}</p>'
        sections.append(f'<section class="card" aria-labelledby="{sid}-title">'
                        f'<div class="card-head"><h2 id="{sid}-title">'
                        f'{E(t["h2"].format(c=t["cond"][cond]))}</h2></div>'
                        f'<p class="intro">{E(t["cond_note"][cond])}</p>{content}'
                        f'<p class="hint"><a href="{home}?m={E(model.replace(" ", "+"))}'
                        f'{"&amp;c=used" if cond != "未開封" else ""}">{t["interactive"]}</a></p></section>')
    others = "".join(f'<li><a href="../{slug(m)}/">{E(m)}</a></li>' for m in models if m != model)
    switch = f'{jp_root}{slug(model)}/' if lang == "ja" else f'../ja/{slug(model)}/'
    hreflang = "".join(f'  <link rel="alternate" hreflang="{TEXT[l]["lang"]}" href="{E(model_url(site_url, l, model))}">\n'
                       for l in ("zh", "ja"))
    return f"""<!doctype html>
<html lang="{t['lang']}">
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
  <title>{E(title)}</title>
  <meta name="description" content="{E(description)}">
  <link rel="canonical" href="{E(url)}">
{hreflang}  <meta property="og:type" content="website">
  <meta property="og:title" content="{E(title)}">
  <meta property="og:description" content="{E(description)}">
  <meta property="og:url" content="{E(url)}">
  <link rel="stylesheet" href="{root}style.css">
  <link rel="stylesheet" href="{jp_root}jp.css">
  <script type="application/ld+json">{ld}</script>
</head>
<body>
  <header class="top">
    <div class="wrap">
      <a class="back" href="{home}">← {E(t['top'])}</a>
      <a class="jp-lang" href="{switch}" hreflang="{TEXT[other_lang]['lang']}" lang="{TEXT[other_lang]['lang']}">{t['switch']}</a>
      <h1>{E(t['h1'].format(m=model))}</h1>
      <p class="sub">{E(lead)}</p>
    </div>
  </header>
  <main class="wrap">
    {''.join(sections)}
    <nav class="card" aria-labelledby="others-title"><div class="card-head"><h2 id="others-title">{t['others']}</h2></div><ul class="jp-models">{others}</ul></nav>
    <footer class="jp-footer">
      <p>{E(t['foot'])}</p>
      <p class="by-crawlsnek">{t['by']}</p>
    </footer>
  </main>
</body>
</html>
"""


def render_jp_pages(out_dir, payload, site_url):
    """輸出 jp/<slug>/、jp/ja/<slug>/，並把主頁的機型連結與預設比較表寫進 HTML；回傳 sitemap 網址。"""
    out = Path(out_dir) / "jp"
    latest = payload.get("latest") or []
    models = [m for m in MODELS if any(r.get("model") == m for r in latest)]
    urls = []
    for model in models:
        for lang in ("zh", "ja"):
            path = out / ("ja" if lang == "ja" else "") / slug(model) / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page_html(payload, model, lang, site_url, models), encoding="utf-8")
            urls.append(model_url(site_url, lang, model))
    for lang, index in (("zh", out / "index.html"), ("ja", out / "ja" / "index.html")):
        html = index.read_text(encoding="utf-8")
        links = '<ul class="jp-models">' + "".join(f'<li><a href="{slug(m)}/">{E(m)}</a></li>' for m in models) + "</ul>"
        html = html.replace("<!--JP_MODEL_LINKS-->", links)
        # 預設機型（18 Pro）的未開封比較表先寫進 HTML，JavaScript 載入後再接手。
        groups, offered = comparison(latest, MODELS[0], "未開封")
        if groups:
            html = re.sub(r'(<div id="comparison" aria-live="polite">).*?(</div>)',
                          lambda m: m[1] + table(groups, offered, TEXT[lang]) + m[2], html, count=1, flags=re.S)
        index.write_text(html, encoding="utf-8")
    return urls
