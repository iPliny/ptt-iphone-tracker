"""首頁在資料請求尚未完成或 JavaScript 關閉時仍能閱讀。"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))
from seo import render_home, metadata


class HomeSeoTest(unittest.TestCase):
    def setUp(self):
        self.template = (Path(__file__).resolve().parents[1] / 'site/index.html').read_text(encoding='utf-8')

    def test_no_javascript_contains_source_time_and_model_links(self):
        data = dict(last_checked='2026-10-18 08:00:00', generated_at='2099-01-01', counts={'total': 14},
                    days=[dict(date='2026-10-18', new=3, sold=2, deleted=0, price_changes=1, on_shelf=9)],
                    models=[dict(model='iPhone 17 Pro', storage='256GB', listed=4,
                                 median_price=30000, median_sold_price=None)])
        html = render_home(self.template, data, 'https://macshop.crawlsnek.com/')
        self.assertIn('最後回訪 2026-10-18 08:00:00 · 共追蹤 14 篇', html)
        self.assertNotIn('2099-01-01', html)
        self.assertIn('href="models/iphone-17-pro.html"', html)
        self.assertIn('$30,000', html)
        self.assertNotIn('$0', html)
        self.assertIn('<td>—</td>', html)
        self.assertIn('2026-10-18</div>', html)
        self.assertIn('id="model-q"', html)
        # 統計與價格取自已清理的 build_data，沒有另一套原始 CSV 讀取路徑。
        self.assertIn("gtag('config', 'G-G3GH12TQSZ')", html)
        self.assertIn('<script src="app.js">', html)

    def test_empty_data_does_not_claim_freshness_or_invent_prices(self):
        html = render_home(self.template, {}, 'https://example.test/')
        self.assertIn('尚無回訪紀錄', html)
        self.assertIn('尚無型號行情', html)
        self.assertIn('尚無每日統計', html)

    def test_structured_data_handles_untrusted_text_and_has_no_offer(self):
        tags = metadata('</script><img src=x>', '測試', 'https://example.test/',
                        [('首頁', 'https://example.test/'), ('機型', 'https://example.test/models/test.html')])
        value = re.search(r'ld\+json">(.*?)</script>', tags).group(1)
        nodes = json.loads(value)
        self.assertEqual(nodes[0]['name'], '</script><img src=x>')
        self.assertNotIn('<img', tags)
        self.assertEqual(nodes[1]['itemListElement'][1]['position'], 2)
        self.assertNotIn('Offer', tags)
