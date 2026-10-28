"""Synthetic parser, coverage, publication, and failure-mode regressions."""
import copy
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coverage_gate
import ledger
import maintain
import parse_cmb
import reconcile
from test_workflow import config, row


class CoverageTests(unittest.TestCase):
    def setup_case(self, directory, rows=None):
        base = Path(directory)
        candidate = base / "household.beancount"
        ledger.build_ledger(rows or [row(category="Expenses:Food", reviewed=True)], config(), candidate)
        from decimal import Decimal
        sources = []
        input_rows = rows or [row(category="Expenses:Food", reviewed=True)]
        for identity in config()["required_streams"]:
            original = base / (identity["owner"] + ".txt")
            original.write_text("SYNTHETIC original, not financial data")
            normalized_rows = [dict(r, source_sha256=ledger.digest(original), source_type="bank")
                               for r in input_rows if r["owner"] == identity["owner"]]
            normalized = base / (identity["owner"] + "-normalized.json")
            normalized.write_text(json.dumps(normalized_rows))
            sources.append(dict(identity, original_path=str(original), normalized_path=str(normalized),
                                **{"from": "2001-02-01", "through": "2001-02-28"},
                                statement_count=len(normalized_rows),
                                statement_net=ledger.money(sum((Decimal(r["amount"]) for r in normalized_rows), Decimal("0"))),
                                confirmed_by="synthetic-reviewer", confirmed_at="2001-03-01T10:00:00+00:00",
                                confirmation_ref="SYNTHETIC test totals; not real reconciliation"))
        spec = base / "source-totals.json"
        spec.write_text(json.dumps({"schema_version": 1, "sources": sources}))
        reconcile.record(spec, candidate, "2001-02", config())
        registry = base / "coverage.json"
        document = json.loads(registry.read_text())
        return candidate, registry, document

    def test_complete_only_when_all_evidence_valid(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, _, _ = self.setup_case(d)
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "complete")

    def test_missing_member_is_partial_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = self.setup_case(d)
            document["streams"].pop()
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "partial")

    def test_self_reduced_expected_members_do_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = self.setup_case(d)
            document["expected_owners"] = ["alice"]
            document["required_streams"] = document["required_streams"][:1]
            document["streams"] = document["streams"][:1]
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")

    def test_mutated_original_or_import_state_is_unknown(self):
        for target in ("alice.txt", "source-import-state.json"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as d:
                candidate, _, _ = self.setup_case(d)
                (Path(d) / target).write_text("changed synthetic evidence")
                self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")

    def test_import_state_hash_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = self.setup_case(d)
            document.pop("import_state_sha256")
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")

    def test_no_pending_does_not_imply_reconciled(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = self.setup_case(d)
            document["streams"][0]["reconciliation"] = "unverified"
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "provisional")

    def test_pending_technical_entry_blocks_close(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, _, _ = self.setup_case(d, [row()])
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "provisional")

    def test_net_zero_unclassified_is_still_pending(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, _, _ = self.setup_case(d, [row(category="Expenses:Unclassified", reviewed=True),
                                                  row("bank:2", "12.00", category="Expenses:Unclassified", reviewed=True)])
            result = ledger.report(candidate, "2001-02", config())
            self.assertEqual(result["net_expenses"], "0.00")
            self.assertEqual(result["close_status"], "provisional")

    def test_malformed_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, _ = self.setup_case(d)
            registry.write_text("[]")
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")

    def test_report_write_and_replay_verify(self):
        with tempfile.TemporaryDirectory() as d:
            candidate, _, _ = self.setup_case(d)
            path = ledger.write_report(candidate, "2001-02", config(), Path(d) / "reports")
            before = path.read_bytes()
            ledger.write_report(candidate, "2001-02", config(), Path(d) / "reports")
            self.assertEqual(path.read_bytes(), before)


class AdapterTests(unittest.TestCase):
    def test_bank_csv_explicit_and_unknown_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.csv"
            p.write_text("date,amount,description\n2001-02-03,-12.00,SYNTHETIC\n")
            result = ledger.normalize(p, "bank-csv", "alice", "Assets:Alice:Bank")
            self.assertEqual(result[0]["amount"], "-12.00")
            self.assertEqual(result[0]["source_sha256"], ledger.digest(p))
            p.write_text("mystery,value\nfoo,bar\n")
            with self.assertRaises(ValueError):
                ledger.normalize(p, "bank-csv", "alice", "Assets:Alice:Bank")

    def test_alipay_gbk_and_exact_payment_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "alipay.csv"
            p.write_bytes("合成测试\n交易时间,金额,收/支,收/付款方式,交易对方,商品说明,交易状态\n2001-02-03 01:02:03,12.00,支出,合成银行卡,合成商户,合成商品,交易成功\n".encode("gbk"))
            mapping = {"合成银行卡": {"account": "Assets:Alice:Bank", "backing": "bank"}}
            result = ledger.normalize(p, "alipay", "alice", payment_map=mapping, encoding="gbk")
            self.assertEqual(result[0]["backing"], "bank")
            with self.assertRaises(ValueError):
                ledger.normalize(p, "alipay", "alice", payment_map={}, encoding="gbk")

    def test_wechat_xlsx_wallet(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wechat.xlsx"
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.append(["SYNTHETIC"])
            sheet.append(["交易时间", "金额(元)", "收/支", "支付方式", "交易对方", "商品", "当前状态"])
            sheet.append(["2001-02-03 01:02:03", "¥12.00", "支出", "零钱", "合成商户", "合成商品", "支付成功"])
            book.save(p)
            book.close()
            rows = ledger.normalize(p, "wechat", "alice", payment_map={"零钱": {"account": "Assets:Alice:Wallet", "backing": "wallet"}})
            self.assertEqual(rows[0]["amount"], "-12.00")
            self.assertEqual(rows[0]["backing"], "wallet")

    def test_pdf_line_parser_with_mocked_synthetic_page(self):
        class Page:
            def extract_text(self):
                return "招商银行交易流水\n2001-02-03 CNY -12.00 88.00 SYNTHETIC\ncontinuation\n2001-02-04 CNY 3.00 91.00 SYNTHETIC refund\n"
        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.object(parse_cmb.pdfplumber, "open", return_value=PDF()):
            rows = parse_cmb.parse("synthetic-only.pdf")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["description"], "SYNTHETIC continuation")
        self.assertEqual(rows[0]["amount"], "-12.00")


class ReleaseSafetyTests(unittest.TestCase):
    def test_secret_detection(self):
        self.assertIn("github_token", maintain.scan_text("gh" + "p_" + "a" * 40))
        self.assertIn("private_key", maintain.scan_text("-----BEGIN " + "OPENSSH PRIVATE KEY-----"))

    def test_private_path_account_and_denied_term_detection(self):
        self.assertIn("absolute_home_path", maintain.scan_text("/" + "Users/example/private/"))
        self.assertIn("possible_full_account", maintain.scan_text("1234" * 4))
        self.assertIn("private_denied_term", maintain.scan_text("private-example", ["private-example"]))

    def test_privacy_scanner_does_not_claim_to_be_complete(self):
        text = (ROOT / "references/maintenance.md").read_text()
        self.assertIn("人工", text)
        self.assertIn("不能证明", text)

    def test_public_repo_refused(self):
        with patch.object(maintain, "run", return_value=json.dumps({"nameWithOwner": "demo/repo", "visibility": "PUBLIC"})):
            with self.assertRaises(ValueError):
                maintain.verify("demo/repo")

    def test_wrong_repo_refused(self):
        with patch.object(maintain, "run", return_value=json.dumps({"nameWithOwner": "other/repo", "visibility": "PRIVATE"})):
            with self.assertRaises(ValueError):
                maintain.verify("demo/repo")


if __name__ == "__main__":
    unittest.main()
