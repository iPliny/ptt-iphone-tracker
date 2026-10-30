"""イオシス販賣頁的離線測試，原始來源與裁切方式見 fixtures/jp/README.md。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from jp import buyback
from jp import local
from jp import local_iosys as sell

FIXTURES = Path(__file__).parent / "fixtures" / "jp"
URL = sell.IOSYS_SELL_INDEX + "/iphone17_pro"


def fixture(name="local-iosys-17pro"):
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


class IosysSellTests(unittest.TestCase):
    def test_real_fixture_minimum_per_spec_and_grade(self):
        rows, updated = sell.parse_iosys_sell(fixture(), URL)
        self.assertEqual(len(rows), 6)  # 七件商品，其中兩件同一規格、等級、版本。
        self.assertEqual(updated, "")
        self.assertEqual({r["model"] for r in rows}, {"iPhone 17 Pro", "iPhone 17 Pro Max"})
        self.assertEqual({r["condition"] for r in rows}, set(sell.SELL_CONDITIONS))
        self.assertEqual({r["carrier"] for r in rows}, {"SIMフリー", "docomo", "au"})
        self.assertTrue(all(r["color"] == "" and r["shop"] == "イオシス" for r in rows))
        self.assertEqual(next(r for r in rows if r["storage"] == "1TB")["price_jpy"], 239800)
        self.assertEqual(next(r for r in rows if r["condition"] == "未使用品")["price_jpy"], 213800)
        self.assertEqual(next(r for r in rows if r["condition"] == "中古C")["price_jpy"], 174800)

    def test_lower_item_and_cross_page_minimum(self):
        html = fixture().replace("239,800", "230,000", 1)
        rows, _ = sell.parse_iosys_sell(html, URL)
        self.assertEqual(next(r for r in rows if r["storage"] == "1TB")["price_jpy"], 230000)
        original, _ = sell.parse_iosys_sell(fixture(), URL)
        merged = sell.minimum_prices(original + rows)
        self.assertEqual(len(merged), 6)
        self.assertEqual(next(r for r in merged if r["storage"] == "1TB")["price_jpy"], 230000)

    def test_recommendations_outside_main_are_not_prices(self):
        soup = BeautifulSoup(fixture(), "html.parser")
        extra = str(soup.select_one("li.item")).replace("239,800", "1,000")
        rows, _ = sell.parse_iosys_sell(extra + fixture(), URL)
        self.assertEqual(next(r for r in rows if r["storage"] == "1TB")["price_jpy"], 239800)

    def test_untracked_models_overseas_and_unknown_version_are_ignored(self):
        for old, new in [("iPhone17 Pro", "iPhone17e"),
                         ("iPhone17 Pro", "iPhone16 Pro"),
                         ("版SIMフリー", "海外版SIMフリー")]:
            with self.subTest(replacement=new):
                rows, _ = sell.parse_iosys_sell(fixture().replace(old, new), URL)
                self.assertEqual(rows, [])
        soup = BeautifulSoup(fixture(), "html.parser")
        for node in soup.select(".name"):
            node.string = "iPhone17 Pro A3522 (MG8D4J/A) 1TB シルバー"
        self.assertEqual(sell.parse_iosys_sell(str(soup), URL)[0], [])

    def test_unrelated_model_on_known_page_is_ignored(self):
        rows, _ = sell.parse_iosys_sell(fixture().replace("iPhone17 Pro", "iPhone18 Pro"), URL)
        self.assertEqual(rows, [])

    def test_missing_price_condition_or_name_fail_closed(self):
        for old, new in [('class="price"', 'class="changed"'),
                         ('class="condition"', 'class="changed"'),
                         ('class="name"', 'class="changed"'),
                         ("中古Aランク", "不明ランク")]:
            with self.subTest(element=old):
                with self.assertRaises(buyback.ParseError):
                    sell.parse_iosys_sell(fixture().replace(old, new), URL)
        with self.assertRaises(buyback.ParseError):
            sell.parse_iosys_sell("<html>blocked</html>", URL)

    def test_catalog_only_discovers_observed_supported_groups(self):
        pages = sell.discover_iosys_pages(fixture("local-iosys-index"))
        self.assertEqual(pages, sell.IOSYS_SELL_GROUPS)
        self.assertNotIn("iPhone 17e", {m for models in pages.values() for m in models})
        self.assertNotIn("iPhone Duo", {m for models in pages.values() for m in models})
        with self.assertRaises(buyback.ParseError):
            sell.discover_iosys_pages('<a href="https://example.com/iphone17_pro">iPhone</a>')
        soup = BeautifulSoup(fixture("local-iosys-index"), "html.parser")
        soup.select_one("a").decompose()
        with self.assertRaises(buyback.ParseError):
            sell.discover_iosys_pages(str(soup))

    def test_next_page_and_last_page(self):
        self.assertEqual(sell.iosys_next_page(fixture(), URL), URL + "?page=2")
        self.assertIsNone(sell.iosys_next_page('<div id="pagination"></div>', URL + "?page=8"))
        for broken in [fixture().replace('rel="next"', ""),
                       '<html>blocked</html>',
                       fixture().replace('page=2" rel="next"', 'page=3" rel="next"')]:
            with self.assertRaises(buyback.ParseError):
                sell.iosys_next_page(broken, URL)

    def test_next_page_cannot_change_host_model_or_query(self):
        for target in ["https://example.com/items/smartphone/iphone/iphone17_pro?page=2",
                       sell.IOSYS_SELL_INDEX + "/iphone18_pro?page=2",
                       URL + "?page=2&session=secret"]:
            with self.subTest(target=target), self.assertRaises(buyback.ParseError):
                sell.iosys_next_page(f'<div id="pagination"><a rel="next" href="{target}">2</a></div>', URL)
        base = sell.IOSYS_SELL_INDEX + "/iphone17?not=pro+17e"
        next_url = base + "&page=2"
        self.assertEqual(sell.iosys_next_page(
            f'<div id="pagination"><a rel="next" href="{next_url}">2</a></div>', base), next_url)
        with self.assertRaises(buyback.ParseError):
            sell.iosys_next_page('<div id="pagination"><a rel="next" href="?page=2">2</a></div>', base)

    def test_fixture_has_no_scripts_forms_tracking_or_session_content(self):
        for name in ("local-iosys-index", "local-iosys-17pro"):
            soup = BeautifulSoup(fixture(name), "html.parser")
            self.assertFalse(soup.select("script, form, input, img, iframe"))
            for node in soup.find_all(True):
                self.assertTrue(set(node.attrs) <= {"class", "id", "href", "rel"})


class IosysSellCollectionTests(unittest.TestCase):
    def setUp(self):
        # 第二頁是由真實片段製作的測試變體，價格與分頁不代表店家歷史。
        soup = BeautifulSoup(fixture().replace("239,800", "230,000", 1), "html.parser")
        soup.select_one("#pagination").clear()
        self.pages = {
            sell.IOSYS_SELL_INDEX: fixture("local-iosys-index"),
            URL: fixture(),
            URL + "?page=2": str(soup),
        }
        self.discovery = patch.object(local, "discover_iosys_pages", return_value={
            URL: sell.IOSYS_SELL_GROUPS[URL]})
        self.discovery.start()
        self.addCleanup(self.discovery.stop)

    def test_all_pages_are_fetched_and_minimum_spans_pages(self):
        fetched = []

        def fetch(url):
            fetched.append(url)
            return self.pages[url]

        results = local.collect(only=("iosys-sell",), fetcher=fetch)
        self.assertEqual(fetched, [sell.IOSYS_SELL_INDEX, URL, URL + "?page=2"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual(results[0]["source"], "iosys-sell")
        rows = results[0]["rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(next(r for r in rows if r["storage"] == "1TB")["price_jpy"], 230000)

    def test_later_page_failure_preserves_previous_prices_and_latest(self):
        good = local.collect(only=("iosys-sell",), fetcher=self.pages.__getitem__)
        fetched = []

        def fetch(url):
            fetched.append(url)
            if url.endswith("?page=2"):
                raise RuntimeError("測試後頁抓取失敗")
            return self.pages[url]

        failed = local.collect(only=("iosys-sell",), fetcher=fetch)
        self.assertEqual(fetched, [sell.IOSYS_SELL_INDEX, URL, URL + "?page=2"])
        self.assertEqual(failed[0]["status"], "fetch_error")
        self.assertEqual(len(failed[0]["rows"]), 6)  # 首頁已解析，但不能拿它覆寫整店。
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "jp"
            local.save_or_check(directory, good, run_at="2026-10-30T09:40:00+09:00")
            paths = [directory / "sell" / name for name in ("prices.csv", "latest.csv")]
            before = {path: path.read_bytes() for path in paths}
            reports = local.save_or_check(directory, failed, run_at="2026-10-30T21:40:00+09:00")
            self.assertEqual(reports[0]["status"], "fetch_error")
            self.assertEqual(before, {path: path.read_bytes() for path in paths})
            self.assertEqual(buyback.read_csv(directory / "sell" / "runs.csv")[-1]["status"], "fetch_error")
            self.assertFalse((directory / "prices.csv").exists())


if __name__ == "__main__":
    unittest.main()
