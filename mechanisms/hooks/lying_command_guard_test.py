import runpy, os

m = runpy.run_path(os.path.expanduser("~/.claude/hooks/lying_command_guard.py"))
check = m["check"]

# A case is (want, command) or (want, command, ignore) where `ignore` is a substring of a
# problem's TEXT that this case is not about.
#
# Why the third element exists: two cases below assert that a quoted commit MESSAGE describing a
# bad command is data, not a command -- i.e. that the idf.ps1 and cd rules do not fire on it. A
# later rule (raw `git commit` -> use commit_verify.py) legitimately blocks every raw `git commit`,
# which turned both cases red and left the suite sitting at 31/33 for long enough that a real
# regression would have been invisible in the noise. Changing them to BLOCK would have thrown away
# what they actually test. Naming the unrelated rule keeps the original assertion intact and states
# the interaction explicitly.
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
    ("ALLOW", 'git commit -m "docs: never run . .\\idf.ps1; idf.py build, it exits 0"',
     "Raw `git commit`"),
    ("ALLOW", 'git commit -m "fix: use git -C instead of cd X ' + "&& git status" + '"',
     "Raw `git commit`"),
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
    # ── The status-page data files ────────────────────────────────────────────────────────────
    # Hand-rolled writes must BLOCK; reads and the file's OWN sanctioned tool must ALLOW.
    # pins.jsonl (the original rule, 2026-08-03):
    ("BLOCK", 'python -c "import json; f=open(r\'pins.jsonl\', \'a\'); f.write(json.dumps({}))"'),
    ("BLOCK", "echo '{\"thread\": \"x\"}' >> conductors/iotta/pins.jsonl"),
    ("BLOCK", 'Add-Content -Path pins.jsonl -Value \'{"thread": "x"}\''),
    ("ALLOW", "grep -n uart-satellite conductors/iotta/pins.jsonl"),
    ("ALLOW", "cat conductors/iotta/pins.jsonl"),
    ("ALLOW", "python tools/pin-thread.py uart-satellite \"state text\""),
    ("ALLOW", 'python -c "import json; print(json.dumps({}))"'),  # json.dumps, no data file at all
    # review.jsonl:
    ("BLOCK", 'python -c "import json; f=open(r\'review.jsonl\', \'a\'); f.write(json.dumps({}))"'),
    ("BLOCK", "echo '{\"id\": \"x\"}' >> conductors/iotta/review.jsonl"),
    ("ALLOW", "python tools/note-review.py report --id r1 \"title\" \"body\""),
    ("ALLOW", "grep -n report- conductors/iotta/review.jsonl"),
    # finds.jsonl:
    ("BLOCK", 'python -c "import json; f=open(r\'finds.jsonl\', \'a\'); f.write(json.dumps({}))"'),
    ("BLOCK", "echo '{\"resolves\": \"find-x\"}' >> conductors/iotta/finds.jsonl"),
    ("BLOCK", 'Add-Content -Path finds.jsonl -Value \'{"title": "x"}\''),
    ("ALLOW", "python tools/note-find.py \"a title\" \"a tldr\""),
    ("ALLOW", "python tools/note-find.py --resolve \"some card title\" --why \"measured\""),
    ("ALLOW", "grep -c resolves conductors/iotta/finds.jsonl"),
    ("ALLOW", "cat conductors/iotta/finds.jsonl"),
    # replies.jsonl:
    ("BLOCK", 'python -c "import json; f=open(r\'replies.jsonl\', \'a\'); f.write(json.dumps({}))"'),
    ("BLOCK", "echo '{\"thread\": \"x\"}' >> conductors/iotta/replies.jsonl"),
    ("ALLOW", "python tools/reply.py some-thread \"an answer for Brad\""),
    ("ALLOW", "python tools/reply.py --to last \"an answer for Brad\""),
    ("ALLOW", "wc -l conductors/iotta/replies.jsonl"),
    # THE EXEMPTION IS PER FILE. Naming pin-thread.py must not license a raw finds.jsonl write --
    # the whole reason the rule keys the exemption to each file's own writer.
    ("BLOCK", 'python -c "import json; f=open(r\'finds.jsonl\',\'a\'); f.write(json.dumps({}))"'
              "  # unlike tools/pin-thread.py this one is fine"),
    # A READ that pretty-prints is not a write. This is the common inspection on the busiest file
    # in the set, and firing on it is how a guard gets disabled and takes its true positives along.
    ("ALLOW", 'python -c "import json; [print(json.dumps(json.loads(l))) for l in '
              "open('conductors/iotta/finds.jsonl')]\""),
    # The heredoc vector: HEREDOC strips the body as prose for every other rule, so this one is
    # checked against the RAW text too. Without that, the realistic shape walks straight through.
    ("BLOCK", "python - <<'PY'\nimport json\nopen('finds.jsonl','a').write(json.dumps({}))\nPY"),
]

fails = 0
for case in cases:
    want, c = case[0], case[1]
    ignore = case[2] if len(case) > 2 else None
    problems = check(c)
    if ignore:
        problems = [p for p in problems if ignore not in p[0]]
    got = "BLOCK" if problems else "ALLOW"
    ok = got == want
    fails += 0 if ok else 1
    shown = c.replace("\n", "\\n")
    print(f"{'ok  ' if ok else 'FAIL'} want={want:5} got={got:5}  {shown}"
          + (f"   [ignoring: {ignore}]" if ignore else ""))

print()
print(f"{len(cases) - fails}/{len(cases)} passed, {fails} failed")
raise SystemExit(1 if fails else 0)
