#!/usr/bin/env python3
"""Compare THIS workstation's mechanisms against what it has declared it means to carry.

WHY THIS EXISTS
---------------
`mechanisms/` is a catalogue. Whether a given machine *runs* a given mechanism is a separate
fact, and **whether it deliberately declined one is a third fact that nothing anywhere records.**

`mechanisms/WHERE-MECHANISMS-LIVE.md` measures the cost of that gap on one workstation: of 21
installed-or-banked hooks, one was banked, tested green, and not installed. That is *either* a
deliberate decline *or* an accidental omission, and no existing instrument can tell which --
`tools/check_guard_ledger_freshness.py` says FRESH (correct: the repo's claim holds) and the
private installed-mechanisms report says not-wired (correct: it is not running). Both right,
neither is the answer. The missing thing is a **written-down intent**, which is what
`~/.claude/mechanisms.toml` is and what this script reads.

WHAT THIS IS NOT
----------------
Not `tools/check_guard_ledger_freshness.py`. That answers "are the ledger's claims still true?"
-- a question about THIS REPO, environment-independent, which is why it runs in CI. This one
answers "is this workstation carrying the mechanisms it means to?" -- a question about a machine,
which is why its manifest cannot live in this repo (`tools/check_sanitized.py` forbids naming a
machine here) and why it is not wired into CI.

The two must never merge. Opting out of a guard does not make a failing banked test acceptable:
a machine that declines `hardware_hedge_guard` has not made the ledger's claim about that guard
any less true or false. Folding per-machine opt-out into the freshness checker would let the
thing being measured switch off the repo's own integrity check.

THE MANIFEST
------------
Authored at `~/.claude/mechanisms.toml`; **not** committed to this repo. Durability comes from
the per-host backup that mirrors an allow-list of `~/.claude` into `<HOSTNAME>/.claude/` -- the
manifest's filename has to be on that allow-list *and* un-ignored in that repo's `.gitignore`,
or it is copied and then silently not committed (that omission is silent by construction and has
already bitten twice; see that script's own comments).

    [mechanisms."hardware_hedge_guard.py"]
    want = "yes"            # "yes" | "no" | "pin:<rev>"   -- "no" is a DECISION, not a gap
    sync = "manual"         # "auto" | "manual" | "never"  -- recorded; nothing acts on it yet
    why  = "..."            # free prose, AUTHORED, never generated, preserved verbatim

VERDICTS
--------
    OK          want yes, installed, and in force here
    DECLINED    want no, and absent -- the entire point of the manifest; never counted as a gap
    MISSING     want yes, but not installed, or installed and nothing runs it
    UNDECLARED  exists in the catalogue or on this machine, no manifest row       <- fails
    UNEXPECTED  want no, but it IS installed                                      <- fails
    DRIFTED     installed and banked, contents differ                             <- fails

UNDECLARED fails on purpose, and that follows from the settled sync rule: there is an option for
auto-UPDATES but never an option for auto-ADD/REMOVE. An *add* is exactly the case where nothing
can know whether a file is new-and-wanted or declined-and-absent -- which is the question this
manifest exists to answer -- so **until a row says so, an add is a question, not an update.**

WHAT "IN FORCE" MEANS, AND WHY PRESENCE IS NOT ENOUGH
-----------------------------------------------------
A hook sitting in the hooks directory that no event dispatches is not running. So OK requires
wiring, read from the live config the same way the private installed-report does: the `hooks`
block of `settings.json` / `settings.local.json`, plus the checks a wired **dispatcher** runs
in-process (one hook wired to an event that executes several others, detected by reading its
`CHECKS` list rather than hardcoding its name here).

But wiring cannot be demanded of every file, and the obvious way to decide which is wrong. The
private report classifies by looking for an event name in the first 60 lines; on this catalogue
that marks `turn_window.py` an unwired event hook, when it is a **shared library imported by five
wired hooks** whose docstring merely says "Stop check". Reporting a control that runs on every
turn as unadopted is the misleading report this repo's own lessons forbid.

So the discriminator here is structural, not lexical: **does the file read a hook payload from
stdin?** Every event hook does; a library or hand-run CLI does not. Measured across all 21
mechanisms on the workstation this was written against, that split is exactly
`{hook_log, hook_rollup, turn_window}` on the library side and every guard on the hook side, with
no false members either way. For a library, wiring is not merely absent but *impossible*, so
presence is the whole test; the import graph is reported as supporting detail.

KNOWN HOLES (named, per this repo's bar: every control here has one, and the ones that hurt are
the ones nobody wrote down)
-----------------------------------------------------------------------------------------------
- **`.git/hooks/` per declared repo is NOT probed.** TODO, deliberately out of scope for this
  pass: it needs a declared *repo* list, which is a second manifest section and a clean second
  probe. It is the third finding in `WHERE-MECHANISMS-LIVE.md` -- a project whose brief claims in
  the present tense that a pre-commit check rejects certain commits had a seven-hook
  `.pre-commit-config.yaml` and no installed `.git/hooks/pre-commit` at all. Nothing here catches
  that; do not read a clean run as covering it.
- **Nothing acts on `sync`.** The field is parsed and validated so a value cannot be a typo, but
  hooks have no sync path at all yet, so `sync = "auto"` has nothing to execute. Recording it now
  is deliberate: the manifest is worth having before the sync exists, because it makes DECLINED
  expressible, which nothing today does.
- **`pin:<rev>` is not resolved.** It is accepted and treated as `yes` for presence and wiring;
  no revision is checked out or compared, because there is no sync path to resolve one against.
  A pinned row that has drifted still reports DRIFTED, which is the useful half.
- **Content comparison is byte-equality against the banked copy.** A mechanism installed here and
  never banked cannot drift by this test -- there is nothing to compare it to. Those are reported
  as `not banked` detail on an otherwise-OK row rather than as a failure, because banking is a
  repo action, not a workstation one.

USAGE
    python tools/check_workstation.py             # verdict per mechanism; exit 1 on any gap
    python tools/check_workstation.py --list      # ...but always exit 0
    python tools/check_workstation.py --generate  # write/extend the manifest from live state
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CATALOGUE = REPO / "mechanisms" / "hooks"
DEFAULT_CLAUDE = Path.home() / ".claude"

# Same shape the private installed-report uses, so there is one parse of "which hook is wired",
# not two that can disagree.
HOOK_PATH_RE = re.compile(r"[\w./\\~-]*hooks[/\\]([\w.-]+\.py)")
CHECKS_RE = re.compile(r"CHECKS\s*=\s*\[(.*?)\]", re.S)
PY_NAME_RE = re.compile(r"[\"']([\w.-]+\.py)[\"']")

OK, DECLINED, MISSING, UNDECLARED, UNEXPECTED, DRIFTED = (
    "OK", "DECLINED", "MISSING", "UNDECLARED", "UNEXPECTED", "DRIFTED")

# Verdicts that make the run fail. DECLINED is deliberately not here -- that is the whole feature.
FAILING = (MISSING, UNDECLARED, UNEXPECTED, DRIFTED)

# Worst-wins ordering, for a mechanism that is true of two rows at once (e.g. installed, unwired
# AND drifted). Exactly one verdict is emitted; the other fact goes in the detail column, so
# nothing is hidden by the collapse.
RANK = {OK: 0, DECLINED: 0, DRIFTED: 1, MISSING: 2, UNEXPECTED: 3, UNDECLARED: 4}

VALID_SYNC = ("auto", "manual", "never")

PLACEHOLDER_WHY = "TODO: not yet stated"


class ManifestError(Exception):
    """The manifest is unreadable or invalid -- a config fault, not a conformance failure."""


def mechanism_names(directory: Path) -> set[str]:
    """Mechanism filenames in a directory: `*.py`, excluding the `*_test.py` that verify them."""
    if not directory.is_dir():
        return set()
    return {p.name for p in directory.glob("*.py") if not p.name.endswith("_test.py")}


def wired_hooks(settings_paths: list[Path], hooks_dir: Path) -> tuple[set[str], list[str]]:
    """Hook filenames the live config actually runs, plus notes about unreadable config.

    Two ways a mechanism is in force: wired directly to an event, or named in the `CHECKS` list
    of a wired dispatcher (one hook on one event that runs several checks in-process). The
    second is read from the dispatcher's source rather than hardcoded, because a hardcoded name
    is one more thing to drift.
    """
    direct: set[str] = set()
    notes: list[str] = []
    for cfg in settings_paths:
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception as exc:
            notes.append(f"{cfg.name}: UNREADABLE ({exc}) -- its hooks are NOT represented below, "
                         f"so a clean run here is not evidence they are absent")
            continue
        for groups in (data.get("hooks") or {}).values():
            for group in groups or []:
                for hook in group.get("hooks") or []:
                    match = HOOK_PATH_RE.search(hook.get("command", ""))
                    if match:
                        direct.add(match.group(1))

    dispatched: set[str] = set()
    for name in direct:
        src = hooks_dir / name
        if not src.exists():
            notes.append(f"{name}: WIRED BUT ABSENT from {hooks_dir}")
            continue
        match = CHECKS_RE.search(src.read_text(encoding="utf-8", errors="replace"))
        if match:
            dispatched |= set(PY_NAME_RE.findall(match.group(1)))
    return direct | dispatched, notes


def reads_hook_payload(path: Path) -> bool:
    """Is this file an event hook (reads a payload on stdin) rather than a library or CLI?

    Structural, not lexical -- see the module docstring for why sniffing event *names* out of a
    docstring gets `turn_window.py` wrong in the direction that produces a misleading report.
    """
    try:
        return "stdin" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # unreadable: assume the stricter kind rather than quietly excusing it


def imported_by(name: str, hooks_dir: Path, universe: set[str]) -> list[str]:
    """Which installed mechanisms import this one. Supporting detail for a library's verdict."""
    stem = name[:-3]
    pattern = re.compile(r"^\s*(?:from\s+" + re.escape(stem) + r"\s+import\b|import\s+"
                         + re.escape(stem) + r"\b)", re.M)
    out = []
    for other in sorted(universe):
        if other == name:
            continue
        path = hooks_dir / other
        if path.exists() and pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            out.append(other)
    return out


def load_manifest(path: Path) -> dict[str, dict]:
    """Parse and validate the manifest. Raises ManifestError; never returns a partial answer."""
    if not path.exists():
        raise ManifestError(
            f"no manifest at {path}.\n"
            f"This machine has not declared what it means to carry, so nothing here can tell a\n"
            f"deliberate decline from an accidental omission -- which is the only question this\n"
            f"check exists to answer. Write one, or generate a starting point from live state:\n"
            f"    python tools/check_workstation.py --generate")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ManifestError(f"{path}: could not parse: {exc}") from exc

    rows = data.get("mechanisms")
    if not isinstance(rows, dict):
        raise ManifestError(f"{path}: expected a [mechanisms] table; found none.")

    out: dict[str, dict] = {}
    for name, row in rows.items():
        if not isinstance(row, dict):
            raise ManifestError(f"{path}: [mechanisms.\"{name}\"] must be a table.")
        want = row.get("want")
        if not isinstance(want, str) or not (
                want in ("yes", "no") or (want.startswith("pin:") and len(want) > 4)):
            raise ManifestError(
                f'{path}: [mechanisms."{name}"] want={want!r} is not "yes", "no" or "pin:<rev>".')
        sync = row.get("sync", "manual")
        if sync not in VALID_SYNC:
            raise ManifestError(
                f'{path}: [mechanisms."{name}"] sync={sync!r} is not one of {VALID_SYNC}.')
        why = row.get("why", "")
        if not isinstance(why, str):
            raise ManifestError(f'{path}: [mechanisms."{name}"] why must be a string.')
        out[name] = {"want": want, "sync": sync, "why": why}
    return out


def evaluate(catalogue: Path, hooks_dir: Path, settings_paths: list[Path],
             manifest: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Return (rows, notes). One row per mechanism, with exactly one verdict each."""
    banked = mechanism_names(catalogue)
    installed = mechanism_names(hooks_dir)
    wired, notes = wired_hooks(settings_paths, hooks_dir)

    rows = []
    for name in sorted(banked | installed | set(manifest)):
        is_banked, is_installed = name in banked, name in installed
        src = (hooks_dir / name) if is_installed else (catalogue / name)
        is_hook = src.exists() and (reads_hook_payload(src) or name in wired)
        is_wired = name in wired

        drifted = (is_banked and is_installed
                   and (catalogue / name).read_bytes() != (hooks_dir / name).read_bytes())

        row = manifest.get(name)
        detail: list[str] = []
        if row is None:
            verdict = UNDECLARED
            where = "the catalogue" if is_banked else "this machine"
            detail.append(f"present in {where}, but no manifest row says whether this machine "
                          f"wants it")
        elif row["want"] == "no":
            verdict = UNEXPECTED if is_installed else DECLINED
            if verdict == UNEXPECTED:
                detail.append(f"declared want=\"no\" but present at {hooks_dir / name}"
                              + (" and wired to an event" if is_wired else ""))
            else:
                detail.append(row["why"] or "no reason recorded")
        else:
            verdict = OK
            if not is_installed:
                verdict = MISSING
                detail.append(f"want={row['want']!r} but not installed at {hooks_dir / name}")
            elif is_hook and not is_wired:
                verdict = MISSING
                detail.append("installed, but nothing in the live config wires or dispatches it, "
                              "so it never runs")
            if drifted:
                if RANK[DRIFTED] > RANK[verdict]:
                    verdict = DRIFTED
                detail.append("installed copy differs from the banked copy "
                              f"({catalogue / name})")
            if row["want"].startswith("pin:"):
                detail.append(f"pinned to {row['want'][4:]} -- revision NOT verified "
                              f"(no sync path exists yet)")
            if is_installed and not is_banked:
                detail.append("not banked in the catalogue, so drift cannot be detected for it")
            if not is_hook:
                users = imported_by(name, hooks_dir, installed)
                detail.append("library/CLI (reads no hook payload), so wiring is impossible and "
                              "presence is the whole test"
                              + (f"; imported by {', '.join(users)}" if users else
                                 "; nothing imports it"))

        rows.append({"name": name, "verdict": verdict, "detail": detail,
                     "want": row["want"] if row else None,
                     "banked": is_banked, "installed": is_installed, "wired": is_wired,
                     "drifted": drifted})
    return rows, notes


def render_manifest_block(name: str, want: str, sync: str, why: str) -> str:
    return (f'[mechanisms."{name}"]\n'
            f'want = "{want}"\n'
            f'sync = "{sync}"\n'
            f'why  = "{why}"\n')


HEADER = """\
# This workstation's mechanism manifest -- what it MEANS to carry.
#
# Read by `tools/check_workstation.py` in the agentic-practices repo. It cannot live in that
# repo: naming a machine there is rejected by that repo's own sanitizer. Durability comes from
# the per-host backup of ~/.claude instead, so this filename must stay on that sync's INCLUDE
# allow-list AND un-ignored in its .gitignore, or it is copied and silently not committed.
#
#   want : "yes" | "no" | "pin:<rev>"   -- "no" is a DECISION. The check reports it as DECLINED,
#                                          never as MISSING. That distinction is the whole point:
#                                          a machine below par and a machine deliberately
#                                          configured differently must not render the same.
#   sync : "auto" | "manual" | "never"  -- recorded and validated; nothing acts on it yet, and
#                                          add/remove is gated regardless of what this says.
#   why  : free prose. AUTHORED, never generated. Any writer must preserve it verbatim -- the
#          mechanical half is re-derived every run, the judgement half is the half a
#          regeneration must not destroy.
#
# `--generate` appends rows for mechanisms with none, and NEVER rewrites a row that exists.
"""


def generate(manifest_path: Path, catalogue: Path, hooks_dir: Path,
             settings_paths: list[Path]) -> list[str]:
    """Write or extend the manifest from live state. Existing bytes are never touched.

    Preserving the file's existing text verbatim (rather than re-serialising a parsed model) is
    what makes `why` -- and any comment around it -- survive a round-trip byte-identical. A
    second run with no state change appends nothing and rewrites nothing.
    """
    banked = mechanism_names(catalogue)
    installed = mechanism_names(hooks_dir)
    wired, _ = wired_hooks(settings_paths, hooks_dir)
    existing = load_manifest(manifest_path) if manifest_path.exists() else {}

    added = []
    blocks = []
    for name in sorted(banked | installed):
        if name in existing:
            continue
        src = (hooks_dir / name) if name in installed else (catalogue / name)
        is_hook = src.exists() and (reads_hook_payload(src) or name in wired)
        in_force = name in installed and (name in wired or not is_hook)
        # `want` is derived from what this machine ALREADY runs -- a statement of current fact,
        # not an invented preference. `why` is left as an explicit placeholder rather than a
        # fabricated justification: an unstated reason must read as unstated.
        blocks.append(render_manifest_block(name, "yes" if in_force else "no", "manual",
                                            PLACEHOLDER_WHY))
        added.append(f'{name}  want="{"yes" if in_force else "no"}"')

    if not manifest_path.exists():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(HEADER + "\n" + "\n".join(blocks), encoding="utf-8")
    elif blocks:
        with manifest_path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + "\n".join(blocks))
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_CLAUDE / "mechanisms.toml")
    ap.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    ap.add_argument("--hooks-dir", type=Path, default=DEFAULT_CLAUDE / "hooks")
    ap.add_argument("--settings", type=Path, action="append",
                    help="a settings file to read wiring from (repeatable); defaults to "
                         "~/.claude/settings.json and settings.local.json")
    ap.add_argument("--list", action="store_true", help="print every verdict and exit 0")
    ap.add_argument("--generate", action="store_true",
                    help="write the manifest, or append rows for mechanisms that have none. "
                         "Never rewrites an existing row.")
    args = ap.parse_args(argv)

    settings = args.settings or [DEFAULT_CLAUDE / "settings.json",
                                 DEFAULT_CLAUDE / "settings.local.json"]

    if args.generate:
        try:
            added = generate(args.manifest, args.catalogue, args.hooks_dir, settings)
        except ManifestError as exc:
            print(f"check_workstation: {exc}", file=sys.stderr)
            return 2
        if added:
            print(f"{args.manifest}: added {len(added)} row(s), each `why` left as a placeholder:")
            for line in added:
                print(f"  + {line}")
            print("\nFill in every `why` by hand. A generated reason would be a fabricated one.")
        else:
            print(f"{args.manifest}: already declares every mechanism; nothing added, "
                  f"nothing rewritten.")
        return 0

    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"check_workstation: {exc}", file=sys.stderr)
        return 2

    rows, notes = evaluate(args.catalogue, args.hooks_dir, settings, manifest)

    for note in notes:
        print(f"  !! {note}")
    if notes:
        print()

    failing = [r for r in rows if r["verdict"] in FAILING]
    shown = rows if args.list else failing
    for r in sorted(shown, key=lambda r: (-RANK[r["verdict"]], r["name"])):
        print(f"{r['verdict']:11} {r['name']}")
        for line in r["detail"]:
            print(f"            {line}")

    counts = {v: sum(1 for r in rows if r["verdict"] == v)
              for v in (OK, DECLINED, MISSING, UNDECLARED, UNEXPECTED, DRIFTED)}
    summary = (f"{len(rows)} mechanism(s): "
               + ", ".join(f"{n} {v.lower()}" for v, n in counts.items()))
    # Drift is named even when it is not a mechanism's headline verdict, so collapsing to one
    # verdict per row can never make a drifted file invisible.
    drifted = [r["name"] for r in rows if r["drifted"]]
    if drifted:
        summary += f"\ndrifted from the banked copy: {', '.join(drifted)}"

    if failing:
        print()
        print("Fix, by verdict:")
        if counts[UNDECLARED]:
            print('  UNDECLARED -- this machine has no opinion on record. Nothing can tell a new '
                  'mechanism\n'
                  '                from a declined one, so it is a question, not an update. '
                  'Answer it with\n'
                  '                one row in the manifest:\n'
                  '                    [mechanisms."<name>.py"]\n'
                  '                    want = "yes"   # or "no" -- and then say why\n'
                  '                    sync = "manual"\n'
                  '                    why  = "<the judgement a regeneration must not destroy>"')
        if counts[MISSING]:
            print("  MISSING    -- declared wanted, but not installed or nothing runs it. Install "
                  "and wire it,\n"
                  "                or change the row to want=\"no\" and record why it was "
                  "declined.")
        if counts[UNEXPECTED]:
            print("  UNEXPECTED -- declared declined, but present. Remove it, or change the row "
                  "to want=\"yes\".")
        if counts[DRIFTED]:
            print("  DRIFTED    -- the running copy and the banked copy disagree. Diff them and "
                  "bank the\n"
                  "                machine's version, or restore the banked one. Nothing syncs "
                  "hooks yet.")
        print()
        print(summary)
        return 0 if args.list else 1

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
