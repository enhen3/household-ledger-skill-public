#!/usr/bin/env python3
"""Private, resumable review queue; notes suggest, explicit approvals decide."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from ledger import ACCOUNT, canonical, digest, immutable_write, money, safe_output, validate_config, validate_row


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def object_id(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def confirmation(value):
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k].strip()
                                          for k in ("confirmed_by", "confirmed_at", "confirmation_ref")):
        raise ValueError("record who confirmed, ISO time and the actual confirmation reference")
    if datetime.fromisoformat(value["confirmed_at"]).tzinfo is None:
        raise ValueError("confirmation time requires timezone")
    return {k: value[k] for k in ("confirmed_by", "confirmed_at", "confirmation_ref")}


def initialize(root, owners, streams):
    root = safe_output(root)
    config = validate_config({"schema_version": 1, "owners": owners, "currency": "CNY", "required_streams": streams})
    immutable_write(root / "config.json", canonical(config))
    for directory in ("inbox", "rules", "runs", "statement-inbox"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    return {"config": str(root / "config.json"), "next": "确认每种支付方式对应的资金账户，再登记和规范化账单"}


def validate_rule(rule):
    if rule.get("schema_version") != 1:
        raise ValueError("unsupported private rule schema")
    confirmation(rule)
    criteria = rule.get("when", {})
    allowed = {"owner", "account", "currency", "merchant", "description", "direction", "amount"}
    if set(criteria) - allowed or not {"owner", "account", "currency", "direction"} <= set(criteria):
        raise ValueError("rule must specify owner, funds account, currency and direction")
    if not any(criteria.get(k) for k in ("merchant", "description")) or any(not str(v).strip() for v in criteria.values()):
        raise ValueError("rule needs an exact nonempty merchant/description; broad name rules are not allowed")
    if criteria["direction"] not in {"income", "expense"} or criteria["currency"] != "CNY":
        raise ValueError("unsupported rule direction/currency")
    category = rule.get("category", "")
    if not ACCOUNT.fullmatch(category) or not category.startswith(("Expenses:", "Income:")):
        raise ValueError("reusable rules only classify income/expenses; transfers require transaction review")
    if "amount" in criteria:
        money(criteria["amount"])
    return rule


def rule_matches(rule, row):
    actual = dict(row, direction="income" if Decimal(row["amount"]) > 0 else "expense")
    return all((money(actual[k]) == money(v)) if k == "amount" else actual.get(k) == v
               for k, v in rule["when"].items())


def load_rules(directory):
    if not directory:
        return []
    root = Path(directory)
    retired = set()
    for path in (root / "retirements").glob("*.json"):
        receipt = read(path); confirmation(receipt)
        retired.update(receipt["rule_ids"])
    rules = []
    for path in sorted(root.glob("*.json")):
        rule = validate_rule(read(path))
        if path.stem != object_id(rule):
            raise ValueError("private rule changed in place; create a confirmed replacement")
        if path.stem not in retired:
            rules.append(dict(rule, rule_id=path.stem))
    return rules


def active_notes(root):
    if not root:
        return []
    notes = [read(p) for p in sorted((Path(root) / "inbox").glob("*/*/*.json"))]
    indexed = {n["event_id"]: n for n in notes}
    replaced = set()
    for n in notes:
        if n.get("event_type") == "correction":
            old = n.get("supersedes_event_id")
            if old not in indexed or indexed[old]["owner"] != n["owner"] or old in replaced:
                raise ValueError("missing or competing note correction; resolve before use")
            replaced.add(old)
    return [n for n in notes if n["event_id"] not in replaced]


def note_matches(note, row):
    if note["owner"] != row["owner"] or note["date"] != row["date"]:
        return False
    if note.get("amount") is not None and Decimal(note["amount"]) != abs(Decimal(row["amount"])):
        return False
    if note.get("transaction_id") and note["transaction_id"] not in {row.get("transaction_id"), row.get("platform_transaction_id")}:
        return False
    if note.get("merchant") and note["merchant"] != row.get("merchant"):
        return False
    return True  # Date-only context remains a suggestion and never approves money.


def prepare(input_path, output, *, notes_root=None, rules_dir=None):
    rows, rules, notes = read(input_path), load_rules(rules_dir), active_notes(notes_root)
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate review source ids")
    items = []
    for row in rows:
        validate_row(row)
        row = dict(row, reviewed=False)
        row.pop("category", None)
        matching = [r for r in rules if rule_matches(r, row)]
        hints = [{k: n[k] for k in ("event_id", "purpose", "event_type")} for n in notes if note_matches(n, row)]
        status = "needs_review"
        if matching and len({r["category"] for r in matching}) == 1 and not row.get("source_issues"):
            row.update(category=matching[0]["category"], reviewed=True,
                       review_basis="approved_rules:" + ",".join(sorted(r["rule_id"] for r in matching)))
            status = "approved_rule"
        elif matching:
            status = "conflicting_rules" if len({r["category"] for r in matching}) > 1 else "source_issue"
        items.append({"row": row, "status": status, "notes": hints,
                      "rule_ids": [r["rule_id"] for r in matching]})
    result = {"schema_version": 1, "input_sha256": digest(input_path), "items": items,
              "pending": sum(not i["row"]["reviewed"] for i in items)}
    immutable_write(output, canonical(result))
    return result


def approve(review_path, decisions_path, output, *, rules_dir=None):
    queue, decisions = read(review_path), read(decisions_path)
    if queue.get("schema_version") != 1 or decisions.get("review_sha256") != digest(review_path):
        raise ValueError("review changed; decisions must target its exact SHA-256")
    proof = confirmation(decisions)
    indexed = {i["row"]["id"]: i for i in queue["items"]}
    selected, new_rules = {}, []
    for decision in decisions.get("decisions", []):
        identifier = decision["id"]
        if identifier not in indexed or identifier in selected:
            raise ValueError("unknown or duplicate decision id")
        row = dict(indexed[identifier]["row"])
        category = decision.get("category", "")
        if not ACCOUNT.fullmatch(category) or category.startswith("Equity:") or category == row["account"]:
            raise ValueError("invalid confirmed category")
        if row.get("source_issues"):
            raise ValueError("resolve source matching before approving category")
        note_id = decision.get("note_event_id")
        if note_id and note_id not in {n["event_id"] for n in indexed[identifier]["notes"]}:
            raise ValueError("note confirmation is not in this review queue")
        row.update(category=category, reviewed=True, review_basis="confirmation:" + proof["confirmation_ref"])
        if note_id:
            row["note_event_id"] = note_id
        scope = decision.get("scope", "once")
        if scope not in {"once", "future"}:
            raise ValueError("decision scope must be once or future")
        if scope == "future":
            if not rules_dir:
                raise ValueError("future rule requires a private rules directory")
            rule = validate_rule(dict(schema_version=1, when=decision["when"], category=category, **proof))
            if not rule_matches(rule, row):
                raise ValueError("future rule must match the confirmed transaction")
            new_rules.append(rule)
        selected[identifier] = row
    rows = [selected.get(i["row"]["id"], i["row"]) for i in queue["items"]]
    receipt = dict(schema_version=1, review_sha256=digest(review_path), decisions_sha256=digest(decisions_path),
                   reviewed_rows_sha256=object_id(rows), approved_ids=sorted(selected),
                   note_links=[{"id": r["id"], "event_id": r["note_event_id"]} for r in selected.values() if r.get("note_event_id")],
                   **proof)
    retired = decisions.get("retire_rule_ids", [])
    import re
    if retired and (not rules_dir or any(not isinstance(rid, str) or not re.fullmatch(r"[a-f0-9]{64}", rid)
                                         or not (Path(rules_dir) / (rid + ".json")).is_file() for rid in retired)):
        raise ValueError("retirement references an unknown private rule")
    # Validate everything before any artifact is written. Replays are byte-identical.
    immutable_write(output, canonical(rows))
    immutable_write(Path(output).with_suffix(".review-receipt.json"), canonical(receipt))
    for rule in new_rules:
        immutable_write(Path(rules_dir) / (object_id(rule) + ".json"), canonical(rule))
    if retired:
        retirement = dict(rule_ids=sorted(set(retired)), **proof)
        immutable_write(Path(rules_dir) / "retirements" / (object_id(retirement) + ".json"), canonical(retirement))
    return {"approved": len(selected), "pending": sum(not r.get("reviewed") for r in rows), "rules_created": len(new_rules)}


def doctor():
    dependencies = {}
    for name in ("beancount", "pdfplumber", "openpyxl", "fava"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = None
    return {"python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 11),
            "dependencies": dependencies, "ready": sys.version_info >= (3, 11) and all(dependencies.values())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    init = sub.add_parser("init"); init.add_argument("--root", type=Path, required=True)
    init.add_argument("--owner", action="append", required=True)
    init.add_argument("--source", action="append", required=True, help="owner:source_type:funds_account")
    prep = sub.add_parser("prepare"); prep.add_argument("--input", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True); prep.add_argument("--notes-root", type=Path)
    prep.add_argument("--rules-dir", type=Path)
    a = sub.add_parser("approve"); a.add_argument("--review", type=Path, required=True)
    a.add_argument("--decisions", type=Path, required=True); a.add_argument("--output", type=Path, required=True)
    a.add_argument("--rules-dir", type=Path)
    args = p.parse_args()
    if args.command == "doctor": result = doctor()
    elif args.command == "init":
        streams = [dict(zip(("owner", "source_type", "account"), s.split(":", 2))) for s in args.source]
        result = initialize(args.root, args.owner, streams)
    elif args.command == "prepare":
        queue = prepare(args.input, args.output, notes_root=args.notes_root, rules_dir=args.rules_dir)
        result = {"items": len(queue["items"]), "pending": queue["pending"], "review_sha256": digest(args.output)}
    else: result = approve(args.review, args.decisions, args.output, rules_dir=args.rules_dir)
    if args.command in {"prepare", "approve"}:
        from presentation import processing_summary
        result["summary"] = processing_summary(args.command,
            read_rows=result["items"] if args.command == "prepare" else None, pending=result["pending"])
    print(json.dumps(result, ensure_ascii=False))
    return 1 if args.command == "doctor" and not result["ready"] else 0


if __name__ == "__main__":
    from ledger import cli_entry
    sys.exit(cli_entry(main))
