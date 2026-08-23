#!/usr/bin/env python3
"""Tests for `hook_log.record_fail_open()` -- the three-state telemetry fix.

Run: python hook_fail_open_telemetry_test.py    (stdlib only, no deps)

WHY THIS EXISTS
----------------
A guard that raises BEFORE reaching its own deny() left no trace at all, and its documented
fail-open contract converted that crash into a silent ALLOW -- indistinguishable from outside
from either a passing check or an absent one. Found live 2026-08-13: a `revive_before_dispatch`
POSITIVE fixture did not deny because an incomplete agent-registry fixture (missing `at`) made
`block_reason()` raise, and fail-open turned the exception into an allow. The lot that found it
said, verbatim: "I would have reported a false pass if I had only run the positive case and
eyeballed the code." That is why every case below has a negative control.

WHY FAKE GUARD SCRIPTS, NOT THE REAL ONES
------------------------------------------
Driven against a TEMP DIRECTORY of synthetic guard scripts, the same pattern
`stop_gate_test.py` uses (see `mechanisms/GUARD-LEDGER.md`'s row for `stop_gate.py`) -- so the
result does not depend on which real guards happen to be installed on this machine, or on their
unrelated business logic. Each fake guard is a real, separate Python PROCESS (subprocess, not
runpy-in-process) that imports the real `hook_log` module from this directory, so what is under
test is the actual shipped `record_fail_open()` / `record()` machinery, not a stand-in.

FOUR REQUIRED CASES
--------------------
  1. a guard that raises  -> the call is ALLOWED (contract preserved) AND a
     COULD-NOT-ADJUDICATE row appears, naming the guard, the exception type, and the call.
  2. a guard that denies  -> DENIED row, unchanged from today (still `decision: deny`).
  3. a guard that passes cleanly -> NO COULD-NOT-ADJUDICATE row. Negative control: proves the
     new record does not fire on every call, only on an actual fail-open.
  4. the telemetry sink itself unwritable -> the guard STILL fails open (exits 0, does not
     brick), even though it could not bank the row.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

_results: list[tuple[bool, str]] = []


def check(condition: bool, label: str) -> None:
    _results.append((bool(condition), label))
    print(f"{'ok  ' if condition else 'FAIL'} {label}")


# --------------------------------------------------------------------------- fake guard scripts
#
# Each mirrors the real shape used across mechanisms/hooks/*.py: parse stdin JSON, hook_log.bind()
# it immediately (so a later crash can still be attributed), run its "adjudication" inside a try,
# and on exception call hook_log.record_fail_open() before allowing -- exactly the fix applied to
# estimate_tracker.py and repo_doc_guard.py in this change.

_PREAMBLE = """\
import sys, os, json
sys.path.insert(0, "__HERE__")
import hook_log

payload = json.load(sys.stdin)
hook_log.bind(payload)
"""

FAKE_RAISES = _PREAMBLE + """
def adjudicate(p):
    raise RuntimeError("simulated crash inside adjudication logic")

try:
    adjudicate(payload)
except Exception as exc:
    hook_log.record_fail_open("fake_guard_raises", exc, payload=payload)
    sys.exit(0)  # FAIL-OPEN: allow, because the guard broke, not because it approved
"""

FAKE_DENIES = _PREAMBLE + """
def adjudicate(p):
    return "deny"

try:
    decision = adjudicate(payload)
except Exception as exc:
    hook_log.record_fail_open("fake_guard_denies", exc, payload=payload)
    sys.exit(0)

if decision == "deny":
    hook_log.record("fake_guard_denies", trigger="denied by fake guard", payload=payload,
                    extra={"decision": "deny"})
    print(json.dumps({"hookSpecificOutput": {"permissionDecision": "deny"}}))
sys.exit(0)
"""

FAKE_PASSES = _PREAMBLE + """
def adjudicate(p):
    return "allow"

try:
    decision = adjudicate(payload)
except Exception as exc:
    hook_log.record_fail_open("fake_guard_passes", exc, payload=payload)
    sys.exit(0)

# Clean allow: no record of any kind. This is the negative control -- record_fail_open must
# not have been called, and hook_rollup must not see a fire from this hook at all.
sys.exit(0)
"""


def write_guard(tmp: str, name: str, body: str) -> str:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body.replace("__HERE__", HERE.replace("\\", "\\\\")))
    return path


def run_guard(path: str, payload: dict, log_path: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOOK_LOG_PATH"] = log_path
    return subprocess.run(
        [sys.executable, path],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=HERE,
        timeout=30,
    )


def read_rows(log_path: str) -> list[dict]:
    if not os.path.exists(log_path):
        return []
    rows = []
    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


PAYLOAD = {
    "session_id": "hooktest-fail-open-session",
    "transcript_path": "/tmp/does-not-exist/hooktest-fail-open-session.jsonl",
    "tool_name": "Bash",
    "tool_input": {"command": "echo hi"},
}


def case_guard_raises(tmp: str) -> None:
    log_path = os.path.join(tmp, "case1.jsonl")
    path = write_guard(tmp, "fake_guard_raises.py", FAKE_RAISES)
    proc = run_guard(path, PAYLOAD, log_path)

    check(proc.returncode == 0,
          "guard-raises: process still exits 0 (fail-open contract preserved)")

    rows = read_rows(log_path)
    cna = [r for r in rows if r.get("decision") == "could_not_adjudicate"]
    check(len(cna) == 1, f"guard-raises: exactly one COULD-NOT-ADJUDICATE row appears (got {len(cna)})")
    if cna:
        row = cna[0]
        check(row.get("hook") == "fake_guard_raises",
              f"guard-raises: row names the guard: got={row.get('hook')!r}")
        check(row.get("exception_type") == "RuntimeError",
              f"guard-raises: row names the exception type: got={row.get('exception_type')!r}")
        check("Bash" in (row.get("tool_call") or ""),
              f"guard-raises: row names the tool call it was adjudicating: got={row.get('tool_call')!r}")
        check(row.get("session") == PAYLOAD["session_id"],
              f"guard-raises: row is attributed to the right session: got={row.get('session')!r}")
        check(row.get("decision") != "deny",
              "guard-raises: row's decision is NOT 'deny' -- a crash must never be recorded as a block")


def case_guard_denies(tmp: str) -> None:
    log_path = os.path.join(tmp, "case2.jsonl")
    path = write_guard(tmp, "fake_guard_denies.py", FAKE_DENIES)
    proc = run_guard(path, PAYLOAD, log_path)

    check(proc.returncode == 0, "guard-denies: process exits 0 (hooks signal deny via stdout, not exit code)")
    check('"permissionDecision": "deny"' in proc.stdout,
          "guard-denies: stdout carries the deny decision")

    rows = read_rows(log_path)
    denied = [r for r in rows if r.get("decision") == "deny"]
    cna = [r for r in rows if r.get("decision") == "could_not_adjudicate"]
    check(len(denied) == 1, f"guard-denies: exactly one DENIED row appears (got {len(denied)}) -- unchanged from today")
    check(len(cna) == 0, f"guard-denies: no COULD-NOT-ADJUDICATE row (got {len(cna)}) -- a clean deny is not a crash")


def case_guard_passes(tmp: str) -> None:
    log_path = os.path.join(tmp, "case3.jsonl")
    path = write_guard(tmp, "fake_guard_passes.py", FAKE_PASSES)
    proc = run_guard(path, PAYLOAD, log_path)

    check(proc.returncode == 0, "guard-passes: process exits 0 (clean allow)")

    rows = read_rows(log_path)
    check(len(rows) == 0,
          f"NEGATIVE CONTROL: guard-passes writes NO row at all (got {len(rows)}) -- "
          "the new machinery does not fire on every call, only on an actual fail-open")


def case_sink_unwritable(tmp: str) -> None:
    # Point HOOK_LOG_PATH at a DIRECTORY, not a file -- open(path, "a") is guaranteed to fail
    # (IsADirectoryError / PermissionError) regardless of platform or ACLs, so this does not
    # depend on OS permission semantics the way a chmod-based test would on Windows.
    unwritable_dir = os.path.join(tmp, "sink_is_a_directory")
    os.makedirs(unwritable_dir, exist_ok=True)
    path = write_guard(tmp, "fake_guard_raises_unwritable.py", FAKE_RAISES)

    env = dict(os.environ)
    env["HOOK_LOG_PATH"] = unwritable_dir
    proc = subprocess.run(
        [sys.executable, path],
        input=json.dumps(PAYLOAD),
        capture_output=True,
        text=True,
        env=env,
        cwd=HERE,
        timeout=30,
    )

    check(proc.returncode == 0,
          "unwritable-sink: guard STILL exits 0 (fails open even though it could not bank the row)")
    check(proc.stderr.strip() == "",
          f"unwritable-sink: no traceback escapes to stderr (got {proc.stderr[:200]!r})")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hook_fail_open_test_") as tmp:
        case_guard_raises(tmp)
        case_guard_denies(tmp)
        case_guard_passes(tmp)
        case_sink_unwritable(tmp)

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} passed")
    if passed != total:
        print("FAILURES:")
        for ok, label in _results:
            if not ok:
                print(f"  - {label}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
