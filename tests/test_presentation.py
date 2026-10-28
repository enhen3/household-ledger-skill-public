"""Presentation regressions: count actual artifacts, preserve failure gates."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ledger
from test_workflow import config, row


class PresentationTests(unittest.TestCase):
    def cli(self, directory, script, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, args)],
                              cwd=directory, capture_output=True, text=True)

    def put(self, directory, name, value):
        p = Path(directory) / name
        p.write_text(json.dumps(value))
        return p

    def test_month_scope_excludes_other_month_and_discloses_pending_amount(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'candidate.beancount'
            rows = [row(category='Expenses:Food', reviewed=True),
                    row('pending', '-5.00'), row('outside', '-99.00', date='2001-03-01', category='Expenses:Food', reviewed=True)]
            ledger.build_ledger(rows, config(), p)
            # Existing reports also accept a valid candidate with pending financial postings.
            p.write_text(p.read_text().replace('#owner-alice\n', '#owner-alice #pending\n', 1))
            result = ledger.report(p, '2001-02', config())
            self.assertEqual(result['net_expenses'], '12.00')
            self.assertEqual(result['pending'], 2)
            self.assertEqual(result['scope']['candidate_transactions'], 2)
            self.assertEqual(result['scope']['financial_transactions'], 1)
            self.assertEqual(result['scope']['pending_financial_transactions'], 1)
            self.assertFalse(result['scope']['pending_excluded_from_totals'])
            self.assertFalse(result['scope']['truncated'])
            self.assertEqual(result['scope']['period_end'], '2001-02-28')
            self.assertEqual(result['close_status'], 'unknown')
            ledger.write_report(p, '2001-02', config(), Path(d) / 'reports')
            text = (Path(d) / 'reports/2001-02.md').read_text()
            self.assertIn('1 笔含支出/收入科目并计入总额', text)
            self.assertNotIn('待确认资金不计入', text)

    def test_full_candidate_count_does_not_hide_pending_tail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'candidate.beancount'
            ledger.build_ledger([row(str(i), '-1.00') for i in range(25)], config(), p)
            r = ledger.report(p, '2001-02', config())
            self.assertEqual(r['scope']['candidate_transactions'], 25)
            self.assertEqual(len(r['pending_items']), 25)
            self.assertTrue(r['scope']['pending_excluded_from_totals'])
            self.assertEqual(r['net_expenses'], '0.00')
            self.assertFalse(r['scope']['truncated'])

    def test_build_summary_counts_deduplicated_candidate_not_input_rows(self):
        with tempfile.TemporaryDirectory() as d:
            c = self.put(d, 'config.json', config())
            a = row(source_sha256='first', transaction_id='synthetic-order', category='Expenses:Food', reviewed=True)
            b = dict(a, id='bank:second', source_sha256='second')
            source = self.put(d, 'rows.json', [a, b]); output = Path(d) / 'candidate.beancount'
            run = self.cli(d, 'ledger.py', 'build', '--config', c, '--input', source, '--output', output)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['result'], 'candidate_created')
            self.assertFalse(result['production_published'])
            self.assertEqual(result['summary']['read_rows'], 2)
            self.assertEqual(result['summary']['candidate_transactions'], 1)
            self.assertEqual(result['summary']['pending_items'], 0)
            self.assertIsNone(result['summary']['suspected_duplicate_rows'])
            self.assertEqual(ledger.report(output, '2001-02', config())['net_expenses'], '12.00')

    def test_suspected_overlap_failure_has_no_success_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            a = row(source_sha256='first')
            b = dict(a, id='bank:second', source_sha256='second')
            source = self.put(d, 'rows.json', [a, b]); output = Path(d) / 'merged.json'
            run = self.cli(d, 'ledger.py', 'match', '--bank', source, '--output', output)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, '')
            r = json.loads(run.stderr)
            self.assertEqual(r['result'], 'error')
            self.assertIn('overlapping exports', r['message'])
            self.assertIn('bank:second', r['message'])
            self.assertEqual(r['summary']['failed_operations'], 1)
            self.assertIsNone(r['summary']['failed_rows'])
            self.assertIsNone(r['summary']['candidate_transactions'])
            self.assertFalse(output.exists())

    def test_partial_match_keeps_issue_state_without_inventing_duplicate_count(self):
        with tempfile.TemporaryDirectory() as d:
            bank = self.put(d, 'bank.json', [row(), row('bank:2')])
            platform = self.put(d, 'platform.json', [row('p:1', kind='platform', backing='bank')])
            output = Path(d) / 'merged.json'; issues = Path(d) / 'issues.json'
            run = self.cli(d, 'ledger.py', 'match', '--bank', bank, '--platform', platform,
                           '--output', output, '--issues-output', issues)
            self.assertEqual(run.returncode, 0, run.stderr)
            r = json.loads(run.stdout)
            self.assertEqual((r['result'], r['unresolved']), ('partial', 1))
            self.assertEqual(r['summary']['read_rows'], 3)
            self.assertIsNone(r['summary']['suspected_duplicate_rows'])
            self.assertIsNone(r['summary']['candidate_transactions'])
            self.assertFalse(json.loads(issues.read_text())['complete'])

    def test_once_approval_summary_preserves_other_pending(self):
        with tempfile.TemporaryDirectory() as d:
            source = self.put(d, 'rows.json', [row(), row('bank:2', '-8.00')])
            queue = Path(d) / 'review.json'
            prep = self.cli(d, 'review.py', 'prepare', '--input', source, '--output', queue)
            self.assertEqual(prep.returncode, 0, prep.stderr)
            q = json.loads(prep.stdout)
            self.assertEqual((q['items'], q['pending'], q['summary']['pending_items']), (2, 2, 2))
            decisions = self.put(d, 'decisions.json', {'review_sha256': q['review_sha256'],
                'confirmed_by': 'synthetic-user', 'confirmed_at': '2001-03-01T10:00:00+00:00',
                'confirmation_ref': 'SYNTHETIC one-row approval',
                'decisions': [{'id': 'bank:1', 'category': 'Expenses:Gifts', 'scope': 'once'}]})
            result = self.cli(d, 'review.py', 'approve', '--review', queue, '--decisions', decisions,
                              '--output', Path(d) / 'reviewed.json')
            self.assertEqual(result.returncode, 0, result.stderr)
            r = json.loads(result.stdout)
            self.assertEqual((r['approved'], r['pending'], r['rules_created']), (1, 1, 0))
            self.assertEqual(r['summary']['pending_items'], 1)
            self.assertIsNone(r['summary']['candidate_transactions'])

    def test_missing_input_reports_unknown_row_not_zero_failures(self):
        with tempfile.TemporaryDirectory() as d:
            run = self.cli(d, 'ledger.py', 'normalize', '--input', Path(d) / 'missing.csv',
                '--kind', 'bank-csv', '--owner', 'alice', '--account', 'Assets:Alice:Bank', '--output', Path(d) / 'out.json')
            self.assertEqual(run.returncode, 1)
            r = json.loads(run.stderr)
            self.assertEqual(r['error_type'], 'FileNotFoundError')
            self.assertEqual(r['summary']['failed_operations'], 1)
            self.assertIsNone(r['summary']['source_detail'])
            self.assertIsNone(r['summary']['read_rows'])


if __name__ == '__main__':
    unittest.main()
