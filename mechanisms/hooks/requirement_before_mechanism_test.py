import json, os, subprocess, sys, tempfile

# The hook UNDER TEST is the banked copy next to this file, not `~/.claude/hooks/`. Until
# 2026-07-29 it was the latter, which made a green run a statement about whatever happened to be
# installed on the machine running the suite — the banked file could be broken and this would
# still pass, and the banked file is the one another machine pulls.
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "requirement_before_mechanism.py")


def transcript(assistant_text, edits):
    lines = [{"type": "user", "message": {"content": "do the thing"}}]
    blocks = [{"type": "text", "text": assistant_text}]
    for p in edits:
        blocks.append({"type": "tool_use", "name": "Edit", "input": {"file_path": p}})
    lines.append({"type": "assistant", "message": {"content": blocks}})
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for entry in lines:
            fh.write(json.dumps(entry) + "\n")
    return path


def run(assistant_text, edits, stop_active=False):
    path = transcript(assistant_text, edits)
    payload = {"transcript_path": path, "stop_hook_active": stop_active}
    out = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                         capture_output=True, text=True).stdout
    os.unlink(path)
    return "BLOCK" if '"block"' in out else "ALLOW"


cases = [
    # (expected, description, assistant_text, edited_paths)
    ("BLOCK", "source edit, no requirement line",
     "I changed the drain to reuse the connection.", ["C:/x/server/src/iotta/devices.py"]),
    ("BLOCK", "firmware source edit, no requirement",
     "Fixed the stack size.", ["C:/x/main/crash_upload.cpp"]),
    ("ALLOW", "source edit WITH requirement line",
     "**Requirement:** the operator needs the decoded crash.\nSo I changed X.",
     ["C:/x/server/src/iotta/devices.py"]),
    ("ALLOW", "requirement without bold markers",
     "Requirement: consumers need current uptime.", ["C:/x/main/app_main.cpp"]),
    ("ALLOW", "docs-only edit", "Recorded the finding.", ["C:/x/docs/decisions.md"]),
    ("ALLOW", "markdown edit", "Updated the brief.", ["C:/x/CLAUDE.md"]),
    ("ALLOW", "test-only edit", "Added a regression test.",
     ["C:/x/server/tests/test_boot_at.py"]),
    ("ALLOW", "changelog", "Noted it.", ["C:/x/CHANGELOG.md"]),
    ("ALLOW", "scratchpad", "Scratch script.", ["C:/tmp/scratchpad/thing.py"]),
    ("ALLOW", "no edits at all", "Just explaining something.", []),
    ("ALLOW", "explicit override", "requirement:ok — mechanical rename only.",
     ["C:/x/server/src/iotta/devices.py"]),
]

fails = 0
for want, desc, text, edits in cases:
    got = run(text, edits)
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} want={want:5} got={got:5}  {desc}")

# loop guard
got = run("no requirement here", ["C:/x/server/src/iotta/devices.py"], stop_active=True)
ok = got == "ALLOW"
fails += 0 if ok else 1
print(f"{'ok  ' if ok else 'FAIL'} want=ALLOW got={got:5}  stop_hook_active (must not loop)")

print()
print(f"{len(cases) + 1 - fails}/{len(cases) + 1} passed, {fails} failed")
# Exit non-zero on failure. Until 2026-07-29 this file printed "N failed" and then exited 0,
# so any runner keying on the exit code saw a pass — the same "reports success while
# demonstrating nothing" shape the ledger exists to catch.
sys.exit(1 if fails else 0)
