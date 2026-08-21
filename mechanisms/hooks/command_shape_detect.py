#!/usr/bin/env python3
"""Shared: does a chunk of shell-shaped text contain POSIX idiom that will not run when pasted
into PowerShell by a Windows operator?

WHY THIS EXISTS
----------------
The operator, three messages in about two minutes, 2026-08-15: "you've GOT TO STOP giving me powershell
commands with the wrong slashes" / "it wastes turns EVERY TIME" / "EVERY powershell command I
have to tell you to fix it."

Judges, does not blindly ban. `&&`/`||` are valid PowerShell 7+ and are NOT flagged. A line that
is itself an escape into a POSIX shell (`wsl -e ...`, `docker exec ...`,
`docker compose exec ...`, `ssh ...`) is legitimate -- its payload runs inside THAT shell, not
PowerShell -- and is skipped, whole-line, from every check below.

Each violation names the exact replacement -- a block that says only "don't do that" is a bad
block (this estate's own rule).

Deliberately NARROW, matching the defect classes actually measured on the live board
(this estate's own conductor transcript log, `command` field, 2026-08-15):
  1. a Windows drive-letter path written with forward slashes (`C:/Users/...`)
  2. a piped POSIX-only filter command (`tail`, `head`, `grep`, `sed`, `awk`, `wc`, `cat`)
  3. `2>/dev/null` (or any `/dev/null` redirect target -- doesn't exist on Windows)
  4. bash-only syntax with no PowerShell equivalent as written: a no-`$`-prefix variable
     assignment feeding `$(...)` (`VAR=$(cmd)`), and backtick command substitution (`` `cmd` ``)

Not flagged, on purpose: `&&`/`||`; bare backslash paths; `$(...)` used as a PowerShell
subexpression (valid in both shells -- only the bash-assignment shape above is unambiguous);
anything on a line that escapes into a POSIX shell.
"""
from __future__ import annotations

import re

_ESCAPE_LINE = re.compile(
    r"\b(?:wsl(?:\.exe)?\s|wsl$|docker\s+(?:exec|compose\s+exec|run)\b|ssh\b)",
    re.I,
)

_DRIVE_FWDSLASH = re.compile(r"\b([A-Za-z]):(/[^\s\"'|>]*)+")

_PIPED_POSIX_FILTER = re.compile(
    r"(?:^|[|;]|&&)\s*(tail|head|grep|sed|awk|wc|cat)\b",
    re.I,
)

_DEV_NULL = re.compile(r"(\d?>>?)\s*/dev/null")

_BASH_ASSIGN_SUBST = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=\$\(([^)]*)\)")

_BACKTICK_SUBST = re.compile(r"`([^`\n]*\s[^`\n]*)`")  # contains a space -> a command, not escape

_FILTER_REPLACEMENT = {
    "tail": "Select-Object -Last N   (e.g. `tail -5` -> `Select-Object -Last 5`)",
    "head": "Select-Object -First N  (e.g. `head -5` -> `Select-Object -First 5`)",
    "grep": "Select-String",
    "sed": "-replace / Select-String, rewritten per case -- no drop-in equivalent",
    "awk": "ForEach-Object / Select-Object, rewritten per case -- no drop-in equivalent",
    "wc": "Measure-Object  (e.g. `wc -l` -> `(Get-Content file | Measure-Object -Line).Lines`)",
    "cat": "Get-Content",
}


def find_violations(text: str) -> list[dict]:
    """[{line, kind, match, suggestion}] for each PowerShell-breaking construct in `text`."""
    out: list[dict] = []
    for line in text.splitlines():
        if _ESCAPE_LINE.search(line):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        drive_hits = [m.group(0) for m in _DRIVE_FWDSLASH.finditer(line)]
        if drive_hits:
            fixed = drive_hits[0][0] + ":" + drive_hits[0][2:].replace("/", "\\")
            out.append({"line": stripped, "kind": "drive-path-forward-slash",
                        "match": drive_hits, "suggestion": f"{drive_hits[0]}  ->  {fixed}"})

        filt_hits = sorted({m.group(1).lower() for m in _PIPED_POSIX_FILTER.finditer(line)})
        if filt_hits:
            sug = "; ".join(f"{k} -> {_FILTER_REPLACEMENT[k]}" for k in filt_hits)
            out.append({"line": stripped, "kind": "posix-filter-command",
                        "match": filt_hits, "suggestion": sug})

        dn = _DEV_NULL.search(line)
        if dn:
            out.append({"line": stripped, "kind": "dev-null-redirect",
                        "match": [f"{dn.group(1)}/dev/null"],
                        "suggestion": f"{dn.group(1)}/dev/null  ->  {dn.group(1)}$null"})

        ba = _BASH_ASSIGN_SUBST.search(line)
        if ba:
            out.append({"line": stripped, "kind": "bash-assignment-substitution",
                        "match": [ba.group(0)],
                        "suggestion": f"{ba.group(0)}  ->  ${ba.group(1)} = $({ba.group(2)})"})

        bt = _BACKTICK_SUBST.search(line)
        if bt:
            out.append({"line": stripped, "kind": "backtick-command-substitution",
                        "match": [bt.group(0)], "suggestion": f"{bt.group(0)}  ->  $({bt.group(1)})"})

    return out


def format_violations(violations: list[dict]) -> str:
    lines = []
    for v in violations:
        lines.append(f"  [{v['kind']}] in: {v['line']}")
        lines.append(f"      fix: {v['suggestion']}")
    return "\n".join(lines)


# Fence languages that render with a Run button aimed at a shell. Deliberately includes
# 'powershell'/'pwsh' -- a POSIX idiom mislabeled as PowerShell is the worst case, not an exempt
# one. Excludes genuinely non-command langs (python, json, yaml, md, ...) where flagging would be
# a pure false positive.
SHELL_FENCE_LANGS = {"", "bash", "sh", "shell", "zsh", "console", "cmd", "shellsession",
                     "powershell", "pwsh", "ps1", "batch"}

_FENCE = re.compile(r"```([\w+-]*)\n(.*?)```", re.S)


def find_violations_in_fenced_blocks(text: str) -> list[dict]:
    """Same as `find_violations`, scoped to fenced code blocks in a shell-shaped language.

    A violation elsewhere in the assistant's prose (not inside a fence) is not a command anyone
    can Run, so it is not scanned -- this only fires on the copy/Run-button surface."""
    out: list[dict] = []
    for m in _FENCE.finditer(text):
        lang = m.group(1).strip().lower()
        if lang not in SHELL_FENCE_LANGS:
            continue
        out.extend(find_violations(m.group(2)))
    return out
