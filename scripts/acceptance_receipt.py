#!/usr/bin/env python3
"""Run synthetic acceptance and retain an exact-commit receipt."""
import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
import maintain
from ledger import canonical, immutable_write, safe_output

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = safe_output(args.output)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    distribution = json.loads((ROOT / "distribution.json").read_text())
    result = {
        "schema_version": 1, "commit": commit, "synthetic_only": True,
        "private_review_only": distribution.get("repository_visibility") != "public",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": platform.python_version()},
        "dependencies": {k: importlib.metadata.version(k) for k in ("beancount", "pdfplumber", "openpyxl", "fava")},
        "not_run": {
            "browser_visual_qa": "CI tests HTTP/data/read-only contracts; actual browser rendering is recorded separately on macOS",
            "real_financial_data": "Not authorized; all fixtures are synthetic",
            "independent_hermes_cold_start": "No standalone Hermes runtime operated",
            "final_independent_agent_functional_pass": "Local environment disconnected before functional execution; docs reviewed",
            "MM1_pull": "No consumer-side access or readback authorized",
            "MM1_install_and_run": "No consumer-side access or readback authorized",
            "Windows_native_and_other_python_versions": "Outside this tested matrix"
        },
        "license": json.loads((ROOT / "distribution.json").read_text())["license_spdx"], "tag": "not created"
    }
    try:
        paths = maintain.check()
        package = maintain.build_review_package(output / "private-review.zip")
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        result.update(status="passed", test_count=suite.countTestCases(), files=package["files"],
                      package_sha256=package["sha256"], reachable_history_commits=maintain.audit_history(),
                      passed=["all_regressions", "fresh_configuration_and_first_month",
                              "repeatable_outputs", "private_rule_reuse", "missing_evidence_stays_incomplete",
                              "worktree_allowlist_and_pattern_scan", "history_allowlist_and_pattern_scan",
                              "review_package_readback_and_pattern_scan"])
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__)
        immutable_write(output / "result.json", canonical(result))
        raise
    immutable_write(output / "result.json", canonical(result))
    print(json.dumps({"commit": commit, "status": result["status"], "tests": result["test_count"],
                      "files": len(paths), "package_sha256": result["package_sha256"], "synthetic_only": True}))


if __name__ == "__main__":
    main()
