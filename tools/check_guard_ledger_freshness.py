#!/usr/bin/env python3
"""Make GUARD-LEDGER.md's staleness Instrumented instead of Voluntary.

WHY THIS EXISTS
----------------
`mechanisms/GUARD-LEDGER.md` records, per guard, evidence that it fires when it should and
stays silent when it should. That evidence is a claim about a point in time. Nothing stops the
guard changing later while the row keeps asserting the old evidence — the row is prose, and
prose does not know its own subject moved.

`mechanisms/WHERE-MECHANISMS-LIVE.md` names this precisely: a registry that nothing enforces
reading or updating is **Voluntary-class**, the same bucket as a `lessons/` entry, no matter how
authoritative it reads. This script is the fix that doc's own last paragraph points at: instead
of trusting a human to notice a guard drifted out from under its ledger row, RUN the test file
each row cites and confirm it still passes. A row's claim is exactly as fresh as its test suite
is green.

WHY THIS CHECKS THE TEST SUITE, NOT THE FILE'S MTIME/HASH
------------------------------------------------------------
The obvious-looking alternative — "flag a row if its guard file changed since the row's date" —
was tried first and rejected. Several rows in this ledger describe DIFFERENT patterns inside the
SAME file (`lying_command_guard.py` has five separate rows, added on five different dates, for
five different rules in one file). Under a whole-file mtime check, adding a SIXTH pattern next
week would mark all five earlier rows stale, even though nothing about the behaviour those rows
describe changed. That is a guard that cries wolf on unrelated edits — this project's own
doctrine is that a check like that gets disabled and takes its true positives with it.

Running the cited test file sidesteps this entirely: if `lying_command_guard_test.py`'s cases
for the writer-tool-substitution pattern still pass, that row's claim holds, regardless of what
else changed in the same file. The signal is "does the specific behaviour still test green", not
"did the file move" — which is also just a better proxy for what a ledger row actually asserts.

WHAT THIS DOES NOT CATCH (named, per this repo's own contributing bar: every control here has a
hole, and the ones that hurt are the ones nobody wrote down)
-----------------------------------------------------------------------------------------------
- A row with NO cited test file (e.g. `pacer_armed.py`, evidenced by "live" observation only)
  cannot be re-verified this way. Reported separately, never silently passed.
- A test file that still passes but no longer tests the SAME cases the row describes (someone
  quietly narrowed the test without updating the row's prose) is invisible to this — it proves a
  suite runs green, not that the green suite still means what the row says it means.
- A row citing a test file that has since been deleted or renamed is caught (reported MISSING),
  but a row that was never updated to cite a test file's NEW name after a rename would read as
  MISSING rather than "renamed, still fine" — the fix there is renaming the citation, not this
  script guessing at it.

THREE HOLES FOUND 2026-08-04 AND CLOSED HERE (each had already cost something)
------------------------------------------------------------------------------
1. **"Could not run HERE" was indistinguishable from "the claim went stale."** A test that needs
   something this machine does not have — a real repo on disk, an installed harness — exited
   non-zero and was reported STALE, which is a statement about the LEDGER. Measured by running
   this script with HOME pointed at an empty directory (a stand-in for the CI runner):
   `18 row(s): 11 fresh, 4 stale, 3 no-test`, where all four "stale" were environmental. The CI
   workflow shipped alongside this script was therefore RED on every push from the day it landed,
   for reasons that had nothing to do with any ledger row going stale — and a check that is always
   red is a check nobody reads, which is this repo's own stated reason for caring about false
   positives. Exit code **2** now means "not runnable in this environment" (the convention
   `repo_doc_guard_test.py` already used and nothing consumed), reported as UNRUNNABLE, never
   silently folded into either PASS or STALE, and always named in the summary line so it cannot
   become a reassuring null. `--strict` makes them fail, for a caller that wants that.

2. **A cited test could load the guard from the MACHINE instead of from this repo, and this script
   would call it FRESH.** `lying_command_guard_test.py` did exactly that: it loaded
   `~/.claude/hooks/lying_command_guard.py` while GUARD-LEDGER.md's row for it had claimed since
   2026-07-29 that it had been retargeted to the banked copy. Three rows cited that file, so three
   rows' evidence described a file this repo does not own. That is the hook-drift hole
   `WHERE-MECHANISMS-LIVE.md` names, arriving inside the ledger that was supposed to catch it.
   Now checked structurally: a cited test that loads from `~/.claude` is MACHINE-COUPLED and fails,
   because a green run of such a test says nothing about the banked copy.

3. **Rows outside `mechanisms/hooks/` were silently out of scope.** The `LEDGER_ROW` pattern only
   matches rows whose Guard cell starts `mechanisms/hooks/`, so rows for guards in sibling repos
   and in `mechanisms/scripts/` were never counted, never checked, and never mentioned. The final
   line read "all N test-backed rows still pass" with an N the reader had no way to know excluded
   others. The count is now reported.

WHAT IS STILL NOT CHECKED, AND DELIBERATELY SO
-----------------------------------------------
Whether a mechanism is INSTALLED AND WIRED on the machine you are sitting at. That is a different
question with a different answer, and folding it in here would make both worse — a row's claim is
about this repo, and it does not become acceptable-to-fail because a given workstation opted out of
the guard. See `mechanisms/WHERE-MECHANISMS-LIVE.md`.

USAGE
    python tools/check_guard_ledger_freshness.py            # scan, exit 1 on any stale/missing row
    python tools/check_guard_ledger_freshness.py --strict   # ...and on any UNRUNNABLE row too
    python tools/check_guard_ledger_freshness.py --list     # show every row's verdict, exit 0
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "mechanisms" / "GUARD-LEDGER.md"
HOOKS_DIR = REPO / "mechanisms" / "hooks"

# Only the "## Ledger" table's rows are in scope. The "Not banked" section further down the file
# lists tests/files DELIBERATELY absent from mechanisms/hooks/ (machine-specific, cannot be
# sanitized) -- those are not drift, and must not be scanned as if they were ledger rows.
LEDGER_ROW = re.compile(r"^\|\s*`mechanisms/hooks/[^`]+`", re.M)
TEST_FILE = re.compile(r"`([A-Za-z0-9_./-]+_test\.py)`")


def _ledger_table_text() -> str:
    text = LEDGER.read_text(encoding="utf-8")
    marker = "\n## Ledger\n"
    idx = text.find(marker)
    if idx == -1:
        print(f"error: could not find '## Ledger' section in {LEDGER}", file=sys.stderr)
        sys.exit(2)
    # Stop at the next top-level '## ' heading (e.g. "## Not banked") so that section's own
    # test-file mentions (deliberately absent, not drift) are never scanned.
    rest = text[idx + len(marker):]
    end = re.search(r"\n## ", rest)
    return rest[: end.start()] if end else rest


def _rows() -> tuple[list[str], int]:
    """Return (in-scope rows, count of table rows this script does NOT check).

    The second half exists because the out-of-scope count used to be invisible: rows for guards in
    sibling repos and in `mechanisms/scripts/` are legitimately not runnable from here, but the
    summary line said "all N test-backed rows still pass" with an N that quietly excluded them.
    A denominator nobody can see is the same defect as a green light nobody can see behind.
    """
    table = _ledger_table_text()
    lines = [ln for ln in table.splitlines() if ln.startswith("|")]
    body = [ln for ln in lines if not re.match(r"^\|[\s:|-]+\|?\s*$", ln)
            and not ln.startswith("| Guard ")]
    scoped = [ln for ln in body if LEDGER_ROW.match(ln)]
    return scoped, len(body) - len(scoped)


def _guard_label(row: str) -> str:
    m = re.match(r"^\|\s*(`[^`]+`(?:\s*\([^)]*\))?)", row)
    return m.group(1) if m else row[:60]


# A cited test that LOADS ITS SUBJECT from the machine proves nothing about the copy in this repo.
#
# This must match the load, not the mention. The first draft matched any `.claude` path anywhere in
# the file and reported 11 of 15 rows COUPLED -- including suites that merely point HOME at a temp
# dir so `~/.claude/hook-events.jsonl` lands somewhere harmless, which is correct behaviour being
# flagged as a defect. That detector would have been switched off inside a day, which is the exact
# failure this ledger's own opening section is about. Verified ground truth on 2026-08-04 before and
# after: exactly ONE banked suite loaded its subject from ~/.claude (`lying_command_guard_test.py`),
# every other one already used `Path(__file__)`.
_LOADERS = ("run_path", "spec_from_file_location", "SourceFileLoader", "load_source")


def _loads_from_machine(src: str) -> bool:
    for fn in _LOADERS:
        for m in re.finditer(re.escape(fn) + r"\s*\(", src):
            depth, i = 1, m.end()
            while i < len(src) and depth:
                depth += (src[i] == "(") - (src[i] == ")")
                i += 1
            if ".claude" in src[m.end():i]:
                return True
    return False

PASS, STALE, UNRUNNABLE, COUPLED, VACUOUS = "PASS", "STALE", "UNRUNNABLE", "COUPLED", "VACUOUS"


def _is_vacuous_under_direct_run(src: str) -> bool:
    """A pytest-shaped file with no `if __name__ == '__main__'` entry point.

    This script's whole method is `python <cited test file>`. A file that defines `def test_...`
    functions and nothing that CALLS them exits 0 having asserted nothing -- and this script would
    report the row FRESH. That is the `archive-elf.ps1` failure at the top of GUARD-LEDGER.md,
    reproduced by the tool built to prevent it.

    Found live 2026-08-04: `revive_before_dispatch_test.py` is 169 lines, 12 `def test_` functions,
    24 asserts, zero prints, no `__main__` guard -- `python revive_before_dispatch_test.py` prints
    nothing and exits 0. No ledger row cites it today, so nothing was actually being mis-reported;
    the hole was one citation away from mattering, which is exactly when it is cheap to close.

    A file WITH a `__main__` guard is fine however it is shaped -- the guard is what makes direct
    execution mean something, whether it hand-rolls its cases or shells out to pytest.
    """
    return bool(re.search(r"^def test_", src, re.M)) and "__main__" not in src


def _run_test(path: Path) -> tuple[str, str]:
    """Run one test file relative to itself, so it exercises the BANKED copy.

    Returns (verdict, one-line detail). Verdicts are deliberately four-valued, not two: the whole
    point of the 2026-08-04 rework is that "this repo's claim went stale", "this machine cannot run
    the test", and "the test is not testing this repo's copy" are three different findings with
    three different fixes, and collapsing them made the CI job permanently red for the one reason
    that needed no action from a ledger author.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return STALE, f"could not read: {exc}"
    if _loads_from_machine(src):
        return COUPLED, ("loads its subject from ~/.claude, so a green run describes the INSTALLED "
                         "copy and this repo's banked copy could be broken unnoticed. Load it "
                         "relative to the test file instead (Path(__file__).parent).")
    if _is_vacuous_under_direct_run(src):
        return VACUOUS, ("defines `def test_` functions but has no `if __name__ == \"__main__\"` "
                         "entry point, so `python <file>` runs NONE of them and exits 0. A green "
                         "here would mean nothing. Add a __main__ guard (hand-rolled, or "
                         "`raise SystemExit(pytest.main([__file__]))`).")
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=120, cwd=str(path.parent),
        )
    except Exception as exc:
        return STALE, f"could not run: {exc}"
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    if proc.returncode == 0:
        return PASS, summary
    # Exit 2 is this repo's existing "NOT RUN, and NOT RUN is not a pass" convention
    # (repo_doc_guard_test.py). It is an environment fact, not a ledger fact.
    if proc.returncode == 2:
        return UNRUNNABLE, summary
    return STALE, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                     help="print every row's verdict and exit 0 regardless of findings")
    ap.add_argument("--strict", action="store_true",
                     help="also fail on UNRUNNABLE rows (tests this environment cannot run). "
                          "Off by default so a CI runner that legitimately lacks a machine's "
                          "checkouts does not sit permanently red for a non-ledger reason.")
    args = ap.parse_args()

    rows, out_of_scope = _rows()
    if not rows:
        print(f"error: found the '## Ledger' section but zero rows matched in {LEDGER} — "
              f"the table format probably changed and this script's LEDGER_ROW pattern needs "
              f"updating. Treat this as a failure, not as 'nothing is stale'.", file=sys.stderr)
        return 2

    # Cache: one test run per unique test file, even if several rows cite the same one.
    test_result_cache: dict[str, tuple[str, str]] = {}
    stale_rows: list[str] = []
    coupled_rows: list[str] = []
    unrunnable_rows: list[str] = []
    unverifiable_rows: list[str] = []
    verdicts: list[str] = []

    # Worst wins: a row citing one stale test and one unrunnable test is STALE, not UNRUNNABLE.
    _RANK = {PASS: 0, UNRUNNABLE: 1, VACUOUS: 2, COUPLED: 3, STALE: 4}
    _LABEL = {PASS: "FRESH", UNRUNNABLE: "UNRUNNABLE", VACUOUS: "VACUOUS",
              COUPLED: "COUPLED", STALE: "STALE"}
    _BUCKET = {UNRUNNABLE: unrunnable_rows, VACUOUS: coupled_rows,
               COUPLED: coupled_rows, STALE: stale_rows}

    for row in rows:
        label = _guard_label(row)
        cited = TEST_FILE.findall(row)
        if not cited:
            unverifiable_rows.append(label)
            verdicts.append(f"NO-TEST     {label}  (evidenced by live/manual observation only "
                             f"-- cannot be auto-reverified)")
            continue

        worst = PASS
        row_detail = []
        for name in cited:
            if name not in test_result_cache:
                path = HOOKS_DIR / name
                if not path.exists():
                    test_result_cache[name] = (STALE, f"MISSING: {path} does not exist")
                else:
                    test_result_cache[name] = _run_test(path)
            verdict, detail = test_result_cache[name]
            if _RANK[verdict] > _RANK[worst]:
                worst = verdict
            row_detail.append(f"{name}: {detail}")

        if worst == PASS:
            verdicts.append(f"FRESH       {label}")
        else:
            _BUCKET[worst].append(label)
            verdicts.append(f"{_LABEL[worst]:11} {label}\n              "
                            + "\n              ".join(row_detail))

    fresh = len(rows) - len(stale_rows) - len(coupled_rows) - len(unrunnable_rows) \
        - len(unverifiable_rows)
    # One summary line, used by every exit path, so no path can report a partial picture. The
    # out-of-scope count is on it because a denominator the reader cannot see is not a denominator.
    summary = (f"{len(rows)} in-scope row(s): {fresh} fresh, {len(stale_rows)} stale, "
               f"{len(coupled_rows)} machine-coupled-or-vacuous, {len(unrunnable_rows)} unrunnable here, "
               f"{len(unverifiable_rows)} no-test. "
               f"{out_of_scope} further ledger row(s) are OUTSIDE this script's scope "
               f"(the guard is not under mechanisms/hooks/) and were never checked.")

    if args.list:
        print("\n".join(verdicts))
        print()
        print(summary)
        return 0

    hard = stale_rows + coupled_rows + (unrunnable_rows if args.strict else [])
    if hard:
        print(f"GUARD-LEDGER.md: {len(hard)} row(s) failed:\n")
        for v in verdicts:
            if v.startswith(("STALE", "COUPLED", "VACUOUS")) or (args.strict and v.startswith("UNRUNNABLE")):
                print(v)
        print(f"\nFix, by verdict:")
        print(f"  STALE      -- re-verify the guard, update its row (evidence + Date), or remove "
              f"the row if the guard was retired.")
        print(f"  COUPLED    -- the cited test loads its subject from ~/.claude. Retarget it to "
              f"load next to itself; until then the row's evidence is about a file this repo does "
              f"not own.")
        print(f"  VACUOUS    -- the cited test asserts nothing when run directly. Its green is not "
              f"evidence of anything, which is the failure this ledger opens with.")
        if args.strict:
            print(f"  UNRUNNABLE -- this environment cannot run the test (no checkout, no "
                  f"harness). Not a ledger defect. Run without --strict to ignore.")
        print()
        print(summary)
        return 1

    if unrunnable_rows:
        # Never silent: an unmeasured row is stated, not folded into the pass.
        print(f"GUARD-LEDGER.md: {len(unrunnable_rows)} row(s) could NOT be checked in this "
              f"environment (exit 2 = 'not run', which is not a pass): "
              + ", ".join(unrunnable_rows))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
