#!/usr/bin/env python3
"""Synthetic first configuration, approval, reconciliation and next-month reuse."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from ledger import canonical, digest, immutable_write, safe_output
from review import doctor

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output = safe_output(output)
    def put(name, obj):
        return immutable_write(output / name, canonical(obj) if not isinstance(obj, str) else obj)
    def call(script, *args):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], check=True, stdout=subprocess.PIPE, text=True)
    private = output / "private"
    call("review.py", "init", "--root", private, "--owner", "alice", "--source", "alice:bank:Assets:Alice:Bank", "--source", "alice:alipay:Assets:Alice:Bank")
    config = private / "config.json"
    bank = put("inputs/bank.csv", "date,amount,description\n2001-02-03,-12.00,SYNTHETIC gift purchase\n2001-02-04,-8.00,SYNTHETIC food\n2001-02-05,3.00,SYNTHETIC confirmed food refund\n")
    alipay = put("inputs/alipay.csv", "交易时间,金额,收/支,收/付款方式,交易对方,商品说明,交易状态,交易订单号\n2001-02-03 10:00:00,12.00,支出,SYNTHETIC Bank,SYNTHETIC flower shop,SYNTHETIC gift,交易成功,synthetic-order-a\n")
    mapping = put("payment-map.json", {"SYNTHETIC Bank": {"account": "Assets:Alice:Bank", "backing": "bank"}})
    note = put("note.json", {"owner": "alice", "date": "2001-02-03", "purpose": "SYNTHETIC gift", "event_type": "gift", "amount": "12.00", "merchant": "SYNTHETIC flower shop"})
    call("ledger.py", "note", "--config", config, "--input", note, "--root", private)
    normalized = {}
    for source_type, source, kind in (("bank", bank, "bank-csv"), ("alipay", alipay, "alipay")):
        call("ledger.py", "register", "--config", config, "--input", source, "--root", private, "--owner", "alice", "--source-type", source_type, "--account", "Assets:Alice:Bank", "--month", "2001-02")
        target = output / "normalized" / (source_type + ".json")
        args = ["normalize", "--input", source, "--kind", kind, "--owner", "alice", "--output", target]
        args += ["--account", "Assets:Alice:Bank"] if source_type == "bank" else ["--payment-map", mapping]
        call("ledger.py", *args)
        normalized[source_type] = target
    merged = output / "merged.json"
    call("ledger.py", "match", "--bank", normalized["bank"], "--platform", normalized["alipay"], "--output", merged)
    queue = output / "review.json"
    # Freeze the initial no-rules review; the separate next-month stage tests reuse.
    call("review.py", "prepare", "--input", merged, "--output", queue, "--notes-root", private)
    items = json.loads(queue.read_text())["items"]
    assert all(not i["row"]["reviewed"] for i in items), "a note must not auto-approve"
    decisions = []
    for item in items:
        row = item["row"]
        choice = {"id": row["id"], "category": "Expenses:Gifts" if row["date"] == "2001-02-03" else "Expenses:Food"}
        if row["date"] == "2001-02-03":
            choice.update(scope="future", note_event_id=item["notes"][0]["event_id"], when={"owner": "alice", "account": "Assets:Alice:Bank", "currency": "CNY", "direction": "expense", "merchant": "SYNTHETIC flower shop"})
        decisions.append(choice)
    proof = {"confirmed_by": "synthetic-user", "confirmed_at": "2001-03-01T10:00:00+00:00", "confirmation_ref": "SYNTHETIC fixture approval; not a real user confirmation"}
    decisions_path = put("decisions.json", dict(review_sha256=digest(queue), decisions=decisions, **proof))
    reviewed = output / "reviewed.json"
    call("review.py", "approve", "--review", queue, "--decisions", decisions_path, "--output", reviewed, "--rules-dir", private / "rules")
    candidate = output / "candidate/household.beancount"
    call("ledger.py", "build", "--config", config, "--input", reviewed, "--output", candidate)
    sources = []
    for source_type, original, count, net in (("bank", bank, 3, "-17.00"), ("alipay", alipay, 1, "-12.00")):
        sources.append(dict(owner="alice", source_type=source_type, account="Assets:Alice:Bank", original_path=str(original), normalized_path=str(normalized[source_type]), **{"from": "2001-02-01", "through": "2001-02-28"}, statement_count=count, statement_net=net, **proof))
    totals = put("source-totals.json", {"schema_version": 1, "sources": sources})
    call("reconcile.py", "--input", totals, "--config", config, "--ledger", candidate, "--month", "2001-02")
    for command in ("report", "verify"):
        call("ledger.py", command, "--config", config, "--ledger", candidate, "--month", "2001-02", "--reports-dir", output / "reports")
    result = json.loads((output / "reports/2001-02.json").read_text())
    assert result["close_status"] == "complete" and result["pending"] == 0 and result["net_expenses"] == "17.00", result
    next_row = dict(items[0]["row"], id="synthetic-next-month", date="2001-03-03")
    next_input = put("next-month.json", [next_row])
    call("review.py", "prepare", "--input", next_input, "--output", output / "next-review.json", "--rules-dir", private / "rules")
    assert json.loads((output / "next-review.json").read_text())["pending"] == 0
    return {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if not doctor()["ready"]:
        raise SystemExit("Dependencies missing: run review.py doctor and install requirements.txt in the venv")
    first, second = run(a.output), run(a.output)
    if first != second:
        raise RuntimeError("first-use replay changed artifacts")
    print(json.dumps({"synthetic_only": True, "two_runs_byte_identical": True, "files": len(first), "close_status": "complete", "pending": 0, "net_expenses": "17.00", "private_rule_reused": True, "production_published": False}))


if __name__ == "__main__":
    main()
