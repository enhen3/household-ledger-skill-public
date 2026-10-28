#!/usr/bin/env python3
"""Bind month-close claims to source counts, totals and ledger row traceability."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from ledger import canonical, digest, immutable_write, money, validate_config, validate_ledger_text, validate_row
from review import confirmation


def identity(row):
    return tuple(row[k] for k in ("owner", "source_type", "account"))


def key(row):
    return hashlib.sha256(canonical({k: row[k] for k in ("owner", "source_type", "account")}).encode()).hexdigest()


def absolute(value, base):
    p = Path(value)
    return (p if p.is_absolute() else base / p).resolve()


def traced_transactions(ledger):
    from beancount.core.data import Transaction
    entries = validate_ledger_text(Path(ledger).read_text(encoding="utf-8"))
    transactions = [e for e in entries if isinstance(e, Transaction)]
    index = {}
    for transaction in transactions:
        ids = json.loads(transaction.meta.get("source_ids", "[]"))
        if not ids:
            ids = [transaction.meta.get("source_id")]
        if not ids or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            raise ValueError("candidate transaction lacks unique source traceability")
        for identifier in ids:
            if identifier in index:
                raise ValueError("source row appears in multiple ledger transactions")
            index[identifier] = transaction
    return transactions, index


def verify_evidence(state, ledger, month, base):
    """Recompute from files; a hash of an empty state is never evidence."""
    if state.get("schema_version") != 2 or state.get("month") != month or state.get("ledger_sha256") != digest(ledger):
        raise ValueError("structured import evidence schema/month/ledger mismatch")
    sources = state.get("sources")
    if not isinstance(sources, list) or not sources or len({identity(s) for s in sources}) != len(sources):
        raise ValueError("one authoritative monthly export is required per source stream")
    transactions, index = traced_transactions(ledger)
    covered = set()
    for source in sources:
        confirmation(source)
        original = absolute(source["original_path"], base)
        normalized = absolute(source["normalized_path"], base)
        input_path = absolute(source.get("parsed_path", source["original_path"]), base)
        for p, sha in ((original, source["original_sha256"]), (normalized, source["normalized_sha256"]),
                       (input_path, source["input_sha256"])):
            if not p.is_file() or digest(p) != sha:
                raise ValueError("source or normalized evidence file changed")
        raw_rows = json.loads(normalized.read_text(encoding="utf-8"))
        if not isinstance(raw_rows, list):
            raise ValueError("normalized evidence must be a row list")
        rows = []
        for row in raw_rows:
            validate_row(row)
            if (row["owner"], row.get("source_type", row["kind"]), row["account"]) == identity(source):
                rows.append(row)
        if raw_rows and not rows:
            raise ValueError("normalized file has no rows for the declared source identity; not zero activity evidence")
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError("duplicated normalized source ids")
        lo, hi = date.fromisoformat(source["from"]), date.fromisoformat(source["through"])
        if lo > hi:
            raise ValueError("source date range inverted")
        for row in rows:
            if row.get("source_sha256") != source["input_sha256"] or not lo <= date.fromisoformat(row["date"]) <= hi:
                raise ValueError("normalized row does not belong to source hash/date range")
            if input_path != original and row.get("original_sha256") != source["original_sha256"]:
                raise ValueError("derived input lacks original PDF provenance")
            if row["id"] not in index:
                raise ValueError("normalized row is absent from candidate: " + row["id"])
            tx = index[row["id"]]
            if "owner-" + row["owner"] not in (tx.tags or ()):
                raise ValueError("source and ledger owner disagree")
            postings = [p for p in tx.postings if p.account == row["account"] and p.units and p.units.currency == "CNY"]
            if len(postings) != 1 or postings[0].units.number != Decimal(row["amount"]):
                raise ValueError("source amount/account differs from candidate posting")
            covered.add(id(tx))
        actual_net = money(sum((Decimal(r["amount"]) for r in rows), Decimal("0")))
        if type(source.get("statement_count")) is not int or source["statement_count"] != len(rows):
            raise ValueError("statement transaction count differs from parsed count")
        if money(source["statement_net"]) != actual_net:
            raise ValueError("statement signed total differs from parsed total")
        if source.get("parsed_count") != len(rows) or source.get("parsed_net") != actual_net:
            raise ValueError("stored reconciliation totals are stale")
        if any("balance" in r for r in rows):
            if not all("balance" in r for r in rows):
                raise ValueError("partial balance evidence")
            if len(rows) > 1:
                asc = all(rows[i]["date"] <= rows[i+1]["date"] and Decimal(rows[i+1]["balance"]) - Decimal(rows[i]["balance"]) == Decimal(rows[i+1]["amount"]) for i in range(len(rows)-1))
                desc = all(rows[i]["date"] >= rows[i+1]["date"] and Decimal(rows[i]["balance"]) - Decimal(rows[i+1]["balance"]) == Decimal(rows[i]["amount"]) for i in range(len(rows)-1))
                if not asc and not desc:
                    raise ValueError("source balance continuity differs from parsed movements")
    if any(id(t) not in covered for t in transactions if t.date.strftime("%Y-%m") == month):
        raise ValueError("candidate contains transactions outside declared source evidence")
    return {key(s): s for s in sources}


def record(spec_path, ledger, month, config):
    validate_config(config)
    ledger, spec_path = Path(ledger).resolve(), Path(spec_path).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError("reconciliation input schema 1 required")
    sources = []
    for entry in spec["sources"]:
        source = dict(entry)
        confirmation(source)
        for field in ("original_path", "normalized_path", "parsed_path"):
            if field in source:
                source[field] = str(absolute(source[field], spec_path.parent))
        original = Path(source["original_path"])
        normalized = Path(source["normalized_path"])
        input_path = Path(source.get("parsed_path", source["original_path"]))
        rows = [r for r in json.loads(normalized.read_text(encoding="utf-8"))
                if (r["owner"], r.get("source_type", r["kind"]), r["account"]) == identity(source)]
        source.update(original_sha256=digest(original), normalized_sha256=digest(normalized),
                      input_sha256=digest(input_path), parsed_count=len(rows),
                      parsed_net=money(sum((Decimal(r["amount"]) for r in rows), Decimal("0"))))
        sources.append(source)
    if set(map(identity, sources)) != set(map(identity, config["required_streams"])):
        raise ValueError("reconciliation sources must match independent config")
    state = {"schema_version": 2, "month": month, "ledger_sha256": digest(ledger), "sources": sources}
    verify_evidence(state, ledger, month, ledger.parent)
    streams = []
    for source in sources:
        streams.append({**{k: source[k] for k in ("owner", "source_type", "account")},
                        "received": {"path": source["original_path"], "sha256": source["original_sha256"],
                                     "from": source["from"], "through": source["through"]},
                        "imported_from": source["from"], "imported_through": source["through"],
                        "reconciliation": "verified", "reconciliation_id": key(source)})
    state_path = immutable_write(ledger.parent / "source-import-state.json", canonical(state))
    coverage = {"schema_version": 2, "month": month, "ledger_sha256": digest(ledger),
                "import_state_sha256": digest(state_path), "expected_owners": config["owners"],
                "required_streams": config["required_streams"], "streams": streams,
                "unresolved_source_issues": 0}
    return immutable_write(ledger.parent / "coverage.json", canonical(coverage))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True); p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True); p.add_argument("--month", required=True)
    a = p.parse_args()
    result = record(a.input, a.ledger, a.month, json.loads(a.config.read_text()))
    print(json.dumps({"coverage": str(result), "evidence_checked": True,
                      "note": "Run report; unresolved purposes still prevent complete"}))


if __name__ == "__main__":
    import sys
    from ledger import cli_entry
    sys.exit(cli_entry(main))
