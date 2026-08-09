import os, runpy
from pathlib import Path

# Load the guard NEXT TO THIS FILE -- i.e. this repo's BANKED copy, not whatever happens to be
# installed under ~/.claude on the machine that runs this.
#
# This line said `os.path.expanduser("~/.claude/hooks/...")` until 2026-08-04, and GUARD-LEDGER.md's
# row for this suite had claimed since 2026-07-29 that it had already been retargeted. It had not.
# Three ledger rows cited this file, so three rows' evidence described the INSTALLED hook while
# asserting something about the banked one -- and the banked one could have been broken with the
# suite still green. That is precisely the hole `WHERE-MECHANISMS-LIVE.md` names for hooks (nothing
# keeps the two copies in step) arriving inside the ledger that was supposed to notice it.
#
# It also made the CI workflow shipped in ef902f5b permanently RED: on a runner with no ~/.claude,
# this file raised FileNotFoundError, and `tools/check_guard_ledger_freshness.py` reported all three
# rows STALE. Measured 2026-08-04 by running the checker with HOME pointed at an empty directory:
# "18 row(s): 11 fresh, 4 stale, 3 no-test" -- three of the four stale were this file, and the
# staleness had nothing to do with any ledger claim going stale.
m = runpy.run_path(str(Path(__file__).resolve().parent / "lying_command_guard.py"))
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
    # Legitimate inside an already-exported IDF shell -- w.r.t. RULE 5, which is what this case
    # is about. It is not silent overall any more: the offload rule (N+2, added 2026-08-08)
    # legitimately fires on it, because a foreground `idf.py build` blocks the tool call for
    # minutes. Naming that rule keeps the original assertion -- "rule 5 must not fire on a bare
    # idf.py" -- intact and exact, instead of flipping the case to BLOCK and throwing it away.
    ("ALLOW", "idf.py build", "in the FOREGROUND"),
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
    # ── Regressions from the 2026-08-04 adversarial review + one found live the same day ──────
    # (a) The exemption must key on the tool being INVOKED, not on its name appearing. Both of
    #     these were confirmed false negatives: a genuine hand-rolled append walked through
    #     because the sanctioned tool's filename occurred in an echo or in a comment.
    ("BLOCK", 'echo "see tools/note-find.py for the sanctioned way" && '
              "python -c \"import json; open('finds.jsonl','a').write(json.dumps({}))\""),
    ("BLOCK", "# uses note-find.py conventions\n"
              "python -c \"import json; open('finds.jsonl','a').write(json.dumps({}))\""),
    # ...while the real invocation, with and without a directory prefix, stays exempt.
    ("ALLOW", "python tools/note-find.py \"another title\" \"another tldr\" --needs action"),
    ("ALLOW", "py -3 note-find.py \"another title\" \"another tldr\""),
    # (b) The filename must sit on a path/word boundary. `scratch_finds.jsonl` is not one of the
    #     four sanctioned files, and the INSTALLED hook really did block this exact command
    #     during the review -- a nuisance fire on a throwaway fixture is how a guard gets routed
    #     around. Both directions asserted so the boundary cannot be widened back silently.
    ("ALLOW", "python -c \"import json; open('scratch_finds.jsonl','a').write(json.dumps({}))\""),
    ("ALLOW", "python -c \"import json; open('test_replies.jsonl','a').write(json.dumps({}))\""),
    ("BLOCK", "python -c \"import json; open('conductors/iotta/finds.jsonl','a')"
              ".write(json.dumps({}))\""),
    # (c) A whole-file REPLACE is strictly worse than an unverified append and was undetected.
    ("BLOCK", "@{title='x'} | ConvertTo-Json -Compress | Set-Content finds.jsonl"),
    ("BLOCK", "@{title='x'} | ConvertTo-Json -Compress | Out-File pins.jsonl"),
    # (d) Rule 4b fired on a QUOTED path even when properly `&&`-chained -- it recommended the
    #     form it was blocking. Found live 2026-08-04 on the first two commands of a run.
    ("ALLOW", 'cd "C:/Users/x/Documents/GitHub/conductor-bs" && sed -n "1,5p" foo.md'),
    ("ALLOW", 'cd "C:/x y/z" && ls'),
    ("ALLOW", "cd \"C:/x y/z\" || { echo failed; exit 1; }"),
    # ...and the real hazard with a quoted path is still caught, so (d) is not a hole punched
    # through the rule. This is the 2026-08-03 shape with the path quoted.
    ("BLOCK", 'cd "C:/x y/conductor-pub"\ngit init -b main'),
    ("BLOCK", 'cd "C:/x y/z"; cat README.md'),
    # ...including inside a nested payload, which the placeholder rewrite must not drop.
    ("BLOCK", 'bash -c "cd /tmp; cat README.md"'),
    # ── Rule N+2: a measured-slow command in the FOREGROUND (2026-08-08) ──────────────────────
    # Narrowed by a 13,527-command corpus; see
    # conductor-bs/conductors/iotta/proposals/2026-08-08-offload-guard-measurement.md.
    # (i) TRUE POSITIVES -- one per guarded shape.
    ("BLOCK", "python -m pytest tools/ -q"),
    ("BLOCK", "PYTHONPATH=src python -m pytest tests/ -q 2>&1 | tail -2"),
    ("BLOCK", "pytest"),
    ("BLOCK", "py -3 -m pytest tests/"),
    ("BLOCK", "cd server && python -m pytest tests/ -q"),
    ("BLOCK", "npm run build"),
    ("BLOCK", "npm test"),
    ("BLOCK", "vitest run"),
    ("BLOCK", "idf.py -p COM7 flash"),
    ("BLOCK", "idf.py monitor"),
    # (ii) THE MANDATORY FALSE-POSITIVE CORPUS. Every one of these was MEASURED as a common,
    #      correct command; the four `DROP`ped candidates in the proposal died on exactly these.
    ("ALLOW", "grep -v x file"),          # invert-match SHRINKS output; `-v` was dropped for this
    ("ALLOW", "git remote -v"),
    ("ALLOW", "docker -v"),
    ("ALLOW", "git log --oneline -1"),    # `git log` dropped: 183 of 215 already bounded
    ("ALLOW", "python tools/ack-inbox.py --all"),  # `--all` dropped: internal tool, tiny inbox
    # A TARGETED pytest is fast and must never fire -- 203 of 333 real invocations are these.
    ("ALLOW", "python -m pytest tests/test_devices.py -q"),
    ("ALLOW", "pytest -k \"rejects_version\" -q"),
    ("ALLOW", "python -m pytest tools/test_status_page.py::SomeTest::test_x"),
    # The word `pytest` as an ARGUMENT rather than the verb -- the reason the invocation regex
    # anchors on segment-start or `-m` instead of matching the bare word anywhere.
    ("ALLOW", "grep -rn pytest docs/"),
    # THE PROSE TRAP, §3: 28 of 30 corpus `idf.py` matches are text, not commands -- including
    # this file's own fixtures. A heredoc body must be invisible to this rule.
    ("ALLOW", "python - <<'PY'\nprint('the runbook says to run idf.py build first')\nPY"),
    # Near-miss controls: the neighbouring subcommands of each guarded shape are NOT slow.
    ("ALLOW", "npm install"),
    ("ALLOW", "npm run dev"),
    ("ALLOW", "idf.py menuconfig"),
    ("ALLOW", "idf.py --version"),
    # (iii) THE GATE THAT MAKES THE RULE HONEST. Identical commands to the true positives above,
    #       differing ONLY in the Bash tool's `run_in_background` PARAMETER. Without this the
    #       rule would fire just as loudly on an agent that had already done the right thing --
    #       a 100% false-positive rate on correct behaviour, strictly worse than no guard.
    ("ALLOW", "python -m pytest tools/ -q", None, True),
    ("ALLOW", "npm run build", None, True),
    ("ALLOW", "idf.py build", None, True),
]

fails = 0
for case in cases:
    want, c = case[0], case[1]
    ignore = case[2] if len(case) > 2 else None
    # 4th element: the Bash tool's `run_in_background` PARAMETER, which is NOT part of the
    # command string and so cannot be expressed in `c`. Only the offload rule reads it.
    bg = case[3] if len(case) > 3 else False
    problems = check(c, run_in_background=bg)
    if ignore:
        problems = [p for p in problems if ignore not in p[0]]
    got = "BLOCK" if problems else "ALLOW"
    ok = got == want
    fails += 0 if ok else 1
    shown = c.replace("\n", "\\n")
    print(f"{'ok  ' if ok else 'FAIL'} want={want:5} got={got:5}  {shown}"
          + (f"   [ignoring: {ignore}]" if ignore else "")
          + ("   [run_in_background=True]" if bg else ""))

print()
print(f"{len(cases) - fails}/{len(cases)} passed, {fails} failed")
raise SystemExit(1 if fails else 0)
