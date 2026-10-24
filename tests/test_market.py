"""二手 iPhone 行情總覽頁的離線測試。"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import market as MK  # noqa: E402


def series(model, storage, values, brand_new=False):
    return {"model": model, "storage": storage, "brand_new": brand_new, "values": values}


class MarketTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "generated_at": "2026-10-17 12:00:00",
            "trends": {"start": "2026-10-01", "series": [
                series("iPhone 17 Pro", "256GB", [31000] * 7 + [30000]),
                series("iPhone 17 Pro", "256GB", [36000] * 8, brand_new=True),
                series("iPhone 13", "128GB", [7000] * 7 + [6500]),
                series("iPhone 18 Pro Max", "256GB", [48000] * 8),
                # 最新一天算不出來的線不列入
                series("iPhone 15", "128GB", [12000] * 7 + [None]),
            ]},
            "models": [
                {"model": "iPhone 17 Pro", "storage": "256GB", "median_days": 1.1, "days_samples": 5, "sold": 20,
                 "days_estimated": 2, "median_sold_price": 30000},
                {"model": "iPhone 13", "storage": "128GB", "median_days": 0.5, "days_samples": 2, "sold": 2},
            ],
        }

    def test_model_rank_newest_first(self):
        models = ["iPhone 13 mini", "iPhone Air", "iPhone 17", "iPhone 17 Pro Max", "iPhone 18 Pro", "iPhone SE3", "iPhone 16e"]
        self.assertEqual(sorted(models, key=MK.model_rank),
                         ["iPhone 18 Pro", "iPhone 17 Pro Max", "iPhone Air", "iPhone 17", "iPhone 16e", "iPhone 13 mini", "iPhone SE3"])

    def test_current_rows(self):
        rows, day = MK.current_rows(self.data)
        self.assertEqual(day, "2026-10-08")
        self.assertEqual([MK.label(r) for r in rows], ["iPhone 18 Pro Max 256GB", "iPhone 17 Pro 256GB", "iPhone 13 128GB"])
        pro = rows[1]
        self.assertEqual((pro["used"], pro["new"], pro["used_7"], pro["used_30"]), (30000, 36000, -3.2, None))

    def test_rankings(self):
        rows, _ = MK.current_rows(self.data)
        period, drops, cheap, fast = MK.rankings(self.data, rows)
        self.assertEqual(period, 7)  # 還沒有 30 天資料
        self.assertEqual([MK.label(r) for r in drops], ["iPhone 13 128GB", "iPhone 17 Pro 256GB"])  # 持平的不列
        self.assertEqual(cheap[0]["model"], "iPhone 13")
        self.assertEqual([m["model"] for m in fast], ["iPhone 17 Pro"])  # 售出不到 3 筆不列

    def test_page(self):
        html = MK.page_html(self.data)
        self.assertIn("<title>二手 iPhone 行情總覽【2026年10月】", html)
        self.assertIn('<link rel="canonical" href="https://macshop.crawlsnek.com/market/">', html)
        self.assertIn('href="../models/iphone-13.html?s=128GB"', html)
        self.assertIn("近 7 天跌最多的是 iPhone 13 128GB（−7.1%）", html)
        self.assertIn("G-G3GH12TQSZ", html)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
        self.assertEqual({x["@type"] for x in ld}, {"BreadcrumbList", "FAQPage"})

    def test_page_without_trends(self):
        html = MK.page_html({"generated_at": "2026-10-17 12:00:00", "trends": {"start": None, "series": []}, "models": []})
        self.assertIn("行情資料準備中", html)
        self.assertIn("【2026年10月】", html)


if __name__ == "__main__":
    unittest.main()


class DuoMarketTest(unittest.TestCase):
    def test_duo_rank_and_slug(self):
        from model_pages import model_path
        self.assertEqual(model_path('iPhone Duo'), 'models/iphone-duo.html')
        self.assertEqual(sorted(['iPhone 18 Pro Max', 'iPhone Duo', 'iPhone 19 Pro'], key=MK.model_rank),
                         ['iPhone 19 Pro', 'iPhone Duo', 'iPhone 18 Pro Max'])
