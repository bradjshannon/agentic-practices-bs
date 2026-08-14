#!/usr/bin/env python3
"""Verify every sentence of the pre-edit CLAUDE.md 'SDK note' section appears
verbatim in EITHER the rewritten section OR docs/sdk-resolution-history.md.

Usage: python3 verify_sentences.py <orig_section.txt> <new_claude_md.md> <history_doc.md>

Method: a deterministic, shared tokenizer splits each document into "sentence"
units (code blocks kept atomic; blockquote/list markers stripped; prose split on
terminal punctuation). The ORIGINAL section's sentence set must be a subset of the
union of the NEW section's and the HISTORY doc's sentence sets, after whitespace
normalization. Reports the exact count of any sentence NOT found in either -- the
number that matters is 0.
"""
import re
import sys


def extract_sdk_section(text: str) -> str:
    """Given a full CLAUDE.md, return the '## SDK note' section (that heading to EOF)."""
    idx = text.index("## SDK note")
    return text[idx:]


def tokenize(text: str):
    """Split markdown prose into a list of normalized 'sentence' strings.

    - Fenced code blocks (```...```) are kept as single atomic tokens (their
      content must not be sentence-split -- it's not prose).
    - Blockquote ('> ') and list markers ('- ', '* ', '1. ') are stripped from
      line starts before joining into paragraphs.
    - Headings ('#'+) are kept as their own atomic token.
    - Paragraphs (runs of non-blank lines) are joined with a space, then split
      into sentences on '.', '!', '?', or ':' followed by whitespace and a
      capital/digit/markdown-emphasis/quote character.
    """
    lines = text.split("\n")
    tokens = []
    para_lines = []
    in_code = False
    code_buf = []

    def flush_para():
        if not para_lines:
            return
        para = " ".join(para_lines).strip()
        para_lines.clear()
        if not para:
            return
        # Split into sentences.
        parts = re.split(r'(?<=[.!?:])\s+(?=[A-Z0-9"`\'*_⚠️✅⛔(])', para)
        for p in parts:
            p = p.strip()
            if p:
                tokens.append(p)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                flush_para()
                in_code = True
                code_buf = [line]
            else:
                code_buf.append(line)
                tokens.append("\n".join(code_buf))
                code_buf = []
                in_code = False
            continue
        if in_code:
            code_buf.append(line)
            continue
        if stripped == "" or stripped == "---":
            flush_para()
            continue
        if stripped.startswith("#"):
            flush_para()
            tokens.append(stripped)
            continue
        if re.match(r'^\|.*\|$', stripped):
            # Table row -- atomic (not prose to sentence-split).
            flush_para()
            tokens.append(stripped)
            continue
        # Strip leading blockquote markers (possibly nested: "> > ").
        s = stripped
        while s.startswith(">"):
            s = s[1:].lstrip()
        # Strip leading list markers.
        s = re.sub(r'^(?:[-*]\s+|\d+\.\s+)', '', s)
        if s == "":
            flush_para()
            continue
        para_lines.append(s)
    flush_para()
    return tokens


def normalize(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def main():
    orig_path, new_claude_path, history_path = sys.argv[1:4]

    with open(orig_path, "r", encoding="utf-8") as f:
        orig_full_text = f.read()
    orig_text = extract_sdk_section(orig_full_text)
    with open(new_claude_path, "r", encoding="utf-8") as f:
        new_claude_text = f.read()
    with open(history_path, "r", encoding="utf-8") as f:
        history_text = f.read()

    new_section_text = extract_sdk_section(new_claude_text)

    orig_tokens = [normalize(t) for t in tokenize(orig_text)]
    new_tokens = set(normalize(t) for t in tokenize(new_section_text))
    history_tokens = set(normalize(t) for t in tokenize(history_text))

    union = new_tokens | history_tokens

    missing = []
    for t in orig_tokens:
        if t not in union:
            missing.append(t)

    print(f"original section sentence/unit count: {len(orig_tokens)}")
    print(f"new section sentence/unit count:       {len(new_tokens)}")
    print(f"history doc sentence/unit count:        {len(history_tokens)}")
    print(f"unaccounted (in neither new section nor history doc): {len(missing)}")
    if missing:
        print()
        print("=== UNACCOUNTED SENTENCES (first 30) ===")
        for m in missing[:30]:
            print(f"  - {m[:200]}")
        sys.exit(1)
    else:
        print("OK: every original sentence/unit is present in the new section or the history doc.")
        sys.exit(0)


if __name__ == "__main__":
    main()
