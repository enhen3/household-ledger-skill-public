#!/usr/bin/env python3
"""Release only explicitly allowed, reviewed, data-free files to a PRIVATE repo."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "absolute_home_path": re.compile(r"/(?:Users|home)/[^\s/]+/"),
    "github_token": re.compile(r"gh[pousr]_" + r"[A-Za-z0-9]{20,}|github_pat_" + r"[A-Za-z0-9_]{20,}"),
    "private_key": re.compile("-----BEGIN " + r"(?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "possible_full_account": re.compile(r"(?<![A-Za-z0-9])\d{16,19}(?![A-Za-z0-9])"),
}


def run(*args, capture=True, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def scan_text(text, deny=()):
    findings = [name for name, pattern in PATTERNS.items() if pattern.search(text)]
    findings += ["private_denied_term" for term in deny if term and term.casefold() in text.casefold()]
    return sorted(set(findings))


def scan_content(name, raw, manifest, deny=()):
    """Only explicitly reviewed, hash-pinned JPEG documentation is non-text."""
    reviewed = manifest.get("reviewed_images", {}).get(name)
    if reviewed is not None:
        if (not name.startswith("references/images/") or not name.endswith(".jpg")
                or reviewed.get("format") != "JPEG" or reviewed.get("synthetic") is not True
                or not raw.startswith(b"\xff\xd8\xff") or not raw.endswith(b"\xff\xd9")
                or hashlib.sha256(raw).hexdigest() != reviewed.get("sha256")):
            return ["unverified_documentation_image"]
        return []
    return scan_text(raw.decode("utf-8"), deny)


def git_content(spec, root):
    return subprocess.check_output(["git", "show", spec], cwd=root)


def manifest_files(root=ROOT):
    manifest = json.loads((root / "release-files.json").read_text())
    paths = manifest["files"]
    if len(paths) != len(set(paths)) or paths != sorted(paths):
        raise ValueError("release allowlist must be unique and sorted")
    if not set(manifest.get("reviewed_images", {})).issubset(paths):
        raise ValueError("reviewed image must be allowlisted")
    return paths


def check_files(root=ROOT, deny=()):
    allowed = manifest_files(root)
    manifest = json.loads((root / "release-files.json").read_text())
    issues = []
    for relative in allowed:
        path = root / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("invalid allowlist path")
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and root in p.parents):
            raise ValueError("symlink export refused")
        if not path.is_file() or path.stat().st_size > 250000:
            raise ValueError("missing or oversized allowed file: " + relative)
        issues += [relative + ":" + item for item in scan_content(relative, path.read_bytes(), manifest, deny)]
    if (root / ".git").exists():
        actual = run("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", cwd=root).split("\0")
        extra = sorted(set(filter(None, actual)) - set(allowed))
        if extra:
            issues += ["not_allowlisted:" + p for p in extra]
        # Also inspect the staged content: working-tree scans alone miss a
        # staged secret removed only from the working tree.
        staged = run("git", "ls-files", "-z", cwd=root).split("\0")
        staged_manifest = json.loads(git_content(":release-files.json", root))
        for p in filter(None, staged):
            content = git_content(":" + p, root)
            issues += [p + ":staged:" + item for item in scan_content(p, content, staged_manifest, deny)]
    if issues:
        raise ValueError("release privacy gate failed: " + "; ".join(issues))
    return allowed


def verify(repo):
    obj = json.loads(run("gh", "repo", "view", repo, "--json", "nameWithOwner,visibility,url,defaultBranchRef"))
    if obj["nameWithOwner"].lower() != repo.lower() or obj["visibility"] != "PRIVATE":
        raise ValueError("release requires the exact PRIVATE repository")
    return obj


def check(deny=()):
    paths = check_files(deny=deny)
    if (ROOT / ".git").exists():
        audit_history(deny=deny)
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", capture=False)
    with tempfile.TemporaryDirectory(prefix="ledger-skill-demo-") as directory:
        run(sys.executable, "scripts/demo.py", "--output", directory, capture=False)
    with tempfile.TemporaryDirectory(prefix="ledger-skill-first-run-") as directory:
        run(sys.executable, "scripts/first_run.py", "--output", directory, capture=False)
    with tempfile.TemporaryDirectory(prefix="ledger-skill-package-") as directory:
        build_review_package(Path(directory) / "private-review.zip", deny=deny)
    return paths


def audit_history(root=ROOT, deny=()):
    commits = run("git", "rev-list", "--all", cwd=root).splitlines()
    for commit in commits:
        names = run("git", "ls-tree", "-r", "--name-only", commit, cwd=root).splitlines()
        manifest = json.loads(run("git", "show", f"{commit}:release-files.json", cwd=root))
        historical = manifest["files"]
        for name in names:
            if name not in historical:
                raise ValueError("history non-allowlisted file: " + commit[:12] + ":" + name)
            findings = scan_content(name, git_content(f"{commit}:{name}", root), manifest, deny)
            if findings:
                raise ValueError("history privacy finding: " + commit[:12] + ":" + name + ":" + ",".join(findings))
    return len(commits)


def build_review_package(output, root=ROOT, deny=()):
    from ledger import safe_output, immutable_write, canonical
    import io
    output = safe_output(output)
    paths = check_files(root, deny)
    manifest = json.loads((root / "release-files.json").read_text())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            info = zipfile.ZipInfo(relative, date_time=(2001, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, (root / relative).read_bytes())
    raw = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != paths:
            raise ValueError("review package differs from allowlist")
        for name in archive.namelist():
            if scan_content(name, archive.read(name), manifest, deny):
                raise ValueError("review package privacy finding: " + name)
    immutable_write(output, raw)
    metadata_path = root / "distribution.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    receipt = {"schema_version": 1, "private_review_only": metadata.get("repository_visibility") != "public", "sha256": hashlib.sha256(raw).hexdigest(),
               "files": [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in paths]}
    immutable_write(output.with_suffix(".manifest.json"), canonical(receipt))
    return receipt


def publish(repo, message, deny=()):
    verify(repo)
    remote = run("git", "remote", "get-url", "origin").strip()
    if remote not in {f"https://github.com/{repo}.git", f"https://github.com/{repo}", f"git@github.com:{repo}.git"}:
        raise ValueError("origin does not match the approved repository")
    if run("git", "branch", "--show-current").strip() != "main":
        raise ValueError("release from main only; merge deliberately first")
    paths = check(deny)
    run("git", "add", "--", *paths)
    check_files(deny=deny)
    if run("git", "diff", "--cached", "--name-only").strip():
        run("git", "commit", "-m", message, capture=False)
    # Audit each reachable local commit, not just HEAD, before any new push.
    audit_history(deny=deny)
    verify(repo)
    run("git", "push", "-u", "origin", "main", capture=False)
    head = run("git", "rev-parse", "HEAD").strip()
    remote_head = json.loads(run("gh", "api", f"repos/{repo}/commits/main"))["sha"]
    final = verify(repo)
    if head != remote_head or run("git", "status", "--porcelain").strip():
        raise RuntimeError("remote commit/readback or clean-tree verification failed")
    print(json.dumps({"result": "synced", "visibility": final["visibility"], "commit": head,
                      "repository": repo, "files": len(paths)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "publish", "verify"])
    parser.add_argument("--repo")
    parser.add_argument("--message", default="maint: update household ledger skill")
    parser.add_argument("--deny-file", type=Path, help="optional private JSON list of forbidden terms; stays outside repository")
    args = parser.parse_args()
    deny = json.loads(args.deny_file.read_text()) if args.deny_file else []
    if not isinstance(deny, list) or any(not isinstance(x, str) for x in deny):
        raise ValueError("deny-file must be a list of strings")
    if args.command == "check":
        paths = check(deny)
        print(json.dumps({"result": "checked", "files": len(paths)}))
    elif args.command == "publish":
        if not args.repo:
            parser.error("--repo required")
        publish(args.repo, args.message, deny)
    else:
        if not args.repo:
            parser.error("--repo required")
        obj = verify(args.repo)
        local = run("git", "rev-parse", "HEAD").strip()
        remote = json.loads(run("gh", "api", f"repos/{args.repo}/commits/main"))["sha"]
        if local != remote:
            raise ValueError("local/remote commit mismatch")
        print(json.dumps({"visibility": obj["visibility"], "commit": local, "matched": True}))


if __name__ == "__main__":
    main()
