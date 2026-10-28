#!/usr/bin/env python3
"""Portable, fail-closed household ledger candidate workflow.

Never imports production defaults or writes into this repository. All inputs
are explicit; unknown semantics remain pending; output is never auto-published.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = re.compile(r"(?:Assets|Liabilities|Equity|Income|Expenses)(?::[A-Z][\w-]*)+")
OWNER = re.compile(r"[a-z][a-z0-9-]{0,31}")


def money(value):
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise ValueError("money requires decimal text, never binary float")
    try:
        result = Decimal(value)
        if not result.is_finite() or result != result.quantize(Decimal("0.01")):
            raise ValueError("finite whole-cent amount required")
    except InvalidOperation as exc:
        raise ValueError("invalid money") from exc
    return format(result, ".2f")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def safe_output(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("financial output must be outside the skill repository")
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("financial output must be outside every Git worktree")
    return path


def immutable_write(path, content):
    """Atomic no-clobber publication; identical repeated writes are no-ops."""
    path = safe_output(path)
    raw = content.encode() if isinstance(content, str) else content
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".candidate-", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise FileExistsError("refusing to replace existing different output; use a new candidate path")
        if path.read_bytes() != raw:
            raise RuntimeError("write readback mismatch")
    finally:
        tmp.unlink(missing_ok=True)
    return path


def validate_config(config):
    if config.get("schema_version") != 1 or config.get("currency") != "CNY":
        raise ValueError("schema 1 and CNY required; no implicit FX conversion")
    owners = config.get("owners")
    if not isinstance(owners, list) or not owners or len(set(owners)) != len(owners):
        raise ValueError("unique nonempty owners required")
    if any(not isinstance(x, str) or not OWNER.fullmatch(x) for x in owners):
        raise ValueError("invalid owner identifier")
    keys = []
    for stream in config.get("required_streams", []):
        if stream.get("owner") not in owners or stream.get("source_type") not in {"bank", "alipay", "wechat"}:
            raise ValueError("invalid required stream")
        if not ACCOUNT.fullmatch(stream.get("account", "")) or not stream["account"].startswith(("Assets:", "Liabilities:")):
            raise ValueError("invalid funds account")
        keys.append(tuple(stream[k] for k in ("owner", "source_type", "account")))
    if not keys or len(keys) != len(set(keys)) or set(owners) != {k[0] for k in keys}:
        raise ValueError("every owner requires explicit unique sources")
    return config


def validate_row(row):
    if not isinstance(row.get("id"), str) or not row["id"] or "\n" in row["id"]:
        raise ValueError("source row id required")
    date.fromisoformat(row["date"])
    money(row["amount"])
    if not OWNER.fullmatch(row.get("owner", "")) or not ACCOUNT.fullmatch(row.get("account", "")):
        raise ValueError("invalid row owner/account")
    if not row["account"].startswith(("Assets:", "Liabilities:")):
        raise ValueError("source account must be an asset/liability")
    if row.get("currency") != "CNY" or row.get("kind") not in {"bank", "platform"}:
        raise ValueError("unsupported currency or row kind")


def match_rows(bank, platform, window_days=2, overlap_decisions=(), history=(), match_decisions=None, issues=None):
    """Match the combined platforms, never choose a nearest ambiguous row."""
    if not isinstance(window_days, int) or not 0 <= window_days <= 7:
        raise ValueError("window must be 0..7 days")
    all_rows = bank + platform
    for row in all_rows:
        validate_row(row)
    if len({r["id"] for r in all_rows}) != len(all_rows):
        raise ValueError("duplicate source row ids")
    if any(r["kind"] != "bank" for r in bank) or any(r["kind"] != "platform" for r in platform):
        raise ValueError("wrong source partition")
    from duplicates import deduplicate
    all_rows, exclusions = deduplicate(all_rows, overlap_decisions, history)
    bank = [r for r in all_rows if r["kind"] == "bank"]
    platform = [r for r in all_rows if r["kind"] == "platform"]
    match_decisions = match_decisions or {}
    if set(match_decisions) - {p["id"] for p in platform}:
        raise ValueError("matching decision references an unknown platform row")
    matches, wallet = {}, []
    blocked = set()
    planned = []
    for p in platform:
        if p.get("backing") == "wallet":
            wallet.append(dict(p))
            continue
        if p.get("backing") != "bank":
            raise ValueError("unknown funding method requires explicit mapping")
        candidates = [b for b in bank if all(b[k] == p[k] for k in ("owner", "account", "currency"))
                      and Decimal(b["amount"]) == Decimal(p["amount"])
                      and abs((date.fromisoformat(b["date"]) - date.fromisoformat(p["date"])).days) <= window_days]
        if p["id"] in match_decisions:
            candidates = [b for b in candidates if b["id"] == match_decisions[p["id"]]]
            if len(candidates) != 1:
                raise ValueError("matching confirmation is outside valid candidates")
        if len(candidates) != 1:
            if issues is None:
                raise ValueError("unmatched or ambiguous bank-card row: " + p["id"])
            issues.append({"type": "bank_match", "platform_id": p["id"], "candidates": [b["id"] for b in candidates]})
            blocked.update(b["id"] for b in candidates)
            continue
        planned.append((candidates[0], p))
    for b, p in planned:
        competition = sum(other["id"] == b["id"] for other, _ in planned) > 1
        if competition or b["id"] in blocked:
            if issues is None:
                raise ValueError("cross-platform competition for bank row: " + b["id"])
            issues.append({"type": "bank_competition", "platform_id": p["id"], "candidates": [b["id"]]})
            blocked.add(b["id"])
        else:
            matches[b["id"]] = p
    output = []
    for bank_row in bank:
        b = dict(bank_row)
        if b["id"] in matches:
            p = matches[b["id"]]
            b.update(platform_id=p["id"], platform_description=p.get("description", ""),
                     platform_source_sha256=p.get("source_sha256"),
                     platform_duplicate_source_ids=p.get("duplicate_source_ids", []),
                     platform_transaction_id=p.get("transaction_id"), platform_occurred_at=p.get("occurred_at"),
                     merchant=p.get("merchant", ""), goods=p.get("goods", ""))
        if b["id"] in blocked:
            b["source_issues"] = ["bank_match_requires_confirmation"]
        output.append(b)
    return sorted(output + wallet, key=lambda r: (r["date"], r["id"]))


def platform_amount(amount, direction, status):
    # A successful refund marked 不计收支 is NOT automatically an expense.
    if status not in {"交易成功", "支付成功", "已支付", "已收钱", "收款成功", "退款成功", "已退款"}:
        raise ValueError("unsupported/failed transaction status requires review: " + status)
    value = Decimal(money(str(amount).replace("¥", "").replace("￥", "").replace(",", "")))
    if value < 0 or direction not in {"收入", "支出"}:
        raise ValueError("unknown amount direction (including 不计收支 refund) requires review")
    if status in {"退款成功", "已退款"} and direction != "收入":
        raise ValueError("refund sign conflict requires original-order review")
    return money(value if direction == "收入" else -value)


def normalize(path, kind, owner, account=None, payment_map=None, encoding="utf-8-sig"):
    """Normalize supported exports without categories or approval claims."""
    path = Path(path)
    sha = digest(path)
    if kind == "bank-csv":
        with path.open(encoding=encoding, newline="") as handle:
            raw = list(csv.DictReader(handle))
        required = {"date", "amount", "description"}
        if not raw or not required <= set(raw[0]):
            raise ValueError("bank CSV requires date,amount,description; unknown format rejected")
    elif kind == "alipay":
        lines = path.read_text(encoding=encoding).splitlines()
        head = next((i for i, line in enumerate(lines)
                     if next(csv.reader([line]), [""])[0].strip() == "交易时间"), None)
        if head is None:
            raise ValueError("unsupported Alipay CSV header")
        raw = [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
               for row in csv.DictReader(lines[head:])]
    elif kind == "wechat":
        import openpyxl
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            values = list(workbook.active.iter_rows(values_only=True))
        finally:
            workbook.close()
        head = next((i for i, r in enumerate(values) if r and str(r[0]).strip() == "交易时间"), None)
        if head is None:
            raise ValueError("unsupported WeChat XLSX header")
        header = [str(c).strip() for c in values[head]]
        raw = [dict(zip(header, [str(c).strip() if c is not None else "" for c in r])) for r in values[head+1:] if r and r[0]]
    else:
        raise ValueError("unsupported parser")
    result = []
    for idx, source in enumerate(raw, 1):
        if kind == "bank-csv":
            row = {"date": source["date"], "amount": money(source["amount"]), "description": source["description"],
                   "account": account, "kind": "bank"}
            if source.get("balance"):
                row["balance"] = money(source["balance"])
            if source.get("original_sha256"):
                row["original_sha256"] = source["original_sha256"]
            if source.get("currency", "CNY") != "CNY":
                raise ValueError("bank row currency not CNY")
        else:
            method_key = "收/付款方式" if kind == "alipay" else "支付方式"
            mapping = (payment_map or {}).get(source.get(method_key, ""))
            if not mapping or mapping.get("backing") not in {"bank", "wallet"}:
                raise ValueError("unmapped funding method; no substring guessing")
            amount_key = "金额" if kind == "alipay" else "金额(元)"
            status_key = "交易状态" if kind == "alipay" else "当前状态"
            goods_key = "商品说明" if kind == "alipay" else "商品"
            row = {"date": source["交易时间"][:10],
                   "amount": platform_amount(source[amount_key], source.get("收/支", ""), source.get(status_key, "")),
                   "description": source.get("交易对方", "") + " " + source.get(goods_key, ""),
                   "merchant": source.get("交易对方", ""), "goods": source.get(goods_key, ""),
                   "account": mapping["account"], "backing": mapping["backing"], "kind": "platform"}
            row["occurred_at"] = source["交易时间"]
        transaction_id = next((source.get(k, "").strip() for k in
                               ("transaction_id", "交易订单号", "交易单号", "交易号") if source.get(k, "").strip()), None)
        if transaction_id:
            row["transaction_id"] = transaction_id
        row["source_type"] = "bank" if kind == "bank-csv" else kind
        row.update(id=f"{owner}:{kind}:{sha}:{idx}", owner=owner, currency="CNY", source_sha256=sha, source_row=idx)
        validate_row(row)
        result.append(row)
    if not result:
        raise ValueError("no transactions parsed; not evidence of no activity")
    return result


def record_note(root, payload, config):
    validate_config(config)
    owner = payload.get("owner")
    if owner not in config["owners"]:
        raise ValueError("note owner not configured")
    parsed = date.fromisoformat(payload["date"])
    if payload.get("event_type") not in {"expense", "refund", "transfer", "advance", "loan", "gift", "correction", "unknown"}:
        raise ValueError("invalid note type")
    if not str(payload.get("purpose", "")).strip():
        raise ValueError("purpose required")
    if payload.get("event_type") == "correction" and not payload.get("supersedes_event_id"):
        raise ValueError("correction requires predecessor id")
    if payload.get("event_type") == "correction":
        predecessor = payload["supersedes_event_id"]
        if not re.fullmatch(r"[a-f0-9]{64}", predecessor):
            raise ValueError("invalid predecessor event id")
        matches = list((Path(root) / "inbox" / owner).glob("*/" + predecessor + ".json"))
        if len(matches) != 1 or json.loads(matches[0].read_text()).get("owner") != owner:
            raise ValueError("correction predecessor must exist for this owner")
    payload = dict(payload)
    if payload.get("amount") is not None:
        payload["amount"] = money(payload["amount"])
        if Decimal(payload["amount"]) < 0:
            raise ValueError("note amount must be nonnegative; type carries semantics")
    token = hashlib.sha256(canonical(payload).encode()).hexdigest()
    event = dict(payload, schema_version=1, event_id=token, status="unprocessed")
    return immutable_write(Path(root) / "inbox" / owner / parsed.strftime("%Y-%m") / (token + ".json"), canonical(event))


def register_statement(source, root, *, owner, source_type, account, month, config):
    validate_config(config)
    month_bounds(month)
    identity = {"owner": owner, "source_type": source_type, "account": account}
    if identity not in config["required_streams"]:
        raise ValueError("statement stream not configured")
    source = Path(source)
    sha = digest(source)
    directory = Path(root) / "statement-inbox" / owner / month / source_type
    suffix = source.suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    target = immutable_write(directory / (sha + suffix), source.read_bytes())
    manifest = dict(identity, schema_version=1, month=month, state="received", sha256=sha,
                    bytes=target.stat().st_size, original_path=target.name,
                    imported=False, reconciliation="unverified")
    manifest_id = hashlib.sha256(canonical(identity).encode()).hexdigest()[:16]
    return immutable_write(directory / (sha + "-" + manifest_id + ".manifest.json"), canonical(manifest))


def month_bounds(month):
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("month must be YYYY-MM")
    year, number = map(int, month.split("-"))
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def validate_ledger_text(text):
    # The Beancount loader may execute plugins or follow includes. Reject those
    # before loading any user candidate; standalone files only in this kit.
    if re.search(r'^\s*(?:plugin|include)\s', text, re.M):
        raise ValueError("standalone ledger required; plugins/includes are not allowed")
    from beancount import loader
    entries, errors, _ = loader.load_string(text)
    if errors:
        raise ValueError("Beancount validation failed; inspect candidate locally at lines: " +
                         ", ".join(str(e.source.get("lineno", "?")) for e in errors[:3]))
    return entries


def build_ledger(rows, config, output):
    validate_config(config)
    if not rows:
        raise ValueError("no rows; do not infer a zero-activity month")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate source ids")
    from duplicates import deduplicate
    rows, _ = deduplicate(rows)
    accounts, transactions = set(), []
    for row in sorted(rows, key=lambda r: (r["date"], r["id"])):
        validate_row(row)
        if row["owner"] not in config["owners"]:
            raise ValueError("unconfigured owner")
        category = row.get("category") if row.get("reviewed") is True and not row.get("source_issues") else None
        pending = not category
        category = category or "Assets:Suspense:NeedsReview"
        if not ACCOUNT.fullmatch(category) or category == row["account"]:
            raise ValueError("invalid or self-offset category")
        if category.startswith("Equity:"):
            raise ValueError("equity adjustments require a separate reviewed adapter")
        accounts.update((row["account"], category))
        tags = f'#owner-{row["owner"]}' + (" #pending" if pending else "")
        description = json.dumps(str(row.get("description", "")), ensure_ascii=False)
        amount = money(row["amount"])
        traced_ids = sorted(set([row["id"], *row.get("duplicate_source_ids", []),
                                 *([row["platform_id"]] if row.get("platform_id") else []),
                                 *row.get("platform_duplicate_source_ids", [])]))
        transactions.append(f'{row["date"]} * {description} {tags}\n'
                            f'  source_id: {json.dumps(row["id"])}\n'
                            f'  source_ids: {json.dumps(json.dumps(traced_ids))}\n'
                            f'  review_basis: {json.dumps(str(row.get("review_basis", "unrecorded")))}\n'
                            f'  {row["account"]}  {amount} CNY\n'
                            f'  {category}  {money(-Decimal(amount))} CNY\n')
    opening = min(r["date"] for r in rows)
    text = '; Candidate only. Opening/closing balances require independent source evidence.\noption "operating_currency" "CNY"\n\n'
    text += "\n".join(f"{opening} open {account} CNY" for account in sorted(accounts)) + "\n\n"
    text += "\n".join(transactions)
    validate_ledger_text(text)
    immutable_write(output, text)
    return Path(output)


def report(ledger, month, config):
    from beancount.core import data
    from coverage_gate import coverage_status, close_gate, needs_review
    validate_config(config)
    ledger = Path(ledger).resolve()
    start, end = month_bounds(month)
    entries = validate_ledger_text(ledger.read_text())
    net_expenses = net_income = Decimal("0")
    pending = unassigned = ambiguous = 0
    uncategorized = False
    owners = {owner: Decimal("0") for owner in config["owners"]}
    categories = {}
    pending_items = []
    transaction_count = financial_count = pending_financial_count = 0
    for entry in entries:
        if not isinstance(entry, data.Transaction) or not start <= entry.date <= end:
            continue
        transaction_count += 1
        if any(p.units is not None and p.units.currency != "CNY" for p in entry.postings):
            raise ValueError("report rejects unsupported currency rather than silently omitting it")
        tags = entry.tags or frozenset()
        is_pending = "pending" in tags or any(needs_review(p.account) for p in entry.postings)
        pending += is_pending
        if is_pending:
            pending_items.append({"id": entry.meta.get("source_id", ""), "date": entry.date.isoformat(),
                                  "description": entry.narration})
        financial = [p for p in entry.postings if p.units and p.account.startswith(("Expenses:", "Income:"))]
        if not financial:
            continue
        financial_count += 1
        pending_financial_count += is_pending
        owner_tags = [t[6:] for t in tags if t.startswith("owner-")]
        matched = [o for o in owner_tags if o in owners]
        unassigned += not matched or any(o not in owners for o in owner_tags)
        ambiguous += len(owner_tags) > 1
        for posting in financial:
            amount = posting.units.number
            if posting.account.startswith("Expenses:"):
                net_expenses += amount
                categories[posting.account] = categories.get(posting.account, Decimal("0")) + amount
                uncategorized |= needs_review(posting.account)
                if len(matched) == 1 and len(owner_tags) == 1:
                    owners[matched[0]] += amount
            else:
                net_income -= amount
    coverage = coverage_status(ledger, month)
    coverage_path = ledger.parent / "coverage.json"
    if coverage["valid"] and coverage_path.exists():
        obj = json.loads(coverage_path.read_text())
        identity = lambda r: tuple(r.get(k) for k in ("owner", "source_type", "account"))
        if set(obj.get("expected_owners", [])) != set(config["owners"]) or set(map(identity, obj.get("required_streams", []))) != set(map(identity, config["required_streams"])):
            coverage["valid"] = False
            coverage["reasons"].append("coverage_does_not_match_independent_config")
    status, blockers = close_gate(coverage, pending=pending, unassigned=unassigned,
                                  ambiguous=ambiguous, uncategorized=uncategorized)
    return dict(schema_version=1, month=month, ledger_sha256=digest(ledger),
                close_status=status, blockers=blockers, net_expenses=money(net_expenses), net_income=money(net_income),
                pending=pending, unassigned=unassigned, ambiguous=ambiguous,
                owner_expenses={k: money(v) for k, v in owners.items()},
                categories={k: money(v) for k, v in sorted(categories.items())},
                pending_items=pending_items,
                scope={"schema_version": 1, "period_start": start.isoformat(), "period_end": end.isoformat(),
                       "filters": {"entry_type": "Transaction", "currency": "CNY", "owner_filter": None,
                                   "amount_accounts": ["Expenses:*", "Income:*"]},
                       "candidate_transactions": transaction_count, "financial_transactions": financial_count,
                       "pending_financial_transactions": pending_financial_count,
                       "pending_excluded_from_totals": pending_financial_count == 0,
                       "truncated": False, "full_within": "supplied_candidate_and_month",
                       "real_world_source_completeness": status,
                       "totals_policy": "Sum Expenses/Income postings, including pending financial postings; suspense and internal transfers excluded."},
                coverage=coverage, note="Unflagged does not mean explicitly human-confirmed. Missing sources are not zero spending.")


def write_report(ledger, month, config, output_dir):
    result = report(ledger, month, config)
    directory = safe_output(output_dir)
    json_path = immutable_write(directory / (month + ".json"), canonical(result))
    labels = {"unknown": "来源证据不足", "partial": "来源尚未齐全", "provisional": "待复核", "complete": "核对完成"}
    escape = lambda s: str(s).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;")
    scope = result["scope"]
    md = (f'# {month} 家庭月报\n\n状态：{labels[result["close_status"]]}（{result["close_status"]}）\n\n'
          f'支出科目净额：{result["net_expenses"]} 元；收入科目净额：{result["net_income"]} 元。\n\n'
          f'期间：{scope["period_start"]} 至 {scope["period_end"]}（含首尾）；筛选：当前候选内 CNY 交易，不另筛成员。\n\n'
          f'覆盖：{scope["candidate_transactions"]} 笔候选交易，其中 {scope["financial_transactions"]} 笔含支出/收入科目。'
          '未截断；仅为当前候选与月份内全量，不代表现实账单已齐。\n\n'
          f'待确认：{result["pending"]} 笔，其中 {scope["pending_financial_transactions"]} 笔含支出/收入科目并计入总额。'
          '暂挂及内部划转不计入支出/收入；负支出表示退款冲减。候选不是正式入账。\n\n' 
          '## 分类支出\n\n| 分类 | 净支出（元） |\n| --- | ---: |\n')
    md += ''.join(f'| {escape(k)} | {v} |\n' for k, v in result['categories'].items()) or '| 暂无已分类支出 | — |\n'
    md += '\n## 待办\n\n'
    md += ''.join(f'- {escape(x)}\n' for x in result['blockers']) or '- 本次校验没有阻断项。\n'
    md += ''.join(f'- {escape(x["date"])}：{escape(x["description"])}（{escape(x["id"])}）\n' for x in result['pending_items'])
    md += '\n来源覆盖或归属未齐时，不比较家庭成员消费高低。\n'
    immutable_write(directory / (month + ".md"), md)
    if json.loads(json_path.read_text()) != result:
        raise RuntimeError("report readback mismatch")
    return json_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    n = commands.add_parser("normalize")
    n.add_argument("--input", type=Path, required=True)
    n.add_argument("--kind", choices=["bank-csv", "alipay", "wechat"], required=True)
    n.add_argument("--owner", required=True)
    n.add_argument("--account")
    n.add_argument("--payment-map", type=Path)
    n.add_argument("--encoding", default="utf-8-sig")
    n.add_argument("--output", type=Path, required=True)
    m = commands.add_parser("match")
    m.add_argument("--bank", type=Path, nargs="+", required=True)
    m.add_argument("--platform", type=Path, nargs="*", default=[])
    m.add_argument("--output", type=Path, required=True)
    m.add_argument("--window-days", type=int, default=2)
    m.add_argument("--overlap-decisions", type=Path)
    m.add_argument("--history", type=Path, nargs="*", default=[])
    m.add_argument("--match-decisions", type=Path)
    m.add_argument("--issues-output", type=Path, help="write partial results and explicit unresolved matching issues")
    for name in ("build", "report", "verify", "note", "register"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", type=Path, required=True)
        if name == "build":
            cmd.add_argument("--input", type=Path, required=True)
            cmd.add_argument("--output", type=Path, required=True)
        elif name in {"report", "verify"}:
            cmd.add_argument("--ledger", type=Path, required=True)
            cmd.add_argument("--month", required=True)
            cmd.add_argument("--reports-dir", type=Path, required=True)
        elif name == "note":
            cmd.add_argument("--input", type=Path, required=True)
            cmd.add_argument("--root", type=Path, required=True)
        else:
            cmd.add_argument("--input", type=Path, required=True)
            cmd.add_argument("--root", type=Path, required=True)
            cmd.add_argument("--owner", required=True)
            cmd.add_argument("--source-type", required=True)
            cmd.add_argument("--account", required=True)
            cmd.add_argument("--month", required=True)
    args = parser.parse_args()
    read = lambda p: json.loads(Path(p).read_text())
    config = read(args.config) if hasattr(args, "config") else None
    summary_counts = {}
    if args.command == "normalize":
        out = normalize(args.input, args.kind, args.owner, args.account, read(args.payment_map) if args.payment_map else None, args.encoding)
        immutable_write(args.output, canonical(out))
        summary_counts["read_rows"] = len(out)
    elif args.command == "match":
        issues = [] if args.issues_output else None
        bank_rows = [r for p in args.bank for r in read(p)]
        platform_rows = [r for p in args.platform for r in read(p)]
        rows = match_rows(bank_rows, platform_rows, args.window_days,
                          read(args.overlap_decisions) if args.overlap_decisions else [],
                          [r for p in args.history for r in read(p)],
                          read(args.match_decisions) if args.match_decisions else {}, issues)
        immutable_write(args.output, canonical(rows))
        summary_counts["read_rows"] = len(bank_rows) + len(platform_rows)
        if args.issues_output:
            immutable_write(args.issues_output, canonical({"schema_version": 1, "issues": issues, "complete": not issues}))
    elif args.command == "build":
        input_rows = read(args.input)
        build_ledger(input_rows, config, args.output)
        from beancount.core import data
        from coverage_gate import needs_review
        actual = [e for e in validate_ledger_text(args.output.read_text()) if isinstance(e, data.Transaction)]
        summary_counts.update(read_rows=len(input_rows), candidate_included=len(actual),
                              pending=sum("pending" in (e.tags or ()) or any(needs_review(p.account) for p in e.postings) for e in actual))
    elif args.command == "report":
        write_report(args.ledger, args.month, config, args.reports_dir)
    elif args.command == "verify":
        actual = read(args.reports_dir / (args.month + ".json"))
        if actual != report(args.ledger, args.month, config):
            raise ValueError("report differs from current ledger/source evidence")
        # Also byte-verify the human-readable report via idempotent writer.
        write_report(args.ledger, args.month, config, args.reports_dir)
    elif args.command == "note":
        record_note(args.root, read(args.input), config)
    elif args.command == "register":
        register_statement(args.input, args.root, owner=args.owner, source_type=args.source_type,
                           account=args.account, month=args.month, config=config)
    states = {"register": "received", "note": "recorded", "normalize": "normalized", "match": "matched",
              "build": "candidate_created", "report": "report_written", "verify": "verified"}
    result = {"result": states[args.command], "operation": args.command, "production_published": False}
    if args.command == "match" and args.issues_output:
        result.update(result="partial" if issues else "matched", unresolved=len(issues))
    if args.command in {"report", "verify"}:
        result["close_status"] = read(args.reports_dir / (args.month + ".json"))["close_status"]
        monthly = read(args.reports_dir / (args.month + ".json"))
        summary_counts.update(candidate_included=monthly["scope"]["candidate_transactions"], pending=monthly["pending"])
    from presentation import processing_summary
    result["summary"] = processing_summary(args.command, **summary_counts)
    print(json.dumps(result, ensure_ascii=False))


def cli_entry(action):
    """Expected failures are explicit and do not dump raw ledger traces."""
    import sys
    try:
        result = action()
        return result if isinstance(result, int) else 0
    except (ValueError, KeyError, OSError, ImportError, RuntimeError) as exc:
        if isinstance(exc, ImportError): message = "Missing dependency; run review.py doctor and install requirements.txt in the active venv"
        elif isinstance(exc, FileNotFoundError): message = "Required input file is missing; check the explicitly supplied paths"
        elif isinstance(exc, OSError): message = "File operation failed; check permissions and use a fresh candidate output path"
        elif isinstance(exc, KeyError): message = "Input schema is missing a required field: " + str(exc)
        else: message = str(exc)
        from presentation import processing_summary
        print(json.dumps({"result": "error", "error_type": type(exc).__name__, "message": message,
                          "summary": processing_summary("failed_command", failure_reason=message)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(cli_entry(main))
