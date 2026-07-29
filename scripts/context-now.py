#!/usr/bin/env python
"""Report THIS session's context usage, read from the live transcript.

WHY THIS EXISTS
---------------
`statusline-context.py` relays context usage to `~/.claude/context-state.json`, but it
runs as a **statusLine** command, and statusLine only fires in the interactive terminal
UI. In a scheduled run, or in the desktop app, nothing ever calls it — so the file is
whatever the last interactive session left, indefinitely.

That is worse than having no file, because a stale reading is indistinguishable from a
current one. It has now caused two failures: a run wound down at 32% believing it was at
~70%, and a later run could not get a number at all because the file still held a **test
invocation** from six days earlier (`session_id: "test"`, `cwd: "D:/x"`).

The transcript does not have that problem. Claude Code appends every assistant message to
`~/.claude/projects/<slug>/<session-id>.jsonl`, and each carries a `usage` block. It is
written by the thing whose context we are measuring, so it cannot go stale while the
session is alive.

USE
---
    py -3 ~/.claude/context-now.py            # human line
    py -3 ~/.claude/context-now.py --json     # machine

Exits non-zero and says why if it cannot produce a trustworthy number. It never guesses:
a wrong number here is the failure it exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

#: Context window by model family. Opus 4.8 / 5 are 1M; assuming 200k overstates usage 5x.
_WINDOWS = {"opus": 1_000_000, "sonnet": 1_000_000, "haiku": 200_000}
_DEFAULT_WINDOW = 1_000_000

#: A transcript untouched for longer than this is probably not the live session.
_STALE_SECONDS = 900


def project_dir(cwd: Path) -> Path:
    """Map a working directory to its Claude Code transcript directory.

    Every character that is not alphanumeric or a dash becomes a dash — separators,
    colons **and dots**. So `D:\\GitHub\\foo\\.claude\\bar` becomes
    `D--GitHub-foo--claude-bar`: the `\\.` collapses to a double dash, which is the
    detail that makes a naive separator-only replacement miss the directory.
    """
    slug = "".join(c if (c.isalnum() or c == "-") else "-" for c in str(cwd))
    return Path.home() / ".claude" / "projects" / slug


def newest_transcript(directory: Path) -> Path | None:
    """Most recently written `.jsonl` in a project directory."""
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def last_usage(path: Path) -> dict | None:
    """The final `usage` block in a transcript.

    Read forward rather than seeking backwards: lines vary hugely in size and the last
    line is not guaranteed to carry usage.
    """
    found = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            usage = (record.get("message") or {}).get("usage")
            if usage:
                found = usage
    return found


def window_for(model: str) -> int:
    """Context window size for a model name."""
    lowered = (model or "").lower()
    for family, size in _WINDOWS.items():
        if family in lowered:
            return size
    return _DEFAULT_WINDOW


def used_tokens(usage: dict) -> int:
    """Tokens occupying the window: fresh input plus everything read from or written to cache."""
    return (int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--cwd", default=os.getcwd(), help="working directory to resolve")
    parser.add_argument("--model", default="", help="override model for window sizing")
    args = parser.parse_args()

    directory = project_dir(Path(args.cwd))
    transcript = newest_transcript(directory)
    if transcript is None:
        print(f"UNAVAILABLE: no transcript under {directory}", file=sys.stderr)
        return 2

    age = time.time() - transcript.stat().st_mtime
    usage = last_usage(transcript)
    if usage is None:
        print(f"UNAVAILABLE: no usage block in {transcript.name}", file=sys.stderr)
        return 2

    model = args.model or ""
    window = window_for(model) if model else _DEFAULT_WINDOW
    used = used_tokens(usage)
    pct = 100.0 * used / window

    payload = {
        "used_tokens": used,
        "context_window_size": window,
        "used_percentage": round(pct, 1),
        "transcript": str(transcript),
        "session_id": transcript.stem,
        "age_seconds": int(age),
        "stale": age > _STALE_SECONDS,
        "output_tokens_last_turn": int(usage.get("output_tokens") or 0),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        flag = "  ** STALE, probably not this session **" if payload["stale"] else ""
        print(f"context {pct:.1f}%  ({used/1000:.0f}k / {window/1000:.0f}k)  "
              f"session {transcript.stem[:8]}  age {int(age)}s{flag}")
    return 1 if payload["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
