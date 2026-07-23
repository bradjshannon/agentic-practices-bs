#!/usr/bin/env python3
"""Fail if any tracked file leaks machine-specific or project-specific detail.

WHY THIS EXISTS
---------------
`agentic-practices-bs` is the **public** repo: portable theory, conceptual mechanisms, and
prose with *sanitized* examples of mechanical implementations. Nothing machine-specific,
nothing project-specific. The real, tactical, install-and-use documentation — including
computer-specific and project-specific detail — lives in the private `conductor-bs` repo.

That boundary is a rule, and a rule an author must remember is the intervention that already
failed. So this makes it structural: CI runs this check, and a commit that drags a hostname, a
private IP, a machine name, an operator path, or a project/product name into the public repo is
**rejected**. You cannot merge the leak, so you cannot forget the rule.

Generic mechanism *code* is welcome here as an example — the test is not "is it code" but
"does it name a specific machine, host, operator, or project." If it does, it belongs in
`conductor-bs`, and this check tells you so.

USAGE
-----
    python tools/check_sanitized.py            # scan tracked files, exit 1 on any finding
    python tools/check_sanitized.py --list     # also print the pattern catalogue

An intentional, genuinely-generic use of a flagged token (e.g. the literal name of this check
in its own docs) can be exempted by adding the exact line's substring to `.sanitize-allow` at
the repo root, one literal per line. Keep that file short; every entry is a hole.
"""
from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Each entry: (category, compiled regex). Patterns are deliberately specific to this estate's
# real identifiers so a generic word ("video", "s3 bucket") does not false-positive. Add a new
# machine/host/project identifier here the day it is coined, not the day it leaks.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("machine-name", re.compile(r"\bIAISM-D04\b")),
    ("machine-name", re.compile(r"\bworkpc\b", re.IGNORECASE)),
    ("machine-name", re.compile(r"\bVIDEO\b")),  # the box named VIDEO (uppercase, as a label)
    ("operator", re.compile(r"\baiadmin\b")),
    ("operator-path", re.compile(r"/home/aiadmin\b")),
    ("operator-path", re.compile(r"C:\\Users\\brads", re.IGNORECASE)),
    ("operator-path", re.compile(r"D:/GitHub", re.IGNORECASE)),
    ("host", re.compile(r"\baidemo\d*\b", re.IGNORECASE)),
    ("host", re.compile(r"\baiserver0*\d+\b", re.IGNORECASE)),
    ("host", re.compile(r"iaismart\.com")),
    ("private-ip", re.compile(r"\b47\.23\.90\.\d{1,3}\b")),
    ("private-ip", re.compile(r"\b10\.100\.\d{1,3}\.\d{1,3}\b")),
    ("project", re.compile(r"iai-xiaozhi", re.IGNORECASE)),
    ("project", re.compile(r"\bxiaozhi\b", re.IGNORECASE)),
    ("project", re.compile(r"\bai-research-bs\b", re.IGNORECASE)),
    ("project", re.compile(r"esp32-server", re.IGNORECASE)),
    ("project", re.compile(r"\bairfryer\b", re.IGNORECASE)),
    ("project", re.compile(r"\bheymars\b", re.IGNORECASE)),
    ("project", re.compile(r"IAI-Smart")),
]

# Files that are allowed to name the tokens because naming them IS their subject: this checker
# and its own docs. Match by repo-relative path.
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "tools/check_sanitized.py",
        ".github/workflows/sanitized.yml",
    }
)

# Extensions we never scan (binaries). Everything else tracked by git is scanned as text.
_SKIP_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".woff", ".woff2"}
)


def _tracked_files(repo_root: Path) -> list[str]:
    """Return git-tracked paths, repo-relative, POSIX-separated."""
    out = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _load_allowlist(repo_root: Path) -> list[str]:
    """Literal substrings that exempt a matching line, from `.sanitize-allow` (optional)."""
    allow = repo_root / ".sanitize-allow"
    if not allow.exists():
        return []
    return [
        line.strip()
        for line in allow.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def scan(repo_root: Path) -> list[tuple[str, int, str, str]]:
    """Scan tracked files. Return findings as (path, lineno, category, line)."""
    allowlist = _load_allowlist(repo_root)
    findings: list[tuple[str, int, str, str]] = []
    for rel in _tracked_files(repo_root):
        if rel in _EXEMPT_PATHS or Path(rel).suffix.lower() in _SKIP_SUFFIXES:
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary, vanished, or an unreadable path; not our concern
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in allowlist):
                continue
            for category, pattern in _PATTERNS:
                if pattern.search(line):
                    findings.append((rel, lineno, category, line.strip()))
                    break
    return findings


def main(argv: list[str] | None = None) -> int:
    """Entry point. Exit 0 when clean, 1 when the public boundary is violated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print the pattern catalogue and exit.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        for category, pattern in _PATTERNS:
            logger.info("%-14s %s", category, pattern.pattern)
        return 0

    # Scan the repo this script lives in (<repo>/tools/check_sanitized.py), not the caller's cwd —
    # so it is correct whether run from the repo root in CI or from anywhere else locally.
    repo_root = Path(__file__).resolve().parent.parent

    findings = scan(repo_root)
    if not findings:
        logger.info("check_sanitized: OK — no machine/project-specific tokens in tracked files.")
        return 0

    logger.error("check_sanitized: %d leak(s) — this content belongs in conductor-bs, not here:", len(findings))
    for path, lineno, category, line in findings:
        logger.error("  %s:%d  [%s]  %s", path, lineno, category, line)
    logger.error("")
    logger.error("Fix: move the file to conductor-bs, or sanitize the line. Genuinely-generic")
    logger.error("uses can be exempted via a literal in .sanitize-allow (keep it short).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
