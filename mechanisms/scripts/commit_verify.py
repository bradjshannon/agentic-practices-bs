#!/usr/bin/env python3
"""Commit, verify, push, verify — as ONE operation that cannot half-succeed.

WHY THIS EXISTS
---------------
2026-07-29, and it is the third instance of the same shape in one session:

    git commit -m "...\\bvideo\\b..."   -> FAILED (the escaped regex in the message
                                          was parsed as a pathspec)
    git push                            -> printed "pushed"
    composite                           -> looked exactly like success

Nothing lied. The push genuinely succeeded at pushing nothing. Only
`git show HEAD:<file>` revealed that the change was still sitting in the index.
The same evening, `archive-elf.ps1` reported success on every build while the server
rejected every upload, and a symbol archive that never existed cost two boards their
reproducibility.

**The lesson is not "check your exit codes."** Every exit code involved was correct for
the command it described. The lesson is that a MULTI-STEP operation needs its
POSTCONDITION verified, not its steps' return values — because the steps are honest
individually and wrong in composition.

WHAT THIS GUARANTEES
--------------------
On exit 0, all of the following have been OBSERVED, not assumed:

  1. Every path named was staged — and nothing else was.
  2. HEAD moved.
  3. HEAD's tree actually contains the staged content for every named path.
  4. If pushing: the remote ref now equals local HEAD.

On any failure it exits NON-ZERO and says which postcondition failed and what state
the repo is in. **It never exits 0 on partial success**, which is the whole point.

WHAT IT DELIBERATELY REFUSES
----------------------------
* **`git add -A` / `.` semantics.** Paths are explicit, always. A shared working tree
  with concurrent agents makes a bare `add -A` a race that silently sweeps another
  agent's staged work into your commit — observed seven times in one project.
* **`-m` for the message.** The message arrives via stdin or `--message-file` and is
  passed with `-F`, so no shell metacharacter, backtick, quote or backslash in prose
  can ever be reinterpreted as an argument. That is the exact bug above.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class Failed(Exception):
    """A postcondition was not met. Always exits non-zero; never swallowed."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    """Run one git command with an argv LIST — never a shell string."""
    # UTF-8 explicitly, never the locale codec: on Windows the default is cp1252,
    # which raises on the em-dashes and arrows this project's messages and paths
    # are full of. errors="replace" so a decoding surprise degrades a diagnostic
    # string rather than aborting a half-staged commit.
    #
    # core.quotepath=false is NOT cosmetic. With git's default (true) a path with
    # any byte >0x7f comes back octal-escaped and quoted —
    #   "r\303\251sum\303\251-\342\206\222.txt"
    # — which never equals the path the caller passed in, so POSTCONDITION 1 and 3
    # both report "not staged" / "not in HEAD" about files that ARE staged and ARE
    # in HEAD. Measured 2026-07-29: it exits 1 with a factually false diagnosis and
    # leaves the tree staged, i.e. the same half-done state by a different route.
    p = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise Failed(f"git {' '.join(args[:2])} failed (exit {p.returncode}): "
                     f"{(p.stderr or p.stdout).strip()}")
    return (p.stdout or "").strip()


def staged_paths(repo: Path) -> set[str]:
    out = git(repo, "diff", "--cached", "--name-only")
    return {l.strip() for l in out.splitlines() if l.strip()}


def run(repo: Path, paths: list[str], message: str, *, push: bool,
        allow_extra_staged: bool) -> int:
    if not message.strip():
        raise Failed("empty commit message — refusing")
    if not paths:
        raise Failed("no paths given — this tool never stages by wildcard")

    for rel in paths:
        if not (repo / rel).exists():
            raise Failed(f"path does not exist: {rel}")

    pre_head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    # ── stage, explicitly ──────────────────────────────────────────────────────
    git(repo, "add", "--", *paths)

    # POSTCONDITION 1: exactly what was asked for is staged.
    # An extra staged path usually means a concurrent agent's work is about to be
    # swept into this commit. That has happened repeatedly and is why this refuses
    # by default rather than warning.
    want = set(paths)
    got = staged_paths(repo)
    missing = {p for p in want if p not in got}
    extra = got - want
    unchanged: set[str] = set()
    if missing:
        # Not an error by itself: a path with no changes stages nothing.
        unchanged = {p for p in missing
                     if not git(repo, "status", "--porcelain", "--", p)}
        real = missing - unchanged
        if real:
            raise Failed(f"asked to stage {sorted(real)} but they are not staged")
        if unchanged == want:
            raise Failed("nothing to commit — every named path is unchanged")
    if extra and not allow_extra_staged:
        raise Failed(
            f"{len(extra)} path(s) staged that you did not name: {sorted(extra)[:5]}"
            + (" …" if len(extra) > 5 else "")
            + "\n  Another agent may be staging concurrently. Unstage YOUR OWN paths"
              " with `git restore --staged <path>` — never a bare reset — or re-run"
              " with --allow-extra-staged if you are certain they are yours.")

    # ── commit, message via stdin ──────────────────────────────────────────────
    # The message goes over the pipe as UTF-8 BYTES. text=True would encode it with
    # the locale codec (cp1252 on Windows) and raise UnicodeEncodeError on the first
    # em-dash — AFTER the staging above, leaving exactly the half-done state this
    # tool exists to make impossible. Bytes in, bytes out, decoded explicitly.
    p = subprocess.run(["git", "-C", str(repo), "-c", "core.quotepath=false",
                        "commit", "-F", "-"],
                       input=message.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        err = (p.stderr or p.stdout or b"").decode("utf-8", "replace")
        raise Failed(f"commit failed (exit {p.returncode}): {err.strip()}")

    # POSTCONDITION 2: HEAD actually moved. `git commit` can report success-ish
    # output in situations where it did not create a commit.
    head = git(repo, "rev-parse", "HEAD")
    if head == pre_head:
        raise Failed("commit reported success but HEAD did not move")

    # POSTCONDITION 3: HEAD's tree really contains each path. This is the check
    # that would have caught the 2026-07-29 failure — the one nothing else does.
    #
    # A path that was ALREADY IDENTICAL to HEAD is exempt, and this exemption is not a
    # loophole — it is the same tolerance POSTCONDITION 1 already grants above, applied
    # consistently. Without it the two checks contradict each other: naming a file that
    # happens to be unchanged is explicitly "not an error by itself" at staging time, and
    # then a guaranteed exit 1 here, AFTER the commit has succeeded. Measured 2026-07-29:
    # a regenerated report came out byte-identical, and the tool reported FAILURE on a
    # commit that was completely fine. A mandatory guard that cries wolf on success is how
    # a guard gets ignored, which costs its true positives too.
    #
    # The check still bites where it matters: `unchanged` is computed from `git status`
    # BEFORE the commit, so a path that had real changes and then failed to land is still
    # absent here and still raises.
    in_commit = set(git(repo, "show", "--pretty=", "--name-only",
                        head).splitlines())
    absent = [p for p in paths if p not in in_commit and p not in unchanged]
    if absent:
        raise Failed(f"HEAD {head[:8]} does not contain: {absent}")

    noted = f" ({len(unchanged)} already current)" if unchanged else ""
    print(f"committed {head[:8]} on {branch}: {len(paths)} path(s){noted}")

    if not push:
        return 0

    # ── push, then verify the REMOTE moved ─────────────────────────────────────
    git(repo, "push", "origin", branch)

    # POSTCONDITION 4: the remote ref equals local HEAD. A push that pushes
    # nothing exits 0 and prints reassuring text; only comparing the refs
    # distinguishes "pushed my work" from "there was nothing to push".
    remote = git(repo, "rev-parse", f"origin/{branch}", check=False)
    if remote != head:
        raise Failed(
            f"push reported success but origin/{branch} is {remote[:8] or '(unknown)'}"
            f", not {head[:8]}")
    print(f"pushed {head[:8]} -> origin/{branch}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Commit + verify + push + verify, as one operation that cannot "
                    "half-succeed. Message comes from stdin or --message-file, never "
                    "-m, so prose containing backticks or backslashes is safe.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", action="append", required=True, dest="paths",
                    help="repo-relative path to stage; repeatable. No wildcards.")
    ap.add_argument("--message-file", help="file holding the commit message "
                                           "(default: read stdin)")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--allow-extra-staged", action="store_true",
                    help="proceed even if paths you did not name are staged. "
                         "Only when you are certain they are yours.")
    a = ap.parse_args()

    # sys.stdin.read() decodes with the locale codec; on Windows that is cp1252 and
    # a heredoc containing an em-dash dies before staging even begins. --message-file
    # was already explicit about UTF-8; stdin now matches it, so the two input paths
    # cannot disagree about the encoding of the same message.
    message = (Path(a.message_file).read_text(encoding="utf-8")
               if a.message_file else sys.stdin.buffer.read().decode("utf-8"))
    try:
        return run(Path(a.repo).resolve(), a.paths, message,
                   push=a.push, allow_extra_staged=a.allow_extra_staged)
    except Failed as exc:
        # Loud, specific, non-zero. The failure mode this tool exists to prevent is
        # a quiet zero, so this path must never become one.
        print(f"commit_verify: FAILED — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
