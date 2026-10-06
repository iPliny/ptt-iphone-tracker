"""網站建置腳本的離線測試。執行：python -m unittest"""
import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import build_site as S  # noqa: E402

LISTING_HEADER = ["source_url", "post_time", "title", "status", "sold_detected_at", "days_to_sell",
                  "model", "storage", "全新未拆封機", "battery_health", "price", "first_price",
                  "warranty", "notes", "model_raw", "first_seen", "last_checked", "body_hash", "days_to_sell_basis"]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def listing(url, post, status="在售", price="10000", sold_at="", days="", model="iPhone 15", storage="128GB"):
    return {"source_url": url, "post_time": post, "status": status, "sold_detected_at": sold_at,
            "days_to_sell": days, "model": model, "storage": storage, "全新未拆封機": "否",
            "price": price, "first_price": price, "last_checked": "2026-09-03 12:00:00"}


class BuildSiteTest(unittest.TestCase):
    def test_clean_listing_private_messages(self):
        for raw, expected in (("2", 2), ("0", 0), ("", None), (None, None)):
            with self.subTest(raw=raw):
                actual = S.clean_listing({"private_msg_count": raw})["pm_count"]
                self.assertEqual(actual, expected)
                if expected is not None:
                    self.assertIsInstance(actual, int)
        self.assertIsNone(S.clean_listing({})["pm_count"])

    def test_build_private_messages_from_csv(self):
        row = listing("pm", "2026-09-03 08:00:00")
        row["private_msg_count"] = "2"
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER + ["private_msg_count"], [row])
        out = os.path.join(self.dir, "pm-site")
        S.build(out, self.dir)
        with open(os.path.join(out, "data.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["listings"][0]["pm_count"], 2)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER, [
            listing("u1", "2026-09-01 10:00:00", status="已售出", price="20000",
                    sold_at="2026-09-02 09:00:00", days="0.9"),
            listing("u2", "2026-09-01 11:00:00", status="已刪除"),
            listing("u3", "2026-09-03 08:00:00", price="12000"),
            listing("u4", "2026-09-03 09:00:00", status="略過", model=""),
        ])
        write_csv(os.path.join(self.dir, "events.csv"), S_EVENT_HEADER, [
            {"time": "2026-09-02 09:00:00", "source_url": "u1", "event": "狀態變更", "detail": "在售 → 已售出"},
            {"time": "2026-09-03 07:00:00", "source_url": "u2", "event": "狀態變更", "detail": "在售 → 已刪除"},
            {"time": "2026-09-03 08:30:00", "source_url": "u3", "event": "價格變動", "detail": "13000 → 12000"},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_daily_series(self):
        data = S.build_data(self.dir, now=datetime(2026, 9, 3, 12))
        days = {d["date"]: d for d in data["days"]}
        self.assertEqual(sorted(days), ["2026-09-01", "2026-09-02", "2026-09-03"])  # 中間沒動靜的日子也要補
        self.assertEqual((days["2026-09-01"]["new"], days["2026-09-01"]["on_shelf"]), (2, 2))
        self.assertEqual((days["2026-09-02"]["sold"], days["2026-09-02"]["on_shelf"]), (1, 1))
        d3 = days["2026-09-03"]
        self.assertEqual((d3["new"], d3["deleted"], d3["price_changes"], d3["on_shelf"]), (1, 1, 1, 1))

    def test_skipped_rows_excluded(self):
        data = S.build_data(self.dir)
        self.assertEqual(data["counts"]["total"], 3)
        self.assertNotIn("u4", [r["url"] for r in data["listings"]])
        self.assertEqual(data["counts"]["已售出"], 1)

    def test_skipped_rows_events_excluded(self):
        # 改成「略過」的配件文，原本的新刊登／改價事件不再出現在網站
        path = os.path.join(self.dir, "events.csv")
        rows = S.read_csv(path) + [
            {"time": "2026-09-03 09:00:00", "source_url": "u4", "event": "新刊登", "detail": "iPhone 17 Pro Max 未知 $1200"},
            {"time": "2026-09-03 10:00:00", "source_url": "u4", "event": "價格變動", "detail": "1200 → 1000"}]
        write_csv(path, S_EVENT_HEADER, rows)
        data = S.build_data(self.dir)
        self.assertNotIn("u4", [e["url"] for e in data["events"]])
        self.assertEqual({d["date"]: d["price_changes"] for d in data["days"]}["2026-09-03"], 1)

    def test_model_stats(self):
        (m,) = S.build_data(self.dir)["models"]
        self.assertEqual((m["listed"], m["active"], m["sold"]), (3, 1, 1))
        self.assertEqual((m["median_price"], m["median_sold_price"], m["median_days"]), (12000, 20000, 0.9))

    def test_multi_items_only_in_price_stats(self):
        write_csv(os.path.join(self.dir, "multi_items.csv"),
                  ["source_url", "item_no", "post_time", "title", "model", "storage", "全新未拆封機", "price"],
                  [{"source_url": "u9", "item_no": 1, "post_time": "2026-09-03 10:00:00", "title": "x",
                    "model": "iPhone 15", "storage": "128GB", "全新未拆封機": "否", "price": "14000"},
                   {"source_url": "u9", "item_no": 2, "post_time": "2026-09-03 10:00:00", "title": "x",
                    "model": "iPhone 16", "storage": "128GB", "全新未拆封機": "否", "price": "18000"}])
        data = S.build_data(self.dir)
        m = next(m for m in data["models"] if m["model"] == "iPhone 15")
        self.assertEqual((m["listed"], m["multi"], m["active"], m["sold"]), (4, 1, 1, 1))
        self.assertEqual(m["median_price"], 13000)
        self.assertIn("iPhone 16", [t["model"] for t in data["model_totals"]])
        self.assertNotIn("u9", [r["url"] for r in data["listings"]])
        self.assertEqual(data["counts"]["total"], 3)
        self.assertEqual(sum(d["new"] for d in data["days"]), 3)

    def test_model_totals_merge_storages(self):
        """機型頁的「全部容量」要把同機型不同容量合在一起，不同機型分開。"""
        path = os.path.join(self.dir, "listings.csv")
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LISTING_HEADER)
            w.writerow(listing("u6", "2026-09-03 10:00:00", price="30000", storage="256GB"))
            w.writerow(listing("u7", "2026-09-03 11:00:00", price="50000", model="iPhone 15 Pro"))
        data = S.build_data(self.dir)
        self.assertEqual(len(data["models"]), 3)
        totals = {m["model"]: m for m in data["model_totals"]}
        self.assertEqual(sorted(totals), ["iPhone 15", "iPhone 15 Pro"])
        t = totals["iPhone 15"]
        self.assertEqual((t["listed"], t["active"], t["sold"]), (4, 2, 1))
        self.assertEqual((t["median_price"], t["min_price"], t["max_price"]), (16000, 10000, 30000))
        self.assertNotIn("storage", t)

    def test_missing_events_file(self):
        os.remove(os.path.join(self.dir, "events.csv"))
        data = S.build_data(self.dir)
        self.assertEqual(data["events"], [])
        self.assertEqual(sum(d["deleted"] for d in data["days"]), 0)  # 沒有事件就不知道刪文日

    def test_build_writes_site(self):
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        for name in S.STATIC_FILES + ["data.json", "data/listings.csv", "sitemap.xml"]:
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        with open(os.path.join(out, "data.json"), encoding="utf-8") as f:
            self.assertIn("days", json.load(f))

    def test_sitemap_lists_home_and_model_pages(self):
        from datetime import date
        from xml.etree import ElementTree
        data = {"model_totals": [{"model": "iPhone 15 Pro"}, {"model": "iPhone 16e"}]}
        root = ElementTree.fromstring(S.sitemap_xml(data, today=date(2026, 10, 4)))
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in root.findall("s:url/s:loc", ns)]
        self.assertEqual(locs, [S.SITE_URL, S.SITE_URL + "prices.html", S.SITE_URL + "model.html?m=iPhone+15+Pro",
                                S.SITE_URL + "model.html?m=iPhone+16e"])
        self.assertEqual({e.text for e in root.findall("s:url/s:lastmod", ns)}, {"2026-10-04"})

    def test_estimated_sold_date(self):
        """推估的售出天數要把售出算回發文日＋天數那天，而不是偵測到的那天。"""
        path = os.path.join(self.dir, "listings.csv")
        row = listing("u5", "2026-09-01 12:00:00", status="已售出", sold_at="2026-09-03 10:00:00", days="0.5")
        row["days_to_sell_basis"] = "推估"
        with open(path, "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=LISTING_HEADER).writerow(row)
        data = S.build_data(self.dir)
        days = {d["date"]: d for d in data["days"]}
        self.assertEqual((days["2026-09-02"]["sold"], days["2026-09-03"]["sold"]), (2, 0))
        (m,) = data["models"]
        self.assertEqual((m["days_estimated"], m["days_samples"]), (1, 2))
        u5 = next(r for r in data["listings"] if r["url"] == "u5")
        self.assertEqual((u5["sold_at"], u5["days_basis"]), ("2026-09-02 00:00:00", "推估"))

    def test_price_outliers_hidden(self):
        """和同組中位數差太多的價格（如把 2028/1/22 抓成 $2028）不公開，也不列入統計。"""
        rows = [{"url": f"u{i}", "model": "iPhone 17 Pro", "storage": "256GB", "brand_new": False, "price": p}
                for i, p in enumerate([29000, 29500, 30000, 28500, 31000, 2028, 70000])]
        rows.append({"url": "x", "model": "iPhone 8", "storage": "64GB", "brand_new": False, "price": 2000})  # 樣本太少不判斷
        S.drop_price_outliers(rows)
        self.assertEqual([r["price"] for r in rows], [29000, 29500, 30000, 28500, 31000, None, None, 2000])

    def test_implausible_price_change_hidden(self):
        bad = {"event": "價格變動", "detail": "25000 → 10000"}
        self.assertTrue(S.implausible_price_change(bad))
        self.assertFalse(S.implausible_price_change({"event": "價格變動", "detail": "25000 → 20000"}))
        self.assertFalse(S.implausible_price_change({"event": "狀態變更", "detail": "在售 → 已售出"}))
        with open(os.path.join(self.dir, "events.csv"), "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=S_EVENT_HEADER).writerow(
                {"time": "2026-09-03 09:00:00", "source_url": "u3", **bad})
        data = S.build_data(self.dir)
        self.assertEqual([e["detail"] for e in data["events"] if e["event"] == "價格變動"], ["13000 → 12000"])

    def test_outlier_report(self):
        """異常價格不公開，但寫進 data/price_outliers.csv 留紀錄，網站輸出不含這個檔。"""
        path = os.path.join(self.dir, "listings.csv")
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LISTING_HEADER)
            for i, p in enumerate(["10000", "10500", "11000", "9500", "2028"]):
                w.writerow(listing(f"o{i}", "2026-09-03 10:00:00", price=p))
        with open(os.path.join(self.dir, "events.csv"), "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=S_EVENT_HEADER).writerow(
                {"time": "2026-09-03 09:00:00", "source_url": "u3", "event": "價格變動", "detail": "25000 → 10000"})
        self.assertEqual(S.write_outlier_report(self.dir), 2)
        rows = S.read_csv(os.path.join(self.dir, S.OUTLIER_REPORT))
        self.assertEqual([(r["kind"], r["source_url"], r["price"], r["detail"]) for r in rows],
                         [("刊登價", "o4", "2028", ""), ("改價", "u3", "", "25000 → 10000")])
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        self.assertFalse(os.path.exists(os.path.join(out, "data", S.OUTLIER_REPORT)))

    def test_apple_prices(self):
        """機型頁的原廠資訊：在售給連結與現行價，停售給最終官方價，沒追蹤到的機型與空白價格不帶。"""
        path = os.path.join(self.dir, "apple.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"checked_at": "2026-10-05", "on_sale": {
                "iPhone 17": {"url": "https://www.apple.com/tw/shop/buy-iphone/iphone-17", "prices": {"256GB": 32900}},
                "iPhone 19": {"url": "https://www.apple.com/tw/shop/buy-iphone/iphone-19", "prices": {"256GB": 1}}},
                "discontinued": {
                "iPhone 15": {"discontinued": "2025-09", "prices": {"128GB": 22900, "256GB": None},
                              "sources": ["https://example.com/a"]},
                "iPhone 13": {"discontinued": "2025-02", "prices": {"128GB": None}}}}, f)
        got = S.apple_prices(["iPhone 17", "iPhone 15", "iPhone 13", "iPhone 12"], path)
        self.assertEqual(sorted(got), ["iPhone 15", "iPhone 17"])
        self.assertEqual(got["iPhone 17"], {"buy_url": "https://www.apple.com/tw/shop/buy-iphone/iphone-17",
                                            "prices": {"256GB": 32900}, "checked_at": "2026-10-05"})
        self.assertEqual(got["iPhone 15"], {"prices": {"128GB": 22900}, "discontinued": "2025-09",
                                            "sources": ["https://example.com/a"]})

    def test_apple_prices_file(self):
        """repo 內的價格檔：在售連結都在 Apple 台灣商店，價格是正整數或 null，來源是 https。"""
        with open(S.APPLE_PRICES, encoding="utf-8") as f:
            src = json.load(f)
        self.assertRegex(src["checked_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertFalse(set(src["on_sale"]) & set(src["discontinued"]))
        for model, info in list(src["on_sale"].items()) + list(src["discontinued"].items()):
            if "url" in info:
                self.assertTrue(info["url"].startswith("https://www.apple.com/tw/shop/buy-iphone/"), model)
            for u in info.get("sources", []):
                self.assertTrue(u.startswith("https://"), model)
            for cap, price in info["prices"].items():
                self.assertRegex(cap, r"^\d+(GB|TB)$")
                if price is not None:
                    self.assertIs(type(price), int)
                    self.assertGreater(price, 5000)

    def test_real_data_builds(self):
        """repo 內現有的 data/ 也要能建置成功。"""
        data = S.build_data()
        self.assertGreater(data["counts"]["total"], 0)


S_EVENT_HEADER = ["time", "source_url", "event", "detail"]

if __name__ == "__main__":
    unittest.main()
