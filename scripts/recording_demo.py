#!/usr/bin/env python3
"""New fictional month: explicit duplicate/purpose stops; self-test is separate."""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path
from ledger import (build_ledger, canonical, digest, immutable_write, match_rows,
                    normalize, register_statement, safe_output, write_report)
from review import approve, confirmation, initialize, prepare as prepare_review
from reconcile import record
from visualize import prepare as prepare_view

MONTH = "2001-04"
ACCOUNT = "Assets:Demo:Bank"
# Authored fictional source facts, not derived from a real person's statements.
ROWS = [
    ("2001-04-01", "12000.00", "虚构-月度工资", "Income:Salary"),
    ("2001-04-02", "-3200.00", "虚构-房租", "Expenses:Rent"),
    ("2001-04-03", "-486.50", "虚构-日常买菜", "Expenses:Food"),
    ("2001-04-05", "-86.00", "虚构-午餐", "Expenses:Food"),
    ("2001-04-06", "-128.00", "虚构-交通充值", "Expenses:Transport"),
    ("2001-04-07", "-68.00", "虚构-数字订阅", "Expenses:Software"),
    ("2001-04-08", "-260.00", "虚构-水电通信", "Expenses:Utilities"),
    ("2001-04-10", "-158.00", "虚构-书籍", "Expenses:Books"),
    ("2001-04-12", "-320.00", "虚构-商店付款-用途待确认", None),
    ("2001-04-14", "86.50", "虚构-买菜部分退款-关联4月3日原单", "Expenses:Food"),
    ("2001-04-16", "-48.00", "虚构-咖啡", "Expenses:Coffee"),
    ("2001-04-18", "-120.00", "虚构-电影", "Expenses:Entertainment"),
    ("2001-04-20", "-180.00", "虚构-体检", "Expenses:Health"),
    ("2001-04-22", "-680.00", "虚构-周末出行", "Expenses:Travel"),
    ("2001-04-24", "-210.00", "虚构-宠物用品", "Expenses:Pets"),
    ("2001-04-26", "-186.00", "虚构-晚餐", "Expenses:Food"),
]
# Independently specified fixture control totals, checked against raw inputs by tests.
BANK_COUNT = 16
BANK_NET = "5956.00"
FINAL_EXPENSES = "6044.00"
PARTIAL_EXPENSES = "5724.00"
ALIPAY_NET = "-806.50"
SELF_TEST_PROOF = {"confirmed_by": "synthetic-test-not-a-person",
                   "confirmed_at": "2001-05-01T00:00:00+00:00",
                   "confirmation_ref": "AUTOMATED SYNTHETIC SELF-TEST; not a human approval"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def put(root, name, value):
    return immutable_write(root / name, value if isinstance(value, str) else canonical(value))


def csv_text(rows, header):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


def prepare(output):
    output = safe_output(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("recording needs a new empty directory; never reset by deleting old evidence")
    output.mkdir(parents=True, exist_ok=True)
    initialize(output / "private", ["demo"], [dict(owner="demo", source_type=t, account=ACCOUNT) for t in ("bank", "alipay")])
    bank = put(output, "inputs/bank.csv", csv_text([r[:3] for r in ROWS], ["date", "amount", "description"]))
    overlap = put(output, "inputs/bank-overlap.csv", csv_text([ROWS[2][:3]], ["date", "amount", "description"]))
    alipay = put(output, "inputs/alipay.csv", csv_text([
        ["2001-04-03 10:00:00", "486.50", "支出", "虚构演示银行卡", "虚构菜市场", "日常买菜", "交易成功", "demo-order-food"],
        ["2001-04-12 14:00:00", "320.00", "支出", "虚构演示银行卡", "虚构商店", "商品用途未记录", "交易成功", "demo-order-unknown"],
    ], ["交易时间", "金额", "收/支", "收/付款方式", "交易对方", "商品说明", "交易状态", "交易订单号"]))
    mapping = put(output, "payment-map.json", {"虚构演示银行卡": {"account": ACCOUNT, "backing": "bank"}})
    config = read(output / "private/config.json")
    for kind, path in (("bank", bank), ("alipay", alipay)):
        register_statement(path, output / "private", owner="demo", source_type=kind, account=ACCOUNT, month=MONTH, config=config)
    normalized = {}
    for key, source in (("bank", bank), ("overlap", overlap), ("alipay", alipay)):
        normalized[key] = normalize(source, "alipay" if key == "alipay" else "bank-csv", "demo",
                                    account=ACCOUNT if key != "alipay" else None,
                                    payment_map=read(mapping) if key == "alipay" else None)
        put(output, "normalized/" + key + ".json", normalized[key])
    try:
        match_rows(normalized["bank"] + normalized["overlap"], normalized["alipay"])
    except ValueError as exc:
        if "possible overlapping exports" not in str(exc):
            raise
        stop = {"status": "paused_for_overlap_confirmation", "synthetic_only": True, "error": str(exc),
                "keep_id": normalized["bank"][2]["id"], "duplicate_id": normalized["overlap"][0]["id"],
                "approved": False, "production_published": False}
    else:
        raise AssertionError("expected overlapping export to stop before ledger creation")
    put(output, "duplicate-stop.json", stop)
    blank = {"confirmed_by": "", "confirmed_at": "", "confirmation_ref": ""}
    put(output, "overlap-confirmation.template.json", {**blank, "pairs": [{"keep_id": stop["keep_id"], "duplicate_id": stop["duplicate_id"]}]})
    put(output, "fixture-facts.json", {"synthetic_only": True, "month": MONTH,
        "bank_count": BANK_COUNT, "bank_signed_total": BANK_NET, "alipay_count": 2, "alipay_signed_total": ALIPAY_NET,
        "overlap_export_rows": 1, "overlap_is_same_food_purchase": True,
        "purpose_question": "4月12日 320元商店付款是什么用途？演示设定为给朋友的生日礼物；录制时由人实际回答。",
        "refund_link": "4月14日86.50元为4月3日486.50元买菜的部分退款，非收入；需要实际确认。",
        "classification_suggestions": [{"date": r[0], "description": r[2], "category": r[3]} for r in ROWS],
        "expected_after_confirmation": {"net_income": "12000.00", "net_expenses": FINAL_EXPENSES, "pending": 0},
        "note": "These are authored fictional control facts, not recorded human decisions."})
    put(output, "RECORDING-STOP.md", "# 虚构演示初始停点\n\n现在只发现疑似重复，尚未合并、分类或生成正式账本。先看 duplicate-stop.json，实际确认同一笔后填写确认副本，再运行 merge。不要把 template 的空确认字段填成假用户回执。接下来先确认15笔已知用途，保留320元待确认；最后由人实际回答用途。具体命令见 Skill 的 references/visual-demo.md。重录另建目录。\n")
    return stop


def merge(workspace, confirmation_path):
    workspace = safe_output(workspace)
    proof = read(confirmation_path)
    confirmation(proof)
    bank = read(workspace / "normalized/bank.json") + read(workspace / "normalized/overlap.json")
    rows = match_rows(bank, read(workspace / "normalized/alipay.json"), overlap_decisions=proof["pairs"])
    merged = put(workspace, "merged.json", rows)
    put(workspace, "overlap-confirmation.json", proof)
    queue = workspace / "review.json"
    prepare_review(merged, queue)
    suggestions = {r[0]: r[3] for r in ROWS}
    choices = [{"id": i["row"]["id"], "category": suggestions[i["row"]["date"]], "scope": "once"}
               for i in read(queue)["items"] if suggestions[i["row"]["date"]]]
    put(workspace, "partial-decisions.template.json", {"review_sha256": digest(queue),
        "confirmed_by": "", "confirmed_at": "", "confirmation_ref": "", "decisions": choices})
    totals = {"schema_version": 1, "sources": []}
    for kind, count, net in (("bank", BANK_COUNT, BANK_NET), ("alipay", 2, ALIPAY_NET)):
        totals["sources"].append(dict(owner="demo", source_type=kind, account=ACCOUNT,
            original_path=str(workspace / "inputs" / (kind + ".csv")),
            normalized_path=str(workspace / "normalized" / (kind + ".json")),
            **{"from": "2001-04-01", "through": "2001-04-30"}, statement_count=count, statement_net=net,
            confirmed_by="", confirmed_at="", confirmation_ref=""))
    put(workspace, "reconciliation.template.json", totals)
    return {"synthetic_only": True, "transactions": len(rows), "pending": read(queue)["pending"],
            "stop": "real category and independent source-total confirmation required", "production_published": False}


def stage(workspace, name, review_path, decisions_path, reconciliation_path=None):
    workspace = safe_output(workspace)
    if not name.isascii() or not name.replace("-", "").isalnum():
        raise ValueError("stage name must use ASCII letters/digits/hyphens")
    # This helper only operates on this generated fictional workspace.
    if read(workspace / "fixture-facts.json").get("synthetic_only") is not True:
        raise ValueError("recording helper requires its synthetic fixture workspace")
    review_path, decisions_path = Path(review_path).resolve(), Path(decisions_path).resolve()
    if workspace not in review_path.parents or workspace not in decisions_path.parents:
        raise ValueError("recording review and decisions must be inside this demo workspace")
    target = workspace / "stages" / name
    config = read(workspace / "private/config.json")
    reviewed = target / "reviewed.json"
    result = approve(review_path, decisions_path, reviewed)
    rows = read(reviewed)
    # Preserve previously approved rows; prepare() would deliberately reset them.
    next_queue = {"schema_version": 1, "input_sha256": digest(reviewed),
                  "pending": result["pending"], "items": [
                      {"row": row, "status": "confirmed" if row.get("reviewed") else "needs_review", "notes": [], "rule_ids": []} for row in rows]}
    put(target, "next-review.json", next_queue)
    candidate = build_ledger(rows, config, target / "candidate/household.beancount")
    if reconciliation_path:
        record(reconciliation_path, candidate, MONTH, config)
    report_path = write_report(candidate, MONTH, config, target / "reports")
    prepare_view(candidate, config, MONTH, target / "view", synthetic=True)
    report_data = read(report_path)
    return {"stage": str(target), "pending": report_data["pending"], "net_expenses": report_data["net_expenses"],
            "close_status": report_data["close_status"], "production_published": False}


def self_test(output):
    """Automation is visibly marked; never call this to fake a human recording."""
    output = safe_output(output)
    stop = prepare(output)
    overlap = put(output, "test-overlap-confirmation.json", {**SELF_TEST_PROOF,
        "pairs": [{"keep_id": stop["keep_id"], "duplicate_id": stop["duplicate_id"]}]})
    merge(output, overlap)
    partial = read(output / "partial-decisions.template.json")
    partial.update(SELF_TEST_PROOF)
    decisions = put(output, "test-partial-decisions.json", partial)
    totals = read(output / "reconciliation.template.json")
    for source in totals["sources"]:
        source.update(SELF_TEST_PROOF)
    evidence = put(output, "test-reconciliation.json", totals)
    first = stage(output, "partial", output / "review.json", decisions, evidence)
    assert first["pending"] == 1 and first["net_expenses"] == PARTIAL_EXPENSES and first["close_status"] == "provisional", first
    queue_path = output / "stages/partial/next-review.json"
    pending = [i["row"] for i in read(queue_path)["items"] if not i["row"].get("reviewed")]
    final = put(output, "test-final-decisions.json", {**SELF_TEST_PROOF, "review_sha256": digest(queue_path),
        "decisions": [{"id": pending[0]["id"], "category": "Expenses:Gifts", "scope": "once"}]})
    second = stage(output, "confirmed", queue_path, final, evidence)
    assert second["pending"] == 0 and second["net_expenses"] == FINAL_EXPENSES and second["close_status"] == "complete", second
    # Identical source identities in explicit imported history must emit no new money.
    replay = match_rows(read(output / "normalized/bank.json"), read(output / "normalized/alipay.json"), history=read(output / "merged.json") + read(output / "normalized/alipay.json"))
    assert replay == [], replay
    receipt = {"synthetic_only": True, "automated_confirmation_not_human": True,
               "duplicate_stopped": True, "repeat_import_new_transactions": len(replay),
               "partial": first, "confirmed": second, "production_published": False}
    put(output, "self-test-receipt.json", receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("prepare", "self-test"):
        sub.add_parser(name).add_argument("--output", type=Path, required=True)
    m = sub.add_parser("merge"); m.add_argument("--workspace", type=Path, required=True); m.add_argument("--confirmation", type=Path, required=True)
    s = sub.add_parser("stage")
    for key in ("workspace", "review", "decisions"):
        s.add_argument("--" + key, type=Path, required=True)
    s.add_argument("--name", required=True); s.add_argument("--reconciliation", type=Path)
    a = p.parse_args()
    if a.command == "prepare": result = prepare(a.output)
    elif a.command == "self-test": result = self_test(a.output)
    elif a.command == "merge": result = merge(a.workspace, a.confirmation)
    else: result = stage(a.workspace, a.name, a.review, a.decisions, a.reconciliation)
    print(canonical(result))


if __name__ == "__main__":
    from ledger import cli_entry
    raise SystemExit(cli_entry(main))
