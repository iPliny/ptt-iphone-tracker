"""販賣價只使用合成資料，不讀私人 checkout。"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))
import jp_build as B
import jp_pages as P


def sell(condition='中古B', price=120000, **extra):
    return dict(shop='イオシス', model='iPhone 18 Pro', storage='256GB', condition=condition,
                carrier='SIMフリー', price_jpy=price, last_checked='2026-11-08T09:00:00+09:00',
                source_url='https://iosys.co.jp/items/123', **extra)


class SellTest(unittest.TestCase):
    def test_minimum_by_condition_capacity_and_model(self):
        rows = [sell('中古A', 140000), sell('中古B', 130000), sell('中古C', 120000),
                sell('未使用品', 180000), sell('未使用品', 175000)]
        rows += [dict(sell(), storage='512GB', price_jpy=150000),
                 dict(sell(), carrier='docomo', price_jpy=1),
                 dict(sell(), model='iPhone 17', price_jpy=1), sell(price=0)]
        self.assertEqual([r['price_jpy'] for r in P.sell_minima(rows, 'iPhone 18 Pro', '中古上限')], [120000, 150000])
        self.assertEqual(P.sell_minima(rows, 'iPhone 18 Pro', '未開封')[0]['price_jpy'], 175000)
        self.assertEqual(P.sell_minima(rows, 'iPhone Air', '未開封'), [])

    def test_equal_price_prefers_grade_then_url(self):
        rows = [dict(sell(grade), source_url='https://iosys.co.jp/items/' + suffix)
                for grade, suffix in [('中古C', '0'), ('中古B', '1'), ('中古A', 'z'), ('中古A', 'a')]]
        best = P.sell_minima(rows, 'iPhone 18 Pro', '中古上限')[0]
        self.assertEqual((best['condition'], best['source_url']),
                         ('中古A', 'https://iosys.co.jp/items/a'))

    def test_checked_time_and_runs_fallback(self):
        runs = [dict(shop='イオシス', status='ok', run_at='2026-11-10T09:00:01+09:00'),
                dict(shop='イオシス', status='fetch_error', run_at='2026-11-20T09:00:00+09:00')]
        for lang in ('zh', 'ja'):
            with self.subTest(lang=lang):
                payload = dict(sell=[sell()], runs=runs)
                html = P.sell_block(payload, 'iPhone 18 Pro', '中古上限', P.TEXT[lang])
                self.assertIn('jp-outdated', html)
                self.assertIn('<small>確認：2026-11-08 09:00（日本時間）</small>', html)
                payload['runs'] = [dict(runs[0], run_at='2026-11-10T09:00:00+09:00'), runs[1]]
                self.assertNotIn('jp-outdated', P.sell_block(payload, 'iPhone 18 Pro', '中古上限', P.TEXT[lang]))
                for value in ('', 'invalid', None, '2026-11-08T09:00:00'):
                    payload['sell'] = [dict(sell(), last_checked=value)]
                    html = P.sell_block(payload, 'iPhone 18 Pro', '中古上限', P.TEXT[lang])
                    self.assertIn('<small>確認：—（日本時間）</small>', html)
                    self.assertNotIn('jp-outdated', html)
                    self.assertNotIn(P.TEXT[lang]['stale'], html)

    def test_stale_boundary_and_product_links_both_languages(self):
        for lang, label in [('zh', '舊資料'), ('ja', '古いデータ')]:
            for at, stale in [('2026-11-10T09:00:00+09:00', False), ('2026-11-10T09:00:01+09:00', True)]:
                payload = dict(sell=[sell()], generated_at=at)
                html = P.sell_block(payload, 'iPhone 18 Pro', '中古上限', P.TEXT[lang])
                self.assertEqual(label in html, stale)
                self.assertEqual('jp-outdated' in html, stale)
                self.assertIn('href="https://iosys.co.jp/items/123"', html)
                self.assertIn('中古B', html)
                self.assertIn('¥120,000', html)
                payload['sell'][0]['source_url'] = 'https://iosys.co.jp.evil.test/'
                self.assertNotIn('<a ', P.sell_block(payload, 'iPhone 18 Pro', '中古上限', P.TEXT[lang]))

    def test_build_absent_empty_and_allowlist(self):
        for mode in ('missing', 'empty', 'header', 'data'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / 'input/jp/sell'
                source.mkdir(parents=True)
                if mode != 'missing':
                    with (source / 'latest.csv').open('w') as stream:
                        if mode != 'empty':
                            row = sell(color='secret', since='secret', shop_updated='secret', internal='secret')
                            writer = csv.DictWriter(stream, fieldnames=list(row))
                            writer.writeheader()
                            if mode == 'data':
                                writer.writerow(row)
                                writer.writerow(dict(row, carrier='docomo'))
                payload = B.build_jp(root / 'output', root / 'input')
                self.assertEqual(len(payload['sell']), 1 if mode == 'data' else 0)
                for row in payload['sell']:
                    self.assertEqual(set(row), set(B.SELL_FIELDS))
                P.render_jp_pages(root / 'output', payload, 'https://example.test/')
                html = (root / 'output/jp/index.html').read_text()
                # 只有中古資料，主頁預設未開封不顯示販賣區。
                self.assertNotIn('イオシス販賣價（最低）', html)
                self.assertEqual(payload['latest'], [])

    def test_static_home_and_model_include_sell(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = B.build_jp(root / 'output', root / 'input')
            payload.update(sell=[sell('未使用品', 180000), sell('中古C', 120000)],
                           latest=[dict(sell(), condition='未開封', color='')])
            P.render_jp_pages(root / 'output', payload, 'https://example.test/')
            for lang, path in [('zh', ''), ('ja', 'ja/')]:
                home = (root / f'output/jp/{path}index.html').read_text()
                page = (root / f'output/jp/{path}iphone-18-pro/index.html').read_text()
                self.assertIn(P.TEXT[lang]['sell'], home)
                self.assertLess(home.index('最高價以底色' if lang == 'zh' else '最高価格は背景色'),
                                home.index('<div id="sell">'))
                self.assertIn('¥180,000', home)
                self.assertIn('¥120,000', page)
                self.assertIn('data-model-cond="中古上限"', page)
