"""歷史價目的公開範圍、安全限制，以及靜態建置回歸測試（離線）。"""
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ('prices.html', 'prices.js', 'prices.css', 'official-prices.json')


class OfficialPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / 'site/official-prices.json').read_text(encoding='utf-8')
        cls.data = json.loads(cls.text)
        cls.rows = [dict(zip(cls.data['columns'], row)) for row in cls.data['records']]

    def test_snapshot_coverage_and_unique_keys(self):
        self.assertEqual(self.data['schema_version'], 1)
        self.assertEqual(len(self.rows), 171)
        self.assertEqual(len({r['model'] for r in self.rows}), 52)
        self.assertEqual(self.data['withheld_records'], 12)
        self.assertEqual(Counter(r['section'] for r in self.rows), {'tw-launch': 152, 'tw-later': 15, 'us': 4})
        self.assertEqual(Counter(r['evidence'] for r in self.rows), {'A': 57, 'B': 6, 'C': 105, 'F': 1, 'N': 2})
        keys = {(r['section'], r['model'], r['storage'], r['price_type'], r['effective_date']) for r in self.rows}
        self.assertEqual(len(keys), len(self.rows))
        for row in self.data['records']:
            self.assertEqual(len(row), len(self.data['columns']))

    def test_pending_amounts_never_shipped(self):
        for r in self.rows:
            with self.subTest(model=r['model'], storage=r['storage']):
                if r['evidence'] not in ('A', 'B'):
                    self.assertIsNone(r['amount'])
                else:
                    self.assertIs(type(r['amount']), int)
                    self.assertGreater(r['amount'], 0)
        self.assertNotIn('iPhone Duo', self.text)
        self.assertNotIn('iphone-18', self.text.lower())
        for marker in ('docs.google.com', 'drive.google.com', '@gmail.com', '1U9eovyf'):
            self.assertNotIn(marker, self.text)

    def test_each_source_has_correct_publisher_and_public_https_url(self):
        for r in self.rows:
            url = urlsplit(self.data['sources'][r['source_id']])
            self.assertEqual(url.scheme, 'https')
            self.assertFalse(url.username or url.password)
            if r['evidence'] == 'A':
                self.assertEqual(url.hostname, 'www.apple.com')
            if r['evidence'] == 'B':
                self.assertEqual(url.hostname, 'corp.taiwanmobile.com')

    def test_exact_capacity_not_starting_price_fallback(self):
        rows = {r['storage']: r for r in self.rows if r['model'] == 'iPhone 16 Pro' and r['section'] == 'tw-launch'}
        self.assertEqual(rows['128GB']['amount'], 36900)
        self.assertIsNone(rows['256GB']['amount'])
        self.assertIsNone(rows['1TB']['amount'])

    def test_later_capacity_and_us_are_not_launch_price(self):
        later = next(r for r in self.rows if r['model'] == 'iPhone SE（第1代）' and r['storage'] == '32GB')
        self.assertEqual(later['section'], 'tw-later')
        self.assertEqual(later['effective_date'], '2017-03-24')
        us16 = next(r for r in self.rows if r['section'] == 'us' and r['storage'] == '16GB')
        self.assertEqual(us16['price_type'], '後增容量')
        self.assertEqual(us16['amount'], 499)
        self.assertTrue(all(r['amount'] is None for r in self.rows if r['section'] == 'tw-launch' and r['model'] == 'iPhone（初代）'))

    def test_homepage_links_to_prices_and_page_returns_home(self):
        self.assertIn('href="prices.html"', (ROOT / 'site/index.html').read_text(encoding='utf-8'))
        html = (ROOT / 'site/prices.html').read_text(encoding='utf-8')
        for text in ('href="./"', 'src="prices.js"', 'href="prices.css"', 'role="alert"', 'noscript'):
            self.assertIn(text, html)
        self.assertNotIn('docs.google.com', html)
        self.assertLess(html.index('gtag/js?id=G-G3GH12TQSZ'), html.index('<title>'))
        self.assertIn('PTT MacShop交易觀測', html)
        self.assertNotIn('PTT每日交易觀測', html)
        self.assertIn('href="prices.html"', (ROOT / 'site/model.html').read_text(encoding='utf-8'))

    def test_build_copies_assets_without_changing_market_schema(self):
        spec = importlib.util.spec_from_file_location('price_test_build', ROOT / 'site/build_site.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for asset in ASSETS:
            self.assertIn(asset, module.STATIC_FILES)
        # 新增功能的離線 fixture：只複製本功能的真實檔案，行情輸入為空。
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'out'
            with patch.object(module, 'STATIC_FILES', ASSETS):
                result = module.build(str(out), str(Path(directory) / 'empty-input'))
            for asset in ASSETS:
                self.assertEqual((out / asset).read_bytes(), (ROOT / 'site' / asset).read_bytes())
            self.assertEqual(result['counts']['total'], 0)
            self.assertNotIn('official_prices', result)
            self.assertEqual(json.loads((out / 'data.json').read_text(encoding='utf-8')), result)


if __name__ == '__main__':
    unittest.main()
