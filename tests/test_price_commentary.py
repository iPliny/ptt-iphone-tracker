"""用合成資料檢查短評事實、稿件規格與機型頁。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"
sys.path.insert(0, str(SITE))

import build_site
import price_commentary as C
from model_pages import render_model_html

MODEL = "iPhone 18 Pro"
MONTH = "2026-11"
AS_OF = "2026-11-24"
STATS = dict(model=MODEL, listed=10, active=6, sold=3, multi=1, median_price=29000,
             min_price=26000, max_price=33000, median_sold_price=28500, median_days=2.5,
             days_samples=2, days_estimated=1)


def commentary(models):
    return {"month": MONTH, "as_of": AS_OF, "models": models}


class PriceCommentaryTest(unittest.TestCase):
    def test_compile_facts(self):
        other = "iPhone 17"
        no_sales = "iPhone 16"
        totals = [STATS, dict(STATS, model=other, listed=9), dict(STATS, model=no_sales, sold=0)]
        capacities = [dict(STATS, storage="256GB"), dict(STATS, storage="512GB", sold=0)]
        sold = dict(model=MODEL, storage="256GB", status="已售出", price=28000,
                    post_time="2026-10-30 22:00:00", sold_at="2026-10-31 18:00:00",
                    sold_detected_at="2026-11-01 08:00:00",
                    url="https://example.test/article", title="原文與賣家帳號")
        listings = [
            sold,
            dict(sold, price=29000, post_time="2026-11-02", sold_detected_at=AS_OF),
            dict(sold, price=None, storage="512GB", post_time="2026-11-03"),
            dict(sold, status="在售", post_time="2026-11-05"),
            dict(sold, post_time="2026-11-25", sold_detected_at="2026-11-25"),
            dict(sold, post_time="2026-10-31", sold_detected_at="2026-10-31"),
        ]
        values = [30000] + [None] * 22 + [32000] + [None] * 6 + [33000, None, 40000]
        series = [dict(model=MODEL, storage="256GB", brand_new=False, values=values),
                  dict(model=MODEL, storage="256GB", brand_new=True, values=[None, 35000])]
        apple = {"sources": ["https://www.apple.com/tw/"], "prices": {"256GB": 35900}}
        data = dict(model_totals=totals, models=capacities, listings=listings,
                    trends={"start": "2026-10-24", "series": series},
                    apple={MODEL: dict(apple, sources=apple["sources"] + ["https://example.test/price"])})
        result = C.compile_facts(data, MONTH, AS_OF)
        self.assertEqual((result["month"], result["as_of"]), (MONTH, AS_OF))
        self.assertEqual(set(result["models"]), {MODEL, other, no_sales})
        facts = result["models"][MODEL]
        for key in set(STATS) - {"model"}:
            self.assertEqual(facts[key], STATS[key])
            self.assertEqual(facts["capacities"]["256GB"][key], STATS[key])
        self.assertEqual(facts["monthly"], {
            "listed": 3, "sold": 3, "median_sold_price_by_storage": {"256GB": 28500},
        })
        self.assertEqual((facts["first_post_date"], facts["last_post_date"]), ("2026-10-30", "2026-11-05"))
        self.assertEqual(facts["capacities"]["256GB"]["trends"], {
            "used": {"date": "2026-11-23", "price": 33000, "change_7d_pct": 3.1, "change_30d_pct": 10.0},
            "brand_new": {"date": "2026-10-25", "price": 35000, "change_7d_pct": None, "change_30d_pct": None},
        })
        self.assertEqual(facts["capacities"]["512GB"]["trends"], {"used": None, "brand_new": None})
        self.assertEqual(facts["apple"], apple)
        self.assertFalse(facts["insufficient_samples"])
        self.assertTrue(result["models"][other]["insufficient_samples"])
        self.assertTrue(result["models"][no_sales]["insufficient_samples"])
        self.assertNotIn("apple", result["models"][other])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("example.test", serialized)
        self.assertNotIn("原文與賣家帳號", serialized)

    def test_validate_lengths_and_whitespace(self):
        for length in (249, 250, 300, 301):
            with self.subTest(length=length):
                body = "  價　" * 120 + "\n\n" + "格" * (length - 120)
                errors = C.validate(commentary({MODEL: body}), [MODEL])
                self.assertEqual(bool(errors), length in (249, 301))

    def test_validate_rejects_disclaimer_wording(self):
        body = "價" * 260 + "這個數字僅供參考"
        errors = C.validate(commentary({MODEL: body}), [MODEL])
        self.assertTrue(any("免責" in e for e in errors))

    def test_validate_missing_model_and_invalid_text(self):
        for suffix in ("#", "*", "`", "|", "\n格", "\n\n\n格"):
            with self.subTest(suffix=suffix):
                errors = C.validate(commentary({MODEL: "價" * 250 + suffix}), [MODEL])
                self.assertIn("Markdown", errors[0])
        for url in ("https://example.com", "www.example.com", "example.com/price"):
            with self.subTest(url=url):
                errors = C.validate(commentary({MODEL: "價" * 250 + url}), [MODEL])
                self.assertIn("網址", errors[0])
        errors = C.validate(commentary({MODEL: 250}), [MODEL, "iPhone 17"])
        self.assertEqual(len(errors), 2)
        self.assertIn("iPhone 17 缺少短評", errors)
        self.assertTrue(C.validate(None, [MODEL]))
        self.assertEqual(len(C.validate({"month": "2026-13", "as_of": "2026-11-31", "models": []}, [])), 3)

    def test_load_and_keep_commentary_out_of_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(C.load_commentary(root))
            before = build_site.build_data(root)
            path = root / "commentary" / "price.json"
            path.parent.mkdir()
            draft = commentary({MODEL: "價" * 250})
            path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(C.load_commentary(root), draft)
            after = build_site.build_data(root)
            self.assertEqual(after["commentary"], draft)
            self.assertEqual(build_site.home_payload(before), build_site.home_payload(after))
            self.assertEqual(build_site.model_payload(before, MODEL), build_site.model_payload(after, MODEL))

    def test_render_escapes_text_and_keeps_section_order_and_asset_paths(self):
        template = (SITE / "model.html").read_text(encoding="utf-8")
        data = dict(model_totals=[STATS], models=[], listings=[])
        canonical = "https://example.test/models/iphone-18-pro"
        for draft in (None, commentary({"iPhone 17": "價" * 250}), commentary({MODEL: " "})):
            with self.subTest(draft=draft):
                data["commentary"] = draft
                html = render_model_html(template, data, MODEL, canonical)
                self.assertNotIn('id="price-commentary"', html)
        data["commentary"] = commentary({MODEL: '<script src="model.js">&</script>\n\n第二段'})
        html = render_model_html(template, data, MODEL, canonical, asset_prefix="../")
        kpis = html.index('id="kpis"')
        card = html.index('id="price-commentary"')
        trend = html.index('id="trend-card"')
        self.assertLess(html.index("</section>", kpis), card)
        self.assertLess(html.index("</section>", card), trend)
        self.assertIn('&lt;script src=&quot;model.js&quot;&gt;&amp;&lt;/script&gt;\n\n第二段', html)
        self.assertIn('src="../model.js"', html)
        self.assertIn(f'資料更新至 {AS_OF}。', html)
