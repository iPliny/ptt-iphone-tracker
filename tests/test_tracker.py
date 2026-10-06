"""離線測試：用假的 PTT 頁面與假的 LLM，不需網路也不需 Ollama。執行：python -m unittest"""
import os
import re
import sys
import tempfile
import unittest
from html import escape
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tracker as T  # noqa: E402


def push_html(userid, content, tag="推"):
    return (f'<div class="push"><span class="hl push-tag">{tag} </span>'
            f'<span class="f3 hl push-userid">{escape(userid)}</span>'
            f'<span class="f3 push-content">: {escape(content)}</span>'
            '<span class="push-ipdatetime"> 09/28 12:34</span></div>')


class PrivateMsgTest(unittest.TestCase):
    def article(self, pushes=""):
        return T.parse_article('<div id="main-content"><div class="article-metaline">'
                               '<span class="article-meta-tag">作者</span>'
                               '<span class="article-meta-value">seller (暱稱)</span></div>'
                               '本文\n--\n※ 發信站: x\n' + pushes + '</div>')

    def test_keywords_and_tags(self):
        words = ["私", "已私", "私訊", "私信", "私你", "私了", "站內", "站內信", "已站內", "密你", "已密"]
        for tag in ("推", "噓", "→"):
            with self.subTest(tag=tag):
                art = self.article("".join(push_html(f"buyer{i}", word, tag) for i, word in enumerate(words)))
                self.assertEqual(art["pm_count"], len(words))

    def test_unique_buyers_and_author(self):
        art = self.article(push_html("buyer1", "私") + push_html("buyer1", "私", "→") +
                           push_html("seller", "已回站內") + push_html("seller", "私訊已回"))
        self.assertEqual(art["pm_count"], 1)

    def test_noise(self):
        for word in ("私密", "私人", "隱私", "自私", "私下", "私心", "公私", "勿私", "不私", "別私", "不要私"):
            with self.subTest(word=word):
                self.assertEqual(self.article(push_html("buyer", word))["pm_count"], 0)
        self.assertEqual(self.article(push_html("buyer", "隱私，已站內"))["pm_count"], 1)

    def test_no_pushes_and_body_hash(self):
        empty = self.article()
        pushed = self.article(push_html("buyer", "私"))
        self.assertEqual(empty["pm_count"], 0)
        self.assertEqual(empty["body"], "本文")
        self.assertEqual(T.body_hash(empty["body"]), T.body_hash(pushed["body"]))


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

    def test_date_in_price_field(self):
        """2026-10-04 M.1791079626 被抓成售價 $2028（AppleCare+ 期限 2028/1/22）；本文依該列 notes 重建。"""
        body = ("[型號] iPhone 17 Pro\n[規格] 256G 銀色\n[保固] 2026/10/22\n"
                "[售價] 有 Apple care+ 到2028/1/22 31000\n[商品照/補充說明] 電池健康度93%")
        f = self.fields("[販售] 雙北 iphone 17pro 銀色 256G", body)
        self.assertEqual((f["model"], f["price"]), ("iPhone 17 Pro", 31000))
        self.assertIsNone(T.parse_price("Apple care+到2028/1/22"))
        self.assertIsNone(T.parse_price("保固到 2028年1月"))
        self.assertEqual(T.parse_price("28000-29000"), 28000)
        self.assertEqual(T.parse_price("$25,000."), 25000)

    def test_rule_text_in_price_field(self):
        body = "[型號]\nA3717\n[規格]\niPhone 18 Pro Max 256G\n[售價]\n不得超過台灣官方定價。\n售出後修改價格至不可視者水桶並劣退。\n48200"
        f = self.fields("[販售] 台北 全新iPhone 18 Pro Max 256G 銀", body)
        self.assertEqual((f["model"], f["price"], f["全新未拆封機"]), ("iPhone 18 Pro Max", 48200, "是"))
        self.assertEqual(T.detect_status("[販售] 台北 全新iPhone 18 Pro Max 256G 銀", body), T.STATUS_ACTIVE)


MULTI_PRODUCT_POST = """[型號]
iPhone 16 pro max

[規格]
256g 金色

[保固]
已過保

[售價]
$25,000

[商品照/補充說明]
1.輕微使用痕跡
2.電池健康度92%
3.無維修過



[型號]
Apple Watch S10 GPS 46mm

[規格]
46mm GPS 黑色

[保固]
過保

[盒裝配件]
完整盒裝+充電線
電池健康度89%

[售價］
7000"""


class MultiProductPostTest(unittest.TestCase):
    """2026-09-28 回報：M.1790391324.A.30C 同篇另賣 Apple Watch，售價被 Watch 的 7000 覆蓋。"""

    def test_uses_iphone_block_only(self):
        f = T.build_fields(T.rule_extract("[販售]  台南 Iphone 16 pro max 256g", MULTI_PRODUCT_POST))
        self.assertEqual((f["model"], f["storage"], f["price"], f["battery_health"]),
                         ("iPhone 16 Pro Max", "256GB", 25000, 92))

    def test_iphone_after_other_product(self):
        watch, phone = MULTI_PRODUCT_POST.split("\n\n\n\n")
        f = T.build_fields(T.rule_extract("[販售] 台南 Apple Watch + iPhone 16 Pro Max", phone and watch + "\n\n" + phone))
        self.assertEqual((f["model"], f["price"]), ("iPhone 16 Pro Max", 25000))

    def test_two_iphone_blocks_skipped(self):
        body = "[型號] iPhone 15\n[售價] 15000\n\n[型號] iPhone 14\n[售價] 9000"
        self.assertIsNone(T.build_fields(T.rule_extract("[販售] iPhone 15 / iPhone 14", body)))


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
                                                  "fetch", "llm_extract", "polite_sleep", "REPARSE")}
        T.LISTINGS_FILE = os.path.join(self.tmp.name, "listings.csv")
        T.EVENTS_FILE = os.path.join(self.tmp.name, "events.csv")
        T.SUMMARY_FILE = os.path.join(self.tmp.name, "summary.csv")
        T.polite_sleep = lambda *a: None
        now = int(T.datetime.now().timestamp())
        self.paths = [f"/bbs/MacShop/M.{now - n * 3600}.A.{n:03d}.html" for n in range(1, 5)]
        a, b, c, d = self.paths
        self.arts = {
            a: ("[販售] 台北 iPhone 15 pro 256", "[物品型號]: iphone15 pro\n[交易價格]: 25000", push_html("buyer1", "私")),
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
        return 200, ('<div id="main-content"><div class="article-metaline"><span class="article-meta-tag">作者</span>'
                     '<span class="article-meta-value">seller (暱稱)</span></div>'
                     '<div class="article-metaline"><span class="article-meta-tag">標題'
                     f'</span><span class="article-meta-value">{title}</span></div>{body}\n--\n※ 發信站: x\n'
                     f'{push}</div>')

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
        self.arts[pa] = ("[販售] 台北 iPhone 15 pro 256 已售出", self.arts[pa][1], push_html("buyer1", "私") + push_html("buyer2", "私"))
        self.arts[pb] = ("[販售] 新北 iPhone 14", self.arts[pb][1].replace("9000", "8500"), push_html("buyer3", "私"))
        self.arts[pd] = None
        self.listed = set()
        second = self.run_main()
        self.assertEqual(second[a]["status"], T.STATUS_SOLD)
        self.assertNotEqual(second[a]["days_to_sell"], "")
        self.assertEqual(second[b]["price"], "8500")
        self.assertEqual(second[b]["first_price"], "9000")
        self.assertEqual(second[d]["status"], T.STATUS_DELETED)
        self.assertEqual(second[d]["private_msg_count"], "0")
        self.assertEqual(second[c]["private_msg_count"], "")

    def test_private_messages_update_without_edit_events(self):
        pa = self.paths[0]
        url = T.BASE_URL + pa
        first = self.run_main()
        self.assertEqual(first[url]["private_msg_count"], "1")
        with open(T.EVENTS_FILE, encoding="utf-8-sig") as f:
            events = f.read()
        title, body, pushes = self.arts[pa]
        self.arts[pa] = (title, body, pushes + push_html("buyer2", "已私", "→"))
        self.listed = set()  # 只靠既有回訪，不新增抓取
        with patch.object(T, "safe_extract", side_effect=AssertionError("推文變動不得重新萃取")) as extract:
            second = self.run_main()
        extract.assert_not_called()
        self.assertEqual(second[url]["private_msg_count"], "2")
        self.assertEqual(second[url]["body_hash"], first[url]["body_hash"])
        with open(T.EVENTS_FILE, encoding="utf-8-sig") as f:
            self.assertEqual(f.read(), events)
        self.arts[pa] = (title + " 已售出", body, self.arts[pa][2] + push_html("buyer3", "私訊"))
        third = self.run_main()
        self.assertEqual(third[url]["status"], T.STATUS_SOLD)
        self.assertEqual(third[url]["private_msg_count"], "2")
        self.assertEqual(self.run_main()[url]["private_msg_count"], "2")

    def test_old_csv_without_private_message_column(self):
        with open(T.LISTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("source_url,status\nold,已售出\n")
        rows = T.load_listings()
        self.assertIsNone(rows["old"].get("private_msg_count"))
        T.save_listings(rows)
        self.assertEqual(T.load_listings()["old"]["private_msg_count"], "")
        self.assertEqual(T.LISTING_FIELDS[-4:],
                         ["days_to_sell_basis", "private_msg_count", "last_edit_at", "price_checked_at"])

    def test_reparse_fixes_old_wrong_price(self):
        a = T.BASE_URL + self.paths[0]
        rows = self.run_main()
        rows[a]["price"] = rows[a]["first_price"] = "7000"  # 模擬舊規則抓錯
        T.save_listings(rows)
        self.listed = set()
        rows = self.run_main("--reparse")
        self.assertEqual((rows[a]["price"], rows[a]["first_price"]), ("25000", "25000"))
        events = open(T.EVENTS_FILE, encoding="utf-8-sig").read()
        self.assertIn("重新解析修正", events)
        self.assertNotIn("價格變動", events)

    def test_sold_on_first_sight_has_no_days(self):
        pa = self.paths[0]
        self.arts[pa] = ("[販售] 台北 iPhone 15 pro 256 已售出", self.arts[pa][1], "")
        rows = self.run_main()
        row = rows[T.BASE_URL + pa]
        self.assertEqual(row["private_msg_count"], "")
        # 假頁面沒有「※ 編輯」紀錄 → 無法推估
        self.assertEqual((row["status"], row["days_to_sell"], row["days_to_sell_basis"]),
                         (T.STATUS_SOLD, "", T.BASIS_UNKNOWN))
        legacy = dict(row, days_to_sell="1.1", sold_detected_at=row["first_seen"])
        self.assertTrue(T.sold_on_first_sight(legacy))



    def test_old_rows_become_skipped(self):
        a, b = T.BASE_URL + self.paths[0], T.BASE_URL + self.paths[1]
        rows = self.run_main()
        rows[b].update(title="[販售] 新北 iPhone 14 原廠殼", storage="未知")  # 舊規則留下的配件列
        rows[a]["model"] = "iPhone X Pro"
        T.save_listings(rows)
        self.listed = set()
        rows = self.run_main("--report-only")
        self.assertEqual((rows[a]["status"], rows[b]["status"]), ("略過", "略過"))
        events = open(T.EVENTS_FILE, encoding="utf-8-sig").read()
        self.assertIn("排除誤判", events)
        with open(T.SUMMARY_FILE, encoding="utf-8-sig") as f:
            self.assertNotIn("iPhone 14", f.read())
        # 第二次執行不再重複記錄
        self.run_main("--report-only")
        self.assertEqual(open(T.EVENTS_FILE, encoding="utf-8-sig").read(), events)

    def test_reparse_skips_accessory(self):
        b = T.BASE_URL + self.paths[1]
        rows = self.run_main()
        pb = self.paths[1]
        self.assertEqual(rows[b]["status"], T.STATUS_ACTIVE)
        # 規則變嚴後，同一篇本文（未編輯）重新解析不再算 iPhone
        with patch.object(T, "safe_extract", return_value=None):
            self.listed = set()
            rows = self.run_main("--reparse")
        self.assertEqual(rows[b]["status"], "略過")

if __name__ == "__main__":
    unittest.main()



class TimezoneTest(unittest.TestCase):
    """Actions 主機是 UTC；tracker.py 強制台灣時間，發文時間才會和 PTT 的編輯時間一致。"""

    def test_post_time_is_taipei(self):
        url = T.BASE_URL + "/bbs/MacShop/M.1790391324.A.30C.html"  # UTC 2026-09-26 02:55:24
        self.assertEqual(T.post_time_from_url(url), "2026-09-26 10:55:24")


class ModelFieldRegressionTest(unittest.TestCase):
    """型號欄下一行接了序號查詢連結、或型號欄沒寫代數時，不能把整段文字當型號。"""
    SERIAL = "可憑商品序號至 Apple官網查詢 https://apple.co/3l6By0R\n"

    def post(self, model_field):
        return ("[型號]：" + model_field + "\n" + self.SERIAL +
                "[規格]：512G\n[保固]：無\n[售價]：36,700\n[交易方式/地點]：面交\n")

    def test_missing_generation_falls_back_to_title(self):
        # M.1790766521.A.A2D
        f = T.rule_extract("[販售] 高雄 iPhone 17 Pro Max 512G 橘色", self.post("iPhone Pro Max"))
        self.assertEqual(f["model"], "iPhone 17 Pro Max")

    def test_glued_promax_and_serial_line(self):
        # M.1790564568.A.B4C
        f = T.rule_extract("[販售] 台中 iPhone18Promax 1T 冰川藍", self.post("iPhone18promax 1T藍"))
        self.assertEqual(f["model"], "iPhone 18 Pro Max")

    def test_model_without_generation_uses_title(self):
        # M.1790710945.A.7BE
        f = T.rule_extract("[販售] 桃園 iPhone 15 pro max 256g", self.post("iPhone pro max 256g"))
        self.assertEqual(f["model"], "iPhone 15 Pro Max")

    def test_nonexistent_model_is_not_recorded(self):
        # M.1790607432.A.D59：標題只有 [販售]，型號寫 iPhone X Pro（不存在）
        self.assertIsNone(T.rule_extract("[販售]", self.post("iPhone X Pro"))["model"])

    def test_title_adds_missing_suffix(self):
        # M.1790406395.A.158：型號欄只寫 iPhone18，標題是 18 pro → 不能記成不存在的 iPhone 18
        f = T.rule_extract("[販售] 高雄 全新Iphone18 pro 256紅", self.post("iPhone18"))
        self.assertEqual(f["model"], "iPhone 18 Pro")
        # 標題是別的代數時不採用
        f = T.rule_extract("[販售] 高雄 iPhone 17 256G", self.post("iPhone18"))
        self.assertEqual(f["model"], "iPhone 18")

    def test_glued_names(self):
        for raw, want in [("iPhone16pro256G金", "iPhone 16 Pro"), ("iPhone 17ProMax 256G", "iPhone 17 Pro Max"),
                          ("Mac mini m4 iPhone 16 pro", "iPhone 16 Pro")]:
            self.assertEqual(T.normalize_model(raw), want)


class AccessoryPostTest(unittest.TestCase):
    """標題寫型號、賣的其實是殼：型號欄照抄適用機型，不能當成一支 iPhone。"""

    def test_case_with_model_field(self):
        # M.1790394640.A.E45：原廠織紋殼被記成 17 Pro Max $1,200
        body = ("[型號]：iPhone 17 Pro Max\n[規格]：原廠織紋殼 黑色\n[保固]：無\n[售價]：1200\n"
                "[補充說明]：很少使用，略有使用痕跡 (如照片)\n")
        self.assertIsNone(T.rule_extract("[販售] 全國 iphone 17 pro max 原廠織紋殼", body)["model"])

    def test_two_cases(self):
        # M.1791217114.A.90E：兩個原廠殼一起賣 $1,000
        body = "[型號]：iPhone16Plus\n[規格]：原廠殼\n[售價]：1000\n[補充說明]：約8-9成新 無明顯傷 兩個一起賣\n"
        self.assertIsNone(T.rule_extract("[販售] 苗栗 iPhone16Plus 原廠殼", body)["model"])

    def test_phone_with_case_in_title_kept(self):
        # M.1790992340.A.022：標題提到透明殼，但賣的是 256G 手機，殼是加購
        body = ("[型號]：iPhone 17 Pro Max\n[規格]：256G\n[保固]：2026/10/4\n[售價]：34000\n"
                "[補充說明]：原廠透明殼也有原盒，加購只要700元\n")
        f = T.rule_extract("[販售]  雙北 iPhone 17Pro Max 原廠透明殼", body)
        self.assertEqual((f["model"], f["storage"], f["price"]), ("iPhone 17 Pro Max", "256GB", 34000))

    def test_misparsed_reason(self):
        row = {"title": "[販售] 全國 iphone 17 pro max 原廠織紋殼", "model": "iPhone 17 Pro Max", "storage": "未知"}
        self.assertEqual(T.misparsed_reason(row), "配件")
        self.assertIn("iPhone X Pro", T.misparsed_reason({"title": "[販售]", "model": "iPhone X Pro", "storage": "64GB"}))
        self.assertIsNone(T.misparsed_reason({"title": "[販售] 雙北 iPhone 17Pro Max 原廠透明殼",
                                              "model": "iPhone 17 Pro Max", "storage": "256GB"}))

