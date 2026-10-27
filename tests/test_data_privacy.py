"""公開建置不得帶出原始 CSV、未知欄位或內部抓取錯誤。"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site'))
import build_site as S
import jp_build as J


class DataPrivacyTests(unittest.TestCase):
    def test_rebuild_removes_stale_downloads_without_changing_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, out = root / 'input', root / 'output'
            source.mkdir()
            raw = source / 'listings.csv'
            raw.write_text('source_url,body_hash,notes\nhttps://example.com,PRIVATE_HASH,PRIVATE_NOTE\n')
            before = raw.read_bytes()
            stale = out / 'data/jp/runs.csv'
            stale.parent.mkdir(parents=True)
            stale.write_text('PRIVATE_ERROR')
            (out / 'data/listings.csv').write_bytes(before)
            S.build(out, source)
            self.assertEqual(raw.read_bytes(), before)
            self.assertFalse((out / 'data').exists())
            self.assertEqual(list(out.rglob('*.csv')), [])
            for path in out.rglob('*.json'):
                text = path.read_text()
                for private in ('PRIVATE_HASH', 'PRIVATE_NOTE', 'PRIVATE_ERROR'):
                    self.assertNotIn(private, text)
            self.assertTrue((out / '404.html').exists())

    def test_refuses_output_that_would_delete_source_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            source = out / 'data'
            source.mkdir()
            raw = source / 'listings.csv'
            raw.write_text('source_url\nprivate\n')
            with self.assertRaises(ValueError):
                S.build(out, source)
            self.assertEqual(raw.read_text(), 'source_url\nprivate\n')

    def test_jp_allowlist_excludes_carriers_unknown_columns_and_raw_logs(self):
        base = dict(shop='mobile-mix', model='iPhone 18 Pro', storage='256GB',
                    condition='未開封', carrier='SIMフリー', color='', price_jpy=200000,
                    raw_note='PRIVATE_NOTE', error='PRIVATE_ERROR')
        rows = J.public_rows([base, {**base, 'carrier': 'docomo'}, {**base, 'model': 'unlisted'}], J.LATEST_FIELDS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['price_jpy'], 200000)
        self.assertNotIn('raw_note', rows[0])
        self.assertNotIn('error', rows[0])
        runs = J.public_runs([
            dict(shop='mobile-mix', run_at='2026-10-01T00:00:00+09:00', status='ok', rows='3', error='secret'),
            dict(shop='mobile-mix', run_at='2026-10-02T00:00:00+09:00', status='parse_error', error='old error'),
            dict(shop='mobile-mix', run_at='2026-10-26T00:00:00+09:00', status='fetch_error', error='secret'),
        ])
        self.assertEqual([r['status'] for r in runs], ['ok', 'fetch_error'])
        self.assertTrue(all(set(r) == {'shop', 'run_at', 'status'} for r in runs))
