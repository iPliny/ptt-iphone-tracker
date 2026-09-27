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


if __name__ == "__main__":
    unittest.main()
