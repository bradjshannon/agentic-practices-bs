#!/usr/bin/env python3
"""Layer 2: correlate each hook FIRE (from hook_log) against what the agent did NEXT, and
report per-hook effectiveness signals. Read-only over ~/.claude/hook-events.jsonl and the
session transcripts.

WHY A SEPARATE PASS
-------------------
hook_log.py banks one fact at fire time — that a hook fired — and deliberately records NO
verdict: a hook that logged "I was necessary" would be a tool asserting its own value, the exact
misleading-report failure the philosophy warns against. Validity is not knowable at fire time; it
depends on what the agent does NEXT:

  * it reissues a corrected command / reads the doc it was told to read  -> the block CHANGED
    behaviour for the better  (call it COMPLIED)
  * it appends the override token and reruns the same thing              -> the block was WORKED
    AROUND  (call it SUSPECT — the fire may have been a false positive, or the agent may just
    have declared it fine; either way the block did not change the outcome)
  * nothing legible follows                                              -> UNKNOWN

So this pass reads each fire, opens that session's transcript, looks at the activity after the
fire's timestamp, and classifies. It aggregates per hook: fires, complied, suspect, unknown, and a
suspect-rate. A high suspect-rate on a hook with real volume is a CANDIDATE for review — it means
the hook is mostly being routed around, which is what a false-positive-heavy or theatre hook looks
like. This script FLAGS candidates; it does NOT decide a hook is worthless. Deterrence is invisible
(a hook that stops the bad action never logs a "save"), so low fires or low suspect-rate is not
proof of value either. Both directions need a human read — this just surfaces the numbers.

HEURISTIC, AND HONEST ABOUT IT
------------------------------
The override-token match is exact and reliable. The "complied" inference is heuristic (did a
plausible corrective action follow in the same session?) and is labelled as such in the output.
When the session cannot be resolved to a transcript, the fire is counted but not classified.

Usage:
  python ~/.claude/hooks/hook_rollup.py            # human-readable report
  python ~/.claude/hooks/hook_rollup.py --json     # machine-readable
  python ~/.claude/hooks/hook_rollup.py --since 2026-07-20   # only fires on/after a date
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hook-events.jsonl")
PROJECTS = os.path.expanduser("~/.claude/projects")

# Per-hook override token: presence in the agent's later activity means the block was WORKED
# AROUND rather than complied with. Exact match, so this signal is reliable.
OVERRIDE_TOKENS = {
    "output_budget": ("output-budget:ok", "output-budget:asked", "output-budget:artifact"),
    "workflow_output_to_repo": ("workflow-output:ok",),
    "lying_command_guard": ("# guard:ok", "#guard:ok"),
    "requirement_before_mechanism": ("requirement:ok", "req:ok"),
    # repo_doc_guard has no override token by design — it is satisfied only by actually Reading
    # the doc, so "complied" is inferred from a subsequent Read, never from a token.
}

# How far ahead (in transcript entries within the same session) to look for the follow-up action.
LOOKAHEAD = 40


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


def _transcript_for(session):
    if not session:
        return None
    hits = glob.glob(os.path.join(PROJECTS, "*", f"{session}.jsonl"))
    return hits[0] if hits else None


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


def _entry_text_and_tools(entry):
    """(joined assistant text, list of (tool_name, input_dict)) for one transcript entry."""
    m = entry.get("message") or {}
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
    return "\n".join(texts), tools


def classify(fire, transcript_cache):
    """Return one of 'complied' | 'suspect' | 'unknown' for a single fire."""
    session = fire.get("session")
    path = _transcript_for(session)
    if not path:
        return "unknown"
    entries = transcript_cache.get(path)
    if entries is None:
        entries = _load_transcript(path)
        transcript_cache[path] = entries
    if not entries:
        return "unknown"

    fire_ts = _parse_ts(fire.get("ts"))
    hook = fire.get("hook")
    tokens = OVERRIDE_TOKENS.get(hook, ())

    # Collect the window of activity strictly after the fire timestamp.
    after = []
    for e in entries:
        ets = _parse_ts(e.get("timestamp"))
        if fire_ts and ets and ets <= fire_ts:
            continue
        after.append(e)
        if len(after) >= LOOKAHEAD:
            break
    if not after:
        return "unknown"

    saw_override = False
    saw_corrective = False
    for e in after:
        text, tools = _entry_text_and_tools(e)
        blob = text
        for _, tin in tools:
            blob += " " + json.dumps(tin, ensure_ascii=False)
        low = blob.lower()
        if tokens and any(tok in low for tok in tokens):
            saw_override = True
            break
        # Corrective-action heuristics, per hook family.
        if hook == "repo_doc_guard":
            for name, tin in tools:
                if name == "Read":
                    fp = (tin.get("file_path") or "").lower()
                    if "claude.md" in fp or "agents.md" in fp:
                        saw_corrective = True
        elif hook in ("lying_command_guard",):
            # a subsequent Bash call = the agent reissued something (usually corrected)
            if any(name == "Bash" for name, _ in tools):
                saw_corrective = True
        else:
            # stop-hook family (output_budget, workflow_output_to_repo, requirement_*):
            # any subsequent assistant text turn = the agent proceeded under the block
            if text.strip():
                saw_corrective = True

    if saw_override:
        return "suspect"
    if saw_corrective:
        return "complied"
    return "unknown"


def rollup(since=None):
    fires = load_fires(since)
    cache = {}
    by_hook = {}
    for f in fires:
        h = f.get("hook") or "?"
        d = by_hook.setdefault(h, {
            "fires": 0, "complied": 0, "suspect": 0, "unknown": 0,
            "sessions": set(), "first": None, "last": None, "triggers": {},
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
        d[classify(f, cache)] += 1

    out = {}
    for h, d in by_hook.items():
        judged = d["complied"] + d["suspect"]
        out[h] = {
            "fires": d["fires"],
            "complied": d["complied"],
            "suspect": d["suspect"],
            "unknown": d["unknown"],
            "sessions": len(d["sessions"]),
            "first": d["first"],
            "last": d["last"],
            "suspect_rate": round(d["suspect"] / judged, 2) if judged else None,
            "top_triggers": sorted(d["triggers"].items(), key=lambda kv: -kv[1])[:3],
        }
    return out


def _fmt_report(data):
    if not data:
        return ("No hook fires recorded yet in ~/.claude/hook-events.jsonl.\n"
                "This is not evidence the hooks are useless — deterrence is invisible; a hook that\n"
                "stops the bad action before it happens never logs anything.")
    lines = []
    lines.append("HOOK FIRE ROLLUP  (observations, not verdicts)")
    lines.append("=" * 62)
    for h in sorted(data, key=lambda k: -data[k]["fires"]):
        d = data[h]
        sr = d["suspect_rate"]
        sr_s = "n/a" if sr is None else f"{sr:.0%}"
        flag = ""
        if sr is not None and sr >= 0.5 and (d["complied"] + d["suspect"]) >= 3:
            flag = "  <-- REVIEW: mostly worked around"
        lines.append(f"\n{h}{flag}")
        lines.append(f"  fires {d['fires']}  |  complied {d['complied']}  "
                     f"suspect {d['suspect']}  unknown {d['unknown']}  |  "
                     f"suspect-rate {sr_s}  |  sessions {d['sessions']}")
        if d["first"]:
            lines.append(f"  span {d['first'][:10]} .. {d['last'][:10]}")
        for trig, n in d["top_triggers"]:
            lines.append(f"    {n:>3}x  {trig}")
    lines.append("\n" + "-" * 62)
    lines.append("complied = a corrective action followed the block (HEURISTIC).")
    lines.append("suspect  = the override token appeared afterward = block worked around (EXACT).")
    lines.append("unknown  = session not resolvable, or nothing legible followed.")
    lines.append("High suspect-rate flags a hook to REVIEW; it does not condemn it. Low fires or")
    lines.append("low suspect-rate is not proof of value either — a true counterfactual needs A/B.")
    return "\n".join(lines)


def main(argv):
    since = None
    as_json = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
            i += 1
        i += 1
    data = rollup(since)
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(_fmt_report(data))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
