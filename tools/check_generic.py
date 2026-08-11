#!/usr/bin/env python3
"""Fail if a tracked file names the operator personally, outside four explicit exemptions.

WHY THIS EXISTS
---------------
This repo's own convention (`conductor-bs/conductors/iotta/brief.md`, §WRITE ARTEFACTS
GENERICALLY) is:

    don't write `Brad`, or `he`/`his` referring to him -- write `the operator` / `the user` /
    `the human`, and `they`/`their`.

The stated reason is upstreaming: anything written generically the first time moves outward
without a rewrite, and the finding is the expensive part. This repo is the **public** one, so it
is where that matters most.

That convention is **Voluntary class** by this corpus's own enforcement table
(`mechanisms/README.md`), and Voluntary-class controls decay -- `hardware_hedge_guard.py`
records prose failing on its own author inside one hour. Measured here 2026-08-11 before this
check existed: **122 occurrences across 42 of 151 tracked files.** A convention that reaches 122
violations is not being followed; it is being remembered, badly. So this makes it structural.

WHAT THIS IS NOT
----------------
This does NOT police pronouns, and deliberately so. `he`/`his`/`him` are ordinary English words
with countless legitimate referents in this corpus ("the author", "a reader", quoted third
parties), so a pronoun rule would fire constantly on correct prose -- and a check with false
positives gets bypassed, taking its true positives with it. That is this repo's own doctrine
(`GUARD-LEDGER.md`). The NAME is unambiguous; the pronouns are a review concern, not a gate.

Nor does it overlap `check_sanitized.py`. That one rejects machine/host/project identifiers --
a different boundary, a different failure. The operator's given name is not in its catalogue,
which is why 122 occurrences sat in a public repo with CI green.

USAGE
-----
    python tools/check_generic.py            # scan tracked files, exit 1 on any finding
    python tools/check_generic.py --list     # print the exemption table and exit

⚠️ THE EXEMPTION TABLE IS A CLOSED LIST, NOT A PATTERN. There is no `.generic-allow` sidecar,
on purpose: `check_sanitized.py`'s `.sanitize-allow` is gitignored and was never created, so it
reported a could-not-check as a pass for months. An exemption that lives in a file the repo does
not carry is an exemption nobody can review. These four live in source, in git, each with its
reason beside it, and adding a fifth is a diff someone has to approve.
"""
from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# The operator's given name in every form measured in this repo: `Brad`, `brad`, `BRAD`,
# `brads` (the username on the other workstation), `bradjshannon` (the GitHub org).
#
# ⚠️ THE SUFFIX IS ENUMERATED, NOT OPEN. The first draft was `\bbrad\w*`, and its own negative
# control caught it firing on `bradawl` -- an ordinary English word. A checker that cries wolf
# gets bypassed and takes its true positives with it (`GUARD-LEDGER.md`), so precision wins over
# reach here. The cost, stated plainly: a NEW form nobody has coined yet (say `bradley`) would
# not be caught. That is the same "add it the day it is coined" limit `check_sanitized.py`
# documents, and it is a real one -- these five are the forms that actually exist.
_NAME = re.compile(r"\bbrad(?:s|jshannon)?\b", re.IGNORECASE)

# ── THE FOUR EXEMPTIONS ──────────────────────────────────────────────────────────────────────
# Each entry is (repo-relative path, literal substring that must appear on the line, reason).
# A line is exempt only when BOTH match, so an exemption cannot quietly widen to cover a new
# occurrence that happens to land in an already-exempt file. `None` as the literal exempts the
# whole file, and is used only where every line of the file is legitimately covered.
_EXEMPTIONS: list[tuple[str, str | None, str]] = [
    # 1. A copyright holder is a legal fact. Genericizing it would misstate who holds the licence.
    ("LICENSE", None, "copyright holder is a legal fact, not a style choice"),
    # 2. Real GitHub URLs and clone commands. These are working instructions; the org name is
    #    part of the address, and genericizing it produces a command that 404s.
    ("README.md", "github.com/bradjshannon/conductor-bs",
     "real repo URL -- genericizing breaks the link"),
    ("README.md", "gh repo clone bradjshannon/agentic-practices-bs",
     "real clone command -- genericizing breaks the instruction"),
    ("mechanisms/README.md", "github.com/bradjshannon/conductor-bs",
     "real repo URL -- genericizing breaks the link"),
    # 3. A DETECTOR PATTERN. `check_sanitized.py` matches the operator's home-directory path to
    #    reject it; editing the pattern disables the mechanism. The name here is the thing being
    #    caught, not a thing being said.
    ("tools/check_sanitized.py", r"C:\\Users\\brads",
     "detector pattern -- editing it disables check_sanitized.py"),
    # 4. TEXT INSIDE A VERBATIM QUOTE. Changing an attribution is honest; changing the words
    #    inside the quotation marks is falsifying a quote, which is worse than the name.
    ("lessons/commit-authorship-is-not-evidence-a-human-acted.md", "That's Brad himself",
     "inside a verbatim quote -- altering quoted words falsifies the quote"),
    ("lessons/how-to-rank-disagreeing-sources.md", "prefer current-brad over past-brad",
     "inside a verbatim quote -- altering quoted words falsifies the quote"),
    # 4b. The same principle one step out: a literal VALUE that was measured. This line reports
    #     what the observed `.gitconfig` user.name actually was. Genericizing it would state a
    #     measurement that was never taken.
    ("lessons/commit-authorship-is-not-evidence-a-human-acted.md", "was authored `Brad Shannon`",
     "literal measured .gitconfig value -- genericizing would misreport the measurement"),
    # ⚠️ SELF-EXEMPTION, AND IT IS A REAL HOLE. The exemption table above must quote the literals
    # it exempts, so this file necessarily contains the name. `check_sanitized.py` exempts itself
    # the same way for the same reason. The cost is that a genuine leak written INTO this file is
    # invisible to it; the mitigation is that this file is short and its only job is this table.
    ("tools/check_generic.py", None, "the checker must quote the literals it exempts"),
    ("tools/check_generic_test.py", None, "the test must contain the name as its positive control"),
]

# Extensions never scanned (binaries). Everything else tracked by git is scanned as text.
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


def _is_exempt(rel: str, line: str) -> str | None:
    """The REASON this line is exempt, or None. Returning the reason rather than a bool is what
    lets `--list` and the test assert that every exemption is justified in place."""
    for path, literal, reason in _EXEMPTIONS:
        if rel != path:
            continue
        if literal is None or literal in line:
            return reason
    return None


def scan(repo_root: Path) -> list[tuple[str, int, str]]:
    """Scan tracked files. Return findings as (path, lineno, stripped line)."""
    findings: list[tuple[str, int, str]] = []
    for rel in _tracked_files(repo_root):
        if Path(rel).suffix.lower() in _SKIP_SUFFIXES:
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary, vanished, or unreadable; not our concern
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not _NAME.search(line):
                continue
            if _is_exempt(rel, line):
                continue
            findings.append((rel, lineno, line.strip()))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Entry point. Exit 0 when clean, 1 when the operator is named outside the exemptions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print the exemption table and exit.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        for path, literal, reason in _EXEMPTIONS:
            logger.info("%-52s %-46s %s", path, literal or "(whole file)", reason)
        return 0

    # Scan the repo this script lives in, not the caller's cwd -- correct whether run from the
    # repo root in CI or from anywhere else locally.
    repo_root = Path(__file__).resolve().parent.parent

    findings = scan(repo_root)
    if not findings:
        logger.info("check_generic: OK -- no personal name in tracked files outside %d exemptions.",
                    len(_EXEMPTIONS))
        return 0

    logger.error("check_generic: %d line(s) name the operator personally:", len(findings))
    for path, lineno, line in findings:
        logger.error("  %s:%d  %s", path, lineno, line[:160])
    logger.error("")
    logger.error("Fix: write `the operator` / `the user` / `the human`, and `they`/`their`.")
    logger.error("Change an ATTRIBUTION freely; never the words inside a verbatim quote.")
    logger.error("If the specific is load-bearing (a legal fact, a real URL, a detector pattern,")
    logger.error("a quoted word), add it to _EXEMPTIONS in tools/check_generic.py WITH ITS REASON.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
