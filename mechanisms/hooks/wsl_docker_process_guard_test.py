import runpy
from pathlib import Path

# Load the guard NEXT TO THIS FILE -- i.e. this repo's BANKED copy, not whatever happens to be
# installed under ~/.claude on the machine that runs this. lying_command_guard_test.py's own
# header explains why this matters: a test that loads the installed copy proves nothing about the
# banked one, and the two can silently drift.
m = runpy.run_path(str(Path(__file__).resolve().parent / "wsl_docker_process_guard.py"))
check = m["check"]
OVERRIDE = m["OVERRIDE"]

# (want, command[, ignore]) -- same convention as lying_command_guard_test.py.
cases = [
    # ── The actual failure shape from the 2026-08-04 incident ──────────────────────────────
    # Step 1 of the real hunt: resolve the PID for port 8000 via netstat. This is the
    # earliest point the chain can be stopped, before any PID even exists to feed a later
    # wmic/Get-CimInstance/taskkill call.
    ("BLOCK", "netstat -ano | findstr :8000"),
    ("BLOCK", "netstat -ano | findstr \"8000\""),
    # tasklist hunting an iotta-named process.
    ("BLOCK", 'tasklist | findstr /i iotta'),
    # wmic process where "ProcessId=X" get CommandLine -- named directly in the incident,
    # with iotta context carried in the same command (a comment, in this case).
    ("BLOCK", 'wmic process where "ProcessId=24680" get CommandLine  # find the iotta 8000 process'),
    # wmic hunting by command-line content instead of a resolved PID.
    ("BLOCK", 'wmic process where "CommandLine like \'%iotta%\'" get ProcessId,CommandLine'),
    # PowerShell Get-CimInstance Win32_Process -Filter "ProcessId = X" -- the exact shape
    # named in the incident, with port context in the same line.
    ("BLOCK", 'Get-CimInstance Win32_Process -Filter "ProcessId = 24680" # port 8000 process'),
    # Get-Process filtered by name/port context.
    ("BLOCK", 'Get-Process | Where-Object {$_.ProcessName -like "*iotta*"}'),
    ("BLOCK", "Get-Process -Id 24680  # the process holding port 8001"),
    # netstat -> taskkill chain in one command.
    ("BLOCK", 'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8000\') do taskkill /PID %a /F'),
    # ── Legitimate uses that MUST NOT fire ──────────────────────────────────────────────────
    # Same commands, no iotta/8000/8001 context at all -- ordinary Windows admin work.
    ("ALLOW", "tasklist | findstr chrome"),
    ("ALLOW", "tasklist /fi \"imagename eq node.exe\""),
    ("ALLOW", 'wmic process where "ProcessId=555" get CommandLine'),
    ("ALLOW", 'Get-CimInstance Win32_Process -Filter "ProcessId = 555"'),
    ("ALLOW", "Get-Process -Id 555"),
    ("ALLOW", "Get-Process notepad"),
    ("ALLOW", "netstat -ano | findstr :3000"),
    ("ALLOW", "taskkill /PID 555 /F"),
    # Reading/writing about iotta with no process-hunt verb at all.
    ("ALLOW", "grep -rn iotta docs/README.md"),
    ("ALLOW", "cd server && python -m pytest tests/ -q  # iotta test suite"),
    # 8000/8001 mentioned but no process-hunt shape (e.g. curling the health endpoint).
    ("ALLOW", "curl http://127.0.0.1:8000/health"),
    ("ALLOW", "curl http://127.0.0.1:8001/health  # iotta stable"),
    # The correct restart mechanism itself must never be blocked.
    ("ALLOW", "gh workflow run deploy.yml -f ref=main -f target=dev"),
    ("ALLOW", "gh workflow run deploy.yml -f ref=main -f target=stable"),
    # A number that merely CONTAINS 8000/8001 as a substring must not count as the port.
    ("ALLOW", "tasklist | findstr 18000"),
    ("ALLOW", "Get-Process -Id 80001"),
]


def run():
    failures = []
    for case in cases:
        want, cmd = case[0], case[1]
        ignore = case[2] if len(case) > 2 else None
        problems = check(cmd)
        got_block = bool(problems)
        if ignore is not None:
            problems = [p for p in problems if ignore not in p[0]]
            got_block = bool(problems)
        want_block = want == "BLOCK"
        if got_block != want_block:
            failures.append(f"{want} expected, got {'BLOCK' if got_block else 'ALLOW'}: {cmd!r}")
    # The escape hatch: check() still finds the problem (it does not know about overrides --
    # that is main()'s job, same split as lying_command_guard.py), but the OVERRIDE token that
    # main() gates on must be reachable, or the guard has no way out of a false positive.
    blockable = "netstat -ano | findstr :8000"
    overridden = blockable + "  # guard:ok"
    if not check(blockable):
        failures.append(f"escape-hatch control: base command unexpectedly ALLOWed: {blockable!r}")
    if not OVERRIDE.search(overridden):
        failures.append(f"escape-hatch: OVERRIDE token not detected in {overridden!r}")

    if failures:
        print(f"{len(failures)}/{len(cases) + 2} FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{len(cases) + 2}/{len(cases) + 2} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
