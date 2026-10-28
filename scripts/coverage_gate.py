"""Fail-closed source coverage and month-close gates. Contains no personal data."""
from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date
from pathlib import Path


def needs_review(account: str) -> bool:
    return any(word in account for word in ("NeedsReview", "Unclassified", "Pending")) or "待确认" in account or "未分类" in account or account in {"Income:Other:其他收入", "Income:Refund:退款"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coverage_status(ledger: Path, month: str) -> dict:
    """Read the sibling coverage.json; never infer completeness from balances."""
    path = ledger.parent / "coverage.json"
    result = {"registry": str(path), "registry_sha256": None, "valid": False,
              "all_imported": False, "all_reconciled": False, "through": None,
              "streams": [], "unresolved_source_issues": 0, "reasons": [], "summary": "来源覆盖清单未建立，不能确认完整性"}
    if not path.is_file():
        result["reasons"].append("coverage_registry_missing")
        return result
    result["registry_sha256"] = digest(path)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("coverage_invalid_document")
        year, number = map(int, month.split("-"))
        start = date(year, number, 1)
        end = date(year, number, calendar.monthrange(year, number)[1])
        if obj.get("schema_version") not in {1, 2} or obj.get("month") != month:
            raise ValueError("coverage_schema_or_month_mismatch")
        if obj.get("ledger_sha256") != digest(ledger):
            raise ValueError("coverage_ledger_hash_stale")
        import_state = path.parent / "source-import-state.json"
        if not obj.get("import_state_sha256") or not import_state.is_file() or digest(import_state) != obj["import_state_sha256"]:
            raise ValueError("coverage_import_state_hash_stale")
        evidence = None
        if obj["schema_version"] == 2:
            from reconcile import verify_evidence
            evidence = verify_evidence(json.loads(import_state.read_text(encoding="utf-8")), ledger, month, path.parent)
        unresolved = obj.get("unresolved_source_issues", 0)
        if type(unresolved) is not int or unresolved < 0:
            raise ValueError("coverage_invalid_issue_count")
        result["unresolved_source_issues"] = unresolved
        expected = obj.get("required_streams", [])
        streams = obj.get("streams", [])
        def identity(row):
            values = tuple(row.get(k) for k in ("owner", "source_type", "account"))
            if any(not isinstance(v, str) or not v for v in values):
                raise ValueError("coverage_invalid_identity")
            return values
        keys = [identity(r) for r in expected]
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("coverage_invalid_required_streams")
        owners = obj.get("expected_owners", [])
        if not owners or set(owners) != {k[0] for k in keys}:
            raise ValueError("coverage_expected_owner_mismatch")
        indexed = {}
        for row in streams:
            key = identity(row)
            if key in indexed or key not in keys:
                raise ValueError("coverage_duplicate_or_unexpected_stream")
            indexed[key] = row
        full = True
        reconciled = True
        if evidence is None:
            reconciled = False
            result["reasons"].append("structured_reconciliation_evidence_required")
        all_through = []
        summaries = []
        for key in keys:
            row = indexed.get(key)
            label = f"{key[0]}/{key[1]}"
            if row is None:
                full = reconciled = False
                result["reasons"].append(f"source_missing:{label}")
                result["streams"].append(dict(zip(("owner", "source_type", "account"), key), state="missing"))
                summaries.append(f"{label} 未接收")
                continue
            if evidence is not None:
                proof = evidence.get(row.get("reconciliation_id"))
                if not proof or identity(proof) != key:
                    raise ValueError("source_reconciliation_evidence_missing")
                received_proof = row.get("received", {})
                proof_path = Path(proof["original_path"])
                declared_path = Path(received_proof.get("path", ""))
                if not declared_path.is_absolute(): declared_path = path.parent / declared_path
                if (declared_path.resolve() != proof_path.resolve() or received_proof.get("sha256") != proof["original_sha256"]
                    or any(row.get(k) != proof[p] for k, p in (("imported_from", "from"), ("imported_through", "through")))
                    or any(received_proof.get(k) != proof[k] for k in ("from", "through"))):
                    raise ValueError("coverage_range_or_source_disagrees_with_evidence")
            received = row.get("received")
            received_from = received_through = date.min
            if not received:
                full = reconciled = False
                result["reasons"].append(f"source_not_received:{label}")
            else:
                source = Path(received["path"])
                if not source.is_absolute():
                    source = path.parent / source
                if not source.is_file() or digest(source) != received.get("sha256"):
                    raise ValueError(f"source_hash_mismatch:{label}")
                received_from = date.fromisoformat(received["from"])
                received_through = date.fromisoformat(received["through"])
                if received_from > received_through:
                    raise ValueError(f"source_invalid_received_range:{label}")
            imported_from = row.get("imported_from")
            imported_through = row.get("imported_through")
            if bool(imported_from) != bool(imported_through):
                raise ValueError(f"source_incomplete_import_range:{label}")
            if imported_from:
                lo, hi = date.fromisoformat(imported_from), date.fromisoformat(imported_through)
                if not received or lo > hi or lo < received_from or hi > received_through:
                    raise ValueError(f"source_import_outside_received:{label}")
                all_through.append(hi)
                if lo > start or hi < end:
                    full = False
                    result["reasons"].append(f"source_partial:{label}")
                state = "imported"
                summaries.append(f"{label} 已入账至{hi.isoformat()}")
            else:
                full = reconciled = False
                state = "received_not_imported" if received else "missing"
                result["reasons"].append(f"source_not_imported:{label}")
                summaries.append(f"{label} 已收到未入账" if received else f"{label} 未接收")
            if row.get("reconciliation") != "verified":
                reconciled = False
                result["reasons"].append(f"source_not_reconciled:{label}")
            result["streams"].append({k: row.get(k) for k in ("owner", "source_type", "account", "imported_from", "imported_through", "reconciliation")} | {"state": state, "received_through": received.get("through") if received else None})
        result.update(valid=True, all_imported=full, all_reconciled=reconciled,
                      through=min(all_through).isoformat() if len(all_through) == len(keys) else None,
                      summary="；".join(summaries))
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        result["reasons"].append(str(exc))
        result["summary"] = "来源覆盖证据失效，需重新核对：" + str(exc)
    return result


def close_gate(coverage: dict, *, pending: int, unassigned: int, ambiguous: int,
               uncategorized: bool, source_issues: int = 0) -> tuple[str, list[str]]:
    source_issues = source_issues or coverage.get("unresolved_source_issues", 0)
    reasons = list(coverage["reasons"])
    if pending:
        reasons.append("pending_transactions")
    if unassigned or ambiguous:
        reasons.append("owner_attribution_incomplete")
    if uncategorized:
        reasons.append("uncategorized_transactions")
    if source_issues:
        reasons.append("unresolved_source_issues")
    if not coverage["valid"]:
        return "unknown", reasons
    if not coverage["all_imported"]:
        return "partial", reasons
    if not coverage["all_reconciled"] or pending or unassigned or ambiguous or uncategorized or source_issues:
        return "provisional", reasons
    return "complete", reasons
