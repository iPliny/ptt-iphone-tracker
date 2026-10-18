"""公開頁的中繼資料及首頁快照；只接收 build_data 清理後的資料。"""
import json
import re
from html import escape
from model_pages import model_path, money


def social_meta(title, description, url, site_url, og_type="website", locale="zh_TW"):
    """分享資訊共用同一張字卡；網址沿用呼叫端的 SITE_URL，不猜部署網域。"""
    tags = {"og:type": og_type, "og:title": title, "og:description": description,
            "og:url": url, "og:locale": locale, "og:site_name": "PTT MacShop交易觀測",
            "og:image": site_url + "og.png", "og:image:width": "1200", "og:image:height": "630",
            "og:image:alt": "PTT MacShop交易觀測｜二手 iPhone 行情・每日更新"}
    return ("\n".join(f'<meta property="{key}" content="{escape(value, quote=True)}">'
                      for key, value in tags.items()) +
            '\n<meta name="twitter:card" content="summary_large_image">\n')


def strip_social_meta(html):
    """預產首頁／機型頁先移除模板的預設分享標籤，避免重複或留下通用機型標題。"""
    return re.sub(r'\s*<meta (?:property="og:[^"]+"|name="twitter:card") content="[^"]*">', "", html)


def metadata(title, description, url, breadcrumbs=(), *, site_url=None):
    nodes = [{"@context": "https://schema.org", "@type": "WebPage",
              "name": title, "description": description, "url": url, "inLanguage": "zh-Hant"}]
    if breadcrumbs:
        nodes.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                      "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                           "name": name, "item": link}
                                          for i, (name, link) in enumerate(breadcrumbs)]})
    # HTML parser 不應把資料裡的 </script> 當成腳本結尾。
    structured = json.dumps(nodes, ensure_ascii=False).replace("<", "\\u003c")
    return (social_meta(title, description, url, site_url or (breadcrumbs[0][1] if breadcrumbs else url)) +
            f'\n<script type="application/ld+json">{structured}</script>\n')


def render_home(template, data, site_url):
    title = "PTT MacShop交易觀測｜二手 iPhone 行情與成交追蹤"
    description = "每日整理 PTT MacShop 二手 iPhone 行情、各容量刊登價、售出天數與成交追蹤，並提供日本買取價、官方價格及行情週報。售出標價不代表實際成交價。"
    html = re.sub(r"<title>.*?</title>", lambda _: f"<title>{title}</title>", strip_social_meta(template), count=1)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  lambda _: f'<meta name="description" content="{description}">', html, count=1)
    html = html.replace("</head>", metadata(title, description, site_url, site_url=site_url) + "</head>", 1)
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
