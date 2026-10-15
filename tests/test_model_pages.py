"""預先產生機型 HTML 的內容、安全性與既有公開統計語意。"""
import copy
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import model_pages as M


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class ModelHtmlTest(unittest.TestCase):
    def setUp(self):
        self.template = (Path(M.__file__).parent / "model.html").read_text()
        self.model = "iPhone 18 Pro"
        self.canonical = "https://example.test/model.html?m=iPhone+18+Pro"
        self.stats = dict(model=self.model, listed=14, active=10, sold=3, multi=1,
                          median_price=30000.0, min_price=27000, max_price=35000,
                          median_sold_price=29000, median_days=1.5, days_samples=3, days_estimated=1)
        self.data = dict(last_checked="2026-10-16 00:23:20", model_totals=[self.stats],
                         models=[dict(self.stats, storage="256GB")], apple={},
                         listings=[dict(model=self.model, storage="256GB", price=30000,
                                        status="在售", post_time="2026-10-15 20:00:00",
                                        url=f"https://www.ptt.cc/bbs/MacShop/M.{i}.html") for i in range(13)])

    def render(self, **kwargs):
        return M.render_model_html(self.template, self.data, self.model, self.canonical, **kwargs)

    def test_contains_readable_content_and_single_canonical_without_javascript(self):
        html = self.render()
        page = Page(html)
        self.assertIn("iPhone 18 Pro 二手行情", "".join(page.text))
        self.assertIn("$30,000", html)
        self.assertNotIn("$30,000.0", html)
        self.assertIn("全部容量的文章（13）", html)
        self.assertIn("在架 10 · 已售 3 · 多品項 1", html)
        self.assertIn("售出時的最後標價", html)
        self.assertIn("（推估）", html)
        self.assertNotIn("載入中…", html)
        self.assertEqual([a["href"] for t, a in page.elements if t == "link" and a.get("rel") == "canonical"],
                         [self.canonical])
        main = next(a for _, a in page.elements if a.get("id") == "model-main")
        self.assertNotIn("hidden", main)
        self.assertEqual(sum(t == "a" and "ptt.cc/bbs" in a.get("href", "") for t, a in page.elements), 10)

    def test_scripts_and_control_ids_survive_and_assets_can_resolve_from_nested_pages(self):
        page = Page(self.render(asset_prefix="../"))
        ids = {a["id"] for _, a in page.elements if "id" in a}
        self.assertTrue({"watch-model", "storage-tabs", "status-f", "sort-f", "more", "compare", "color-table"} <= ids)
        self.assertTrue({"../common.js", "../watchlist.js", "../model.js"} <=
                        {a.get("src") for t, a in page.elements if t == "script"})
        self.assertIn("gtag('config', 'G-G3GH12TQSZ')", self.render())

    def test_escape_untrusted_text_and_link_schemes(self):
        self.model = '<img src=x onerror="alert(1)">'
        self.stats["model"] = self.model
        for row in self.data["models"] + self.data["listings"]:
            row["model"] = self.model
        self.data["listings"][0]["url"] = "javascript:alert(1)"
        html = self.render()
        self.assertNotIn("<img", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("&lt;img", html)

    def test_missing_prices_and_multi_only_model_do_not_invent_sales_or_articles(self):
        self.data["listings"] = []
        self.stats.update(listed=1, active=0, sold=0, multi=1, median_price=None,
                          median_sold_price=None, min_price=None, max_price=None, median_days=None, days_samples=0)
        before = copy.deepcopy(self.data)
        html = self.render()
        self.assertIn("多品項只納入刊登價統計", html)
        self.assertIn("還沒有售出天數", html)
        self.assertNotIn("$0", html)
        self.assertEqual(self.data, before)

    def test_official_price_information_keeps_unknown_capacity_and_source(self):
        self.data["apple"][self.model] = dict(prices={"256GB": 36900, "512GB": None},
                                                   sources=["https://www.apple.com/tw/newsroom/example"])
        html = self.render()
        self.assertIn("最終官方售價", html)
        self.assertIn("查無官方價格", html)
        self.assertIn("https://www.apple.com/tw/newsroom/example", html)

    def test_build_outputs_independent_pages_and_removes_stale_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "model.html").write_text(self.template)
            paths = M.build_model_pages(out, self.data, "https://example.test/")
            self.assertEqual(paths, ["models/iphone-18-pro.html"])
            self.assertIn(self.model, (out / paths[0]).read_text())
            self.assertEqual((out / "model.html").read_text(), self.template)
            (out / "models/stale.html").write_text("obsolete")
            M.build_model_pages(out, self.data, "https://example.test/")
            self.assertFalse((out / "models/stale.html").exists())

    def test_safe_paths_and_collisions_fail_without_overwriting(self):
        self.assertEqual(M.model_path("iPhone SE (第 3 代)"), "models/iphone-se-3.html")
        self.assertRegex(M.model_path("../../x?y=#z"), r"^models/[a-z0-9-]+\.html$")
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "model.html").write_text(self.template)
            self.data["model_totals"].append(dict(self.stats, model="IPHONE 18 PRO"))
            with self.assertRaisesRegex(ValueError, "網址重複"):
                M.build_model_pages(out, self.data, "https://example.test/")

    def test_multiple_models_have_distinct_metadata_and_do_not_mix_articles(self):
        other = "iPhone 15"
        self.data["model_totals"].append(dict(self.stats, model=other, listed=1, median_price=12000))
        self.data["models"].append(dict(self.stats, model=other, storage="128GB"))
        self.data["listings"].append(dict(model=other, storage="128GB", price=12000,
                                            status="在售", url="https://www.ptt.cc/only-iphone-15"))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "model.html").write_text(self.template)
            paths = M.build_model_pages(out, self.data, "https://example.test/")
            first, second = [(out / path).read_text() for path in paths]
            self.assertNotIn("only-iphone-15", first)
            self.assertIn("only-iphone-15", second)
            self.assertIn("全部容量的文章（1）", second)
            self.assertNotIn("iPhone 18 Pro", second)
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
