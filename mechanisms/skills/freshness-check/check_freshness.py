#!/usr/bin/env python3
"""Freshness registry checker.

Reads a freshness registry (a markdown file containing a fenced ```yaml block, or a plain
.yaml/.yml file) and reports which entries are due for re-verification, based purely on
`last_checked` + `check_every_days`. The due-ness math is deterministic — no model in the loop,
no hallucinated status. Actual verification of a due entry is handed back to the caller via its
`how_to_check` instruction (or run mechanically with --run if the entry has a `check_cmd`).

Status bands: OK (< cadence) · DUE (>= cadence) · OVERDUE (>= 2x cadence) · ALWAYS (cadence <= 0).
Malformed entries (missing/!parseable last_checked or check_every_days) are surfaced, not skipped.

Exit code: 0 if nothing needs attention, 1 if any entry is due/overdue/always/malformed,
2 on usage or parse error. The exit code lets wind-down or CI gate on staleness.

--run executes each due entry's `check_cmd` via the shell. It runs commands defined IN the
registry file, so treat the registry as trusted input (it is your own repo file); do not point
this at a registry you did not author.
"""
import os
import sys
import re
import argparse
import pathlib
import subprocess
from datetime import date, datetime


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_entries(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read {path}: {e}")
    if path.endswith((".md", ".markdown")):
        # ALL fenced yaml blocks, not just the first. The registry is organised BY FILE so a
        # file's entries can be plucked out and moved with it -- which means one fence per file
        # group is the natural layout. With re.search (the original), a second block was parsed
        # as ZERO entries: silently dropped, no error, and the report still looked clean. A
        # registry that under-reports staleness without saying so is worse than no registry.
        blocks = re.findall(r"```ya?ml\s*\n(.*?)\n```", text, re.DOTALL)
        if not blocks:
            die(f"no fenced ```yaml block found in {path}")
        text = "\n".join(blocks)
    try:
        import yaml
    except ImportError:
        die("PyYAML not installed — run: pip install pyyaml")
    try:
        data = yaml.safe_load(text)
    except Exception as e:
        die(f"YAML parse failed: {e}")
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    if not isinstance(data, list):
        die("registry must be a YAML list of entries (or a dict with an 'entries' list)")
    return data


def parse_date(s):
    return datetime.strptime(str(s), "%Y-%m-%d").date()


def status_for(days_since, every):
    if every <= 0:
        return "ALWAYS"
    if days_since < every:
        return "OK"
    if days_since < 2 * every:
        return "DUE"
    return "OVERDUE"


def main():
    ap = argparse.ArgumentParser(description="Check a freshness registry for stale entries.")
    ap.add_argument("path", nargs="?", default="freshness.md",
                    help="registry file (default: freshness.md in cwd)")
    ap.add_argument("--run", action="store_true",
                    help="execute check_cmd for due/overdue entries (runs registry-defined shell)")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    ap.add_argument("--all", action="store_true", help="also list OK entries")
    args = ap.parse_args()

    today = parse_date(args.today) if args.today else date.today()
    entries = load_entries(args.path)

    rows = []
    for e in entries:
        eid = e.get("id", "?")
        every = e.get("check_every_days")
        lc = e.get("last_checked")
        if every is None or lc is None:
            rows.append((eid, "MALFORMED", None, e))
            continue
        try:
            days = (today - parse_date(lc)).days
            every_i = int(every)
        except Exception:
            rows.append((eid, "MALFORMED", None, e))
            continue
        rows.append((eid, status_for(days, every_i), days, e))

    rank = {"OVERDUE": 0, "DUE": 1, "ALWAYS": 2, "MALFORMED": 3, "OK": 4}
    rows.sort(key=lambda r: (rank.get(r[1], 9), -(r[2] or 0)))

    needs = [r for r in rows if r[1] != "OK"]
    print(f"freshness: {args.path}  (as of {today})")
    print(f"{len(needs)} of {len(rows)} entries need attention\n")

    for eid, st, days, e in rows:
        if st == "OK" and not args.all:
            continue
        age = f"{days}d since check" if days is not None else "no valid last_checked"
        every = e.get("check_every_days", "?")
        print(f"[{st:8}] {eid}  ({age}, cadence {every}d)")
        for k in ("claim", "trigger", "location", "how_to_check", "confidence"):
            if e.get(k):
                print(f"           {k}: {e[k]}")
        if args.run and st in ("DUE", "OVERDUE", "ALWAYS"):
            cmd = e.get("check_cmd")
            if cmd:
                # POSIX-shell syntax in a check_cmd is REFUSED, not run.
                # shell=True on Windows invokes cmd.exe, which does not expand $(...), ${..},
                # backticks or `&&`-with-quoting the way the author meant. Observed 2026-07-26:
                # a check_cmd comparing two version strings with [ "$(grep ...)" = "$(grep ...)" ]
                # returned NON-ZERO against two files that genuinely matched -- cmd.exe compared
                # the literal text. That is the worst failure a checker can have: a confident
                # wrong verdict on a claim that was fine, indistinguishable from a real staleness
                # hit. Refusing is the only safe answer, because there is no way to detect from
                # the exit code alone that the shell misread the command.
                bad = [t for t in ("$(", "${", "`", "&&", "||", ";") if t in cmd] \
                    if os.name == "nt" else []
                if bad:
                    print(f"           result [refused]: check_cmd uses POSIX shell syntax "
                          f"{bad} but this is Windows (cmd.exe). It would run and return a "
                          f"MEANINGLESS verdict. Use a plain argv command, or move the check "
                          f"into how_to_check.")
                    continue
                print(f"           running: {cmd}")
                try:
                    # cwd = the registry's own directory. A check_cmd is written relative
                    # to the repo that owns the registry (that is what makes the registry
                    # pluckable-with-its-files); running it from the caller's cwd made 7
                    # of 19 real entries report a false STALE on 2026-07-26.
                    out = subprocess.run(cmd, shell=True, capture_output=True,
                                         text=True, timeout=60,
                                         cwd=str(pathlib.Path(args.path).resolve().parent))
                    tag = "ok" if out.returncode == 0 else f"exit {out.returncode}"
                    body = (out.stdout or out.stderr).strip().splitlines()
                    print(f"           result [{tag}]: {body[0] if body else '(no output)'}")
                except Exception as ex:
                    print(f"           result [error]: {ex}")
        print()

    sys.exit(1 if needs else 0)


if __name__ == "__main__":
    main()
