"""分享資訊、真實 sitemap 日期與標準網址的離線驗收。"""
import json
import struct
import sys
import tempfile
import unittest
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))
import blog as B
import build_site as S
import column as C
from tests.test_jp_pages import row as jp_row
from tests.test_site import LISTING_HEADER, S_EVENT_HEADER, listing, write_csv


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.metas, self.canonicals = {}, []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name')
            self.metas.setdefault(key, []).append(attrs.get('content'))
        elif tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))


def entries(xml):
    root = ET.fromstring(xml)
    return {u.findtext('{*}loc'): u.findtext('{*}lastmod') for u in root.findall('{*}url')}


class SocialSitemapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data, self.out = Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'out'
        self.data.mkdir()
        rows = [listing('u1', '2026-09-27 10:00:00'), listing('u2', '2026-10-01 10:00:00', model='iPhone 17 Pro')]
        rows[0]['last_checked'] = '2026-10-10 12:00:00'
        rows[1]['last_checked'] = '2026-10-11 12:00:00'
        write_csv(self.data / 'listings.csv', LISTING_HEADER, rows)
        write_csv(self.data / 'events.csv', S_EVENT_HEADER,
                  [{'time': '2026-10-10 11:00:00', 'source_url': 'u1', 'event': '價格變動', 'detail': '11000 → 10000'}])

    def all_sections(self):
        (self.data / 'column').mkdir()
        issue = C.compute_issue(str(self.data), date(2026, 9, 27), date(2026, 10, 3), now=datetime(2026, 10, 4, 12))
        (self.data / 'column/2026-09-27.json').write_text(json.dumps(issue), encoding='utf-8')
        posts, _ = B.parse_feed((Path(__file__).parent / 'fixtures/blog/feed.atom').read_text())
        B.sync(posts, str(self.data / 'blog'))
        (self.data / 'weekly').mkdir()
        native = {'id': '2026-10-18', 'title': '本站週報', 'published': '2026-10-18T12:00:00+08:00',
                  'updated': '2026-10-18T18:00:00Z', 'description': '本期說明', 'labels': [], 'html': '<p>本期內容</p>'}
        (self.data / 'weekly/2026-10-18.json').write_text(json.dumps(native), encoding='utf-8')
        (self.data / 'jp').mkdir()
        row = jp_row('アメモバ', 173000, last_checked='2026-10-18T00:30:00+09:00')
        write_csv(self.data / 'jp/latest.csv', list(row), [row])

    def test_share_image_dimensions_and_budget(self):
        image = (Path(S.SITE_DIR) / 'og.png').read_bytes()
        self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', image[16:24]), (1200, 630))
        self.assertLessEqual(len(image), 100_000)

    def test_source_dates_are_valid_and_converted_to_taipei(self):
        self.assertEqual(S.sitemap_day('2026-10-18T00:30:00+09:00'), '2026-10-17')
        self.assertEqual(S.sitemap_day('2026-10-17T18:00:00Z'), '2026-10-18')
        for value in (None, '', 'unknown', '2026-02-30', '2026-00-01'):
            self.assertEqual(S.sitemap_day(value), '')

    def test_sitemap_uses_content_dates_and_omits_unknown_dates(self):
        data = {'last_checked': '2026-10-08 12:00:00', 'days': [{'date': '2026-10-07'}],
                'model_totals': [{'model': 'iPhone 15'}, {'model': 'iPhone 7'}],
                'listings': [{'url': 'u', 'model': 'iPhone 15', 'post_time': '2026-10-01',
                              'last_checked': '2026-10-04'}],
                'events': [{'url': 'u', 'time': '2026-10-05T20:00:00Z'}]}
        xml = S.sitemap_xml(data, today=date(2099, 1, 1), column_urls=[S.SITE_URL + 'column/'])
        urls = entries(xml)
        self.assertEqual(urls[S.SITE_URL], '2026-10-08')
        self.assertEqual(urls[S.SITE_URL + 'market/'], '2026-10-08')
        self.assertEqual(urls[S.SITE_URL + 'models/iphone-15.html'], '2026-10-06')
        self.assertIsNone(urls[S.SITE_URL + 'models/iphone-7.html'])
        self.assertIsNone(urls[S.SITE_URL + 'jp/'])
        self.assertIsNone(urls[S.SITE_URL + 'prices.html'])
        self.assertNotIn(S.SITE_URL + 'column/', urls)
        self.assertNotIn('2099', xml)

    def test_catalogue_uses_updated_at_and_omits_missing_check_date(self):
        catalogue = Path(self.tmp.name) / 'catalogue'
        catalogue.mkdir()
        path = catalogue / 'official-prices.json'
        with patch.object(S, 'SITE_DIR', str(catalogue)):
            for raw, expected in (({'updated_at': '2025-01-03'}, '2025-01-03'), ({}, None)):
                path.write_text(json.dumps(raw))
                result = S.sitemap_lastmods({'model_totals': []}, str(self.data))
                self.assertEqual(result.get(S.SITE_URL + 'prices.html'), expected)

    def test_all_built_pages_have_one_social_set_and_canonical_url(self):
        self.all_sections()
        for base in (S.SITE_URL, 'https://example.test/preview/'):
            with self.subTest(base=base), patch.object(S, 'SITE_URL', base):
                S.build(str(self.out), str(self.data))
                pages = list(self.out.rglob('*.html'))
                for path in pages:
                    if path.name == '404.html':
                        self.assertIn('noindex', path.read_text(encoding='utf-8'))
                        continue
                    with self.subTest(page=path.relative_to(self.out)):
                        head = Head(path.read_text(encoding='utf-8'))
                        for key in ('og:type', 'og:title', 'og:description', 'og:url', 'og:site_name',
                                    'og:locale', 'og:image', 'twitter:card'):
                            self.assertEqual(len(head.metas.get(key, [])), 1, key)
                        self.assertEqual(head.metas['og:image'], [base + 'og.png'])
                        self.assertEqual(head.metas['twitter:card'], ['summary_large_image'])
                        locale = 'ja_JP' if '/jp/ja/' in str(path) else 'zh_TW'
                        self.assertEqual(head.metas['og:locale'], [locale])
                        if path == self.out / 'model.html':
                            # 舊入口尚未給定 m；canonical 與 og:url 由 model.js 同步設定。
                            self.assertEqual(head.canonicals, [])
                            self.assertEqual(head.metas['og:url'], [''])
                        else:
                            self.assertEqual(head.metas['og:url'], head.canonicals)
                self.assertTrue((self.out / 'og.png').is_file())
                self.assertTrue((self.out / 'column/2026-09-27/index.html').is_file())
                self.assertTrue((self.out / 'weekly/2026-10-18/index.html').is_file())
                self.assertTrue((self.out / 'jp/ja/iphone-17-pro/index.html').is_file())
                home = (self.out / 'index.html').read_text()
                self.assertIn('<title>PTT MacShop交易觀測｜二手 iPhone 行情與成交追蹤</title>', home)
                self.assertIn('<h1>PTT MacShop交易觀測</h1>', home)
                self.assertLessEqual(len(Head(home).metas['description'][0]), 120)

    def test_every_sitemap_url_is_self_canonical_and_blogger_urls_stay_external(self):
        self.all_sections()
        S.build(str(self.out), str(self.data))
        urls = entries((self.out / 'sitemap.xml').read_text())
        for url in urls:
            path = self.out / url.removeprefix(S.SITE_URL)
            if path.is_dir():
                path /= 'index.html'
            self.assertEqual(Head(path.read_text()).canonicals, [url], url)
        self.assertNotIn(S.SITE_URL + 'column/', urls)
        for name in ('2026-10-04', '2026-10-11'):
            head = Head((self.out / f'weekly/{name}/index.html').read_text())
            self.assertTrue(head.canonicals[0].startswith('https://tcssh.blogspot.com/'))
            self.assertNotIn(S.SITE_URL + f'weekly/{name}/', urls)

    def test_column_blog_jp_and_models_use_their_source_dates(self):
        self.all_sections()
        S.build(str(self.out), str(self.data))
        urls = entries((self.out / 'sitemap.xml').read_text())
        self.assertEqual(urls[S.SITE_URL + 'column/2026-09-27/'], '2026-10-04')
        self.assertEqual(urls[S.SITE_URL + 'weekly/2026-10-18/'], '2026-10-19')
        self.assertEqual(urls[S.SITE_URL + 'weekly/'], '2026-10-19')
        self.assertEqual(urls[S.SITE_URL + 'models/iphone-15.html'], '2026-10-10')
        for suffix in ('jp/', 'jp/ja/', 'jp/iphone-17-pro/', 'jp/ja/iphone-17-pro/'):
            self.assertEqual(urls[S.SITE_URL + suffix], '2026-10-17')

    def test_missing_jp_data_does_not_get_lastmod(self):
        S.build(str(self.out), str(self.data))
        urls = entries((self.out / 'sitemap.xml').read_text())
        self.assertIsNone(urls[S.SITE_URL + 'jp/'])
        self.assertIsNone(urls[S.SITE_URL + 'jp/ja/'])
