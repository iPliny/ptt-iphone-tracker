import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "site"))
import jp_pages as P  # noqa: E402

SITE = "https://macshop.crawlsnek.com/"


def row(shop, price, storage="256GB", condition="未開封", model="iPhone 17 Pro", **extra):
    base = {"shop": shop, "model": model, "storage": storage, "condition": condition, "carrier": "SIMフリー",
            "color": "", "price_jpy": price, "last_checked": "2026-10-18T00:47:44+09:00",
            "source_url": "https://amemoba.com/smartphone/iphone/iphone-17-pro/"}
    base.update(extra)
    return base


class JpPagesTest(unittest.TestCase):
    def test_visible_prices_matches_jp_js(self):
        # 與 tests/jp.test.cjs 的 visiblePrices 案例相同。
        self.assertEqual(P.visible_prices([200000, 210000, 90000]), [200000, 210000, None])
        self.assertEqual(P.visible_prices([200000, 210000, 430000]), [200000, 210000, None])
        self.assertEqual(P.visible_prices([200000, 400000, None]), [200000, 400000, None])
        self.assertEqual(P.visible_prices([200000, 500000, None]), [None, None, None])
        self.assertEqual(P.visible_prices([500000, None, None]), [500000, None, None])

    def test_comparison_main_price_only_and_used_shops(self):
        latest = [row("mobile-mix", 173000), row("イオシス", 166000), row("アメモバ", 169000),
                  row("mobile-mix", 150000, color="シルバー"), row("アメモバ", 990000, carrier="docomo"),
                  row("イオシス", 150000, condition="中古上限"), row("アメモバ", 151000, condition="中古上限")]
        groups, offered = P.comparison(latest, "iPhone 17 Pro", "未開封")
        self.assertEqual((groups[0]["highest"], groups[0]["spread"]), (173000, 7000))
        groups, offered = P.comparison(latest, "iPhone 17 Pro", "中古上限")
        self.assertEqual(offered, [False, True, True])
        html = P.table(groups, offered, P.TEXT["ja"])
        self.assertIn("中古買取なし", html)
        self.assertIn('class="jp-best"', html)
        self.assertNotIn("990,000", html)

    def test_page_metadata_and_links(self):
        latest = [row("mobile-mix", 173000), row("アメモバ", 151000, condition="中古上限"),
                  row("イオシス", 166000, source_url="javascript:alert(1)")]
        for lang, path in (("zh", "jp/iphone-17-pro/"), ("ja", "jp/ja/iphone-17-pro/")):
            html = P.page_html({"latest": latest}, "iPhone 17 Pro", lang, SITE)
            self.assertIn(f'<link rel="canonical" href="{SITE}{path}">', html)
            self.assertIn(f'hreflang="zh-Hant-TW" href="{SITE}jp/iphone-17-pro/"', html)
            self.assertIn(f'hreflang="ja" href="{SITE}jp/ja/iphone-17-pro/"', html)
            self.assertIn("2026年10月", html)
            self.assertIn("G-G3GH12TQSZ", html)
            self.assertIn('href="../?m=iPhone+17+Pro&amp;c=used"', html)
            self.assertIn('href="../iphone-air/"', html)
            self.assertNotIn("javascript:", html)
            self.assertEqual(html.count("jp-none"), 2)  # 只有中古表的 mobile-mix、イオシス
            self.assertIn("¥173,000", html)
            data = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])
            self.assertEqual(data["itemListElement"][-1]["item"], SITE + path)

    def test_build_writes_pages_sitemap_and_prefills_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data, out = root / "input", root / "site"
            (data / "jp").mkdir(parents=True)
            header = "shop,model,storage,condition,carrier,color,price_jpy,since,last_checked,shop_updated,source_url\n"
            (data / "jp" / "latest.csv").write_text(
                header + "アメモバ,iPhone 18 Pro,256GB,未開封,SIMフリー,,200000,2026-10-17T09:00:00+09:00,"
                "2026-10-18T00:47:44+09:00,,https://amemoba.com/smartphone/iphone/iphone-18-pro/\n", encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "site/build_site.py"), "--data", str(data), "--out", str(out)],
                           check=True, capture_output=True)
            self.assertTrue((out / "jp/iphone-18-pro/index.html").exists())
            self.assertTrue((out / "jp/ja/iphone-18-pro/index.html").exists())
            self.assertFalse((out / "jp/iphone-air").exists())
            self.assertNotIn("iphone-air/", (out / "jp/iphone-18-pro/index.html").read_text())
            sitemap = (out / "sitemap.xml").read_text()
            self.assertIn(SITE + "jp/iphone-18-pro/", sitemap)
            self.assertIn(SITE + "jp/ja/iphone-18-pro/", sitemap)
            for index in ("jp/index.html", "jp/ja/index.html"):
                html = (out / index).read_text()
                self.assertNotIn("<!--JP_MODEL_LINKS-->", html)
                self.assertIn('<a href="iphone-18-pro/">', html)
                self.assertIn("¥200,000", html)


if __name__ == "__main__":
    unittest.main()
