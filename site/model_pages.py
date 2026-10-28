"""機型頁的建置時內容；只使用 build_data 已排除異常值的公開資料。"""
import math
import re
import shutil
from html import escape
from urllib.parse import urlsplit


def model_path(model):
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-") or "model"
    return "models/" + slug + ".html"


def model_url_path(model):
    """Cloudflare Pages 的公開網址不含 .html；建置檔名仍由 model_path 決定。"""
    return model_path(model)[:-len(".html")]


def model_navigation(data, root="", current=None):
    """固定顯示的機型入口；同代優先，再依世代與機型等級排序。"""
    rows = [r for r in data.get("model_totals", []) if r["model"] != current]
    generation = re.match(r"iPhone (\d+)(?:\D|$)", "iPhone 18" if current == "iPhone Duo" else current or "")

    def same_generation(name):
        match = re.match(r"iPhone (\d+)(?:\D|$)", "iPhone 18" if name == "iPhone Duo" else name)
        return bool(generation and match and generation[1] == match[1])

    from market import model_rank
    rows.sort(key=lambda r: (not same_generation(r["model"]), model_rank(r["model"])))
    if not rows:
        return ""
    title = "比較其他機型" if current else "機型行情快速查詢"
    links = "".join(f'<li><a href="{escape(root + model_url_path(r["model"]), quote=True)}">'
                    f'{escape(r["model"])} 二手行情</a></li>' for r in rows[:6])
    return (f'<nav class="card model-navigation" aria-label="{title}"><h2>{title}</h2>'
            f'<ul>{links}</ul><p class="hint"><a href="{escape(root + "market/", quote=True)}">'
            '查看全部機型與容量行情</a></p></nav>')


def money(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "$" + format(value, ",")


def safe_link(url, label):
    """來源網址不接受 script 等可執行協定；缺連結仍保留文字。"""
    label = escape(str(label))
    if urlsplit(url or "").scheme not in ("https", "http"):
        return label
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{label}</a>'


def storage_key(storage):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(GB|TB)", storage or "", re.I)
    return (float(match[1]) * (1024 if match[2].upper() == "TB" else 1)
            if match else float("inf"), storage or "")


def summary_cards(stats):
    days = stats.get("median_days")
    samples = stats.get("days_samples")
    cards = [
        ("刊登", stats.get("listed", 0),
         f'在架 {stats.get("active", 0)} · 已售 {stats.get("sold", 0)}' +
         (f' · 多品項 {stats["multi"]}' if stats.get("multi") else "")),
        ("刊登中位數", money(stats.get("median_price")),
         money(stats.get("min_price")) + " – " + money(stats.get("max_price"))),
        ("成交中位數", money(stats.get("median_sold_price")), "售出時的最後標價"),
        ("售出天數中位數", str(days) + " 天" if days is not None else "—",
         (f"{samples} 筆樣本" + ("（推估）" if stats.get("days_estimated") else ""))
         if samples else "還沒有售出天數"),
    ]
    return "".join(f'<div class="kpi"><div class="label">{escape(label)}</div>'
                   f'<div class="value">{escape(str(value))}</div>'
                   f'<div class="note">{escape(note)}</div></div>'
                   for label, value, note in cards)


def capacity_table(rows):
    columns = [("storage", "容量"), ("listed", "刊登"), ("active", "在架"),
               ("sold", "已售"), ("median_price", "刊登中位數"),
               ("median_sold_price", "成交中位數"), ("min_price", "最低"),
               ("max_price", "最高"), ("median_days", "售出天數")]
    header = "<thead><tr>" + "".join(f"<th>{label}</th>" for _, label in columns) + "</tr></thead>"
    body = []
    for row in sorted(rows, key=lambda r: storage_key(r.get("storage"))):
        cells = []
        for key, _ in columns:
            value = row.get(key)
            if key == "storage":
                text = escape(value or "容量未提供")
            elif "price" in key:
                text = escape(money(value))
            else:
                text = "—" if value is None else escape(str(value))
            if key == "median_days" and value is not None and row.get("days_estimated"):
                text += "（推估）"
            attr = ' class="num"' if key != "storage" else ""
            cells.append(f'<td{attr}>{text}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return header + "<tbody>" + "".join(body) + "</tbody>"


def listing_cards(listings):
    cards = []
    for row in listings[:10]:
        tags = [row.get("storage"), row.get("color"), "全新未拆" if row.get("brand_new") else "",
                "電池 " + str(row["battery"]) + "%" if row.get("battery") else "", row.get("warranty")]
        chips = "".join(f'<span class="chip">{escape(str(tag))}</span>' for tag in tags if tag)
        cards.append('<div class="item"><div>' +
                     safe_link(row.get("url"), row.get("model") or row.get("title") or "（未解析）") +
                     " " + chips + f'</div><div class="price">{escape(money(row.get("price")))}</div>' +
                     f'<div class="meta">{escape(row.get("notes") or "")}</div>' +
                     f'<div class="meta side">{escape(row.get("status") or "")} · ' +
                     escape((row.get("post_time") or "")[5:16]) + "</div></div>")
    return ('<div class="items">' + "".join(cards) + "</div>" if cards else
            '<p class="empty">這個機型目前沒有單支刊登文章；多品項只納入刊登價統計。</p>')


def apple_table(info):
    if not info:
        return ""
    on_sale = bool(info.get("buy_url"))
    heading = "官網售價" if on_sale else "最終官方售價"
    link = safe_link(info.get("buy_url"), "到 Apple 官網購買 ↗") if on_sale else "官網已停售"
    missing = "官網沒有這個容量" if on_sale else "查無官方價格"
    rows = "".join(f'<tr><td>{escape(storage)}</td><td class="num">{escape(money(price) if price else missing)}</td></tr>'
                   for storage, price in sorted(info.get("prices", {}).items(), key=lambda x: storage_key(x[0])))
    note = ("官網售價為 " + str(info.get("checked_at", "")) + " 在 Apple 台灣官網查到的價格，購買前請以官網為準。"
            if on_sale else "最終官方售價是 Apple 台灣官網停售前最後的建議售價。")
    sources = "、".join(safe_link(url, f"來源{i + 1}") for i, url in enumerate(info.get("sources", [])))
    return (f'<div class="card-head"><h2>Apple 原廠</h2>{link}</div><div class="scroll"><table>'
            f'<thead><tr><th>容量</th><th>{heading}</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="hint">{escape(note)}{sources}</p>')


def trend_pct(values, days):
    """最新一天和 days 天前相比的漲跌百分比（四捨五入到 0.1），算不出來回傳 None。"""
    idx = [i for i, v in enumerate(values) if v is not None]
    if not idx or idx[-1] - days < 0 or values[idx[-1] - days] is None:
        return None
    last, before = values[idx[-1]], values[idx[-1] - days]
    return math.floor((last - before) / before * 100 * 10 + 0.5) / 10  # 和 JavaScript 的 Math.round 一樣，.5 往正方向進位


def pct_text(pct):
    if pct is None:
        return "—"
    return "持平" if pct == 0 else ("+" if pct > 0 else "−") + f"{abs(pct):.1f}%"


def trend_change(values, days):
    """最新一天和 days 天前的漲跌，格式與 model.js 的 changeText 相同。"""
    return pct_text(trend_pct(values, days))


def trend_summary(data, model):
    """全部容量分頁的行情摘要：每個容量的二手行情（沒有二手時用全新），JavaScript 會再重畫。"""
    series = [x for x in data.get("trends", {}).get("series", []) if x["model"] == model]
    used = [x for x in series if not x["brand_new"]]
    rows = sorted(used or series, key=lambda x: storage_key(x["storage"]))
    storages = sorted({r["storage"] for r in data["listings"] if r["model"] == model}, key=storage_key)
    out = []
    for x in rows:
        latest = next(v for v in reversed(x["values"]) if v is not None)
        label = (x["storage"] or "容量未提供") + (" 全新未拆" if x["brand_new"] else " 二手")
        cls = "s" + str((storages.index(x["storage"]) if x["storage"] in storages else 0) % 5 + 1)
        out.append(f'<div class="trend-item"><div class="label"><span class="key {cls}"></span>{escape(label)}</div>'
                   f'<div class="value">{escape(money(latest))}</div>'
                   f'<div class="note">7 天 {trend_change(x["values"], 7)} · 30 天 {trend_change(x["values"], 30)}</div></div>')
    return "".join(out)


def render_model_html(template, data, model, canonical_url, asset_prefix=""):
    """保留互動元件 ID 與腳本，預先填入可直接閱讀的機型內容。"""
    from seo import metadata, strip_social_meta
    stats = next(row for row in data["model_totals"] if row["model"] == model)
    listings = [row for row in data["listings"] if row["model"] == model]
    capacities = [row for row in data["models"] if row["model"] == model]
    title = model + " 二手行情、各容量價格 · PTT MacShop交易觀測"
    description = (f'{model} 的 PTT MacShop 刊登行情：{stats.get("listed", 0)} 筆刊登，'
                   f'刊登價中位數 {money(stats.get("median_price"))}。售出價格為賣家售出時最後標價，非實際成交價。')
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{escape(title)}</title>", strip_social_meta(template), count=1)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  lambda _: f'<meta name="description" content="{escape(description, quote=True)}">', html, count=1)
    html = html.replace("</head>", f'<link rel="canonical" href="{escape(canonical_url, quote=True)}">\n</head>', 1)
    root_url = canonical_url.split("/models/")[0] + "/" if "/models/" in canonical_url else canonical_url.split("model.html")[0]
    html = html.replace("</head>", metadata(title, description, canonical_url,
                        [("PTT MacShop交易觀測", root_url), (model, canonical_url)], site_url=root_url) + "</head>", 1)
    html = html.replace("<body>", f'<body data-model="{escape(model, quote=True)}">', 1)
    html = html.replace('<h1 id="model-name">載入中…</h1>', f'<h1 id="model-name">{escape(model)}</h1>')
    updated = f'最後回訪 {data.get("last_checked") or "—"} · 這個機型共追蹤 {len(listings)} 篇'
    html = html.replace('<span id="updated">載入中…</span>', f'<span id="updated">{escape(updated)}</span>')
    html = html.replace('<main class="wrap" id="model-main" hidden>', '<main class="wrap" id="model-main">')
    html = html.replace('<section class="kpis" id="kpis"></section>',
                        '<section class="kpis" id="kpis">' + summary_cards(stats) + '</section>')
    html = html.replace('<table id="compare"></table>', '<table id="compare">' + capacity_table(capacities) + '</table>')
    html = html.replace('<h2 id="list-title">文章</h2>', f'<h2 id="list-title">全部容量的文章（{len(listings)}）</h2>')
    html = html.replace('<div id="list"></div>', '<div id="list">' + listing_cards(listings) + '</div>')
    html = html.replace('<div id="chart" class="chart"></div>',
                        '<div id="chart" class="chart"><p class="hint">啟用 JavaScript 可查看價格分布圖及篩選文章。</p></div>')
    trend = trend_summary(data, model)
    if trend:
        html = html.replace('<section class="card" id="trend-card" hidden>', '<section class="card" id="trend-card">', 1)
        html = html.replace('<div id="trend-summary" class="trend-summary"></div>',
                            '<div id="trend-summary" class="trend-summary">' + trend + '</div>', 1)
    apple = apple_table(data.get("apple", {}).get(model))
    if apple:
        html = html.replace('<section class="card apple" id="apple" hidden></section>',
                            '<section class="card apple" id="apple">' + apple + '</section>')
    if asset_prefix:
        for value in ["favicon.svg", "style.css", "./", "column/", "market/", "market/#faq", "prices", "common.js", "watchlist.js", "model.js"]:
            for attr in ["src", "href"]:
                html = html.replace(f'{attr}="{value}"', f'{attr}="{asset_prefix}{value}"')
    html = html.replace('</main>', model_navigation(data, asset_prefix, model) + '\n</main>', 1)
    return html


def build_model_pages(out_dir, data, site_url):
    """每次重建自有的 models/ 目錄，避免消失機型留下過期公開頁。"""
    from pathlib import Path
    out = Path(out_dir)
    paths = [model_path(row["model"]) for row in data["model_totals"]]
    if len(set(paths)) != len(paths):
        raise ValueError("機型靜態網址重複；請先處理機型名稱，不能覆蓋其他機型頁。")
    directory = out / "models"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()
    if not paths:
        return []
    template = (out / "model.html").read_text(encoding="utf-8")
    for row, path in zip(data["model_totals"], paths):
        html = render_model_html(template, data, row["model"], site_url + model_url_path(row["model"]), asset_prefix="../")
        (out / path).write_text(html, encoding="utf-8")
    return paths
