#!/usr/bin/env python3
"""Stop hook: a Workflow that produced repo-work must have written it INTO the repo.

WHY
---
The operator, 2026-07-20: *"new rule: workflows output repo-work to the repo."*

The cost that produced the rule is measured, not hypothetical. A ~3.3M-token fan-out
audit on 2026-07-19 found 19 "this exists in code but nothing consumes it" defects. Its
findings were **never written to any repo file** — they survived only inside a session
workflow artifact under ``~/.claude/projects/.../workflows/``. They were recovered on
2026-07-20 by parsing that artifact, one session before it would have been gone.

A conductor run is a Prestige cycle: the successor resets to zero and carries over
**only what is on disk in the repo**. Transcripts and session artifacts do not survive.
So an audit whose output stayed in the harness is an audit that was paid for and not
banked, and the failure is invisible at the time — the workflow *succeeded*, it reported
findings, and the orchestrator read them. Nothing signals that they evaporated.

WHY A HOOK RATHER THAN A LINE IN THE BRIEF
------------------------------------------
Workflow scripts have **no filesystem access** — they cannot write the repo themselves.
So the obligation necessarily lands on the orchestrator, after the workflow returns,
which is exactly the kind of "remember to do the thing afterwards" that prose does not
enforce. Same reasoning as requirement_before_mechanism.py: a rule satisfiable by
*saying* you followed it selects for the appearance of the behaviour.

WHAT IT DOES
------------
On Stop, if the turn used the Workflow tool and the repo is **unchanged**, block once
and name the rule.

EFFECT, NOT TOOL NAME (2026-07-22)
----------------------------------
Until now "did it write the repo?" was answered by scanning the parent transcript for
``Write``/``Edit`` tool_use blocks with a repo ``file_path``. That is a *proxy for* the
effect, and it was wrong in both directions:

  * FALSE POSITIVE — a workflow whose own Emit agent writes the report into the repo
    (the design of ``myproject-firmware/tools/workflows/tooling-opportunity.workflow.js``)
    really does satisfy the rule, but a subagent's write never appears in the parent's
    transcript, so the turn was blocked anyway. The workaround was to make the caller
    append an index line by hand — a voluntary step propped up by a guard, i.e. exactly
    the shape that workflow teaches you to distrust.
  * FALSE NEGATIVE — a parent that writes the repo through ``Bash`` (heredoc,
    ``python -c``, ``git apply``) is equally invisible. Same blind spot as
    repo_doc_guard: 62 Bash heredoc writes in one run went unobserved.

So the check now asks the filesystem: for each repo root in play, ``git status
--porcelain`` plus the HEAD commit time. A new/modified/deleted path (or a commit made
during this turn) satisfies it. That is satisfiable *only* by actually changing the
repo, no matter which tool did it — the transcript scan is kept merely as a free fast
path, never as the sole authority.

The change is scoped to **this turn** by mtime (and commit time) against the turn's
start timestamp, because a repo left dirty by an earlier turn must not silently satisfy
every later one — a guard that quietly stops guarding is the failure mode this hook
exists to prevent.

DESIGN TENSION — A DEAD METRIC MUST NOT TAKE A LIVE HOOK DOWN
-------------------------------------------------------------
The effect check costs a ``git`` subprocess per repo root on every Stop: single-digit
milliseconds, capped at MAX_ROOTS roots with a hard timeout. That cost is affordable.
What is NOT affordable is it *raising*. Every git call is wrapped and returns None on
any failure (git absent, repo locked by a concurrent index.lock, path vanished,
timeout, non-UTF8 output); a missing measurement degrades to "no evidence of a change",
never to a traceback that fails the Stop hook. The narrow guard stays narrow: if the
evidence cannot be gathered, the pre-existing transcript fast path and the
``workflow-output:ok`` escape hatch still decide the turn.

REPO_FRAGMENTS is machine-local CONFIGURATION, not a literal in this file -- see
``load_repo_fragments()`` below for why, and ``workflow-output-repos.conf.example``. It
is only a HINT, not the sole authority: any directory with a ``.git`` ancestor also
counts (see ``has_git_ancestor``), which is what lets a repo outside the configured list
(a fresh clone, a worktree under a different name) still satisfy the rule.

Deliberately narrow, because a guard that cries wolf gets disabled and takes its true
positives with it:
  * only the ``Workflow`` tool counts — a plain ``Agent`` subagent is exempt, since
    delegating a lookup is not the same as commissioning repo-work;
  * a change anywhere under a known repo root satisfies it — docs, reviews, TODO, source;
  * scratchpad/temp writes do NOT satisfy it (that is the failure mode itself);
  * fires at most ONCE per turn (honours stop_hook_active);
  * ``workflow-output:ok`` anywhere in the turn is the explicit escape hatch, for the
    genuine case where a workflow answered a throwaway question with no durable product.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# A write under one of these counts as "in the repo". Kept as path fragments so it works
# regardless of drive letter or checkout location. This list is only a HINT -- any
# directory with a .git ancestor also counts (see has_git_ancestor), which is what lets
# a repo outside the list (conductor-bs, a fresh clone) satisfy the rule.
#
# WHY THIS IS CONFIGURATION AND NOT A LITERAL IN THIS FILE
# -------------------------------------------------------
# The list is inherently machine-specific: it is *which repos this operator does durable
# work in*, which differs per box and names private projects. Hardcoding it here would
# either leak those names into a public repo or, if scrubbed, leave the hook matching
# nothing -- and a hook that matches nothing does not fail loudly, it silently stops
# recognising real repo writes and blocks every workflow turn instead. That silent
# mis-fire is the exact class of failure the rest of this file argues against.
#
# So: the MECHANISM ships here, the DATA lives next to the machine that knows it.
# One fragment per line in the config file, blank lines and `#` comments ignored.
# See workflow-output-repos.conf.example.
CONF_ENV = "WORKFLOW_OUTPUT_REPOS_CONF"        # override the config path (tests use this)
CONF_DEFAULT = "~/.claude/workflow-output-repos.conf"

# Used when no config file exists. Deliberately BROAD rather than empty: an empty list
# means "no write ever counts", which turns the guard into a blocker on every workflow
# turn. A checkout-directory fragment keeps it roughly right on an unconfigured box, and
# the operator narrows it by writing the config file.
FALLBACK_FRAGMENTS = ("/github/",)


def load_repo_fragments(conf_path: str | None = None) -> tuple[str, ...]:
    """Read durable-repo path fragments from machine-local config.

    Falls back to FALLBACK_FRAGMENTS when the file is absent or contains no entries,
    so an unconfigured machine still gets a working hook rather than a silent one.
    """
    path = conf_path or os.environ.get(CONF_ENV) or os.path.expanduser(CONF_DEFAULT)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return FALLBACK_FRAGMENTS
    frags = tuple(
        s.lower().replace("\\", "/")
        for s in (line.strip() for line in lines)
        if s and not s.startswith("#")
    )
    return frags or FALLBACK_FRAGMENTS


REPO_FRAGMENTS = load_repo_fragments()

# These never satisfy the rule even though they are real writes -- writing the findings
# to a temp file is precisely the thing that lost the audit.
NON_DURABLE = ("/scratchpad/", "\\scratchpad\\", "/temp/", "\\temp\\", "/tmp/", "\\tmp\\",
               "/appdata/local/temp/", "\\appdata\\local\\temp\\")

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
OVERRIDE = re.compile(r"workflow-output:\s*ok", re.I)

GIT_TIMEOUT = 5.0        # seconds per git call; a hung repo must not hang the Stop hook
MAX_ROOTS = 8            # bound the per-Stop cost regardless of how many paths appear
MTIME_SLACK = 5.0        # seconds of tolerance on the turn-start timestamp (clock skew)
# Env override, for tests: os.pathsep-separated repo roots, used INSTEAD of discovery.
ROOTS_ENV = "WORKFLOW_OUTPUT_REPO_ROOTS"

_PATH_STOP = set(" \t\r\n\"'`,;()[]{}<>|=*?")


def is_non_durable(path: str) -> bool:
    low = (path or "").lower().replace("\\", "/")
    return any(frag.replace("\\", "/") in low for frag in NON_DURABLE)


def has_git_ancestor(path: str) -> bool:
    """True if `path` sits inside a git repo (.git may be a dir or a worktree file)."""
    try:
        d = os.path.dirname(os.path.abspath(path))
        for _ in range(40):  # bounded: never walk forever on a pathological path
            if os.path.exists(os.path.join(d, ".git")):
                return True
            parent = os.path.dirname(d)
            if parent == d:
                return False
            d = parent
    except Exception:
        pass
    return False


def in_repo(path: str) -> bool:
    if not path:
        return False
    if is_non_durable(path):
        return False
    low = path.lower().replace("\\", "/")
    if any(frag in low for frag in REPO_FRAGMENTS):
        return True
    return has_git_ancestor(path)


def _to_epoch(stamp) -> float:
    """ISO-8601 (with or without trailing Z) -> epoch seconds. 0.0 if unparseable."""
    if not isinstance(stamp, str) or not stamp:
        return 0.0
    try:
        s = stamp.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def current_turn(transcript_path: str):
    """What happened since the last real user message.

    Returns (assistant_text, used_workflow, repo_paths_written, turn_start_epoch, blob).
    `blob` is the raw JSON of the turn's entries, used only to mine repo paths that never
    appear as a `file_path` (Bash commands, subagent prompts).
    """
    # Turn boundary from the shared window (excludes <task-notification> and other machine
    # markers); the old local loop reset the turn at a notification. The raw blob for mining
    # repo paths that never appear as a file_path (Bash commands, subagent prompts) is rebuilt
    # from the in-window entries — json.dumps preserves those embedded strings for the grep.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from turn_window import window
        entries, start = window(transcript_path)
    except Exception:
        return "", False, [], 0.0, ""

    turn_start = 0.0
    for e in entries[start:]:
        ts = _to_epoch(e.get("timestamp"))
        if ts:
            turn_start = ts
            break

    text_parts, used_workflow, written = [], False, []
    for e in entries[start:]:
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                name = block.get("name")
                if name == "Workflow":
                    used_workflow = True
                elif name in EDIT_TOOLS:
                    path = (block.get("input") or {}).get("file_path") or ""
                    if in_repo(path):
                        written.append(path)
    blob = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries[start:])
    return "\n".join(text_parts), used_workflow, written, turn_start, blob


def _mine_roots(blob: str):
    """Repo roots named anywhere in the turn -- including inside Bash command strings."""
    out = []
    if not blob:
        return out
    # Backslashes are doubled inside the transcript's JSON, so "C:\\Users\\..." becomes
    # "C://Users//..." after the naive replace and the fragments stop matching. Collapse
    # runs of slashes; `norm` and `low` are derived from the SAME string so the indices
    # used for slicing below stay valid.
    norm = re.sub(r"/{2,}", "/", blob.replace("\\", "/"))
    low = norm.lower()
    for frag in (f.replace("\\", "/") for f in REPO_FRAGMENTS):
        i = 0
        while True:
            j = low.find(frag, i)
            if j < 0:
                break
            i = j + 1
            k = j
            while k > 0 and low[k - 1] not in _PATH_STOP:
                k -= 1
            root = norm[k:j + len(frag) - 1]   # keep the fragment, drop its trailing "/"
            if root:
                out.append(root)
            if len(out) > 200:                 # pathological transcript; roots dedupe anyway
                return out
    return out


def fix_msys(p: str) -> str:
    """Git-Bash "/c/Users/..." -> "C:/Users/...". Bash commands in the transcript quote
    paths this way, and without the rewrite those roots silently resolve to nothing."""
    if os.name == "nt" and isinstance(p, str) and len(p) >= 3 \
            and p[0] == "/" and p[1].isalpha() and p[2] == "/":
        return p[1].upper() + ":" + p[2:]
    return p


def _git_root(path: str):
    try:
        d = os.path.abspath(fix_msys(path))
        if not os.path.isdir(d):
            d = os.path.dirname(d)
        for _ in range(40):
            if os.path.exists(os.path.join(d, ".git")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent
    except Exception:
        pass
    return None


def repo_roots(payload: dict, blob: str):
    """The repo roots to inspect, most-specific first. Never raises."""
    env = os.environ.get(ROOTS_ENV)
    if env:
        return [p for p in (x.strip() for x in env.split(os.pathsep)) if p][:MAX_ROOTS]

    candidates = []
    cwd = payload.get("cwd") or ""
    if cwd:
        candidates.append(cwd)
    candidates.extend(_mine_roots(blob))

    roots, seen = [], set()
    for cand in candidates:
        try:
            if is_non_durable(cand):
                continue
            root = _git_root(cand)
            if not root:
                continue
            key = os.path.normcase(os.path.realpath(root))
            if key in seen:
                continue
            seen.add(key)
            roots.append(root)
            if len(roots) >= MAX_ROOTS:
                break
        except Exception:
            continue
    return roots


def _git(root: str, *args):
    """Run git in `root`. Returns stdout (str) or None. NEVER raises -- a dead metric
    must not take a live hook down."""
    try:
        proc = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, timeout=GIT_TIMEOUT,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None


def repo_changed(root: str, since: float):
    """Did `root` gain a new/modified/deleted path (or a commit) during this turn?

    Returns a short human-readable reason, or None. `since` <= 0 disables the time
    scoping (unknown turn start -> accept any dirt rather than assert something false).
    """
    porcelain = _git(root, "status", "--porcelain", "-z",
                     "--untracked-files=all", "--no-renames")
    if porcelain is not None:
        for record in porcelain.split("\0"):
            if len(record) < 4:
                continue
            status, rel = record[:2], record[3:]
            # Non-durability is judged on the repo-RELATIVE path (a scratchpad/ or tmp/
            # subdir inside the repo). Whether the root itself is durable was already
            # decided in repo_roots(); re-testing the absolute path here would reject a
            # root an operator declared explicitly via ROOTS_ENV.
            if not rel or is_non_durable(rel):
                continue
            if "D" in status:
                return f"deleted {rel}"          # a real effect; no mtime to check
            if since <= 0:
                return f"changed {rel}"
            try:
                if os.path.getmtime(os.path.join(root, rel)) >= since - MTIME_SLACK:
                    return f"changed {rel}"
            except Exception:
                continue

    # A turn that wrote the repo and then COMMITTED leaves a clean tree -- the effect is
    # in the history, not the worktree. Without this, committing your work looks exactly
    # like never doing it.
    if since > 0:
        head = _git(root, "log", "-1", "--format=%ct")
        if head:
            try:
                if float(head.strip()) >= since - MTIME_SLACK:
                    return "commit on HEAD"
            except Exception:
                pass
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never break the session on a malformed payload

    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        return 0

    text, used_workflow, written, turn_start, blob = current_turn(transcript)
    if not used_workflow:
        return 0
    if written:
        return 0  # fast path: a parent-side repo write is proof enough, no git needed
    if OVERRIDE.search(text):
        return 0

    for root in repo_roots(payload, blob):
        if repo_changed(root, turn_start):
            return 0

    reason = (
        "This turn ran a Workflow but the repo is unchanged.\n\n"
        "RULE (the operator, 2026-07-20): workflows output repo-work to the repo.\n\n"
        "A run is a Prestige cycle -- the next agent carries over ONLY what is on disk "
        "in the repo. Transcripts and session artifacts do not survive. A 3.3M-token "
        "audit on 2026-07-19 found 19 real defects and banked none of them; they lived "
        "only in ~/.claude/projects/.../workflows/ and were recovered by luck one "
        "session later.\n\n"
        "This is an EFFECT check ('git status' under each repo root in play), not a "
        "tool-name check -- a write by a subagent, by Bash, or by 'git apply' all count. "
        "So does committing the work. If you believe you wrote the repo and still see "
        "this, the write did not land where you think it did.\n\n"
        "Do one of these before finishing:\n"
        "  - write the workflow's product to the repo (docs/reviews/<date>-<topic>.md "
        "for findings, docs/TODO.md for work items, or the source it changed);\n"
        "  - if the workflow answered a throwaway question with no durable product, say "
        "'workflow-output:ok' and why.\n\n"
        "A scratchpad or temp-file write does NOT count -- that is the failure mode."
    )
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.record("workflow_output_to_repo", trigger="workflow ran, repo unchanged",
                        transcript_path=transcript)
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
