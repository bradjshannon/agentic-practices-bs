"""Coverage for rule 7 (lying_command_guard.py): raw esptool/idf.py flash primitives vs
tools\\flash-device.ps1.

THE INCIDENT, 2026-08-13: a firmware lot's brief did not name flash-device.ps1. It tried
`idf.py flash`, hit the permission classifier, and retried with raw `esptool write_flash` for the
same intent -- and that wrote the WRONG board, trusting a stale docs\\device-roster.md COM-port row
instead of a verified MAC. A second raw esptool call later raised an approval card that blocked
the operator's session.

Every MUST-FIRE case here is paired with a must-NOT case that is deliberately similar, per this
file's own rule: a guard test that only checks "the bad command fires" can pass on a guard that
fires on everything.
"""
import os
import runpy
import tempfile
from pathlib import Path

# Telemetry isolation -- keep this suite OUT of the live ~/.claude/hook-events.jsonl, the
# one file that says whether a hook works. Must be set before any hook runs; subprocesses
# inherit it. Any new hook test needs these two lines. See hook_log.log_path().
os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")

# Load the guard NEXT TO THIS FILE -- i.e. this repo's BANKED copy, not whatever happens to be
# installed under ~/.claude on the machine that runs this. See lying_command_guard_test.py's own
# header for why this matters (the 2026-08-04 retargeting fix).
m = runpy.run_path(str(Path(__file__).resolve().parent / "lying_command_guard.py"))
check = m["check"]

cases = [
    # ── MUST FIRE: the raw primitives, in the shapes actually seen on this estate ─────────────
    ("MUST FIRE  bare esptool write_flash",
     "esptool --port COM7 write_flash 0x0 a.bin", True),
    ("MUST FIRE  esptool.py write_flash",
     "esptool.py --port COM7 write_flash 0x1000 image.bin", True),
    ("MUST FIRE  python esptool.py write_flash",
     "python esptool.py --port COM7 write_flash 0x1000 image.bin", True),
    ("MUST FIRE  python -m esptool write_flash",
     "python -m esptool --chip esp32s3 -p COM7 write_flash 0x0 boot.bin 0x10000 app.bin", True),
    ("MUST FIRE  py -3 -m esptool write_flash",
     "py -3 -m esptool --port COM7 write_flash 0x0 a.bin", True),
    ("MUST FIRE  full quoted venv python.exe -m esptool write_flash (the REAL shape on this box)",
     '& "E:\\Espressif\\python_env\\idf5.3_py3.12_env\\Scripts\\python.exe" -m esptool '
     '--port COM7 write_flash 0x0 a.bin', True),
    ("MUST FIRE  full quoted esptool.exe write_flash",
     '& "E:\\Espressif\\tools\\esptool.exe" --port COM7 write_flash 0x0 a.bin', True),
    ("MUST FIRE  idf.py flash",
     "idf.py -p COM7 flash", True),
    ("MUST FIRE  idf.py app-flash",
     "idf.py -B build -p COM7 app-flash", True),
    ("MUST FIRE  bare idf.py flash",
     "idf.py flash", True),
    ("MUST FIRE  chained after cd",
     "cd repo && idf.py -p COM7 flash", True),
    ("MUST FIRE  nested pwsh -Command payload (the 2026-07-19 idf.ps1 trap's own shape)",
     'pwsh -NoProfile -Command "python -m esptool --port COM7 write_flash 0x0 a.bin"', True),
    ("MUST FIRE  retry-with-rephrase, same intent as an idf.py flash block "
     "(THE EXACT 2026-08-13 INCIDENT SHAPE)",
     'esptool --port COM9 write_flash 0x0 build/myproject_firmware.bin', True),

    # ── must NOT: read-only identity checks (requirement 2 -- these must stay allowed) ────────
    ("must NOT   esptool read_mac (bare)",
     "esptool --port COM7 read_mac", False),
    ("must NOT   esptool chip_id (bare)",
     "esptool --port COM7 chip_id", False),
    ("must NOT   esptool read_mac via the REAL quoted venv python.exe path "
     "(flash-device.ps1's own Invoke-EsptoolReadMac shape)",
     '& "E:\\Espressif\\python_env\\idf5.3_py3.12_env\\Scripts\\python.exe" --port COM7 '
     '--baud 115200 --before default_reset --after hard_reset read_mac', False),
    ("must NOT   esptool -m form read_mac",
     "python -m esptool --port COM7 read_mac", False),

    # ── must NOT: idf.py operations that never touch a port's identity ────────────────────────
    ("must NOT   idf.py build", "idf.py build", False),
    ("must NOT   idf.py monitor", "idf.py -p COM7 monitor", False),

    # ── must NOT: the wrapper's OWN invocation (requirement -- the sanctioned route) ──────────
    ("must NOT   flash-device.ps1 invoked relative, multi-line",
     'Set-Location "C:\\x\\myproject-firmware"\n'
     '& tools\\flash-device.ps1 -Board nulllab-ai-vox3 -Device nulllab-ai-vox3-d55940', False),
    ("must NOT   flash-device.ps1 invoked absolute, quoted, -DryRun",
     '& "C:\\x\\myproject-firmware\\tools\\flash-device.ps1" '
     '-Board esp32-s3-audio-box -Device esp32-s3-audio-box-84c938 -DryRun', False),

    # NOT TESTABLE HERE, AND DELIBERATELY NOT ASSERTED: flash-device.ps1's internal
    # `idf.py -B $BuildDir -p $Port app-flash` (Invoke-UsbFlash) and internal `esptool ...
    # read_mac` (Invoke-EsptoolReadMac) are never seen by this hook AT ALL, because a PreToolUse
    # hook only inspects the text of the agent's OWN tool call, never a subprocess an
    # already-running script spawns. There is no `check()` call that demonstrates this -- it is a
    # structural property of the hook mechanism, not a regex outcome, and the two ALLOW cases
    # above (the wrapper's own invocation, matched on ITS OWN command text) are the closest this
    # test file can get to it. If `idf.py -B $BuildDir -p $Port app-flash` were EVER typed
    # directly BY AN AGENT (not sourced from inside flash-device.ps1), it WOULD fire -- correctly.

    # ── must NOT: reading/inspecting the wrapper or the primitives, never invoking them ────────
    ("must NOT   grep for the primitive in prose",
     'grep -rn "esptool write_flash" tools/', False),
    ("must NOT   cat the wrapper source (which itself mentions esptool/idf.py)",
     "cat tools/flash-device.ps1", False),
    ("must NOT   grep the wrapper source for esptool",
     "grep -n esptool tools/flash-device.ps1", False),
    ("must NOT   a commit message describing this very rule",
     'git commit -m "feat: block raw esptool write_flash, route to flash-device.ps1"', False),

    # ── must NOT: unrelated OTA-rule primitives (sanity -- rules must not cross-fire) ──────────
    ("must NOT   firmware-list (read-only OTA CLI, unrelated rule)",
     "myproject-devices firmware-list", False),
]

# Filtered to THIS rule's own fingerprint text, not "did check() return anything at all" -- two
# of the ALLOW fixtures below (`idf.py build`, a commit message about this very rule) legitimately
# trip OTHER, unrelated rules already in this file (the slow-foreground N+2 rule; the raw
# `git commit` rule) and must stay green for THOSE reasons while proving nothing about rule 7.
# Same "ignore" idiom lying_command_guard_test.py uses for its own idf.ps1/cd overlap cases.
FINGERPRINT = "esptool/idf.py flash primitive"

ok = 0
for name, cmd, want in cases:
    problems = [p for p in check(cmd) if FINGERPRINT in p[0]]
    fired = bool(problems)
    good = fired == want
    ok += good
    shown = cmd.replace("\n", "\\n")
    print(f"{'PASS' if good else 'FAIL'}  {name}  (fired={fired}, want={want})  {shown[:90]}")
    if not good:
        for prob, fix in check(cmd):
            print("        ->", prob[:160])

print(f"\n{ok}/{len(cases)}")
raise SystemExit(0 if ok == len(cases) else 1)
