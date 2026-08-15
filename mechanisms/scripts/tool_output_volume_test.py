import json
import os
import runpy
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
m = runpy.run_path(os.path.join(HERE, "tool_output_volume.py"))

result_chars = m["result_chars"]
spool_info = m["spool_info"]

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += 0 if ok else 1
    print(f"{'ok  ' if ok else 'FAIL'} {label}: got={got!r} want={want!r}")


# -- result_chars: shape tolerance, because a metric that silently reads 0 is worse than none --
check("stdout only", result_chars({"stdout": "abcde", "stderr": ""}), 5)
check("stdout + stderr are summed", result_chars({"stdout": "abc", "stderr": "de"}), 5)
check("bare string response", result_chars("abcdefg"), 7)
check("None response does not raise", result_chars(None), 0)
check("empty dict falls back to json length", result_chars({}), len("{}"))

# -- spool_info: the truncation signal is the harness's own out-of-band fields, not a sniffed
# marker. Verified against 1135 real Bash results (see module docstring). --
check("not spooled", spool_info({"stdout": "x" * 100}), (False, None))
check(
    "spooled carries the true pre-truncation size",
    spool_info({"stdout": "x" * 30000,
                "persistedOutputPath": r"C:\tmp\tool-results\b95r40syx.txt",
                "persistedOutputSize": 33205}),
    (True, 33205),
)
check("non-dict response is not spooled", spool_info("plain text"), (False, None))

# -- End-to-end through handle_post, with hook_log redirected into a scratch file so the real
# ~/.claude/hook-events.jsonl is never touched. This used to monkeypatch hook_log.LOG_PATH, which
# worked only because the hook runs IN-PROCESS here; HOOK_LOG_PATH is the estate-wide mechanism
# (hook_log.log_path() re-reads it per call) and also covers subprocesses. Same file either way.
import hook_log  # noqa: E402,F401

with tempfile.TemporaryDirectory() as tmp:
    log_path = os.path.join(tmp, "hook-events.jsonl")
    os.environ["HOOK_LOG_PATH"] = log_path

    def rows():
        if not os.path.isfile(log_path):
            return []
        with open(log_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def run(payload):
        """Drive main() the way the harness does: JSON on stdin. Returns the exit code."""
        stdin_path = os.path.join(tmp, "stdin.json")
        with open(stdin_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        old = sys.stdin
        try:
            with open(stdin_path, encoding="utf-8") as fh:
                sys.stdin = fh
                try:
                    m["main"]()
                    return 0
                except SystemExit as e:
                    return e.code or 0
        finally:
            sys.stdin = old

    # 1. A normal Bash call is recorded with the right length.
    code = run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "sess-1",
        "tool_input": {"command": "pytest -q tests/"},
        "tool_response": {"stdout": "y" * 4321, "stderr": "err", "interrupted": False},
    })
    check("normal Bash call exits 0 (never blocks)", code, 0)
    r = rows()
    check("normal Bash call is recorded exactly once", len(r), 1)
    if r:
        check("recorded char count = stdout + stderr", r[0]["chars"], 4321 + 3)
        check("recorded command is the short form", r[0]["trigger"], "pytest -q tests/")
        check("recorded under this hook's name", r[0]["hook"], "tool_output_volume")
        check("session is carried through", r[0]["session"], "sess-1")
        check("not flagged as spooled", r[0]["spooled"], False)
        check("result CONTENT is never logged",
              any("yyyy" in str(v) for v in r[0].values()), False)

    # 2. A spooled/truncated result is flagged, with the harness's true size.
    run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "sess-1",
        "tool_input": {"command": "docker compose logs"},
        "tool_response": {"stdout": "z" * 30000, "stderr": "",
                          "persistedOutputPath": r"C:\tmp\b6svwx50w.txt",
                          "persistedOutputSize": 126731},
    })
    r = rows()
    check("spooled result is flagged", r[-1]["spooled"], True)
    check("spooled result records the true pre-truncation size", r[-1]["spooled_size"], 126731)

    # 3. A malformed / missing tool_response must not raise and must not cost the call.
    before = len(rows())
    code = run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "sess-1",
        "tool_input": {"command": "true"},
        # tool_response entirely absent
    })
    check("missing tool_response exits 0", code, 0)
    r = rows()
    check("missing tool_response still records one row (chars=0)", len(r) - before, 1)
    if len(r) > before:
        check("missing tool_response records zero chars", r[-1]["chars"], 0)

    code = run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "sess-1",
        "tool_input": "not-a-dict",
        "tool_response": 12345,
    })
    check("garbage tool_input/tool_response exits 0", code, 0)

    # 4. A non-Bash tool is IGNORED. Chosen deliberately: Read/Grep/Glob volume is bounded and
    # already visible in the call itself, and the decision this instrument feeds -- "run this
    # command inline or hand it to a chore-runner" -- is only ever made about shell commands.
    # Recording every tool would bury the signal in the noise it exists to find.
    before = len(rows())
    code = run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "session_id": "sess-1",
        "tool_input": {"file_path": "/x/y.txt"},
        "tool_response": {"stdout": "q" * 99999},
    })
    check("non-Bash tool exits 0", code, 0)
    check("non-Bash tool is not recorded", len(rows()) - before, 0)

    # PowerShell IS recorded -- same shell-volume problem, primary shell on this box.
    before = len(rows())
    run({
        "hook_event_name": "PostToolUse",
        "tool_name": "PowerShell",
        "session_id": "sess-1",
        "tool_input": {"command": "Get-ChildItem -Recurse"},
        "tool_response": {"stdout": "p" * 700},
    })
    r = rows()
    check("PowerShell is recorded too", len(r) - before, 1)
    if len(r) > before:
        check("PowerShell entry is tagged with its tool", r[-1]["tool"], "PowerShell")

    # 5. A long command line is truncated so this log cannot itself become a context problem.
    run({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "session_id": "sess-1",
        "tool_input": {"command": "echo " + "a" * 500},
        "tool_response": {"stdout": ""},
    })
    check("long command is capped at 120 chars", len(rows()[-1]["trigger"]), 120)

print()
print(f"{'ALL PASS' if fails == 0 else f'{fails} FAILED'}")
