"""日本買取價的離線回歸測試；只使用 fixture 與 TemporaryDirectory。"""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from jp import buyback as jp

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "jp"
T0, T1, T2, T3, T4 = [f"2026-10-0{d}T09:30:00+09:00" for d in range(1, 6)]


def fixture(name):
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def find(rows, model="iPhone 18 Pro", storage="256GB", condition="未開封", carrier="SIMフリー", color=""):
    return next(r for r in rows if [r[k] for k in jp.KEY[1:]] == [model, storage, condition, carrier, color])


def result(shop, rows, **kwargs):
    return dict(shop=shop, rows=copy.deepcopy(rows), status="ok", **kwargs)


class ParserTests(unittest.TestCase):
    def test_mobilemix_actual_rows_and_color_exclusions(self):
        rows, updated = jp.parse_mobilemix(fixture("mobilemix"))
        self.assertEqual(updated, "2026-10-07")
        self.assertEqual(len(rows), 26)
        self.assertEqual({r["model"] for r in rows}, {"iPhone 18 Pro", "iPhone 18 Pro Max"})
        self.assertEqual(find(rows)["price_jpy"], 212000)
        self.assertEqual(find(rows, color="グレイシャー")["price_jpy"], 197000)
        self.assertEqual(find(rows, model="iPhone 18 Pro Max", color="シルバー")["price_jpy"], 221000)
        self.assertFalse(any(r["color"] == "シルバー" and r["model"] == "iPhone 18 Pro" and r["storage"] == "256GB" for r in rows))
        only = [r["color"] for r in rows if r["model"] == "iPhone 18 Pro" and r["storage"] == "1TB"]
        self.assertEqual(only, ["", "バーガンディ"])

    def test_iosys_groups_new_and_used_upper(self):
        rows, updated = jp.parse_iosys(fixture("iosys-pro"), jp.IOSYS_URLS[0])
        self.assertEqual(updated, "")
        self.assertEqual(len(rows), 16)
        self.assertEqual(find(rows, carrier="docomo")["price_jpy"], 192000)
        self.assertEqual(find(rows, condition="中古上限")["price_jpy"], 182000)
        self.assertEqual(find(rows, storage="2TB")["price_jpy"], 360000)
        rows, _ = jp.parse_iosys(fixture("iosys-max"), jp.IOSYS_URLS[1])
        self.assertEqual(find(rows, model="iPhone 18 Pro Max")["price_jpy"], 210000)
        self.assertEqual({r["model"] for r in rows}, {"iPhone 18 Pro Max"})

    def test_amemoba_groups_date_and_new_synonym(self):
        rows, updated = jp.parse_amemoba(fixture("amemoba-pro"), jp.AMEMOBA_URLS[0])
        self.assertEqual(updated, "2026-10-05")
        self.assertEqual(len(rows), 16)
        self.assertEqual(find(rows)["price_jpy"], 200000)
        self.assertEqual(find(rows, carrier="au")["price_jpy"], 192000)
        self.assertEqual(find(rows, condition="中古上限")["price_jpy"], 187000)
        html = fixture("amemoba-max").replace("未開封買取価格", "新品買取価格")
        rows, _ = jp.parse_amemoba(html, jp.AMEMOBA_URLS[1])
        self.assertEqual(find(rows, model="iPhone 18 Pro Max", storage="2TB")["price_jpy"], 390000)

    def test_other_models_ignored_and_carriers_normalized(self):
        for parser, name, url in [(jp.parse_iosys, "iosys-pro", jp.IOSYS_URLS[0]), (jp.parse_amemoba, "amemoba-pro", jp.AMEMOBA_URLS[0])]:
            for replace in ("17", "18 Air", "18 Pro Ultra"):
                with self.subTest(name=name, replace=replace):
                    rows, _ = parser(fixture(name).replace("18", replace), url)
                    self.assertEqual(rows, [])
        for label, carrier in [("au版SIMフリー", "au"), ("docomo版SIMフリー", "docomo"), ("SoftBank版", "SoftBank"), ("国内版SIMフリー", "SIMフリー"), ("Rakuten版SIMフリー", "Rakuten"), ("楽天モバイル版SIMフリー", "Rakuten")]:
            self.assertEqual(jp.carrier_name(label), carrier)

    def test_missing_price_is_error_not_delisting(self):
        for parser, name, url, selector in [(jp.parse_iosys,"iosys-pro",jp.IOSYS_URLS[0],"s-price"), (jp.parse_amemoba,"amemoba-pro",jp.AMEMOBA_URLS[0],"p-purchaseArchive__priceNew")]:
            with self.assertRaises(jp.ParseError):
                parser(fixture(name).replace(selector, "changed-layout"), url)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "jp"
        self.rows, _ = jp.parse_mobilemix(fixture("mobilemix"))

    def read(self, name):
        return jp.read_csv(self.directory / f"{name}.csv")

    def write(self, rows, at, extra=()):
        return jp.apply_results(self.directory, [result("mobile-mix", rows), *extra], at)

    def test_unchanged_changed_removed_and_returned(self):
        self.write(self.rows, T0)
        first = (self.directory / "prices.csv").read_bytes()
        self.write(self.rows, T1)
        self.assertEqual((self.directory / "prices.csv").read_bytes(), first)
        self.assertEqual({r["since"] for r in self.read("latest")}, {T0})
        self.assertEqual({r["last_checked"] for r in self.read("latest")}, {T1})
        changed = copy.deepcopy(self.rows)
        changed[0]["price_jpy"] += 1000
        self.write(changed, T2)
        self.assertEqual(len(self.read("prices")), len(self.rows) + 1)
        self.assertTrue((self.directory / "prices.csv").read_bytes().startswith(first))
        self.assertEqual(self.read("prices")[-1]["price_jpy"], str(changed[0]["price_jpy"]))
        self.assertEqual(next(r for r in self.read("latest") if jp.row_key(r) == jp.row_key(changed[0]))["since"], T2)
        self.write(changed[1:], T3)
        self.assertEqual(self.read("prices")[-1]["price_jpy"], "")
        self.assertNotIn(jp.row_key(changed[0]), {jp.row_key(r) for r in self.read("latest")})
        self.write(changed, T4)
        self.assertEqual(len(self.read("prices")), len(self.rows) + 3)
        self.assertEqual(next(r for r in self.read("latest") if jp.row_key(r) == jp.row_key(changed[0]))["since"], T4)

    def test_failed_shop_frozen_while_other_shop_updates(self):
        iosys, _ = jp.parse_iosys(fixture("iosys-pro"), jp.IOSYS_URLS[0])
        self.write(self.rows, T0, [result("イオシス", iosys)])
        original_latest = [r for r in self.read("latest") if r["shop"] == "mobile-mix"]
        original_prices = [r for r in self.read("prices") if r["shop"] == "mobile-mix"]
        for bad in ([], self.rows[:len(self.rows)//2], self.rows[:5]):
            iosys[0]["price_jpy"] += 1000
            runs = self.write(bad, T1, [result("イオシス", iosys)])
            self.assertEqual([r["status"] for r in runs], ["parse_error", "ok"])
            self.assertEqual([r for r in self.read("latest") if r["shop"] == "mobile-mix"], original_latest)
            self.assertEqual([r for r in self.read("prices") if r["shop"] == "mobile-mix"], original_prices)
        self.assertEqual(self.read("runs")[-2]["status"], "parse_error")

    def test_fetch_error_preserves_files_byte_for_byte(self):
        self.write(self.rows, T0)
        before = {name: (self.directory/name).read_bytes() for name in ("prices.csv", "latest.csv")}
        jp.apply_results(self.directory, [dict(shop="mobile-mix", status="fetch_error", rows=[], error="timeout")], T1)
        self.assertEqual(before, {name: (self.directory/name).read_bytes() for name in before})
        self.assertEqual(self.read("runs")[-1]["status"], "fetch_error")

    def test_duplicate_conflicting_keys_are_rejected(self):
        changed = copy.deepcopy(self.rows[0]); changed["price_jpy"] += 1
        runs = self.write([*self.rows, changed], T0)
        self.assertEqual(runs[0]["status"], "parse_error")
        self.assertFalse((self.directory/"prices.csv").exists())

    def test_timestamp_is_tokyo_even_with_utc_input(self):
        jp.apply_results(self.directory, [result("mobile-mix", self.rows)], "2026-10-01T00:30:00+00:00")
        self.assertEqual(self.read("prices")[0]["observed_at"], T0)
        with self.assertRaises(ValueError):
            self.write(self.rows, "2026-10-01T09:30:00")

    def test_recovery_with_history_but_missing_latest(self):
        self.write(self.rows, T0)
        (self.directory/"latest.csv").unlink()
        self.write(self.rows, T1)
        self.assertEqual(len(self.read("prices")), len(self.rows))
        self.assertEqual({r["since"] for r in self.read("latest")}, {T0})


class FetchAndBuildTests(unittest.TestCase):
    def test_fetch_spacing_retry_and_headers(self):
        clock = [0]
        calls = []
        def sleep(seconds):
            clock[0] += seconds
        def request(url, **kwargs):
            calls.append((clock[0], url, kwargs))
            if len(calls) == 2:
                raise jp.requests.RequestsError("fixture timeout")
            return Mock(text="fixture", raise_for_status=Mock())
        with patch.object(jp, "_last_request", None), patch.object(jp, "_host_requests", {}), patch.object(jp.time, "monotonic", side_effect=lambda:clock[0]), patch.object(jp.time, "sleep", side_effect=sleep), patch.object(jp.requests, "get", side_effect=request):
            jp.fetch(jp.MOBILEMIX_URL)
            jp.fetch(jp.IOSYS_URLS[0])
            jp.fetch(jp.IOSYS_URLS[1])
            jp.fetch(jp.AMEMOBA_URLS[0])
        self.assertEqual([c[0] for c in calls], [0, 5, 65, 125, 130])
        for _, _, kwargs in calls:
            self.assertEqual(kwargs["impersonate"], "chrome")
            self.assertEqual(kwargs["headers"]["Accept-Language"], "ja-JP,ja;q=0.9")

    def test_partial_shop_failure_does_not_write_half_a_shop(self):
        lookup={jp.MOBILEMIX_URL:"mobilemix", jp.IOSYS_URLS[0]:"iosys-pro", jp.AMEMOBA_URLS[0]:"amemoba-pro", jp.AMEMOBA_URLS[1]:"amemoba-max"}
        def fetch(url):
            if url == jp.IOSYS_URLS[1]:
                raise RuntimeError("fixture failure")
            return fixture(lookup[url])
        results=jp.collect(fetch)
        self.assertEqual([r["status"] for r in results], ["ok", "fetch_error", "ok"])
        with tempfile.TemporaryDirectory() as directory:
            jp.apply_results(directory, results, T0)
            self.assertEqual({r["shop"] for r in jp.read_csv(Path(directory)/"latest.csv")}, {"mobile-mix", "アメモバ"})
        results=jp.collect(lambda url: "<html>blocked</html>" if url in jp.IOSYS_URLS else fixture(lookup[url]))
        self.assertEqual(results[1]["status"], "parse_error")

    def test_dry_run_does_not_create_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/"not-created"
            with patch.object(sys, "argv", ["buyback.py", "--dry-run", "--data", str(target)]), patch.object(jp,"collect",return_value=[result("mobile-mix", [])]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(jp.main(), 0)
            self.assertFalse(target.exists())

    def test_build_without_jp_and_with_empty_jp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); data=root/"input"; out=root/"site"; data.mkdir()
            for empty in (False, True):
                if empty:
                    (data/"jp").mkdir()
                    for name in ("latest", "prices", "runs"):
                        (data/"jp"/f"{name}.csv").touch()
                subprocess.run([sys.executable,str(ROOT/"site/build_site.py"),"--data",str(data),"--out",str(out)],check=True,capture_output=True)
                payload=json.loads((out/"jp/data.json").read_text())
                self.assertEqual(payload["latest"], [])
                self.assertEqual(payload["prices"], [])
                self.assertIn("資料準備中", (out/"jp/index.html").read_text())
                self.assertIn("https://ipliny.github.io/ptt-iphone-tracker/jp/",(out/"sitemap.xml").read_text())
                ja=(out/"jp/ja/index.html").read_text()
                self.assertIn('<html lang="ja">', ja)
                self.assertIn('data-base="../"', ja)
                self.assertIn("G-G3GH12TQSZ", ja)
                self.assertIn("https://ipliny.github.io/ptt-iphone-tracker/jp/ja/",(out/"sitemap.xml").read_text())

    def test_build_jp_downloads_and_keeps_taiwan_json_unchanged(self):
        sys.path.insert(0,str(ROOT/"site"))
        import build_site
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); data=root/"input"; data.mkdir()
            before=build_site.build_data(data, now=jp.datetime(2026,10,7))
            rows,_=jp.parse_mobilemix(fixture("mobilemix"))
            jp.apply_results(data/"jp",[result("mobile-mix", rows)],T0)
            after=build_site.build_data(data, now=jp.datetime(2026,10,7))
            self.assertEqual(before,after)
            build_site.build(root/"out",data)
            payload=json.loads((root/"out/jp/data.json").read_text())
            self.assertEqual(len(payload["latest"]),26)
            self.assertIsInstance(payload["latest"][0]["price_jpy"],int)
            for name in ("latest", "prices", "runs"):
                self.assertEqual((data/"jp"/f"{name}.csv").read_bytes(),(root/"out/data/jp"/f"{name}.csv").read_bytes())
