"""OpenAI 多機拆單整合測試，全程使用本機替身與暫存資料。"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import tracker as T


TITLE = "[販售] 家人換下的 iPhone"
BODY = "iPhone 16 Pro 256G 售 28,000 元\niPhone 15 128G 售 15000 元"
URL = "https://example.invalid/M.1791016469.A.001.html"
ITEM = dict(model="iPhone 16 Pro", storage="256GB", battery_health=85,
            price=28000, is_brand_new=False)

PAIR = [ITEM, dict(ITEM, model="iPhone 15", storage="128GB", price=15000)]
SINGLE = "[型號] iPhone 16 Pro\n[售價] 28,000"
EDIT = SINGLE + "\n另售 iPhone 15 售 15000"


class OpenAIMultiTest(unittest.TestCase):
    def setUp(self):
        root = Path(self.enter_tempdir())
        self.cache = root / "multi_llm_cache.json"
        self.replace(patch.object(T, "SPLIT_CACHE_FILE", str(self.cache)))
        for name, filename in (("MULTI_FILE", "multi_items.csv"), ("RETRY_FILE", "extract_retry.csv"),
                               ("EVENTS_FILE", "events.csv")):
            self.replace(patch.object(T, name, str(root / filename)))
        self.replace(patch.dict(os.environ, {"OPENAI_API_KEY": "openai-test-secret", "OPENAI_MAX_CALLS": "20",
                                             "OPENAI_MODEL": ""}))
        self.replace(patch.object(T, "EXTRACTOR", "rules"))
        self.replace(patch.object(T, "REPARSE", False))
        self.replace(patch.object(T, "fetch", return_value=(200, "")))
        self.article = self.replace(patch.object(T, "parse_article"))
        self.post = self.replace(patch.object(T.requests, "post"))
        self.sleep = self.replace(patch.object(T.time, "sleep"))
        self.listings, self.multi, self.retries = {}, {}, {}
        self.stats = dict(new=0, errors=0, sold=0, price_changes=0)
        self.reply(PAIR)

    def enter_tempdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tmp.name

    def replace(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def reply(self, items):
        self.post.return_value = Mock(status_code=200)
        self.post.return_value.json.return_value = {"output_text": json.dumps({"items": items})}

    def process(self, url=URL, title=TITLE, body=BODY):
        self.article.return_value = dict(title=title, body=body, pm_count=0, last_edit=None)
        T.process_article(url, self.listings, True, self.stats, self.multi, retries=self.retries)

    def test_body_trigger_schema_validation_and_csv(self):
        raw = [dict(ITEM, battery_health=101)] * 2 + [
            dict(ITEM, price=8000), dict(ITEM, price=11000), dict(ITEM, model="Galaxy 16"),
            dict(ITEM, price=999), dict(ITEM, price=250001),
            dict(ITEM, model="iPhone 15", storage="128GB", price=15000)]
        self.post.return_value.json.return_value = {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"items": raw})}]}]}
        self.process(body=BODY + "\n附件 999 元；備註 250001")
        args, kwargs = self.post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/responses")
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "gpt-6.2-sol")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertGreater(kwargs["timeout"], 0)
        T.save_multi(self.multi)
        rows = T.load_multi()[URL]
        self.assertEqual(list(rows[0]), T.MULTI_FIELDS)
        self.assertEqual([(r["model"], r["price"]) for r in rows],
                         [("iPhone 16 Pro", "28000"), ("iPhone 15", "15000")])
        self.assertEqual(rows[0]["battery_health"], "")
        self.assertEqual(self.listings[URL]["status"], "略過")

    def test_identical_phones_keep_one_per_matching_body_line(self):
        item = dict(ITEM, model="iPhone 16", battery_health=None)
        line = "iPhone 16 256GB 售28000"
        title = line + " 兩支"
        body = line + "\n" + line
        # 舊版已將兩筆合併且快取成單筆。
        self.cache.write_text(json.dumps({URL: {T.body_hash(body): [item]}}))
        self.reply([item] * 3)
        self.process(title=title, body=body)
        with patch.object(T, "REPARSE", True):
            self.process(title=title, body=body)
        self.post.assert_called_once()
        T.save_multi(self.multi)
        self.assertEqual([r["item_no"] for r in T.load_multi()[URL]], ["1", "2"])
        other = URL + "2"
        self.process(other, title, line)
        self.assertNotIn(other, self.multi)
        self.assertEqual(json.loads(self.cache.read_text())[other][T.body_hash(line)], [item])

    def test_expired_edited_listing_only_calls_again_after_another_edit(self):
        self.process(title="iPhone 16 Pro", body=SINGLE)
        previous = self.listings[URL].copy()
        self.post.return_value.status_code = 503
        self.process()
        self.retries[URL]["first_failed"] = "2020-01-01 00:00:00"
        T.save_extract_retries(self.retries)
        self.retries = T.load_extract_retries()
        T.expire_extract_retries(self.retries, self.listings)
        self.assertEqual(self.listings[URL], previous)
        self.process()
        self.post.assert_called_once()
        self.assertEqual(self.retries, {})
        for field in ("price", "price_checked_at", "body_hash"):
            self.assertEqual(self.listings[URL][field], previous[field])
        self.reply(PAIR)
        self.process(body=BODY + " 可議")
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(len(self.multi[URL]), 2)

    def test_cache_including_empty_and_old_version(self):
        T.REPARSE = True
        self.reply([])
        self.process()
        self.reply(PAIR)
        self.process()
        self.assertNotIn(URL, self.multi)
        self.process(body=BODY + " 可議")
        self.assertIn(URL, self.multi)
        self.process()
        self.assertNotIn(URL, self.multi)
        self.assertEqual(self.post.call_count, 2)
        self.assertTrue(self.sleep.called)
        self.assertEqual(len(json.loads(self.cache.read_text())[URL]), 2)

    def test_title_trigger_override_and_limit(self):
        os.environ.update(OPENAI_MAX_CALLS="1", OPENAI_MODEL="test-model")
        self.process(title="iPhone 兩支", body="各售 28,000 元")
        self.assertEqual(self.post.call_args.kwargs["json"]["model"], "test-model")
        self.process(url=URL + "2")
        self.assertIn(URL + "2", self.retries)
        self.assertNotIn(URL + "2", self.listings)
        self.post.assert_called_once()

    def test_rules_single_accessory_and_ollama_do_not_call(self):
        self.process(title="iPhone 15 / iPhone 16", body=(
            "[型號]\n1.iPhone 15\n2.iPhone 16\n[售價]15000/28000"))
        self.assertEqual(len(self.multi[URL]), 2)
        self.process(url=URL + "2", title="iPhone 16 Pro", body="[型號] iPhone 16 Pro\n[售價]28000")
        self.assertEqual(self.listings[URL + "2"]["price"], 28000)
        self.process(url=URL + "3", title="iPhone 15 / iPhone 16 保護殼", body="兩款保護殼")
        T.EXTRACTOR = "ollama"
        with patch.object(T, "llm_extract", return_value={}):
            self.process(url=URL + "4")
        self.post.assert_not_called()
        self.assertFalse(self.cache.exists())

    def test_body_list_overrides_apparent_single_only_with_key(self):
        title = "iPhone 16 Pro"
        body = "[型號] iPhone 16 Pro\n[售價] 28,000\n另售 iPhone 15 售 15000"
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.process(title=title, body=body)
            self.assertEqual(self.listings[URL]["price"], 28000)
        self.process(url=URL + "2", title=title, body=body)
        self.assertEqual(self.listings[URL + "2"]["status"], "略過")
        self.assertEqual(self.multi[URL + "2"][0]["price"], 28000)
        self.post.assert_called_once()

    def test_no_key_keeps_rules_and_does_not_read_cache(self):
        os.environ.pop("OPENAI_API_KEY")
        self.cache.write_text("故意損毀")
        self.process(title="iPhone 兩支")
        self.assertEqual(self.listings[URL]["status"], "略過")
        self.assertEqual(self.multi, {})
        self.assertEqual(self.retries, {})
        self.assertEqual(self.cache.read_text(), "故意損毀")
        self.post.assert_not_called()

    def test_blocked_status_applies_to_remaining_articles(self):
        for code in (401, 403, 429):
            with self.subTest(code=code):
                self.set_empty_run()
                self.post.return_value.status_code = code
                self.process()
                self.process(url=URL + "2")
                self.post.assert_called_once()
                self.assertEqual(len(self.retries), 2 if code == 429 else 0)
                self.assertEqual(len(self.listings), 0 if code == 429 else 2)
                if code == 429:
                    self.assertEqual(self.retries[URL + "2"]["last_error"], "429")
                self.assertFalse(self.cache.exists())

    def set_empty_run(self):
        self.stats = dict(new=0, errors=0, sold=0, price_changes=0)
        self.listings.clear()
        self.retries.clear()
        self.post.reset_mock()

    def test_transient_failure_retries_and_recovers(self):
        for failure in ("timeout", "408", "503", "broken_json", "wrong_shape", "refusal", "incomplete"):
            with self.subTest(failure=failure):
                self.set_empty_run()
                url = URL + failure
                self.reply([])
                if failure == "timeout":
                    self.post.side_effect = T.requests.Timeout("fixture-secret")
                elif failure in ("408", "503"):
                    self.post.return_value.status_code = int(failure)
                elif failure == "incomplete":
                    self.post.return_value.json.return_value["status"] = "incomplete"
                elif failure == "refusal":
                    self.post.return_value.json.return_value = {"output": [{"type": "message", "content": [
                        {"type": "refusal", "refusal": "拒答"}]}]}
                elif failure == "broken_json":
                    self.post.return_value.json.return_value = {"output_text": "broken"}
                else:
                    self.post.return_value.json.return_value = {"output_text": '{"items":{}}'}
                self.process(url=url)
                T.save_extract_retries(self.retries)
                self.retries = T.load_extract_retries()
                self.assertNotIn(url, self.listings)
                self.assertEqual(self.retries[url]["last_error"], failure if failure in ("408", "503") else "")
                first_seen = self.retries[url]["first_failed"]
                self.post.side_effect = None
                self.reply(PAIR)
                self.process(url=url)
                self.assertNotIn(url, self.retries)
                self.assertEqual(self.multi[url][0]["first_seen"], first_seen)
                self.assertEqual(self.post.call_count, 2)

    def test_single_phone_mentions_and_serial_numbers(self):
        self.process(title="iPhone 16 Pro", body=SINGLE + "\n換購 iPhone 17\niPhone 16 Pro A3296\niPhone 16 Pro 2026 年購入")
        self.post.assert_not_called()
        self.assertEqual(self.listings[URL]["status"], T.STATUS_ACTIVE)
        self.assertEqual(self.listings[URL]["price"], 28000)

    def test_small_results_follow_rules_for_new_and_edited_articles(self):
        for n, items in enumerate(([], [ITEM])):
            url = URL + str(n)
            self.reply(items)
            self.process(url, "iPhone 16 Pro", EDIT)
            self.process(url, "iPhone 16 Pro", EDIT + " 可議")
            self.assertEqual(self.listings[url]["status"], T.STATUS_ACTIVE)
            self.assertEqual(self.listings[url]["price"], 28000)
            self.assertNotIn(url, self.multi)
        self.assertEqual(self.post.call_count, 4)
        self.assertNotIn("排除誤判", Path(T.EVENTS_FILE).read_text())

    def test_edited_listing_retries_without_modifying_previous_observation(self):
        self.process(title="iPhone 16 Pro", body=SINGLE)
        previous = self.listings[URL].copy()
        self.post.return_value.status_code = 429
        self.process(title="iPhone 16 Pro", body=EDIT.replace("28,000", "25,000"))
        self.assertIn(URL, self.retries)
        self.assertEqual(self.listings[URL], previous)
        self.assertNotIn("價格變動", Path(T.EVENTS_FILE).read_text())
        self.stats.pop("openai_blocked")
        self.reply([dict(ITEM, price=25000), PAIR[1]])
        self.process(title="iPhone 16 Pro", body=EDIT.replace("28,000", "25,000"))
        self.assertEqual(self.listings[URL]["status"], "略過")
        self.assertEqual(len(self.multi[URL]), 2)
        self.assertNotIn(URL, self.retries)

    def test_reparse_pending_retries_unchanged_body_on_normal_run(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            self.process(title="iPhone 16 Pro", body=EDIT)
        with patch.object(T, "REPARSE", True):
            self.post.return_value.status_code = 408
            self.process(title="iPhone 16 Pro", body=EDIT)
        self.assertIn(URL, self.retries)
        self.reply(PAIR)
        self.process(title="iPhone 16 Pro", body=EDIT)
        self.assertEqual(len(self.multi[URL]), 2)
        self.assertNotIn(URL, self.retries)

    def test_bad_cache_rebuilt(self):
        for bad in ("{", "[]", json.dumps({URL: []}), json.dumps({URL: {T.body_hash(BODY): [None]}})):
            with self.subTest(bad=bad):
                self.set_empty_run()
                self.cache.write_text(bad)
                self.process()
                self.post.assert_called_once()
                self.assertEqual(len(json.loads(self.cache.read_text())[URL][T.body_hash(BODY)]), 2)
                self.assertNotIn(URL, self.retries)

    def test_price_formats_in_title_and_body_and_battery_limits(self):
        for i, price in enumerate(("２８， ０００", "2.8萬", "28k")):
            self.reply([dict(ITEM, battery_health=49, is_brand_new=True),
                        dict(PAIR[1], battery_health=(50, 100, 90)[i])])
            url = URL + str(i)
            self.process(url, "iPhone 兩支 " + price, "另一支售 １５０００ 元")
            first, second = self.multi[url]
            self.assertEqual((first["price"], first["全新未拆封機"], first["battery_health"]), (28000, "是", ""))
            self.assertEqual(second["battery_health"], (50, 100, 90)[i])

    def test_split_price_separators_units_and_non_prices(self):
        for text, expected in (
                ("28000，15000", {28000, 15000}), ("28,000，95%", {28000}),
                ("28,000，100%", {28000}), ("28000，\n2.", {28000}),
                ("2.8w／15千／NT28000", {28000, 15000}),
                ("95％、100%、256GB、1024 GB、2TB、A28000", set())):
            with self.subTest(text=text):
                self.assertEqual(T.split_prices(text), expected)
        body = "iPhone 16 Pro 256GB NT28000，95%\niPhone 16 Pro 128GB 15千"
        self.reply([ITEM, dict(ITEM, storage="128GB", price=15000)])
        self.process(body=body)
        self.assertEqual([row["price"] for row in self.multi[URL]], [28000, 15000])

    def test_cache_repair_preserves_unaffected_entries(self):
        digest = T.body_hash(BODY)
        other = {"other-url": {"other-hash": PAIR}}
        for versions in ([], {"older": [], digest: [{}]}):
            with self.subTest(versions=versions):
                self.set_empty_run()
                self.cache.write_text(json.dumps({**other, URL: versions}))
                self.process()
                expected = {"older": []} if isinstance(versions, dict) else {}
                self.assertEqual(json.loads(self.cache.read_text()),
                                 {**other, URL: {**expected, digest: PAIR}})

    def test_accessory_post_ignores_unrelated_storage_numbers(self):
        title = "iPhone 15 / iPhone 16 保護殼"
        for detail in ("[售價] 512 元", "重量 128g", "地址 256 號"):
            with self.subTest(detail=detail):
                self.process(URL + detail, title, "[型號] iPhone 16 保護殼\n" + detail)
                self.post.assert_not_called()

    def test_existing_split_retry_ends_after_unsuccessful_rule_fallback(self):
        for n, (code, items) in enumerate(((200, []), (200, [ITEM]), (400, []), (404, []))):
            with self.subTest(code=code, items=items):
                url = URL + str(n)
                self.process(url, "iPhone 16 Pro", SINGLE)
                row = self.listings[url].copy()
                self.post.return_value.status_code = 503
                self.process(url)
                self.assertIn(url, self.retries)
                self.reply(items)
                self.post.return_value.status_code = code
                self.process(url)
                self.assertNotIn(url, self.retries)
                calls = self.post.call_count
                self.process(url)
                self.assertEqual(self.post.call_count, calls)
                for field in ("price", "body_hash", "price_checked_at"):
                    self.assertEqual(self.listings[url][field], row[field])

    def test_accessory_gift_and_fullwidth_pm(self):
        self.assertTrue(T.looks_multi_item("iPhone 送殼", "ｉＰｈｏｎｅ １６ｐｍ ２５６Ｇ\niPhone 16 256G"))

    def test_http_fallback_and_secret_absent_from_outputs(self):
        output = io.StringIO()
        with redirect_stdout(output):
            for code in (400, 404):
                self.post.return_value.status_code = code
                self.process(URL + str(code), "iPhone 16 Pro", EDIT)
                self.assertEqual(self.listings[URL + str(code)]["price"], 28000)
            self.assertFalse(self.retries)
            self.assertFalse(self.cache.exists())
            self.post.side_effect = T.requests.Timeout(os.environ["OPENAI_API_KEY"])
            self.process(URL + "timeout")
            self.assertIn(URL + "timeout", self.retries)
            self.post.side_effect = None
            self.reply(PAIR)
            self.process()
            T.save_multi(self.multi)
            T.save_listings(self.listings, str(self.cache.parent / "listings.csv"))
            T.save_extract_retries(self.retries)
        self.assertNotIn(os.environ["OPENAI_API_KEY"], output.getvalue())
        for path in self.cache.parent.iterdir():
            self.assertNotIn(os.environ["OPENAI_API_KEY"], path.read_text())
