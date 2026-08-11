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

THE `myproject` PLACEHOLDER
---------------------------
Where a project name was load-bearing as an IDENTIFIER rather than as prose -- a detector regex,
a repo path in a hook, a test fixture that must match one -- the 2026-08-11 sweep substituted the
placeholder family `myproject` / `myproject-server` / `myproject-firmware` / `myproject-setup` /
`myproject-devices` rather than deleting the identifier. Deleting it would have broken the
mechanism; leaving it would have kept the leak. The banked copy therefore differs from the
installed copy on those lines, deliberately, and `tools/compare_mechanism_copies.py` is built for
exactly this: *"A public copy of a mechanism is legitimately stripped of machine- and
project-specific detail"* -- it reports DIFFERENT and refuses to guess a direction. Prose, by
contrast, got a phrase ("the server repo", "a conductor run"), not a placeholder.
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
    # ── The case gap the label patterns above cannot close ─────────────────────────────────
    # A machine written as a LABEL is uppercase; the same machine written as a HOSTNAME is
    # lowercase — and the hostname is the form that actually leaks, because it arrives inside a
    # URL. Making the label patterns IGNORECASE is NOT the fix: `\bvideo\b` would then fire on
    # the ordinary word in any lesson about audio/video, and a checker that cries wolf gets
    # bypassed, taking its true positives with it (this repo's own doctrine).
    #
    # So match the SHAPE, not the name. Every Tailscale MagicDNS name ends in `.ts.net` and is
    # private by construction; none belongs in a shareable repo. This also covers machines
    # nobody has coined yet — which the "add it the day it is coined" instruction above cannot
    # do, because that instruction requires someone to remember, and remembering is the class
    # of control this repo exists to replace.
    #
    # Found 2026-07-29: a hook was hand-rejected for carrying a real tailnet host in a fallback
    # URL, and this checker had passed it clean. Nothing else would have caught it.
    ("host", re.compile(r"\b[a-z0-9-]+\.ts\.net\b", re.IGNORECASE)),
    ("host", re.compile(r"\btail[0-9a-f]{6,}\b", re.IGNORECASE)),  # the tailnet id itself
    ("operator", re.compile(r"\baiadmin\b")),
    ("operator-path", re.compile(r"/home/aiadmin\b")),
    # Both workstation usernames, and the trailing separator is load-bearing twice over.
    # Found 2026-08-11: this read `C:\\Users\\brads` -- the OTHER workstation -- so this
    # machine's `C:\Users\brad\...` never matched, and two real operator home paths sat in
    # this public repo with CI green. A check that cannot fail reports clean forever. The
    # separator keeps it off `bradley` and any longer name, because a guard that cries wolf
    # gets bypassed and takes its true positives with it. Both directions covered in
    # check_sanitized_test.py, which did not exist until this was found.
    ("operator-path", re.compile(r"C:[\\/]Users[\\/]brads?[\\/]", re.IGNORECASE)),
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
    # ── The catalogue hole that made this whole check ornamental ────────────────────────────
    # Found 2026-08-11: the docstring above says this repo "must never name a specific machine,
    # host, operator, or project/product", and the catalogue duly banned five project names --
    # but the estate's LARGEST project was simply absent. Measured on the tree at the time:
    # **166 occurrences across 32 tracked files**, with CI green the entire time. That is this
    # repo's own recurring failure arriving in its own guard for the second time in one day: a
    # check that cannot fail reports clean forever, and its green run is what stops anyone
    # looking. `check_generic.py` records the identical shape for the operator's given name
    # (122 occurrences, same cause, same green CI).
    #
    # ⚠️ DELIBERATELY NO WORD BOUNDARIES, unlike most entries above. `\biotta\b` was written
    # first and it misses the two forms that actually leak hardest, because `_` is a word
    # character and kills the boundary on both sides:
    #     CONFIG_IOTTA_DIAG_WEB   (a Kconfig symbol quoted in a lesson)
    #     iotta_firmware.bin      (a build artefact named in a guard's block message)
    # The usual argument for boundaries is precision -- a guard that cries wolf gets bypassed
    # and takes its true positives with it. It does not apply here: `iotta` is a coined name
    # with no English substring host, so the bare match has no false-positive surface to
    # protect. Same reasoning as the boundary-free `iai-xiaozhi` and `esp32-server` above.
    # Both directions are covered in check_sanitized_test.py.
    ("project", re.compile(r"iotta", re.IGNORECASE)),
]

# Files that are allowed to name the tokens because naming them IS their subject: this checker
# and its own docs. Match by repo-relative path.
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "tools/check_sanitized.py",
        ".github/workflows/sanitized.yml",
        # The test file must contain the tokens as its positive controls -- a pattern nobody can
        # demonstrate firing is the failure this catalogue was just extended to fix. Same
        # self-exemption `check_generic.py` grants `check_generic_test.py`, same reason, and the
        # same cost: a genuine leak written INTO this file is invisible to the check. The
        # mitigation is that the file is short and its only job is the two-directional table.
        "tools/check_sanitized_test.py",
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
