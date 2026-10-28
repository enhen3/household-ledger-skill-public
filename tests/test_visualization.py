"""Fictional graph data, human stops and read-only Fava boundary regressions."""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import recording_demo as demo
import visualize
from ledger import canonical, digest, immutable_write


class VisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ledger-visual-test-")
        cls.root = Path(cls.temp.name)
        cls.receipt = demo.self_test(cls.root / "automatic")
        cls.fixture = cls.root / "automatic"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_authored_totals_match_raw_fictional_inputs(self):
        with (self.fixture / "inputs/bank.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), demo.BANK_COUNT)
        self.assertEqual(sum(Decimal(r["amount"]) for r in rows), Decimal(demo.BANK_NET))
        self.assertTrue(all("虚构" in r["description"] for r in rows))

    def test_prepare_stops_without_any_approval_or_candidate(self):
        output = self.root / "human-initial"
        result = demo.prepare(output)
        self.assertFalse(result["approved"])
        self.assertFalse((output / "merged.json").exists())
        self.assertFalse(list(output.rglob("*.beancount")))
        proof = demo.read(output / "overlap-confirmation.template.json")
        self.assertEqual(proof["confirmation_ref"], "")
        with self.assertRaisesRegex(ValueError, "record who confirmed"):
            demo.merge(output, output / "overlap-confirmation.template.json")

    def test_reset_never_overwrites_existing_recording(self):
        with self.assertRaisesRegex(ValueError, "new empty directory"):
            demo.prepare(self.fixture)

    def test_partial_vs_confirmed_amounts_and_pending(self):
        a, b = self.receipt["partial"], self.receipt["confirmed"]
        self.assertEqual((a["pending"], a["close_status"], a["net_expenses"]), (1, "provisional", "5724.00"))
        self.assertEqual((b["pending"], b["close_status"], b["net_expenses"]), (0, "complete", "6044.00"))
        self.assertEqual(Decimal(b["net_expenses"]) - Decimal(a["net_expenses"]), Decimal("320.00"))
        self.assertEqual(self.receipt["repeat_import_new_transactions"], 0)

    def test_refund_is_expense_reduction_and_chart_sums_match(self):
        r = demo.read(self.fixture / "stages/confirmed/view/report.json")
        self.assertEqual(r["net_income"], "12000.00")
        self.assertEqual(r["categories"]["Expenses:Food"], "672.00")
        self.assertEqual(sum(map(Decimal, r["categories"].values())), Decimal(r["net_expenses"]))
        self.assertEqual(r["scope"]["candidate_transactions"], 16)

    def test_native_fava_gets_same_month_totals(self):
        app = visualize.create_view_app(self.fixture / "stages/confirmed/view")
        ledger = app.config["LEDGERS"].ledgers[0]
        from beancount.core.data import Transaction
        amounts = [p.units.number for e in ledger.all_entries if isinstance(e, Transaction)
                   for p in e.postings if p.account.startswith("Expenses:")]
        self.assertEqual(sum(amounts), Decimal("6044.00"))

    def test_root_enters_native_fava_for_partial_and_confirmed_candidates(self):
        for stage, pending in (("partial", 1), ("confirmed", 0)):
            app = visualize.create_view_app(self.fixture / f"stages/{stage}/view")
            client = app.test_client()
            response = client.get("/")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/income_statement/"))
            page = client.get(response.location)
            self.assertEqual(page.status_code, 200)
            self.assertIn(f"待确认 {pending}", page.get_data(as_text=True))
            self.assertIn("只读候选", page.get_data(as_text=True))
            self.assertEqual(client.get("/ledger-status").status_code, 200)
            slug = app.config["LEDGERS"].first_slug()
            self.assertEqual(client.get(f"/{slug}/journal/").status_code, 200)

    def test_startup_primary_url_opens_native_fava_on_loopback(self):
        view = self.fixture / "stages/confirmed/view"
        output = io.StringIO()
        with patch("cheroot.wsgi.Server") as server, redirect_stdout(output):
            visualize.serve(view, 5231)
        server.assert_called_once()
        self.assertEqual(server.call_args.args[0], ("127.0.0.1", 5231))
        primary_url = next(word for word in output.getvalue().splitlines()[0].split() if word.startswith("http://"))
        parsed = urlsplit(primary_url)
        self.assertEqual(parsed.netloc, "127.0.0.1:5231")
        self.assertTrue(parsed.path.endswith("/income_statement/"))
        client = server.call_args.args[1].test_client()
        self.assertEqual(client.get(parsed.path).status_code, 200)

    def test_read_only_blocks_all_mutating_methods(self):
        view = self.fixture / "stages/confirmed/view"
        before = digest(view / "view.beancount")
        app = visualize.create_view_app(view)
        slug = app.config["LEDGERS"].first_slug()
        c = app.test_client()
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            self.assertEqual(c.open(f"/{slug}/api/source", method=method, json={"source": "changed"}).status_code, 401)
        self.assertEqual(digest(view / "view.beancount"), before)

    def test_status_and_fava_reopen_are_read_only(self):
        view = self.fixture / "stages/partial/view"
        app = visualize.create_view_app(view)
        c = app.test_client()
        for _ in range(2):
            page = c.get("/ledger-status").get_data(as_text=True)
            self.assertIn("待确认 1 笔", page)
            self.assertIn("5724.00", page)
            self.assertIn("尚未正式入账", page)
        self.assertEqual(c.get("/report.json").json["pending"], 1)

    def test_local_assets_and_rebinding_guard(self):
        c = visualize.create_view_app(self.fixture / "stages/confirmed/view").test_client()
        r = c.get("/ledger-status")
        self.assertIn("connect-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(c.get("/ledger-status", headers={"Host": "untrusted.invalid"}).status_code, 403)

    def test_ambient_ledger_environment_is_not_loaded(self):
        with patch.dict(os.environ, {"BEANCOUNT_FILE": "/not-an-authorized-ledger", "FAVA_HOST": "0.0.0.0"}):
            app = visualize.create_view_app(self.fixture / "stages/confirmed/view")
        self.assertEqual(len(app.config["BEANCOUNT_FILES"]), 1)
        self.assertTrue(app.config["BEANCOUNT_FILES"][0].endswith("view.beancount"))

    def test_modified_snapshot_is_rejected(self):
        dest = self.root / "tampered"
        shutil.copytree(self.fixture / "stages/confirmed/view", dest)
        with (dest / "view.beancount").open("a") as f:
            f.write("\n; changed\n")
        with self.assertRaisesRegex(ValueError, "view changed"):
            visualize.create_view_app(dest)

    def test_untrusted_extension_rejected_before_fava(self):
        raw = self.root / "custom.beancount"
        immutable_write(raw, '2001-04-01 custom "fava-extension" "untrusted_code"\n')
        config = demo.read(self.fixture / "private/config.json")
        with self.assertRaisesRegex(ValueError, "candidate Open/Transaction"):
            visualize.prepare(raw, config, demo.MONTH, self.root / "bad-view")

    def test_empty_data_is_unknown_not_complete(self):
        raw = self.root / "empty.beancount"
        immutable_write(raw, 'option "operating_currency" "CNY"\n2001-04-01 open Assets:Demo:Bank CNY\n')
        target = self.root / "empty-view"
        visualize.prepare(raw, demo.read(self.fixture / "private/config.json"), demo.MONTH, target, synthetic=True)
        c = visualize.create_view_app(target).test_client()
        self.assertEqual(c.get("/report.json").json["close_status"], "unknown")
        self.assertIn("候选无交易", c.get("/ledger-status").get_data(as_text=True))

    def test_wrong_month_never_shows_other_month_transactions(self):
        target = self.root / "next-month-empty"
        visualize.prepare(self.fixture / "stages/confirmed/candidate/household.beancount",
                          demo.read(self.fixture / "private/config.json"), "2001-05", target, synthetic=True)
        r = demo.read(target / "report.json")
        self.assertEqual(r["scope"]["candidate_transactions"], 0)
        self.assertNotIn('2001-04-12 *', (target / "view.beancount").read_text())

    def test_status_escapes_untrusted_descriptions(self):
        r = demo.read(self.fixture / "stages/partial/view/report.json")
        r["pending_items"][0]["description"] = '<script src="https://untrusted.invalid/x"></script>'
        page = visualize.status_html(r, "/native/")
        self.assertNotIn('<script src=', page)
        self.assertIn("&lt;script", page)


if __name__ == "__main__":
    unittest.main()
