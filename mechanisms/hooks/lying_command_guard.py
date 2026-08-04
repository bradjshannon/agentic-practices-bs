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

    # 4b. A bare `cd <dir>` whose result is never checked, with more commands following that
    #     assume it worked. `cd` can fail silently (typo, a directory not yet created because
    #     an earlier command in the same turn never ran) and the shell just keeps executing
    #     the rest of the script in the OLD cwd -- no error, no pause, nothing distinguishing
    #     "cd worked" from "cd silently failed" until whatever runs next either breaks loudly
    #     or, worse, succeeds quietly against the wrong directory.
    #     Observed 2026-08-03: `mkdir conductor-pub` (in a command blocked before it ran) then,
    #     in the NEXT command, `cd conductor-pub` / `git init` / `cat > README.md` / more --
    #     four separate statements, no `&&`/`||` anywhere. The directory did not exist yet, cd
    #     failed, and everything after ran against whatever repo happened to be cwd -- a
    #     DIFFERENT real project, whose README.md and docs/decisions.md were overwritten.
    #     Caught only by reading `git diff` afterward, not by anything at the point of damage.
    #     This is rule 4's failure mode one step earlier: that rule catches `cd X && git ...`
    #     specifically; this one catches the un-chained cd itself, for any command, so the
    #     agent has a chance to react to the failure instead of finding out from a later diff.
    for m in re.finditer(r"\bcd\s+(?:--\s+)?(\S+)", cmd):
        target = m.group(1)
        if target in ("-", ".", ".."):
            continue  # returning to known-good ground, not entering unverified new ground
        after = cmd[m.end():]
        if re.match(r"\s*(&&|\|\|)", after):
            continue  # chained: a failed cd either skips what follows or hits a fallback
        remainder = re.split(r"[;\n]", after, maxsplit=1)
        tail_same_line = remainder[0]
        more_after = remainder[1] if len(remainder) > 1 else ""
        if not tail_same_line.strip() and not more_after.strip():
            continue  # cd is the last thing in the command; nothing depends on it
        problems.append((
            "`cd <dir>` result is never checked, and more commands follow assuming it "
            "worked. A failed cd (typo, or a directory another command was supposed to "
            "create first) leaves the shell in the OLD cwd with no error -- everything "
            "after silently runs against the wrong directory. This overwrote a different "
            "project's README.md and docs/decisions.md on 2026-08-03.",
            "Chain the very next step so a failure stops the block: `cd <dir> && <next>`, "
            "or check explicitly: `cd <dir> || { echo cd failed; exit 1; }`. Better still, "
            "skip cd entirely -- pass the path explicitly to each command instead "
            "(`git -C <dir> ...`, absolute paths for file writes) so nothing depends on "
            "shell state carrying over at all.",
        ))
        break  # one report per command is enough; don't pile on for every cd in a script

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
        # A QUOTED heredoc body is inert: `<<'PY'` and `<<"PY"` both disable every
        # expansion inside, so a backtick there is literal text. Only a BARE `<<PY`
        # expands. Strip quoted-heredoc bodies before walking, or this fires on the
        # exact form the fix text recommends -- and a guard that cries wolf on the
        # correct form is how it gets switched off, taking its true positives with it.
        # (Caught the day it was written: the first status-page reply written the
        # recommended way was blocked by its own guard.)
        scan = re.sub(
            r"<<-?\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
            "<<HEREDOC_ELIDED",
            raw,
            flags=re.S | re.M,
        )
        state, live = None, False   # state: None | "'" | '"'
        i = 0
        while i < len(scan):
            ch = scan[i]
            if state is None and ch in "'\"":
                state = ch
            elif state is not None and ch == state:
                state = None
            elif state != "'" and (ch == "`" or scan.startswith("$(", i)):
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

    # N. A raw `git commit`. The COMPOSITE of commit-then-push lies even though every
    #    individual exit code is correct: on 2026-07-29 a message containing an escaped
    #    regex was parsed as a pathspec, the commit FAILED, the following `git push`
    #    printed reassuring output, and the pair read exactly like success. Only
    #    `git show HEAD:<file>` found the change still sitting in the index. The same
    #    shape also sweeps a concurrent agent's staged paths into your commit -- seven
    #    times in one project -- because `git add` reports nothing about what else was
    #    already staged.
    #
    #    commit_verify.py exists and verifies the POSTCONDITIONS (paths staged and
    #    nothing else; HEAD moved; HEAD's tree really contains each path; remote ref
    #    equals HEAD). Nothing made anyone use it, and "I'll remember to" is the
    #    Voluntary class -- the one the enforcement table says reliably decays. So the
    #    reminder moves to the action, where it also reaches a subagent that has read
    #    no brief. The block text is therefore the whole teaching moment and must be
    #    self-contained.
    #
    #    THREE DELIBERATE LIMITS, each so the guard cannot cry wolf:
    #      * It fires ONLY if commit_verify.py is actually resolvable on this machine,
    #        so a block always names a command that exists. The guard's own rule is that
    #        a block naming no valid replacement converts one wrong turn into two.
    #      * `--amend` is EXEMPT. commit_verify cannot express an amend, so blocking one
    #        would leave nothing to recommend.
    #      * `commit` must be git's SUBCOMMAND token, found by walking argv past git's
    #        global options -- not a substring. `git commit-graph`, `git commit-tree`,
    #        `git log --grep=commit` and `git show`/`status` must all pass through. This
    #        is the trap the flash gate hit with `flash` inside `app-flash`.
    #    Push is intentionally NOT blocked: a bare push of work committed earlier is
    #    legitimate, and push verification comes along free when commit_verify commits.
    if "commit_verify" not in raw:
        script = commit_verify_path()
        if script:
            # Quoted spans collapse to a single placeholder TOKEN rather than to
            # whitespace here. shell_only() blanks them, which would turn
            # `git -C "C:/a b" commit` into `git -C   commit` and make -C swallow the
            # word `commit` -- a silent miss on exactly the quoted-path form that is
            # normal on Windows. A placeholder keeps the argv shape intact while still
            # hiding quoted DATA (`echo "git commit is bad"` stays a no-fire).
            argvish = (QUOTED.sub(" Q ", HEREDOC.sub(" ", raw)) + " ; "
                       + QUOTED.sub(" Q ", nested_payloads(raw)))
            for segment in re.split(r"[;\n]|&&|\|\|", argvish):
                if _git_subcommand(segment) != "commit":
                    continue
                if re.search(r"(?<![\w-])--amend(?![\w-])", segment):
                    continue
                # Read the repo path out of RAW, not out of `argvish` -- the placeholder
                # substitution above turns a quoted path into the literal token `Q`, and
                # the first live block printed `--repo Q`. A block message that names a
                # command with a WRONG argument is worse than no block, so this is read
                # from the untouched text and unquoted by hand.
                m = re.search(r"\bgit\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)", raw)
                repo = m.group(1).strip("\"'") if m else "<repo>"
                problems.append((
                    "Raw `git commit`. The commit can FAIL while the surrounding sequence "
                    "still reads as success -- a message parsed as a pathspec, a hook "
                    "rejection, an empty index -- and the `git push` after it then pushes "
                    "nothing and prints reassuring output. Every exit code is correct for "
                    "its own command; the COMPOSITE is what lies. `git add` also stages "
                    "silently alongside whatever a concurrent agent already staged.",
                    "Use commit_verify.py, which fails loudly unless it has OBSERVED: the "
                    "named paths staged and nothing else, HEAD moved, HEAD's tree really "
                    "containing each path, and (with --push) origin equal to HEAD --\n"
                    f"      python {script} --repo {repo} \\\n"
                    "        --path <file> --path <file> <<'MSG'\n"
                    "      your commit message\n"
                    "      MSG\n"
                    "    The message arrives on stdin, so backticks/quotes/backslashes in "
                    "prose can never be reparsed as arguments. Paths are explicit -- no "
                    "wildcards, ever. Add --push only when you mean to push; add "
                    "--allow-extra-staged only if you are certain the extra paths are yours. "
                    "For an amend, a rebase fixup or anything it cannot express, append "
                    "`# guard:ok`.",
                ))
                break

    # N. A hand-rolled write to a conductor's pins.jsonl. This is the exact shape that
    #    produced a stale thread pin on 2026-08-03: `written_at` typed by hand (wrong, missing,
    #    or copy-pasted stale), a field name typo invisible to the writer but invisible to the
    #    resolver too, and no verification that the pin now reads fresh against the real inbox.
    #    tools/pin-thread.py exists specifically to make those three failures structurally
    #    impossible (real timestamp, correct fields, self-verifying write) -- see its docstring.
    #    Match on the filename plus an append/write shape, not on "pins.jsonl" alone, so a
    #    command that merely READS the file (grep, cat, python -c "print(open(...).read())")
    #    is not blocked -- only something that looks like it is constructing a JSON line by
    #    hand and appending it.
    # Checked against BOTH the stripped `cmd` and the untouched `raw`: a heredoc body (the
    # realistic vector -- `python - <<'PY' ... PY`) is stripped by HEREDOC as "probably prose"
    # for every other rule, which would make this one blind to the exact shape that caused the
    # 2026-08-03 incident. The tradeoff this accepts: a heredoc/commit-message that merely
    # DESCRIBES this pattern in prose could false-positive here where other rules would not --
    # judged acceptable because the fix (`# guard:ok`) is one token and this failure mode is
    # narrow (pins.jsonl specifically, not a general string).
    def _pins_write_shape(text: str) -> bool:
        if not re.search(r"pins\.jsonl", text):
            return False
        return bool(
            re.search(r"pins\.jsonl['\"]?\s*,\s*['\"]a", text)          # open(path, "a"...)
            or re.search(r">>\s*['\"]?[^|;]*pins\.jsonl", text)          # shell append redirect
            or re.search(r"json\.dumps", text)                          # building the JSON by hand
            or re.search(r"Add-Content|Out-File\s+-Append", text, re.I)  # PowerShell append
        )

    if (_pins_write_shape(cmd) or _pins_write_shape(raw)) and "pin-thread.py" not in raw:
            problems.append((
                "Hand-rolled write to pins.jsonl. This is the exact shape that produced a "
                "stale thread pin on 2026-08-03 -- a hand-typed (or omitted) `written_at`, "
                "a field-name typo the resolver silently ignores, and no check that the pin "
                "now actually reads as fresh.",
                "Use tools/pin-thread.py, which always writes a real current timestamp in the "
                "exact form the resolver expects, uses the correct field set, and re-reads the "
                "file afterward to confirm the thread now verifies NOT STALE against the live "
                "inbox before it reports success --\n"
                "      python tools/pin-thread.py <thread> \"<state, 1-3 sentences>\"\n"
                "    Use `python tools/pin-thread.py --check <thread>` to see a verdict without "
                "writing anything. For a one-off migration or test fixture that genuinely needs "
                "a raw line, append `# guard:ok`.",
            ))

    return problems


# git's own global options, the ones that take a VALUE. Needed so `git -C <path> commit`
# and `git -c user.name=x commit` resolve to the subcommand `commit` rather than to the
# option's argument.
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                          "--exec-path", "--super-prefix"}


def _git_subcommand(segment: str):
    """Return git's subcommand token in this shell segment, or None.

    Tokenising rather than substring-matching is the whole point: `git commit-graph`,
    `git log --grep=commit` and `git show` all contain the letters `commit` somewhere,
    and none of them creates a commit.
    """
    toks = segment.split()
    try:
        i = next(n for n, t in enumerate(toks)
                 if t == "git" or t.endswith("/git") or t.endswith("\\git")) + 1
    except StopIteration:
        return None
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            if t in _GIT_GLOBAL_WITH_VALUE:
                i += 2
            else:
                i += 1
            continue
        return t
    return None


def commit_verify_path():
    """Locate commit_verify.py, or None if this machine has no copy.

    A module-level function so the rule can be exercised in BOTH directions by a test
    that swaps it out — the "script not reachable, so do not fire" branch is exactly the
    one that would otherwise never be demonstrated.
    """
    env = os.environ.get("COMMIT_VERIFY")
    if env and os.path.isfile(env):
        return env
    home = os.path.expanduser("~")
    for cand in (
        os.path.join(home, ".claude", "scripts", "commit_verify.py"),
        os.path.join(home, "Documents", "GitHub", "agentic-practices-bs",
                     "mechanisms", "scripts", "commit_verify.py"),
    ):
        if os.path.isfile(cand):
            return cand
    return None


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
