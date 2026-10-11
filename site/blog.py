"""Blogger「iPhone二手週報」轉貼：把部落格上公開的週報同步到網站 weekly/。

原文在 POYU 的 Blogger（tcssh.blogspot.com），由 ChatGPT 排程撰寫、Email 投稿發布。
這裡只讀公開 Atom feed，不需要帳號或 API key：
    python site/blog.py                 # 抓公開 feed，寫入 data/blog/<發布日>.json
    python site/blog.py --feed 匯出.atom  # 改讀 Blogger 匯出檔或存下來的 feed
每篇存成 data/blog/<台灣時間發布日>.json；Blogger 上改過就覆寫，從 feed 消失（轉草稿／刪除）就移除。
建置網站時 build_site.py 呼叫 render_blog，輸出 weekly/ 與 weekly/<發布日>/，canonical 指向 Blogger 原文。
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote, urlparse
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import build_site as S

BLOG_URL = "https://tcssh.blogspot.com/"
# 同時有「週報」與「iPhone」兩個標籤的文章（好市多週報不會進來）
FEED_URL = BLOG_URL + "feeds/posts/default/-/" + quote("週報") + "/iPhone?max-results=150"
TITLE_PREFIX = "iPhone二手週報"
BLOG_DIR = os.path.join(S.DATA_DIR, "blog")
SECTION = "iPhone 二手週報"
BRAND = "PTT MacShop交易觀測"
GA_ID = "G-G3GH12TQSZ"
TAIPEI = ZoneInfo("Asia/Taipei")
ATOM = "{http://www.w3.org/2005/Atom}"
BLOGGER = "{http://schemas.google.com/blogger/2018}"
# 指向本站的連結（含搬家前的 github.io 網址）改成站內相對路徑
SITE_HOSTS = {("ipliny.github.io", "/ptt-iphone-tracker/"), ("macshop.crawlsnek.com", "/")}


# ---------- 讀 feed ----------

def parse_feed(text):
    """Atom（公開 feed 或 Blogger 匯出檔）→ (標題以「iPhone二手週報」開頭的公開文章, feed 裡最舊一篇的發布日)。"""
    root = ElementTree.fromstring(text)
    posts, oldest = [], None
    for e in root.iter(ATOM + "entry"):
        if e.findtext(ATOM + "published"):
            day = to_taipei(e.findtext(ATOM + "published")).date().isoformat()
            oldest = min(oldest or day, day)
        title = (e.findtext(ATOM + "title") or "").strip()
        content = e.findtext(ATOM + "content") or ""
        if not title.startswith(TITLE_PREFIX) or not content.strip():
            continue
        kind, status = e.findtext(BLOGGER + "type"), e.findtext(BLOGGER + "status")
        if (kind and kind != "POST") or (status and status != "LIVE"):  # 匯出檔才有這兩欄
            continue
        url = next((l.get("href") for l in e.findall(ATOM + "link") if l.get("rel") == "alternate"), None)
        if not url and e.findtext(BLOGGER + "filename"):
            url = BLOG_URL.rstrip("/") + e.findtext(BLOGGER + "filename")
        published = to_taipei(e.findtext(ATOM + "published"))
        updated = e.findtext(ATOM + "updated") or ""
        labels = [c.get("term") for c in e.findall(ATOM + "category") if c.get("term") and "#" not in c.get("term")]
        body = clean_html(content)
        posts.append({"id": published.date().isoformat(), "title": title, "url": url,
                      "published": published.isoformat(timespec="seconds"), "updated": updated,
                      "labels": labels, "description": summary(body), "html": body})
    posts.sort(key=lambda p: p["published"])
    by_id = {}
    for p in posts:  # 同一天發兩篇時只留較晚那篇
        by_id[p["id"]] = p
    return list(by_id.values()), oldest


def to_taipei(ts):
    return datetime.fromisoformat(ts.strip().replace("Z", "+00:00")).astimezone(TAIPEI)


def fetch_feed(url=FEED_URL):
    req = urllib.request.Request(url, headers={"User-Agent": "ptt-iphone-tracker blog sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return r.read().decode("utf-8")


# ---------- 清理內文 ----------

ALLOWED = {"p", "h2", "h3", "strong", "b", "em", "i", "a", "small", "ul", "ol", "li", "br",
           "table", "thead", "tbody", "tr", "th", "td", "blockquote"}
VOID = {"br"}


def local_href(href):
    """本站網址改成相對於網站根目錄的路徑（之後再加 root）；其他網址原樣；非 http(s) 回傳 None。"""
    u = urlparse(href or "")
    if u.scheme not in ("http", "https"):
        return None
    for host, prefix in SITE_HOSTS:
        if u.netloc == host and (u.path + "/").startswith(prefix):
            rest = u.path[len(prefix):] if len(u.path) >= len(prefix) else ""
            return "{{ROOT}}" + rest + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")
    return href


class _Cleaner(HTMLParser):
    """只留文章排版需要的標籤；屬性只留 a 的 http(s) href，script／style 整段丟掉。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.open = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        if tag == "a":
            href = local_href(dict(attrs).get("href"))
            if href is None:
                self.open.append(None)
                return
            ext = "" if href.startswith("{{ROOT}}") else ' rel="noopener"'
            self.out.append(f'<a href="{html.escape(href)}"{ext}>')
        else:
            self.out.append(f"<{tag}>")
        if tag not in VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in ALLOWED or tag in VOID:
            return
        if tag in [t or "a" for t in self.open]:
            while self.open:
                t = self.open.pop()
                if t:
                    self.out.append(f"</{t}>")
                if (t or "a") == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self):
        return "".join(self.out) + "".join(f"</{t}>" for t in reversed(self.open) if t)


def clean_html(raw):
    c = _Cleaner()
    c.feed(raw)
    c.close()
    return c.result().strip()


def summary(body, limit=120):
    """搜尋說明：第一段純文字，最多 limit 字。"""
    m = re.search(r"<p>(.*?)</p>", body, re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1) if m else body)).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ---------- 存檔 ----------

def sync(posts, blog_dir=BLOG_DIR, prune_since=None):
    """寫入有變動的文章；給 prune_since（feed 涵蓋的最早日期）時，把這天之後、feed 裡卻沒有的文章刪掉
    （Blogger 上轉草稿或刪除）。更早的文章可能只是超出 feed 筆數，保留。回傳 (新增或更新, 移除) 的 id。"""
    os.makedirs(blog_dir, exist_ok=True)
    changed = []
    for p in posts:
        path = os.path.join(blog_dir, p["id"] + ".json")
        text = json.dumps(p, ensure_ascii=False, indent=1) + "\n"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        changed.append(p["id"])
    removed = []
    if prune_since:
        keep = {p["id"] for p in posts}
        for name in sorted(os.listdir(blog_dir)):
            if name.endswith(".json") and name[:-5] not in keep and name[:-5] >= prune_since:
                os.remove(os.path.join(blog_dir, name))
                removed.append(name[:-5])
    return changed, removed


def load_posts(blog_dir=BLOG_DIR):
    if not os.path.isdir(blog_dir):
        return []
    posts = []
    for name in sorted(os.listdir(blog_dir)):
        if name.endswith(".json"):
            with open(os.path.join(blog_dir, name), encoding="utf-8") as f:
                posts.append(json.load(f))
    return sorted(posts, key=lambda p: p["published"], reverse=True)


# ---------- 頁面 ----------

E = html.escape


def head(title, description, canonical, root, og_type="article"):
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
  <link rel="canonical" href="{E(canonical)}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:title" content="{E(title)}">
  <meta property="og:description" content="{E(description)}">
  <meta property="og:url" content="{E(canonical)}">
  <meta property="og:locale" content="zh_TW">
  <link rel="stylesheet" href="{root}style.css">
</head>
<body class="column">
"""


FOOT = f"""  <footer class="wrap foot">
    <p>{SECTION}原文發表於 <a href="{BLOG_URL}" rel="noopener">老鍋見聞錄</a>，本站轉貼全文；統計資料來自 <a href="{{root}}">{BRAND}</a>。</p>
    <p class="by-crawlsnek">由 <a href="https://crawlsnek.com/">CrawlSnek</a> 提供</p>
  </footer>
</body>
</html>
"""


def short_date(iso):
    d = datetime.fromisoformat(iso)
    return f"{d.year}/{d.month}/{d.day}"


def post_html(post, posts, root):
    body = post["html"].replace("{{ROOT}}", root)
    current = ' aria-current="page"'
    others = "".join(
        f'<li><a href="{root}weekly/{p["id"]}/"{current if p is post else ""}>{E(p["title"])}</a></li>'
        for p in posts)
    # 原文在 Blogger，canonical 指回原文，避免兩邊搶同一篇的搜尋排名
    return (head(post["title"], post["description"], post["url"], root) + f"""  <header class="top">
    <div class="wrap">
      <nav class="crumbs" aria-label="breadcrumb"><a href="{root}">{BRAND}</a> › <a href="{root}weekly/">{SECTION}</a> › <span>{E(short_date(post["published"]))}</span></nav>
    </div>
  </header>
  <main class="wrap">
    <article class="card col-article blog-post">
      <h1>{E(post["title"])}</h1>
      <p class="hint"><time datetime="{post["published"]}">{short_date(post["published"])} 發表</time>・轉貼自 <a href="{E(post["url"])}" rel="noopener">Blogger 原文</a></p>
      {body}
    </article>
    <section class="card back-issues"><h2>歷期{SECTION}</h2><ul>{others}</ul>
      <p class="hint">另有每週日自動產生的 <a href="{root}column/">二手 iPhone 行情週報</a>（統計表與常見問題）。</p></section>
  </main>
""" + FOOT.replace("{root}", root))


def index_html(posts, root):
    items = "".join(
        f'<li><a href="{root}weekly/{p["id"]}/">{E(p["title"])}</a> <span class="hint">{short_date(p["published"])}</span>'
        f'<br><span class="hint">{E(p["description"])}</span></li>' for p in posts)
    desc = "PTT MacShop iPhone 二手刊登價、改價與售出狀態的每週觀察專文，資料來自 PTT MacShop交易觀測。"
    return (head(SECTION, desc, f"{S.SITE_URL}weekly/", root, og_type="website") + f"""  <header class="top">
    <div class="wrap">
      <nav class="crumbs" aria-label="breadcrumb"><a href="{root}">{BRAND}</a> › <span>{SECTION}</span></nav>
    </div>
  </header>
  <main class="wrap">
    <section class="card back-issues blog-index">
      <h1>{SECTION}</h1>
      <p class="hint">每週一篇的 iPhone 二手市場觀察，原文發表於 Blogger，這裡轉貼全文。</p>
      <ul>{items}</ul>
    </section>
  </main>
""" + FOOT.replace("{root}", root))


def render_blog(out_dir, data_dir=S.DATA_DIR):
    """輸出 weekly/index.html 與 weekly/<發布日>/index.html；回傳要列入 sitemap 的網址（只有入口頁）。"""
    posts = load_posts(os.path.join(data_dir, "blog"))
    if not posts:
        return []
    base = os.path.join(out_dir, "weekly")
    for p in posts:
        os.makedirs(os.path.join(base, p["id"]), exist_ok=True)
        with open(os.path.join(base, p["id"], "index.html"), "w", encoding="utf-8") as f:
            f.write(post_html(p, posts, "../../"))
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html(posts, "../"))
    return [f"{S.SITE_URL}weekly/"]  # 各篇 canonical 在 Blogger，不列入本站 sitemap


def main():
    ap = argparse.ArgumentParser(description="把 Blogger 上的 iPhone二手週報同步到 data/blog/")
    ap.add_argument("--feed", help="改讀本機的 Atom 檔（Blogger 匯出或存下來的 feed），不連網、不刪舊檔")
    ap.add_argument("--data", default=S.DATA_DIR, help="資料目錄（預設 data/）")
    args = ap.parse_args()
    if args.feed:
        with open(args.feed, encoding="utf-8") as f:
            text = f.read()
    else:
        try:
            text = fetch_feed()
        except Exception as e:  # 抓不到就不動舊檔
            print(f"[BLOG] 抓取失敗，不更新：{e}", file=sys.stderr)
            sys.exit(1)
    posts, oldest = parse_feed(text)
    # 讀本機檔、或 feed 一篇都沒有（多半是暫時異常）時不刪舊檔
    prune_since = oldest if posts and not args.feed else None
    changed, removed = sync(posts, os.path.join(args.data, "blog"), prune_since)
    print(f"[BLOG] feed {len(posts)} 篇；新增或更新 {changed or '無'}；移除 {removed or '無'}")


if __name__ == "__main__":
    main()
