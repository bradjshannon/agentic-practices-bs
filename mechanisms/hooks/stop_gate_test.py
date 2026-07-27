#!/usr/bin/env python3
"""Tests for stop_gate.py — the one-gate-many-checks Stop hook.

Run: python stop_gate_test.py    (stdlib only, no deps)

WHY THESE PROPERTIES
--------------------
The gate's whole value is that it speaks for several checks at once, so the ways it can fail
are: dropping a check's objection (a guard silently stops guarding), or letting one broken
check take the turn hostage (worse than the duplication the gate was built to fix). Both are
invisible in normal use — a dropped objection looks exactly like a passing turn.

The checks are driven from a TEMP DIRECTORY of fake check scripts (HERE/CHECKS are repointed),
never the real ones, so this test cannot be perturbed by whichever guards happen to be
installed on the machine running it — the exact reason the real CHECKS list differs per host.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stop_gate  # noqa: E402

PASSES = "print('')\n"
BLOCKS = "import json\nprint(json.dumps({'decision': 'block', 'reason': %r}))\n"
RAISES = "raise RuntimeError('check exploded')\n"
GARBAGE = "print('not json at all')\n"
APPROVES = "import json\nprint(json.dumps({'decision': 'approve'}))\n"

_results: list[tuple[bool, str]] = []


def check(condition: bool, label: str) -> None:
    _results.append((bool(condition), label))
    print(f"{'ok  ' if condition else 'FAIL'} {label}")


def run_gate(tmp: str, files: dict[str, str], payload: dict | str) -> str:
    """Write *files* as the gate's checks, run main(), return its stdout."""
    for name, body in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    raw = payload if isinstance(payload, str) else json.dumps(payload)
    old_here, old_checks = stop_gate.HERE, stop_gate.CHECKS
    old_stdin, old_stdout = sys.stdin, sys.stdout
    stop_gate.HERE, stop_gate.CHECKS = tmp, list(files)
    sys.stdin, sys.stdout = io.StringIO(raw), io.StringIO()
    try:
        stop_gate.main()
        return sys.stdout.getvalue().strip()
    finally:
        stop_gate.HERE, stop_gate.CHECKS = old_here, old_checks
        sys.stdin, sys.stdout = old_stdin, old_stdout


def reason_of(out: str) -> str | None:
    if not out:
        return None
    obj = json.loads(out)
    return obj.get("reason") if obj.get("decision") == "block" else None


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="stop-gate-test-")
    live = {"transcript_path": "/nonexistent", "stop_hook_active": False}
    try:
        # --- the pass-through case -------------------------------------------------------
        out = run_gate(tmp, {"a.py": PASSES, "b.py": PASSES}, live)
        check(out == "", "no check objects -> gate stays silent")

        # --- a single objection ----------------------------------------------------------
        out = run_gate(tmp, {"a.py": BLOCKS % "REASON ALPHA", "b.py": PASSES}, live)
        check("REASON ALPHA" in (reason_of(out) or ""), "one objection is carried")

        # --- several objections, THE property the gate exists for -------------------------
        out = run_gate(tmp, {"a.py": BLOCKS % "REASON ALPHA",
                             "b.py": BLOCKS % "REASON BETA",
                             "c.py": BLOCKS % "REASON GAMMA"}, live)
        merged = reason_of(out) or ""
        check(all(r in merged for r in ("REASON ALPHA", "REASON BETA", "REASON GAMMA")),
              "every objection survives the merge")
        check(all(n in merged for n in ("a.py", "b.py", "c.py")),
              "each objection is attributed to its check")
        check(out.count('"decision"') == 1, "several objections still produce ONE decision")

        # --- fail-open, per check ---------------------------------------------------------
        out = run_gate(tmp, {"boom.py": RAISES, "b.py": PASSES}, live)
        check(out == "", "a raising check does NOT block the turn (fail-open)")

        out = run_gate(tmp, {"boom.py": RAISES, "b.py": BLOCKS % "STILL REPORTED"}, live)
        merged = reason_of(out) or ""
        check("STILL REPORTED" in merged, "a raising check does not suppress the others")
        check("boom.py" in merged, "the crash is surfaced alongside a real block, not swallowed")

        # --- a check that is listed but not installed --------------------------------------
        out = run_gate(tmp, {"b.py": BLOCKS % "PRESENT CHECK"}, live)
        stop_gate.CHECKS = ["b.py"]  # restored by run_gate's finally on the next call
        merged = reason_of(out) or ""
        check("PRESENT CHECK" in merged, "an installed check still reports when others are absent")

        # --- malformed output from a check --------------------------------------------------
        out = run_gate(tmp, {"junk.py": GARBAGE, "b.py": PASSES}, live)
        check(out == "", "unparseable check output never blocks")

        out = run_gate(tmp, {"ok.py": APPROVES, "b.py": PASSES}, live)
        check(out == "", "a non-block decision is not treated as a block")

        # --- never break the session ---------------------------------------------------------
        out = run_gate(tmp, {"a.py": BLOCKS % "SHOULD NOT APPEAR"}, "{not json")
        check(out == "", "a malformed payload never blocks the session")

        out = run_gate(tmp, {"a.py": BLOCKS % "SHOULD NOT APPEAR"},
                       {"stop_hook_active": True, "transcript_path": "/nonexistent"})
        check(out == "", "stop_hook_active is honoured (no block loop)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} passed, {total - passed} failed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
