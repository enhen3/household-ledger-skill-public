"""Synthetic regressions for the three review findings and first-use workflow."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ledger
import review
from duplicates import deduplicate
from test_workflow import config, row


class DuplicateTests(unittest.TestCase):
    def exports(self, base):
        paths = [Path(base) / n for n in ("first.csv", "expanded.csv")]
        common = "date,amount,description\n2001-02-03,-12.00,SYNTHETIC A\n"
        paths[0].write_text(common)
        paths[1].write_text(common + "2001-02-04,-8.00,SYNTHETIC B\n")
        return [ledger.normalize(p, "bank-csv", "alice", "Assets:Alice:Bank") for p in paths]

    def test_overlapping_export_cannot_silently_count_twice(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.exports(d)
            with self.assertRaisesRegex(ValueError, "overlapping exports"):
                ledger.match_rows(a + b, [])

    def test_explicit_overlap_pair_preserves_trace_and_correct_count(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.exports(d)
            result = ledger.match_rows(a + b, [], overlap_decisions=[{"keep_id": a[0]["id"], "duplicate_id": b[0]["id"]}])
            self.assertEqual(len(result), 2)
            self.assertIn(b[0]["id"], result[0]["duplicate_source_ids"])
            from decimal import Decimal
            self.assertEqual(sum(Decimal(r["amount"]) for r in result), Decimal("-20.00"))

    def test_same_day_same_amount_real_transactions_survive(self):
        a = row(source_sha256="synthetic-file", transaction_id="synthetic-order-a")
        b = row("bank:2", source_sha256="synthetic-file", transaction_id="synthetic-order-b")
        self.assertEqual(len(ledger.match_rows([a, b], [])), 2)
        # Distinct native order IDs also survive separate exports.
        b["source_sha256"] = "synthetic-other-file"
        self.assertEqual(len(ledger.match_rows([a, b], [])), 2)

    def test_same_file_identical_rows_without_native_ids_are_not_deleted(self):
        self.assertEqual(len(ledger.match_rows([row(source_sha256="one"), row("bank:2", source_sha256="one")], [])), 2)

    def test_native_id_reimport_is_once_and_conflicting_amount_rejected(self):
        a = row(source_sha256="first", transaction_id="synthetic-order")
        b = row("bank:2", source_sha256="second", transaction_id="synthetic-order")
        self.assertEqual(len(ledger.match_rows([a, b], [])), 1)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            ledger.match_rows([a, dict(b, amount="-13.00")], [])

    def test_prior_import_is_not_new_money(self):
        rows, excluded = deduplicate([row()], history=[row()])
        self.assertEqual(rows, [])
        self.assertTrue(excluded[0]["already_imported"])

    def test_partial_matching_records_issues_and_blocks_approval(self):
        issues = []
        result = ledger.match_rows([row(), row("bank:2")], [row("platform:1", kind="platform", backing="bank")], issues=issues)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(issues), 1)
        self.assertTrue(all(r["source_issues"] for r in result))

    def test_quoted_alipay_headers_are_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            p.write_text('"交易时间","金额","收/支","收/付款方式","交易对方","商品说明","交易状态","交易订单号"\n'
                         '"2001-02-03 10:00:00","12.00","支出","SYNTHETIC bank","SYNTHETIC merchant","SYNTHETIC goods","交易成功","synthetic-order"\n')
            result = ledger.normalize(p, "alipay", "alice", payment_map={"SYNTHETIC bank": {"account": "Assets:Alice:Bank", "backing": "bank"}})
            self.assertEqual(result[0]["transaction_id"], "synthetic-order")
            merged = ledger.match_rows([row()], result)
            self.assertEqual(merged[0]["platform_transaction_id"], "synthetic-order")


class ReviewTests(unittest.TestCase):
    def test_init_is_idempotent_and_wrong_config_fails(self):
        with tempfile.TemporaryDirectory() as d:
            c = config()
            review.initialize(d, c["owners"], c["required_streams"])
            before = (Path(d) / "config.json").read_bytes()
            review.initialize(d, c["owners"], c["required_streams"])
            self.assertEqual((Path(d) / "config.json").read_bytes(), before)
            with self.assertRaises(ValueError): review.initialize(Path(d) / "bad", ["alice"], [])

    def test_note_hint_requires_confirmation_and_approved_rule_reused(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            note = ledger.record_note(base, {"owner": "alice", "date": "2001-02-03", "purpose": "SYNTHETIC gift", "event_type": "gift", "amount": "12.00"}, config())
            source = base / "merged.json"
            source.write_text(json.dumps([row(merchant="SYNTHETIC shop")]))
            queue = base / "review.json"
            initial = review.prepare(source, queue, notes_root=base)
            self.assertEqual(initial["pending"], 1)
            self.assertEqual(len(initial["items"][0]["notes"]), 1)
            decisions = base / "decisions.json"
            decisions.write_text(json.dumps({"review_sha256": ledger.digest(queue),
                "confirmed_by": "synthetic-user", "confirmed_at": "2001-02-04T10:00:00+00:00", "confirmation_ref": "SYNTHETIC explicit rule approval",
                "decisions": [{"id": "bank:1", "category": "Expenses:Gifts", "scope": "future",
                    "note_event_id": json.loads(note.read_text())["event_id"],
                    "when": {"owner": "alice", "account": "Assets:Alice:Bank", "currency": "CNY", "direction": "expense", "merchant": "SYNTHETIC shop"}}]}))
            result = review.approve(queue, decisions, base / "reviewed.json", rules_dir=base / "rules")
            self.assertEqual(result, {"approved": 1, "pending": 0, "rules_created": 1})
            source.write_text(json.dumps([row("bank:2", date="2001-03-03", merchant="SYNTHETIC shop")]))
            repeated = review.prepare(source, base / "next-review.json", notes_root=base, rules_dir=base / "rules")
            self.assertEqual(repeated["pending"], 0)
            self.assertEqual(repeated["items"][0]["status"], "approved_rule")
            # Replay changes nothing.
            self.assertEqual(review.approve(queue, decisions, base / "reviewed.json", rules_dir=base / "rules"), result)

    def test_stale_review_cannot_be_approved(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "queue.json").write_text('{"schema_version":1,"items":[]}')
            (p / "decisions.json").write_text('{"review_sha256":"stale"}')
            with self.assertRaisesRegex(ValueError, "review changed"):
                review.approve(p / "queue.json", p / "decisions.json", p / "out.json")

    def test_orphan_correction_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "predecessor"):
                ledger.record_note(d, {"owner": "alice", "date": "2001-02-03", "purpose": "SYNTHETIC", "event_type": "correction", "supersedes_event_id": "a" * 64}, config())

    def test_missing_dependency_is_explicit(self):
        with patch.object(review.importlib.metadata, "version", side_effect=review.importlib.metadata.PackageNotFoundError):
            self.assertFalse(review.doctor()["ready"])


    def test_once_approval_preserves_other_pending_and_creates_no_rule(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "input.json").write_text(json.dumps([row(), row("bank:2", "-8.00")]))
            review.prepare(p / "input.json", p / "queue.json")
            (p / "decisions.json").write_text(json.dumps({
                "review_sha256": ledger.digest(p / "queue.json"),
                "confirmed_by": "synthetic-user", "confirmed_at": "2001-03-01T10:00:00+00:00",
                "confirmation_ref": "SYNTHETIC once only confirmation",
                "decisions": [{"id": "bank:1", "category": "Expenses:Gifts", "scope": "once"}]}))
            result = review.approve(p / "queue.json", p / "decisions.json", p / "reviewed.json", rules_dir=p / "rules")
            self.assertEqual(result, {"approved": 1, "pending": 1, "rules_created": 0})
            self.assertFalse((p / "rules").exists())
            receipt = json.loads((p / "reviewed.review-receipt.json").read_text())
            self.assertEqual(receipt["approved_ids"], ["bank:1"])
            self.assertEqual(receipt["reviewed_rows_sha256"], ledger.digest(p / "reviewed.json"))

    def test_registration_cli_says_received_not_reconciled(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "config.json").write_text(json.dumps(config()))
            (p / "source.csv").write_text("date,amount,description\n2001-02-03,-12.00,SYNTHETIC\n")
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/ledger.py"), "register",
                "--config", str(p / "config.json"), "--input", str(p / "source.csv"), "--root", str(p / "private"),
                "--owner", "alice", "--source-type", "bank", "--account", "Assets:Alice:Bank", "--month", "2001-02"],
                check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(completed.stdout)["result"], "received")


class ParserAndEvidenceTests(unittest.TestCase):
    def test_actual_synthetic_pdf_extraction_and_bad_line(self):
        import parse_cmb
        def make_pdf(path, lines):
            stream = 'BT /F1 10 Tf 40 800 Td ' + ' 0 -15 Td '.join('(' + line + ') Tj' for line in lines) + ' ET'
            objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                       b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                       b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                       ('<< /Length ' + str(len(stream)) + ' >>\nstream\n' + stream + '\nendstream').encode('ascii')]
            raw = b'%PDF-1.4\n'; positions = [0]
            for i, obj in enumerate(objects, 1):
                positions.append(len(raw)); raw += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
            offset = len(raw)
            raw += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{n:010d} 00000 n \n'.encode() for n in positions[1:])
            raw += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(offset).encode() + b'\n%%EOF\n'
            path.write_bytes(raw)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'synthetic.pdf'
            make_pdf(path, ['2001-02-03 CNY -12.00 88.00 SYNTHETIC', '2001-02-04 CNY 3.00 91.00 SYNTHETIC'])
            self.assertEqual(len(parse_cmb.parse(path)), 2)
            make_pdf(path, ['2001-02-03 CNY -12.00 88.00 SYNTHETIC', '2001-02-04 CNY -7.OO 81.00 SYNTHETIC'])
            with self.assertRaisesRegex(ValueError, 'page 1, line 2'):
                parse_cmb.parse(path)

    def parse_text(self, text):
        import parse_cmb
        class Page:
            def extract_text(self): return text
        class PDF:
            pages = [Page()]
            def __enter__(self): return self
            def __exit__(self, *args): return False
        with patch.object(parse_cmb.pdfplumber, "open", return_value=PDF()):
            return parse_cmb.parse("synthetic-only.pdf")


    def test_descending_pdf_returns_correct_chronological_balances(self):
        result = self.parse_text("2001-02-04 CNY 3.00 91.00 SYNTHETIC\n2001-02-03 CNY -12.00 88.00 SYNTHETIC\n")
        self.assertEqual([r["date"] for r in result], ["2001-02-03", "2001-02-04"])
        self.assertEqual(result[-1]["balance"], "91.00")
        self.assertEqual(result[0]["line"], 2)

    def test_malformed_pdf_transaction_reports_page_and_line(self):
        with self.assertRaisesRegex(ValueError, "page 1, line 2"):
            self.parse_text("2001-02-03 CNY -12.00 88.00 SYNTHETIC\n2001-02-04 CNY -7.OO 81.00 SYNTHETIC\n")

    def test_pdf_balance_gap_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "balance continuity"):
            self.parse_text("2001-02-03 CNY -12.00 88.00 SYNTHETIC\n2001-02-05 CNY -5.00 76.00 SYNTHETIC\n")

    def test_textless_pdf_is_not_empty_success(self):
        with self.assertRaisesRegex(ValueError, "page 1"):
            self.parse_text("")

    def test_empty_import_state_cannot_close_after_hash_refresh(self):
        from test_safety import CoverageTests
        import coverage_gate
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = CoverageTests().setup_case(d)
            state = Path(d) / "source-import-state.json"
            state.write_text("{}")
            document["import_state_sha256"] = ledger.digest(state)
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")
            document["schema_version"] = 1
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "provisional")

    def test_wrong_source_count_even_with_refreshed_hash_blocks_close(self):
        from test_safety import CoverageTests
        with tempfile.TemporaryDirectory() as d:
            candidate, registry, document = CoverageTests().setup_case(d)
            state = Path(d) / "source-import-state.json"
            content = json.loads(state.read_text()); content["sources"][0]["statement_count"] += 1
            state.write_text(json.dumps(content)); document["import_state_sha256"] = ledger.digest(state)
            registry.write_text(json.dumps(document))
            self.assertEqual(ledger.report(candidate, "2001-02", config())["close_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
