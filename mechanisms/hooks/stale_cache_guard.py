#!/usr/bin/env python3
"""PreToolUse guard — never read a plugin CACHE copy when an editable SOURCE exists.

THE FAILURE THIS PREVENTS, paid for 2026-08-01. A conductor needed the `conductor-winddown`
skill. `Skill(conductor-winddown)` answered `Unknown skill`, so it searched the filesystem,
found the file under `~/.claude/plugins/cache/...`, read it, and executed a wind-down against
instructions **two days stale**: the cache copy was 277 lines dated 07-24, while the editable
source in `conductor-bs/skills/` was 307 lines dated 07-26. The stale copy put the context
start gun at the wrong number and, worse, **omitted a required `<!-- winddown: <ISO> -->`
marker** that the status page reads to tell the human a run has handed off. The handoff was
written without it and looked complete.

Nothing announced any of that. Both files are real, both parse, and the cache path looks
authoritative precisely because it lives under `~/.claude`.

WHY A GUARD AND NOT A RULE. The conductor was actively being careful when it happened — it had
spent the run building machinery about measurement provenance. A rule of the form "remember to
prefer the repo source" is Voluntary class and would have lost to the fact that the cache path
is what `find` returns first. This fires at the moment of the read, on an agent that never read
any rule.

CONTRACT
  - Fires on Read and on Bash (the cache is just as easily read with sed/head/cat).
  - DENIES only when a newer-or-different source copy actually exists. A cache read with no
    counterpart is allowed — plenty of plugin content has no local repo.
  - Names the exact replacement path. A block that only says "don't" makes the agent guess.
  - FAIL-OPEN on any internal error. A bug here must never block reading.
"""
import glob
import hashlib
import json
import os
import re
import sys

# Where editable sources live. Checked in order; first hit wins.
SOURCE_ROOTS = [os.path.expanduser("~/Documents/GitHub")]
CACHE_MARKERS = (os.path.join("plugins", "cache"), "plugins/cache")


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _digest(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def _cache_paths_in(text):
    """Every path-like token that lives under a plugin cache."""
    out = []
    for tok in re.findall(r"[A-Za-z]:[\\/][^\s'\"]+|/[^\s'\"]+|~[^\s'\"]+", text or ""):
        t = tok.strip("'\"`,;)")
        norm = t.replace("\\", "/")
        if any(m.replace("\\", "/") in norm for m in CACHE_MARKERS):
            out.append(os.path.expanduser(t))
    return out


def _find_source(cache_path):
    """Find an editable counterpart for a cached file.

    Matches on the tail of the path (…/skills/<name>/SKILL.md), not just the basename --
    every skill's file is called SKILL.md, so a basename match would collide constantly.
    """
    norm = os.path.normpath(cache_path).replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return None
    # At least TWO components. A bare-basename match was the first version's bug: every skill's
    # file is called SKILL.md, so `~/Documents/GitHub/*/**/SKILL.md` matched an unrelated repo
    # and the guard denied a cache file that had no counterpart at all. A guard that cries wolf
    # gets disabled and takes its true positives with it, so the match must be specific enough
    # to mean something.
    tails = []
    for n in (3, 2):                          # skills/<name>/SKILL.md, then <name>/SKILL.md
        if len(parts) >= n:
            tails.append("/".join(parts[-n:]))
    for root in SOURCE_ROOTS:
        if not os.path.isdir(root):
            continue
        for tail in tails:                   # most specific tail first
            hits = glob.glob(os.path.join(root, "*", "**", *tail.split("/")), recursive=True)
            hits = [h for h in hits
                    if "plugins/cache" not in h.replace("\\", "/")
                    and os.path.isfile(h)]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:                # ambiguous: prefer the newest, but say so
                return max(hits, key=lambda h: os.path.getmtime(h))
    return None


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}

    # Escape hatch, honoured before anything else: an agent that MEANS to read the cache
    # (to diff it, or to inspect what a plugin actually shipped) says so explicitly, and the
    # use is visible in the transcript rather than silent.
    if "# cache:ok" in (ti.get("command") or ""):
        allow()

    candidates = []
    if tool == "Read":
        fp = ti.get("file_path") or ""
        if fp:
            candidates = _cache_paths_in(fp)
    elif tool == "Bash":
        candidates = _cache_paths_in(ti.get("command") or "")
    if not candidates:
        allow()

    for cache_path in candidates:
        if not os.path.isfile(cache_path):
            continue
        src = _find_source(cache_path)
        if not src:
            continue                          # no counterpart: the cache IS the only copy
        if _digest(src) == _digest(cache_path):
            continue                          # identical content; reading either is fine
        c_m, s_m = os.path.getmtime(cache_path), os.path.getmtime(src)
        try:
            c_n = sum(1 for _ in open(cache_path, encoding="utf-8", errors="replace"))
            s_n = sum(1 for _ in open(src, encoding="utf-8", errors="replace"))
            sizes = f"\n  cache: {c_n} lines   source: {s_n} lines"
        except OSError:
            sizes = ""
        newer = "SOURCE is newer" if s_m > c_m else "cache is newer (source may be behind — check both)"
        deny(
            "Blocked: that path is a PLUGIN CACHE copy, and an editable source exists whose "
            "contents DIFFER.\n\n"
            f"  cache : {cache_path}\n"
            f"  source: {src}\n"
            f"  {newer}{sizes}\n\n"
            "Read the SOURCE. On 2026-08-01 a conductor read a cached skill that was two days "
            "stale, and executed a wind-down missing a required status-page marker — both files "
            "were real and neither announced the difference.\n\n"
            "If you genuinely need the cached copy (e.g. to diff them), append '# cache:ok' to a "
            "Bash command, or read the source first and then the cache."
        )
    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        allow()   # FAIL-OPEN: a bug in this guard must never block reading
