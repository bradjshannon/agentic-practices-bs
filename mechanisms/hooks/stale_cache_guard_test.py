#!/usr/bin/env python3
"""Falsifiers for stale_cache_guard.

The negative cases (it blocks the real stale read) are easy. The POSITIVE cases matter more:
a guard that blocks every cache read would pass a block-only suite and would be turned off
within a day, taking its true positives with it. So each block case is paired with an allow.
"""
import json
import os
import subprocess
import sys
import tempfile
import pathlib

# Load the guard SITTING NEXT TO THIS TEST, not whichever copy happens to be installed. This
# file is banked in mechanisms/hooks/ AND installed to ~/.claude/hooks/; with a hardcoded install
# path the banked copy silently tested the installed copy, so a regression in the banked copy
# could never fail here. __file__-relative resolves correctly from BOTH locations, which is why
# the two copies can stay byte-identical.
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stale_cache_guard.py")
results = []


def run(tool, tool_input):
    p = subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
                       capture_output=True, text=True, timeout=30)
    denied = '"permissionDecision": "deny"' in p.stdout
    return denied, p.stdout


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# --- THE REAL CASE: the actual files that caused the incident ------------------------------
cache = os.path.expanduser(
    "~/.claude/plugins/cache/conductor-bs/conductor-bs/0.1.0/skills/conductor-winddown/SKILL.md")
src = os.path.expanduser("~/Documents/GitHub/conductor-bs/skills/conductor-winddown/SKILL.md")

if os.path.isfile(cache) and os.path.isfile(src):
    denied, out = run("Read", {"file_path": cache})
    check("REAL: reading the stale cached winddown skill is DENIED", denied)
    check("REAL:  and the block names the source path", src.replace("\\", "/") in out.replace("\\\\", "/").replace("\\", "/"))

    denied, _ = run("Bash", {"command": f"sed -n '1,40p' {cache}"})
    check("REAL: reading it via Bash is DENIED too", denied)

    denied, _ = run("Bash", {"command": f"sed -n '1,40p' {cache}  # cache:ok"})
    check("REAL:  but '# cache:ok' lets a deliberate read through", not denied)

    denied, _ = run("Read", {"file_path": src})
    check("POSITIVE: reading the SOURCE is allowed", not denied)
else:
    check("REAL: fixture files present", False)

# --- POSITIVE: a cache file with NO local counterpart must be readable ---------------------
d = pathlib.Path(tempfile.mkdtemp())
orphan = d / "plugins" / "cache" / "someplugin" / "0.1.0" / "skills" / "zzz-no-such-skill"
orphan.mkdir(parents=True)
(orphan / "SKILL.md").write_text("standalone plugin content\n", encoding="utf-8")
denied, _ = run("Read", {"file_path": str(orphan / "SKILL.md")})
check("POSITIVE: a cached file with no editable counterpart is allowed", not denied)

# --- POSITIVE: identical content must not block -------------------------------------------
if os.path.isfile(src):
    twin = d / "plugins" / "cache" / "conductor-bs" / "0.1.0" / "skills" / "conductor-winddown"
    twin.mkdir(parents=True)
    (twin / "SKILL.md").write_bytes(pathlib.Path(src).read_bytes())
    denied, _ = run("Read", {"file_path": str(twin / "SKILL.md")})
    check("POSITIVE: a cache copy IDENTICAL to source is allowed", not denied)

# --- POSITIVE: ordinary reads are untouched ------------------------------------------------
denied, _ = run("Read", {"file_path": HOOK})
check("POSITIVE: a normal file read is untouched", not denied)
denied, _ = run("Bash", {"command": "git -C . status -sb"})
check("POSITIVE: a normal bash command is untouched", not denied)

# --- FAIL-OPEN: malformed input must never block -------------------------------------------
p = subprocess.run([sys.executable, HOOK], input="not json at all",
                   capture_output=True, text=True, timeout=30)
check("FAIL-OPEN: malformed hook input allows (exit 0, no deny)",
      p.returncode == 0 and "deny" not in p.stdout)

print()
bad = [n for n, ok in results if not ok]
print(f"{len(results)} checks ran")
print("ALL PASS" if not bad else f"FAILURES ({len(bad)}): " + "; ".join(bad))
sys.exit(0 if not bad else 1)
