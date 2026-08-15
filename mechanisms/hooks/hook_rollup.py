#!/usr/bin/env python3
"""Layer 2: correlate each hook FIRE (from hook_log) against what the ACTOR did NEXT, and
report per-hook effectiveness signals. Read-only over ~/.claude/hook-events.jsonl and the
session/subagent transcripts.

WHY A SEPARATE PASS
-------------------
hook_log.py banks one fact at fire time — that a hook fired — and deliberately records NO
verdict: a hook that logged "I was necessary" would be a tool asserting its own value, the exact
misleading-report failure the philosophy warns against. Validity is not knowable at fire time; it
depends on what the actor does NEXT:

  * it takes the specific corrective action the hook asked for   -> COMPLIED
  * it appends the override token and reruns the same thing      -> SUSPECT (the block did not
    change the outcome; the fire may have been a false positive, or the actor may just have
    declared it fine)
  * anything else                                                -> UNCLASSIFIED, **with a
    stated reason** — see `--unclassified-reasons`.

A high suspect-rate on a hook with real volume is a CANDIDATE for review. This script FLAGS
candidates; it does NOT decide a hook is worthless. Deterrence is invisible (a hook that stops the
bad action never logs a "save"), so low fires or low suspect-rate is not proof of value either.

REPAIR, 2026-08-14 — WHAT THIS PASS USED TO GET WRONG
-----------------------------------------------------
Measured over the 23,127-fire log (2026-07-21 → 2026-08-14). The previous version reported
"complied 6,466 / suspect 44 / unknown 16,617" and a 0% suspect-rate on nearly every hook. Every
one of those three numbers was wrong, for four independent reasons:

  1. WRONG ACTOR. 10,925 fires carry an `agent_id`; 10,792 of those subagents have their own
     transcript at `<proj>/<session>/subagents/agent-<id>.jsonl` (1,197 such files on disk). The
     old resolver globbed `<proj>/<session>.jsonl` only, so half the corpus was classified
     against the PARENT's transcript — a different actor's activity — or not at all.
  2. THE LOOKAHEAD WINDOW FILLED WITH METADATA. Transcripts contain entries with no `timestamp`
     (`last-prompt`, `custom-title`, `mode`, `file-history-snapshot`, `ai-title`). The old window
     loop skipped an entry only when its timestamp was <= the fire; a MISSING timestamp fell
     through and was kept, from anywhere in the file. For 9,092 `tool_output_volume` fires the
     entire 40-entry window was `last-prompt`/`custom-title` rows carrying no message at all.
  3. THE "EXACT AND RELIABLE" OVERRIDE SIGNAL WAS NEVER ONCE AN ACTUAL OVERRIDE. All 44 suspects
     in the corpus matched the token inside the HOOK'S OWN BLOCK TEXT ("...say `requirement:ok`
     and why"), echoed back into the transcript as a user-role feedback entry. Zero were
     agent-authored. Meanwhile 943 genuine agent-authored `# guard:ok` overrides sit in the
     corpus unseen, because `lying_command_guard` logs no resolvable actor. Token matches are now
     counted ONLY in assistant-authored text or assistant tool inputs.
  4. THE DENOMINATOR MIXED INSTRUMENTS WITH GUARDS. `tool_output_volume` is 78% of all fires and
     is not a guard: its own docstring says "never blocks, never rewrites", it makes no ask, and
     nothing can comply with it. It supplied 6,066 of the 6,466 "complied". Likewise `output_budget`
     fires tagged `mode: advisory` are silent by design — the agent never saw them.

The honest consequence: the repaired classified fraction is LOWER on some hooks, not higher,
because the old "complied" was mostly the vacuous rule *any assistant text followed the fire*.
That rule is gone. A hook with no checkable corrective action now reports `no_evidence_rule`
rather than a compliance number it cannot support.

EVIDENCE RULES ARE PER HOOK AND NAMED
-------------------------------------
`EVIDENCE_RULES` below holds one function per hook that has a checkable ask. A hook absent from
that table is not silently guessed at — its fires come out unclassified with the reason
`no_evidence_rule`, which is the instrument reporting its own blind spot. Each rule states its own
strength in a comment; `reissued_command` for `lying_command_guard` is a WEAK rule (a later Bash
call is not proof the command was corrected) and is labelled as such in the output.

Usage:
  python ~/.claude/hooks/hook_rollup.py                          # human-readable report
  python ~/.claude/hooks/hook_rollup.py --unclassified-reasons   # WHY each fire is unclassified
  python ~/.claude/hooks/hook_rollup.py --json
  python ~/.claude/hooks/hook_rollup.py --since 2026-07-20
Test seams (used by hook_rollup_test.py): HOOK_ROLLUP_LOG, HOOK_ROLLUP_PROJECTS.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

LOG_PATH = os.environ.get("HOOK_ROLLUP_LOG") or os.path.expanduser("~/.claude/hook-events.jsonl")
PROJECTS = os.environ.get("HOOK_ROLLUP_PROJECTS") or os.path.expanduser("~/.claude/projects")

# Hooks that make NO ask of the agent — pure measurement. Their fires cannot be complied with or
# worked around, so classifying them is a category error. Hand-derived from each source's own
# stated contract, not guessed: tool_output_volume.py — "never blocks, never rewrites, never
# non-zero-exits"; it is a collection layer for a volume metric.
RECORDS_ONLY = {"tool_output_volume"}

# Per-hook override token: presence in ASSISTANT-AUTHORED text or tool input means the block was
# worked around. Matching anywhere else (notably the hook's own block message, which the harness
# echoes back as a user-role entry) is what made every historical "suspect" false.
OVERRIDE_TOKENS = {
    "output_budget": ("output-budget:ok", "output-budget:asked", "output-budget:artifact"),
    "workflow_output_to_repo": ("workflow-output:ok",),
    "lying_command_guard": ("# guard:ok", "#guard:ok"),
    "wsl_docker_process_guard": ("# guard:ok", "#guard:ok"),
    "requirement_before_mechanism": ("requirement:ok", "req:ok"),
    "subagent_background_wait_guard": ("# bg:ok", "#bg:ok"),
    # repo_doc_guard has no override token by design — it is satisfied only by actually Reading
    # the doc, so "complied" is inferred from a subsequent Read, never from a token.
}

# How far ahead (in message-bearing transcript entries, same actor) to look for the follow-up.
LOOKAHEAD = 40

# Ids that are test fixtures rather than real actors. These come from hook test suites that
# append to the REAL log (397 rows measured 2026-08-14) — they are corpus contamination, and are
# reported as their own reason rather than silently dropped or silently counted.
_SYNTHETIC = re.compile(r"^(tmp|L2[A-Z]+-|smoke-|a\d{1,3}$|a99887766554)|(-SESSION$)|TEST", re.I)

REASONS = (
    "records_only_hook",        # the hook makes no ask; nothing to comply with
    "silent_fire",              # fire produced no agent-visible output (mode: advisory)
    "synthetic_test_fire",      # actor id is a test fixture, not a real run
    "no_actor_id",              # neither session nor agent_id was recorded at fire time
    "actor_transcript_missing",  # id recorded, no transcript on disk (pruned, or a logging bug)
    "actor_transcript_empty",
    "no_activity_after_fire",   # transcript resolved, but nothing followed the fire
    "no_evidence_rule",         # this pass has no checkable rule for this hook — BLIND SPOT
    "rule_found_no_evidence",   # rule ran over real activity and saw neither signal
)


def _parse_ts(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def load_fires(since=None):
    fires = []
    if not os.path.exists(LOG_PATH):
        return fires
    with open(LOG_PATH, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if since and (row.get("ts") or "") < since:
                continue
            fires.append(row)
    return fires


_INDEX = None


def build_index(force=False):
    """{'sessions': {id: path}, 'agents': {agent_id: path}} — built once, not globbed per fire.

    Subagent transcripts live at <proj>/<session>/subagents/[workflows/wf_*/]agent-<id>.jsonl.
    The old resolver never looked there, which is repair reason 1 in the module docstring.
    """
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    sessions, agents = {}, {}
    for p in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        sessions.setdefault(os.path.basename(p)[:-6], p)
    for p in glob.glob(os.path.join(PROJECTS, "**", "agent-*.jsonl"), recursive=True):
        agents.setdefault(os.path.basename(p)[6:-6], p)
    _INDEX = {"sessions": sessions, "agents": agents}
    return _INDEX


def _load_transcript(path):
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return entries


def _entry_parts(entry):
    """(role, assistant_text, [(tool_name, input_dict)]) for one transcript entry.

    Role matters: the harness echoes a hook's own block message back as a user-role entry, so a
    token found there is the HOOK talking, not the agent.
    """
    m = entry.get("message") or {}
    role = m.get("role")
    content = m.get("content")
    texts, tools = [], []
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                texts.append(b.get("text") or "")
            elif b.get("type") == "tool_use":
                tools.append((b.get("name"), b.get("input") or {}))
    elif isinstance(content, str):
        texts.append(content)
    return role, "\n".join(texts), tools


def _authored_blob(entry):
    """Everything the ASSISTANT wrote in this entry (text + tool inputs). '' for other roles."""
    role, text, tools = _entry_parts(entry)
    if role != "assistant":
        return ""
    return text + " " + " ".join(json.dumps(t, ensure_ascii=False) for _, t in tools)


def _window(entries, fire_ts):
    """Message-bearing entries strictly after the fire, in order, capped at LOOKAHEAD.

    Entries with no parseable timestamp are DROPPED, not kept: they are `last-prompt`,
    `custom-title`, `mode`, `file-history-snapshot` metadata rows with no message, and the old
    code let them fill the whole window (repair reason 2).
    """
    out = []
    for e in entries:
        ets = _parse_ts(e.get("timestamp"))
        if ets is None:
            continue
        if fire_ts and ets <= fire_ts:
            continue
        if not (e.get("message") or {}).get("role"):
            continue
        out.append(e)
        if len(out) >= LOOKAHEAD:
            break
    return out


# ---------------------------------------------------------------- evidence rules, one per hook
# Each returns "complied" | None. Suspect is decided globally by the override token (assistant-
# authored only) before these run. A hook with no entry here is NOT guessed at.

def _ev_repo_doc_guard(window):
    # STRONG: the ask is literally "read this repo's guidance", and a Read of it is visible.
    for e in window:
        role, _, tools = _entry_parts(e)
        if role != "assistant":
            continue
        for name, tin in tools:
            if name == "Read":
                fp = (tin.get("file_path") or "").lower()
                if "claude.md" in fp or "agents.md" in fp:
                    return "complied"
    return None


_REQ_LINE = re.compile(r"^\s*requirement\s*:", re.I | re.M)


def _ev_requirement_before_mechanism(window):
    # STRONG: the ask is "write a line starting with 'Requirement:'". Exact, and agent-authored.
    for e in window:
        role, text, _ = _entry_parts(e)
        if role == "assistant" and _REQ_LINE.search(text or ""):
            return "complied"
    return None


def _ev_lying_command_guard(window):
    # WEAK, and labelled weak in the report: a later Bash call means the actor reissued
    # SOMETHING. It is not proof the command was corrected. Kept because it is the signal the
    # original pass used; do not read it as a compliance rate.
    for e in window:
        role, _, tools = _entry_parts(e)
        if role == "assistant" and any(n in ("Bash", "PowerShell") for n, _ in tools):
            return "complied"
    return None


_POLL_TOOLS = {"BashOutput", "Monitor", "TaskOutput", "KillShell"}


def _ev_subagent_background_wait_guard(window):
    # STRONG-ish: the ask is "poll it to completion before ending your turn", and a poll is a
    # distinct tool call. Absence is NOT evidence of non-compliance — the actor may have polled
    # past the window — so absence returns None (unclassified), never "suspect".
    for e in window:
        role, _, tools = _entry_parts(e)
        if role == "assistant" and any(n in _POLL_TOOLS for n, _ in tools):
            return "complied"
    return None


EVIDENCE_RULES = {
    "repo_doc_guard": _ev_repo_doc_guard,
    "requirement_before_mechanism": _ev_requirement_before_mechanism,
    "lying_command_guard": _ev_lying_command_guard,
    "wsl_docker_process_guard": _ev_lying_command_guard,  # same shape: block, reissue, override
    "subagent_background_wait_guard": _ev_subagent_background_wait_guard,
}
WEAK_RULES = {"lying_command_guard", "wsl_docker_process_guard"}


def resolve_actor(fire):
    """(path, actor_kind, reason_or_None). The ACTING agent's transcript wins over the session's."""
    idx = build_index()
    agent = fire.get("agent_id")
    session = fire.get("session")
    if agent and _SYNTHETIC.search(agent):
        return None, "agent", "synthetic_test_fire"
    if session and _SYNTHETIC.search(session):
        return None, "session", "synthetic_test_fire"
    if agent:
        p = idx["agents"].get(agent)
        if p:
            return p, "agent", None
    if session:
        p = idx["sessions"].get(session)
        if p:
            return p, "session", None
        return None, "session", "actor_transcript_missing"
    if agent:
        return None, "agent", "actor_transcript_missing"
    return None, None, "no_actor_id"


def classify(fire, cache):
    """('complied'|'suspect'|'unclassified', reason_or_rule_name)."""
    hook = fire.get("hook") or "?"
    if hook in RECORDS_ONLY:
        return "unclassified", "records_only_hook"
    if (fire.get("mode") or "") == "advisory":
        return "unclassified", "silent_fire"

    path, _kind, reason = resolve_actor(fire)
    if reason:
        return "unclassified", reason
    entries = cache.get(path)
    if entries is None:
        entries = _load_transcript(path)
        cache[path] = entries
    if not entries:
        return "unclassified", "actor_transcript_empty"

    window = _window(entries, _parse_ts(fire.get("ts")))
    if not window:
        return "unclassified", "no_activity_after_fire"

    tokens = OVERRIDE_TOKENS.get(hook, ())
    if tokens:
        for e in window:
            low = _authored_blob(e).lower()
            if low and any(tok in low for tok in tokens):
                return "suspect", "override_token_assistant_authored"

    rule = EVIDENCE_RULES.get(hook)
    if rule is None:
        return "unclassified", "no_evidence_rule"
    if rule(window) == "complied":
        return "complied", rule.__name__[4:]
    return "unclassified", "rule_found_no_evidence"


def rollup(since=None):
    fires = load_fires(since)
    cache = {}
    by_hook = {}
    for f in fires:
        h = f.get("hook") or "?"
        d = by_hook.setdefault(h, {
            "fires": 0, "complied": 0, "suspect": 0, "unclassified": 0,
            "sessions": set(), "first": None, "last": None, "triggers": {}, "reasons": {},
        })
        d["fires"] += 1
        if f.get("session"):
            d["sessions"].add(f["session"])
        ts = f.get("ts")
        if ts:
            d["first"] = ts if d["first"] is None else min(d["first"], ts)
            d["last"] = ts if d["last"] is None else max(d["last"], ts)
        trig = (f.get("trigger") or "")[:60]
        d["triggers"][trig] = d["triggers"].get(trig, 0) + 1
        verdict, why = classify(f, cache)
        d[verdict] += 1
        if verdict == "unclassified":
            d["reasons"][why] = d["reasons"].get(why, 0) + 1

    out = {}
    for h, d in by_hook.items():
        judged = d["complied"] + d["suspect"]
        out[h] = {
            "fires": d["fires"],
            "complied": d["complied"],
            "suspect": d["suspect"],
            "unclassified": d["unclassified"],
            "classified_fraction": round(judged / d["fires"], 3) if d["fires"] else None,
            "sessions": len(d["sessions"]),
            "first": d["first"],
            "last": d["last"],
            "suspect_rate": round(d["suspect"] / judged, 2) if judged else None,
            "judged_denominator": judged,
            "weak_rule": h in WEAK_RULES,
            "unclassified_reasons": sorted(d["reasons"].items(), key=lambda kv: -kv[1]),
            "top_triggers": sorted(d["triggers"].items(), key=lambda kv: -kv[1])[:3],
        }
    return out


def _fmt_report(data, show_reasons=False):
    if not data:
        return ("No hook fires recorded yet in ~/.claude/hook-events.jsonl.\n"
                "This is not evidence the hooks are useless — deterrence is invisible; a hook that\n"
                "stops the bad action before it happens never logs anything.")
    tot_f = sum(d["fires"] for d in data.values())
    tot_c = sum(d["complied"] for d in data.values())
    tot_s = sum(d["suspect"] for d in data.values())
    lines = []
    lines.append("HOOK FIRE ROLLUP  (observations, not verdicts)")
    lines.append("=" * 62)
    lines.append(f"corpus: {tot_f} fires from {os.path.basename(LOG_PATH)}  |  "
                 f"classified {tot_c + tot_s} ({(tot_c + tot_s) / tot_f:.1%} of {tot_f}): "
                 f"{tot_c} complied, {tot_s} suspect")
    for h in sorted(data, key=lambda k: -data[k]["fires"]):
        d = data[h]
        sr = d["suspect_rate"]
        sr_s = "n/a" if sr is None else f"{sr:.0%} of {d['judged_denominator']} judged"
        flag = ""
        if sr is not None and sr >= 0.5 and d["judged_denominator"] >= 3:
            flag = "  <-- REVIEW: mostly worked around"
        if d["complied"] and h in WEAK_RULES:
            flag += "  [complied rule is WEAK]"
        lines.append(f"\n{h}{flag}")
        lines.append(f"  fires {d['fires']}  |  complied {d['complied']}  "
                     f"suspect {d['suspect']}  unclassified {d['unclassified']}  |  "
                     f"suspect-rate {sr_s}  |  sessions {d['sessions']}")
        if d["first"]:
            lines.append(f"  span {d['first'][:10]} .. {d['last'][:10]}")
        if show_reasons:
            for why, n in d["unclassified_reasons"]:
                lines.append(f"    unclassified: {n:>6}x  {why}")
        else:
            for trig, n in d["top_triggers"]:
                lines.append(f"    {n:>3}x  {trig}")
    lines.append("\n" + "-" * 62)
    lines.append("complied = the hook's SPECIFIC corrective action followed, by the acting agent.")
    lines.append("suspect  = the override token appeared in ASSISTANT-authored text afterward.")
    lines.append("unclassified = everything else, and it always has a stated reason:")
    lines.append("               run --unclassified-reasons to see the breakdown per hook.")
    lines.append("A hook with no evidence rule reports `no_evidence_rule` — that is this pass's")
    lines.append("own blind spot, not a compliance result. Absence of `suspect` is not precision.")
    lines.append("High suspect-rate flags a hook to REVIEW; it does not condemn it. Low fires or")
    lines.append("low suspect-rate is not proof of value either — a true counterfactual needs A/B.")
    return "\n".join(lines)


def main(argv):
    since = None
    as_json = False
    reasons = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--unclassified-reasons":
            reasons = True
        elif a == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
            i += 1
        i += 1
    data = rollup(since)
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(_fmt_report(data, show_reasons=reasons))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
