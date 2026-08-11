#!/usr/bin/env python3
"""Compare the copies of each mechanism across two or more directories, and REPORT. Nothing else.

WHAT THIS IS FOR
----------------
`mechanisms/WHERE-MECHANISMS-LIVE.md` says almost everything here that actually *runs* exists in
at least two places at once -- a machine copy that is live and a repo copy that is durable -- and
its own table answers "kept in sync by" for guard hooks with: **"Nothing, currently. Found live
this session: a hook had a rule on the machine that had never been banked. No tool detects this;
a human or an agent has to think to `diff` the two files."**

This is that tool. `mechanisms/SCOPE-AND-VENDORING.md` specifies it, including the build order and
the reason for it: *"The cheapest instrument is a content comparison between the banked copy and
the installed copy, per mechanism ... The manifest adds exactly one thing on top: the ability to
distinguish DECLINED from MISSING ... but it is the second increment, not the first. A manifest
without a comparator records intentions nobody checks."*

IT REPORTS. IT DOES NOT DECIDE, SYNC, ADOPT, OR WRITE ANYTHING.
---------------------------------------------------------------
It never writes to any copy, never proposes a merge direction, and never names a side as
authoritative. That is not timidity -- it is the only defensible behaviour, because **sanitisation
and drift are indistinguishable to a differ.** A public copy of a mechanism is legitimately
stripped of machine- and project-specific detail; a stale copy is legitimately behind. Both render
as "these two files differ", and no amount of heuristic separates them. In particular this tool
does not treat "one copy is shorter" as evidence of anything: a shorter copy is equally consistent
with sanitisation, with a feature not yet carried across, and with a feature deliberately declined.

The output is a list for a human to route. Any tool that guessed a direction here would eventually
guess wrong on a file somebody had just improved.

FIVE VERDICTS, AND THE LAST THREE ARE THE POINT
------------------------------------------------
    IDENTICAL        present in every copy, all equal once line endings are normalised
    DIFFERENT        present in every copy, they differ -- reported with a MAGNITUDE, see below
    MISSING          present in at least one copy and absent from at least one other
    AMBIGUOUS        one copy contains this mechanism TWICE, so there is no single subject
    COULD-NOT-CHECK  present somewhere but a file could not be read

`MISSING` is a finding, never a skip. A mechanism in the bank and not on the machine, or on the
machine and never banked, is exactly the population this repo has been bitten by in both
directions -- and a tool that quietly compared only the intersection would have reported a clean
table over both of them.

`AMBIGUOUS` exists because the first version of this tool did not have it, and that version was
wrong on its first real run. A copy may span several directories (see `collect`), and when the
same mechanism name resolves in two of them there is no single subject to compare -- so the tool
silently picked the first and reported a verdict that was really a verdict about its own
tie-break. Measured: one mechanism was banked in two directories, one of those copies matched the
machine exactly and the other was eighty lines apart, and the tie-break decided which of those two
true statements got printed. Choosing a subject IS deciding which side is authoritative, one level
down from where this tool refuses to do it, so it reports the collision instead.

`COULD-NOT-CHECK` is never folded into `IDENTICAL`. Same rule one layer down, and the same rule
this repo applies to every other instrument: a check that could not evaluate its subject must not
be indistinguishable from one that evaluated it and found nothing wrong.

WHY LINE ENDINGS ARE NORMALISED, AND WHY NOTHING ELSE IS
---------------------------------------------------------
The naive implementation is a byte comparison, and on the population this was written for it is
**useless**: line endings differ per file and per copy, so a byte differ reports every file as
100% changed and the real divergence stays invisible underneath. That is measured, not
hypothetical -- it is how this went unnoticed.

Normalisation stops there, deliberately. Stripping trailing whitespace, comments or blank lines
would each be a judgement about what "the same mechanism" means, and every one of them can hide a
real difference. CRLF-vs-LF cannot: no mechanism's behaviour depends on it. (Splitting into lines
also makes a missing final newline invisible, which is the same class of non-difference.)

MAGNITUDE, NOT A BOOLEAN
-------------------------
Two copies at 0.59 similarity and two copies at 0.31 are different situations -- the first is
plausibly a few edits, the second is closer to a rewrite -- and a same/different boolean hides
exactly the information that decides which to look at first. So every `DIFFERENT` row carries a
similarity ratio and a changed-line count, and names the WORST-AGREEING PAIR when there are more
than two roots.

    similarity     `difflib.SequenceMatcher` ratio over normalised LINES, so 1.0 is identical and
                   0.0 shares no line. Lines, not characters: the unit a reader diffs in.
    changed lines  additions plus deletions in a unified diff of the same two line lists.

State the ruler when quoting a number from this tool. A similarity computed over characters, or a
changed-line count taken from a byte diff, will not reconcile with these, and that is a units
mismatch rather than a disagreement about the files.

EXIT CODES -- the estate's 0 / 1 / 2 contract
----------------------------------------------
    0  every mechanism is present in every root and identical
    1  something to report: at least one DIFFERENT or MISSING
    2  could not check: at least one copy exists and could not be read

Exit 2 outranks exit 1. An instrument that could not see its subject must not report a backlog it
did not actually measure.

DELIBERATELY NOT WIRED INTO ANY GATE (yet)
-------------------------------------------
Landing this as a pre-commit or CI gate while a known, unresolved divergence exists would redden
every commit over unrelated work, and a gate that fails for a reason its author cannot act on
right now gets bypassed -- `SCOPE-AND-VENDORING.md` records that exact outcome for a suite wired
too broadly, and the bypass takes the true positives with it. It exits non-zero so it CAN gate,
once the population it reports is a population somebody has decided about.

USAGE
-----
    python tools/compare_mechanism_copies.py --dir bank=<path> --dir installed=<path>
    python tools/compare_mechanism_copies.py --dir a=<p> --dir b=<p> --dir c=<p> --json
    python tools/compare_mechanism_copies.py --dir a=<p> --dir b=<p> --include '*.py' --all

Roots are labelled because the labels are what the report is read in. No root is special; the
order they are given is the order the columns appear, and that is the only meaning order has.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import sys
from pathlib import Path

IDENTICAL = "IDENTICAL"
DIFFERENT = "DIFFERENT"
MISSING = "MISSING"
AMBIGUOUS = "AMBIGUOUS"
COULD_NOT_CHECK = "COULD-NOT-CHECK"

#: Never compared, in any root. Compiler output is derived from a source this tool already reads,
#: so reporting it would be reporting the same divergence twice -- once truthfully and once as an
#: unreadable binary blob.
ALWAYS_EXCLUDED = ("__pycache__", "*.pyc", "*.pyo", ".DS_Store")

DEFAULT_INCLUDE = ("*.py",)


def normalise(text: str) -> list[str]:
    """A file as comparable LINES: line endings normalised, nothing else touched.

    See the module docstring for why the normalisation stops here. `splitlines` is what makes a
    CR, CRLF or LF file compare equal, and incidentally makes a missing final newline invisible.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").splitlines()


def _excluded(rel: Path) -> bool:
    parts = rel.parts
    for pattern in ALWAYS_EXCLUDED:
        if any(fnmatch.fnmatch(p, pattern) for p in parts):
            return True
    return False


def collect(roots: list[Path], include: tuple[str, ...]) -> tuple[dict[str, Path], list[str]]:
    """`({relative-path-as-posix: absolute path}, ambiguities)` for one labelled COPY.

    A copy is a LIST of directories, not one directory, and that is not a convenience -- it is the
    fix for a false negative this corpus has already recorded. `SCOPE-AND-VENDORING.md`: two hooks
    lived in `mechanisms/scripts/` rather than `mechanisms/hooks/` despite being event hooks, and
    *"a survey conducted by directory concluded both were unbanked and machine-only. They were
    neither."* One logical copy that is physically split across directories, compared against one
    that is not, produces MISSING rows for files that are present -- the instrument reporting a
    finding that is an artifact of its own input shape.

    Keyed by path relative to its own root rather than by bare filename, so roots that organise
    into subdirectories are compared like with like. A root that does not exist contributes
    nothing -- the caller turns that into MISSING rows, which is a finding, not a crash.

    One name resolving in more than one of a label's directories is returned as an AMBIGUITY
    rather than silently resolved: the first wins so the run can continue, but a copy that exists
    twice under one label is a fact about the tree that the reader has to see.
    """
    out: dict[str, Path] = {}
    ambiguous: dict[str, list[str]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if _excluded(rel):
                continue
            if not any(fnmatch.fnmatch(rel.name, pat) for pat in include):
                continue
            key = rel.as_posix()
            if key in out:
                ambiguous.setdefault(key, [str(out[key])]).append(str(path))
                continue
            out[key] = path
    return out, ambiguous


def read_lines(path: Path) -> tuple[list[str] | None, str | None]:
    """`(lines, None)` or `(None, reason)`. An unreadable file NEVER returns empty lines --
    that would make it compare identical to another unreadable file and land in the OK bucket,
    which is the exact failure this tool's own docstring forbids one layer up."""
    try:
        return normalise(path.read_text(encoding="utf-8", errors="strict")), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def changed_line_count(a: list[str], b: list[str]) -> int:
    """Additions + deletions in a unified diff of two line lists, headers excluded."""
    n = 0
    for line in difflib.unified_diff(a, b, n=0, lineterm=""):
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            n += 1
    return n


def similarity(a: list[str], b: list[str]) -> float:
    """SequenceMatcher ratio over LINES. 1.0 identical, 0.0 no shared line."""
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def compare_one(name: str, copies: dict[str, Path], labels: list[str],
                doubled_in: dict[str, list[str]] | None = None) -> dict:
    """One mechanism across every copy. Returns a row; decides no direction and ranks no side."""
    row: dict = {
        "mechanism": name,
        "present_in": [],
        "absent_from": [],
        "unreadable_in": {},
        "doubled_in": dict(doubled_in or {}),
        "lines": {},
    }
    contents: dict[str, list[str]] = {}
    for label in labels:
        path = copies.get(label)
        if path is None:
            row["absent_from"].append(label)
            continue
        lines, err = read_lines(path)
        if lines is None:
            row["unreadable_in"][label] = err
            continue
        row["present_in"].append(label)
        row["lines"][label] = len(lines)
        contents[label] = lines

    if row["unreadable_in"]:
        row["verdict"] = COULD_NOT_CHECK
        return row

    # WORST-AGREEING PAIR, not "the first pair" and not an average. With more than two roots the
    # useful number is how far apart the two furthest copies are; an average would let one
    # in-step pair mask a rewritten third copy.
    worst: tuple[float, str, str, int] | None = None
    present = row["present_in"]
    for i, la in enumerate(present):
        for lb in present[i + 1:]:
            ratio = similarity(contents[la], contents[lb])
            changed = changed_line_count(contents[la], contents[lb])
            if worst is None or ratio < worst[0]:
                worst = (ratio, la, lb, changed)
    if worst is not None:
        row["similarity"] = round(worst[0], 3)
        row["worst_pair"] = [worst[1], worst[2]]
        row["changed_lines"] = worst[3]

    # AMBIGUOUS outranks MISSING and DIFFERENT: if the tool had to pick which of two same-named
    # files IS the copy, every number below it describes that pick as much as it describes the
    # tree. Reporting it as a plain DIFFERENT would launder a tie-break into a measurement.
    if row["doubled_in"]:
        row["verdict"] = AMBIGUOUS
    elif row["absent_from"]:
        row["verdict"] = MISSING
    elif worst is not None and worst[0] < 1.0:
        row["verdict"] = DIFFERENT
    else:
        row["verdict"] = IDENTICAL
    return row


def compare(roots: dict[str, list[Path]], include: tuple[str, ...]) -> list[dict]:
    """Every mechanism named in ANY copy, compared across all of them.

    The union, never the intersection: comparing only what both sides happen to have is blind to
    a mechanism one side does not have at all, which is half of what this exists to find.
    """
    labels = list(roots)
    found: dict[str, dict[str, Path]] = {}
    doubled: dict[str, dict[str, list[str]]] = {}
    for label, paths in roots.items():
        found[label], amb = collect(_as_list(paths), include)
        for key, where in amb.items():
            doubled.setdefault(key, {})[label] = where
    names = sorted({n for m in found.values() for n in m})
    return [compare_one(n, {lab: found[lab][n] for lab in labels if n in found[lab]}, labels,
                        doubled.get(n))
            for n in names]


def _as_list(paths) -> list[Path]:
    """One directory or several. Callers (and tests) may pass either; the tool's own CLI always
    passes a list."""
    return [paths] if isinstance(paths, Path) else list(paths)


def ambiguities(roots: dict[str, list[Path]], include: tuple[str, ...]) -> dict[str, dict]:
    """`{label: {name: [both paths]}}` for every name resolving twice under one label."""
    out: dict[str, dict] = {}
    for label, paths in roots.items():
        _, amb = collect(_as_list(paths), include)
        if amb:
            out[label] = amb
    return out


def exit_code(rows: list[dict]) -> int:
    """0 clean / 1 something to report / 2 could not check. 2 outranks 1 -- see the docstring."""
    if any(r["verdict"] == COULD_NOT_CHECK for r in rows):
        return 2
    if any(r["verdict"] in (DIFFERENT, MISSING, AMBIGUOUS) for r in rows):
        return 1
    return 0


def format_report(rows: list[dict], labels: list[str], show_all: bool,
                  roots: dict[str, list[Path]] | None = None) -> str:
    """The table. Identical rows are summarised rather than listed unless `--all`: a report whose
    signal is buried in forty OK lines is a report nobody reads to the bottom of."""
    out: list[str] = []
    counts = {v: sum(1 for r in rows if r["verdict"] == v)
              for v in (IDENTICAL, DIFFERENT, MISSING, AMBIGUOUS, COULD_NOT_CHECK)}
    out.append("copies compared (order is presentation only -- no copy is authoritative):")
    for label in labels:
        paths = (roots or {}).get(label) or []
        if paths:
            out.append(f"    {label:<12} {paths[0]}")
            for extra in paths[1:]:
                out.append(f"    {'':<12} {extra}")
        else:
            out.append(f"    {label}")
    out.append("")
    out.append(f"{len(rows)} mechanism(s): "
               + ", ".join(f"{v}={counts[v]}" for v in
                           (IDENTICAL, DIFFERENT, MISSING, AMBIGUOUS, COULD_NOT_CHECK)))
    out.append("")

    interesting = [r for r in rows
                   if show_all or r["verdict"] != IDENTICAL]
    if not interesting:
        out.append("Every mechanism is present in every root and identical.")
        return "\n".join(out)

    width = max(len(r["mechanism"]) for r in interesting)
    for r in sorted(interesting, key=lambda r: (r["verdict"], r.get("similarity", 1.0),
                                                r["mechanism"])):
        head = f"  {r['verdict']:<16}{r['mechanism']:<{width}}"
        if r["verdict"] == COULD_NOT_CHECK:
            detail = "; ".join(f"{k}: {v}" for k, v in r["unreadable_in"].items())
            out.append(f"{head}  unreadable in {detail}")
            continue
        if r["verdict"] == AMBIGUOUS:
            for label, paths in r["doubled_in"].items():
                out.append(f"{head}  {label} contains it {len(paths)} times: "
                           + " AND ".join(paths))
            out.append(f"{'':<18}{'':<{width}}  no single subject to compare -- "
                       "picking one would be deciding which copy is authoritative")
            continue
        bits = []
        if r["absent_from"]:
            bits.append("absent from " + ", ".join(r["absent_from"]))
            bits.append("present in " + ", ".join(r["present_in"]))
        if "similarity" in r and r["similarity"] < 1.0:
            a, b = r["worst_pair"]
            bits.append(f"similarity {r['similarity']:.3f} ({a} vs {b}), "
                        f"{r['changed_lines']} changed line(s)")
        if r["lines"]:
            bits.append("lines " + ", ".join(f"{k}={v}" for k, v in r["lines"].items()))
        out.append(f"{head}  " + "; ".join(bits))
    return "\n".join(out)


def parse_dir(spec: str) -> tuple[str, Path]:
    """`LABEL=PATH`. The label is required rather than derived from the path, because a path is a
    machine fact and the report has to be legible to someone who does not have this filesystem."""
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            f"--dir needs LABEL=PATH (got {spec!r}); the label names the copy in the report")
    label, _, raw = spec.partition("=")
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError(f"--dir needs a non-empty label (got {spec!r})")
    return label, Path(raw.strip()).expanduser()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Report how the copies of each mechanism differ across two or more "
                    "directories. Reports only: never writes, never syncs, never picks a side.")
    parser.add_argument("--dir", dest="dirs", action="append", type=parse_dir, metavar="LABEL=PATH",
                        help="a labelled copy to compare; give it at least twice")
    parser.add_argument("--include", action="append", metavar="GLOB",
                        help=f"filename globs to compare (default: {' '.join(DEFAULT_INCLUDE)})")
    parser.add_argument("--all", action="store_true",
                        help="list IDENTICAL mechanisms too, not just the ones with a finding")
    parser.add_argument("--json", action="store_true", help="machine-readable rows on stdout")
    args = parser.parse_args(argv)

    if not args.dirs or len(args.dirs) < 2:
        parser.error("give --dir at least twice; comparing one copy to nothing is not a comparison")

    # A REPEATED LABEL IS ONE COPY SPREAD OVER SEVERAL DIRECTORIES, not an error. See `collect`:
    # rejecting it was this tool's own first design and it produced a false MISSING on its first
    # real run, for the same reason the corpus already records -- a logical copy split across two
    # directories, compared against one that is not.
    roots: dict[str, list[Path]] = {}
    labels: list[str] = []
    for label, path in args.dirs:
        if label not in roots:
            roots[label] = []
            labels.append(label)
        roots[label].append(path)

    if len(labels) < 2:
        parser.error("give at least two DIFFERENT labels; comparing one copy to itself is not a "
                     "comparison (repeat a label only to spread one copy over several directories)")

    missing_roots = [f"{lab} -> {p}" for lab in labels for p in roots[lab] if not p.is_dir()]

    include = tuple(args.include) if args.include else DEFAULT_INCLUDE
    rows = compare(roots, include)
    amb = ambiguities(roots, include)

    if args.json:
        print(json.dumps({"roots": {k: [str(p) for p in v] for k, v in roots.items()},
                          "include": list(include),
                          "missing_roots": missing_roots,
                          "ambiguous": amb,
                          "rows": rows}, indent=2))
    else:
        if missing_roots:
            # A root that is not a directory at all is louder than any single row, and it is
            # reported BEFORE the table: every mechanism will read MISSING from it, and that is
            # one fact about a path, not N findings about N mechanisms.
            print("WARNING: root(s) that are not directories -- every mechanism will read "
                  "MISSING from them:", file=sys.stderr)
            for entry in missing_roots:
                print(f"      {entry}", file=sys.stderr)
            print(file=sys.stderr)
        if amb:
            print("WARNING: name(s) resolving in more than one directory of one copy; the first "
                  "was used:", file=sys.stderr)
            for label, entries in amb.items():
                for entry in entries:
                    print(f"      {label}: {entry}", file=sys.stderr)
            print(file=sys.stderr)
        print(format_report(rows, labels, args.all, roots))

    return exit_code(rows)


if __name__ == "__main__":
    raise SystemExit(main())
