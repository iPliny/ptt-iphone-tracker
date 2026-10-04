"""每週專欄「二手 iPhone 行情週報」：產生每期統計快照，並在建置網站時輸出靜態頁面。

一期涵蓋一週（週日～週六，台灣時間）。排程在週日晚上（日本時間 21:00）執行：
    python site/column.py                 # 為上一個完整週產生一期，已存在就跳過
    python site/column.py --date 2026-10-04 --force
每期的統計存成 data/column/<週日日期>.json，之後資料再變動也不改舊期數字；
文章內文在建置網站時由統計套範本產生（build_site.py 會呼叫 render_column）。
"""
import argparse
import html
import json
import os
import statistics
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import build_site as S

COLUMN_DIR = os.path.join(S.DATA_DIR, "column")
COLUMN_TITLE = "二手 iPhone 行情週報"
BRAND = "PTT每日交易觀測"
GA_ID = "G-G3GH12TQSZ"
TOP_GROUPS = 8      # 表格列出幾組型號×容量
FAST_MIN = 2        # 售出天數至少幾筆才列入「賣得最快」


# ---------- 統計 ----------

def week_bounds(today):
    """today 之前最近一個完整的週日～週六。週日執行時就是剛結束的那一週。"""
    back = (today.weekday() - 5) % 7 or 7   # 距離上一個週六幾天（Mon=0 … Sat=5）
    end = today - timedelta(days=back)
    return end - timedelta(days=6), end


def median_int(values):
    return int(statistics.median(values)) if values else None


def parse_price_change(detail):
    """'42000 → 39500' → (42000, 39500)；格式不對回傳 None。"""
    try:
        a, b = (S.to_int(x) for x in (detail or "").split("→"))
    except ValueError:
        return None
    return (a, b) if a and b else None


def load_tracked(data_dir):
    raw = S.read_csv(os.path.join(data_dir, "listings.csv"))
    events = S.read_csv(os.path.join(data_dir, "events.csv"))
    events = S.attach_price_times(events, S.read_csv(os.path.join(data_dir, "price_event_times.csv")))
    listings = [S.clean_listing(r) for r in raw if r.get("status") in S.TRACKED_STATUSES]
    first_seen = min((d for d in (S.day_of(r.get("first_seen")) for r in raw) if d), default=None)
    return listings, events, first_seen


def week_counts(listings, events, del_day, start, end):
    """一週內的新刊登、售出、刪文、改價，以及週六結束時仍在架上的篇數。"""
    def inweek(d):
        return bool(d) and start <= d <= end

    new = [r for r in listings if inweek(S.day_of(r["post_time"]))]
    sold = [r for r in listings if r["status"] == "已售出" and inweek(S.day_of(r["sold_at"]))]
    deleted = [r for r in listings if r["status"] == "已刪除" and inweek(del_day.get(r["url"]))]
    changes = [parse_price_change(e.get("detail")) for e in events
               if e.get("event") == "價格變動" and inweek(S.day_of(e.get("time")))]
    changes = [c for c in changes if c and c[0] != c[1]]
    cuts = [(a - b) / a * 100 for a, b in changes if b < a]
    on_shelf = 0
    for r in listings:
        posted = S.day_of(r["post_time"])
        if not posted or posted > end:
            continue
        gone = S.day_of(r["sold_at"]) if r["status"] == "已售出" else (
            del_day.get(r["url"]) if r["status"] == "已刪除" else None)
        if gone is None or gone > end:
            on_shelf += 1
    return new, sold, deleted, {
        "new": len(new), "sold": len(sold), "deleted": len(deleted),
        "brand_new": sum(1 for r in new if r["brand_new"]),
        "price_changes": len(changes), "price_cuts": len(cuts),
        "price_raises": len(changes) - len(cuts),
        "avg_cut_pct": round(statistics.mean(cuts), 1) if cuts else None,
        "on_shelf": on_shelf,
    }


def group_by(rows, key):
    out = {}
    for r in rows:
        out.setdefault(key(r), []).append(r)
    return out


def price_groups(new, sold, brand_new):
    """本週刊登的型號×容量價格（全新與二手分開，避免全新機拉高二手行情）。"""
    pick = [r for r in new if r["price"] and r["model"] and r["brand_new"] == brand_new]
    sold_by = group_by([r for r in sold if r["price"] and r["model"] and r["brand_new"] == brand_new],
                       lambda r: (r["model"], r["storage"]))
    out = []
    for (model, storage), items in group_by(pick, lambda r: (r["model"], r["storage"])).items():
        prices = [r["price"] for r in items]
        sold_prices = [r["price"] for r in sold_by.get((model, storage), [])]
        out.append({"model": model, "storage": storage, "listed": len(items),
                    "median_price": median_int(prices), "min_price": min(prices), "max_price": max(prices),
                    "sold": len(sold_prices), "median_sold_price": median_int(sold_prices)})
    out.sort(key=lambda g: (-g["listed"], -g["sold"], g["model"], g["storage"]))
    return out


def fast_models(sold):
    """本週售出、有售出天數的機型，依售出天數中位數由快到慢。"""
    timed = [r for r in sold if r["model"] and r["days_to_sell"] is not None]
    out = [{"model": m, "n": len(items), "median_days": round(statistics.median(r["days_to_sell"] for r in items), 1)}
           for m, items in group_by(timed, lambda r: r["model"]).items() if len(items) >= FAST_MIN]
    out.sort(key=lambda g: (g["median_days"], -g["n"], g["model"]))
    return out


def compute_issue(data_dir, start, end, now=None):
    """一期的統計快照。start／end 是 date（週日／週六）。"""
    listings, events, first_seen = load_tracked(data_dir)
    del_day = S.deleted_dates(events)
    s, e = start.isoformat(), end.isoformat()
    new, sold, _, counts = week_counts(listings, events, del_day, s, e)
    timed = [r["days_to_sell"] for r in sold if r["days_to_sell"] is not None]
    issue = {
        "week_start": s, "week_end": e,
        "generated_at": (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        **counts,
        "median_days": round(statistics.median(timed), 1) if timed else None,
        "days_samples": len(timed),
        "groups": price_groups(new, sold, brand_new=False)[:TOP_GROUPS],
        "new_groups": price_groups(new, sold, brand_new=True)[:3],
        "fast": fast_models(sold)[:5],
        "prev": None,
    }
    # 追蹤開始前的週次資料不完整，不拿來比較
    ps, pe = start - timedelta(days=7), start - timedelta(days=1)
    if first_seen and first_seen <= ps.isoformat():
        pnew, psold, _, pcounts = week_counts(listings, events, del_day, ps.isoformat(), pe.isoformat())
        issue["prev"] = {**pcounts, "medians": {
            f"{g['model']}|{g['storage']}": g["median_price"]
            for g in price_groups(pnew, psold, brand_new=False) if g["listed"] >= 2}}
    return issue


def issue_path(week_start, column_dir=COLUMN_DIR):
    return os.path.join(column_dir, f"{week_start}.json")


def load_issues(column_dir=COLUMN_DIR):
    """所有期數，最新的在最前面。"""
    if not os.path.isdir(column_dir):
        return []
    issues = []
    for name in os.listdir(column_dir):
        if name.endswith(".json"):
            with open(os.path.join(column_dir, name), encoding="utf-8") as f:
                issues.append(json.load(f))
    return sorted(issues, key=lambda i: i["week_start"], reverse=True)


def write_issue(data_dir=S.DATA_DIR, today=None, force=False, column_dir=None):
    column_dir = column_dir or os.path.join(data_dir, "column")
    start, end = week_bounds(today or datetime.now(S.TAIPEI).date())
    path = issue_path(start.isoformat(), column_dir)
    if os.path.exists(path) and not force:
        return path, False
    issue = compute_issue(data_dir, start, end)
    os.makedirs(column_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path, True


# ---------- 文字 ----------

def money(n):
    return f"${n:,}"


def short_date(d, with_year=True):
    d = date.fromisoformat(d)
    return f"{d.year}/{d.month}/{d.day}" if with_year else f"{d.month}/{d.day}"


def week_label(issue):
    s, e = issue["week_start"], issue["week_end"]
    return f"{short_date(s)}–{short_date(e, with_year=s[:4] != e[:4])}"


def name(g):
    return f"{g['model']} {g['storage']}".strip()


def pct(a, b):
    return round(a / b * 100) if b else 0


def diff_phrase(now, before, unit):
    if before is None:
        return ""
    if now == before:
        return "和上週持平"
    word = "增加" if now > before else "減少"
    tail = f"（{'+' if now > before else '−'}{pct(abs(now - before), before)}%）" if before else ""
    return f"比上週{word} {abs(now - before)} {unit}{tail}"


def heat_comment(issue):
    if not issue["new"]:
        return "本週沒有新的販售文。"
    ratio = issue["sold"] / issue["new"]
    if ratio >= 0.5:
        return "售出數超過新刊登的一半，買氣相當熱絡。"
    if ratio >= 0.3:
        return "售出約為新刊登的三到五成，買賣雙方大致平衡。"
    return "售出不到新刊登的三成，架上選擇多、賣家競爭較激烈，買方議價空間相對大。"


def article(issue):
    """依統計快照產生一期的標題、摘要與各段內文（約 600 字）。"""
    label = week_label(issue)
    groups, fast, prev = issue["groups"], issue["fast"], issue["prev"]
    top = groups[0] if groups else None
    medians = (prev or {}).get("medians", {})

    title = f"【{label}】PTT MacShop 二手 iPhone 行情週報"
    if top:
        title += f"｜{name(top)} 二手價約 {money(top['median_price'])}"
    desc = (f"{label} PTT MacShop 版二手 iPhone 價格與成交整理：本週新刊登 {issue['new']} 篇、售出 {issue['sold']} 支"
            + (f"，刊登最多的 {name(top)} 二手刊登價中位數 {money(top['median_price'])}" if top else "")
            + "，並整理賣得最快的機型與降價情況。")
    lead = (f"{label} 這一週（週日到週六），PTT MacShop 版共有 {issue['new']} 篇 iPhone 販售文、"
            f"{issue['sold']} 支被標為售出。本期週報整理最多人賣的機型與二手價、賣得最快的型號，以及賣家降價的情況，"
            "想買或想賣二手 iPhone 前，可以先用這些數字抓行情。")

    points = [f"本週新刊登 {issue['new']} 篇、售出 {issue['sold']} 支、刪文 {issue['deleted']} 篇。"]
    if top:
        points.append(f"刊登最多的是 {name(top)}（{top['listed']} 篇），二手刊登價中位數 {money(top['median_price'])}。")
    if fast:
        points.append(f"賣得最快的是 {fast[0]['model']}，售出天數中位數 {fast[0]['median_days']} 天。")
    if issue["price_cuts"]:
        points.append(f"賣家降價 {issue['price_cuts']} 次，平均降幅 {issue['avg_cut_pct']}%。")

    sections = []

    # 1. 交易熱度
    p = [f"本週 MacShop 版新增 {issue['new']} 篇 iPhone 販售文，其中全新未拆封 {issue['brand_new']} 篇"
         f"（{pct(issue['brand_new'], issue['new'])}%）。同一週偵測到 {issue['sold']} 支售出、{issue['deleted']} 篇刪文，"
         f"週六結束時仍有 {issue['on_shelf']} 篇在架上。"]
    if prev:
        p.append(f"新刊登{diff_phrase(issue['new'], prev['new'], '篇')}，售出{diff_phrase(issue['sold'], prev['sold'], '支')}。")
    p.append(heat_comment(issue))
    sections.append({"id": "heat", "h": "這週 PTT MacShop 二手 iPhone 交易熱不熱？", "body": ["".join(p)]})

    # 2. 機型與二手價
    body = []
    if top:
        parts = [f"{name(g)}（{g['listed']} 篇，中位數 {money(g['median_price'])}）" for g in groups[:3]]
        s = f"只看二手（非全新）刊登，本週最多人賣的是 {parts[0]}"
        if len(parts) > 1:
            s += "，其次是 " + "、".join(parts[1:])
        s += "。"
        moves = []
        for g in groups[:3]:
            before = medians.get(f"{g['model']}|{g['storage']}")
            if before and before != g["median_price"]:
                d = g["median_price"] - before
                moves.append(f"{name(g)} 中位數{'上漲' if d > 0 else '下跌'} {money(abs(d))}")
        if moves:
            s += "和上週相比，" + "、".join(moves) + "。"
        body.append(s)
        ng = issue["new_groups"]
        if ng:
            body.append(f"全新未拆封機則以 {name(ng[0])} 最多（{ng[0]['listed']} 篇），刊登價中位數 {money(ng[0]['median_price'])}。")
    else:
        body.append("本週沒有可以統計價格的二手刊登。")
    sections.append({"id": "models", "h": "哪些 iPhone 最多人賣？二手價多少？", "body": body, "table": bool(groups)})

    # 3. 售出速度
    if fast:
        parts = [f"{g['model']}（{g['median_days']} 天，{g['n']} 支）" for g in fast[:3]]
        s = "以本週售出、能算出售出天數的文章來看，賣得最快的是 " + "、".join(parts) + "。"
    else:
        s = f"本週能算出售出天數的機型都不到 {FAST_MIN} 支，樣本太少，暫不排名。"
    if issue["median_days"] is not None:
        s += f"全部 {issue['days_samples']} 支售出的中位數是發文後 {issue['median_days']} 天。"
    sections.append({"id": "speed", "h": "哪些機型賣得最快？", "body": [s]})

    # 4. 降價
    if issue["price_changes"]:
        s = (f"本週偵測到 {issue['price_changes']} 次改價，其中降價 {issue['price_cuts']} 次、漲價 {issue['price_raises']} 次。")
        if issue["price_cuts"]:
            s += f"降價的平均幅度是 {issue['avg_cut_pct']}%。想撿便宜的人，可以多留意剛降價的文章。"
    else:
        s = "本週沒有偵測到改價，賣家大多維持原本的標價。"
    sections.append({"id": "price-cut", "h": "賣家有在降價嗎？", "body": [s]})

    # 5. 買賣建議
    tips = []
    if top:
        tips.append(f"想買的人可以把上表的刊登價中位數當出價基準，例如 {name(top)} 低於 {money(top['median_price'])} 的文章就算不錯的價格；")
    tips.append("想賣的人可以參考同型號、同容量的中位數訂價，標價明顯高於中位數時，可能要等比較久或需要降價。"
                "電池健康度、保固與外觀也會影響價格，本週報只比較型號與容量，實際出價請再看個別文章。")
    sections.append({"id": "tips", "h": "想買或想賣二手 iPhone，可以怎麼參考？", "body": ["".join(tips)]})

    faq = []
    if top:
        faq.append({"q": f"二手 {name(top)} 現在大概多少錢？",
                    "a": f"{label} 這週 PTT MacShop 版的二手 {name(top)} 共 {top['listed']} 篇，刊登價中位數 {money(top['median_price'])}，"
                         f"價格區間 {money(top['min_price'])}～{money(top['max_price'])}。"})
    faq += [
        {"q": "週報裡的成交價是真實成交價嗎？",
         "a": "不是。PTT 沒有公開成交價，本站把偵測到「已售出」時的最後標價當作成交標價，實際成交可能再議價。"},
        {"q": "週報多久更新一次？",
         "a": "每週日晚上 8 點（台灣時間）出刊，統計剛結束的週日到週六。每天的即時動態可以看網站首頁。"},
    ]
    return {"title": title, "description": desc, "lead": lead, "points": points, "sections": sections, "faq": faq}


# ---------- 頁面 ----------

E = html.escape


def issue_url(issue):
    return f"{S.SITE_URL}column/{issue['week_start']}/"


def page_html(issue, issues, root):
    """一期的完整頁面。root 是回到網站根目錄的相對路徑（'../' 或 '../../'）。"""
    a = article(issue)
    url = issue_url(issue)
    published = issue["generated_at"][:10]
    label = week_label(issue)
    model_link = lambda m: f"{root}model.html?{urlencode({'m': m})}"  # noqa: E731

    json_ld = [
        {"@context": "https://schema.org", "@type": "Article", "headline": a["title"],
         "description": a["description"], "inLanguage": "zh-Hant-TW",
         "datePublished": published, "dateModified": published, "mainEntityOfPage": url,
         "author": {"@type": "Organization", "name": BRAND, "url": S.SITE_URL},
         "publisher": {"@type": "Organization", "name": BRAND, "url": S.SITE_URL}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(
                [(BRAND, S.SITE_URL), (COLUMN_TITLE, S.SITE_URL + "column/"), (label, url)])]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in a["faq"]]},
    ]
    ld = json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")

    out = [f"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
  <!-- Google tag (gtag.js)：Google Analytics 4，Search Console 也靠這段驗證擁有權 -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());

    gtag('config', '{GA_ID}');
  </script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{E(a['title'])}｜{BRAND}</title>
  <meta name="description" content="{E(a['description'])}">
  <link rel="canonical" href="{E(url)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{E(a['title'])}">
  <meta property="og:description" content="{E(a['description'])}">
  <meta property="og:url" content="{E(url)}">
  <meta property="og:locale" content="zh_TW">
  <link rel="stylesheet" href="{root}style.css">
  <script type="application/ld+json">{ld}</script>
</head>
<body class="column">
  <header class="top">
    <div class="wrap">
      <nav class="crumbs" aria-label="breadcrumb"><a href="{root}">{BRAND}</a> › <a href="{root}column/">{COLUMN_TITLE}</a> › <span>{E(label)}</span></nav>
    </div>
  </header>
  <main class="wrap">
    <article class="card col-article">
      <p class="issue">{E(label)}</p>
      <h1>{E(a['title'])}</h1>
      <p class="hint"><time datetime="{published}">{short_date(published)} 出刊</time></p>
      <p>{E(a['lead'])}</p>
      <section class="points">
        <h2>本期重點</h2>
        <ul>{''.join(f'<li>{E(x)}</li>' for x in a['points'])}</ul>
      </section>
      <nav class="toc" aria-label="目次">
        <p class="toc-title">目次</p>
        <ol>{''.join(f'<li><a href="#{s["id"]}">{E(s["h"])}</a></li>' for s in a['sections'])}<li><a href="#faq">常見問題</a></li><li><a href="#method">資料怎麼來</a></li></ol>
      </nav>
"""]
    for sec in a["sections"]:
        out.append(f'      <section id="{sec["id"]}">\n        <h2>{E(sec["h"])}</h2>\n')
        out += [f"        <p>{E(p)}</p>\n" for p in sec["body"]]
        if sec.get("table"):
            rows = "".join(
                f'<tr><th scope="row"><a href="{E(model_link(g["model"]))}">{E(g["model"])}</a> {E(g["storage"])}</th>'
                f'<td class="num">{g["listed"]}</td><td class="num">{money(g["median_price"])}</td>'
                f'<td class="num">{money(g["min_price"])}～{money(g["max_price"])}</td><td class="num">{g["sold"]}</td></tr>'
                for g in issue["groups"])
            out.append('        <div class="scroll"><table><caption>本週二手 iPhone 刊登價（不含全新未拆）</caption>'
                       '<thead><tr><th scope="col">型號／容量</th><th scope="col" class="num">刊登</th>'
                       '<th scope="col" class="num">刊登價中位數</th><th scope="col" class="num">價格區間</th>'
                       f'<th scope="col" class="num">本週售出</th></tr></thead><tbody>{rows}</tbody></table></div>\n')
        out.append("      </section>\n")
    faq = "".join(f"<dt>Q. {E(f['q'])}</dt><dd>A. {E(f['a'])}</dd>" for f in a["faq"])
    out.append(f"""      <section id="faq">
        <h2>常見問題</h2>
        <dl class="faq">{faq}</dl>
      </section>
      <section id="method">
        <h2>資料怎麼來</h2>
        <p class="hint">統計期間 {E(label)}（台灣時間）。資料來自 PTT MacShop 版標題含「[販售]」與 iPhone 的文章，本站每 6 小時回訪一次，依推文與內文關鍵字判斷是否售出。刊登價取文章標價，同一篇文章只算一次；售出天數是發文到售出的時間，第一次看到就已售出的文章用最後編輯時間推估。價格表不含全新未拆封機。</p>
      </section>
    </article>
""")
    if len(issues) > 1:
        current = ' aria-current="page"'
        items = "".join(
            f'<li><a href="{root}column/{i["week_start"]}/"{current if i is issue else ""}>{E(article(i)["title"])}</a></li>'
            for i in issues)
        out.append(f'    <section class="card back-issues"><h2>歷期週報</h2><ul>{items}</ul></section>\n')
    out.append(f"""  </main>
  <footer class="wrap foot">
    <p>{COLUMN_TITLE}由 <a href="{root}">{BRAND}</a> 依 PTT MacShop 版公開文章自動整理，每週日晚上 8 點（台灣時間）更新。</p>
  </footer>
</body>
</html>
""")
    return "".join(out)


def render_column(out_dir, data_dir=S.DATA_DIR):
    """輸出 column/index.html（最新一期全文）與每期的 column/<週日>/index.html；回傳各期網址。"""
    issues = load_issues(os.path.join(data_dir, "column"))
    if not issues:
        return []
    col = os.path.join(out_dir, "column")
    for issue in issues:
        os.makedirs(os.path.join(col, issue["week_start"]), exist_ok=True)
        with open(os.path.join(col, issue["week_start"], "index.html"), "w", encoding="utf-8") as f:
            f.write(page_html(issue, issues, "../../"))
    # 入口頁顯示最新一期全文，canonical 指向該期網址（和好市多專案的本月話題相同）
    with open(os.path.join(col, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_html(issues[0], issues, "../"))
    return [issue_url(i) for i in issues]


def main():
    ap = argparse.ArgumentParser(description="產生每週專欄的統計快照")
    ap.add_argument("--date", help="以這天（台灣時間）為準找上一個完整週，預設今天")
    ap.add_argument("--data", default=S.DATA_DIR, help="CSV 所在目錄（預設 data/）")
    ap.add_argument("--force", action="store_true", help="這期已存在也重新產生")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else None
    path, written = write_issue(args.data, today, args.force)
    print(f"[COLUMN] {'已寫入' if written else '已存在，略過'} {path}")


if __name__ == "__main__":
    main()
