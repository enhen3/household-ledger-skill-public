#!/usr/bin/env python3
"""解析招商银行交易流水 PDF -> 规范化 CSV。

处理要点：
- 交易摘要/对手信息可能跨多行折行，需要合并
- 金额含千分位逗号
- 保留 source_index / page / line 便于溯源
"""
import csv
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

ROW = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<cur>[A-Z]{3})\s+"
    r"(?P<amt>-?[\d,]+\.\d{2})\s+"
    r"(?P<bal>-?[\d,]+\.\d{2})\s*"
    r"(?P<rest>.*)$"
)
SKIP = ("记账日期", "Transaction", "Date Currency", "招商银行交易流水",
        "户 名", "账户类型", "申请时间", "Name Account", "Account Type",
        "Amount", "第", "页", "Page")


def parse(pdf_path):
    if pdfplumber is None:
        raise ImportError("pdfplumber is required")
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            lines = (page.extract_text() or "").splitlines()
            if not lines:
                raise ValueError(f"PDF page {pno} has no extractable text; OCR or format review required")
            for lno, raw in enumerate(lines, 1):
                line = " ".join(raw.split())
                if not line:
                    continue
                m = ROW.match(line)
                if m:
                    rows.append({
                        "source_index": len(rows) + 1,
                        "date": m.group("date"),
                        "currency": m.group("cur"),
                        "amount": f'{Decimal(m.group("amt").replace(",", "")):.2f}',
                        "balance": f'{Decimal(m.group("bal").replace(",", "")):.2f}',
                        "desc_parts": [m.group("rest").strip()],
                        "page": pno,
                        "line": lno,
                    })
                elif re.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", line):
                    raise ValueError(f"Unparsed transaction-like line at page {pno}, line {lno}; review original PDF")
                elif rows and not any(line.startswith(s) for s in SKIP):
                    # 折行续接：归属上一条
                    if not re.match(r"^\d{4}-\d{2}-\d{2}", line):
                        rows[-1]["desc_parts"].append(line)

    out = []
    for r in rows:
        parts = r.pop("desc_parts")
        desc = " ".join(p for p in parts if p).strip()
        desc = re.sub(r"\s+", " ", desc)
        # 清理跨行污染：页码、分隔线、朝朝宝行的尾巴串到下一条
        desc = re.sub(r"待清算电子汇差[-–]?代销理财快赎?投?资?", " ", desc)
        desc = re.sub(r"\d+/\d+", " ", desc)          # 页码 1/3
        desc = re.sub(r"[—─-]{4,}", " ", desc)         # 分隔线
        desc = re.sub(r"\s+", " ", desc).strip()
        amt = Decimal(r["amount"])
        r["description"] = desc
        r["direction"] = "income" if amt > 0 else "expense" if amt < 0 else "zero"
        out.append(r)
    if len(out) > 1:
        ascending = all(out[i]["date"] <= out[i+1]["date"] and
                        Decimal(out[i+1]["balance"]) - Decimal(out[i]["balance"]) == Decimal(out[i+1]["amount"])
                        for i in range(len(out)-1))
        descending = all(out[i]["date"] >= out[i+1]["date"] and
                         Decimal(out[i]["balance"]) - Decimal(out[i+1]["balance"]) == Decimal(out[i]["amount"])
                         for i in range(len(out)-1))
        if not ascending and not descending:
            raise ValueError("PDF balance continuity failed; possible omitted row, mixed account or unsupported ordering")
        if descending and not ascending:
            out.reverse()  # Chronological output; retain original page/line/source_index.
    return out


def main():
    import argparse
    from ledger import safe_output, immutable_write
    import io
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    pdf_path = args.input
    out_csv = safe_output(args.output)
    rows = parse(pdf_path)
    if not rows:
        print("未解析到任何交易行", file=sys.stderr)
        return 1

    from ledger import digest
    for row in rows:
        row["original_sha256"] = digest(pdf_path)
    cols = ["source_index", "date", "currency", "amount", "direction", "original_sha256",
            "balance", "description", "page", "line"]
    f = io.StringIO(newline="")
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({c: r[c] for c in cols})
    immutable_write(out_csv, f.getvalue().encode("utf-8-sig"))

    pos = sum(Decimal(r["amount"]) for r in rows if Decimal(r["amount"]) > 0)
    neg = sum(Decimal(r["amount"]) for r in rows if Decimal(r["amount"]) < 0)
    summary = {
        "count": len(rows),
        "date_min": min(r["date"] for r in rows),
        "date_max": max(r["date"] for r in rows),
        "positive_total": f"{pos:.2f}",
        "negative_total": f"{neg:.2f}",
        "opening_balance": f'{Decimal(rows[0]["balance"]) - Decimal(rows[0]["amount"]):.2f}',
        "closing_balance": rows[-1]["balance"],
        "output": str(out_csv),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    from ledger import cli_entry
    sys.exit(cli_entry(main))
