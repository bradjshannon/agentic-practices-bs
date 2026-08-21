#!/usr/bin/env python3
"""Tests for command_shape_guard / command_shape_detect.

Run:  py -3 ~/.claude/hooks/command_shape_guard_test.py
"""
import os
import runpy
import sys
import tempfile

os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")

HERE = os.path.dirname(os.path.abspath(__file__))
G = runpy.run_path(os.path.join(HERE, "command_shape_guard.py"))
evaluate = G["evaluate"]

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


def fence(lang, body):
    return f"```{lang}\n{body}\n```"


# --- SHOULD FIRE: the four real board commands, as they would appear fenced in chat -----------

check("board1: drive-fwdslash + piped tail, unlabeled fence",
      bool(evaluate(fence("", 'git -C "C:/Users/user/Documents/GitHub/myproject-firmware" tag -l | tail -5'))),
      True)

check("board2: drive-fwdslash, bash-labeled fence",
      bool(evaluate(fence("bash", "git -C C:/Users/user/Documents/GitHub/myproject push origin main"))),
      True)

check("board4: drive-fwdslash, powershell-labeled fence (mislabeled-but-still-broken)",
      bool(evaluate(fence("powershell", "git -C C:/Users/user/Documents/GitHub/myproject ls-files .env"))),
      True)

check("grep piped, no drive path",
      bool(evaluate(fence("bash", "docker logs myproject-dev | grep ERROR"))),
      True)

check("bash var-assign command substitution",
      bool(evaluate(fence("", "TOK=$(cat ~/.env) && curl -H \"Authorization: Bearer $TOK\" http://x"))),
      True)

check("backtick substitution",
      bool(evaluate(fence("", "echo `git rev-parse HEAD`"))),
      True)

check("2>/dev/null",
      bool(evaluate(fence("", "some-cmd 2>/dev/null"))),
      True)

# --- SHOULD NOT FIRE: the three positive controls the brief names, plus fence-lang exemptions --

check("CONTROL: legit PowerShell command with backslashes",
      bool(evaluate(fence("powershell", r"git -C C:\Users\user\Documents\GitHub\myproject status"))),
      False)

check("CONTROL: wsl -e docker exec with container POSIX paths",
      bool(evaluate(fence("", "wsl -e docker exec myproject-dev cat /etc/hostname"))),
      False)

check("CONTROL: && is valid pwsh7, not flagged",
      bool(evaluate(fence("powershell", "cd C:\\foo && dir"))),
      False)

check("CONTROL: forward-slash path but every context is bash/WSL (fence-lang inferred)",
      bool(evaluate(fence("bash", "ls -la /mnt/c/Users/user/Documents/GitHub/myproject"))),
      False)

check("CONTROL: non-shell fence language (python) is not scanned even with bash-looking text",
      bool(evaluate(fence("python", 'import os; os.system("tail -5 x")'))),
      False)

check("CONTROL: json fence never scanned",
      bool(evaluate(fence("json", '{"path": "C:/Users/user/foo"}'))),
      False)

# --- Note: a normal Bash-tool invocation is structurally out of scope ---------------------------
# `evaluate()` only ever receives the assistant's own TEXT blocks (turn_said() pulls "said" from
# turn_window.turn(), which is text blocks only) -- a tool_use block (what the Bash tool actually
# executes) is never passed to this function at all, so there is nothing to test here: the
# exclusion is structural, not a judgment call the detector makes at runtime.

if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):")
    for f in FAILURES:
        print(f"  {f}")
    sys.exit(1)
print("all command_shape_guard checks passed")
