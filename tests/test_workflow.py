"""All financial examples are synthetic; no live directories are accessed."""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ledger


def config():
    return {"schema_version": 1, "owners": ["alice", "bob"], "currency": "CNY",
            "required_streams": [
                {"owner": "alice", "source_type": "bank", "account": "Assets:Alice:Bank"},
                {"owner": "bob", "source_type": "bank", "account": "Assets:Bob:Bank"}]}


def row(id="bank:1", amount="-12.00", **kw):
    return dict({"id": id, "owner": "alice", "date": "2001-02-03", "amount": amount,
                 "currency": "CNY", "account": "Assets:Alice:Bank", "description": "Synthetic purchase",
                 "kind": "bank"}, **kw)


class WorkflowTests(unittest.TestCase):
    def test_money_rejects_nonfinite_float_and_fractional_cents(self):
        for value in ("NaN", "Infinity", "1.001", 1.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ledger.money(value)

    def test_duplicate_source_ids_rejected(self):
        with self.assertRaises(ValueError):
            ledger.match_rows([row(), row()], [])

    def test_unique_joint_match_counts_bank_once(self):
        bank = [row()]
        platform = [row("alipay:1", kind="platform", backing="bank")]
        result = ledger.match_rows(bank, platform)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["platform_id"], "alipay:1")

    def test_same_amount_two_days_ambiguous_even_when_one_closer(self):
        with self.assertRaises(ValueError):
            ledger.match_rows([row(), row("bank:2", date="2001-02-04")],
                              [row("alipay:1", kind="platform", backing="bank")])

    def test_cross_platform_competition_rejected(self):
        with self.assertRaises(ValueError):
            ledger.match_rows([row()], [row("alipay:1", kind="platform", backing="bank"),
                                       row("wechat:1", kind="platform", backing="bank")])

    def test_bank_match_owner_account_currency_all_required(self):
        for field, value in (("owner", "bob"), ("account", "Assets:Alice:Other"), ("currency", "USD")):
            p = row("alipay:1", kind="platform", backing="bank")
            p[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                ledger.match_rows([row()], [p])

    def test_unmatched_bank_payment_blocks(self):
        with self.assertRaises(ValueError):
            ledger.match_rows([], [row("alipay:1", kind="platform", backing="bank")])

    def test_wallet_is_independent_and_unrecognized_backing_rejected(self):
        p = row("wechat:1", kind="platform", backing="wallet", account="Assets:Alice:Wallet")
        self.assertEqual(len(ledger.match_rows([], [p])), 1)
        with self.assertRaises(ValueError):
            ledger.match_rows([], [dict(p, backing="unknown")])

    def test_platform_refund_no_direction_requires_review(self):
        with self.assertRaises(ValueError):
            ledger.platform_amount("12.00", "不计收支", "退款成功")

    def test_platform_status_is_not_ignored(self):
        with self.assertRaises(ValueError):
            ledger.platform_amount("12.00", "支出", "交易关闭")

    def test_platform_income_is_positive(self):
        self.assertEqual(ledger.platform_amount("12.00", "收入", "交易成功"), "12.00")

    def test_note_idempotent_and_not_a_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            payload = {"owner": "alice", "date": "2001-02-03", "purpose": "Synthetic note", "event_type": "unknown"}
            a = ledger.record_note(root, payload, config())
            b = ledger.record_note(root, payload, config())
            self.assertEqual(a, b)
            self.assertEqual(len(list(root.rglob("*.json"))), 1)
            self.assertNotIn("postings", json.loads(a.read_text()))

    def test_note_invalid_owner_and_unknown_date_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for owner, date in (("../x", "2001-02-03"), ("alice", "today")):
                with self.assertRaises(ValueError):
                    ledger.record_note(Path(d), {"owner": owner, "date": date, "purpose": "Synthetic", "event_type": "unknown"}, config())

    def test_statement_registration_idempotent_and_received_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "synthetic.txt"
            p.write_text("synthetic input\n")
            kw = dict(owner="alice", source_type="bank", account="Assets:Alice:Bank", month="2001-02", config=config())
            a = ledger.register_statement(p, Path(d) / "private", **kw)
            b = ledger.register_statement(p, Path(d) / "private", **kw)
            self.assertEqual(a, b)
            self.assertEqual(json.loads(a.read_text())["state"], "received")

    def test_build_report_refund_transfer_and_unknown(self):
        rows = [row(category="Expenses:Food", reviewed=True),
                row("bank:2", "3.00", category="Expenses:Food", reviewed=True),
                row("bank:3", "-20.00", category="Assets:Alice:Wallet", reviewed=True),
                row("bank:4", "4.00")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.beancount"
            ledger.build_ledger(rows, config(), p)
            report = ledger.report(p, "2001-02", config())
            self.assertEqual(report["net_expenses"], "9.00")
            self.assertEqual(report["net_income"], "0.00")
            self.assertEqual(report["pending"], 1)
            self.assertEqual(report["close_status"], "unknown")

    def test_build_rejects_unknown_owner_and_unreviewed_category(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                ledger.build_ledger([row(owner="eve")], config(), Path(d) / "x.beancount")
            ledger.build_ledger([row(category="Expenses:Food", reviewed=False)], config(), Path(d) / "x.beancount")
            self.assertEqual(ledger.report(Path(d) / "x.beancount", "2001-02", config())["pending"], 1)

    def test_build_is_idempotent_and_never_overwrites_different_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.beancount"
            ledger.build_ledger([row()], config(), p)
            first = p.read_bytes()
            ledger.build_ledger([row()], config(), p)
            self.assertEqual(p.read_bytes(), first)
            with self.assertRaises(FileExistsError):
                ledger.build_ledger([row(amount="-13.00")], config(), p)
            self.assertEqual(p.read_bytes(), first)

    def test_unbalanced_ledger_not_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.beancount"
            p.write_text('2001-01-01 open Assets:Bank CNY\n2001-01-01 open Expenses:Food CNY\n2001-02-01 * "bad"\n  Assets:Bank -10 CNY\n  Expenses:Food 9 CNY\n')
            with self.assertRaises(ValueError):
                ledger.report(p, "2001-02", config())

    def test_data_writes_inside_repository_rejected(self):
        with self.assertRaises(ValueError):
            ledger.safe_output(ROOT / "private" / "ledger.json")

    def test_data_writes_inside_any_git_worktree_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            other_repo = Path(d) / "other-project"
            other_repo.mkdir()
            (other_repo / ".git").mkdir()
            with self.assertRaises(ValueError):
                ledger.safe_output(other_repo / "private" / "ledger.json")

    def test_report_rejects_plugins_and_includes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "unsafe.beancount"
            for content in ('plugin "os"\n', 'include "elsewhere.beancount"\n'):
                p.write_text(content)
                with self.assertRaises(ValueError):
                    ledger.report(p, "2001-02", config())


class SkillContractTests(unittest.TestCase):
    def test_skill_structure_and_critical_rules(self):
        text = (ROOT / "SKILL.md").read_text()
        for required in ("name: household-ledger-skill", "Use when", "PRIVATE_SYNC", "同一任务", "私有", "git", "pending", "complete", "scripts/ledger.py"):
            self.assertIn(required, text)

    def test_all_local_markdown_links_resolve(self):
        import re
        allowed = json.loads((ROOT / "release-files.json").read_text())["files"]
        for p in (ROOT / name for name in allowed if name.endswith(".md")):
            for target in re.findall(r'\]\(([^)]+)\)', p.read_text()):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue((p.parent / target.split("#")[0]).exists(), (p.name, target))


if __name__ == "__main__":
    unittest.main()
