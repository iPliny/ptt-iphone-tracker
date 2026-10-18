"""公開頁的中繼資料及首頁快照；只接收 build_data 清理後的資料。"""
import json
from html import escape
from model_pages import model_path, money


def metadata(title, description, url, breadcrumbs=()):
    nodes = [{"@context": "https://schema.org", "@type": "WebPage",
              "name": title, "description": description, "url": url, "inLanguage": "zh-Hant"}]
    if breadcrumbs:
        nodes.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                      "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                           "name": name, "item": link}
                                          for i, (name, link) in enumerate(breadcrumbs)]})
    tags = {"og:type": "website", "og:title": title, "og:description": description,
            "og:url": url, "og:locale": "zh_TW", "og:site_name": "PTT MacShop交易觀測"}
    # HTML parser 不應把資料裡的 </script> 當成腳本結尾。
    structured = json.dumps(nodes, ensure_ascii=False).replace("<", "\\u003c")
    return ("\n".join(f'<meta property="{key}" content="{escape(value, quote=True)}">'
                      for key, value in tags.items()) +
            '\n<meta name="twitter:card" content="summary">' +
            f'\n<script type="application/ld+json">{structured}</script>\n')


def render_home(template, data, site_url):
    title = "二手 iPhone 價格、售出行情與日本買取價 · PTT MacShop交易觀測"
    description = "每日追蹤 PTT MacShop 二手 iPhone 刊登價、售出時最後標價與各容量行情，並整理日本買取價、官方價格與行情週報。售出標價不代表實際成交價。"
    html = template.replace("<title>PTT MacShop交易觀測</title>", f"<title>{title}</title>")
    html = html.replace("每天整理 PTT MacShop 版 iPhone 二手機的新刊登、售出與行情。", description)
    html = html.replace("</head>", metadata(title, description, site_url) + "</head>", 1)
    checked = data.get("last_checked") or "尚無回訪紀錄"
    updated = f'最後回訪 {checked} · 共追蹤 {data.get("counts", {}).get("total", 0)} 篇'
    html = html.replace('<span id="updated">載入中…</span>', f'<span id="updated">{escape(updated)}</span>')
    day = next(iter(data.get("days", [])[-1:]), None)
    if day:
        cards = [("新刊登", "new"), ("售出", "sold"), ("刪文", "deleted"),
                 ("改價", "price_changes"), ("日終在架", "on_shelf")]
        kpis = "".join(f'<div class="kpi"><div class="label">{label}</div>'
                       f'<div class="value">{day.get(key, 0)}</div>'
                       f'<div class="note">{escape(day["date"])}</div></div>' for label, key in cards)
    else:
        kpis = '<p class="empty">尚無每日統計</p>'
    html = html.replace('<section class="kpis" id="kpis"></section>',
                        '<section class="kpis" id="kpis">' + kpis + '</section>')
    rows = []
    for row in data.get("models", []):
        rows.append(f'<tr><td><a href="{escape(model_path(row["model"]), quote=True)}">{escape(row["model"])}</a></td>'
                    f'<td>{escape(row.get("storage") or "容量未提供")}</td><td>{row.get("listed", 0)}</td>'
                    f'<td>{escape(money(row.get("median_price")))}</td>'
                    f'<td>{escape(money(row.get("median_sold_price")))}</td></tr>')
    table = ('<thead><tr><th>型號</th><th>容量</th><th>刊登</th><th>刊登中位數</th><th>售出時最後標價中位數</th></tr></thead>'
             '<tbody>' + ("".join(rows) or '<tr><td colspan="5">尚無型號行情</td></tr>') + '</tbody>')
    return html.replace('<table id="models"></table>', '<table id="models">' + table + '</table>')
