"""Blogger 週報轉貼的離線測試。執行：python -m unittest"""
import json
import os
import sys
import tempfile
import unittest
from xml.etree import ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import blog as B  # noqa: E402
import build_site as S  # noqa: E402
from tests.test_site import LISTING_HEADER, S_EVENT_HEADER, write_csv  # noqa: E402

FEED = os.path.join(os.path.dirname(__file__), "fixtures", "blog", "feed.atom")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class BlogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.posts, self.oldest = B.parse_feed(read(FEED))

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_feed_keeps_iphone_weekly_only(self):
        self.assertEqual([p["id"] for p in self.posts], ["2026-10-04", "2026-10-11"])  # 台灣時間的發布日
        self.assertEqual(self.oldest, "2026-10-04")
        p = self.posts[1]
        self.assertEqual(p["url"], "https://tcssh.blogspot.com/2026/10/iphone318-propro20261011.html")
        self.assertEqual(p["published"], "2026-10-11T19:04:02+08:00")
        self.assertIn("iPhone 18 Pro", p["labels"])
        self.assertEqual(p["description"], "這週的 MacShop iPhone 刊登，一邊很整齊。")

    def test_clean_html_strips_scripts_attrs_and_rewrites_site_links(self):
        body = self.posts[1]["html"]
        for bad in ("<script", "alert", "style=", "onclick", "javascript:"):
            self.assertNotIn(bad, body)
        self.assertIn('<a href="{{ROOT}}">iPhone 二手交易追蹤網站</a>', body)  # 舊 github.io 網址改站內
        self.assertIn('<a href="{{ROOT}}model.html?m=iPhone%2018%20Pro">機型頁</a>', body)
        self.assertIn("壞連結", body)  # 連結拿掉，文字留著
        self.assertIn('<a href="https://github.com/iPliny/ptt-iphone-tracker/tree/abc/data" rel="noopener">', body)
        self.assertIn("<h2>18 Pro：價格已經排好隊</h2>", body)
        self.assertEqual(B.clean_html("<p>a<strong>b</p>"), "<p>a<strong>b</strong></p>")

    def test_export_file_uses_filename_and_skips_drafts(self):
        export = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:blogger="http://schemas.google.com/blogger/2018">
        <entry><blogger:type>POST</blogger:type><blogger:status>LIVE</blogger:status>
          <title>iPhone二手週報#1：首期</title><content type="html">&lt;p&gt;一&lt;/p&gt;</content>
          <published>2026-10-02T07:54:21.095Z</published><blogger:filename>/2026/10/a.html</blogger:filename></entry>
        <entry><blogger:type>POST</blogger:type><blogger:status>DRAFT</blogger:status>
          <title>iPhone二手週報#9：草稿</title><content type="html">&lt;p&gt;草&lt;/p&gt;</content>
          <published>2026-10-05T07:54:21Z</published><blogger:filename>/2026/10/b.html</blogger:filename></entry></feed>"""
        posts, _ = B.parse_feed(export)
        self.assertEqual([(p["id"], p["url"]) for p in posts], [("2026-10-02", "https://tcssh.blogspot.com/2026/10/a.html")])

    def test_sync_writes_changes_and_prunes_only_within_feed_range(self):
        d = os.path.join(self.dir, "blog")
        os.makedirs(d)
        for old in ("2026-09-20", "2026-10-07"):  # 前者超出 feed 範圍要保留，後者已從 Blogger 撤下
            with open(os.path.join(d, old + ".json"), "w", encoding="utf-8") as f:
                json.dump({"id": old}, f)
        changed, removed = B.sync(self.posts, d, prune_since=self.oldest)
        self.assertEqual(changed, ["2026-10-04", "2026-10-11"])
        self.assertEqual(removed, ["2026-10-07"])
        self.assertEqual(B.sync(self.posts, d, prune_since=self.oldest), ([], []))
        self.assertEqual(sorted(os.listdir(d)), ["2026-09-20.json", "2026-10-04.json", "2026-10-11.json"])

    def test_build_renders_weekly_pages_with_canonical_to_blogger(self):
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER, [])
        write_csv(os.path.join(self.dir, "events.csv"), S_EVENT_HEADER, [])
        B.sync(self.posts, os.path.join(self.dir, "blog"))
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        page = read(os.path.join(out, "weekly", "2026-10-11", "index.html"))
        index = read(os.path.join(out, "weekly", "index.html"))
        self.assertIn('<link rel="canonical" href="https://tcssh.blogspot.com/2026/10/iphone318-propro20261011.html">', page)
        self.assertIn('<a href="../../">iPhone 二手交易追蹤網站</a>', page)
        self.assertIn('href="../../style.css"', page)
        self.assertLess(page.index("gtag/js?id=G-G3GH12TQSZ"), page.index("<title>"))
        self.assertIn('href="../../weekly/2026-10-04/"', page)
        self.assertIn(f'<link rel="canonical" href="{S.SITE_URL}weekly/">', index)
        self.assertLess(index.index("#3"), index.index("#2"))  # 新的在前
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in ElementTree.parse(os.path.join(out, "sitemap.xml")).findall("s:url/s:loc", ns)]
        self.assertIn(S.SITE_URL + "weekly/", locs)
        self.assertFalse(any("weekly/2026" in u for u in locs))  # 各篇 canonical 在 Blogger


    def draft(self, **kw):
        d = {"id": "2026-10-18", "title": "iPhone二手週報#4：測試", "description": "本週 iPhone 17 Pro 二手刊登價整理。",
             "labels": ["iPhone", "二手市場", "週報", "iPhone 17 Pro", "iPhone二手價格"],
             "html": "<p>" + "內文" * 200 + '<a href="https://macshop.crawlsnek.com/model.html?m=iPhone%2017%20Pro">機型頁</a></p><script>x</script>',
             "period": "2026/10/11–10/17", "commit": "abc"}
        d.update(kw)
        return d

    def test_publish_validates_and_keeps_first_publish_time(self):
        d = os.path.join(self.dir, "weekly")
        for bad in (self.draft(description="字" * 151), self.draft(id="10/18"), self.draft(id="2026-13-40"),
                    self.draft(labels=["iPhone", "二手市場", "週報", "iPhone 17 Pro"]),
                    self.draft(labels=["iPhone", "二手市場", "iPhone 17 Pro", "iPhone二手價格", "17 Pro"]), self.draft(html="<p>太短 <a href='https://macshop.crawlsnek.com/'>站</a></p>"),
                    self.draft(html="<p>" + "內文" * 200 + "</p>"), self.draft(title=" ")):
            with self.assertRaises(ValueError):
                B.publish(bad, d)
        self.assertFalse(os.path.exists(d))
        from datetime import datetime
        t1, t2 = (datetime(2026, 10, 18, h, tzinfo=B.TAIPEI) for h in (20, 22))
        path = B.publish(self.draft(), d, now=t1)
        B.publish(self.draft(title="iPhone二手週報#4：改標題"), d, now=t2)
        post = json.loads(read(path))
        self.assertEqual(post["published"], "2026-10-18T20:00:00+08:00")
        self.assertEqual(post["title"], "iPhone二手週報#4：改標題")
        self.assertNotIn("<script", post["html"])

    def test_site_posts_canonical_to_site_and_listed_in_sitemap(self):
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER, [])
        write_csv(os.path.join(self.dir, "events.csv"), S_EVENT_HEADER, [])
        B.sync(self.posts, os.path.join(self.dir, "blog"))
        B.publish(self.draft(), os.path.join(self.dir, "weekly"))
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        page = read(os.path.join(out, "weekly", "2026-10-18", "index.html"))
        url = f"{S.SITE_URL}weekly/2026-10-18/"
        self.assertIn(f'<link rel="canonical" href="{url}">', page)
        self.assertIn('"@type": "Article"', page)
        self.assertNotIn("轉貼自", page)
        self.assertIn('href="../../model.html?m=iPhone%2017%20Pro"', page)
        self.assertIn("weekly/2026-10-11/", page)  # 歷期列表含 Blogger 轉貼
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in ElementTree.parse(os.path.join(out, "sitemap.xml")).findall("s:url/s:loc", ns)]
        self.assertIn(url, locs)
        self.assertNotIn(f"{S.SITE_URL}weekly/2026-10-11/", locs)


if __name__ == "__main__":
    unittest.main()
