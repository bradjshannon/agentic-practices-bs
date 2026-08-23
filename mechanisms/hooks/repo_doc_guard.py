#!/usr/bin/env python3
"""PreToolUse guard — orient before editing.

Blocks Write/Edit/MultiEdit/NotebookEdit on a file inside a git repo until that repo's
CLAUDE.md / AGENTS.md have been Read *this session*. Enforced by Claude Code (the harness
runs it, the model cannot skip it).

Design contract:
  - FAIL-OPEN on any script error: a bug in this guard must NEVER block all editing. Any
    unexpected exception -> exit 0 (allow).
  - FAIL-CLOSED on the rule: if the repo has guidance docs and they weren't read, deny.
  - "Was it read?" is verified from the session TRANSCRIPT (the Read tool-uses), so there is
    no state file to write, cache, or clean up.

Reads hook input as JSON on stdin: {tool_input:{file_path|notebook_path}, transcript_path, ...}
"""
import sys, os, json, glob

# "any"  -> reading at least one guidance doc satisfies the gate (default: in these repos
#           one doc is canonical per scope and cross-references the other, so reading either
#           orients you — e.g. an AGENTS.md that just points at CLAUDE.md).
# "all"  -> every guidance doc that exists in the repo root must have been read.
REQUIRE = "any"
DOC_NAMES = ("CLAUDE.md", "AGENTS.md")


def allow():
    sys.exit(0)


def _log(trigger, transcript_path=None, repo_root=None, agent_id=None, extra=None):
    # agent_id is logged on every event. Without it the 2026-07-27 workflow-agent denies could
    # not be attributed to an actor -- four fires, one victim, and the log could not say which
    # of ~20 concurrent agents it was. An unattributable fire is half a datum.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        row = {"repo": os.path.basename(repo_root) if repo_root else None,
               "agent_id": agent_id}
        if extra:
            row.update(extra)
        hook_log.record("repo_doc_guard", trigger=str(trigger)[:120],
                        transcript_path=transcript_path, extra=row)
    except Exception:
        pass


def deny(reason, transcript_path=None, repo_root=None, subagent_likely=False, agent_id=None):
    # transcript_path is what hook_log derives the SESSION from. Omitting it logged
    # `"session": null` on every fire, which made hook_rollup report this hook's 32 fires --
    # the loudest signal in the event log -- as `unknown 32, sessions 0`: it could not
    # correlate any of them with what the agent did next, so the guard's true-positive rate
    # was unmeasurable for its entire life. Found 2026-07-22 by finally RUNNING the rollup
    # that was built 27h earlier and never read.
    # The 120-char trigger truncation cut off the repo path -- the one field that attributes
    # a fire -- so 41 logged fires could not be told apart by repo. Same shape as a `tail`
    # that drops the disambiguating line. `repo` is logged as its OWN field, never inside
    # truncatable prose.
    _log(reason, transcript_path=transcript_path, repo_root=repo_root, agent_id=agent_id,
         extra={"subagent_likely": subagent_likely})
    if subagent_likely:
        # A BLOCK MUST NAME A REPLACEMENT THAT ACTUALLY WORKS. For a subagent this hook is
        # handed the PARENT session's transcript (measured 2026-07-22: every deny raised
        # during a subagent's run logged the parent's session id, never the subagent's), so
        # the subagent's own Reads are invisible here and "Read it, then retry" is advice
        # that CANNOT succeed. Two agents hit exactly this the day before: one stopped and
        # asked, one routed around it with direct shell writes and called it bookkeeping.
        # The bypass is the guard's fault, not the agent's -- a guard whose stated remedy
        # does not work teaches that guards are obstacles.
        reason += (
            "\n\nNOTE FOR A SUBAGENT: reading it YOURSELF now clears this gate — since "
            "2026-07-22 the check keys on the ACTING agent's own transcript, not the parent "
            "session's. If you are a delegated agent, Read the named file and retry; that is "
            "the whole remedy. (Before that fix it was keyed session-wide, so a subagent could "
            "never satisfy it and two agents worked around it with shell writes. If Read-then-"
            "retry still fails, that is a REGRESSION — stop and report it rather than routing "
            "around, and say which file and which agent_id.)"
        )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def fix_msys(p):
    # On Windows, tolerate Git-Bash-style paths ("/c/Users/..." -> "C:/Users/...") so the
    # guard works no matter which shell produced the path. No-op for native paths and on
    # non-Windows (guarded by os.name so a real POSIX "/a/b" is never rewritten).
    if os.name == "nt" and isinstance(p, str) and len(p) >= 3 \
            and p[0] == "/" and p[1].isalpha() and p[2] == "/":
        return p[1].upper() + ":" + p[2:]
    return p


def norm(p):
    p = fix_msys(p)
    try:
        return os.path.normcase(os.path.realpath(p))
    except Exception:
        return os.path.normcase(os.path.abspath(p))


def find_repo_root(start_dir):
    d = start_dir
    while True:
        if os.path.exists(os.path.join(d, ".git")):  # dir (repo) or file (worktree)
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _walk_for_reads(node, out):
    if isinstance(node, dict):
        if node.get("name") == "Read":
            inp = node.get("input")
            if isinstance(inp, dict):
                fp = inp.get("file_path")
                if isinstance(fp, str) and fp:
                    out.add(norm(fp))
        for v in node.values():
            _walk_for_reads(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_for_reads(v, out)


def _transcript_has_agent_dispatch(transcript_path):
    """Did this session ever dispatch a subagent? Cheap substring scan, best-effort."""
    if not transcript_path:
        return False
    try:
        with open(fix_msys(transcript_path), "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"name": "Agent"' in line or '"name":"Agent"' in line:
                    return True
    except Exception:
        pass
    return False


def actor_transcript(data):
    """The transcript of the ACTOR making this call — the subagent's own, if it is one.

    PER-AGENT KEYING (the intent the operator confirmed: "every actor that edits must itself have read
    the conventions"). Until 2026-07-22 this guard read `transcript_path`, which for a
    delegated agent is the PARENT session's file. That is wrong in both directions:

      * FALSE DENY  — a subagent that DID read is blocked, because its reads are in its own
        transcript, which was never opened. Visible and infuriating; two agents hit it, and one
        responded by making its edits through PowerShell and calling it bookkeeping. A guard
        whose stated remedy cannot work teaches that guards are obstacles.
      * FALSE ALLOW — a subagent that NEVER read is admitted because the parent read once.
        Silent. **This is the more serious half**: the guard stops protecting and nothing says so.

    The payload was assumed not to identify the actor. It does — measured by instrumenting this
    hook and running one throwaway subagent against it. The real keys are:
        agent_id, agent_type, cwd, hook_event_name, permission_mode, prompt_id,
        session_id, tool_input, tool_name, tool_use_id, transcript_path
    `agent_id` is present exactly when a delegated agent is acting, and its transcript sits at
    `<projects>/<slug>/<session_id>/subagents/agent-<agent_id>.jsonl`. So the information was
    there the whole time and the guard was reading the wrong file — worth stating plainly,
    because "the payload doesn't tell us who is acting" was a NEGATIVE assumption that pruned
    the search and was never checked.

    The flat path is not the only layout. Workflow-orchestrated (Claude Agent SDK-spawned)
    agents write their transcripts one level deeper:
        <session>/subagents/workflows/<wf_runId>/agent-<agent_id>.jsonl
    Measured 2026-07-27 after four denies against a workflow agent that had Read the repo's
    CLAUDE.md three times: the flat candidate did not exist, so this function silently fell
    back to the PARENT transcript — recreating the exact false-deny mode the 2026-07-22 fix
    was for, with the same "remedy that cannot succeed" message. The fallback-to-parent was
    the bug: for an actor with an agent_id, the parent transcript is always the WRONG file,
    so "fall back" meant "deny for an unfixable reason". Hence the contract below.

    Returns:
      * the actor's own transcript path when it can be located (flat first, then a recursive
        glob under subagents/ so future nesting schemes are found without another regression);
      * the parent transcript when there is no agent_id (the top-level session is the actor);
      * None when the actor HAS an agent_id but no transcript can be found anywhere — the
        caller must FAIL OPEN on None (allow, log), never substitute the parent's file.
    """
    parent = fix_msys(data.get("transcript_path") or "")
    agent_id = data.get("agent_id")
    if not agent_id or not parent:
        return parent
    session_dir = os.path.splitext(parent)[0]  # <session>.jsonl -> <session>/
    candidate = os.path.join(session_dir, "subagents", f"agent-{agent_id}.jsonl")
    if os.path.exists(candidate):
        return candidate
    matches = glob.glob(os.path.join(session_dir, "subagents", "**",
                                     f"agent-{agent_id}.jsonl"), recursive=True)
    if matches:
        return sorted(matches)[0]  # agent ids are unique; sort only for determinism
    return None


def collect_read_paths(transcript_path):
    out = set()
    if not transcript_path:
        return out
    transcript_path = fix_msys(transcript_path)
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"Read"' not in line:      # cheap prefilter before JSON parse
                    continue
                try:
                    _walk_for_reads(json.loads(line), out)
                except Exception:
                    continue
    except Exception:
        pass
    return out


def main():
    data = json.loads(sys.stdin.read())
    try:
        # So a crash further down (caught by the __main__ fail-open below) can still name the
        # session and the tool call it was adjudicating -- deny()/_log() already resolve the
        # session this way; the fail-open path had no equivalent until now.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hook_log
        hook_log.bind(data)
    except Exception:
        pass
    tin = data.get("tool_input") or {}
    target = tin.get("file_path") or tin.get("notebook_path")
    if not target:
        allow()

    target_abs = norm(target)
    repo_root = find_repo_root(os.path.dirname(target_abs) or target_abs)
    if not repo_root:
        allow()  # not inside a git repo -> nothing to orient in

    docs = []
    for name in DOC_NAMES:
        p = os.path.join(repo_root, name)
        if os.path.exists(p):
            docs.append((name, norm(p)))
    if not docs:
        allow()  # repo has no guidance docs

    if any(target_abs == dp for _, dp in docs):
        allow()  # editing the guidance doc itself is fine

    actor_path = actor_transcript(data)
    if actor_path is None:
        # A delegated agent is acting but its transcript is nowhere under the session dir, so
        # "did it read the docs?" is unanswerable. FAIL-OPEN per the design contract: denying
        # here would hand the actor a remedy (Read-then-retry) that cannot work, which is how
        # agents learn to route around guards. Logged so the blind spot stays visible.
        _log("fail-open: actor transcript unlocatable",
             transcript_path=data.get("transcript_path"), repo_root=repo_root,
             agent_id=data.get("agent_id"), extra={"event": "fail_open"})
        allow()

    read = collect_read_paths(actor_path)
    unread = [name for name, dp in docs if dp not in read]

    satisfied = (len(unread) < len(docs)) if REQUIRE == "any" else (len(unread) == 0)
    if satisfied:
        allow()

    unread_paths = ", ".join(os.path.join(repo_root, n) for n in unread)
    deny(
        "Orientation gate: read this repo's guidance before creating or editing files in it. "
        f"Unread: {unread_paths}. Use the Read tool on each, then retry the edit. "
        "This enforces reading a repo's CLAUDE.md/AGENTS.md before working in it.",
        transcript_path=data.get("transcript_path"),
        repo_root=repo_root,
        # Deliberately a WEAK signal used only to append a CONDITIONALLY-worded note ("if you
        # are a delegated agent"). A subagent's tool call is indistinguishable from the
        # parent's in this payload, so anything stronger would be a claim the data does not
        # support -- and a hook asserting something false is worse than one saying nothing.
        subagent_likely=_transcript_has_agent_dispatch(data.get("transcript_path")),
        agent_id=data.get("agent_id"),
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as _exc:
        # FAIL-OPEN: never block editing because the guard broke. But a broken guard and an
        # absent guard must not be indistinguishable from outside -- record the crash to the
        # SAME sink deny() writes to, distinctly from a deny (2026-08-13: an incomplete
        # agent-registry fixture made a revive_before_dispatch positive fail open silently;
        # this is that class of miss, made observable without making it blocking).
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import hook_log
            hook_log.record_fail_open("repo_doc_guard", _exc)
        except Exception:
            pass
        sys.exit(0)
