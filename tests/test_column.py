"""每週專欄的離線測試。執行：python -m unittest"""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date
from xml.etree import ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import build_site as S  # noqa: E402
import column as C  # noqa: E402
from tests.test_site import LISTING_HEADER, S_EVENT_HEADER, write_csv  # noqa: E402


def row(url, post, status="在售", price="20000", model="iPhone 15", storage="128GB", new="否",
        sold_at="", days="", first_seen="2026-09-01 00:00:00", battery=""):
    return {"source_url": url, "post_time": post, "status": status, "sold_detected_at": sold_at,
            "days_to_sell": days, "model": model, "storage": storage, "全新未拆封機": new,
            "price": price, "first_price": price, "first_seen": first_seen, "battery_health": battery, "last_checked": "2026-10-04 12:00:00"}


class ColumnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER, [
            # 上一週（9/20–9/26）
            row("p1", "2026-09-21 10:00:00", price="19000"),
            row("p2", "2026-09-22 10:00:00", price="19000"),
            # 本週（9/27–10/3）
            row("a1", "2026-09-27 10:00:00", price="20000", status="已售出", sold_at="2026-09-28 10:00:00", days="1.0", battery="95"),
            row("a2", "2026-09-28 10:00:00", price="21000", status="已售出", sold_at="2026-09-30 10:00:00", days="2.0"),
            row("a3", "2026-09-29 10:00:00", price="22000", battery="85"),
            row("b1", "2026-09-30 10:00:00", price="30000", model="iPhone 15 Pro", status="已刪除"),
            row("n1", "2026-10-01 10:00:00", price="50000", model="iPhone 17 Pro", storage="256GB", new="是"),
            # 下一週，不算
            row("x1", "2026-10-04 10:00:00", price="99999"),
        ])
        write_csv(os.path.join(self.dir, "events.csv"), S_EVENT_HEADER, [
            {"time": "2026-10-01 09:00:00", "source_url": "b1", "event": "狀態變更", "detail": "在售 → 已刪除"},
            {"time": "2026-10-02 09:00:00", "source_url": "a3", "event": "價格變動", "detail": "24000 → 22000"},
            {"time": "2026-10-02 10:00:00", "source_url": "a3", "event": "價格變動", "detail": "22000 → 22500"},
            {"time": "2026-10-05 09:00:00", "source_url": "x1", "event": "價格變動", "detail": "100000 → 99999"},
        ])
        self.start, self.end = date(2026, 9, 27), date(2026, 10, 3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_week_bounds_sunday_to_saturday(self):
        for today in (date(2026, 10, 4), date(2026, 10, 7), date(2026, 10, 10)):
            with self.subTest(today=today):
                self.assertEqual(C.week_bounds(today), (date(2026, 9, 27), date(2026, 10, 3)))
        self.assertEqual(C.week_bounds(date(2026, 10, 3)), (date(2026, 9, 20), date(2026, 9, 26)))

    def test_parse_price_change(self):
        self.assertEqual(C.parse_price_change("42000 → 39,500"), (42000, 39500))
        self.assertIsNone(C.parse_price_change("在售 → 已售出"))
        self.assertIsNone(C.parse_price_change(""))
        # 2026/9/27 那期的 iPhone 14 Pro 25000 → 10000 是價格抓錯，不算降價
        self.assertIsNone(C.parse_price_change("25000 → 10000"))
        self.assertIsNone(C.parse_price_change("9000 → 19000"))
        self.assertEqual(C.parse_price_change("20000 → 10000"), (20000, 10000))

    def test_compute_issue_counts(self):
        i = C.compute_issue(self.dir, self.start, self.end)
        self.assertEqual((i["new"], i["sold"], i["deleted"], i["brand_new"]), (5, 2, 1, 1))
        self.assertEqual((i["price_changes"], i["price_cuts"], i["price_raises"]), (2, 1, 1))
        self.assertEqual(i["avg_cut_pct"], 8.3)
        self.assertEqual(i["on_shelf"], 4)  # p1、p2、a3、n1
        self.assertEqual((i["median_days"], i["days_samples"]), (1.5, 2))

    def test_groups_exclude_brand_new(self):
        i = C.compute_issue(self.dir, self.start, self.end)
        top = i["groups"][0]
        self.assertEqual((top["model"], top["listed"], top["median_price"], top["sold"]), ("iPhone 15", 3, 21000, 2))
        self.assertNotIn("iPhone 17 Pro", [g["model"] for g in i["groups"]])
        self.assertEqual(i["new_groups"][0]["model"], "iPhone 17 Pro")
        self.assertEqual(i["fast"], [{"model": "iPhone 15", "n": 2, "median_days": 1.5}])

    def test_previous_week_only_when_tracked(self):
        i = C.compute_issue(self.dir, self.start, self.end)
        self.assertEqual(i["prev"]["new"], 2)
        self.assertEqual(i["prev"]["medians"], {"iPhone 15|128GB": 19000})
        self.assertIn("iPhone 15 128GB 中位數上漲 $2,000", C.article(i)["sections"][1]["body"][0])
        # 追蹤從本週才開始，上週資料不完整，不比較
        later = C.compute_issue(self.dir, date(2026, 8, 30), date(2026, 9, 5))
        self.assertIsNone(later["prev"])

    def test_article_length_and_keywords(self):
        a = C.article(C.compute_issue(self.dir, self.start, self.end))
        self.assertIn("PTT MacShop", a["title"])
        self.assertIn("二手 iPhone", a["title"])
        self.assertIn("2026/9/27–10/3", a["title"])
        self.assertIn("battery", [s["id"] for s in a["sections"]])
        self.assertIn("從 $24,000 降到 $22,000", a["sections"][-2]["body"][0])
        text = a["lead"] + "".join(p for s in a["sections"] for p in s["body"])
        self.assertTrue(600 <= len(text) <= C.MAX_CHARS, len(text))

    def test_article_max_length(self):
        """每段都寫滿、型號名稱很長時，內文也不超過 1000 字。"""
        g = {"model": "iPhone 17 Pro Max", "storage": "1TB", "listed": 99, "median_price": 123456,
             "min_price": 100000, "max_price": 150000, "sold": 99, "median_sold_price": 120000}
        issue = {"week_start": "2026-12-27", "week_end": "2027-01-02", "generated_at": "2027-01-03 20:00:00",
                 "new": 999, "sold": 999, "deleted": 999, "brand_new": 999, "price_changes": 999,
                 "price_cuts": 999, "price_raises": 999, "avg_cut_pct": 12.3, "on_shelf": 999,
                 "median_days": 12.5, "days_samples": 999, "groups": [g] * 8, "new_groups": [g] * 3,
                 "fast": [{"model": "iPhone 17 Pro Max", "n": 99, "median_days": 12.5}] * 5,
                 "battery_listed": 88, "battery_sold": 91,
                 "biggest_cut": {"model": "iPhone 17 Pro Max", "storage": "1TB", "from": 150000, "to": 100000},
                 "prev": {"new": 1, "sold": 1, "medians": {"iPhone 17 Pro Max|1TB": 100000}}}
        a = C.article(issue)
        self.assertLessEqual(C.trim(a["lead"], a["sections"]), C.MAX_CHARS)
        self.assertNotIn("battery", [s["id"] for s in a["sections"]])  # 先拿掉補充段落

    def test_write_issue_once(self):
        path, written = C.write_issue(self.dir, today=date(2026, 10, 4))
        self.assertTrue(written)
        self.assertTrue(path.endswith(os.path.join("column", "2026-09-27.json")))
        self.assertFalse(C.write_issue(self.dir, today=date(2026, 10, 4))[1])
        self.assertTrue(C.write_issue(self.dir, today=date(2026, 10, 4), force=True)[1])

    def test_build_renders_column_pages(self):
        C.write_issue(self.dir, today=date(2026, 9, 27))
        C.write_issue(self.dir, today=date(2026, 10, 4))
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        with open(os.path.join(out, "column", "index.html"), encoding="utf-8") as f:
            index = f.read()
        with open(os.path.join(out, "column", "2026-09-20", "index.html"), encoding="utf-8") as f:
            older = f.read()
        # 入口頁是最新一期全文，canonical 指向該期網址
        self.assertIn(f'<link rel="canonical" href="{S.SITE_URL}column/2026-09-27/">', index)
        self.assertIn('href="../style.css"', index)
        self.assertIn('href="../../style.css"', older)
        self.assertLess(index.index("gtag/js?id=G-G3GH12TQSZ"), index.index("<title>"))
        self.assertIn("歷期週報", index)
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', index, re.S).group(1)
        self.assertEqual([x["@type"] for x in json.loads(ld)], ["Article", "BreadcrumbList", "FAQPage"])

        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in ElementTree.parse(os.path.join(out, "sitemap.xml")).findall("s:url/s:loc", ns)]
        self.assertEqual(locs[-3:], [S.SITE_URL + "column/", S.SITE_URL + "column/2026-09-27/",
                                     S.SITE_URL + "column/2026-09-20/"])

    def test_no_issues_no_column(self):
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        self.assertFalse(os.path.exists(os.path.join(out, "column")))

    def test_empty_week_renders(self):
        i = C.compute_issue(self.dir, date(2026, 11, 1), date(2026, 11, 7))
        self.assertEqual((i["new"], i["groups"]), (0, []))
        self.assertIn("<h1>", C.page_html(i, [i], "../"))

    def test_real_data_renders(self):
        """repo 內現有的 data/ 也要能產生一期並輸出頁面。"""
        i = C.compute_issue(S.DATA_DIR, date(2026, 9, 27), date(2026, 10, 3))
        self.assertIn("二手 iPhone", C.page_html(i, [i], "../"))


if __name__ == "__main__":
    unittest.main()
