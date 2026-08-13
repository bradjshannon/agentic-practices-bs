#!/usr/bin/env python3
"""Diagram-opportunity signal scanner — DUMB, EXPERIMENTAL, calibration-only.

WHY
---
The operator noticed a passage of their own prose (explaining hook vs. guard) had the shape of good
diagram material: definitions, a subtype relationship, a temporal/flow relationship, named
recurring entities. They asked whether that shape is machine-detectable, then asked for the
cheapest possible instrument to find out — before deciding whether a real mechanism is
worth building at all. This is that instrument. It does NOT decide anything, block anything,
or suggest anything to the user. It prints a score breakdown so a human can eyeball whether
the heuristic even correlates with "this text wants to be a diagram" before more effort goes
in. Treat every number below as noise until it's been checked against a few known-good and
known-bad passages by hand.

WHAT IT MEASURES, per assistant-authored text block since the last scan:
  - copula_defs      : "X is a/the/just Y" — definitional sentences (relationship anchors)
  - contrast         : vs / rather than / instead of / not X but Y / "is just a specific
                        pattern/case/instance of" — subtype/contrast language
  - sequence         : before / after / then / once / "at the moment" — flow/ordering language
  - enumeration      : "one of a small number", "either...or", numbered/bulleted lines
  - entity_reuse     : distinct backtick-spans (`like_this`) that recur >=2 times in the block
                        — a real graph needs nodes referenced more than once, not just named

SCORE is a plain unweighted sum of the five counts, on purpose — weighting implies confidence
this doesn't have yet. Read the breakdown, not just the total.

STATE: one JSON file per transcript (keyed by transcript path stem) under
~/.claude/diagram_signal_state/, storing the byte offset already scanned. Run it as often as
you like; it only looks at what's new since last time. Corrupt/missing state reads as
"nothing scanned yet" (offset 0), never as an error — this is a throwaway instrument, not a
system of record.

USAGE
-----
    python ~/.claude/diagram_signal_scan.py [--session SID] [--min-score N] [--quiet]

Intended to be run right alongside turn-pacer.py (same background call, e.g.
`python diagram_signal_scan.py; python turn-pacer.py --label '...'`) so it "fires with the
heartbeat" without touching the shared pacer script itself.

NOT BUILT, DELIBERATELY: any action on a high score (a suggestion, a chip, a block). This
is step 1 of "is there a signal at all" — see the conversation this was built from.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path


STATE_DIR = Path.home() / ".claude" / "diagram_signal_state"

COPULA_RE = re.compile(r"\bis (?:a|the|just|only)\b", re.IGNORECASE)
CONTRAST_RE = re.compile(
    r"\b(?:vs\.?|versus|rather than|instead of|not\s+\w+(?:\s+\w+){0,3}\s+but\s+)\b"
    r"|is just the specific (?:pattern|case|instance) of",
    re.IGNORECASE,
)
SEQUENCE_RE = re.compile(
    r"\b(?:before|after|then|once)\b.{0,40}|at the moment\b", re.IGNORECASE
)
ENUM_RE = re.compile(
    r"\bone of a small number\b|\beither\b.{0,60}\bor\b|^\s*(?:[-*]|\d+[.)])\s+",
    re.IGNORECASE | re.MULTILINE,
)
BACKTICK_RE = re.compile(r"`([^`\n]{1,80})`")


def _transcript(session_id: str | None) -> Path | None:
    """Mirrors turn-pacer.py's _transcript() — session-id-first, ambiguity-averse.

    Deliberately duplicated rather than imported: this script must survive turn-pacer.py
    being edited or absent, since it is explicitly a throwaway/experimental instrument.
    """
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return None
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get(
        "CLAUDE_SESSION_ID"
    )
    if sid:
        exact = list(root.glob(f"*/{sid}.jsonl"))
        if exact:
            return max(exact, key=lambda p: p.stat().st_mtime)
    files = list(root.glob("*/*.jsonl"))
    if not files:
        return None
    now = time.time()
    recent = [p for p in files if now - p.stat().st_mtime < 600]
    if len(recent) > 1:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _state_path(transcript: Path) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{transcript.stem}.json"


def _load_offset(transcript: Path) -> int:
    p = _state_path(transcript)
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0


def _save_offset(transcript: Path, offset: int) -> None:
    p = _state_path(transcript)
    try:
        p.write_text(json.dumps({"offset": offset}), encoding="utf-8")
    except Exception:
        pass  # throwaway instrument -- a failed save just rescans next time, harmless


def _assistant_texts_since(transcript: Path, offset: int) -> tuple[list[str], int]:
    """Return (new assistant text blocks, new byte offset). Never raises on bad lines."""
    texts: list[str] = []
    with transcript.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
        new_offset = offset + len(chunk)
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        msg = entry.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text")
                    if isinstance(t, str) and t.strip():
                        texts.append(t)
    return texts, new_offset


def _score_block(text: str) -> dict:
    copula = len(COPULA_RE.findall(text))
    contrast = len(CONTRAST_RE.findall(text))
    sequence = len(SEQUENCE_RE.findall(text))
    enumeration = len(ENUM_RE.findall(text))
    spans = BACKTICK_RE.findall(text)
    counts: dict[str, int] = {}
    for s in spans:
        counts[s] = counts.get(s, 0) + 1
    entity_reuse = sum(1 for c in counts.values() if c >= 2)
    total = copula + contrast + sequence + enumeration + entity_reuse
    return {
        "copula_defs": copula,
        "contrast": contrast,
        "sequence": sequence,
        "enumeration": enumeration,
        "entity_reuse": entity_reuse,
        "score": total,
        "chars": len(text),
        "preview": (text[:90] + "…") if len(text) > 90 else text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--session", default=None, help="Session id override")
    ap.add_argument(
        "--min-score",
        type=int,
        default=1,
        help="Only print blocks scoring >= this (default 1; use 0 to see everything scanned)",
    )
    ap.add_argument("--quiet", action="store_true", help="Print nothing when no new blocks")
    args = ap.parse_args()

    transcript = _transcript(args.session)
    if transcript is None:
        print("diagram_signal_scan: could not identify this session's transcript -- skipping")
        return 0

    offset = _load_offset(transcript)
    texts, new_offset = _assistant_texts_since(transcript, offset)
    _save_offset(transcript, new_offset)

    if not texts:
        if not args.quiet:
            print(f"diagram_signal_scan: 0 new assistant blocks since last scan ({transcript.name})")
        return 0

    results = [_score_block(t) for t in texts]
    shown = [r for r in results if r["score"] >= args.min_score]

    print(f"diagram_signal_scan: {len(texts)} new block(s), {len(shown)} scoring >= {args.min_score}")
    for r in sorted(shown, key=lambda r: -r["score"]):
        print(
            f"  score={r['score']:>2}  copula={r['copula_defs']} contrast={r['contrast']} "
            f"sequence={r['sequence']} enum={r['enumeration']} entity_reuse={r['entity_reuse']}  "
            f"({r['chars']} chars)  {r['preview']!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
