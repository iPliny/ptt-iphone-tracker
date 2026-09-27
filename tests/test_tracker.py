"""離線測試：用假的 PTT 頁面與假的 LLM，不需網路也不需 Ollama。執行：python -m unittest"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tracker as T  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_model(self):
        cases = {
            "iPhone 17 pro max": "iPhone 17 Pro Max", "iphone 11 pro": "iPhone 11 Pro",
            "iPhone Air": "iPhone Air", "iPhone 14 plus": "iPhone 14 Plus",
            "IPHONE15PM": "iPhone 15 Pro Max", "i14 pro max": "iPhone 14 Pro Max",
            "iPhone SE 3": "iPhone SE3", "iphone 16e": "iPhone 16e", "iPhone XS Max": "iPhone XS Max",
            "iphone xr": "iPhone XR", "iPhone 13 mini": "iPhone 13 mini", "15p 256": "iPhone 15 Pro",
        }
        for raw, want in cases.items():
            self.assertEqual(T.normalize_model(raw), want, raw)

    def test_storage(self):
        self.assertEqual(T.normalize_storage("1T"), "1TB")
        self.assertEqual(T.normalize_storage("256 G"), "256GB")


class StatusTest(unittest.TestCase):
    def check(self, title, body, want):
        self.assertEqual(T.detect_status(title, body), want, (title, body))

    def test_sold(self):
        self.check("[販售] 台北 iPhone 15 256 已售出", "", T.STATUS_SOLD)
        self.check("[販售] x", "已售出\n\n[物品型號]: ...", T.STATUS_SOLD)
        self.check("[販售] x", "iPhone 15 已售出 謝謝大家", T.STATUS_SOLD)
        self.check("[販售] x", "已賣出，感謝", T.STATUS_SOLD)

    def test_rule_text_not_sold(self):
        self.check("[販售] x", "[交易價格]: 20000 售出後修改價格至不可視者水桶並劣退", T.STATUS_ACTIVE)
        self.check("[販售] x", "請勿在售出後修改價格", T.STATUS_ACTIVE)
        self.check("[販售] x", "價格可議，售出為止", T.STATUS_ACTIVE)

    def test_pending(self):
        self.check("[販售] 台北 iPhone 15 交易中", "", T.STATUS_PENDING)


SAMPLE_1 = """[型號] iPhone 17 pro max

[規格] 256gb/橘

[保固] 開通後一年

[盒裝配件] 原廠配件

[售價] 41500元

[交易方式/地點] 台中西屯面交

[連絡方式] 站內信

[商品照/補充說明]
https://i.imgur.com/0BAjZFr.jpeg
-----
Sent from JPTT on my iPhone"""

SAMPLE_2 = """[型號]
iPhone 14
[規格]
128G 藍色
[保固]
過保
[盒裝配件]
原廠盒裝(不含線)
[售價]
7000
[交易方式/地點]
林口面交 新莊面交
[連絡方式]
站內信
[商品照/補充說明]
外觀良好
電池健康度77%
https://i.mopix.cc/9T9dgT.jpg"""


class RuleExtractTest(unittest.TestCase):
    def test_same_line_template(self):
        f = T.build_fields(T.rule_extract("[販售] 台中iPhone 17 pro max 256橘", SAMPLE_1))
        self.assertEqual((f["model"], f["storage"], f["price"], f["warranty"]),
                         ("iPhone 17 Pro Max", "256GB", 41500, "一年"))

    def test_next_line_template(self):
        f = T.build_fields(T.rule_extract("[販售] 雙北 iPhone 14 128G 藍色", SAMPLE_2))
        self.assertEqual((f["model"], f["storage"], f["price"], f["battery_health"], f["warranty"]),
                         ("iPhone 14", "128GB", 7000, 77, "無保固"))
        self.assertIn("外觀良好", f["notes"])

    def test_multi_model_skipped(self):
        body = "[型號] iPhone 15 Pro/14 Pro Max/13 Pro Max/13/12 Pro\n[售價] 詳見內文"
        self.assertIsNone(T.build_fields(T.rule_extract("[販售] 台中 iPhone 15 Pro/14 Pro Max", body)))

    def test_accessory_skipped(self):
        body = "[型號] 犀牛盾手機殼 iPhone 15 Pro 用\n[售價] 1500"
        self.assertIsNone(T.build_fields(T.rule_extract("[販售] iPhone 15 Pro 手機殼", body)))

    def test_brand_new_and_price_units(self):
        body = "[型號] iPhone 17\n[規格] 256G 黑 全新未拆封\n[保固] 2027/7/10\n[售價] 2.5萬"
        f = T.build_fields(T.rule_extract("[販售] 台北 iPhone 17 256GB 黑 全新", body))
        self.assertEqual((f["全新未拆封機"], f["price"], f["battery_health"]), ("是", 25000, 100))
        self.assertEqual(T.parse_warranty("保固至 2027/7/10"), "2027/7/10")


class RealPostRegressionTest(unittest.TestCase):
    """取自 2026-09-27 實際 MacShop 文章（精簡），曾被誤判的格式。"""

    def fields(self, title, body):
        return T.build_fields(T.rule_extract(title, body))

    def test_fullwidth_brackets(self):
        body = "［型號］iPhone 18 Pro max\n［規格］512G 藍色\n［保固］一年\n［售價］56900\n----\nSent from BePTT on my iPhone 17"
        f = self.fields("[販售] 台中 iPhone 18 Pro max 512G 藍色", body)
        self.assertEqual((f["model"], f["storage"], f["price"]), ("iPhone 18 Pro Max", "512GB", 56900))
        f = self.fields("[販售] 桃園 iPhone 15 pro 256G藍 保內",
                        "[型號］iPhone 15 pro 256G 藍\n[規格］256G 藍\n[保固］2026/10/19\n[售價］現金16500")
        self.assertEqual((f["model"], f["price"], f["warranty"]), ("iPhone 15 Pro", 16500, "2026/10/19"))

    def test_part_number_in_model_field(self):
        f = self.fields("[販售] 台中 iPhone 17 Pro 256G 橘",
                        "[型號]\nA3523\n\n[規格]\niPhone 17 Pro 256G 橘\n\n[保固]\n已過保\n[售價]\n29000")
        self.assertEqual((f["model"], f["storage"], f["price"]), ("iPhone 17 Pro", "256GB", 29000))
        f = self.fields("[販售] 台北 iPhone 17 256G 白色",
                        "[型號] MG6K4ZP/A\n[規格] iPhone 17 265G 白色\n[保固] 2027/06/27\n[售價]25900")
        self.assertEqual((f["model"], f["storage"]), ("iPhone 17", "256GB"))  # 265G 筆誤改用標題
        f = self.fields("[販售] 全國 iphone13 128g 紅 過保", "[型號]\n\nA2633\n\n[規格]\n\n128g紅\n\n[售價]\n\n$6500")
        self.assertEqual((f["model"], f["price"]), ("iPhone 13", 6500))

    def test_numbered_multi_item_skipped(self):
        body = "[型號]\n1. iPhone 17 256g 白 (全新)\n2. Airpods 5 一般版(全新)\n[售價]\n1.29800\n2.4000"
        self.assertIsNone(self.fields("[販售] 台北 iPhone 17", body))

    def test_accessory_new_is_not_brand_new(self):
        cases = [
            ("[販售] 雙北 iphone XR 256g", "[型號] iPhone XR 256G\n[保固] 過保\n[盒裝配件] 完整盒裝 配件（耳機、線、豆腐頭）全新未使用\n[售價] 3300"),
            ("[販售] 高雄 iPhone 17 Pro 512G 橘色", "[型號] iPhone 17 Pro\n[保固] 保固至2026/10/20\n[盒裝配件] 原廠盒裝，傳輸線和SIM卡針全新未使用過\n[售價] 35,000\n[商品照/補充說明]\n電池健康度96%"),
            ("[販售] 新北 iPhone 16 Pro Max 512G 白色", "[型號] iPhone 16 Pro Max (A3296)\n[保固] 已過保\n[盒裝配件] 原廠盒裝完整，配件全新未拆\n[售價] 32,000 元"),
        ]
        for title, body in cases:
            self.assertEqual(self.fields(title, body)["全新未拆封機"], "否", title)

    def test_sealed_phone_is_brand_new(self):
        f = self.fields("[販售] 台北 iPhone 18 Pro 256GB 紅色",
                        "[型號] iPhone 18 Pro 256GB 紅色\n[保固] 連網後開通，保固一年\n[盒裝配件] 全新未拆\n[售價] $42500")
        self.assertEqual((f["全新未拆封機"], f["price"]), ("是", 42500))

    def test_rule_text_in_price_field(self):
        body = "[型號]\nA3717\n[規格]\niPhone 18 Pro Max 256G\n[售價]\n不得超過台灣官方定價。\n售出後修改價格至不可視者水桶並劣退。\n48200"
        f = self.fields("[販售] 台北 全新iPhone 18 Pro Max 256G 銀", body)
        self.assertEqual((f["model"], f["price"], f["全新未拆封機"]), ("iPhone 18 Pro Max", 48200, "是"))
        self.assertEqual(T.detect_status("[販售] 台北 全新iPhone 18 Pro Max 256G 銀", body), T.STATUS_ACTIVE)


class DaysToSellTest(unittest.TestCase):
    def setUp(self):
        self.now = T.datetime.now()
        self.posted = self.now - T.timedelta(days=5)
        self.row = {"post_time": self.posted.strftime("%Y-%m-%d %H:%M:%S")}

    def fmt(self, dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def test_parse_last_edit(self):
        html = ('<div id="main-content">[型號] iPhone 14\n--\n※ 發信站: 批踢踢實業坊(ptt.cc)\n'
                '※ 編輯: abc (1.2.3.4 臺灣), 09/25/2026 10:00:00\n'
                '<div class="push">推 x</div>※ 編輯: abc (1.2.3.4 臺灣), 09/26/2026 21:30:05\n</div>')
        art = T.parse_article(html)
        self.assertEqual(art["last_edit"], T.datetime(2026, 9, 26, 21, 30, 5))
        self.assertNotIn("編輯", art["body"])

    def test_first_sight_uses_last_edit(self):
        T.set_days_to_sell(self.row, "", self.posted + T.timedelta(days=2))
        self.assertEqual((self.row["days_to_sell"], self.row["days_to_sell_basis"]), (2.0, T.BASIS_ESTIMATED))

    def test_first_sight_without_edit(self):
        T.set_days_to_sell(self.row, "", None)
        self.assertEqual((self.row["days_to_sell"], self.row["days_to_sell_basis"]), ("", T.BASIS_UNKNOWN))

    def test_observed_prefers_edit_between_checks(self):
        prev = self.fmt(self.now - T.timedelta(hours=6))
        T.set_days_to_sell(self.row, prev, self.now - T.timedelta(hours=3))
        self.assertEqual(self.row["days_to_sell_basis"], T.BASIS_OBSERVED)
        self.assertAlmostEqual(self.row["days_to_sell"], 4.9, places=1)

    def test_observed_ignores_old_edit(self):
        prev = self.fmt(self.now - T.timedelta(hours=6))
        T.set_days_to_sell(self.row, prev, self.posted + T.timedelta(hours=1))  # 早於上次檢查的編輯不採用
        self.assertEqual((self.row["days_to_sell"], self.row["days_to_sell_basis"]), (5.0, T.BASIS_OBSERVED))

    def test_edit_before_post_is_ignored(self):
        T.set_days_to_sell(self.row, "", self.posted - T.timedelta(days=1))
        self.assertEqual(self.row["days_to_sell_basis"], T.BASIS_UNKNOWN)


class PipelineTest(unittest.TestCase):
    """模擬兩次執行：第一次抓到新文章，第二次文章已擠出首頁，但回訪仍偵測到售出/改價/刪文。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = {k: getattr(T, k) for k in ("LISTINGS_FILE", "EVENTS_FILE", "SUMMARY_FILE",
                                                  "fetch", "llm_extract", "polite_sleep")}
        T.LISTINGS_FILE = os.path.join(self.tmp.name, "listings.csv")
        T.EVENTS_FILE = os.path.join(self.tmp.name, "events.csv")
        T.SUMMARY_FILE = os.path.join(self.tmp.name, "summary.csv")
        T.polite_sleep = lambda *a: None
        now = int(T.datetime.now().timestamp())
        self.paths = [f"/bbs/MacShop/M.{now - n * 3600}.A.{n:03d}.html" for n in range(1, 5)]
        a, b, c, d = self.paths
        self.arts = {
            a: ("[販售] 台北 iPhone 15 pro 256", "[物品型號]: iphone15 pro\n[交易價格]: 25000", "推 x"),
            b: ("[販售] 新北 iPhone 14", "[物品型號]: i14\n[交易價格]: 9000", ""),
            c: ("[販售] 台中 iPhone 殼", "[物品型號]: 手機殼\n[交易價格]: 300", ""),
            d: ("[販售] 高雄 iphone 13", "[物品型號]: iphone 13\n[交易價格]: 8000", ""),
        }
        self.listed = set(self.paths)
        T.fetch = self.fake_fetch
        T.llm_extract = self.fake_llm

    def tearDown(self):
        for k, v in self.orig.items():
            setattr(T, k, v)
        self.tmp.cleanup()

    def fake_fetch(self, url, max_retries=3):
        if "index" in url:
            if not url.endswith("index.html"):
                return 200, "<div></div>"
            ents = "".join(f'<div class="r-ent"><div class="title"><a href="{p}">{self.arts[p][0]}</a></div></div>'
                           for p in self.paths if p in self.listed and self.arts[p])
            return 200, ('<div class="btn-group btn-group-paging"><a href="/x">最舊</a>'
                         f'<a href="/bbs/MacShop/index1.html">上頁</a></div>{ents}')
        art = self.arts.get(url.replace(T.BASE_URL, ""))
        if art is None:
            return 404, ""
        title, body, push = art
        return 200, ('<div id="main-content"><div class="article-metaline"><span class="article-meta-tag">標題'
                     f'</span><span class="article-meta-value">{title}</span></div>{body}\n--\n※ 發信站: x\n'
                     f'<div class="push">{push}</div></div>')

    @staticmethod
    def fake_llm(title, body):
        price = re.search(r"價格\]: (\d+)", body)
        model = re.search(r"型號\]: (.+)", body)
        return {"model": model.group(1) if model else None, "storage": "256",
                "price": int(price.group(1)) if price else None, "battery_health": "88%",
                "warranty": "無保固", "notes": "", "is_brand_new": False}

    def run_main(self, *args):
        sys.argv = ["tracker.py", *args]
        T.main()
        return T.load_listings()

    def test_two_runs(self):
        a, b, c, d = (T.BASE_URL + p for p in self.paths)
        first = self.run_main()
        self.assertEqual(first[a]["status"], T.STATUS_ACTIVE)
        self.assertEqual(first[a]["model"], "iPhone 15 Pro")
        self.assertEqual(first[c]["status"], "略過")

        pa, pb, _, pd = self.paths
        self.arts[pa] = ("[販售] 台北 iPhone 15 pro 256 已售出", self.arts[pa][1], "推 x\n推 y")
        self.arts[pb] = ("[販售] 新北 iPhone 14", self.arts[pb][1].replace("9000", "8500"), "推 z")
        self.arts[pd] = None
        self.listed = set()
        second = self.run_main()
        self.assertEqual(second[a]["status"], T.STATUS_SOLD)
        self.assertNotEqual(second[a]["days_to_sell"], "")
        self.assertEqual(second[b]["price"], "8500")
        self.assertEqual(second[b]["first_price"], "9000")
        self.assertEqual(second[d]["status"], T.STATUS_DELETED)

    def test_sold_on_first_sight_has_no_days(self):
        pa = self.paths[0]
        self.arts[pa] = ("[販售] 台北 iPhone 15 pro 256 已售出", self.arts[pa][1], "")
        rows = self.run_main()
        row = rows[T.BASE_URL + pa]
        # 假頁面沒有「※ 編輯」紀錄 → 無法推估
        self.assertEqual((row["status"], row["days_to_sell"], row["days_to_sell_basis"]),
                         (T.STATUS_SOLD, "", T.BASIS_UNKNOWN))
        legacy = dict(row, days_to_sell="1.1", sold_detected_at=row["first_seen"])
        self.assertTrue(T.sold_on_first_sight(legacy))


if __name__ == "__main__":
    unittest.main()
