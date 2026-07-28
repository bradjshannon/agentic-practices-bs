#!/usr/bin/env python3
"""PreToolUse(Bash) guard: block command shapes that return a plausible WRONG answer.

WHY A HOOK AND NOT A RULE
-------------------------
A rule in a doc shapes what an agent *writes*, not what it *does*. An agent that reads
"always verify a negative result" reliably learns to say "I verified this" — the surface
form of compliance — without the check necessarily happening. The rule is satisfiable by
narration, so it selects for the appearance of the behaviour.

A hook is not. It fires on the ACTION, before the command runs, and it works on an agent
that has never read this file. That is the test for a real mechanism versus theatre:
*does it still work on an unaware agent?*

Evidence it is needed: on 2026-07-19 an agent documented the `turn-pacer &` trap in a
brief and then repeated it FIFTEEN MINUTES LATER, in the same session, having written the
warning itself. Prose lost to habit at the moment of being busy. Every pattern below is
one that actually fired that night and produced a confident wrong conclusion.

SCOPE DISCIPLINE
----------------
Only patterns where the output is *actively misleading* — not merely inelegant. A guard
that cries wolf gets disabled, so false positives cost more here than misses. Each rule
must name the exact fix, because a block that does not say what to run instead just
converts one wrong turn into two.

Exit 2 blocks the call and shows stderr to the model. Exit 0 allows.
"""
import json
import re
import os
import sys


# Strip content that is DATA, not shell syntax: heredoc bodies, and single/double-quoted
# spans. Without this the guard reads a commit message that *describes* a trap as if it were
# performing it — writing "the &/nohup trap" in prose blocked the very commit documenting it,
# twice. A guard that punishes writing about its own patterns is one that gets disabled.
HEREDOC = re.compile(r"<<-?\s*'?(\w+)'?.*?^\1\s*$", re.S | re.M)
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"", re.S)


def shell_only(cmd: str) -> str:
    return QUOTED.sub(" ", HEREDOC.sub(" ", cmd))


# A payload handed to a NESTED shell (`pwsh -Command "…"`, `bash -c '…'`) is shell syntax that
# will execute — not data — so stripping it as a quoted string hides real commands from every
# rule below. That is not hypothetical: the idf.ps1 trap of 2026-07-19 arrived as
# `pwsh -NoProfile -Command ". .\idf.ps1; idf.py build"` and rule 5 did not see it at all until
# this was added (caught by testing the rule against the exact failing command, not a paraphrase).
#
# Deliberately narrow: it matches ONLY the -c/-Command flag forms. A quoted string that is mere
# data — `git commit -m "... . .\idf.ps1 ..."` — stays stripped, which is what keeps this from
# firing on commit messages and docs edits that merely DESCRIBE a bad command.
NESTED = re.compile(
    r"""(?:-c|-Command|--Command)\s+("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""",
    re.I | re.X,
)


def nested_payloads(cmd: str) -> str:
    return " ; ".join(m.group(1)[1:-1] for m in NESTED.finditer(cmd))


def check(cmd: str):
    """Return a list of (problem, fix) for a command string."""
    # Analyse the outer command with quoted DATA stripped, plus any nested-shell payloads
    # unwrapped — those are commands, not data. See NESTED above.
    # RAW is needed by the two instrument-lie checks below: their tell is inside a quoted
    # string (an ANSI-C quoted CR, a JSON payload), which shell_only() strips by design --
    # for every OTHER check, quoted text is data rather than command. Analysing both is
    # the point.
    # OTHER check quoted text is data rather than command. Analysing both is the point.
    raw = cmd
    cmd = shell_only(cmd) + " ; " + shell_only(nested_payloads(cmd))
    problems = []

    # 1. `$?` after a pipeline reports the LAST stage's status, not the command's.
    #    Cost that night: a working enforcement script looked like it exited 0 on FAIL,
    #    nearly filed as "the check does not work".
    if "$?" in cmd and "|" in cmd:
        before = cmd.split("$?")[0]
        if "|" in before:
            problems.append((
                "`$?` after a pipeline reports the LAST pipeline stage (often `tail`/`head`), "
                "NOT the command you care about.",
                "Run the command unpiped and then echo $?, or use ${PIPESTATUS[0]}.",
            ))

    # 2. Detaching the turn pacer kills it silently: the background TASK exits at once, the
    #    completion notification fires in ~1s, and the pacer looks armed while being dead.
    # Match a BACKGROUNDING `&` only: one not part of `&&`. The first version tested for a
    # bare "&" in the command and fired on `cp turn-pacer.py … && git commit …` — a false
    # positive on a command that never launched the pacer at all. A guard that cries wolf
    # gets disabled and takes its true positives with it, so this is the expensive kind of
    # miss.
    # A NEWLINE terminates a backgrounded command too. The first version required the
    # `&` to be followed by end-of-string, `;` or `|`, so a multi-line compound like
    #     python ~/.claude/turn-pacer.py --label "x" > /dev/null 2>&1 &
    #     echo "next"; git log
    # slipped straight through — the `&` is followed by "\necho", which matched none of
    # them. Observed 2026-07-20: the conductor launched a detached pacer this exact way
    # and the guard stayed silent, which is the miss that costs most (a pacer that never
    # fires looks identical to one that is armed).
    detached = re.search(r"(?<!&)&(?!&)\s*(?:$|[;|\n])", cmd) or "nohup" in cmd
    if "turn-pacer.py" in cmd and detached:
        if re.search(r"turn-pacer\.py[^;|]*?(?<!&)&(?!&)", cmd) or "nohup" in cmd:
            problems.append((
                "turn-pacer launched detached (`&`/`nohup`). The sleeping process must BE the "
                "background task — detaching makes it exit instantly and the pacer is silently "
                "dead while appearing armed.",
                "Run it as its OWN call with run_in_background:true and no `&`, no `nohup`, "
                "and not appended to another command.",
            ))

    # 3. Filtering context-usage.py's own output drops the provenance that carries the
    #    meaning — the resolved `[window=...]` tag. (Originally it printed both pct_of_1M
    #    and pct_of_200k and a `tail -3` kept the wrong one, costing half a run of false
    #    austerity. It now resolves the window from the model, so the surviving risk is
    #    losing that tag, not keeping the wrong line.)
    #
    #    NARROWED 2026-07-22 after two false positives in ONE run: the old test was
    #    `"context-usage" in cmd` AND a pipe ANYWHERE in cmd, so it fired on
    #    `grep -n window ~/.claude/context-usage.py | head` (reading the SOURCE, not running
    #    it) and on `python turn-pacer.py | tail -8; python context-usage.py` (the filter
    #    belonged to a different command entirely). A guard that cries wolf gets routed
    #    around and takes its true positives with it — so the pipe must attach to THIS
    #    invocation, in the same shell segment, with the script actually being EXECUTED.
    for segment in re.split(r"[;\n]|&&|\|\|", cmd):
        m = re.search(r"(?:python\w*|py)\b[^|]*context-usage(?:\.py)?\b", segment)
        if m and re.search(r"\|\s*(tail|head|grep|sed|awk|findstr)\b", segment[m.end():]):
            problems.append((
                "Filtering context-usage.py's output drops the `[window=...]` provenance — "
                "the field saying WHICH context window the percentage is against. A "
                "percentage without its window caused half a run of false context austerity.",
                "Run it unfiltered; it is one short line.",
            ))
            break

    # 4. `cd X && git ...` — the shell cwd does not persist reliably between calls here, so a
    #    compound cd can report on the WRONG repo while looking authoritative.
    if re.search(r"\bcd\s+\S+.*&&.*\bgit\s+(log|status|show|diff)\b", cmd):
        problems.append((
            "`cd ... && git ...` can report on the wrong repository — the shell cwd resets "
            "between calls, and the output looks authoritative either way.",
            "Use `git -C <path> ...` so the target is explicit.",
        ))

    # 5. `. .\idf.ps1; idf.py ...` — idf.ps1 is a WRAPPER that invokes idf.py with your args,
    #    NOT an env script to dot-source. Dot-sourcing runs idf.py with NO args, prints the
    #    help, and EXITS 0 having built nothing; a background runner then reports "completed"
    #    and the stale build/ output reads as a successful build. Cost two build cycles on
    #    2026-07-19 and was only caught by the unchanged iotta_firmware.bin size.
    #    Match the dot-source specifically — a bare `idf.py` inside an already-exported IDF
    #    shell is legitimate and must NOT fire.
    if re.search(r"(^|[;&|]|\s)\.\s+[^\s;|&]*idf\.ps1", cmd) and re.search(r"\bidf\.py\b", cmd):
        problems.append((
            "`. idf.ps1` then `idf.py` — idf.ps1 is a WRAPPER around idf.py, not an env script. "
            "Dot-sourcing it runs idf.py argless, prints the help and EXITS 0 while building "
            "NOTHING; the runner still reports success and the stale build/ output looks fresh.",
            "Call the wrapper directly: `.\\idf.ps1 build` / `.\\idf.ps1 -p COM7 app-flash`. "
            "Then confirm the build really happened by comparing build/iotta_firmware.bin size "
            "before and after — never trust the exit code.",
        ))

    # N. Counting CR bytes through a Git Bash pipe. MSYS applies text-mode translation on the
    #    way through, so the count is fabricated -- in BOTH directions. Observed 2026-07-26,
    #    twice in one investigation: `grep -c $'\r'` reported clean LF blobs as "225 CRLF lines"
    #    and then reported a correctly-fixed worktree as still broken. A whole diagnosis was
    #    built on the first number and a working fix was nearly reverted on the second.
    if re.search(r"grep\b[^;|&]*\$'\\r'", raw):
        problems.append((
            "Counting CR/CRLF with grep in Git Bash: MSYS translates line endings through the "
            "pipe, so the number is fabricated -- it has reported clean LF files as CRLF and "
            "correctly-fixed files as broken, in the same session.",
            "Read the bytes in Python: "
            "python -c \"import pathlib;print(pathlib.Path(r'FILE').read_bytes().count(b'\\r\\n'))\"",
        ))

    # N+1. A Git-Bash-style /c/... path inside a JSON string. MSYS translates paths that appear
    #      as ARGV, but never text inside a quoted JSON payload, so the receiving Python sees a
    #      path that does not exist on Windows -- and a hook or tool that fails open then looks
    #      like it PASSED. Observed 2026-07-26: a hook under test printed nothing and read as
    #      "silent, therefore fine"; it had simply never found the transcript. The same shape
    #      that makes `--dry-run` prove nothing.
    if re.search(r'\\?"\s*:\s*\\?"/[a-z]/[A-Za-z]', raw):
        problems.append((
            "A Git Bash `/c/...` path embedded in a JSON string. MSYS rewrites paths in argv but "
            "NOT inside JSON, so the program receives a path Windows cannot resolve. Anything "
            "that fails open then prints nothing and reads as a PASS.",
            "Build the payload in Python so the path is native: "
            "python - <<'PY' … json.dumps({'transcript_path': str(pathlib.Path(...))}) … PY  "
            "-- and assert a POSITIVE control (a case that MUST produce output) in the same run.",
        ))

    # N. A conductor WRITER tool carrying `…` or $(…) inside DOUBLE quotes. The shell runs
    #    the substitution before the tool ever sees the argument, so the words vanish and
    #    what lands in front of Brad is a sentence with a hole in it. Nothing errors: the
    #    tool prints its usual "replied on <thread>", the JSONL line is written, and the
    #    corruption is only visible by reading the stored text back.
    #
    #    Observed 2026-07-28: a reply explaining a diagnostic field was posted as
    #    "… `cause` also takes `telemetry_suppressed` …" and STORED as
    #    "… also takes  (the device saying, …" -- three clauses lost their subject, and
    #    bash printed `cause: command not found` into the middle of an unrelated tool's
    #    output where it read like that tool's own noise. Backticks in prose are the norm
    #    when the prose is about code, so this will recur for as long as it is possible.
    #
    #    Deliberately NOT flagged: single quotes. `'…`…'` is safe -- the shell does not
    #    substitute inside them -- and flagging it would make the guard cry wolf on the
    #    correct form, which is how a guard gets disabled and takes its true positives with
    #    it. So this walks RAW tracking quote state and fires only on a substitution that
    #    is genuinely live (inside double quotes, or unquoted).
    if re.search(r"\b(reply|note-find|note-review|name-thread|mark-active|mark-msg)\.py\b", raw):
        state, live = None, False   # state: None | "'" | '"'
        i = 0
        while i < len(raw):
            ch = raw[i]
            if state is None and ch in "'\"":
                state = ch
            elif state is not None and ch == state:
                state = None
            elif state != "'" and (ch == "`" or raw.startswith("$(", i)):
                live = True
                break
            i += 1
        if live:
            problems.append((
                "A status-page writer tool is being called with a backtick or $(...) that the "
                "SHELL will execute first. The substituted words are deleted from the message "
                "before the tool sees them -- the tool still reports success, and the corruption "
                "is visible only by reading the stored text back. Brad reads the corrupted "
                "version.",
                "Pass the text without live substitution: single-quote the argument, or (better, "
                "since the prose usually contains apostrophes too) build it in Python and call "
                "the tool via subprocess with an argv LIST -- "
                "python - <<'PY' ... subprocess.run([sys.executable, 'tools/reply.py', thread, msg]) ... PY  "
                "Then read the last line of the JSONL back and assert the text is intact.",
            ))

    return problems


# Escape hatch. Every block MUST be overridable, or the guard becomes a wall rather than a
# seatbelt and the first false positive gets the whole hook disabled — taking its true
# positives with it. Two properties matter:
#   * it lives IN the command, so the override is recorded in the transcript and is
#     auditable after the fact, unlike an env var set once and forgotten;
#   * it is deliberate to type, so it cannot be reached by reflex.
OVERRIDE = re.compile(r"#\s*guard:\s*ok\b", re.I)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a malformed payload

    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    if OVERRIDE.search(cmd):
        return 0  # explicitly overridden; the token is the audit record

    problems = check(cmd)
    if not problems:
        return 0

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("lying_command_guard", trigger=(cmd or "")[:120])
    except Exception:
        pass
    print("Blocked: this command shape returns a plausible WRONG answer.\n", file=sys.stderr)
    for problem, fix in problems:
        print(f"  - {problem}\n    FIX: {fix}\n", file=sys.stderr)
    print("OVERRIDE: append `# guard:ok` to the command to run it anyway.\n", file=sys.stderr)
    print("(~/.claude/hooks/lying_command_guard.py — each pattern is one that produced a "
          "confident wrong conclusion in a real run.)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
