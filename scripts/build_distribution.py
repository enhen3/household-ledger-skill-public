#!/usr/bin/env python3
"""Build source distribution variants without changing the ledger implementation."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import maintain

ROOT = Path(__file__).resolve().parents[1]
RED_SUFFIXES = frozenset(".md .txt .html .htm .css .js .py .java .cpp .c .h .php .sh .bat .ps1 .json .xml .sql .ini .cfg .log .db .sqlite .sqlite3 .mdb .accdb .sys".split())
RED_EXCLUDED = frozenset({".github/workflows/verify.yml", ".gitignore"})
MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 30 * 1024 * 1024


def verify_core(root):
    metadata = json.loads((root / "distribution.json").read_text())
    for name, expected in metadata["core_files_sha256"].items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("core differs from declared source: " + name)
    return metadata


def validate_redskill(root, paths):
    if "SKILL.md" not in paths:
        raise ValueError("RedSkill requires root SKILL.md")
    unsupported = [p for p in paths if Path(p).suffix.lower() not in RED_SUFFIXES]
    if unsupported:
        raise ValueError("unsupported RedSkill suffix: " + ", ".join(unsupported))
    sizes = [(p, (root / p).stat().st_size) for p in paths]
    oversized = [p for p, size in sizes if size > MAX_FILE]
    if oversized or sum(size for _, size in sizes) > MAX_TOTAL:
        raise ValueError("RedSkill size limit exceeded")
    return {"files": len(paths), "total_bytes": sum(s for _, s in sizes),
            "max_file_bytes": max((s for _, s in sizes), default=0),
            "unsupported": [], "filter_would_drop": []}


def build(root, variant, output):
    root = Path(root).resolve()
    paths = maintain.check_files(root)
    metadata = verify_core(root)
    if variant not in {"github-full", "redskill"}:
        raise ValueError("unknown distribution variant")
    if variant == "github-full" and metadata["build_kind"] != "github-full":
        raise ValueError("full build requires the full source package; a RedSkill package cannot restore omitted files")
    included = sorted(p for p in paths if variant != "redskill" or p not in RED_EXCLUDED)
    with tempfile.TemporaryDirectory(prefix="ledger-distribution-stage-") as directory:
        stage = Path(directory)
        for name in included:
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, destination)
        metadata = dict(metadata, build_kind=variant,
                        excluded_source_files=sorted(RED_EXCLUDED) if variant == "redskill" else [])
        (stage / "distribution.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        (stage / "release-files.json").write_text(json.dumps({"schema_version": 1, "files": included}, indent=2) + "\n")
        verify_core(stage)
        red = validate_redskill(stage, included) if variant == "redskill" else None
        package = maintain.build_review_package(Path(output), root=stage)
    return {"candidate_version": metadata["candidate_version"], "build_kind": variant,
            "core_source_commit": metadata["core_source_commit"], "license_status": metadata["license_status"],
            "private_review_only": metadata.get("repository_visibility") != "public", "files": len(included), "sha256": package["sha256"],
            "redskill_static_validation": red}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["github-full", "redskill"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.variant, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
