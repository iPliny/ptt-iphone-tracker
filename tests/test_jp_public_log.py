"""公開 Actions 不可從日本抓取 log 取回整列原始資料。"""
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from jp import buyback as jp


class PublicLogTest(unittest.TestCase):
    def test_dry_run_and_write_log_only_counts(self):
        result = {'shop': 'mobile-mix', 'status': 'fetch_error',
                  'rows': [{'price_jpy': 123456, 'private': 'RAW_MARKER'}],
                  'error': 'ERROR_MARKER'}
        for dry in (True, False):
            with self.subTest(dry=dry), tempfile.TemporaryDirectory() as tmp:
                args = ['buyback.py', '--data', tmp] + (['--dry-run'] if dry else [])
                out = io.StringIO()
                runs = [{'shop': 'mobile-mix', 'status': 'fetch_error', 'rows': 1, 'error': 'ERROR_MARKER'}]
                with patch('sys.argv', args), patch.object(jp, 'collect', return_value=[result]), \
                     patch.object(jp, 'apply_results', return_value=runs) as apply, contextlib.redirect_stdout(out):
                    jp.main()
                self.assertEqual(json.loads(out.getvalue()), [{'shop': 'mobile-mix', 'status': 'fetch_error', 'rows': 1}])
                self.assertEqual(apply.call_count, 0 if dry else 1)
