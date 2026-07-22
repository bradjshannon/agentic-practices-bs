#!/usr/bin/env python3
"""Stop hook: run EVERY turn-end check and report ALL failures in ONE block.

WHY THIS EXISTS — the hooks were multiplying Brad's reading, which is the opposite of the job
------------------------------------------------------------------------------------------------
Four separate Stop hooks were wired independently. Each one that blocks costs Brad a full
re-read: the blocked message is **already rendered in his chat**, and then the rewrite lands
next to it. Two hooks firing in sequence = the same content twice. Three = three times.

Brad, 2026-07-22, with screenshots: *"[image]: duplicated output / [image2]: triplicate
output."*

The `output_budget` hook is the sharpest version of the irony: it exists **solely** to reduce how
much he has to read, and in its blocking path it was tripling it. A control whose failure mode
directly negates its own purpose is worse than no control — it is a control arguing for its own
removal.

THE FIX
-------
One gate, run once, that executes every check and concatenates their objections into a single
block. The agent then rewrites **once**, so Brad reads at most two versions instead of four.

This does NOT weaken the checks. Every one of them still blocks, still on the same rule, and
still without the agent's participation. What changes is only that they speak together.

WHY NOT "make them advisory"
----------------------------
That was the obvious alternative and it is wrong for the reason the codebase already documents:
a check that merely warns is the Voluntary class, and every Voluntary control in this project
has decayed — measurably, with counts. Blocking is what makes them real. The defect was never
that they block; it is that they block *serially*.

ADDING A CHECK
--------------
Append to CHECKS. Each entry is a module in this directory exposing `main()` that reads a hook
payload on stdin and prints either nothing (pass) or a JSON `{"decision":"block","reason":...}`.
They are run in-process with stdin/stdout redirected, so an individual check remains runnable
and testable on its own.

FAIL-OPEN, per check. A crash in one check must not block the turn and must not suppress the
others — an exception is reported as a note and the remaining checks still run. A broken gate
that blocks everything would be worse than the duplication it was built to fix.
"""
from __future__ import annotations

import io
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Order matters only for readability of the combined message: cheapest/most-structural first.
CHECKS = [
    "requirement_before_mechanism.py",
    "workflow_output_to_repo.py",
    "evidence_with_claim.py",
    "output_budget.py",
    "pacer_armed.py",
]


def run_check(name: str, payload: str) -> tuple[str | None, str | None]:
    """(block_reason, error). Both None means the check passed."""
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return None, f"{name}: not found"
    old_stdin, old_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(payload), io.StringIO()
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit:
        pass
    except Exception as exc:  # fail-open for THIS check only
        sys.stdin, sys.stdout = old_stdin, old_stdout
        return None, f"{name}: raised {type(exc).__name__}: {exc}"
    finally:
        out = sys.stdout.getvalue() if isinstance(sys.stdout, io.StringIO) else ""
        sys.stdin, sys.stdout = old_stdin, old_stdout
    try:
        data = json.loads(out.strip()) if out.strip() else {}
    except Exception:
        return None, f"{name}: unparseable output {out[:80]!r}"
    if data.get("decision") == "block":
        return data.get("reason") or f"{name} blocked without a reason", None
    return None, None


def main() -> int:
    payload = sys.stdin.read()
    try:
        parsed = json.loads(payload)
    except Exception:
        return 0
    if parsed.get("stop_hook_active"):
        return 0

    reasons, errors = [], []
    for name in CHECKS:
        reason, err = run_check(name, payload)
        if reason:
            reasons.append((name, reason))
        if err:
            errors.append(err)

    if not reasons:
        # Errors alone never block — a broken check must not hold the turn hostage. They are
        # surfaced on the next real block so they cannot rot silently either.
        return 0

    parts = [f"{len(reasons)} turn-end check(s) objected. **All of them, so you rewrite ONCE** — "
             "each separate block costs Brad a full re-read of a message he has already seen, "
             "which is how three hooks turned one message into three.\n"]
    for i, (name, reason) in enumerate(reasons, 1):
        parts.append(f"\n───── {i}. {name} ─────\n{reason}")
    if errors:
        parts.append("\n\n(check errors, non-blocking: " + "; ".join(errors) + ")")
    print(json.dumps({"decision": "block", "reason": "\n".join(parts)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
