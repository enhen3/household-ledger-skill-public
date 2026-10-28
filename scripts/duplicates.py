"""Conservative cross-export identity. Equal amounts are never enough."""
import hashlib
import json
from decimal import Decimal


def signature(row):
    return tuple(str(row.get(k, "")) for k in
                 ("owner", "account", "currency", "date", "occurred_at", "description", "kind", "backing")) + (str(Decimal(row["amount"]).normalize()),)


def native_key(row):
    value = row.get("transaction_id")
    if not value:
        return None
    return (row["owner"], row.get("source_type", row["kind"]), row["account"], str(value))


def source_ids(row):
    return set([row["id"], *row.get("duplicate_source_ids", [])])


def deduplicate(rows, decisions=(), history=()):
    """Return current rows once; only trustworthy IDs or explicit pairs collapse.

    Without a native ID, identical content in different exports is ambiguous.
    Decisions are {keep_id, duplicate_id} objects, not a blanket dedupe switch.
    History represents already imported rows and is never emitted as new money.
    """
    rows = [dict(r) for r in rows]
    history = [dict(r) for r in history]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate source row ids")
    decision_map = {}
    for decision in decisions:
        keep, duplicate = decision["keep_id"], decision["duplicate_id"]
        if keep == duplicate or duplicate in decision_map:
            raise ValueError("invalid or repeated overlap decision")
        decision_map[duplicate] = keep
    used, accepted, excluded = set(), [], []
    # A keep target must precede its duplicate, irrespective of file order.
    pending = list(rows)
    ordered = []
    known = {r["id"] for r in history}
    while pending:
        ready = [r for r in pending if r["id"] not in decision_map or decision_map[r["id"]] in known]
        if not ready:
            raise ValueError("overlap decision refers to a missing/cyclic keep_id")
        for row in ready:
            ordered.append(row); known.add(row["id"]); pending.remove(row)
    for row in ordered:
        previous = history + accepted
        same_id = [p for p in previous if row["id"] in source_ids(p)]
        native = [p for p in previous if native_key(row) and native_key(row) == native_key(p)]
        explicit = [p for p in previous if p["id"] == decision_map.get(row["id"])]
        candidates = same_id or native or explicit
        if candidates:
            if len(candidates) != 1 or signature(candidates[0]) != signature(row):
                raise ValueError("conflicting transaction identity; review original exports: " + row["id"])
            keep = candidates[0]
            if explicit:
                used.add(row["id"])
            if keep in accepted:
                keep["duplicate_source_ids"] = sorted((source_ids(keep) | source_ids(row)) - {keep["id"]})
            excluded.append({"id": row["id"], "duplicate_of": keep["id"],
                             "basis": "explicit_confirmation" if explicit else "source_or_native_id",
                             "already_imported": keep in history})
            continue
        collisions = [p for p in previous if signature(p) == signature(row)
                      and p.get("source_sha256") and row.get("source_sha256")
                      and p["source_sha256"] != row["source_sha256"]
                      and not (native_key(p) and native_key(row) and native_key(p) != native_key(row))]
        if collisions:
            raise ValueError("possible overlapping exports; confirm keep_id/duplicate_id, do not guess: "
                             + json.dumps([p["id"] for p in collisions] + [row["id"]]))
        accepted.append(row)
    if used != set(decision_map):
        raise ValueError("unused overlap decision; input may have changed")
    return accepted, excluded
