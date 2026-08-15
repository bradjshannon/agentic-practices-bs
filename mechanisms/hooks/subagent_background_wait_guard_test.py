import json
import os
import runpy
import tempfile

# Telemetry isolation -- keep this suite OUT of the live ~/.claude/hook-events.jsonl, the
# one file that says whether a hook works. Must be set before any hook runs; subprocesses
# inherit it. Any new hook test needs these two lines. See hook_log.log_path().
os.environ["HOOK_LOG_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="hooklog-test-"), "events.jsonl")


HERE = os.path.dirname(os.path.abspath(__file__))
m = runpy.run_path(os.path.join(HERE, "subagent_background_wait_guard.py"))

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} {label}: got={got!r} want={want!r}")


def run_main(payload, tmp):
    """Feed `payload` to main() via stdin, in a fresh state dir. Returns the deny reason
    string, or None if it allowed (exit 0, no output)."""
    import io
    import sys

    os.environ["SUBAGENT_BG_GUARD_STATE_DIR"] = tmp
    old_stdin, old_stdout = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(json.dumps(payload))
    sys.stdout = io.StringIO()
    try:
        try:
            m["main"]()
        except SystemExit:
            pass
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = old_stdin, old_stdout
    if not out.strip():
        return None
    obj = json.loads(out)
    return obj["hookSpecificOutput"]["permissionDecisionReason"]


TOP_LEVEL = {
    "tool_name": "Bash",
    "session_id": "s1",
    "tool_input": {"command": "python build.py", "run_in_background": True},
    # no agent_id -- this IS the top-level conductor
}
SUBAGENT_BG = {
    "tool_name": "Bash",
    "session_id": "s1",
    "agent_id": "a1",
    "tool_input": {"command": "python build.py", "run_in_background": True},
}
SUBAGENT_FG = {
    "tool_name": "Bash",
    "session_id": "s1",
    "agent_id": "a1",
    "tool_input": {"command": "python build.py"},  # no run_in_background at all
}

with tempfile.TemporaryDirectory() as tmp:
    # -- POSITIVE: a subagent backgrounding a command gets the reminder, once --
    reason1 = run_main(SUBAGENT_BG, tmp)
    check("first background dispatch from a subagent is denied-with-reminder",
          reason1 is not None, True)
    check("the reminder names the actual failure mode",
          "does NOT mean you will be resumed" in (reason1 or ""), True)

    reason2 = run_main(SUBAGENT_BG, tmp)
    check("the SAME subagent's second background dispatch this session is allowed",
          reason2, None)

    # -- NEGATIVE CONTROLS, each must NOT fire --
    check("the top-level conductor backgrounding a command is never interrupted",
          run_main(TOP_LEVEL, tmp), None)

    check("a subagent running a command in the FOREGROUND is never interrupted",
          run_main(SUBAGENT_FG, tmp), None)

    other_agent = dict(SUBAGENT_BG, agent_id="a2")
    reason3 = run_main(other_agent, tmp)
    check("a DIFFERENT subagent in the same session still gets its own first reminder",
          reason3 is not None, True)

    # -- Escape hatch --
    fresh_agent = dict(SUBAGENT_BG, agent_id="a3",
                       tool_input={"command": "python build.py # bg:ok",
                                   "run_in_background": True})
    check("the # bg:ok override skips the reminder outright",
          run_main(fresh_agent, tmp), None)
    # And it must not have consumed a3's one-time budget -- a real background dispatch right
    # after the overridden one should still get the reminder, since a3 was never actually warned.
    reason4 = run_main(dict(SUBAGENT_BG, agent_id="a3"), tmp)
    check("using the override once does not silently spend the per-actor budget",
          reason4 is not None, True)

    # -- Fail-open on malformed input --
    import io
    import sys

    os.environ["SUBAGENT_BG_GUARD_STATE_DIR"] = tmp
    old_stdin = sys.stdin
    sys.stdin = io.StringIO("not json")
    try:
        try:
            m["main"]()
            exited_clean = True
        except SystemExit as e:
            exited_clean = e.code in (0, None)
    finally:
        sys.stdin = old_stdin
    check("malformed stdin fails open (no exception escapes)", exited_clean, True)

print()
print(f"{'ALL PASS' if fails == 0 else f'{fails} FAILED'}")
