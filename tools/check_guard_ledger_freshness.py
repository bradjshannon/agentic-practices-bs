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

USAGE
    python tools/check_guard_ledger_freshness.py            # scan, exit 1 on any stale/missing row
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


def _rows() -> list[str]:
    table = _ledger_table_text()
    return [line for line in table.splitlines() if LEDGER_ROW.match(line)]


def _guard_label(row: str) -> str:
    m = re.match(r"^\|\s*(`[^`]+`(?:\s*\([^)]*\))?)", row)
    return m.group(1) if m else row[:60]


def _run_test(path: Path) -> tuple[bool, str]:
    """Run one test file exactly as the ledger's own convention expects: relative to itself, so
    it exercises the BANKED copy, not whatever happens to be installed on this machine."""
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=120, cwd=str(path.parent),
        )
    except Exception as exc:
        return False, f"could not run: {exc}"
    ok = proc.returncode == 0
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[-1] if tail else "(no output)"
    return ok, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                     help="print every row's verdict and exit 0 regardless of findings")
    args = ap.parse_args()

    rows = _rows()
    if not rows:
        print(f"error: found the '## Ledger' section but zero rows matched in {LEDGER} — "
              f"the table format probably changed and this script's LEDGER_ROW pattern needs "
              f"updating. Treat this as a failure, not as 'nothing is stale'.", file=sys.stderr)
        return 2

    # Cache: one test run per unique test file, even if several rows cite the same one.
    test_result_cache: dict[str, tuple[bool, str]] = {}
    stale_rows: list[str] = []
    unverifiable_rows: list[str] = []
    verdicts: list[str] = []

    for row in rows:
        label = _guard_label(row)
        cited = TEST_FILE.findall(row)
        if not cited:
            unverifiable_rows.append(label)
            verdicts.append(f"NO-TEST     {label}  (evidenced by live/manual observation only "
                             f"-- cannot be auto-reverified)")
            continue

        row_ok = True
        row_detail = []
        for name in cited:
            if name not in test_result_cache:
                path = HOOKS_DIR / name
                if not path.exists():
                    test_result_cache[name] = (False, f"MISSING: {path} does not exist")
                else:
                    test_result_cache[name] = _run_test(path)
            ok, detail = test_result_cache[name]
            row_ok = row_ok and ok
            row_detail.append(f"{name}: {detail}")

        if row_ok:
            verdicts.append(f"FRESH       {label}")
        else:
            stale_rows.append(label)
            verdicts.append(f"STALE       {label}\n              " + "\n              ".join(row_detail))

    if args.list:
        print("\n".join(verdicts))
        print()
        print(f"{len(rows)} row(s): {len(rows) - len(stale_rows) - len(unverifiable_rows)} fresh, "
              f"{len(stale_rows)} stale, {len(unverifiable_rows)} no-test")
        return 0

    if stale_rows:
        print(f"GUARD-LEDGER.md: {len(stale_rows)} row(s) cite a test that no longer passes "
              f"(or no longer exists) -- the ledger's claim is stale:\n")
        for v in verdicts:
            if v.startswith("STALE"):
                print(v)
        print(f"\nFix: re-verify the guard, update its row (evidence + Date), or remove the row "
              f"if the guard was retired. Run with --list to see every row's verdict, including "
              f"the {len(unverifiable_rows)} row(s) with no cited test (not a failure -- those "
              f"rely on live/manual evidence and this script cannot re-check them).")
        return 1

    print(f"GUARD-LEDGER.md: all {len(rows) - len(unverifiable_rows)} test-backed row(s) still "
          f"pass. {len(unverifiable_rows)} row(s) have no cited test and were not checked "
          f"(run --list to see which).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
