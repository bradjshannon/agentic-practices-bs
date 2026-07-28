"""Positive AND negative controls for the writer-tool substitution guard.

Lives in a file rather than on a command line on purpose: the fixtures below ARE the
shapes the guard matches, so passing them as argv makes the guard fire on its own test
run. That is a true positive on the text and a false positive on the intent -- worth
recording, because it is the shape of every text-matching guard's blind spot.
"""
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location(
    "g", pathlib.Path.home() / ".claude" / "hooks" / "lying_command_guard.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

TICK = chr(96)
DOLLAR_PAREN = "$" + "("

CASES = [
    ("POSITIVE  backtick inside double quotes",
     'python tools/reply.py other "the ' + TICK + 'cause' + TICK + ' field also takes '
     + TICK + 'x' + TICK + '"', True),
    ("POSITIVE  $(...) inside double quotes",
     'python tools/reply.py other "value is ' + DOLLAR_PAREN + 'whoami) today"', True),
    ("POSITIVE  unquoted backtick",
     'python tools/note-find.py t tldr --detail ' + TICK + 'x' + TICK, True),
    ("POSITIVE  note-review, double-quoted",
     'python tools/note-review.py report --id x "a ' + TICK + 'sym' + TICK + '"', True),
    # --- negatives: the guard must stay silent, or it cries wolf on the CORRECT form ---
    ("NEGATIVE  single-quoted backtick is safe",
     "python tools/reply.py other 'the " + TICK + "cause" + TICK + " field is safe'", False),
    ("NEGATIVE  plain double-quoted prose",
     'python tools/reply.py other "no substitution here at all"', False),
    ("NEGATIVE  unrelated tool with a backtick",
     'git commit -m "fixes ' + TICK + 'foo' + TICK + '"', False),
    ("NEGATIVE  subprocess argv form (the recommended fix)",
     "python - <<'PY'\nsubprocess.run([sys.executable, 'tools/reply.py', t, m])\nPY", False),
    ("NEGATIVE  writer tool with no substitution at all",
     "python tools/mark-active.py diagnostics 'working on the thing'", False),
]


def fired(cmd: str) -> bool:
    return any("writer tool" in p for p, _ in g.check(cmd))


bad = 0
for name, cmd, want in CASES:
    got = fired(cmd)
    ok = got == want
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL':4} | fired={str(got):5} want={str(want):5} | {name}")

print()
print("ALL CORRECT" if not bad else f"{bad} WRONG")
sys.exit(1 if bad else 0)
