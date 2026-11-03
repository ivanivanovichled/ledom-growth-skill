#!/usr/bin/env python3
"""Offline structural/provenance validation. No third-party Python packages."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ledom-growth"


def validate():
    errors = []
    entry = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if not entry.startswith("---\nname: ledom-growth\n") or "\ndescription: " not in entry:
        errors.append("entrypoint name/description/frontmatter invalid")
    if len(entry.splitlines()) > 130:
        errors.append("entrypoint too large; move mode-specific content to references")
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            errors.append(f"symlink not allowed: {path.relative_to(ROOT)}")
    md_files = list(ROOT.rglob("*.md"))
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            link = link.split("#", 1)[0]
            if not link or "://" in link or link.startswith("mailto:"):
                continue
            target = (path.parent / link).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"broken/escaping link {path.relative_to(ROOT)}: {link}")
    manifest = json.loads((SKILL / "sources.lock.json").read_text(encoding="utf-8-sig"))
    if len(manifest["sources"]) != 5:
        errors.append("expected five pinned upstream sources")
    for source in manifest["sources"]:
        sha = source["commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            errors.append("invalid commit: " + source["repository"])
        for file in source["files"]:
            expected = f'https://raw.githubusercontent.com/{source["repository"]}/{sha}/{file["path"]}'
            if file["url"] != expected or not re.fullmatch(r"[0-9a-f]{64}", file["sha256"]):
                errors.append("unpinned or invalid source file: " + file["path"])
            if file["path"] == "LICENSE":
                license_path = SKILL / "licenses" / (source["repository"].replace("/", "--") + ".txt")
                if not license_path.exists() or hashlib.sha256(license_path.read_bytes()).hexdigest() != file["sha256"]:
                    errors.append("license missing or changed: " + source["repository"])
    for name in ("outreach-ledger.csv", "prospects.csv"):
        with (SKILL / "templates" / name).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                errors.append("invalid template header: " + name)
            if list(reader):
                errors.append("template contains real/example contacts: " + name)
    # Publication guard, not a comprehensive secret scanner.
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix == ".pyc":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            continue
        patterns = (r"gh[pousr]_[A-Za-z0-9]{25,}", r"github_pat_[A-Za-z0-9_]{30,}",
                    r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----")
        if any(re.search(pattern, text) for pattern in patterns):
            errors.append("possible credential: " + str(path.relative_to(ROOT)))
    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1
    print(f"PASS: {len(md_files)} Markdown files; resource links, five pinned sources, license hashes, empty contact templates checked")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
