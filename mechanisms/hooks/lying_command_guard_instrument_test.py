"""Test the two new lying_command_guard patterns, both directions.

A guard test that only checks "the bad command fires" can pass on a guard that fires on
everything, so every MUST-FIRE case here is paired with a must-NOT case that is deliberately
similar.
"""
import importlib.util
import pathlib

# Relative to THIS file = the banked copy in this repo. Loading from ~/.claude/hooks/ (as this
# did until 2026-07-29) makes a green run a statement about the installed hook, not about what
# another machine would pull.
spec = importlib.util.spec_from_file_location(
    "g", str(pathlib.Path(__file__).resolve().parent / "lying_command_guard.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

CR = "$" + chr(39) + chr(92) + "r" + chr(39)          # $'\r' without letting a shell see it
JSONPATH = '"{\\"transcript_path\\": \\"/c/Users/user/t.jsonl\\"}"'

cases = [
    ("MUST FIRE  crlf grep",      f"grep -c {CR} /c/Users/user/x.sh", True),
    ("MUST FIRE  crlf grep piped", f"cat f | grep -c {CR}", True),
    ("MUST FIRE  json /c/ path",  f"echo {JSONPATH} | python h.py", True),
    ("must NOT   ordinary grep",  "grep -c foo file.txt", False),
    ("must NOT   grep for CRLF word", "grep -rn CRLF ~/.claude/hooks/", False),
    ("must NOT   python read_bytes",
     'python -c "import pathlib;print(pathlib.Path(r\'C:/x\').read_bytes().count(b\'\\r\\n\'))"',
     False),
    ("must NOT   native win path in json",
     'python -c "import json;print(json.dumps({\'p\': \'C:/Users/user/t.jsonl\'}))"', False),
    ("must NOT   url inside json", 'curl -d \'{"url": "http://localhost:8000/x"}\' http://h', False),
]

ok = 0
for name, cmd, want in cases:
    fired = bool(g.check(cmd))
    good = fired == want
    ok += good
    print(f"{'PASS' if good else 'FAIL'}  {name}  (fired={fired}, want={want})")
    if not good:
        for prob, fix in g.check(cmd):
            print("        ->", prob[:100])
print(f"\n{ok}/{len(cases)}")
raise SystemExit(0 if ok == len(cases) else 1)
