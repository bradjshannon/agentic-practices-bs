import runpy, os

m = runpy.run_path(os.path.expanduser("~/.claude/hooks/lying_command_guard.py"))
check = m["check"]

cases = [
    # The EXACT command that failed on 2026-07-19 -- fully inside double quotes,
    # which shell_only() strips. This is the case the rule must actually catch.
    ("BLOCK", 'pwsh -NoProfile -Command ". .\\idf.ps1; idf.py build"'),
    ("BLOCK", ". ./idf.ps1; idf.py -p COM7 flash"),
    ("BLOCK", "Set-Location C:\\x; . .\\idf.ps1; idf.py app-flash"),
    # Benign -- these MUST NOT fire. A guard that cries wolf gets disabled.
    ("ALLOW", ".\\idf.ps1 build"),
    ("ALLOW", ".\\idf.ps1 -p COM7 app-flash"),
    ("ALLOW", "idf.py build"),  # legitimate inside an already-exported IDF shell
    ("ALLOW", "grep -n idf.ps1 CLAUDE.md"),
    ("ALLOW", "cat idf.ps1"),
    # Nested-payload change: a real command inside -c/-Command must be seen...
    ("BLOCK", 'bash -c "cd /tmp ' + "&& git log" + '"'),
    ("BLOCK", "cd /tmp " + "&& git status"),
    # ...but a quoted string that is DATA (a commit message describing a bad
    # command) must NOT fire, or every docs commit about these traps is blocked.
    ("ALLOW", 'git commit -m "docs: never run . .\\idf.ps1; idf.py build, it exits 0"'),
    ("ALLOW", 'git commit -m "fix: use git -C instead of cd X ' + "&& git status" + '"'),
    # context-usage filtering: the pipe must attach to an ACTUAL RUN of the script.
    ("BLOCK", "python ~/.claude/context-usage.py | tail -3"),
    ("BLOCK", "py -3 ~/.claude/context-usage.py | grep pct"),
    # The two false positives observed on 2026-07-22 -- both MUST be allowed.
    ("ALLOW", "grep -n window ~/.claude/context-usage.py | head -30"),  # reads the SOURCE
    ("ALLOW", "python ~/.claude/turn-pacer.py | tail -8; python ~/.claude/context-usage.py"),
    ("ALLOW", "python ~/.claude/context-usage.py"),  # unfiltered, the correct form
    # 4b: bare cd, result unchecked, more commands follow -- the 2026-08-03 shape.
    ("BLOCK", "mkdir conductor-pub\ncd conductor-pub\ngit init -b main"),
    ("BLOCK", "cd /tmp; ls"),
    ("BLOCK", "cd /tmp\ncat README.md"),
    # Chained: a failed cd stops the rest (&&) or hits an explicit fallback (||) -- ALLOW.
    ("ALLOW", "cd /tmp && ls"),
    ("ALLOW", "cd /tmp || { echo failed; exit 1; }"),
    # cd is the only/last statement -- nothing depends on it, ALLOW.
    ("ALLOW", "cd /tmp"),
    ("ALLOW", "mkdir /tmp/x && cd /tmp/x"),
    # No cd at all -- the convention this rule is steering toward -- ALLOW.
    ("ALLOW", "git -C /tmp status"),
    ("ALLOW", "mkdir -p /tmp/x\ngit -C /tmp/x init -b main"),
    # pins.jsonl: hand-rolled writes must BLOCK, reads and the real tool must ALLOW.
    ("BLOCK", 'python -c "import json; f=open(r\'pins.jsonl\', \'a\'); f.write(json.dumps({}))"'),
    ("BLOCK", "echo '{\"thread\": \"x\"}' >> conductors/iotta/pins.jsonl"),
    ("BLOCK", 'Add-Content -Path pins.jsonl -Value \'{"thread": "x"}\''),
    ("ALLOW", "grep -n uart-satellite conductors/iotta/pins.jsonl"),
    ("ALLOW", "cat conductors/iotta/pins.jsonl"),
    ("ALLOW", "python tools/pin-thread.py uart-satellite \"state text\""),
    ("ALLOW", 'python -c "import json; print(json.dumps({}))"'),  # json.dumps with no pins.jsonl at all
]

fails = 0
for want, c in cases:
    got = "BLOCK" if check(c) else "ALLOW"
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} want={want:5} got={got:5}  {c}")

print()
print(f"{len(cases) - fails}/{len(cases)} passed, {fails} failed")
