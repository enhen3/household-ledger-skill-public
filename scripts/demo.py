#!/usr/bin/env python3
"""Run a synthetic end-to-end acceptance in an external directory, twice."""
from __future__ import annotations
import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from ledger import canonical, digest, immutable_write, safe_output

ROOT = Path(__file__).resolve().parents[1]


def run_demo(output):
    output = safe_output(output)
    config = json.loads((ROOT / "examples/config.json").read_text())
    config_path = immutable_write(output / "config.json", canonical(config))
    bank_specs = {"alice": [("2001-02-03", "-12.00", "SYNTHETIC food"),
                             ("2001-02-04", "3.00", "SYNTHETIC refund"),
                             ("2001-02-05", "-20.00", "SYNTHETIC transfer"),
                             ("2001-02-06", "4.00", "SYNTHETIC unknown receipt")],
                  "bob": [("2001-02-03", "-8.00", "SYNTHETIC food")]}
    def call(*args):
        subprocess.run([sys.executable, str(ROOT / "scripts/ledger.py"), *map(str, args)], check=True, stdout=subprocess.PIPE, text=True)
    bank_paths = []
    for owner, values in bank_specs.items():
        stream = next(s for s in config["required_streams"] if s["owner"] == owner and s["source_type"] == "bank")
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(["date", "amount", "description"])
        writer.writerows(values)
        source = immutable_write(output / "inputs" / (owner + "-synthetic.csv"), text.getvalue())
        call("register", "--input", source, "--root", output / "private", "--owner", owner,
             "--source-type", "bank", "--account", stream["account"], "--month", "2001-02", "--config", config_path)
        normalized = output / "normalized" / (owner + ".json")
        call("normalize", "--input", source, "--kind", "bank-csv", "--owner", owner, "--account", stream["account"], "--output", normalized)
        bank_paths.append(normalized)
    ali = immutable_write(output / "inputs/alipay-synthetic.csv",
                          "交易时间,金额,收/支,收/付款方式,交易对方,商品说明,交易状态\n2001-02-03 10:00:00,12.00,支出,Synthetic Bank,SYNTHETIC merchant,SYNTHETIC food,交易成功\n")
    mapping = immutable_write(output / "payment-map.json", canonical({"Synthetic Bank": {"account": "Assets:Alice:Bank", "backing": "bank"}}))
    call("register", "--input", ali, "--root", output / "private", "--owner", "alice", "--source-type", "alipay", "--account", "Assets:Alice:Bank", "--month", "2001-02", "--config", config_path)
    platform = output / "normalized/alipay.json"
    call("normalize", "--input", ali, "--kind", "alipay", "--owner", "alice", "--payment-map", mapping, "--output", platform)
    merged = output / "merged.json"
    call("match", "--bank", *bank_paths, "--platform", platform, "--output", merged)
    rows = json.loads(merged.read_text())
    for row in rows:
        description = row["description"]
        if "food" in description or "refund" in description:
            row.update(category="Expenses:Food", reviewed=True)
        elif "transfer" in description:
            row.update(category="Assets:Alice:Wallet", reviewed=True)
        # The synthetic unknown receipt is deliberately NOT approved.
    reviewed = immutable_write(output / "reviewed.json", canonical(rows))
    note = immutable_write(output / "note.json", canonical({"owner": "alice", "date": "2001-02-06", "purpose": "SYNTHETIC unknown receipt needs confirmation", "event_type": "unknown"}))
    call("note", "--input", note, "--root", output / "private", "--config", config_path)
    candidate = output / "candidate/household.beancount"
    call("build", "--input", reviewed, "--config", config_path, "--output", candidate)
    call("report", "--ledger", candidate, "--month", "2001-02", "--config", config_path, "--reports-dir", output / "reports")
    call("verify", "--ledger", candidate, "--month", "2001-02", "--config", config_path, "--reports-dir", output / "reports")
    result = json.loads((output / "reports/2001-02.json").read_text())
    assert result["net_expenses"] == "17.00", result
    assert result["net_income"] == "0.00" and result["pending"] == 1, result
    assert result["close_status"] == "unknown", result
    return {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}


def main():
    from review import doctor
    if not doctor()["ready"]:
        raise SystemExit("Dependencies missing: run review.py doctor and install requirements.txt in the venv")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first = run_demo(args.output)
    second = run_demo(args.output)
    if first != second:
        raise RuntimeError("replay changed output bytes")
    print(json.dumps({"synthetic_only": True, "two_runs_byte_identical": True, "files": len(first),
                      "bean_validation_errors": 0, "close_status": "unknown", "pending": 1,
                      "production_published": False}))


if __name__ == "__main__":
    main()
