#!/usr/bin/env python3
"""Read-only local Fava view of a validated monthly candidate, never production."""
from __future__ import annotations

import argparse
import html
import importlib.metadata
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlsplit

from ledger import (canonical, digest, immutable_write, month_bounds, report,
                    safe_output, validate_ledger_text)

FAVA_VERSION = "1.30.16"
LABELS = {"unknown": "来源证据不足", "partial": "来源未齐", "provisional": "待复核", "complete": "核对完成"}
CATEGORIES = {"Rent": "住房", "Food": "餐饮与买菜", "Transport": "交通", "Software": "数字订阅",
              "Utilities": "水电通信", "Books": "书籍", "Gifts": "礼物", "Coffee": "咖啡",
              "Entertainment": "娱乐", "Health": "健康", "Travel": "出行", "Pets": "宠物"}


def prepare(ledger, config, month, output, *, synthetic=False):
    """Strip all runtime directives, retain typed transactions/opens for one month."""
    from beancount.core import data
    from beancount.parser import printer
    ledger, output = Path(ledger).resolve(), safe_output(output)
    text = ledger.read_text(encoding="utf-8")
    entries = validate_ledger_text(text)
    # A Fava extension or a Document can execute code / expose files even when
    # Beancount's own plugin/include guard passed. Accept only our candidate types.
    if any(not isinstance(e, (data.Open, data.Transaction)) for e in entries):
        raise ValueError("viewer accepts candidate Open/Transaction entries only; no custom/document/query directives")
    result = report(ledger, month, config)
    start, end = month_bounds(month)
    selected = [e for e in entries if isinstance(e, data.Open) or start <= e.date <= end]
    title = f'{month} 只读候选 · 待确认 {result["pending"]} · {LABELS[result["close_status"]]} · 非正式'
    if synthetic:
        title = "虚构演示 · " + title
    header = (f'option "title" {json.dumps(title, ensure_ascii=False)}\n'
              'option "operating_currency" "CNY"\n'
              '2000-01-01 custom "fava-option" "language" "zh_CN"\n'
              '2000-01-01 custom "fava-option" "default-page" "income_statement"\n'
              '2000-01-01 custom "fava-sidebar-link" "候选状态与口径" "/ledger-status"\n')
    # Re-serialize typed entries; never copy arbitrary original options/comments.
    snapshot = header + "\n".join(printer.format_entry(e) for e in selected)
    snapshot_path = immutable_write(output / "view.beancount", snapshot)
    result = dict(result, synthetic_only=synthetic, production_published=False,
                  display_mode="read_only_monthly_candidate", viewer="Fava " + FAVA_VERSION)
    report_path = immutable_write(output / "report.json", canonical(result))
    manifest = {"schema_version": 1, "month": month, "source_sha256": digest(ledger),
                "snapshot_sha256": digest(snapshot_path), "report_sha256": digest(report_path),
                "fava_version": FAVA_VERSION, "read_only": True, "host": "127.0.0.1"}
    immutable_write(output / "view-manifest.json", canonical(manifest))
    return {"view": str(output), "pending": result["pending"], "close_status": result["close_status"],
            "transactions": result["scope"]["candidate_transactions"], "production_published": False}


def load_view(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "view-manifest.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("fava_version") != FAVA_VERSION:
        raise ValueError("unsupported view manifest; prepare a new view")
    for filename, key in (("view.beancount", "snapshot_sha256"), ("report.json", "report_sha256")):
        if (directory / filename).is_symlink() or digest(directory / filename) != manifest[key]:
            raise ValueError("view changed since preparation; prepare a new directory")
    report_data = json.loads((directory / "report.json").read_text())
    # Defense in depth: a manifest is a checksum, not authorization to run code.
    from beancount.core import data
    snapshot_text = (directory / "view.beancount").read_text()
    if any(name not in {"title", "operating_currency"} for name in re.findall(r'^\s*option\s+"([^"]+)"', snapshot_text, re.M)):
        raise ValueError("untrusted option in viewer snapshot")
    entries = validate_ledger_text(snapshot_text)
    expected = {("fava-option", "language", "zh_CN"),
                ("fava-option", "default-page", "income_statement"),
                ("fava-sidebar-link", "候选状态与口径", "/ledger-status")}
    for entry in entries:
        if isinstance(entry, data.Custom):
            if (entry.type, *(v.value for v in entry.values)) not in expected:
                raise ValueError("untrusted custom directive in viewer snapshot")
        elif not isinstance(entry, (data.Open, data.Transaction)):
            raise ValueError("untrusted entry in viewer snapshot")
    return directory, report_data


def status_html(result, fava_url):
    e = html.escape
    scope = result["scope"]
    categories = result["categories"]
    maximum = max((abs(Decimal(v)) for v in categories.values()), default=Decimal(0))
    bars = []
    for name, amount in categories.items():
        width = float(abs(Decimal(amount)) / maximum * 100) if maximum else 0
        label = CATEGORIES.get(name.split(":")[-1], name)
        bars.append(f'<tr><td>{e(label)}<small>{e(name)}</small></td><td><span class="bar" style="width:{width:.2f}%"></span></td><td>{e(amount)}</td></tr>')
    pending = "".join(f'<li>{e(i["date"])} · {e(i["description"])}<small>来源 ID：{e(i["id"])}</small></li>' for i in result["pending_items"])
    warning = "全部金额、人物、确认均为虚构演示，不代表真实家庭成效。" if result["synthetic_only"] else "数据来自你明确指定的本地候选；不要对外分享此页面。"
    readable = {"pending_transactions": "仍有交易用途待确认", "owner_attribution_incomplete": "成员归属待核", "uncategorized_transactions": "仍有未分类交易", "unresolved_source_issues": "来源对应关系待核", "coverage_missing": "尚未提供来源覆盖证据", "structured_reconciliation_evidence_required": "缺少结构化核对证据"}
    blocked = "；".join(readable.get(x, "来源核对未完成，请查看机器报告中的具体原因") for x in result["blockers"]) or "当前候选无核对阻断项；仍未发布到正式账本。"
    if not scope["candidate_transactions"]:
        blocked = "候选无交易，不能视为零活动或已完整核对。" + blocked
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>候选账本 · {e(result["month"])}</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;color:#18332c;background:#f5f7f4;margin:0}}main{{max-width:980px;margin:40px auto;padding:0 28px}}h1{{font-size:32px}}.badge{{background:#e6eee7;padding:7px 13px;border-radius:8px;display:inline-block}}.warn{{background:#fff0d3;padding:18px;border-left:4px solid #b77918}}.cards{{display:flex;gap:18px;flex-wrap:wrap}}.card{{flex:1;min-width:180px;background:white;padding:22px;border:1px solid #e1e8e1;border-radius:12px}}strong{{font-size:30px;display:block}}small{{display:block;color:#607269;font-size:12px;overflow-wrap:anywhere}}a{{color:#135d45}}.button{{background:#175d46;color:white;padding:12px 18px;border-radius:8px;display:inline-block;text-decoration:none;margin:12px 0}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #e7ece7}}td:nth-child(2){{width:40%}}td:last-child{{text-align:right}}.bar{{display:block;height:14px;background:#3d8167;min-width:1px;border-radius:3px}}li{{margin:12px 0}}code{{overflow-wrap:anywhere}}</style>
<main><span class="badge">只读 · 候选账本 · 尚未正式入账</span><h1>{e(result["month"])} 家庭收支</h1><p>{e(warning)}</p>
<div class="warn"><b>状态：{e(LABELS[result["close_status"]])}（{e(result["close_status"])}） · 待确认 {result["pending"]} 笔</b><br>{e(blocked)}</div>
<p>期间 {e(scope["period_start"])} 至 {e(scope["period_end"])}，CNY，当前候选全部成员。</p>
<div class="cards"><section class="card">收入科目净额<strong>¥ {e(result["net_income"])}</strong></section><section class="card">支出科目净额<strong>¥ {e(result["net_expenses"])}</strong></section><section class="card">候选交易<strong>{scope["candidate_transactions"]} 笔</strong></section></div>
<p><a class="button" href="{e(fava_url)}">打开 Fava 图表与逐笔流水 →</a> <a href="report.json">查看本次机器报告</a></p>
<h2>分类净支出</h2><table><thead><tr><th>分类</th><th>相对金额</th><th>元</th></tr></thead><tbody>{''.join(bars) or '<tr><td colspan="3">暂无已分类支出；不代表零消费。</td></tr>'}</tbody></table>
<p>负支出是退款冲减；条形长度显示绝对值，金额列保留符号。含收支科目 {scope["financial_transactions"]} 笔；其中 pending 收支 {scope["pending_financial_transactions"]} 笔计入总额。暂挂及内部转账不计入收支。</p>
<h2>待确认用途</h2><ul>{pending or '<li>当前候选没有待确认用途。</li>'}</ul>
<h2>范围与边界</h2><p>未截断，仅在这个候选与月份内全量；现实账单完整性见上方状态。Fava 可继续筛选，筛选后不得把子集当全量。候选不含独立期初余额，因此资产负债页不是完整家庭净资产。</p><p>页面不能批准用途、改写账目或发布生产账本。确认后请生成新候选和新展示目录；当前页面是冻结快照，不会自动变成最新状态。关闭终端服务即可停止访问。</p><small>展示：Fava {FAVA_VERSION}（MIT）；本适配层作者 Soren（GPL-2.0-only）。飞书接入未内置。</small></main></html>'''


def native_fava_path(app):
    return quote(f'/{app.config["LEDGERS"].first_slug()}/income_statement/', safe="/")


def create_view_app(directory):
    if importlib.metadata.version("fava") != FAVA_VERSION:
        raise ValueError("install the pinned Fava version from requirements.txt in this venv")
    from fava.application import create_app
    from flask import Response, abort, redirect, request
    directory, result = load_view(directory)
    app = create_app([str(directory / "view.beancount")], read_only=True)
    native_path = native_fava_path(app)
    page = status_html(result, native_path)

    @app.before_request
    def local_only():
        if urlsplit("http://" + request.host).hostname not in {"127.0.0.1", "localhost"}:
            abort(403)
        if request.path == "/":
            return redirect(native_path)

    @app.after_request
    def local_assets(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/ledger-status")
    def ledger_status():
        return Response(page, content_type="text/html; charset=utf-8")

    @app.get("/report.json")
    def machine_report():
        return Response(canonical(result), content_type="application/json")

    return app


def serve(directory, port):
    if not 1024 <= port <= 65535:
        raise ValueError("choose an unprivileged port 1024..65535")
    from cheroot.wsgi import Server
    app = create_view_app(directory)
    server = Server(("127.0.0.1", port), app)
    print(f"Native Fava (read-only candidate): http://127.0.0.1:{port}{native_fava_path(app)} ; Ctrl-C stops this process.", flush=True)
    print(f"Optional candidate status: http://127.0.0.1:{port}/ledger-status", flush=True)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    except OSError as exc:
        raise ValueError("cannot bind local server (permission or occupied port): " + str(exc) + "; do not stop unrelated services or bypass host approval") from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for key in ("ledger", "config", "output"):
        prep.add_argument("--" + key, type=Path, required=True)
    prep.add_argument("--month", required=True)
    prep.add_argument("--synthetic", action="store_true", help="Only for known fictional inputs; never labels real data synthetic")
    view = sub.add_parser("serve")
    view.add_argument("--view", type=Path, required=True)
    view.add_argument("--port", type=int, default=5231)
    a = p.parse_args()
    if a.command == "prepare":
        print(canonical(prepare(a.ledger, json.loads(a.config.read_text()), a.month, a.output, synthetic=a.synthetic)))
    else:
        serve(a.view, a.port)


if __name__ == "__main__":
    from ledger import cli_entry
    raise SystemExit(cli_entry(main))
