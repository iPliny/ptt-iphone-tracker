"""資料 checkout 必須獨立，拒絕回退到外層程式庫。"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('check_data_checkout', Path(__file__).resolve().parents[1] / '.github/check_data_checkout.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DataCheckoutTest(unittest.TestCase):
    def git(self, directory, *args):
        subprocess.run(['git', '-C', str(directory), *args], check=True, capture_output=True)

    def test_refuses_parent_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, 'init')
            (root / 'data').mkdir()
            with self.assertRaisesRegex(ValueError, '獨立'):
                module.check(root / 'data')

    def test_origin_and_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.git(root, 'init')
            self.git(root, 'remote', 'add', 'origin', 'https://github.com/iPliny/ptt-iphone-tracker.git')
            with self.assertRaisesRegex(ValueError, 'origin'):
                module.check(root)
            self.git(root, 'remote', 'set-url', 'origin', 'https://github.com/iPliny/ptt-iphone-data.git')
            with self.assertRaisesRegex(ValueError, '必要資料'):
                module.check(root)
            for name in ('listings.csv', 'events.csv', 'jp/latest.csv', 'jp/prices.csv'):
                p = root / name
                p.parent.mkdir(exist_ok=True)
                p.write_text('synthetic_header\n')
            module.check(root)
