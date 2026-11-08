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
from jp.local_pastec import (discover_pastec_pages, parse_pastec, PASTEC_INDEX,
                             PASTEC_EXPECTED_SPECS)

FIXTURES = Path(__file__).parent / "fixtures" / "jp"
URL = "https://pastec.net/iphone/iphone17pro256gb?purchase_type=net"
AT = "2026-10-30T09:40:00+09:00"


def fixture(name):
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def pastec_result():
    rows, updated = parse_pastec(fixture("local-pastec-17pro256"), URL)
    return dict(source="pastec", shop="モバステ", rows=rows, status="ok", shop_updated=updated)


def complete_pastec_pages():
    """以真實新版規格頁合成各目標規格；網路及資料庫皆不參與測試。"""
    pages, entries = {}, []
    template = fixture("local-pastec-17pro256-20261104")
    for i, (model, storage) in enumerate(sorted(PASTEC_EXPECTED_SPECS)):
        url = f"https://pastec.net/iphone/fixture{i}?purchase_type=net"
        spec = f"{model} {storage}"
        entries.append(f'<div class="p-priceTable__inner"><div class="p-priceTable__name">'
                       f'<span>{spec}</span></div><a href="{url}">郵送買取</a></div>')
        pages[url] = template.replace("iPhone17 Pro 256GB", spec)
    pages[PASTEC_INDEX] = "\n".join(entries)
    return pages


class PastecTests(unittest.TestCase):
    def test_other_real_model_pages(self):
        for slug, model, prices in (
            ("iphone18promax256gb", "iPhone 18 Pro Max", (231000, 181000)),
            ("iphoneduo256gb", "iPhone Duo", (373000, 284000)),
        ):
            with self.subTest(model=model):
                html = fixture(f"local-pastec-{slug}-20261104")
                rows, _ = parse_pastec(html, f"https://pastec.net/iphone/{slug}?purchase_type=net")
                self.assertEqual([(r["model"], r["storage"], r["condition"], r["price_jpy"])
                                  for r in rows],
                                 [(model, "256GB", "未開封", prices[0]),
                                  (model, "256GB", "中古上限", prices[1])])

    def test_new_and_old_layouts_preserve_prices_and_types(self):
        for name in ("local-pastec-17pro256", "local-pastec-17pro256-20261104"):
            with self.subTest(layout=name):
                rows, updated = parse_pastec(fixture(name), URL)
                self.assertEqual([(r["model"], r["storage"], r["condition"], r["price_jpy"])
                                  for r in rows],
                                 [("iPhone 17 Pro", "256GB", "未開封", 171000),
                                  ("iPhone 17 Pro", "256GB", "中古上限", 143500)])
                self.assertTrue(all(type(r["price_jpy"]) is int and r["carrier"] == "SIMフリー"
                                    for r in rows))
                self.assertEqual(updated, "")

    def test_new_layout_models_and_broken_fields(self):
        html = fixture("local-pastec-17pro256-20261104")
        for model, expected in (("iPhone Duo", "iPhone Duo"), ("iPhone18 Pro", "iPhone 18 Pro"),
                                ("iPhone18 Pro Max", "iPhone 18 Pro Max")):
            with self.subTest(model=model):
                rows, _ = parse_pastec(html.replace("iPhone17 Pro", model), URL)
                self.assertEqual({r["model"] for r in rows}, {expected})
        for old, new in (("assess__iphone-model-card-name", "missing-name"),
                         ("SIMフリー", "不明"), ("SIMフリー", "海外版SIMフリー"),
                         ("p-priceRankTable__table", "missing-table"),
                         ("p-priceRankTable__badge", "missing-badge"),
                         ("p-priceRankTable__price", "missing-price"),
                         ("171,000円", "要確認")):
            with self.subTest(missing=old, replacement=new), self.assertRaises(jp.ParseError):
                parse_pastec(html.replace(old, new), URL)
        rows, _ = parse_pastec(html.replace("SIMフリー", "docomo版"), URL)
        self.assertEqual({r["carrier"] for r in rows}, {"docomo"})
        self.assertEqual(parse_pastec(html.replace("iPhone17 Pro", "iPhone17e"), URL)[0], [])
        rows, _ = parse_pastec(html.replace("128,500円", "150,000円"), URL)
        self.assertEqual(rows[1]["price_jpy"], 150000)

    def test_real_grades_and_carrier(self):
        result = pastec_result()
        self.assertEqual([(r["condition"], r["price_jpy"]) for r in result["rows"]],
                         [("未開封", 171000), ("中古上限", 143500)])
        self.assertEqual({r["carrier"] for r in result["rows"]}, {"SIMフリー"})
        self.assertEqual(result["shop_updated"], "")
        with self.assertRaises(jp.ParseError):
            discover_pastec_pages(fixture("local-pastec-index"))
        self.assertEqual(set(discover_pastec_pages(complete_pastec_pages()[PASTEC_INDEX]).values()),
                         PASTEC_EXPECTED_SPECS)

    def test_individual_condition_empty_or_unavailable_is_parse_error(self):
        html = fixture("local-pastec-17pro256-20261104")
        for price in ("171,000円", "143,500円"):
            for replacement in ("", "買取不可", "0円"):
                with self.subTest(price=price, replacement=replacement):
                    with self.assertRaises(jp.ParseError):
                        parse_pastec(html.replace(price, replacement, 1), URL)

    def test_mixed_layouts_are_ambiguous(self):
        old = fixture("local-pastec-17pro256")
        new = fixture("local-pastec-17pro256-20261104")
        for html in (old + new, new + old):
            with self.assertRaises(jp.ParseError):
                parse_pastec(html, URL)

    def test_description_row_without_badge_is_ignored(self):
        html = fixture("local-pastec-17pro256-20261104")
        description = ('<tr><td class="p-priceRankTable__rank">價格說明</td>'
                       '<td>說明</td></tr>')
        rows, _ = parse_pastec(html.replace("<tbody>", "<tbody>" + description, 1), URL)
        self.assertEqual([r["price_jpy"] for r in rows], [171000, 143500])

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
        pages = complete_pastec_pages()
        result = local.collect(("pastec",), pages.__getitem__)[0]
        self.assertEqual((result["status"], len(result["rows"])),
                         ("ok", len(PASTEC_EXPECTED_SPECS) * 2))
        del pages[next(url for url in pages if url != PASTEC_INDEX)]
        result = local.collect(("pastec",), pages.__getitem__)[0]
        self.assertEqual(result["status"], "fetch_error")
        with tempfile.TemporaryDirectory() as tmp:
            reports = local.save_or_check(tmp, [result], run_at=AT)
            self.assertEqual(reports[0]["status"], "fetch_error")
            self.assertFalse((Path(tmp) / "prices.csv").exists())

    def test_collect_rejects_missing_or_duplicate_spec(self):
        for defect in ("missing", "duplicate"):
            with self.subTest(defect=defect):
                pages = complete_pastec_pages()
                entries = pages[PASTEC_INDEX].splitlines()
                if defect == "missing":
                    entries.pop()
                else:
                    # 同規格不同網址也不能抵銷遺失的規格。
                    entries[-1] = entries[0].replace("fixture0", "duplicate")
                pages[PASTEC_INDEX] = "\n".join(entries)
                result = local.collect(("pastec",), pages.__getitem__)[0]
                self.assertEqual(result["status"], "parse_error")


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
            self.assertEqual({r["shop"] for r in jp.read_csv(target / "local/prices.csv")}, {"モバステ"})
            self.assertEqual({r["condition"] for r in jp.read_csv(target / "sell/prices.csv")}, {"中古A"})
            before = (target / "local/prices.csv").read_bytes()
            local.save_or_check(target, [sell], run_at=AT)
            self.assertEqual((target / "local/prices.csv").read_bytes(), before)

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
            before = {p.name: p.read_bytes() for p in (Path(tmp) / "local").iterdir()}
            bad = copy.deepcopy(result)
            bad["rows"] = bad["rows"][:1]  # 少一半不可誤報成功。
            with patch.object(local, "collect", return_value=[bad]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(local.main(["--data", tmp, "--dry-run"]), 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (Path(tmp) / "local").iterdir()})
            with patch.dict("os.environ", {"PTT_LOCAL_LOCK_PATH": str(Path(tmp) / "locks/runner.lock")}), patch.object(local, "collect", return_value=[bad]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(local.main(["--data", tmp]), 1)
            for name in ("prices.csv", "latest.csv"):
                self.assertEqual(before[name], (Path(tmp) / "local" / name).read_bytes())

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
