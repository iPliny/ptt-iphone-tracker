"""本機爬蟲離線驗證；CSV 全部位於暫存目錄。"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jp import buyback as jp
from jp import local
from jp.local_pastec import discover_pastec_pages, parse_pastec, PASTEC_INDEX

FIXTURES = Path(__file__).parent / "fixtures" / "jp"
URL = "https://pastec.net/iphone/iphone17pro256gb?purchase_type=net"
AT = "2026-10-30T09:40:00+09:00"


def fixture(name):
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def pastec_result():
    rows, updated = parse_pastec(fixture("local-pastec-17pro256"), URL)
    return dict(source="pastec", shop="モバステ", rows=rows, status="ok", shop_updated=updated)


class PastecTests(unittest.TestCase):
    def test_real_grades_and_carrier(self):
        result = pastec_result()
        self.assertEqual([(r["condition"], r["price_jpy"]) for r in result["rows"]],
                         [("未開封", 171000), ("中古上限", 143500)])
        self.assertEqual({r["carrier"] for r in result["rows"]}, {"SIMフリー"})
        self.assertEqual(result["shop_updated"], "")
        self.assertEqual(discover_pastec_pages(fixture("local-pastec-index")),
                         {URL: ("iPhone 17 Pro", "256GB")})

    def test_unknown_carrier_and_broken_price_fail(self):
        html = fixture("local-pastec-17pro256")
        for bad in (html.replace("SIMフリー", "不明"), html.replace("171,000円", "要確認"),
                    html.replace("assess__table", "changed")):
            with self.subTest(bad=bad[:40]), self.assertRaises(jp.ParseError):
                parse_pastec(bad, URL)
        rows, _ = parse_pastec(html.replace("SIMフリー", "docomo版"), URL)
        self.assertEqual({r["carrier"] for r in rows}, {"docomo"})

    def test_excluded_models_and_highest_used_not_opened_new(self):
        html = fixture("local-pastec-17pro256")
        self.assertEqual(parse_pastec(html.replace("iPhone17 Pro", "iPhone17e"), URL)[0], [])
        rows, _ = parse_pastec(html.replace("128,500円", "150,000円"), URL)
        self.assertEqual(rows[1]["price_jpy"], 150000)

    def test_collect_and_partial_page_failure(self):
        pages = {PASTEC_INDEX: fixture("local-pastec-index"), URL: fixture("local-pastec-17pro256")}
        result = local.collect(("pastec",), pages.__getitem__)[0]
        self.assertEqual((result["status"], len(result["rows"])), ("ok", 2))
        index = pages[PASTEC_INDEX].replace("iphone17pro256gb", "iphone17pro512gb").replace("256GB", "512GB")
        pages[PASTEC_INDEX] += index
        result = local.collect(("pastec",), pages.__getitem__)[0]
        self.assertEqual((result["status"], len(result["rows"])), ("fetch_error", 2))
        with tempfile.TemporaryDirectory() as tmp:
            reports = local.save_or_check(tmp, [result], run_at=AT)
            self.assertEqual(reports[0]["status"], "fetch_error")
            self.assertFalse((Path(tmp) / "prices.csv").exists())


class LocalStorageTests(unittest.TestCase):
    def test_sell_is_separate_and_buyback_defaults_unchanged(self):
        buy = pastec_result()
        sell = dict(source="iosys-sell", shop="イオシス", status="ok", rows=[
            jp.make_row("イオシス", ("iPhone 17 Pro", "256GB"), "中古A", "SIMフリー", 170000,
                        "https://iosys.co.jp/items/smartphone/iphone/iphone17_pro", "")])
        with self.assertRaises(jp.ParseError):
            jp.validate_rows("イオシス", sell["rows"], {})
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "jp"
            local.save_or_check(target, [buy, sell], run_at=AT)
            self.assertEqual({r["shop"] for r in jp.read_csv(target / "prices.csv")}, {"モバステ"})
            self.assertEqual({r["condition"] for r in jp.read_csv(target / "sell/prices.csv")}, {"中古A"})
            before = (target / "prices.csv").read_bytes()
            local.save_or_check(target, [sell], run_at=AT)
            self.assertEqual((target / "prices.csv").read_bytes(), before)

    def test_dry_run_no_files_and_summary_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing"
            output = io.StringIO()
            with patch.object(local, "collect", return_value=[pastec_result()]), contextlib.redirect_stdout(output):
                self.assertEqual(local.main(["--data", str(target), "--dry-run", "--only", "pastec"]), 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(json.loads(output.getvalue()), [dict(shop="モバステ", status="ok", rows=2)])

    def test_validation_failure_is_nonzero_and_dry_run_does_not_modify(self):
        result = pastec_result()
        with tempfile.TemporaryDirectory() as tmp:
            local.save_or_check(tmp, [result], run_at=AT)
            before = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            bad = copy.deepcopy(result)
            bad["rows"] = bad["rows"][:1]  # 少一半不可誤報成功。
            with patch.object(local, "collect", return_value=[bad]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(local.main(["--data", tmp, "--dry-run"]), 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(tmp).iterdir()})
            with patch.object(local, "collect", return_value=[bad]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(local.main(["--data", tmp]), 1)
            for name in ("prices.csv", "latest.csv"):
                self.assertEqual(before[name], (Path(tmp) / name).read_bytes())

    def test_only_rejects_unknown_or_duplicate(self):
        for value in ("suruga", "pastec,pastec", "iosys-sell,", ""):
            with self.subTest(value=value), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                local.main(["--data", "/unused", "--only", value])


class LocalFetchTests(unittest.TestCase):
    def test_intervals_apply_to_retries_and_hosts(self):
        clock, calls = [0], []
        def request(url, **kwargs):
            calls.append((clock[0], url))
            if len(calls) == 2:
                raise jp.requests.RequestsError("fixture")
            return Mock(text="fixture", raise_for_status=Mock())
        with patch.object(jp, "_last_request", None), patch.object(jp, "_host_requests", {}), \
                patch.object(jp.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(jp.time, "sleep", side_effect=lambda s: clock.__setitem__(0, clock[0]+s)), \
                patch.object(jp.requests, "get", side_effect=request):
            for url in (PASTEC_INDEX, URL, "https://iosys.co.jp/a", "https://iosys.co.jp/b",
                        "https://www.suruga-ya.jp/a", "https://www.suruga-ya.jp/b", *jp.IOSYS_URLS[:2]):
                local.fetch(url)
        self.assertEqual([t for t, _ in calls], [0, 10, 20, 25, 35, 40, 70, 75, 135])
